"""T-13 — Card mask Amex 15 digits → ``411111*****1111``.

``modules.notification.card_masker.mask_card_number`` keeps the BIN (first 6)
and last 4 digits, masking the middle.  For a 15-digit card that is
6 + 5 asterisks + 4 = ``411111*****1111``.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.notification.card_masker import mask_card_number  # noqa: E402
from _e2e_harness import E2EBase  # noqa: E402


class TestT13CardMaskAmex(E2EBase):
    """T-13: 15-digit Amex masks to ``411111*****1111``."""

    def test_amex_15_digits_expected_shape(self):
        # A 15-digit PAN starting with 411111 and ending with 1111.
        pan = "411111" + "23456" + "1111"  # 6 + 5 + 4 = 15 digits
        self.assertEqual(len(pan), 15)
        self.assertEqual(mask_card_number(pan), "411111*****1111")

    def test_amex_15_digits_exact_example(self):
        # Exact example from the issue acceptance criterion.
        self.assertEqual(mask_card_number("411111234561111"), "411111*****1111")

    def test_visa_16_digits_unchanged_contract(self):
        # Sanity: 16-digit Visa → 6 + 6 asterisks + 4.
        self.assertEqual(
            mask_card_number("4111111111111111"), "411111******1111",
        )

    def test_whitespace_and_dashes_stripped(self):
        # 15-digit with spaces/dashes should mask identically.
        self.assertEqual(
            mask_card_number("4111-11 23 456 1111"), "411111*****1111",
        )


if __name__ == "__main__":
    unittest.main()
