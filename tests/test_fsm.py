import unittest

from modules.fsm.main import (
    add_new_state,
    get_current_state,
    reset_states,
    transition_to,
)
from spec.schema import InvalidStateError, InvalidTransitionError, State


class FsmTests(unittest.TestCase):
    def setUp(self):
        reset_states()

    def test_add_new_state_returns_state(self):
        result = add_new_state("ui_lock")
        self.assertIsInstance(result, State)
        self.assertEqual(result.name, "ui_lock")

    def test_add_new_state_duplicate_raises_value_error(self):
        add_new_state("success")
        with self.assertRaises(ValueError):
            add_new_state("success")

    def test_add_new_state_invalid_state_raises_invalid_state_error(self):
        with self.assertRaises(InvalidStateError):
            add_new_state("not_a_real_state")

    def test_transition_to_valid(self):
        add_new_state("vbv_3ds")
        transition_to("vbv_3ds")
        current = get_current_state()
        self.assertIsNotNone(current)
        self.assertEqual(current.name, "vbv_3ds")

    def test_transition_to_invalid_raises_invalid_transition_error(self):
        with self.assertRaises(InvalidTransitionError):
            transition_to("declined")

    def test_reset_states_clears_all(self):
        add_new_state("ui_lock")
        add_new_state("success")
        transition_to("ui_lock")
        reset_states()
        self.assertIsNone(get_current_state())


if __name__ == "__main__":
    unittest.main()