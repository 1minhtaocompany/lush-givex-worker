"""Determinism audit tests for rollout & runtime consistency.

Phase 6 — ensures the system always produces deterministic results with
the same input.  Covers:

* Rollout decision depends only on (step_index, check_fn result)
* Same input → same output across repeated calls
* No uncontrolled randomness in rollout/monitor modules
* No state drift after reset cycles
"""

import ast
import os
import threading
import time
import unittest
from unittest.mock import patch, mock_open

from modules.monitor import main as monitor
from modules.rollout import main as rollout


# ── Helpers ──────────────────────────────────────────────────────


class _MonitorResetMixin:
    def setUp(self):
        monitor.reset()
        rollout.reset()

    def tearDown(self):
        monitor.reset()
        rollout.reset()


def _rollout_initial_snapshot():
    """Return a dict representing the expected initial rollout state."""
    return {
        "current_workers": rollout.SCALE_STEPS[0],
        "step_index": 0,
        "max_step_index": len(rollout.SCALE_STEPS) - 1,
        "can_scale_up": True,
        "rollback_count": 0,
    }


def _monitor_initial_metrics():
    """Return a dict representing the expected initial monitor metrics."""
    return {
        "success_count": 0,
        "error_count": 0,
        "success_rate": 1.0,
        "error_rate": 0.0,
        "restarts_last_hour": 0,
        "baseline_success_rate": None,
    }


# ── 1. No uncontrolled randomness ────────────────────────────────


class TestNoRandomnessInRollout(unittest.TestCase):
    """Rollout module must not import or use the *random* module."""

    def test_no_random_import(self):
        path = os.path.join(
            os.path.dirname(__file__), os.pardir, "modules", "rollout", "main.py"
        )
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "random",
                        "rollout/main.py must not import random"
                    )
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(
                    node.module, "random",
                    "rollout/main.py must not import from random"
                )


class TestNoRandomnessInMonitor(unittest.TestCase):
    """Monitor module must not import or use the *random* module."""

    def test_no_random_import(self):
        path = os.path.join(
            os.path.dirname(__file__), os.pardir, "modules", "monitor", "main.py"
        )
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "random",
                        "monitor/main.py must not import random"
                    )
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(
                    node.module, "random",
                    "monitor/main.py must not import from random"
                )


class TestNoRandomnessInRuntime(unittest.TestCase):
    """Runtime module must not import or use the *random* module."""

    def test_no_random_import(self):
        path = os.path.join(
            os.path.dirname(__file__), os.pardir, "integration", "runtime.py"
        )
        with open(path, "r") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(
                        alias.name, "random",
                        "runtime.py must not import random"
                    )
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(
                    node.module, "random",
                    "runtime.py must not import from random"
                )


# ── 2. Rollout determinism: same state + same check_fn → same output ──


class TestRolloutDeterminism(_MonitorResetMixin, unittest.TestCase):
    """Given the same step index and check_fn result, try_scale_up must
    always return the same (worker_count, action, reasons) tuple."""

    def test_healthy_scale_up_is_deterministic(self):
        """Consecutive healthy calls produce the same result for the same step."""
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        first = rollout.try_scale_up()
        # Reset to same starting state
        rollout.reset()
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        second = rollout.try_scale_up()
        self.assertEqual(first, second)

    def test_rollback_is_deterministic(self):
        """Consecutive calls with the same bad check_fn produce the same rollback."""
        reasons_input = ["error rate 50.0% exceeds 5%"]
        rollout.configure(
            check_rollback_fn=lambda: list(reasons_input),
            save_baseline_fn=lambda: None,
        )
        first = rollout.try_scale_up()
        rollout.reset()
        rollout.configure(
            check_rollback_fn=lambda: list(reasons_input),
            save_baseline_fn=lambda: None,
        )
        second = rollout.try_scale_up()
        self.assertEqual(first, second)

    def test_at_max_is_deterministic(self):
        """at_max returns identical result when already at maximum."""
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        for _ in range(len(rollout.SCALE_STEPS) - 1):
            rollout.try_scale_up()
        first = rollout.try_scale_up()
        second = rollout.try_scale_up()
        self.assertEqual(first, second)

    def test_full_scale_sequence_deterministic(self):
        """Complete scale-up sequence is identical across two full runs."""
        def run_full_sequence():
            rollout.reset()
            rollout.configure(
                check_rollback_fn=lambda: [], save_baseline_fn=lambda: None
            )
            results = []
            for _ in range(len(rollout.SCALE_STEPS) + 1):
                results.append(rollout.try_scale_up())
            return results

        first_run = run_full_sequence()
        second_run = run_full_sequence()
        self.assertEqual(first_run, second_run)

    def test_repeat_n_times_identical(self):
        """Repeating the same operation N times from the same state is stable."""
        n = 10
        results = []
        for _ in range(n):
            rollout.reset()
            rollout.configure(
                check_rollback_fn=lambda: [], save_baseline_fn=lambda: None
            )
            results.append(rollout.try_scale_up())
        self.assertTrue(all(r == results[0] for r in results))


