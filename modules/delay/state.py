"""Context-aware behavior state machine for delay decisions.

Tracks the current behavioral context of a worker within a cycle.
Operates at a *different layer* from the worker lifecycle states
(IDLE / IN_CYCLE / CRITICAL_SECTION / SAFE_POINT) defined in
``integration/runtime.py`` — the two state systems run in parallel.
"""
import threading

# Mandatory states (SPEC §10.2)
BEHAVIOR_STATES = {"IDLE", "FILLING_FORM", "PAYMENT", "VBV", "POST_ACTION"}

# Allowed transitions between behavior states
_VALID_BEHAVIOR_TRANSITIONS = {
    "IDLE": {"FILLING_FORM", "PAYMENT"},
    "FILLING_FORM": {"PAYMENT", "IDLE"},
    "PAYMENT": {"VBV", "POST_ACTION", "IDLE"},
    "VBV": {"POST_ACTION", "IDLE"},
    "POST_ACTION": {"IDLE"},
}

# States that represent critical / non-delayable contexts
_CRITICAL_CONTEXTS = {"VBV", "POST_ACTION"}

# States where behavioral delay *may* be injected (SPEC §10.4)
_SAFE_FOR_DELAY = {"IDLE", "FILLING_FORM", "PAYMENT"}


class BehaviorStateMachine:
    """Thread-safe FSM tracking the behavioral context of a worker.

    Parameters
    ----------
    initial_state : str
        Must be one of :data:`BEHAVIOR_STATES`.  Defaults to ``"IDLE"``.
    """

    def __init__(self, initial_state: str = "IDLE") -> None:
        if initial_state not in BEHAVIOR_STATES:
            raise ValueError(f"Invalid initial state: {initial_state}")
        self._state = initial_state
        self._lock = threading.Lock()

    def transition(self, new_state: str) -> bool:
        """Attempt to move to *new_state*.

        Returns ``True`` on success, ``False`` if the transition is
        invalid or *new_state* is not recognised.
        """
        if new_state not in BEHAVIOR_STATES:
            return False
        with self._lock:
            allowed = _VALID_BEHAVIOR_TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                return False
            self._state = new_state
            return True

    def get_state(self) -> str:
        """Return the current behavior state."""
        with self._lock:
            return self._state

    def is_critical_context(self) -> bool:
        """Return ``True`` when in VBV or POST_ACTION."""
        with self._lock:
            return self._state in _CRITICAL_CONTEXTS

    def is_safe_for_delay(self) -> bool:
        """Return ``True`` when delay injection is permitted.

        True for IDLE, FILLING_FORM, and PAYMENT — i.e. states that
        are *not* in a CRITICAL_SECTION and represent UI interaction.
        """
        with self._lock:
            return self._state in _SAFE_FOR_DELAY

    def reset(self) -> None:
        """Reset the machine back to IDLE."""
        with self._lock:
            self._state = "IDLE"
