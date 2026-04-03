import logging
import threading
import time
import unittest
from unittest.mock import patch

from integration import runtime
from modules.monitor import main as monitor
from modules.rollout import main as rollout
from integration.runtime import (
    ALLOWED_STATES,
    _apply_scale,
    get_active_workers,
    get_state,
    get_status,
    is_running,
    reset,
    start,
    start_worker,
    stop,
    stop_worker,
)

WORKER_BLOCK_TIMEOUT = 1
CLEANUP_TIMEOUT = 2
WARMUP_DELAY = 0.2
INSUFFICIENT_TIMEOUT = 0.01


class RuntimeResetMixin:
    def setUp(self):
        reset()
        rollout.reset()
        monitor.reset()

    def tearDown(self):
        reset()
        rollout.reset()
        monitor.reset()


# ── Worker control ────────────────────────────────────────────────


class TestStartWorker(RuntimeResetMixin, unittest.TestCase):
    def test_returns_worker_id(self):
        barrier = threading.Event()
        wid = start_worker(lambda _: barrier.wait(timeout=1))
        self.assertTrue(wid.startswith("worker-"))
        barrier.set()

    def test_worker_appears_in_active_list(self):
        barrier = threading.Event()
        wid = start_worker(lambda _: barrier.wait(timeout=1))
        self.assertIn(wid, get_active_workers())
        barrier.set()

    def test_multiple_workers(self):
        barrier = threading.Event()
        ids = [start_worker(lambda _: barrier.wait(timeout=1)) for _ in range(3)]
        self.assertEqual(len(set(ids)), 3)
        barrier.set()


class TestStopWorker(RuntimeResetMixin, unittest.TestCase):
    def test_stop_running_worker(self):
        barrier = threading.Event()
        wid = start_worker(lambda _: barrier.wait(timeout=1))
        barrier.set()
        result = stop_worker(wid, timeout=2)
        self.assertTrue(result)
        self.assertNotIn(wid, get_active_workers())

    def test_stop_nonexistent_worker(self):
        self.assertFalse(stop_worker("no-such-worker"))

    def test_stop_running_worker_timeout_keeps_worker_active(self):
        barrier = threading.Event()
        started = threading.Event()

        def blocking_task(_):
            started.set()
            barrier.wait(timeout=WORKER_BLOCK_TIMEOUT)

        wid = start_worker(blocking_task)
        started.wait(timeout=2)
        try:
            self.assertFalse(stop_worker(wid, timeout=INSUFFICIENT_TIMEOUT))
            self.assertIn(wid, get_active_workers())
            self.assertTrue(runtime._workers[wid].is_alive())
        finally:
            barrier.set()
            stop_worker(wid, timeout=CLEANUP_TIMEOUT)


# ── Scale up / down ──────────────────────────────────────────────


class TestApplyScale(RuntimeResetMixin, unittest.TestCase):
    def _noop(self, _):
        time.sleep(0.01)

    def test_scale_up(self):
        from integration import runtime
        runtime._running = True
        _apply_scale(3, self._noop)
        self.assertEqual(len(get_active_workers()), 3)
        runtime._running = False
        time.sleep(0.1)

    def test_scale_down(self):
        from integration import runtime
        runtime._running = True
        _apply_scale(3, self._noop)
        self.assertEqual(len(get_active_workers()), 3)
        _apply_scale(1, self._noop)
        self.assertEqual(len(get_active_workers()), 1)
        runtime._running = False
        time.sleep(0.1)

    def test_scale_to_zero(self):
        from integration import runtime
        runtime._running = True
        _apply_scale(2, self._noop)
        _apply_scale(0, self._noop)
        self.assertEqual(len(get_active_workers()), 0)
        runtime._running = False


# ── Worker crash handling ────────────────────────────────────────


class TestWorkerCrash(RuntimeResetMixin, unittest.TestCase):
    def test_crash_removes_worker_from_active_set(self):
        """A failed standalone worker exits cleanly and is deregistered."""
        crash_event = threading.Event()

        def crashing_fn(_):
            crash_event.set()
            raise RuntimeError("boom")

        from integration import runtime
        runtime._running = True
        start_worker(crashing_fn)
        crash_event.wait(timeout=2)
        time.sleep(0.1)
        runtime._running = False
        self.assertEqual(get_active_workers(), [])

    def test_crash_does_not_stop_other_workers(self):
        """One crashing worker must not kill another."""
        from integration import runtime
        runtime._running = True
        good_barrier = threading.Event()
        start_worker(lambda _: good_barrier.wait(timeout=2))

        def bad_fn(_):
            raise RuntimeError("fail")

        start_worker(bad_fn)
        time.sleep(0.2)
        # Good worker should still be in the active list
        self.assertGreaterEqual(len(get_active_workers()), 1)
        good_barrier.set()
        runtime._running = False
        time.sleep(0.1)


