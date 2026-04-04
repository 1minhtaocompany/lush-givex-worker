"""Tests for Phase 9 Task 1: Safe Point Architecture.

Validates that:
  - ALLOWED_WORKER_STATES contains exactly {IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT}
  - State transitions follow _VALID_TRANSITIONS strictly (no skip, no implicit)
  - set_worker_state() rejects unknown states and illegal transitions
  - get_worker_state() / get_all_worker_states() return correct snapshots
  - is_safe_to_control() returns True only when all workers are IDLE or SAFE_POINT
  - _worker_fn tracks state transitions (IDLE → IN_CYCLE → SAFE_POINT)
  - get_status() exposes worker_states
  - reset() clears worker_states
  - Behavior Decision Engine is read-only (does not mutate worker state)
  - Lifecycle states (INIT/RUNNING/STOPPING/STOPPED) unchanged
  - Thread-safety under concurrent access
"""

import threading
import time
import unittest

from integration import runtime
from integration.runtime import (
    ALLOWED_STATES,
    ALLOWED_WORKER_STATES,
    _VALID_TRANSITIONS,
    get_all_worker_states,
    get_status,
    get_worker_state,
    is_safe_to_control,
    reset,
    set_worker_state,
    start_worker,
    stop_worker,
)
from modules.behavior import main as behavior
from modules.monitor import main as monitor
from modules.rollout import main as rollout


class SafePointResetMixin:
    """Common setUp/tearDown for safe point tests."""

    def setUp(self):
        reset()
        rollout.reset()
        monitor.reset()
        behavior.reset()

    def tearDown(self):
        reset()
        rollout.reset()
        monitor.reset()
        behavior.reset()


# ── Worker state model ───────────────────────────────────────────


class TestWorkerStateModel(SafePointResetMixin, unittest.TestCase):
    """ALLOWED_WORKER_STATES must define exactly the required states."""

    def test_allowed_worker_states(self):
        """ALLOWED_WORKER_STATES == {IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT}."""
        self.assertEqual(
            ALLOWED_WORKER_STATES,
            {"IDLE", "IN_CYCLE", "CRITICAL_SECTION", "SAFE_POINT"},
        )

    def test_lifecycle_states_unchanged(self):
        """Lifecycle ALLOWED_STATES remain {INIT, RUNNING, STOPPING, STOPPED}."""
        self.assertEqual(
            ALLOWED_STATES,
            {"INIT", "RUNNING", "STOPPING", "STOPPED"},
        )

    def test_valid_transitions_complete(self):
        """Every ALLOWED_WORKER_STATE has an entry in _VALID_TRANSITIONS."""
        for state in ALLOWED_WORKER_STATES:
            self.assertIn(state, _VALID_TRANSITIONS)

    def test_transition_targets_are_valid(self):
        """Every transition target is an ALLOWED_WORKER_STATE."""
        for src, targets in _VALID_TRANSITIONS.items():
            for tgt in targets:
                self.assertIn(tgt, ALLOWED_WORKER_STATES,
                              f"invalid target {tgt} from {src}")


# ── State transitions ────────────────────────────────────────────


