from __future__ import annotations

from dataclasses import dataclass
import re
from threading import Lock
from typing import Dict


@dataclass(frozen=True)
class State:
    name: str


_states: Dict[str, State] = {}
_states_lock = Lock()


_RESERVED_STATE_NAMES = {"initial", "final", "error"}
_STATE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def add_new_state(state_name: str) -> bool:
    if not isinstance(state_name, str) or not state_name:
        return False
    if _STATE_NAME_PATTERN.match(state_name) is None:
        return False
    normalized_name = state_name.lower()
    if normalized_name in _RESERVED_STATE_NAMES:
        return False
    with _states_lock:
        if state_name in _states:
            return False
        _states[state_name] = State(name=state_name)
        return True


def _clear_states() -> None:
    with _states_lock:
        _states.clear()