# ── Runtime loop (start / stop) ──────────────────────────────────


class TestStartStop(RuntimeResetMixin, unittest.TestCase):
    def test_start_returns_true(self):
        result = start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertTrue(result)
        self.assertTrue(is_running())
        stop(timeout=2)

    def test_double_start_returns_false(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertFalse(start(lambda _: None, interval=0.05))
        stop(timeout=2)

    def test_stop_returns_true(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertTrue(stop(timeout=2))
        self.assertFalse(is_running())

    def test_stop_when_not_running(self):
        self.assertFalse(stop(timeout=1))

    def test_stop_timeout_returns_false_when_worker_still_alive(self):
        worker_block = threading.Event()
        with patch("integration.runtime.rollout.try_scale_up",
                   return_value=(1, "at_max", [])):
            start(lambda _: worker_block.wait(timeout=WORKER_BLOCK_TIMEOUT), interval=1)
            time.sleep(WARMUP_DELAY)
            self.assertFalse(stop(timeout=INSUFFICIENT_TIMEOUT))
            self.assertFalse(is_running())
            self.assertNotEqual(get_active_workers(), [])
            worker_block.set()
            time.sleep(1.1)


# ── Runtime loop integration ─────────────────────────────────────


class TestRuntimeLoop(RuntimeResetMixin, unittest.TestCase):
    def test_loop_restarts_crashed_worker(self):
        calls = []
        wait_event = threading.Event()

        def task_fn(_):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            wait_event.wait(timeout=1)

        with patch("integration.runtime.rollout.try_scale_up",
                   return_value=(1, "at_max", [])):
            start(task_fn, interval=0.05)
            time.sleep(0.3)
            self.assertGreater(monitor.get_restarts_last_hour(), 0)
            self.assertEqual(len(get_active_workers()), 1)
            wait_event.set()
            stop(timeout=2)

    def test_loop_scales_workers(self):
        """Runtime loop should scale workers based on rollout."""
        rollout.configure(check_rollback_fn=lambda: [],
                          save_baseline_fn=lambda: None)
        tick = threading.Event()

        def task_fn(_):
            tick.wait(timeout=2)

        start(task_fn, interval=0.05)
        time.sleep(0.3)
        # After a few ticks, rollout should have advanced and workers scaled
        status = get_status()
        self.assertTrue(status["running"])
        self.assertGreater(status["worker_count"], 0)
        tick.set()
        stop(timeout=2)

    def test_loop_handles_rollback(self):
        """When rollout triggers rollback, consecutive counter increases."""
        rollout.configure(
            check_rollback_fn=lambda: ["error too high"],
            save_baseline_fn=lambda: None,
        )
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.3)
        status = get_status()
        self.assertGreater(status["consecutive_rollbacks"], 0)
        stop(timeout=2)


class TestRuntimeMonitorUnavailable(RuntimeResetMixin, unittest.TestCase):
    def test_loop_survives_monitor_failure(self):
        """Runtime loop must not crash when monitor.get_metrics raises."""
        with patch("integration.runtime.monitor") as mock_mon:
            mock_mon.get_metrics.side_effect = RuntimeError("unavailable")
            start(lambda _: time.sleep(0.5), interval=0.05)
            time.sleep(0.2)
            self.assertTrue(is_running())
            stop(timeout=2)


# ── get_status / is_running ──────────────────────────────────────


class TestStatus(RuntimeResetMixin, unittest.TestCase):
    def test_initial_status(self):
        status = get_status()
        self.assertFalse(status["running"])
        self.assertEqual(status["worker_count"], 0)
        self.assertEqual(status["consecutive_rollbacks"], 0)

    def test_status_during_run(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.1)
        self.assertTrue(is_running())
        stop(timeout=2)


class TestReset(RuntimeResetMixin, unittest.TestCase):
    def test_reset_clears_all(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.1)
        reset()
        self.assertFalse(is_running())
        self.assertEqual(get_active_workers(), [])
        status = get_status()
        self.assertEqual(status["worker_count"], 0)


# ── Phase 6 hardening audit ──────────────────────────────────────


class TestHardeningRaceCondition(RuntimeResetMixin, unittest.TestCase):
    """Verify no race conditions remain in worker lifecycle."""

    def test_concurrent_start_stop_no_crash(self):
        """Rapid start/stop cycles must not raise RuntimeError."""
        from integration import runtime
        runtime._running = True
        errors = []

        def start_stop():
            try:
                wid = start_worker(lambda _: time.sleep(0.01))
                stop_worker(wid, timeout=1)
            except RuntimeError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=start_stop) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        runtime._running = False
        time.sleep(0.1)
        self.assertEqual(errors, [], f"Race condition errors: {errors}")

    def test_start_worker_thread_started_under_lock(self):
        """Thread must be started before the lock is released."""
        barrier = threading.Event()
        wid = start_worker(lambda _: barrier.wait(timeout=1))
        # Thread should already be alive immediately after start_worker
        with runtime._lock:
            thread = runtime._workers.get(wid)
        self.assertIsNotNone(thread)
        self.assertTrue(thread.is_alive())
        barrier.set()
        time.sleep(0.1)


