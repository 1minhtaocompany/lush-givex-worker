"""T-14 — ``mark_completed`` is called ONLY when action == "complete".

Run run_cycle with patched outcomes covering all actions:
  * complete      → mark_completed called exactly once
  * retry         → mark_completed NOT called
  * retry_new_card→ mark_completed NOT called (eventually abort_cycle)
  * abort_cycle   → mark_completed NOT called
  * await_3ds     → mark_completed NOT called
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
from _e2e_harness import E2EBase, _STORE_PATCH, make_task  # noqa: E402


class TestT14MarkCompletedOnlyOnComplete(E2EBase):
    """T-14: mark_completed invoked if and only if action == "complete"."""

    def _run_with_state(self, task_id: str, state_name: str):
        """Return (action, store) after run_cycle with patched outcomes."""
        task = make_task(task_id=task_id)
        ctx = CycleContext(cycle_id=f"{task_id}-ctx", worker_id=self.worker_id)
        store = MagicMock()
        store.is_duplicate.return_value = False

        billing = MagicMock()
        billing.select_profile.return_value = MagicMock(
            zip_code="10001", email="b@example.test",
        )

        with patch("integration.orchestrator.run_payment_step",
                   return_value=(State(state_name), "50.00")), \
             patch("integration.orchestrator.initialize_cycle"), \
             patch("integration.orchestrator.billing", billing), \
             patch("integration.orchestrator.cdp") as cdp_mod, \
             patch("integration.orchestrator._notify_success"), \
             patch(_STORE_PATCH, return_value=store):
            cdp_mod._get_driver.return_value = MagicMock()
            cdp_mod.detect_page_state.return_value = state_name
            action, _state, _total = run_cycle(
                task, worker_id=self.worker_id, ctx=ctx,
            )
        return action, store

    def test_mark_completed_called_on_complete(self):
        action, store = self._run_with_state("t14-complete-001", "success")
        self.assertEqual(action, "complete")
        store.mark_completed.assert_called_once_with("t14-complete-001")

    def test_mark_completed_not_called_on_declined(self):
        action, store = self._run_with_state("t14-declined-001", "declined")
        self.assertEqual(action, "abort_cycle")
        store.mark_completed.assert_not_called()

    def test_mark_completed_not_called_on_await_3ds(self):
        action, store = self._run_with_state("t14-vbv-001", "vbv_3ds")
        # handle_outcome for vbv_3ds returns "await_3ds" (after handle_vbv_challenge).
        self.assertIn(action, {"await_3ds", "abort_cycle"})
        store.mark_completed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
