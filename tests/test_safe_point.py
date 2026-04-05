"""Tests for Task 9.1 — Safe Point Architecture (Worker Execution State)."""
import threading
import time
import unittest
import unittest.mock

from integration import runtime
from integration.runtime import (
    ALLOWED_WORKER_STATES,
    _VALID_TRANSITIONS,
    get_active_workers,
    get_all_worker_states,
    get_worker_state,
    is_safe_to_control,
    reset,
    set_worker_state,
    start_worker,
    stop_worker,
)
from modules.monitor import main as monitor
from modules.rollout import main as rollout


WARMUP_DELAY = 0.2
CLEANUP_TIMEOUT = 2
_THREAD_CLEANUP_DELAY = 0.05


def _poll_until(predicate, timeout=2, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class SafePointResetMixin:
    def setUp(self):
        reset()
        rollout.reset()
        monitor.reset()
        # Allow daemon threads from prior tests to finish cleanup.
        time.sleep(_THREAD_CLEANUP_DELAY)

    def tearDown(self):
        reset()
        rollout.reset()
        monitor.reset()


def _register_fake_worker(worker_id, initial_state="IDLE"):
    """Register a fake worker entry (no real thread) for unit testing."""
    with runtime._lock:
        runtime._workers[worker_id] = threading.Thread()
        runtime._worker_states[worker_id] = initial_state


def _unregister_fake_worker(worker_id):
    """Remove a fake worker entry."""
    with runtime._lock:
        runtime._workers.pop(worker_id, None)
        runtime._worker_states.pop(worker_id, None)


# ── Constants ────────────────────────────────────────────────────


class TestAllowedWorkerStates(SafePointResetMixin, unittest.TestCase):
    """Validate ALLOWED_WORKER_STATES constant."""

    def test_contains_exactly_four_states(self):
        self.assertEqual(ALLOWED_WORKER_STATES, {"IDLE", "IN_CYCLE", "CRITICAL_SECTION", "SAFE_POINT"})

    def test_is_a_set(self):
        self.assertIsInstance(ALLOWED_WORKER_STATES, set)


class TestValidTransitions(SafePointResetMixin, unittest.TestCase):
    """Validate _VALID_TRANSITIONS mapping."""

    def test_idle_transitions(self):
        self.assertEqual(_VALID_TRANSITIONS["IDLE"], {"IN_CYCLE"})

    def test_in_cycle_transitions(self):
        self.assertEqual(_VALID_TRANSITIONS["IN_CYCLE"], {"CRITICAL_SECTION", "SAFE_POINT", "IDLE"})

    def test_critical_section_transitions(self):
        self.assertEqual(_VALID_TRANSITIONS["CRITICAL_SECTION"], {"IN_CYCLE"})

    def test_safe_point_transitions(self):
        self.assertEqual(_VALID_TRANSITIONS["SAFE_POINT"], {"IN_CYCLE", "IDLE"})

    def test_all_states_have_transitions(self):
        for state in ALLOWED_WORKER_STATES:
            self.assertIn(state, _VALID_TRANSITIONS, f"Missing transitions for {state}")

    def test_all_targets_are_valid_states(self):
        for source, targets in _VALID_TRANSITIONS.items():
            for target in targets:
                self.assertIn(target, ALLOWED_WORKER_STATES, f"Invalid target {target} from {source}")


# ── set_worker_state — unit tests (fake workers) ────────────────


class TestSetWorkerStateUnit(SafePointResetMixin, unittest.TestCase):
    """Unit tests for set_worker_state() using fake workers."""

    def test_idle_to_in_cycle(self):
        _register_fake_worker("w1", "IDLE")
        set_worker_state("w1", "IN_CYCLE")
        self.assertEqual(get_worker_state("w1"), "IN_CYCLE")

    def test_in_cycle_to_critical_section(self):
        _register_fake_worker("w1", "IN_CYCLE")
        set_worker_state("w1", "CRITICAL_SECTION")
        self.assertEqual(get_worker_state("w1"), "CRITICAL_SECTION")

    def test_critical_section_to_in_cycle(self):
        _register_fake_worker("w1", "CRITICAL_SECTION")
        set_worker_state("w1", "IN_CYCLE")
        self.assertEqual(get_worker_state("w1"), "IN_CYCLE")

    def test_in_cycle_to_safe_point(self):
        _register_fake_worker("w1", "IN_CYCLE")
        set_worker_state("w1", "SAFE_POINT")
        self.assertEqual(get_worker_state("w1"), "SAFE_POINT")

    def test_safe_point_to_in_cycle(self):
        _register_fake_worker("w1", "SAFE_POINT")
        set_worker_state("w1", "IN_CYCLE")
        self.assertEqual(get_worker_state("w1"), "IN_CYCLE")

    def test_safe_point_to_idle(self):
        _register_fake_worker("w1", "SAFE_POINT")
        set_worker_state("w1", "IDLE")
        self.assertEqual(get_worker_state("w1"), "IDLE")

    def test_in_cycle_to_idle(self):
        _register_fake_worker("w1", "IN_CYCLE")
        set_worker_state("w1", "IDLE")
        self.assertEqual(get_worker_state("w1"), "IDLE")

    def test_idle_to_critical_section_invalid(self):
        _register_fake_worker("w1", "IDLE")
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("w1", "CRITICAL_SECTION")
        self.assertIn("Invalid transition", str(ctx.exception))

    def test_idle_to_safe_point_invalid(self):
        _register_fake_worker("w1", "IDLE")
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("w1", "SAFE_POINT")
        self.assertIn("Invalid transition", str(ctx.exception))

    def test_critical_section_to_idle_invalid(self):
        _register_fake_worker("w1", "CRITICAL_SECTION")
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("w1", "IDLE")
        self.assertIn("Invalid transition", str(ctx.exception))

    def test_critical_section_to_safe_point_invalid(self):
        _register_fake_worker("w1", "CRITICAL_SECTION")
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("w1", "SAFE_POINT")
        self.assertIn("Invalid transition", str(ctx.exception))

    def test_unknown_worker_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("nonexistent-worker", "IDLE")
        self.assertIn("Unknown worker", str(ctx.exception))

    def test_invalid_state_name_raises_value_error(self):
        _register_fake_worker("w1", "IDLE")
        with self.assertRaises(ValueError) as ctx:
            set_worker_state("w1", "BOGUS_STATE")
        self.assertIn("Invalid worker state", str(ctx.exception))

    def test_all_valid_transitions_succeed(self):
        """Walk through every edge in _VALID_TRANSITIONS."""
        for source, targets in _VALID_TRANSITIONS.items():
            for target in targets:
                _register_fake_worker("w-walk", source)
                set_worker_state("w-walk", target)
                self.assertEqual(get_worker_state("w-walk"), target)
                _unregister_fake_worker("w-walk")


# ── get_worker_state — unit tests ────────────────────────────────


class TestGetWorkerStateUnit(SafePointResetMixin, unittest.TestCase):
    """Unit tests for get_worker_state()."""

    def test_returns_none_for_unknown_worker(self):
        self.assertIsNone(get_worker_state("nonexistent"))

    def test_returns_current_state(self):
        _register_fake_worker("w1", "IN_CYCLE")
        self.assertEqual(get_worker_state("w1"), "IN_CYCLE")

    def test_returns_none_after_removal(self):
        _register_fake_worker("w1", "IDLE")
        _unregister_fake_worker("w1")
        self.assertIsNone(get_worker_state("w1"))


# ── get_all_worker_states — unit tests ───────────────────────────


class TestGetAllWorkerStatesUnit(SafePointResetMixin, unittest.TestCase):
    """Unit tests for get_all_worker_states()."""

    def test_empty_when_no_workers(self):
        self.assertEqual(get_all_worker_states(), {})

    def test_returns_snapshot_with_workers(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "IN_CYCLE")
        states = get_all_worker_states()
        self.assertEqual(states, {"w1": "IDLE", "w2": "IN_CYCLE"})

    def test_snapshot_is_a_copy(self):
        _register_fake_worker("w1", "IDLE")
        snap1 = get_all_worker_states()
        snap2 = get_all_worker_states()
        self.assertIsNot(snap1, snap2)
        self.assertEqual(snap1, snap2)


# ── is_safe_to_control — unit tests ─────────────────────────────


class TestIsSafeToControlUnit(SafePointResetMixin, unittest.TestCase):
    """Unit tests for is_safe_to_control()."""

    def test_true_when_no_workers(self):
        self.assertTrue(is_safe_to_control())

    def test_true_when_all_idle(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "IDLE")
        self.assertTrue(is_safe_to_control())

    def test_true_when_all_safe_point(self):
        _register_fake_worker("w1", "SAFE_POINT")
        _register_fake_worker("w2", "SAFE_POINT")
        self.assertTrue(is_safe_to_control())

    def test_true_when_mix_idle_and_safe_point(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "SAFE_POINT")
        self.assertTrue(is_safe_to_control())

    def test_false_when_any_in_cycle(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "IN_CYCLE")
        self.assertFalse(is_safe_to_control())

    def test_false_when_any_critical_section(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "CRITICAL_SECTION")
        self.assertFalse(is_safe_to_control())

    def test_false_when_single_in_cycle(self):
        _register_fake_worker("w1", "IN_CYCLE")
        self.assertFalse(is_safe_to_control())

    def test_false_when_single_critical_section(self):
        _register_fake_worker("w1", "CRITICAL_SECTION")
        self.assertFalse(is_safe_to_control())

    def test_false_when_worker_missing_state_entry(self):
        """Worker in _workers but missing from _worker_states is unsafe."""
        with runtime._lock:
            runtime._workers["ghost"] = threading.Thread()
        self.assertFalse(is_safe_to_control())


# ── _transition_worker_state_locked — unit tests ─────────────────


class TestTransitionWorkerStateLockedUnit(SafePointResetMixin, unittest.TestCase):
    """Unit tests for _transition_worker_state_locked."""

    def test_valid_transition_updates_state(self):
        _register_fake_worker("w1", "IDLE")
        with runtime._lock:
            runtime._transition_worker_state_locked("w1", "IN_CYCLE")
        self.assertEqual(get_worker_state("w1"), "IN_CYCLE")

    def test_invalid_transition_raises(self):
        _register_fake_worker("w1", "IDLE")
        with self.assertRaises(ValueError):
            with runtime._lock:
                runtime._transition_worker_state_locked("w1", "CRITICAL_SECTION")

    def test_missing_worker_is_noop(self):
        with runtime._lock:
            runtime._transition_worker_state_locked("ghost-worker", "IDLE")

    def test_chain_of_transitions(self):
        _register_fake_worker("w1", "IDLE")
        with runtime._lock:
            runtime._transition_worker_state_locked("w1", "IN_CYCLE")
            runtime._transition_worker_state_locked("w1", "CRITICAL_SECTION")
            runtime._transition_worker_state_locked("w1", "IN_CYCLE")
            runtime._transition_worker_state_locked("w1", "SAFE_POINT")
            runtime._transition_worker_state_locked("w1", "IDLE")
        self.assertEqual(get_worker_state("w1"), "IDLE")


# ── Integration tests — real worker threads ──────────────────────


class TestWorkerStateIntegration(SafePointResetMixin, unittest.TestCase):
    """Integration tests with real worker threads."""

    def test_worker_fn_sets_in_cycle_before_task(self):
        """_worker_fn transitions to IN_CYCLE before calling task_fn."""
        state_at_start = {}
        barrier = threading.Event()
        entered = threading.Event()

        def observe_task(wid):
            state_at_start["state"] = get_worker_state(wid)
            entered.set()
            barrier.wait(timeout=10)

        wid = start_worker(observe_task)
        self.assertTrue(entered.wait(timeout=5))
        self.assertEqual(state_at_start["state"], "IN_CYCLE")
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())

    def test_worker_state_cleaned_up_on_stop(self):
        barrier = threading.Event()
        entered = threading.Event()
        wid = start_worker(lambda _: (entered.set(), barrier.wait(timeout=10)))
        self.assertTrue(entered.wait(timeout=5))
        self.assertIsNotNone(get_worker_state(wid))
        barrier.set()
        stop_worker(wid, timeout=CLEANUP_TIMEOUT)
        _poll_until(lambda: get_worker_state(wid) is None)
        self.assertIsNone(get_worker_state(wid))

    def test_worker_state_cleaned_up_on_error(self):
        def failing_task(_):
            raise RuntimeError("boom")

        wid = start_worker(failing_task)
        _poll_until(lambda: wid not in get_active_workers())
        self.assertIsNone(get_worker_state(wid))

    def test_reset_clears_worker_states(self):
        barrier = threading.Event()
        entered = threading.Event()
        wid = start_worker(lambda _: (entered.set(), barrier.wait(timeout=10)))
        self.assertTrue(entered.wait(timeout=5))
        self.assertNotEqual(get_all_worker_states(), {})
        barrier.set()
        reset()
        self.assertEqual(get_all_worker_states(), {})

    def test_set_worker_state_during_task(self):
        """task_fn can change execution state via set_worker_state."""
        barrier = threading.Event()
        state_set = threading.Event()

        def task(wid):
            set_worker_state(wid, "CRITICAL_SECTION")
            state_set.set()
            barrier.wait(timeout=10)

        wid = start_worker(task)
        self.assertTrue(state_set.wait(timeout=5))
        self.assertEqual(get_worker_state(wid), "CRITICAL_SECTION")
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())

    def test_full_transition_chain_during_task(self):
        """IN_CYCLE → CS → IN_CYCLE → SAFE_POINT → IDLE during single task."""
        barrier = threading.Event()
        chain_done = threading.Event()
        chain = []

        def payment_task(wid):
            chain.append(get_worker_state(wid))
            set_worker_state(wid, "CRITICAL_SECTION")
            chain.append(get_worker_state(wid))
            set_worker_state(wid, "IN_CYCLE")
            chain.append(get_worker_state(wid))
            set_worker_state(wid, "SAFE_POINT")
            chain.append(get_worker_state(wid))
            set_worker_state(wid, "IDLE")
            chain.append(get_worker_state(wid))
            chain_done.set()
            barrier.wait(timeout=10)

        wid = start_worker(payment_task)
        self.assertTrue(chain_done.wait(timeout=5))
        self.assertEqual(chain, ["IN_CYCLE", "CRITICAL_SECTION", "IN_CYCLE", "SAFE_POINT", "IDLE"])
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())

    def test_multiple_workers_independent_states(self):
        barrier1 = threading.Event()
        barrier2 = threading.Event()
        ready1 = threading.Event()
        ready2 = threading.Event()

        def task_critical(wid):
            set_worker_state(wid, "CRITICAL_SECTION")
            ready1.set()
            barrier1.wait(timeout=10)

        def task_safe(wid):
            set_worker_state(wid, "SAFE_POINT")
            ready2.set()
            barrier2.wait(timeout=10)

        wid1 = start_worker(task_critical)
        wid2 = start_worker(task_safe)
        self.assertTrue(ready1.wait(timeout=5))
        self.assertTrue(ready2.wait(timeout=5))
        self.assertEqual(get_worker_state(wid1), "CRITICAL_SECTION")
        self.assertEqual(get_worker_state(wid2), "SAFE_POINT")
        barrier1.set()
        barrier2.set()
        _poll_until(lambda: len(get_active_workers()) == 0)

    def test_is_safe_true_with_real_worker_at_safe_point(self):
        barrier = threading.Event()
        ready = threading.Event()

        def task(wid):
            set_worker_state(wid, "SAFE_POINT")
            ready.set()
            barrier.wait(timeout=10)

        wid = start_worker(task)
        self.assertTrue(ready.wait(timeout=5))
        self.assertTrue(is_safe_to_control())
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())

    def test_is_safe_false_with_real_worker_in_cycle(self):
        barrier = threading.Event()
        entered = threading.Event()

        def task(wid):
            entered.set()
            barrier.wait(timeout=10)

        wid = start_worker(task)
        self.assertTrue(entered.wait(timeout=5))
        self.assertFalse(is_safe_to_control())
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())

    def test_is_safe_false_with_real_worker_in_critical_section(self):
        barrier = threading.Event()
        state_set = threading.Event()

        def task(wid):
            set_worker_state(wid, "CRITICAL_SECTION")
            state_set.set()
            barrier.wait(timeout=10)

        wid = start_worker(task)
        self.assertTrue(state_set.wait(timeout=5))
        self.assertFalse(is_safe_to_control())
        barrier.set()
        _poll_until(lambda: wid not in get_active_workers())


# ── Thread safety ────────────────────────────────────────────────


class TestWorkerStateThreadSafety(SafePointResetMixin, unittest.TestCase):
    """Concurrent access to worker state APIs."""

    def test_concurrent_set_worker_state(self):
        _register_fake_worker("w1", "IN_CYCLE")
        errors = []

        def toggle_states():
            try:
                for _ in range(50):
                    set_worker_state("w1", "CRITICAL_SECTION")
                    set_worker_state("w1", "IN_CYCLE")
                    set_worker_state("w1", "SAFE_POINT")
                    set_worker_state("w1", "IN_CYCLE")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=toggle_states) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertIn(get_worker_state("w1"), ALLOWED_WORKER_STATES)

    def test_concurrent_is_safe_to_control(self):
        _register_fake_worker("w1", "IDLE")
        _register_fake_worker("w2", "SAFE_POINT")
        results = []

        def check_safe():
            for _ in range(100):
                results.append(is_safe_to_control())

        threads = [threading.Thread(target=check_safe) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(results), 400)
        self.assertTrue(all(isinstance(r, bool) for r in results))


if __name__ == "__main__":
    unittest.main()
