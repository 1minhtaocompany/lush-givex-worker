"""T-07 — URL ``?error=vv`` routes to Ngã rẽ 4 (declined).

``GivexDriver.detect_page_state`` must return ``"declined"`` when the current
URL contains the Givex VBV failure signal ``error=vv``.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.cdp.driver import GivexDriver  # noqa: E402
from _e2e_harness import E2EBase  # noqa: E402


class TestT07UrlErrorVvRoutesDeclined(E2EBase):
    """T-07: URL with ``?error=vv`` must resolve to FSM state ``declined``."""

    def _make_driver(self, url: str):
        base = MagicMock()
        base.current_url = url
        # No confirmation / VBV iframe / error-message elements.
        base.find_elements.return_value = []
        body_el = MagicMock()
        body_el.text = ""
        base.find_element.return_value = body_el
        gd = GivexDriver(base)
        return gd

    def test_error_vv_lowercase(self):
        gd = self._make_driver(
            "https://checkout.example.test/review?error=vv&session=1",
        )
        self.assertEqual(gd.detect_page_state(), "declined")

    def test_error_vv_uppercase_accepted(self):
        # Detection is case-insensitive per the implementation.
        gd = self._make_driver(
            "https://checkout.example.test/review?ERROR=VV",
        )
        self.assertEqual(gd.detect_page_state(), "declined")


if __name__ == "__main__":
    unittest.main()