class TestHardeningZombieWorker(RuntimeResetMixin, unittest.TestCase):
    """Verify no zombie workers after crash or stop."""

    def test_crashed_worker_fully_deregistered(self):
        """A crashed worker must not remain in _workers or _stop_requests."""
        from integration import runtime
        runtime._running = True
        crash_done = threading.Event()

        def crash_fn(_):
            crash_done.set()
            raise RuntimeError("crash")

        start_worker(crash_fn)
        crash_done.wait(timeout=2)
        time.sleep(0.1)
        runtime._running = False
        with runtime._lock:
            self.assertEqual(len(runtime._workers), 0)
            self.assertEqual(len(runtime._stop_requests), 0)

    def test_stopped_worker_fully_deregistered(self):
        """A normally stopped worker must not remain in _workers."""
        barrier = threading.Event()
        wid = start_worker(lambda _: barrier.wait(timeout=1))
        barrier.set()
        stop_worker(wid, timeout=2)
        with runtime._lock:
            self.assertNotIn(wid, runtime._workers)
            self.assertNotIn(wid, runtime._stop_requests)


class TestHardeningLifecycleDeterministic(RuntimeResetMixin, unittest.TestCase):
    """Validate lifecycle transitions are deterministic."""

    def test_start_stop_start_cycle(self):
        """Runtime must support clean start → stop → start cycles."""
        task = lambda _: time.sleep(0.5)
        self.assertTrue(start(task, interval=0.05))
        self.assertTrue(is_running())
        self.assertTrue(stop(timeout=2))
        self.assertFalse(is_running())
        # Second cycle
        self.assertTrue(start(task, interval=0.05))
        self.assertTrue(is_running())
        self.assertTrue(stop(timeout=2))
        self.assertFalse(is_running())

    def test_reset_enables_clean_restart(self):
        """After reset, all state must be cleared for a clean start."""
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.1)
        reset()
        status = get_status()
        self.assertFalse(status["running"])
        self.assertEqual(status["worker_count"], 0)
        self.assertEqual(status["consecutive_rollbacks"], 0)
        self.assertEqual(get_active_workers(), [])


class TestHardeningSilentFailure(RuntimeResetMixin, unittest.TestCase):
    """Confirm no silent failures exist."""

    def test_task_error_is_recorded(self):
        """Errors in task_fn must be recorded by monitor."""
        from integration import runtime
        runtime._running = True
        done = threading.Event()

        def failing_fn(_):
            done.set()
            raise ValueError("test error")

        monitor.reset()
        start_worker(failing_fn)
        done.wait(timeout=2)
        time.sleep(0.1)
        runtime._running = False
        metrics = monitor.get_metrics()
        self.assertGreater(metrics["error_count"], 0)

    def test_log_event_failure_does_not_crash_worker(self):
        """If _log_event fails in finally, worker cleanup still completes."""
        from integration import runtime
        runtime._running = True
        done = threading.Event()

        original_log = runtime._log_event

        def broken_log(*args, **kwargs):
            # _log_event signature: (worker_id, state, action, metrics=None)
            # Fail on the "stopped"/"stop" event emitted in the finally block
            if len(args) >= 3 and args[1] == "stopped" and args[2] == "stop":
                raise RuntimeError("log broken")
            return original_log(*args, **kwargs)

        def task_fn(_):
            done.set()
            raise RuntimeError("exit task")

        with patch("integration.runtime._log_event", side_effect=broken_log):
            wid = start_worker(task_fn)
            done.wait(timeout=2)
            time.sleep(0.2)

        runtime._running = False
        # Worker must still be cleaned up despite log failure
        self.assertNotIn(wid, get_active_workers())


