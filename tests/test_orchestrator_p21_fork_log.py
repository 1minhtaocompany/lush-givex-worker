"""P2-1 tests: FORK=X structured log in handle_outcome (#120).

Verifies that handle_outcome emits a log line containing:
  "FORK=<state>" for each recognised branch (success, declined,
  vbv_cancelled, ui_lock, vbv_3ds) as well as the default (unknown state).
The log record must also contain the worker_id and swap count.
"""
# pylint: disable=protected-access
import logging
import unittest
from unittest.mock import MagicMock, patch

from integration.orchestrator import handle_outcome
from modules.common.types import CycleContext, State

_WORKER = "p21-log-test"
_LOGGER_NAME = "integration.orchestrator"


def _make_ctx(swap: int = 0) -> CycleContext:
    return CycleContext(
        cycle_id="p21-test-cycle",
        worker_id=_WORKER,
        swap_count=swap,
    )


class ForkLogSuccessTest(unittest.TestCase):
    def test_fork_success_logged(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            handle_outcome(State("success"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=success" in line for line in cm.output))

    def test_fork_success_contains_worker(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            handle_outcome(State("success"), (), worker_id=_WORKER)
        self.assertTrue(any(_WORKER in line for line in cm.output))

    def test_fork_success_swap_zero(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            handle_outcome(State("success"), (), worker_id=_WORKER)
        self.assertTrue(any("swap=0" in line for line in cm.output))


class ForkLogDeclinedTest(unittest.TestCase):
    def test_fork_declined_logged(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            with patch("integration.orchestrator._alerting") as m:
                m.send_alert.return_value = None
                handle_outcome(State("declined"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=declined" in line for line in cm.output))

    def test_fork_declined_swap_count(self):
        ctx = _make_ctx(swap=2)
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            with patch("integration.orchestrator._alerting") as m:
                m.send_alert.return_value = None
                handle_outcome(State("declined"), (), worker_id=_WORKER, ctx=ctx)
        self.assertTrue(any("swap=2" in line for line in cm.output))


class ForkLogVbvCancelledTest(unittest.TestCase):
    def test_fork_vbv_cancelled_logged(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            with patch("integration.orchestrator._alerting") as m:
                m.send_alert.return_value = None
                handle_outcome(State("vbv_cancelled"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=vbv_cancelled" in line for line in cm.output))


class ForkLogUiLockTest(unittest.TestCase):
    def test_fork_ui_lock_logged(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            handle_outcome(State("ui_lock"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=ui_lock" in line for line in cm.output))


class ForkLogVbv3dsTest(unittest.TestCase):
    def test_fork_vbv_3ds_logged(self):
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            with patch("integration.orchestrator.cdp") as mock_cdp:
                mock_cdp._get_driver.side_effect = RuntimeError("no driver")
                handle_outcome(State("vbv_3ds"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=vbv_3ds" in line for line in cm.output))


class ForkLogDefaultTest(unittest.TestCase):
    def test_fork_unknown_logged(self):
        """Unknown state falls through to default retry branch; FORK=<name> emitted."""
        with self.assertLogs(_LOGGER_NAME, level="INFO") as cm:
            handle_outcome(State("unknown_state"), (), worker_id=_WORKER)
        self.assertTrue(any("FORK=unknown_state" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
