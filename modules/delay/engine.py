"""Action-aware bounded delay calculator.

Computes behavioural delays based on action type, BehaviorState context,
and PersonaProfile.  All delays are clamped to hard constraints before
being returned.
"""
import threading

from modules.delay.persona import PersonaProfile, MAX_TYPING_DELAY, MIN_TYPING_DELAY
from modules.delay.state import BehaviorStateMachine

# Hard constraints (Blueprint §10, SPEC §10.6)
MAX_HESITATION_DELAY = 5.0
MAX_STEP_DELAY = 7.0
WATCHDOG_HEADROOM = 3.0

# Click delay is spatial-only, no significant time (SPEC §10.6)
_CLICK_DELAY = 0.0

# Thinking delay bounds (Blueprint §5: 3–5 s hover/scroll)
_THINKING_MIN = 3.0
_THINKING_MAX = 5.0

# Recognised action types
_ACTION_TYPES = {"typing", "click", "thinking"}


class DelayEngine:
    """Calculate bounded delays for worker actions.

    Parameters
    ----------
    persona : PersonaProfile
        The worker's persona providing base delay values.
    state_machine : BehaviorStateMachine
        The current behavioural context FSM.
    """

    def __init__(self, persona: PersonaProfile, state_machine: BehaviorStateMachine) -> None:
        self._persona = persona
        self._state_machine = state_machine
        self._step_accumulated: float = 0.0
        self._lock = threading.Lock()

    # --- public API ---

    def calculate_typing_delay(self, group_index: int) -> float:
        """Return typing delay for a 4-digit group, clamped to bounds.

        Returns 0.0 when delay is not permitted.
        """
        if not self.is_delay_permitted():
            return 0.0
        raw = self._persona.get_typing_delay(group_index)
        clamped = max(MIN_TYPING_DELAY, min(raw, MAX_TYPING_DELAY))
        return self._accumulate(clamped)

    def calculate_click_delay(self) -> float:
        """Return click delay (≈0, spatial offset only)."""
        return _CLICK_DELAY

    def calculate_thinking_delay(self) -> float:
        """Return thinking delay (3–5 s), clamped and accumulated.

        Returns 0.0 when delay is not permitted.
        """
        if not self.is_delay_permitted():
            return 0.0
        with self._persona._rnd_lock:
            raw = self._persona._rnd.uniform(_THINKING_MIN, _THINKING_MAX)
        clamped = min(raw, MAX_HESITATION_DELAY)
        return self._accumulate(clamped)

    def calculate_delay(self, action_type: str) -> float:
        """Dispatch to the correct delay calculator by *action_type*.

        Recognised types: ``typing``, ``click``, ``thinking``.
        Unknown types return 0.0.
        """
        if action_type == "typing":
            return self.calculate_typing_delay(0)
        if action_type == "click":
            return self.calculate_click_delay()
        if action_type == "thinking":
            return self.calculate_thinking_delay()
        return 0.0

    def get_step_accumulated_delay(self) -> float:
        """Return the total delay accumulated in the current step."""
        with self._lock:
            return self._step_accumulated

    def reset_step_accumulator(self) -> None:
        """Reset the per-step accumulator (call at step boundaries)."""
        with self._lock:
            self._step_accumulated = 0.0

    def is_delay_permitted(self) -> bool:
        """Return ``True`` only when the behaviour state allows delay.

        Checks that the current BehaviorState is safe *and* that adding
        more delay would not breach the per-step ceiling.
        """
        if not self._state_machine.is_safe_for_delay():
            return False
        with self._lock:
            return self._step_accumulated < MAX_STEP_DELAY
        return False  # pragma: no cover – unreachable defensive guard

    # --- internal ---

    def _accumulate(self, delay: float) -> float:
        """Add *delay* to the step total, clamping so the sum ≤ MAX_STEP_DELAY."""
        with self._lock:
            headroom = MAX_STEP_DELAY - self._step_accumulated
            if headroom <= 0:
                return 0.0
            actual = min(delay, headroom)
            self._step_accumulated += actual
            return actual