class TestStateTransitions(SafePointResetMixin, unittest.TestCase):
    """set_worker_state must enforce transition rules strictly."""

    def _register_worker(self, wid="test-w"):
        """Register a fake worker in IDLE state."""
        with runtime._lock:
            runtime._workers[wid] = threading.current_thread()
            runtime._worker_states[wid] = "IDLE"
        return wid

    def test_idle_to_in_cycle(self):
        """IDLE → IN_CYCLE is allowed."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        self.assertEqual(get_worker_state(wid), "IN_CYCLE")

    def test_in_cycle_to_critical_section(self):
        """IN_CYCLE → CRITICAL_SECTION is allowed."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        self.assertEqual(get_worker_state(wid), "CRITICAL_SECTION")

    def test_in_cycle_to_safe_point(self):
        """IN_CYCLE → SAFE_POINT is allowed."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "SAFE_POINT")
        self.assertEqual(get_worker_state(wid), "SAFE_POINT")

    def test_critical_section_to_safe_point(self):
        """CRITICAL_SECTION → SAFE_POINT is allowed."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        set_worker_state(wid, "SAFE_POINT")
        self.assertEqual(get_worker_state(wid), "SAFE_POINT")

    def test_critical_section_to_in_cycle(self):
        """CRITICAL_SECTION → IN_CYCLE is allowed (re-entering cycle)."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        set_worker_state(wid, "IN_CYCLE")
        self.assertEqual(get_worker_state(wid), "IN_CYCLE")

    def test_safe_point_to_idle(self):
        """SAFE_POINT → IDLE is allowed."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "SAFE_POINT")
        set_worker_state(wid, "IDLE")
        self.assertEqual(get_worker_state(wid), "IDLE")

    def test_safe_point_to_in_cycle(self):
        """SAFE_POINT → IN_CYCLE is allowed (next cycle)."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "SAFE_POINT")
        set_worker_state(wid, "IN_CYCLE")
        self.assertEqual(get_worker_state(wid), "IN_CYCLE")

    def test_skip_idle_to_critical_section_rejected(self):
        """IDLE → CRITICAL_SECTION is NOT allowed (skip state)."""
        wid = self._register_worker()
        with self.assertRaises(ValueError):
            set_worker_state(wid, "CRITICAL_SECTION")

    def test_skip_idle_to_safe_point_rejected(self):
        """IDLE → SAFE_POINT is NOT allowed (skip state)."""
        wid = self._register_worker()
        with self.assertRaises(ValueError):
            set_worker_state(wid, "SAFE_POINT")

    def test_in_cycle_to_idle_rejected(self):
        """IN_CYCLE → IDLE is NOT allowed (must go through SAFE_POINT)."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        with self.assertRaises(ValueError):
            set_worker_state(wid, "IDLE")

    def test_critical_section_to_idle_rejected(self):
        """CRITICAL_SECTION → IDLE is NOT allowed (must go through SAFE_POINT)."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        with self.assertRaises(ValueError):
            set_worker_state(wid, "IDLE")

    def test_unknown_state_rejected(self):
        """set_worker_state rejects unknown state names."""
        wid = self._register_worker()
        with self.assertRaises(ValueError):
            set_worker_state(wid, "RUNNING")

    def test_empty_state_rejected(self):
        """set_worker_state rejects empty string."""
        wid = self._register_worker()
        with self.assertRaises(ValueError):
            set_worker_state(wid, "")

    def test_unknown_worker_rejected(self):
        """set_worker_state rejects worker_id not in _workers."""
        with self.assertRaises(ValueError):
            set_worker_state("nonexistent-worker", "IN_CYCLE")


# ── State query ──────────────────────────────────────────────────


class TestStateQuery(SafePointResetMixin, unittest.TestCase):
    """get_worker_state / get_all_worker_states correctness."""

    def test_unknown_worker_returns_none(self):
        """get_worker_state for unknown worker returns None."""
        self.assertIsNone(get_worker_state("nonexistent"))

    def test_get_all_returns_snapshot(self):
        """get_all_worker_states returns a copy, not a reference."""
        with runtime._lock:
            runtime._worker_states["w1"] = "IDLE"
            runtime._worker_states["w2"] = "IN_CYCLE"
        snap = get_all_worker_states()
        self.assertEqual(snap, {"w1": "IDLE", "w2": "IN_CYCLE"})
        # Mutating the snapshot must not affect internal state
        snap["w3"] = "SAFE_POINT"
        self.assertIsNone(get_worker_state("w3"))


# ── is_safe_to_control ───────────────────────────────────────────


class TestIsSafeToControl(SafePointResetMixin, unittest.TestCase):
    """Control actions only permitted at IDLE or SAFE_POINT."""

    def _register(self, wid, state):
        with runtime._lock:
            runtime._workers[wid] = threading.current_thread()
            runtime._worker_states[wid] = state

    def test_no_workers_is_safe(self):
        """No workers → safe to control."""
        self.assertTrue(is_safe_to_control())

    def test_all_idle_is_safe(self):
        """All workers IDLE → safe to control."""
        self._register("w1", "IDLE")
        self._register("w2", "IDLE")
        self.assertTrue(is_safe_to_control())

    def test_all_safe_point_is_safe(self):
        """All workers SAFE_POINT → safe to control."""
        self._register("w1", "SAFE_POINT")
        self._register("w2", "SAFE_POINT")
        self.assertTrue(is_safe_to_control())

    def test_mix_idle_safe_point_is_safe(self):
        """Mix of IDLE and SAFE_POINT → safe to control."""
        self._register("w1", "IDLE")
        self._register("w2", "SAFE_POINT")
        self.assertTrue(is_safe_to_control())

    def test_in_cycle_is_not_safe(self):
        """Any worker IN_CYCLE → NOT safe to control."""
        self._register("w1", "SAFE_POINT")
        self._register("w2", "IN_CYCLE")
        self.assertFalse(is_safe_to_control())

    def test_critical_section_is_not_safe(self):
        """Any worker CRITICAL_SECTION → NOT safe to control."""
        self._register("w1", "IDLE")
        self._register("w2", "CRITICAL_SECTION")
        self.assertFalse(is_safe_to_control())

    def test_missing_state_is_not_safe(self):
        """Active worker with missing state entry → NOT safe to control."""
        with runtime._lock:
            runtime._workers["w1"] = threading.current_thread()
            # Deliberately do NOT set _worker_states["w1"]
        self.assertFalse(is_safe_to_control())


# ── Worker lifecycle integration ─────────────────────────────────


class TestWorkerStateLifecycle(SafePointResetMixin, unittest.TestCase):
    """_worker_fn must track worker state transitions."""

    def _poll_until(self, predicate, timeout=2, interval=0.01):
        """Poll *predicate* until it returns True or *timeout* expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return predicate()

    def test_worker_reaches_safe_point(self):
        """Worker enters SAFE_POINT after successful task execution."""
        task_started = threading.Event()
        allow_task_exit = threading.Event()

        def task_fn(_wid):
            task_started.set()
            allow_task_exit.wait(timeout=2)

        runtime._state = "RUNNING"
        wid = start_worker(task_fn)
        try:
            self.assertTrue(task_started.wait(timeout=2))
            allow_task_exit.set()
            self.assertTrue(
                self._poll_until(lambda: get_worker_state(wid) == "SAFE_POINT"),
                "Expected worker to reach SAFE_POINT",
            )
        finally:
            stop_worker(wid, timeout=2)
            runtime._state = "INIT"

    def test_worker_state_cleaned_on_stop(self):
        """Worker state removed from _worker_states when worker stops."""
        barrier = threading.Event()

        def task_fn(_wid):
            barrier.wait(timeout=2)

        runtime._state = "RUNNING"
        wid = start_worker(task_fn)
        self.assertTrue(
            self._poll_until(lambda: get_worker_state(wid) is not None),
            "Worker state should be set after start",
        )
        barrier.set()
        stop_worker(wid, timeout=2)
        self.assertTrue(
            self._poll_until(lambda: get_worker_state(wid) is None),
            "Worker state should be cleaned up after stop",
        )
        runtime._state = "INIT"

    def test_worker_state_cleaned_on_error(self):
        """Worker state removed when task raises an exception."""
        started = threading.Event()

        def crash_fn(_wid):
            started.set()
            raise RuntimeError("boom")

        runtime._state = "RUNNING"
        wid = start_worker(crash_fn)
        started.wait(timeout=2)
        self.assertTrue(
            self._poll_until(lambda: get_worker_state(wid) is None),
            "Worker state should be cleaned up after crash",
        )
        runtime._state = "INIT"


