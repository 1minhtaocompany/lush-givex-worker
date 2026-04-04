"""Behavioral delay injection — non-uniform timing layer.

Produces human-like delay patterns before worker task execution:
  - **burst**: rapid successive short delays
  - **long_gap**: occasional long pauses
  - **normal**: non-uniform variation influenced by runtime state

Thread-safe via ``threading.Lock``.  No cross-module imports.
"""
import logging
import math
import random
import threading
import time

_logger = logging.getLogger(__name__)
_lock = threading.Lock()

# ── Delay bounds (seconds) ────────────────────────────────────────
MIN_DELAY = 0.1
MAX_DELAY = 5.0
BURST_DELAY_MIN = 0.05
BURST_DELAY_MAX = 0.3
LONG_GAP_DELAY_MIN = 3.0
LONG_GAP_DELAY_MAX = 8.0

# ── Pattern probabilities ────────────────────────────────────────
BURST_PROBABILITY = 0.15
LONG_GAP_PROBABILITY = 0.10

# ── Internal state ────────────────────────────────────────────────
_call_count = 0
_last_delay = 0.0
_burst_remaining = 0
_delay_history: list = []
_MAX_HISTORY = 100


def _compute_burst_delay():
    """Return a short delay for burst pattern."""
    return random.uniform(BURST_DELAY_MIN, BURST_DELAY_MAX)


def _compute_long_gap_delay():
    """Return a long delay for long-gap pattern."""
    return random.uniform(LONG_GAP_DELAY_MIN, LONG_GAP_DELAY_MAX)


def _compute_normal_delay():
    """Return a non-uniform normal delay with sinusoidal variation."""
    base = random.uniform(MIN_DELAY, MAX_DELAY)
    variation = math.sin(_call_count * 0.3) * 0.5
    return max(MIN_DELAY, base + variation)


def compute_delay(runtime_state=None):
    """Compute the next behavioral delay value.

    Patterns:
      - *burst*: 2-5 rapid successive short delays
      - *long_gap*: occasional long pauses
      - *normal*: non-uniform variation with sinusoidal component

    Args:
        runtime_state: Optional lifecycle state string (e.g. ``"RUNNING"``).
            ``"STOPPING"`` halves the delay; ``"INIT"`` adds 50 %.

    Returns:
        ``(delay_seconds, pattern_name)`` tuple.
    """
    global _call_count, _last_delay, _burst_remaining

    with _lock:
        _call_count += 1

        # Continue an active burst sequence
        if _burst_remaining > 0:
            _burst_remaining -= 1
            delay = _compute_burst_delay()
            pattern = "burst"
        else:
            roll = random.random()
            if roll < BURST_PROBABILITY:
                _burst_remaining = random.randint(1, 4)
                delay = _compute_burst_delay()
                pattern = "burst"
            elif roll < BURST_PROBABILITY + LONG_GAP_PROBABILITY:
                delay = _compute_long_gap_delay()
                pattern = "long_gap"
            else:
                delay = _compute_normal_delay()
                pattern = "normal"

        # Runtime-state variation
        if runtime_state == "STOPPING":
            delay *= 0.5
        elif runtime_state == "INIT":
            delay *= 1.5

        # Clamp to absolute bounds
        delay = max(BURST_DELAY_MIN, min(delay, LONG_GAP_DELAY_MAX))

        _last_delay = delay
        _delay_history.append({
            "time": time.time(),
            "delay": delay,
            "pattern": pattern,
            "call_count": _call_count,
            "runtime_state": runtime_state,
        })
        if len(_delay_history) > _MAX_HISTORY:
            _delay_history[:] = _delay_history[-_MAX_HISTORY:]

        _logger.debug(
            "Delay: %.3fs (%s) [call=%d, state=%s]",
            delay, pattern, _call_count, runtime_state,
        )
        return delay, pattern


def apply_delay(runtime_state=None):
    """Compute and sleep for a behavioral delay.

    Wraps :func:`compute_delay` and calls ``time.sleep``.

    Args:
        runtime_state: Optional lifecycle state for variation.

    Returns:
        ``(delay_seconds, pattern_name)`` tuple.
    """
    delay, pattern = compute_delay(runtime_state)
    time.sleep(delay)
    return delay, pattern


def get_delay_history():
    """Return a copy of recent delay records (bounded to 100)."""
    with _lock:
        return list(_delay_history)


def get_last_delay():
    """Return the most recently computed delay value."""
    with _lock:
        return _last_delay


def get_status():
    """Return a snapshot of delay-system state."""
    with _lock:
        return {
            "call_count": _call_count,
            "last_delay": _last_delay,
            "burst_remaining": _burst_remaining,
            "history_size": len(_delay_history),
        }


def reset():
    """Reset all delay state.  Intended for testing."""
    global _call_count, _last_delay, _burst_remaining, _delay_history
    with _lock:
        _call_count = 0
        _last_delay = 0.0
        _burst_remaining = 0
        _delay_history = []
