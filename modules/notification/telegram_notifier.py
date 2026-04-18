"""Telegram Bot notifier for success/alert events.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED (1/true/yes).
"""
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from modules.notification.card_masker import mask_card_number

_logger = logging.getLogger(__name__)
_API = "https://api.telegram.org"
_ENABLED = {"1", "true", "yes"}


def _enabled() -> bool:
    return os.environ.get("TELEGRAM_ENABLED", "").strip().lower() in _ENABLED


def _post(url: str, data: bytes, headers=None, timeout: int = 10) -> bool:
    if not url.lower().startswith("https://"):
        _logger.warning("telegram_notifier: refusing non-HTTPS URL %r", url)
        return False
    try:
        req = urllib.request.Request(url, data=data, method="POST", headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310  # noqa: S310
            pass
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _logger.warning("telegram_notifier: POST %s failed: %s", url.rsplit("/", 1)[-1], exc)
        return False


def _send_message(token: str, chat_id: str, text: str) -> bool:
    return _post(f"{_API}/bot{token}/sendMessage",
                 urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode())


def _send_photo(token: str, chat_id: str, photo: bytes, caption: str) -> bool:
    boundary = "----TelegramBoundary"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
            f"filename=\"screenshot.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body = head + photo + f"\r\n--{boundary}--\r\n".encode()
    return _post(f"{_API}/bot{token}/sendPhoto", body,
                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def _credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return (token, chat_id) if (token and chat_id) else (None, None)


def send_success_notification(worker_id: str, task, total, screenshot_bytes):
    """Send a success notification to Telegram. Never raises."""
    if not _enabled():
        return False
    token, chat_id = _credentials()
    if token is None:
        _logger.warning("telegram_notifier: TELEGRAM_BOT_TOKEN/CHAT_ID not set.")
        return False
    try:
        card = getattr(getattr(task, "primary_card", None), "card_number", "")
        recipient = getattr(task, "recipient_email", "")
        msg = (f"✅ SUCCESS — Worker {worker_id}\n💰 Amount: ${total}\n"
               f"📧 Recipient: {recipient}\n💳 Card: {mask_card_number(card)}\n"
               f"🕐 Time: {datetime.utcnow().isoformat()}")
        if screenshot_bytes is not None:
            return _send_photo(token, chat_id, screenshot_bytes, msg)
        return _send_message(token, chat_id, msg)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("telegram_notifier: unexpected error: %s", exc)
        return False


def _send_alert_to_telegram(message: str) -> None:
    if not _enabled():
        return
    token, chat_id = _credentials()
    if token is None:
        return
    try:
        _send_message(token, chat_id, f"⚠️ ALERT: {message}")
    except Exception as exc:  # noqa: BLE001
        _logger.warning("telegram_notifier: alert forward failed: %s", exc)


def register_as_alert_handler() -> None:
    """Register Telegram handler with optional ``modules.observability.alerting``."""
    try:
        from modules.observability import alerting  # noqa: PLC0415
    except ImportError as exc:
        _logger.warning("telegram_notifier: alerting unavailable: %s", exc)
        return
    alerting.register_alert_handler(_send_alert_to_telegram)
