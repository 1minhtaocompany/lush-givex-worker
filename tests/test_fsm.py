import importlib

import pytest

from modules.fsm import main as fsm_main


@pytest.fixture()
def fsm_module():
    return importlib.reload(fsm_main)


def _get_allowed_states(fsm_module):
    allowed_states = getattr(fsm_module, "ALLOWED_STATES", None)
    if allowed_states is None or isinstance(allowed_states, str):
        return None
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
