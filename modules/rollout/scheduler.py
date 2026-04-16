"""Local rollout scheduler: stable-window tracking and interval management.

Responsibilities
----------------
* Manage the stable-window anchor (``_stable_since``) used to decide when the
  rollout is eligible to advance.
* Ensure **all mutations** to ``_stable_since`` are performed while holding
  ``_lock`` so that concurrent callers (e.g. ``advance_step()`` called from
  outside while the loop is running) cannot produce a TOCTOU window.
* Clamp the polling interval to a finite, positive range so that edge-case
  values (NaN, ±infinity, negative numbers) cannot silently produce unsafe
  scheduling behavior.

Cross-module isolation
----------------------
This module must not import from any other ``modules.*`` package except
``modules.rollout``.  All external behaviour (health / stability checking)
is injected through :func:`configure`.
"""

import logging
import math
import threading
import time

from modules.rollout import main as rollout

_logger = logging.getLogger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────

STABLE_DURATION_SECONDS: float = 43200.0
"""Duration of uninterrupted stability required before advancing (12 h)."""

_MIN_INTERVAL: float = 1.0
"""Minimum allowed polling interval in seconds."""

_MAX_INTERVAL: float = 86400.0
"""Maximum allowed polling interval in seconds (24 h)."""

_DEFAULT_INTERVAL: float = 300.0
"""Fallback polling interval used when the supplied value is not usable."""

# ── Module-level state ────────────────────────────────────────────────────────

_lock = threading.Lock()
_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None

# Stable-window anchor.  Set to ``time.monotonic()`` when health is first
# confirmed; reset to ``None`` on any scaling event or instability.
# ALL reads and writes MUST be performed while holding ``_lock``.
_stable_since: float | None = None

# Injected callback: ``() -> bool`` — returns True when the system is stable.
_is_stable_fn = None


# ── Interval clamping ─────────────────────────────────────────────────────────

def _clamp_interval(interval) -> float:
    """Return *interval* clamped to ``[_MIN_INTERVAL, _MAX_INTERVAL]``.

    NaN, ±infinity, non-numeric, and out-of-range values are all handled
    explicitly so that the scheduler loop is never started with an unsafe
    or undefined polling period.

    Args:
        interval: Candidate polling interval (seconds).  Any type accepted;
            non-convertible values fall back to :data:`_DEFAULT_INTERVAL`.

    Returns:
        A finite float in ``[_MIN_INTERVAL, _MAX_INTERVAL]``.
    """
    try:
        v = float(interval)
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL
    if not math.isfinite(v) or v < _MIN_INTERVAL:
        return _MIN_INTERVAL
    return min(v, _MAX_INTERVAL)


# ── Dependency injection ──────────────────────────────────────────────────────

def configure(is_stable_fn=None) -> None:
    """Inject the stability-check callback used by the scheduler loop.

    Args:
        is_stable_fn: Callable ``() -> bool`` returning *True* when the
            current system state is considered stable.  Pass ``None`` to
            disable proactive advance (the scheduler runs but never marks
            the window as stable).
    """
    global _is_stable_fn
    with _lock:
        _is_stable_fn = is_stable_fn


# ── Internal helpers ──────────────────────────────────────────────────────────

def _reset_stable_locked() -> None:
    """Reset the stable-window anchor.  Caller **must** hold ``_lock``."""
    global _stable_since
    _stable_since = None


def _do_advance() -> None:
    """Attempt to advance to the next rollout step and reset stable window."""
    global _stable_since
    workers, action, reasons = rollout.try_scale_up()
    if action == "scaled_up":
        _logger.info(
            "rollout advanced to step %d: %d workers",
            rollout.get_current_step_index(),
            workers,
        )
    elif action == "rollback":
        _logger.warning("rollback triggered: %s", "; ".join(reasons))
    elif action == "at_max":
        _logger.info("rollout complete: at max workers")
        return
    else:
        # Unknown action returned by try_scale_up — do not reset the stable
        # window; no scaling event has occurred.
        return
    # Reset stable window after a known scaling event (scaled_up or rollback).
    with _lock:
        _reset_stable_locked()


