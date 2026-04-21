"""T-05 — Thank-you popup text-match is exact and rejects cookie-modal text.

Verifies:
  * Thank-you patterns (EN + VN) match confirmation text.
  * Cookie-modal body text like "We use cookies to improve your experience"
    does NOT trigger a false positive.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.cdp.driver import detect_popup_thank_you  # noqa: E402
from _e2e_harness import E2EBase  # noqa: E402


def _driver(url: str = "", body_text: str = ""):
    base = MagicMock()
    base.current_url = url
    body_el = MagicMock()
    body_el.text = body_text
    base.find_element.return_value = body_el
    base.execute_script.return_value = ""  # no shadow DOM match
    wrapper = MagicMock()
    wrapper._driver = base
    return wrapper


class TestT05PopupTextMatch(E2EBase):
    """T-05: popup text-match is exact — no cookie-modal false positive."""

    def test_thank_you_confirmation_matches(self):
        # EN pattern
        self.assertTrue(detect_popup_thank_you(
            _driver(body_text="Thank you for your order, user!"),
        ))
        # VN pattern
        self.assertTrue(detect_popup_thank_you(
            _driver(body_text="Cảm ơn bạn đã đặt hàng"),
        ))

    def test_cookie_modal_does_not_match(self):
        # Classic cookie-banner text — must NOT be treated as thank-you popup.
        cookie_text = (
            "We use cookies to improve your experience. "
            "By clicking Accept, you agree to our cookie policy."
        )
        self.assertFalse(detect_popup_thank_you(
            _driver(body_text=cookie_text),
        ))

        # GDPR-style text — another common false-positive trap.
        gdpr_text = (
            "This website uses cookies and similar technologies to provide "
            "core site functionality and analytics."
        )
        self.assertFalse(detect_popup_thank_you(
            _driver(body_text=gdpr_text),
        ))


if __name__ == "__main__":
    unittest.main()
