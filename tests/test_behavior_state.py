"""Tests for BehaviorStateMachine — Task 10.2."""
import threading
import unittest

from modules.delay.state import (
    BehaviorStateMachine,
    BEHAVIOR_STATES,
    _VALID_BEHAVIOR_TRANSITIONS,
)


class TestInitialState(unittest.TestCase):
    def test_default_idle(self):
        sm = BehaviorStateMachine()
        self.assertEqual(sm.get_state(), "IDLE")

    def test_custom_initial(self):
        sm = BehaviorStateMachine("PAYMENT")
        self.assertEqual(sm.get_state(), "PAYMENT")

    def test_invalid_initial_raises(self):
        with self.assertRaises(ValueError):
            BehaviorStateMachine("BOGUS")


class TestTransitions(unittest.TestCase):
    def test_valid_transitions(self):
        sm = BehaviorStateMachine()
        self.assertTrue(sm.transition("FILLING_FORM"))
        self.assertEqual(sm.get_state(), "FILLING_FORM")
        self.assertTrue(sm.transition("PAYMENT"))
        self.assertEqual(sm.get_state(), "PAYMENT")

    def test_invalid_transition_returns_false(self):
        sm = BehaviorStateMachine()
        self.assertFalse(sm.transition("VBV"))  # IDLE → VBV not allowed
        self.assertEqual(sm.get_state(), "IDLE")

    def test_unknown_state_returns_false(self):
        sm = BehaviorStateMachine()
        self.assertFalse(sm.transition("UNKNOWN"))

    def test_all_declared_transitions_work(self):
        for src, targets in _VALID_BEHAVIOR_TRANSITIONS.items():
            for tgt in targets:
                sm = BehaviorStateMachine(src)
                self.assertTrue(sm.transition(tgt),
                                f"{src} → {tgt} should be valid")


class TestCriticalContext(unittest.TestCase):
    def test_vbv_is_critical(self):
        sm = BehaviorStateMachine()
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("VBV")
        self.assertTrue(sm.is_critical_context())

    def test_post_action_is_critical(self):
        sm = BehaviorStateMachine()
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("POST_ACTION")
        self.assertTrue(sm.is_critical_context())

    def test_idle_not_critical(self):
        sm = BehaviorStateMachine()
        self.assertFalse(sm.is_critical_context())

    def test_filling_form_not_critical(self):
        sm = BehaviorStateMachine("FILLING_FORM")
        self.assertFalse(sm.is_critical_context())


class TestSafeForDelay(unittest.TestCase):
    def test_idle_safe(self):
        sm = BehaviorStateMachine()
        self.assertTrue(sm.is_safe_for_delay())

    def test_filling_form_safe(self):
        sm = BehaviorStateMachine("FILLING_FORM")
        self.assertTrue(sm.is_safe_for_delay())

    def test_payment_safe(self):
        sm = BehaviorStateMachine("PAYMENT")
        self.assertTrue(sm.is_safe_for_delay())

    def test_vbv_not_safe(self):
        sm = BehaviorStateMachine()
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("VBV")
        self.assertFalse(sm.is_safe_for_delay())

    def test_post_action_not_safe(self):
        sm = BehaviorStateMachine()
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("POST_ACTION")
        self.assertFalse(sm.is_safe_for_delay())


class TestReset(unittest.TestCase):
    def test_reset_returns_to_idle(self):
        sm = BehaviorStateMachine()
        sm.transition("FILLING_FORM")
        sm.reset()
        self.assertEqual(sm.get_state(), "IDLE")


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_transitions(self):
        sm = BehaviorStateMachine()
        errors = []

        def worker():
            try:
                for _ in range(200):
                    sm.transition("FILLING_FORM")
                    sm.transition("PAYMENT")
                    sm.reset()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertIn(sm.get_state(), BEHAVIOR_STATES)


if __name__ == "__main__":
    unittest.main()
