"""Behavioral anti-detection biometric layer (Layer 2).

Generates realistic inter-keystroke timing, burst patterns, and noise
to prevent behavioral fingerprinting.  Builds *on top of* the base
delay engine — never replaces it.
"""
import math
import random
import threading

from modules.delay.persona import PersonaProfile, MAX_TYPING_DELAY, MIN_TYPING_DELAY

# Inter-keystroke log-normal parameters (Blueprint §12)
_LOGNORMAL_MU = -2.5
_LOGNORMAL_SIGMA = 0.4

# Burst rhythm: fast keys then pause (Blueprint §12, §4 rule 4×4)
_BURST_FAST_MIN = 0.03
_BURST_FAST_MAX = 0.08
_BURST_PAUSE_MIN = 0.6
_BURST_PAUSE_MAX = 1.8

# Gaussian noise ±10 % (Blueprint §12)
_NOISE_SIGMA = 0.10

# Per-keystroke hard ceiling (seconds)
_KEYSTROKE_MAX = 0.3

# Number of digits in a 4×4 card group
_GROUP_SIZE = 4
_TOTAL_GROUPS = 4


class BiometricProfile:
    """Generate biometric keystroke timing for a worker.

    Parameters
    ----------
    persona : PersonaProfile
        Provides seed for deterministic random stream.
    """

    def __init__(self, persona: PersonaProfile) -> None:
        self._persona = persona
        self._rnd = random.Random(persona._seed + 2)  # separate stream
        self._rnd_lock = threading.Lock()

    # --- public API ---

    def generate_keystroke_delay(self, char_index: int) -> float:
        """Return inter-keystroke delay for a single character.

        Uses a log-normal distribution clamped to [0, _KEYSTROKE_MAX].
        """
        with self._rnd_lock:
            raw = self._rnd.lognormvariate(_LOGNORMAL_MU, _LOGNORMAL_SIGMA)
        return max(0.0, min(raw, _KEYSTROKE_MAX))

    def generate_burst_pattern(self, total_chars: int) -> list:
        """Return a list of delays (one per character) with burst rhythm.

        Fast keystrokes interrupted by short pauses every 4 characters.
        """
        delays = []
        for i in range(total_chars):
            if i > 0 and i % _GROUP_SIZE == 0:
                # Pause between groups
                with self._rnd_lock:
                    pause = self._rnd.uniform(_BURST_PAUSE_MIN, _BURST_PAUSE_MAX)
                delays.append(min(pause, MAX_TYPING_DELAY))
            else:
                with self._rnd_lock:
                    fast = self._rnd.uniform(_BURST_FAST_MIN, _BURST_FAST_MAX)
                delays.append(fast)
        return delays

    def generate_4x4_pattern(self) -> list:
        """Return 16 delay values for a 16-digit card number.

        Structure: 4 fast → pause → 4 fast → pause → 4 fast → pause → 4 fast.
        Pause duration is clamped to [MIN_TYPING_DELAY, MAX_TYPING_DELAY].
        """
        delays = []
        for group in range(_TOTAL_GROUPS):
            for digit in range(_GROUP_SIZE):
                with self._rnd_lock:
                    fast = self._rnd.uniform(_BURST_FAST_MIN, _BURST_FAST_MAX)
                delays.append(fast)
            # After each group except the last, insert a pause
            if group < _TOTAL_GROUPS - 1:
                with self._rnd_lock:
                    pause = self._rnd.uniform(_BURST_PAUSE_MIN, _BURST_PAUSE_MAX)
                delays.append(max(MIN_TYPING_DELAY, min(pause, MAX_TYPING_DELAY)))
        return delays

    def apply_noise(self, base_delay: float) -> float:
        """Apply gaussian noise (±10 %) to *base_delay*, clamped ≥ 0."""
        with self._rnd_lock:
            noise = self._rnd.gauss(0, _NOISE_SIGMA * base_delay)
        return max(0.0, base_delay + noise)