# ── get_status exposes worker_states ─────────────────────────────


class TestStatusExposesWorkerStates(SafePointResetMixin, unittest.TestCase):
    """get_status() must include worker_states for control layer visibility."""

    def test_status_contains_worker_states_key(self):
        """get_status() returns dict with 'worker_states' key."""
        status = get_status()
        self.assertIn("worker_states", status)
        self.assertIsInstance(status["worker_states"], dict)

    def test_status_worker_states_reflects_active(self):
        """worker_states in get_status() reflects active worker states."""
        barrier = threading.Event()

        def task_fn(_wid):
            barrier.wait(timeout=2)

        runtime._state = "RUNNING"
        wid = start_worker(task_fn)
        # State is initialized synchronously in start_worker; no sleep needed
        status = get_status()
        self.assertIn(wid, status["worker_states"])
        self.assertIn(status["worker_states"][wid], ALLOWED_WORKER_STATES)
        barrier.set()
        stop_worker(wid, timeout=2)
        runtime._state = "INIT"


# ── reset clears worker_states ───────────────────────────────────


class TestResetClearsWorkerStates(SafePointResetMixin, unittest.TestCase):
    """reset() must clear _worker_states."""

    def test_reset_empties_worker_states(self):
        """After reset(), get_all_worker_states() is empty."""
        with runtime._lock:
            runtime._worker_states["fake-w"] = "IDLE"
        reset()
        self.assertEqual(get_all_worker_states(), {})


# ── Behavior engine is read-only ─────────────────────────────────


