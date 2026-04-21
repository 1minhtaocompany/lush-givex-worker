"""T-02 — 3 declined cards → swap chain, card #3 used, swap_count increments.

The order_queue contains two swap cards.  With the primary card + two swaps
we have 3 cards total; each one declines.  run_cycle should:

    primary (A)  → declined  → retry_new_card (B)
    swap  (B)    → declined  → retry_new_card (C)
    swap  (C)    → declined  → abort_cycle (queue empty, can't swap further)
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.common.types import CycleContext  # noqa: E402
from integration.orchestrator import run_cycle  # noqa: E402
from _e2e_harness import E2EBase, fresh_store_mock, make_card, make_task  # noqa: E402


class TestT02SwapChain(E2EBase):
    """T-02: swap chain exhausts 3 declined cards then aborts."""

    def test_three_declines_swap_chain(self):
        card_b = make_card("2222")
        card_c = make_card("3333")
        task = make_task(
            task_id="t02-swap-001",
            order_queue=(card_b, card_c),
        )
        ctx = CycleContext(cycle_id="t02-ctx", worker_id=self.worker_id)

        from modules.common.types import State
        from unittest.mock import MagicMock

        swap_driver = MagicMock()

        # Every attempt returns (declined, 50.00).
        with patch("integration.orchestrator.run_payment_step",
                   return_value=(State("declined"), "50.00")), \
             patch("integration.orchestrator.initialize_cycle"), \
             patch("integration.orchestrator.billing") as billing, \
             patch("integration.orchestrator.cdp") as cdp_mod, \
             patch("integration.orchestrator._get_idempotency_store",
                   return_value=fresh_store_mock()):
            billing.select_profile.return_value = object()
            cdp_mod._get_driver.return_value = swap_driver
            action, state, _total = run_cycle(
                task, worker_id=self.worker_id, ctx=ctx,
            )

        self.assertEqual(action, "abort_cycle")
        self.assertEqual(state.name, "declined")
        # swap_count advances once for each swap slot consumed (queue size = 2).
        self.assertEqual(ctx.swap_count, 2)
        # Verify the final swap actually wired the third card (card_c).
        # fill_card_fields is invoked by the retry_new_card CDP swap path.
        fill_calls = swap_driver.fill_card_fields.call_args_list
        self.assertTrue(
            any(call.args and call.args[0] is card_c for call in fill_calls),
            f"Expected swap chain to fill card_c on the final attempt, "
            f"got fill_card_fields calls: {fill_calls}",
        )


if __name__ == "__main__":
    unittest.main()