def _scheduler_loop(interval: float) -> None:
    """Main scheduler loop — runs in a background daemon thread.

    Stable-window semantics (serialized)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    All reads **and** the eligibility decision for ``_stable_since`` are
    performed within a single ``_lock`` acquisition.  This eliminates the
    TOCTOU window that would exist if the lock were released between reading
    the anchor and deciding to advance.
    """
    global _stable_since
    while not _stop_event.is_set():
        try:
            now = time.monotonic()
            with _lock:
                is_stable_fn = _is_stable_fn
            stable = is_stable_fn() if is_stable_fn is not None else False
            if not stable:
                with _lock:
                    _reset_stable_locked()
            else:
                # Serialize the read-modify-check of _stable_since so that no
                # concurrent advance_step() or reset() call can produce a TOCTOU
                # window between reading the anchor and acting on the result.
                with _lock:
                    if _stable_since is None:
                        _stable_since = now
                    snap = _stable_since
                    eligible = (now - snap) >= STABLE_DURATION_SECONDS
                # can_scale_up() is a cheap pre-check: it avoids calling
                # try_scale_up() when the rollout is already at max.  A
                # concurrent advance_step() could change the step between
                # this check and the call to _do_advance(); try_scale_up()
                # handles that case gracefully (returning "at_max").
                if eligible and rollout.can_scale_up():
                    _do_advance()
        except Exception:
            _logger.exception("scheduler loop error")
        _stop_event.wait(timeout=interval)


# ── Public API ────────────────────────────────────────────────────────────────

def start(interval: float = _DEFAULT_INTERVAL) -> bool:
    """Start the scheduler loop in a background daemon thread.

    Args:
        interval: Polling interval in seconds.  NaN, ±infinity, negative, and
            out-of-range values are clamped to the valid range
            ``[_MIN_INTERVAL, _MAX_INTERVAL]`` by :func:`_clamp_interval`.

    Returns:
        ``True`` if started; ``False`` if already running.
    """
    global _scheduler_thread
    safe_interval = _clamp_interval(interval)
    with _lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return False
        _stop_event.clear()
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(safe_interval,),
            daemon=True,
            name="rollout-scheduler",
        )
        _scheduler_thread.start()
    return True


def stop(timeout: float = 10.0) -> bool:
    """Stop the scheduler loop.

    Returns:
        ``True`` if stopped cleanly; ``False`` if timed out or not running.
    """
    with _lock:
        thread = _scheduler_thread
    if thread is None or not thread.is_alive():
        return False
    _stop_event.set()
    thread.join(timeout=timeout)
    return not thread.is_alive()


def get_status() -> dict:
    """Return a scheduler status snapshot."""
    with _lock:
        running = _scheduler_thread is not None and _scheduler_thread.is_alive()
        stable_since = _stable_since
    step = rollout.get_current_step_index()
    workers = rollout.get_current_workers()
    max_idx = len(rollout.SCALE_STEPS) - 1
    complete = step == max_idx
    next_workers = rollout.SCALE_STEPS[step + 1] if step < max_idx else None
    now = time.monotonic()
    if stable_since is not None:
        elapsed = now - stable_since
        seconds_until = max(0.0, STABLE_DURATION_SECONDS - elapsed)
        eligible = elapsed >= STABLE_DURATION_SECONDS
    else:
        seconds_until, eligible = None, False
    return {
        "running": running,
        "current_step": step,
        "current_workers": workers,
        "next_workers": next_workers,
        "stable_since": stable_since,
        "seconds_until_advance": seconds_until,
        "advance_eligible": eligible,
        "rollout_complete": complete,
    }


def advance_step() -> tuple[bool, str]:
    """Manually trigger advance to the next rollout step.

    The stable-window anchor is reset under ``_lock`` immediately after any
    scaling event to keep scheduler state consistent.

    Returns:
        ``(success, reason)`` pair.
    """
    global _stable_since
    if not rollout.can_scale_up():
        return False, "at max step"
    workers, action, reasons = rollout.try_scale_up()
    if action == "scaled_up":
        with _lock:
            _reset_stable_locked()
        return True, f"advanced to {workers} workers"
    if action == "rollback":
        with _lock:
            _reset_stable_locked()
        return False, "rollback: " + "; ".join(reasons)
    return False, action


def reset() -> None:
    """Reset all scheduler state.  Intended for testing."""
    global _scheduler_thread, _stable_since
    _stop_event.set()
    with _lock:
        thread = _scheduler_thread
    if thread is not None:
        thread.join(timeout=5.0)
    with _lock:
        _scheduler_thread = None
        _reset_stable_locked()
    _stop_event.clear()
