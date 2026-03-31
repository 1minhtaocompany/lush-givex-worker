import importlib

import pytest

from modules.fsm import main as fsm_main


@pytest.fixture()
def fsm_module():
    return importlib.reload(fsm_main)


def _get_allowed_states(fsm_module):
    allowed_states = getattr(fsm_module, "ALLOWED_STATES", None)
    if allowed_states is None:
        return None
    if isinstance(allowed_states, str):
        return [allowed_states]
    try:
        iter(allowed_states)
    except TypeError:
        return None
    return allowed_states


def _pick_allowed_state(fsm_module):
    allowed_states = _get_allowed_states(fsm_module)
    if allowed_states:
        return next(iter(allowed_states))
    return "success"


def _pick_disallowed_state(fsm_module, allowed_state):
    candidate = "invalid_state"
    allowed_states = _get_allowed_states(fsm_module)
    if allowed_states and candidate in allowed_states:
        candidate = f"{allowed_state}_invalid"
    if candidate == allowed_state:
        candidate = f"{allowed_state}_invalid"
    return candidate


def test_add_new_state_valid_returns_state(fsm_module):
    state_name = _pick_allowed_state(fsm_module)
    state = fsm_module.add_new_state(state_name)
    assert isinstance(state, fsm_module.State)
    assert state.name == state_name


def test_add_new_state_duplicate_raises_value_error(fsm_module):
    state_name = _pick_allowed_state(fsm_module)
    fsm_module.add_new_state(state_name)
    with pytest.raises(ValueError):
        fsm_module.add_new_state(state_name)


def test_add_new_state_disallowed_state_raises_value_error(fsm_module):
    allowed_state = _pick_allowed_state(fsm_module)
    invalid_state = _pick_disallowed_state(fsm_module, allowed_state)
    with pytest.raises(ValueError):
        fsm_module.add_new_state(invalid_state)
import unittest

from modules.fsm.main import (
    ALLOWED_STATES,
    add_new_state,
    get_current_state,
    reset_states,
    transition_to,
)
from spec.schema import State


class FsmStateTests(unittest.TestCase):
    def setUp(self):
        reset_states()

    def test_get_current_state_initially_none(self):
        self.assertIsNone(get_current_state())

    def test_add_new_state_returns_state(self):
        state = add_new_state(ALLOWED_STATES[0])
        self.assertIsInstance(state, State)
        self.assertEqual(state.name, ALLOWED_STATES[0])

    def test_add_new_state_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            add_new_state("invalid_state")

    def test_add_new_state_non_string_raises(self):
        with self.assertRaises(ValueError):
            add_new_state(None)

    def test_add_new_state_duplicate_raises(self):
        add_new_state(ALLOWED_STATES[1])
        with self.assertRaises(ValueError):
            add_new_state(ALLOWED_STATES[1])

    def test_transition_to_missing_state_raises(self):
        with self.assertRaises(ValueError):
            transition_to(ALLOWED_STATES[2])

    def test_transition_to_invalid_state_name_raises(self):
        with self.assertRaises(ValueError):
            transition_to("invalid_state")

    def test_transition_to_updates_current_state(self):
        state = add_new_state(ALLOWED_STATES[2])
        returned = transition_to(ALLOWED_STATES[2])
        self.assertEqual(returned, state)
        self.assertEqual(get_current_state(), state)

    def test_get_current_state_after_multiple_transitions(self):
        first = add_new_state(ALLOWED_STATES[0])
        second = add_new_state(ALLOWED_STATES[3])
        transition_to(ALLOWED_STATES[0])
        transition_to(ALLOWED_STATES[3])
        self.assertEqual(get_current_state(), second)
        self.assertNotEqual(get_current_state(), first)

    def test_reset_states_clears_current_state(self):
        add_new_state(ALLOWED_STATES[0])
        transition_to(ALLOWED_STATES[0])
        reset_states()
        self.assertIsNone(get_current_state())

    def test_reset_states_removes_registered_states(self):
        add_new_state(ALLOWED_STATES[1])
        reset_states()
        with self.assertRaises(ValueError):
            transition_to(ALLOWED_STATES[1])

    def test_add_all_allowed_states(self):
        states = [add_new_state(name) for name in ALLOWED_STATES]
        self.assertEqual([state.name for state in states], ALLOWED_STATES)

    def test_add_state_after_reset(self):
        add_new_state(ALLOWED_STATES[0])
        reset_states()
        state = add_new_state(ALLOWED_STATES[0])
        self.assertEqual(state.name, ALLOWED_STATES[0])


if __name__ == "__main__":
    unittest.main()