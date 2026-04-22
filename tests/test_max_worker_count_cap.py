"""End-to-end tests for the MAX_WORKER_COUNT cap wiring.

Verifies that MAX_WORKER_COUNT propagates from the environment, through
``runtime.start()``, into ``rollout.SCALE_STEPS`` and ultimately into
``_apply_scale`` targets — so the runtime never scales above the configured
cap.
"""
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from integration import runtime
from integration.runtime import ConfigError, reset, start, stop
from modules.billing import main as billing
from modules.monitor import main as monitor
from modules.rollout import main as rollout


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class _MaxWorkerCapMixin:
    def setUp(self):
        reset()
        rollout.reset()
        monitor.reset()
        self._saved_env = os.environ.get("MAX_WORKER_COUNT")
        self._saved_worker = os.environ.get("WORKER_COUNT")
        self._billing_pool_dir = tempfile.mkdtemp()
        with open(
            os.path.join(self._billing_pool_dir, "profiles.txt"),
            "w", encoding="utf-8",
        ) as handle:
            handle.write(
                "Alice|Smith|1 Main St|City|NY|10001|2125550001|a@e.com\n"
            )
        self._billing_pool_patcher = patch.object(
            billing, "_pool_dir",
            return_value=Path(self._billing_pool_dir),
        )
        self._billing_pool_patcher.start()

    def tearDown(self):
        self._billing_pool_patcher.stop()
        shutil.rmtree(self._billing_pool_dir, ignore_errors=True)
        if self._saved_env is None:
            os.environ.pop("MAX_WORKER_COUNT", None)
        else:
            os.environ["MAX_WORKER_COUNT"] = self._saved_env
        if self._saved_worker is None:
            os.environ.pop("WORKER_COUNT", None)
        else:
            os.environ["WORKER_COUNT"] = self._saved_worker
        reset()
        rollout.reset()
        monitor.reset()


class TestMaxWorkerCountCapE2E(_MaxWorkerCapMixin, unittest.TestCase):
    """End-to-end: runtime loop never requests a target above the cap."""

    def _run_for_cap(self, n):
        os.environ["MAX_WORKER_COUNT"] = str(n)
        os.environ.pop("WORKER_COUNT", None)
        applied: list[int] = []
        lock = threading.Lock()

        def _record(target, _task_fn):
            with lock:
                applied.append(target)

        with patch("integration.runtime._apply_scale", side_effect=_record):
            started = start(lambda _: None, interval=0.02)
            self.assertTrue(started)
            try:
                _wait_until(
                    lambda: len(applied) >= 3, timeout=2.0, interval=0.02,
                )
            finally:
                stop(timeout=2)
        return applied

    def test_runtime_never_exceeds_cap_n1(self):
        self._assert_cap(1)

    def test_runtime_never_exceeds_cap_n2(self):
        self._assert_cap(2)

    def test_runtime_never_exceeds_cap_n4(self):
        self._assert_cap(4)

    def test_runtime_never_exceeds_cap_n7(self):
        self._assert_cap(7)

    def test_runtime_never_exceeds_cap_n10(self):
        self._assert_cap(10)

    def test_runtime_never_exceeds_cap_n12(self):
        self._assert_cap(12)

    def _assert_cap(self, n):
        applied = self._run_for_cap(n)
        self.assertTrue(
            applied, f"expected at least one _apply_scale call for cap={n}",
        )
        self.assertTrue(
            all(t <= n for t in applied),
            f"_apply_scale targets exceeded cap={n}: {applied}",
        )
        # SCALE_STEPS must terminate at exactly the cap.
        self.assertEqual(rollout.SCALE_STEPS[-1], n)


class TestValidateStartupConfigMaxWorkerCount(_MaxWorkerCapMixin, unittest.TestCase):
    """_validate_startup_config enforces MAX_WORKER_COUNT range & coupling."""

    def test_rejects_non_integer(self):
        os.environ["MAX_WORKER_COUNT"] = "abc"
        with self.assertRaises(ConfigError):
            runtime._validate_startup_config()  # pylint: disable=protected-access

    def test_rejects_zero(self):
        os.environ["MAX_WORKER_COUNT"] = "0"
        with self.assertRaises(ConfigError):
            runtime._validate_startup_config()  # pylint: disable=protected-access

    def test_rejects_over_50(self):
        os.environ["MAX_WORKER_COUNT"] = "51"
        with self.assertRaises(ConfigError):
            runtime._validate_startup_config()  # pylint: disable=protected-access

    def test_rejects_worker_count_above_max(self):
        os.environ["MAX_WORKER_COUNT"] = "3"
        os.environ["WORKER_COUNT"] = "5"
        with self.assertRaises(ConfigError):
            runtime._validate_startup_config()  # pylint: disable=protected-access

    def test_accepts_worker_count_equal_to_max(self):
        os.environ["MAX_WORKER_COUNT"] = "5"
        os.environ["WORKER_COUNT"] = "5"
        # Should not raise.
        runtime._validate_startup_config()  # pylint: disable=protected-access

    def test_accepts_unset_max(self):
        os.environ.pop("MAX_WORKER_COUNT", None)
        os.environ["WORKER_COUNT"] = "3"
        # Should not raise when MAX_WORKER_COUNT is not set.
        runtime._validate_startup_config()  # pylint: disable=protected-access


class TestApplyScaleDefensiveClamp(_MaxWorkerCapMixin, unittest.TestCase):
    """_apply_scale defensively clamps targets above SCALE_STEPS[-1]."""

    def test_clamp_logs_warning_and_reduces_target(self):
        os.environ["MAX_WORKER_COUNT"] = "4"
        rollout.configure_max_workers(4)
        launches: list[None] = []

        # Stub worker start to avoid real threads; count launches to verify
        # the clamp reduced the requested target down to the cap (4).
        def _fake_start(_task_fn):
            launches.append(None)

        runtime._state = "RUNNING"  # pylint: disable=protected-access
        try:
            with patch("integration.runtime.start_worker", side_effect=_fake_start), \
                 patch("integration.runtime._logger") as mock_logger:
                runtime._apply_scale(99, lambda _: None)  # pylint: disable=protected-access
                # Requested 99; cap is 4 → exactly 4 launches must be attempted.
                self.assertEqual(len(launches), 4)
                # A warning must have been emitted.
                self.assertTrue(
                    any(
                        "clamp target" in str(call.args[0])
                        for call in mock_logger.warning.call_args_list
                    ),
                    "expected a 'clamp target' warning log",
                )
        finally:
            runtime._state = "INIT"  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
