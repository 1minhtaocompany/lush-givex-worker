"""T-01 — E2E happy path.

FSM must transition to ``success`` and the Telegram success notifier must
receive a blurred PNG (via ``_notify_success`` → ``capture_and_blur`` →
``send_success_notification``).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.cdp.main as _cdp_main  # noqa: E402
from integration.orchestrator import run_cycle  # noqa: E402
from _e2e_harness import (  # noqa: E402
    E2EBase,
    _STORE_PATCH,
    _StubGivexDriver,
    fresh_store_mock,
    make_mock_billing,
    make_task,
)


class TestT01HappyPath(E2EBase):
    """T-01: E2E happy path → FSM ghi success + Telegram blur PNG."""

    def test_happy_path_success_and_telegram_blur_png(self):
        task = make_task(task_id="t01-happy-001")
        stub = _StubGivexDriver(self.worker_id, final_state="success", dom_total="50.00")
        _cdp_main.register_driver(self.worker_id, stub)

        with patch("integration.orchestrator.billing", make_mock_billing()), \
             patch(_STORE_PATCH, return_value=fresh_store_mock()), \
             patch("modules.notification.screenshot_blur.capture_and_blur",
                   return_value=b"\x89PNG\r\n\x1a\n-blurred") as cap, \
             patch("modules.notification.telegram_notifier.send_success_notification") as send:
            action, state, total = run_cycle(task, worker_id=self.worker_id)

        # FSM/orchestrator
        self.assertEqual(action, "complete")
        self.assertIsNotNone(state)
        self.assertEqual(state.name, "success")
        self.assertEqual(total, 50.0)

        # Telegram received a blurred PNG payload (T-01 acceptance).
        cap.assert_called_once()
        send.assert_called_once()
        _args, _kwargs = send.call_args
        # send_success_notification(worker_id, task, total, screenshot)
        screenshot = _args[3] if len(_args) >= 4 else _kwargs.get("screenshot")
        self.assertIsNotNone(screenshot)
        self.assertTrue(screenshot.startswith(b"\x89PNG"),
                        f"Expected PNG bytes, got {screenshot!r}")


if __name__ == "__main__":
    unittest.main()
