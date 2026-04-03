import threading
import time
import unittest
from unittest.mock import patch

from integration import runtime
from modules.monitor import main as monitor
from modules.rollout import main as rollout
from integration.runtime import (
    _apply_scale,
    get_active_workers,
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
        wid = start_worker(lambda _: barrier.wait(timeout=WORKER_BLOCK_TIMEOUT))
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


# ── Failure mode audit ────────────────────────────────────────────


class TestFailureModeAudit(RuntimeResetMixin, unittest.TestCase):
    """Phase 6: ensure no silent failures across crash, timeout, and exceptions."""

    def test_crash_with_monitor_error_still_cleans_up(self):
        """Worker must be deregistered even when monitor.record_error fails."""
        crash_event = threading.Event()

        def crashing_fn(_):
            crash_event.set()
            raise RuntimeError("task boom")

        from integration import runtime
        runtime._running = True
        with patch("integration.runtime.monitor") as mock_mon:
            mock_mon.record_error.side_effect = RuntimeError("monitor boom")
            wid = start_worker(crashing_fn)
            crash_event.wait(timeout=2)
            time.sleep(0.15)
        runtime._running = False
        self.assertNotIn(wid, get_active_workers())

    def test_crash_with_monitor_error_still_logs_task_error(self):
        """Original task error must still be logged even if monitor fails."""
        crash_event = threading.Event()

        def crashing_fn(_):
            crash_event.set()
            raise RuntimeError("real task error")

        from integration import runtime
        runtime._running = True
        with patch("integration.runtime.monitor") as mock_mon, \
             patch("integration.runtime._log_event") as mock_log:
            mock_mon.record_error.side_effect = RuntimeError("monitor dead")
            start_worker(crashing_fn)
            crash_event.wait(timeout=2)
            time.sleep(0.15)
        runtime._running = False
        logged_actions = [c[0][2] for c in mock_log.call_args_list]
        self.assertIn("task_failed", logged_actions)

    def test_success_with_monitor_failure_continues_worker(self):
        """Worker must survive monitor.record_success failure and keep running."""
        call_count = []
        barrier = threading.Event()

        def task_fn(_):
            call_count.append(1)
            if len(call_count) >= 3:
                barrier.set()

        from integration import runtime
        runtime._running = True
        with patch("integration.runtime.monitor") as mock_mon:
            mock_mon.record_success.side_effect = RuntimeError("monitor boom")
            start_worker(task_fn)
            barrier.wait(timeout=2)
        runtime._running = False
        time.sleep(0.15)
        self.assertGreaterEqual(len(call_count), 3,
                                "Worker should keep running despite monitor failure")

    def test_stop_worker_unstarted_thread(self):
        """stop_worker must handle a thread registered but not yet started."""
        from integration import runtime
        t = threading.Thread(target=lambda: None, daemon=True)
        with runtime._lock:
            runtime._workers["ghost-1"] = t
        # Thread not started – join() would raise RuntimeError
        result = stop_worker("ghost-1", timeout=1)
        self.assertFalse(result)
        with runtime._lock:
            self.assertNotIn("ghost-1", runtime._stop_requests)
            # Worker remains in _workers (cleanup happens when thread runs);
            # manually remove since this thread will never start.
            runtime._workers.pop("ghost-1", None)

    def test_unexpected_exception_logged(self):
        """An unexpected exception in the worker loop must be logged, not silent."""
        from integration import runtime
        runtime._running = True
        with patch("integration.runtime._log_event",
                    side_effect=RuntimeError("log broken")), \
             patch.object(runtime._logger, "error") as mock_err:
            start_worker(lambda _: None)
            time.sleep(0.15)
        runtime._running = False
        # The outer except block should have called _logger.error
        self.assertTrue(mock_err.called,
                        "Unexpected exception must be logged via _logger.error")

    def test_timeout_stop_deterministic_state(self):
        """After stop(timeout=...) the runtime must be in a consistent state."""
        worker_block = threading.Event()
        with patch("integration.runtime.rollout.try_scale_up",
                    return_value=(1, "at_max", [])):
            start(lambda _: worker_block.wait(timeout=WORKER_BLOCK_TIMEOUT),
                  interval=1)
            time.sleep(WARMUP_DELAY)
            stop(timeout=INSUFFICIENT_TIMEOUT)
        # _running must be False regardless of whether workers finished
        self.assertFalse(is_running())
        # Status must be consistent with is_running
        status = get_status()
        self.assertFalse(status["running"])
        worker_block.set()
        time.sleep(0.2)

    def test_crash_recovery_state(self):
        """After a worker crash the system must recover to expected state."""
        crash_event = threading.Event()
        call_count = {"n": 0}

        def task_fn(_):
            call_count["n"] += 1
            if call_count["n"] == 1:
                crash_event.set()
                raise RuntimeError("boom")
            time.sleep(0.5)

        with patch("integration.runtime.rollout.try_scale_up",
                    return_value=(1, "at_max", [])):
            start(task_fn, interval=0.05)
            crash_event.wait(timeout=2)
            time.sleep(0.4)
            # System should have restarted the worker
            status = get_status()
            self.assertTrue(status["running"])
            self.assertGreater(call_count["n"], 1,
                               "Worker should have been restarted after crash")
            stop(timeout=2)


if __name__ == "__main__":
    unittest.main()
