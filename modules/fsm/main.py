from threading import Lock
from typing import Dict, Optional

from spec.schema import State

ALLOWED_STATES = ["ui_lock", "success", "vbw_36s", "declined"]

_states: Dict[str, State] = {}
_current_state: Optional[State] = None
_states_lock = Lock()


def add_new_state(state_name: str) -> State:
    if not isinstance(state_name, str):
        raise ValueError("state_name must be a string")
    if state_name not in ALLOWED_STATES:
        raise ValueError(
            f'state_name "{state_name}" is not allowed. Allowed states: {ALLOWED_STATES}'
        )
    with _states_lock:
        if state_name in _states:
            raise ValueError("state_name already exists")
        state = State(name=state_name)
        _states[state_name] = state
        return state


def reset_states() -> None:
    global _current_state
    with _states_lock:
        _states.clear()
        _current_state = None


def get_current_state() -> Optional[State]:
    with _states_lock:
        return _current_state


def transition_to(state_name: str) -> State:
    global _current_state
    if not isinstance(state_name, str):
        raise ValueError("state_name must be a string")
    with _states_lock:
        if state_name not in _states:
            raise ValueError(f'state_name "{state_name}" does not exist')
        _current_state = _states[state_name]
        return _current_state
