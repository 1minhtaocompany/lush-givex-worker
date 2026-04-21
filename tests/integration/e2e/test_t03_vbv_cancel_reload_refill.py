"""T-03 — VBV cancel → reload → refill full sequence.

When state is ``vbv_cancelled`` and ``is_payment_page_reloaded`` returns True,
``refill_after_vbv_reload`` must execute the complete purchase sequence:
preflight_geo_check → navigate_to_egift → fill_egift_form →
add_to_cart_and_checkout → select_guest_checkout → fill_payment_and_billing.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.common.types import CycleContext  # noqa: E402
from integration.orchestrator import refill_after_vbv_reload  # noqa: E402
from _e2e_harness import (  # noqa: E402
    E2EBase,
    make_billing_profile,
    make_card,
    make_task,
)


class TestT03VbvCancelReload(E2EBase):
    """T-03: VBV cancel → reload → full refill (egift→cart→guest→payment)."""

    def test_refill_after_vbv_reload_full_sequence(self):
        new_card = make_card("2222")
        task = make_task(task_id="t03-vbv-reload-001",
                         order_queue=(new_card,))
        profile = make_billing_profile()
        ctx = CycleContext(
            cycle_id="t03-ctx",
            worker_id=self.worker_id,
            task=task,
            billing_profile=profile,
        )

        driver = MagicMock()
        refill_after_vbv_reload(driver, ctx, new_card)

        # Required full-refill sequence — order-sensitive.
        driver.preflight_geo_check.assert_called_once_with()
        driver.navigate_to_egift.assert_called_once_with()
        driver.fill_egift_form.assert_called_once_with(task, profile)
        driver.add_to_cart_and_checkout.assert_called_once_with()
        driver.select_guest_checkout.assert_called_once_with(profile.email)
        driver.fill_payment_and_billing.assert_called_once_with(new_card, profile)

        # Order assertion: preflight before navigate before egift…payment last.
        observed = [c[0] for c in driver.mock_calls
                    if c[0] in {
                        "preflight_geo_check", "navigate_to_egift",
                        "fill_egift_form", "add_to_cart_and_checkout",
                        "select_guest_checkout", "fill_payment_and_billing",
                    }]
        self.assertEqual(observed, [
            "preflight_geo_check",
            "navigate_to_egift",
            "fill_egift_form",
            "add_to_cart_and_checkout",
            "select_guest_checkout",
            "fill_payment_and_billing",
        ])


if __name__ == "__main__":
    unittest.main()
