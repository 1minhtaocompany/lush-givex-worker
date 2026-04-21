"""T-10 — Telegram bot token must NOT leak into log output.

Asserts that when ``telegram_notifier._post`` fails, the error log message
does NOT contain the bot token value.  The notifier is configured with a
synthetic token so the test can scan log output reliably.
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.notification import telegram_notifier  # noqa: E402
from _e2e_harness import E2EBase  # noqa: E402


_FAKE_TOKEN = "123456789:AAH_THIS_IS_A_FAKE_TELEGRAM_BOT_TOKEN_xyz"


class TestT10TelegramTokenNoLeak(E2EBase):
    """T-10: Telegram token MUST NOT leak in log file/output."""

    def test_token_not_in_log_on_http_failure(self):
        import urllib.error

        # Capture telegram_notifier logs.
        log_records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                log_records.append(record)

        tg_log = logging.getLogger("modules.notification.telegram_notifier")
        handler = _Capture(level=logging.DEBUG)
        tg_log.addHandler(handler)
        tg_log.setLevel(logging.DEBUG)

        url = f"https://api.telegram.org/bot{_FAKE_TOKEN}/sendMessage"
        try:
            with patch(
                "modules.notification.telegram_notifier.urllib.request.urlopen",
                side_effect=urllib.error.URLError("boom"),
            ):
                result = telegram_notifier._post(url, b"chat_id=42&text=hi")
        finally:
            tg_log.removeHandler(handler)

        self.assertFalse(result, "POST must fail to trigger the warning path")
        self.assertTrue(log_records, "expected at least one log record")

        # Scan every captured log message.
        for rec in log_records:
            msg = rec.getMessage()
            self.assertNotIn(
                _FAKE_TOKEN, msg,
                f"Telegram token leaked in log record: {msg!r}",
            )
            # Also guard against the BIN (pre-colon) leaking on its own.
            self.assertNotIn(
                "123456789:AAH", msg,
                f"Telegram token leaked (prefix) in log record: {msg!r}",
            )


if __name__ == "__main__":
    unittest.main()
