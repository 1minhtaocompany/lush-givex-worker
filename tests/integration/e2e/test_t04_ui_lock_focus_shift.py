"""T-04 — UI lock → focus_shift called exactly once → 2nd attempt success.

When ``run_payment_step`` reports ``ui_lock`` the orchestrator invokes
``cdp.handle_ui_lock_focus_shift`` then re-detects the page state.  If the
re-detection returns a non-lock state the cycle should complete without
firing focus_shift again.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.common.types import CycleContext, State  # noqa: E402
from integration.orchestrator import run_cycle  # noqa: E402
from _e2e_harness import (  # noqa: E402
    E2EBase,
    _STORE_PATCH,
    fresh_store_mock,
    make_task,
)


class TestT04UiLockFocusShift(E2EBase):
    """T-04: UI lock triggers exactly one focus_shift then 2nd attempt succeeds."""

    def test_focus_shift_called_exactly_once_then_success(self):
        task = make_task(task_id="t04-ui-lock-001")

        billing = MagicMock()
        billing.select_profile.return_value = MagicMock(
            zip_code="10001", email="b@example.test",
        )

        with patch("integration.orchestrator.run_payment_step",
                   return_value=(State("ui_lock"), "0.00")), \
             patch("integration.orchestrator.billing", billing), \
             patch(_STORE_PATCH, return_value=fresh_store_mock()), \
             patch("integration.orchestrator._notify_success"), \
             patch("integration.orchestrator.initialize_cycle"), \
             patch("integration.orchestrator._alerting"), \
             patch("integration.orchestrator.fsm") as mock_fsm, \
             patch("integration.orchestrator.cdp") as mock_cdp:
            mock_cdp.handle_ui_lock_focus_shift.return_value = True
            # First re-detect still returns ui_lock; the second returns success.
            # handle_outcome then sees State("success") and returns "complete".
            mock_cdp.detect_page_state.return_value = "success"
            mock_cdp._get_driver.return_value = MagicMock()
            mock_fsm.transition_for_worker.return_value = State("success")
            action, state, _total = run_cycle(
                task, worker_id=self.worker_id,
                ctx=CycleContext(cycle_id="t04-ctx", worker_id=self.worker_id),
            )

        self.assertEqual(action, "complete")
        self.assertEqual(state.name, "success")
        # focus_shift should fire EXACTLY once (T-04 acceptance).
        self.assertEqual(
            mock_cdp.handle_ui_lock_focus_shift.call_count, 1,
            f"focus_shift must be called exactly once, "
            f"got {mock_cdp.handle_ui_lock_focus_shift.call_count}",
        )


if __name__ == "__main__":
    unittest.main()
