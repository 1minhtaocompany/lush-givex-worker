import importlib

import pytest

from modules.fsm import main as fsm_main


@pytest.fixture()
def fsm_module():
    return importlib.reload(fsm_main)


def test_add_new_state_valid_returns_state(fsm_module):
    state = fsm_module.add_new_state("success")
    assert isinstance(state, fsm_module.State)


def test_add_new_state_duplicate_raises_value_error(fsm_module):
    fsm_module.add_new_state("success")
    with pytest.raises(ValueError):
        fsm_module.add_new_state("success")


def test_add_new_state_disallowed_state_raises_value_error(fsm_module):
    with pytest.raises(ValueError):
        fsm_module.add_new_state("invalid_state")
