import threading

from spec.schema import State

ALLOWED_STATES = {"ui_lock", "success", "vbv_3ds", "declined"}

_states: dict[str, State] = {}
_states_lock = threading.Lock()


def add_new_state(state_name: str) -> State:
    if not isinstance(state_name, str):
        raise ValueError("state_name must be a string")
    if state_name not in ALLOWED_STATES:
        raise ValueError("state_name is not allowed")
    with _states_lock:
        if state_name in _states:
            raise ValueError("state already exists")
        state = State(name=state_name)
        _states[state_name] = state
        return state