class TestBehaviorReadOnly(SafePointResetMixin, unittest.TestCase):
    """Behavior Decision Engine must NOT mutate worker state."""

    def test_evaluate_does_not_change_worker_states(self):
        """behavior.evaluate() does not alter _worker_states."""
        with runtime._lock:
            runtime._worker_states["w1"] = "IN_CYCLE"
        before = get_all_worker_states()
        behavior.evaluate(
            {"error_rate": 0.0, "success_rate": 1.0,
             "restarts_last_hour": 0, "baseline_success_rate": 1.0},
            0, 3,
        )
        after = get_all_worker_states()
        self.assertEqual(before, after)


# ── Thread safety ────────────────────────────────────────────────


class TestSafePointThreadSafety(SafePointResetMixin, unittest.TestCase):
    """Concurrent state transitions must not corrupt state."""

    def test_concurrent_set_worker_state(self):
        """Parallel set_worker_state calls must not crash or corrupt."""
        errors = []
        N = 10

        def cycle(idx):
            wid = f"tw-{idx}"
            try:
                with runtime._lock:
                    runtime._workers[wid] = threading.current_thread()
                    runtime._worker_states[wid] = "IDLE"
                for _ in range(20):
                    set_worker_state(wid, "IN_CYCLE")
                    set_worker_state(wid, "CRITICAL_SECTION")
                    set_worker_state(wid, "SAFE_POINT")
                    set_worker_state(wid, "IDLE")
            except Exception as exc:
                errors.append(str(exc))
            finally:
                with runtime._lock:
                    runtime._workers.pop(wid, None)
                    runtime._worker_states.pop(wid, None)

        threads = [threading.Thread(target=cycle, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])

    def test_concurrent_is_safe_to_control(self):
        """is_safe_to_control() under contention must not crash."""
        errors = []
        results = []

        def reader():
            try:
                for _ in range(50):
                    results.append(is_safe_to_control())
            except Exception as exc:
                errors.append(str(exc))

        def writer():
            wid = "tw-writer"
            try:
                with runtime._lock:
                    runtime._workers[wid] = threading.current_thread()
                    runtime._worker_states[wid] = "IDLE"
                for _ in range(50):
                    set_worker_state(wid, "IN_CYCLE")
                    set_worker_state(wid, "SAFE_POINT")
                    set_worker_state(wid, "IDLE")
            except Exception as exc:
                errors.append(str(exc))
            finally:
                with runtime._lock:
                    runtime._workers.pop(wid, None)
                    runtime._worker_states.pop(wid, None)

        threads = (
            [threading.Thread(target=reader) for _ in range(3)]
            + [threading.Thread(target=writer)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        # results should contain only booleans
        for r in results:
            self.assertIsInstance(r, bool)


# ── Full transition path ─────────────────────────────────────────


class TestFullTransitionPath(SafePointResetMixin, unittest.TestCase):
    """Explicit transition: IN_CYCLE → CRITICAL_SECTION → SAFE_POINT."""

    def _register_worker(self, wid="path-w"):
        with runtime._lock:
            runtime._workers[wid] = threading.current_thread()
            runtime._worker_states[wid] = "IDLE"
        return wid

    def test_full_cycle_path(self):
        """IDLE → IN_CYCLE → CRITICAL_SECTION → SAFE_POINT → IDLE."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        self.assertEqual(get_worker_state(wid), "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        self.assertEqual(get_worker_state(wid), "CRITICAL_SECTION")
        set_worker_state(wid, "SAFE_POINT")
        self.assertEqual(get_worker_state(wid), "SAFE_POINT")
        set_worker_state(wid, "IDLE")
        self.assertEqual(get_worker_state(wid), "IDLE")

    def test_critical_section_blocks_control(self):
        """Worker in CRITICAL_SECTION → is_safe_to_control() is False."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "CRITICAL_SECTION")
        self.assertFalse(is_safe_to_control())

    def test_safe_point_allows_control(self):
        """Worker in SAFE_POINT → is_safe_to_control() is True."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        set_worker_state(wid, "SAFE_POINT")
        self.assertTrue(is_safe_to_control())

    def test_in_cycle_blocks_control(self):
        """Worker in IN_CYCLE → is_safe_to_control() is False."""
        wid = self._register_worker()
        set_worker_state(wid, "IN_CYCLE")
        self.assertFalse(is_safe_to_control())


if __name__ == "__main__":
    unittest.main()
