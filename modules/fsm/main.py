import threading
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Dict, Optional


ALLOWED_STATES = {"ui_lock", "success", "vbv_3ds", "declined"}


@dataclass(frozen=True)
class State:
    name: str


_STATE_REGISTRY: Dict[str, State] = {}
_STATE_LOCK = threading.Lock()


def _add_state(
    state_name: str,
    registry: Dict[str, State],
    lock: Optional[threading.Lock] = None,
) -> State:
    _validate_state_name(state_name)
    context = lock if lock is not None else nullcontext()
    with context:
        if state_name in registry:
            raise ValueError(f"State '{state_name}' already exists.")
        state = State(state_name)
        registry[state_name] = state
        return state


def _validate_state_name(state_name: str) -> None:
    if state_name not in ALLOWED_STATES:
        allowed = ", ".join(sorted(ALLOWED_STATES))
        raise ValueError(
            f"Invalid state_name '{state_name}'. Allowed states: {allowed}."
        )


def add_new_state(state_name: str) -> State:
    return _add_state(state_name, _STATE_REGISTRY, _STATE_LOCK)


def _reset_states_for_test() -> None:
    with _STATE_LOCK:
        _STATE_REGISTRY.clear()


class FSM:
    def __init__(self) -> None:
        self._states: Dict[str, State] = {}
        self._lock = threading.Lock()

    def add_new_state(self, state_name: str) -> State:
        return _add_state(state_name, self._states, self._lock)
