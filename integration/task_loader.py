"""FileTaskLoader: thread-safe pipe-delimited task reader.

Format: recipient_email|amount|card|exp_m|exp_y|cvv[|card2|m|y|cvv2|...]
"""
from __future__ import annotations

import logging
import os
import threading
from typing import List, Optional

from modules.common.types import CardInfo, WorkerTask

_logger = logging.getLogger(__name__)
_DEFAULT_TASK_FILE = "tasks/input.txt"
_CARD_BLOCK = 4  # card_number, exp_month, exp_year, cvv
_PREFIX = 2  # recipient_email, amount


def _make_card(fields: List[str]) -> CardInfo:
    return CardInfo(card_number=fields[0].strip(), exp_month=fields[1].strip(),
                    exp_year=fields[2].strip(), cvv=fields[3].strip(), card_name="")


class FileTaskLoader:
    """Thread-safe loader; multiple workers may call ``get_task`` concurrently."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file_path = file_path or os.environ.get("TASK_INPUT_FILE", _DEFAULT_TASK_FILE)
        self._lock = threading.Lock()
        self._lines: List[str] = []
        self._index = 0
        self._loaded = False

    def _load(self) -> None:
        try:
            with open(self._file_path, encoding="utf-8") as fh:
                raw = fh.readlines()
        except OSError as exc:
            _logger.error("FileTaskLoader: cannot open %r: %s", self._file_path, exc)
            self._lines = []
            return
        self._lines = [s for s in (ln.strip() for ln in raw) if s and not s.startswith("#")]
        _logger.info("FileTaskLoader: loaded %d task(s) from %r", len(self._lines), self._file_path)

    def _parse_line(self, line: str) -> Optional[WorkerTask]:
        parts = line.split("|")
        if len(parts) < _PREFIX + _CARD_BLOCK:
            _logger.warning("FileTaskLoader: malformed line: %r", line)
            return None
        recipient = parts[0].strip()
        try:
            amount = int(parts[1].strip())
        except ValueError:
            _logger.warning("FileTaskLoader: bad amount in %r", line)
            return None
        if amount <= 0 or not recipient:
            _logger.warning("FileTaskLoader: invalid email/amount in %r", line)
            return None
        cards = parts[2:]
        primary = _make_card(cards[:_CARD_BLOCK])
        extras: List[CardInfo] = []
        i = _CARD_BLOCK
        while i + _CARD_BLOCK <= len(cards):
            extras.append(_make_card(cards[i:i + _CARD_BLOCK]))
            i += _CARD_BLOCK
        try:
            return WorkerTask(recipient_email=recipient, amount=amount,
                              primary_card=primary, order_queue=tuple(extras))
        except (ValueError, TypeError) as exc:
            _logger.warning("FileTaskLoader: WorkerTask build failed for %r: %s", line, exc)
            return None

    def get_task(self, worker_id: str) -> Optional[WorkerTask]:  # noqa: ARG002
        """Return the next WorkerTask, or None when exhausted. Thread-safe."""
        with self._lock:
            if not self._loaded:
                self._load()
                self._loaded = True
            while self._index < len(self._lines):
                line = self._lines[self._index]
                self._index += 1
                task = self._parse_line(line)
                if task is not None:
                    return task
        return None
