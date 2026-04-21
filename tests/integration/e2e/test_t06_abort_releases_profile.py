"""T-06 — Card pool exhausted → abort_cycle + profile released cleanly.

When all cards in the queue are exhausted, run_cycle must:
  * Return ``abort_cycle``.
  * NOT call ``mark_completed`` (task remains eligible to be re-picked).
  * Always call ``release_inflight`` in finally (profile / task released).
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


class TestT06AbortReleasesProfile(E2EBase):
    """T-06: card pool exhausted → abort_cycle + release_inflight + no mark_completed."""

    def test_abort_cycle_releases_profile_cleanly(self):
        # No order_queue → only the primary card available.  A single decline
        # empties the swap pool immediately.
        task = make_task(task_id="t06-exhaust-001", order_queue=())
        ctx = CycleContext(cycle_id="t06-ctx", worker_id=self.worker_id)

        store = MagicMock()
        store.is_duplicate.return_value = False

        with patch("integration.orchestrator.run_payment_step",
                   return_value=(State("declined"), "50.00")), \
             patch("integration.orchestrator.initialize_cycle"), \
             patch("integration.orchestrator.billing") as billing, \
             patch("integration.orchestrator.cdp") as cdp_mod, \
             patch(_STORE_PATCH, return_value=store):
            billing.select_profile.return_value = MagicMock(
                zip_code="10001", email="b@example.test",
            )
            cdp_mod._get_driver.return_value = MagicMock()
            action, state, _total = run_cycle(
                task, worker_id=self.worker_id, ctx=ctx,
            )

        self.assertEqual(action, "abort_cycle")
        self.assertEqual(state.name, "declined")
        # No completion checkpoint should be persisted.
        store.mark_completed.assert_not_called()
        # Release must have fired (profile / task released in finally).
        store.release_inflight.assert_called_once_with("t06-exhaust-001")


if __name__ == "__main__":
    unittest.main()
