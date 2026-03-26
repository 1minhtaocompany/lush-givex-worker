from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict

ALLOWED_STATES = {"ui_lock", "success", "vbv_3ds", "declined"}


@dataclass(frozen=True)
class State:
    name: str


_states: Dict[str, State] = {}
_states_lock = Lock()


def add_new_state(state_name: str, extra: int = 0) -> bool:
    if state_name not in ALLOWED_STATES:
        allowed = ", ".join(sorted(ALLOWED_STATES))
        raise ValueError(
            f"State '{state_name}' is not allowed. Allowed states: {allowed}."
        )
    with _states_lock:
        if state_name in _states:
            raise ValueError(f"State '{state_name}' already exists.")
        state = State(name=state_name)
        _states[state_name] = state
        return state
