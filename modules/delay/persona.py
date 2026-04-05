"""Seed-based persona profile for behavioral delay.

Generates deterministic worker personality attributes from an integer seed.
Each worker receives a fixed profile that persists across the entire cycle.
"""
import random
import threading

_lock = threading.Lock()

# Persona type catalogue (Blueprint §2: demographic classification)
_PERSONA_TYPES = ("fast_typer", "moderate_typer", "slow_typer", "cautious", "impulsive")

# Typing speed range in seconds per character (lower = faster)
_TYPING_SPEED_MIN = 0.04
_TYPING_SPEED_MAX = 0.12

# Typo probability bounds (Blueprint §4)
_TYPO_RATE_MIN = 0.02
_TYPO_RATE_MAX = 0.05

# Hesitation delay bounds in seconds (Blueprint §5)
_HESITATION_MIN_LOWER = 0.5
_HESITATION_MIN_UPPER = 1.5
_HESITATION_MAX_LOWER = 2.0
_HESITATION_MAX_UPPER = 5.0

# Night penalty range (Blueprint §14)
_NIGHT_PENALTY_MIN = 0.15
_NIGHT_PENALTY_MAX = 0.30

# Fatigue threshold bounds in cycles (Blueprint §14)
_FATIGUE_THRESHOLD_MIN = 5
_FATIGUE_THRESHOLD_MAX = 15

# Active hours range (Blueprint §14)
_ACTIVE_HOURS_STARTS = (6, 7, 8, 9, 10)
_ACTIVE_HOURS_ENDS = (20, 21, 22, 23)

# Hard constraint for typing delay per 4-digit group (Blueprint §10)
MAX_TYPING_DELAY = 1.8
MIN_TYPING_DELAY = 0.6


class PersonaProfile:
    """Seed-deterministic persona providing behavioral attributes for a worker.

    Parameters
    ----------
    seed : int
        Integer seed.  Same seed always produces the same profile.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._rnd = random.Random(seed)
        # Lock protects the shared Random instance
        self._rnd_lock = threading.Lock()

        # --- generate attributes (order matters for determinism) ---
        self.persona_type: str = self._rnd.choice(_PERSONA_TYPES)
        self.typing_speed: float = self._rnd.uniform(_TYPING_SPEED_MIN, _TYPING_SPEED_MAX)
        self.typo_rate: float = self._rnd.uniform(_TYPO_RATE_MIN, _TYPO_RATE_MAX)
        self.hesitation_pattern: dict = {
            "min": self._rnd.uniform(_HESITATION_MIN_LOWER, _HESITATION_MIN_UPPER),
            "max": self._rnd.uniform(_HESITATION_MAX_LOWER, _HESITATION_MAX_UPPER),
        }
        self.active_hours: tuple = (
            self._rnd.choice(_ACTIVE_HOURS_STARTS),
            self._rnd.choice(_ACTIVE_HOURS_ENDS),
        )
        self.fatigue_threshold: int = self._rnd.randint(
            _FATIGUE_THRESHOLD_MIN, _FATIGUE_THRESHOLD_MAX
        )
        self.night_penalty_factor: float = self._rnd.uniform(
            _NIGHT_PENALTY_MIN, _NIGHT_PENALTY_MAX
        )

    # --- public API ---

    def get_typing_delay(self, group_index: int) -> float:
        """Return a typing delay in seconds for a 4-digit group.

        The delay is influenced by *group_index* (later groups tend to be
        slightly faster as the user "gets into rhythm") and is clamped to
        [MIN_TYPING_DELAY, MAX_TYPING_DELAY].
        """
        with self._rnd_lock:
            base = self._rnd.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY)
        # Slight speed-up for later groups (rhythm effect)
        factor = max(0.85, 1.0 - group_index * 0.03)
        return max(MIN_TYPING_DELAY, min(base * factor, MAX_TYPING_DELAY))

    def get_hesitation_delay(self) -> float:
        """Return a hesitation delay in seconds, clamped to pattern bounds."""
        low = self.hesitation_pattern["min"]
        high = self.hesitation_pattern["max"]
        with self._rnd_lock:
            return self._rnd.uniform(low, high)

    def get_typo_probability(self) -> float:
        """Return the probability of a typo for this persona."""
        return self.typo_rate

    def to_dict(self) -> dict:
        """Serialise profile to a plain dict (useful for logging / debug)."""
        return {
            "seed": self._seed,
            "persona_type": self.persona_type,
            "typing_speed": self.typing_speed,
            "typo_rate": self.typo_rate,
            "hesitation_pattern": dict(self.hesitation_pattern),
            "active_hours": self.active_hours,
            "fatigue_threshold": self.fatigue_threshold,
            "night_penalty_factor": self.night_penalty_factor,
        }