# ── 3. Monitor determinism: same counters → same metrics/reasons ──


class TestMonitorDeterminism(_MonitorResetMixin, unittest.TestCase):
    """Given the same counter state, monitor must return the same metrics
    and rollback decisions."""

    def _setup_known_state(self):
        """Record a known pattern of successes and errors."""
        for _ in range(8):
            monitor.record_success()
        for _ in range(2):
            monitor.record_error()

    def test_get_metrics_deterministic(self):
        """get_metrics returns consistent results for the same counter state."""
        self._setup_known_state()
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=100):
            m1 = monitor.get_metrics()
            m2 = monitor.get_metrics()
        self.assertEqual(m1["success_count"], m2["success_count"])
        self.assertEqual(m1["error_count"], m2["error_count"])
        self.assertEqual(m1["success_rate"], m2["success_rate"])
        self.assertEqual(m1["error_rate"], m2["error_rate"])

    def test_check_rollback_deterministic_healthy(self):
        """Healthy state produces empty reasons consistently."""
        for _ in range(10):
            monitor.record_success()
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=100):
            r1 = monitor.check_rollback_needed()
            r2 = monitor.check_rollback_needed()
        self.assertEqual(r1, r2)
        self.assertEqual(r1, [])

    def test_check_rollback_deterministic_unhealthy(self):
        """Unhealthy state produces identical reasons consistently."""
        monitor.record_success()
        monitor.record_error()
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=100):
            r1 = monitor.check_rollback_needed()
            r2 = monitor.check_rollback_needed()
        self.assertEqual(r1, r2)

    def test_success_rate_deterministic(self):
        """Success rate calculation is consistent for the same counters."""
        for _ in range(7):
            monitor.record_success()
        for _ in range(3):
            monitor.record_error()
        rates = [monitor.get_success_rate() for _ in range(5)]
        self.assertTrue(all(r == rates[0] for r in rates))

    def test_error_rate_deterministic(self):
        """Error rate calculation is consistent for the same counters."""
        for _ in range(7):
            monitor.record_success()
        for _ in range(3):
            monitor.record_error()
        rates = [monitor.get_error_rate() for _ in range(5)]
        self.assertTrue(all(r == rates[0] for r in rates))


# ── 4. Rollout decision depends only on monitor metrics ──────────


class TestRolloutDependsOnlyOnMetrics(_MonitorResetMixin, unittest.TestCase):
    """Rollout decision must be determined entirely by the check_fn result
    (which comes from monitor metrics), not by wall-clock time or other
    external factors."""

    def test_decision_ignores_wall_clock(self):
        """Rollout result is the same regardless of when it is called."""
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        r1 = rollout.try_scale_up()
        rollout.reset()
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        # Advance wall clock (simulate delay)
        time.sleep(0.01)
        r2 = rollout.try_scale_up()
        self.assertEqual(r1, r2)

    def test_check_fn_controls_decision(self):
        """Changing the check_fn result changes the rollout decision."""
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        healthy_result = rollout.try_scale_up()
        self.assertEqual(healthy_result[1], "scaled_up")

        rollout.reset()
        rollout.configure(
            check_rollback_fn=lambda: ["degraded"],
            save_baseline_fn=lambda: None,
        )
        unhealthy_result = rollout.try_scale_up()
        self.assertEqual(unhealthy_result[1], "rollback")

    def test_same_check_fn_same_decision(self):
        """Identical check_fn result always produces the same decision."""
        reasons = ["error rate high"]
        for _ in range(5):
            rollout.reset()
            rollout.configure(
                check_rollback_fn=lambda: list(reasons),
                save_baseline_fn=lambda: None,
            )
            count, action, returned_reasons = rollout.try_scale_up()
            self.assertEqual(action, "rollback")
            self.assertEqual(returned_reasons, reasons)


# ── 5. No state drift ────────────────────────────────────────────