class TestHardeningLogging(RuntimeResetMixin, unittest.TestCase):
    """Review logging format and traceability."""

    def test_log_event_format(self):
        """_log_event must produce structured log output."""
        records = []
        test_handler = logging.Handler()
        test_handler.emit = lambda record: records.append(record)
        logger = logging.getLogger("integration.runtime")
        logger.addHandler(test_handler)
        logger.setLevel(logging.DEBUG)
        try:
            runtime._log_event("test-worker", "running", "start", {"key": "val"})
            self.assertEqual(len(records), 1)
            msg = records[0].getMessage()
            self.assertIn("test-worker", msg)
            self.assertIn("running", msg)
            self.assertIn("start", msg)
            # Verify pipe-separated format
            self.assertGreaterEqual(msg.count("|"), 3)
        finally:
            logger.removeHandler(test_handler)

    def test_stop_worker_logs_stop_requested(self):
        """stop_worker must log a stop_requested event on success."""
        records = []
        test_handler = logging.Handler()
        test_handler.emit = lambda record: records.append(record)
        logger = logging.getLogger("integration.runtime")
        logger.addHandler(test_handler)
        logger.setLevel(logging.DEBUG)
        try:
            barrier = threading.Event()
            wid = start_worker(lambda _: barrier.wait(timeout=1))
            barrier.set()
            stop_worker(wid, timeout=2)
            msgs = [r.getMessage() for r in records]
            stop_msgs = [m for m in msgs if "stop_requested" in m]
            self.assertGreater(len(stop_msgs), 0)
        finally:
            logger.removeHandler(test_handler)
# ── Lifecycle state machine audit ────────────────────────────────


class TestLifecycleStateMachine(RuntimeResetMixin, unittest.TestCase):
    """Phase 6 — validate INIT → RUNNING → STOPPING → STOPPED transitions."""

    def test_allowed_states_set(self):
        self.assertEqual(ALLOWED_STATES, {"INIT", "RUNNING", "STOPPING", "STOPPED"})

    def test_initial_state_is_init(self):
        self.assertEqual(get_state(), "INIT")

    def test_start_transitions_to_running(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)

    def test_stop_transitions_to_stopped(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")

    def test_start_allowed_from_init(self):
        self.assertEqual(get_state(), "INIT")
        self.assertTrue(start(lambda _: time.sleep(0.5), interval=0.05))
        stop(timeout=2)

    def test_start_allowed_from_stopped(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        self.assertTrue(start(lambda _: time.sleep(0.5), interval=0.05))
        stop(timeout=2)

    def test_start_blocked_while_running(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertFalse(start(lambda _: None, interval=0.05))
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)

    def test_stopping_blocks_start(self):
        """Verify STOPPING state blocks start()."""
        with runtime._lock:
            runtime._state = "STOPPING"
        self.assertFalse(start(lambda _: None, interval=0.05))
        with runtime._lock:
            runtime._state = "INIT"

    def test_stop_only_from_running(self):
        self.assertFalse(stop(timeout=1))
        self.assertEqual(get_state(), "INIT")

    def test_stop_from_stopped_returns_false(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        self.assertFalse(stop(timeout=1))

    def test_restart_no_state_leak(self):
        """Validate restart cycle does not leak state."""
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.1)
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        self.assertEqual(get_active_workers(), [])
        status = get_status()
        self.assertEqual(status["worker_count"], 0)
        self.assertFalse(status["running"])
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertEqual(get_state(), "RUNNING")
        self.assertTrue(is_running())
        stop(timeout=2)

    def test_reset_returns_to_init(self):
        start(lambda _: time.sleep(0.5), interval=0.05)
        time.sleep(0.1)
        reset()
        self.assertEqual(get_state(), "INIT")

    def test_get_status_includes_state(self):
        status = get_status()
        self.assertIn("state", status)
        self.assertEqual(status["state"], "INIT")

    def test_deterministic_full_cycle(self):
        """INIT → RUNNING → STOPPED → RUNNING → STOPPED → INIT."""
        self.assertEqual(get_state(), "INIT")
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        reset()
        self.assertEqual(get_state(), "INIT")


if __name__ == "__main__":
    unittest.main()
