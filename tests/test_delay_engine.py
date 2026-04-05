"""Tests for DelayEngine — Task 10.3."""
import unittest

from modules.delay.persona import PersonaProfile, MAX_TYPING_DELAY, MIN_TYPING_DELAY
from modules.delay.state import BehaviorStateMachine
from modules.delay.engine import (
    DelayEngine,
    MAX_HESITATION_DELAY,
    MAX_STEP_DELAY,
    WATCHDOG_HEADROOM,
)


class _EngineSetup(unittest.TestCase):
    """Common setup: persona + state machine + engine."""

    def setUp(self):
        self.persona = PersonaProfile(42)
        self.sm = BehaviorStateMachine()
        self.engine = DelayEngine(self.persona, self.sm)


class TestTypingDelay(_EngineSetup):
    def test_within_bounds(self):
        self.sm.transition("FILLING_FORM")
        for gi in range(5):
            d = self.engine.calculate_typing_delay(gi)
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, MAX_TYPING_DELAY)

    def test_zero_in_critical_context(self):
        self.sm.transition("FILLING_FORM")
        self.sm.transition("PAYMENT")
        self.sm.transition("VBV")
        self.assertEqual(self.engine.calculate_typing_delay(0), 0.0)


class TestClickDelay(_EngineSetup):
    def test_click_is_zero(self):
        self.assertEqual(self.engine.calculate_click_delay(), 0.0)


class TestThinkingDelay(_EngineSetup):
    def test_within_bounds(self):
        self.sm.transition("FILLING_FORM")
        d = self.engine.calculate_thinking_delay()
        self.assertGreater(d, 0.0)
        self.assertLessEqual(d, MAX_HESITATION_DELAY)

    def test_zero_in_critical(self):
        self.sm.transition("FILLING_FORM")
        self.sm.transition("PAYMENT")
        self.sm.transition("VBV")
        self.assertEqual(self.engine.calculate_thinking_delay(), 0.0)


class TestDispatcher(_EngineSetup):
    def test_typing_dispatch(self):
        self.sm.transition("FILLING_FORM")
        d = self.engine.calculate_delay("typing")
        self.assertGreater(d, 0.0)

    def test_click_dispatch(self):
        self.assertEqual(self.engine.calculate_delay("click"), 0.0)

    def test_unknown_dispatch(self):
        self.assertEqual(self.engine.calculate_delay("unknown"), 0.0)


class TestAccumulator(_EngineSetup):
    def test_accumulation(self):
        self.sm.transition("FILLING_FORM")
        self.engine.calculate_delay("typing")
        self.assertGreater(self.engine.get_step_accumulated_delay(), 0.0)

    def test_reset_accumulator(self):
        self.sm.transition("FILLING_FORM")
        self.engine.calculate_delay("typing")
        self.engine.reset_step_accumulator()
        self.assertEqual(self.engine.get_step_accumulated_delay(), 0.0)

    def test_accumulator_respects_ceiling(self):
        self.sm.transition("FILLING_FORM")
        total = 0.0
        for _ in range(20):
            d = self.engine.calculate_delay("thinking")
            total += d
        self.assertLessEqual(self.engine.get_step_accumulated_delay(), MAX_STEP_DELAY)


class TestCriticalSectionBypass(_EngineSetup):
    def test_vbv_zero_delay(self):
        self.sm.transition("FILLING_FORM")
        self.sm.transition("PAYMENT")
        self.sm.transition("VBV")
        self.assertFalse(self.engine.is_delay_permitted())
        self.assertEqual(self.engine.calculate_delay("typing"), 0.0)
        self.assertEqual(self.engine.calculate_delay("thinking"), 0.0)

    def test_post_action_zero_delay(self):
        self.sm.transition("FILLING_FORM")
        self.sm.transition("PAYMENT")
        self.sm.transition("POST_ACTION")
        self.assertFalse(self.engine.is_delay_permitted())


class TestDeterminism(_EngineSetup):
    def test_same_seed_same_delays(self):
        p2 = PersonaProfile(42)
        sm2 = BehaviorStateMachine()
        e2 = DelayEngine(p2, sm2)
        self.sm.transition("FILLING_FORM")
        sm2.transition("FILLING_FORM")
        d1 = self.engine.calculate_typing_delay(0)
        d2 = e2.calculate_typing_delay(0)
        self.assertEqual(d1, d2)


class TestWatchdogHeadroom(unittest.TestCase):
    def test_headroom_constant(self):
        self.assertEqual(WATCHDOG_HEADROOM, 3.0)

    def test_max_step_plus_headroom(self):
        self.assertLessEqual(MAX_STEP_DELAY + WATCHDOG_HEADROOM, 10.0)


if __name__ == "__main__":
    unittest.main()