class TestNoStateDrift(_MonitorResetMixin, unittest.TestCase):
    """State must not drift after reset cycles.  Every reset must restore
    the exact initial state."""

    def test_rollout_reset_restores_initial_state(self):
        """Rollout reset produces the exact same initial snapshot."""
        initial = _rollout_initial_snapshot()
        self.assertEqual(rollout.get_status(), initial)

        # Perform operations
        rollout.configure(check_rollback_fn=lambda: [], save_baseline_fn=lambda: None)
        rollout.try_scale_up()
        rollout.force_rollback("test")
        rollout.try_scale_up()

        # Reset
        rollout.reset()
        self.assertEqual(rollout.get_status(), initial)

    def test_monitor_reset_restores_initial_state(self):
        """Monitor reset produces the exact same initial metric values."""
        expected = _monitor_initial_metrics()
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=0):
            initial = monitor.get_metrics()
        for key in expected:
            self.assertEqual(initial[key], expected[key])

        # Perform operations
        for _ in range(5):
            monitor.record_success()
        for _ in range(3):
            monitor.record_error()
        monitor.save_baseline()

        # Reset
        monitor.reset()
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=0):
            after_reset = monitor.get_metrics()
        for key in expected:
            self.assertEqual(after_reset[key], expected[key])

    def test_multiple_reset_cycles_no_drift(self):
        """Running N operate-reset cycles produces the same state each time."""
        n = 5
        snapshots = []
        for _ in range(n):
            rollout.configure(
                check_rollback_fn=lambda: [], save_baseline_fn=lambda: None
            )
            rollout.try_scale_up()
            rollout.force_rollback("cycle test")
            rollout.reset()
            snapshots.append(rollout.get_status())

        for snap in snapshots:
            self.assertEqual(snap, snapshots[0])

    def test_monitor_multiple_reset_cycles_no_drift(self):
        """Monitor state is identical after each reset cycle."""
        n = 5
        snapshots = []
        for _ in range(n):
            for _ in range(10):
                monitor.record_success()
            for _ in range(5):
                monitor.record_error()
            monitor.save_baseline()
            monitor.reset()
            with patch("modules.monitor.main.get_memory_usage_bytes", return_value=0):
                snapshots.append(monitor.get_metrics())

        for snap in snapshots:
            for key in _monitor_initial_metrics():
                self.assertEqual(snap[key], snapshots[0][key])

    def test_rollback_history_cleared_on_reset(self):
        """Rollback history does not leak across reset boundaries."""
        rollout.configure(
            check_rollback_fn=lambda: ["bad"], save_baseline_fn=lambda: None
        )
        rollout.try_scale_up()
        self.assertGreater(len(rollout.get_rollback_history()), 0)
        rollout.reset()
        self.assertEqual(rollout.get_rollback_history(), [])

    def test_baseline_cleared_on_monitor_reset(self):
        """Baseline success rate does not leak across reset boundaries."""
        for _ in range(10):
            monitor.record_success()
        monitor.save_baseline()
        self.assertIsNotNone(monitor.get_baseline_success_rate())
        monitor.reset()
        self.assertIsNone(monitor.get_baseline_success_rate())


# ── 6. End-to-end determinism: monitor → rollout pipeline ────────


class TestEndToEndDeterminism(_MonitorResetMixin, unittest.TestCase):
    """The full monitor → rollout pipeline must be deterministic when
    given the same sequence of events."""

    def _run_scenario(self, successes, errors):
        """Run a deterministic scenario and return the rollout result."""
        monitor.reset()
        rollout.reset()
        for _ in range(successes):
            monitor.record_success()
        for _ in range(errors):
            monitor.record_error()
        rollout.configure(
            check_rollback_fn=monitor.check_rollback_needed,
            save_baseline_fn=monitor.save_baseline,
        )
        with patch("modules.monitor.main.get_memory_usage_bytes", return_value=100):
            return rollout.try_scale_up()

    def test_healthy_scenario_deterministic(self):
        """Healthy events → scale up (deterministic across runs)."""
        r1 = self._run_scenario(successes=10, errors=0)
        r2 = self._run_scenario(successes=10, errors=0)
        self.assertEqual(r1, r2)
        self.assertEqual(r1[1], "scaled_up")

    def test_unhealthy_scenario_deterministic(self):
        """High error rate → rollback (deterministic across runs)."""
        r1 = self._run_scenario(successes=1, errors=10)
        r2 = self._run_scenario(successes=1, errors=10)
        self.assertEqual(r1, r2)
        self.assertEqual(r1[1], "rollback")

    def test_borderline_scenario_deterministic(self):
        """Borderline metrics → same decision (deterministic across runs)."""
        r1 = self._run_scenario(successes=95, errors=5)
        r2 = self._run_scenario(successes=95, errors=5)
        self.assertEqual(r1, r2)

    def test_alternating_health_deterministic(self):
        """Alternating healthy/unhealthy cycles produce same sequence."""
        def run_alternating():
            monitor.reset()
            rollout.reset()
            results = []
            # Healthy phase
            for _ in range(10):
                monitor.record_success()
            rollout.configure(
                check_rollback_fn=monitor.check_rollback_needed,
                save_baseline_fn=monitor.save_baseline,
            )
            with patch("modules.monitor.main.get_memory_usage_bytes",
                       return_value=100):
                results.append(rollout.try_scale_up())
            # Unhealthy phase: add errors
            for _ in range(20):
                monitor.record_error()
            with patch("modules.monitor.main.get_memory_usage_bytes",
                       return_value=100):
                results.append(rollout.try_scale_up())
            return results

        first_run = run_alternating()
        second_run = run_alternating()
        self.assertEqual(first_run, second_run)


if __name__ == "__main__":
    unittest.main()
