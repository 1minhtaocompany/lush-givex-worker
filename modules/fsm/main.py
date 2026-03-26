from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set

_ALLOWED_STATES: Set[str] = {
    "ui_lock",
    "success",
    "vbv_3ds",
    "declined",
}


@dataclass(frozen=True)
class State:
    name: str


_STATE_REGISTRY: Dict[str, State] = {}


def add_new_state(state_name: str) -> State:
    if not isinstance(state_name, str):
        raise TypeError("state_name must be a string")
    if state_name not in _ALLOWED_STATES:
        raise ValueError("state_name is not allowed by FSM rules")
    if state_name in _STATE_REGISTRY:
        raise ValueError("state_name already exists")
    state = State(name=state_name)
    _STATE_REGISTRY[state_name] = state
    return state
