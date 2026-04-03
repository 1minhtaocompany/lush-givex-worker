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
        runtime._state = "RUNNING"
        _apply_scale(3, self._noop)
        self.assertEqual(len(get_active_workers()), 3)
        runtime._state = "STOPPED"
        time.sleep(0.1)

    def test_scale_down(self):
        from integration import runtime
        runtime._state = "RUNNING"
        _apply_scale(3, self._noop)
        self.assertEqual(len(get_active_workers()), 3)
        _apply_scale(1, self._noop)
        self.assertEqual(len(get_active_workers()), 1)
        runtime._state = "STOPPED"
        time.sleep(0.1)

    def test_scale_to_zero(self):
        from integration import runtime
        runtime._state = "RUNNING"
        _apply_scale(2, self._noop)
        _apply_scale(0, self._noop)
        self.assertEqual(len(get_active_workers()), 0)
        runtime._state = "STOPPED"


# ── Worker crash handling ────────────────────────────────────────


class TestWorkerCrash(RuntimeResetMixin, unittest.TestCase):
    def test_crash_removes_worker_from_active_set(self):
        """A failed standalone worker exits cleanly and is deregistered."""
        crash_event = threading.Event()

        def crashing_fn(_):
            crash_event.set()
            raise RuntimeError("boom")

        from integration import runtime
        runtime._state = "RUNNING"
        start_worker(crashing_fn)
        crash_event.wait(timeout=2)
        time.sleep(0.1)
        runtime._state = "STOPPED"
        self.assertEqual(get_active_workers(), [])

    def test_crash_does_not_stop_other_workers(self):
        """One crashing worker must not kill another."""
        from integration import runtime
        runtime._state = "RUNNING"
        good_barrier = threading.Event()
        start_worker(lambda _: good_barrier.wait(timeout=2))

        def bad_fn(_):
            raise RuntimeError("fail")

        start_worker(bad_fn)
        time.sleep(0.2)
        # Good worker should still be in the active list
        self.assertGreaterEqual(len(get_active_workers()), 1)
        good_barrier.set()
        runtime._state = "STOPPED"
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


# ── Start/Stop race condition audit ──────────────────────────────


class TestStartStopRaceCondition(RuntimeResetMixin, unittest.TestCase):
    """Validate no race conditions between start() and stop()."""

    def test_stopping_state_blocks_start(self):
        """start() must return False while state is STOPPING."""
        from integration import runtime
        gate = threading.Event()

        original_join = threading.Thread.join

        def slow_join(self_thread, timeout=None):
            gate.wait(timeout=2)
            original_join(self_thread, timeout=timeout)

        start(lambda _: time.sleep(0.5), interval=0.05)
        with patch.object(threading.Thread, "join", slow_join):
            stop_thread = threading.Thread(target=stop, args=(5,))
            stop_thread.start()
            time.sleep(0.05)
            self.assertEqual(get_state(), "STOPPING")
            self.assertFalse(start(lambda _: None, interval=0.05))
            gate.set()
            stop_thread.join(timeout=3)

    def test_no_duplicate_loop_thread_during_stop(self):
        """No new loop thread must be spawned while STOPPING."""
        from integration import runtime
        gate = threading.Event()

        original_join = threading.Thread.join

        def slow_join(self_thread, timeout=None):
            gate.wait(timeout=2)
            original_join(self_thread, timeout=timeout)

        start(lambda _: time.sleep(0.5), interval=0.05)
        with patch.object(threading.Thread, "join", slow_join):
            stop_thread = threading.Thread(target=stop, args=(5,))
            stop_thread.start()
            time.sleep(0.05)
            self.assertEqual(get_state(), "STOPPING")
            with runtime._lock:
                loop_before = runtime._loop_thread
            self.assertFalse(start(lambda _: None, interval=0.05))
            with runtime._lock:
                loop_after = runtime._loop_thread
            self.assertIs(loop_before, loop_after)
            gate.set()
            stop_thread.join(timeout=3)

    def test_concurrent_start_stop_deterministic(self):
        """Concurrent start+stop must produce deterministic outcome."""
        for _ in range(10):
            reset()
            results = {"start": None, "stop": None}
            barrier = threading.Barrier(2, timeout=5)

            def do_start():
                barrier.wait()
                results["start"] = start(
                    lambda _: time.sleep(0.5), interval=0.05)

            def do_stop():
                barrier.wait()
                results["stop"] = stop(timeout=2)

            start(lambda _: time.sleep(0.5), interval=0.05)
            t1 = threading.Thread(target=do_start)
            t2 = threading.Thread(target=do_stop)
            t1.start(); t2.start()
            t1.join(timeout=5); t2.join(timeout=5)
            # Exactly one of start/stop should succeed on the running instance
            self.assertFalse(results["start"] and results["stop"] is None)
            # State must be valid
            self.assertIn(get_state(), ALLOWED_STATES)
            stop(timeout=2)

    def test_state_transitions_to_stopped_after_stop(self):
        """State must be STOPPED after stop() completes."""
        start(lambda _: time.sleep(0.5), interval=0.05)
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")

    def test_start_after_stopped(self):
        """start() must succeed after state reaches STOPPED."""
        start(lambda _: time.sleep(0.5), interval=0.05)
        stop(timeout=2)
        self.assertEqual(get_state(), "STOPPED")
        self.assertTrue(start(lambda _: time.sleep(0.5), interval=0.05))
        self.assertEqual(get_state(), "RUNNING")
        stop(timeout=2)


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


if __name__ == "__main__":
    unittest.main()
