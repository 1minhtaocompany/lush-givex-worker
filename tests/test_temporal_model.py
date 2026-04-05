"""Tests for TemporalModel — Task 10.4."""
import time
import unittest

from modules.delay.main import (
    PersonaProfile, MAX_TYPING_DELAY, MAX_HESITATION_DELAY, MAX_STEP_DELAY,
    TemporalModel, DAY_START, DAY_END,
    NIGHT_SPEED_PENALTY_RANGE, NIGHT_HESITATION_INCREASE_RANGE, NIGHT_TYPO_INCREASE,
)


class _TemporalSetup(unittest.TestCase):
    def setUp(self):
        self.persona = PersonaProfile(42)
        self.tm = TemporalModel(self.persona)


class TestTimeState(_TemporalSetup):
    def test_day_range(self):
        for offset in range(-12, 13):
            state = self.tm.get_time_state(offset)
            self.assertIn(state, ("DAY", "NIGHT"))

    def test_known_day(self):
        # Force a known local hour by calculating offset
        utc_hour = time.gmtime().tm_hour
        # Want local_hour=12 (clearly DAY)
        offset = (12 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        self.assertEqual(self.tm.get_time_state(offset), "DAY")

    def test_known_night(self):
        utc_hour = time.gmtime().tm_hour
        # Want local_hour=3 (clearly NIGHT)
        offset = (3 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        self.assertEqual(self.tm.get_time_state(offset), "NIGHT")


class TestTemporalModifier(_TemporalSetup):
    def test_day_no_penalty(self):
        utc_hour = time.gmtime().tm_hour
        offset = (12 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        base = 1.0
        modified = self.tm.apply_temporal_modifier(base, "typing", offset)
        self.assertEqual(modified, base)

    def test_night_penalty_applied(self):
        utc_hour = time.gmtime().tm_hour
        offset = (3 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        base = 1.0
        modified = self.tm.apply_temporal_modifier(base, "typing", offset)
        self.assertGreater(modified, base)

    def test_typing_clamped(self):
        utc_hour = time.gmtime().tm_hour
        offset = (3 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        modified = self.tm.apply_temporal_modifier(MAX_TYPING_DELAY, "typing", offset)
        self.assertLessEqual(modified, MAX_TYPING_DELAY)

    def test_thinking_clamped(self):
        utc_hour = time.gmtime().tm_hour
        offset = (3 - utc_hour) % 24
        if offset > 12:
            offset -= 24
        modified = self.tm.apply_temporal_modifier(MAX_HESITATION_DELAY, "thinking", offset)
        self.assertLessEqual(modified, MAX_HESITATION_DELAY)


class TestFatigue(_TemporalSetup):
    def test_no_fatigue_below_threshold(self):
        base = 1.0
        result = self.tm.apply_fatigue(base, 0)
        self.assertEqual(result, base)

    def test_fatigue_above_threshold(self):
        base = 1.0
        # Use a high cycle count to trigger fatigue
        result = self.tm.apply_fatigue(base, self.persona.fatigue_threshold + 10)
        self.assertGreater(result, base)

    def test_fatigue_capped(self):
        base = 1.0
        result = self.tm.apply_fatigue(base, self.persona.fatigue_threshold + 1000)
        # Extra should be at most 1.0
        self.assertLessEqual(result - base, 1.0 + 1e-9)


class TestMicroVariation(_TemporalSetup):
    def test_variation_bounds(self):
        base = 1.0
        for _ in range(100):
            v = self.tm.apply_micro_variation(base)
            self.assertGreaterEqual(v, 0.8)  # generous lower bound
            self.assertLessEqual(v, 1.2)     # generous upper bound

    def test_deterministic(self):
        tm2 = TemporalModel(PersonaProfile(42))
        a = self.tm.apply_micro_variation(1.0)
        b = tm2.apply_micro_variation(1.0)
        self.assertEqual(a, b)


class TestGetCurrentModifiers(_TemporalSetup):
    def test_keys(self):
        mods = self.tm.get_current_modifiers()
        self.assertIn("night_penalty_factor", mods)
        self.assertIn("fatigue_threshold", mods)
        self.assertIn("micro_var_range", mods)


if __name__ == "__main__":
    unittest.main()
