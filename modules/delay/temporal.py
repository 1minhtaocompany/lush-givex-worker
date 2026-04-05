"""Day / night temporal model for behavioral delay modulation.

Adjusts worker behavior based on time-of-day, applying night penalties,
session fatigue, and micro-variation.  All modifiers remain within the
hard delay constraints defined by the engine layer.
"""
import random
import threading
import time

from modules.delay.persona import PersonaProfile, MAX_TYPING_DELAY
from modules.delay.engine import MAX_HESITATION_DELAY, MAX_STEP_DELAY

# Day/night boundaries (Blueprint §14)
DAY_START = 6
DAY_END = 21

# Night modifier ranges (Blueprint §14)
NIGHT_SPEED_PENALTY_RANGE = (0.15, 0.30)
NIGHT_HESITATION_INCREASE_RANGE = (0.20, 0.40)
NIGHT_TYPO_INCREASE = 0.02

# Micro-variation bounds (Blueprint §14: ±5–10%)
_MICRO_VAR_MIN = 0.90
_MICRO_VAR_MAX = 1.10

# Fatigue increase per cycle beyond threshold (small additive seconds)
_FATIGUE_INCREMENT = 0.05
_FATIGUE_MAX_EXTRA = 1.0


class TemporalModel:
    """Apply time-of-day, fatigue, and micro-variation modifiers.

    Parameters
    ----------
    persona : PersonaProfile
        Worker persona (provides night_penalty_factor, fatigue_threshold,
        and the deterministic ``Random`` instance).
    """

    def __init__(self, persona: PersonaProfile) -> None:
        self._persona = persona
        self._rnd = random.Random(persona._seed + 1)  # separate stream
        self._rnd_lock = threading.Lock()

    # --- public API ---

    @staticmethod
    def get_time_state(utc_offset_hours: int) -> str:
        """Return ``"DAY"`` or ``"NIGHT"`` for the given UTC offset.

        DAY = 06:00–21:59 local, NIGHT = 22:00–05:59 local.
        """
        utc_hour = time.gmtime().tm_hour
        local_hour = (utc_hour + utc_offset_hours) % 24
        if DAY_START <= local_hour <= DAY_END:
            return "DAY"
        return "NIGHT"

    def apply_temporal_modifier(self, base_delay: float, action_type: str,
                                utc_offset_hours: int = 0) -> float:
        """Scale *base_delay* according to day/night state.

        Night-time applies a penalty sourced from the persona's
        ``night_penalty_factor``.  Result is clamped to hard bounds.
        """
        if self.get_time_state(utc_offset_hours) == "NIGHT":
            penalty = self._persona.night_penalty_factor
            modified = base_delay * (1.0 + penalty)
        else:
            modified = base_delay
        return self._clamp(modified, action_type)

    def apply_fatigue(self, base_delay: float, cycle_count: int) -> float:
        """Add fatigue-induced slowdown after ``fatigue_threshold`` cycles.

        The extra delay grows linearly but is capped at
        ``_FATIGUE_MAX_EXTRA``.
        """
        threshold = self._persona.fatigue_threshold
        if cycle_count <= threshold:
            return base_delay
        extra_cycles = cycle_count - threshold
        extra = min(extra_cycles * _FATIGUE_INCREMENT, _FATIGUE_MAX_EXTRA)
        return base_delay + extra

    def apply_micro_variation(self, base_delay: float) -> float:
        """Apply ±5–10 % deterministic noise to *base_delay*."""
        with self._rnd_lock:
            factor = self._rnd.uniform(_MICRO_VAR_MIN, _MICRO_VAR_MAX)
        return base_delay * factor

    def get_current_modifiers(self) -> dict:
        """Return a snapshot of the current temporal parameters."""
        return {
            "night_penalty_factor": self._persona.night_penalty_factor,
            "fatigue_threshold": self._persona.fatigue_threshold,
            "micro_var_range": (_MICRO_VAR_MIN, _MICRO_VAR_MAX),
        }

    # --- internal ---

    @staticmethod
    def _clamp(value: float, action_type: str) -> float:
        """Ensure *value* stays within the hard ceiling for *action_type*."""
        if action_type == "typing":
            return min(value, MAX_TYPING_DELAY)
        if action_type == "thinking":
            return min(value, MAX_HESITATION_DELAY)
        return min(value, MAX_STEP_DELAY)
