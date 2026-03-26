from dataclasses import dataclass
from typing import Dict


ALLOWED_STATES = {"ui_lock", "success", "vbv_3ds", "declined"}


@dataclass(frozen=True)
class State:
    name: str


class FSM:
    def __init__(self) -> None:
        self._states: Dict[str, State] = {}

    def add_new_state(self, state_name: str) -> State:
        self._validate_state_name(state_name)
        if state_name in self._states:
            raise ValueError(f"State '{state_name}' already exists.")
        state = State(state_name)
        self._states[state_name] = state
        return state

    @staticmethod
    def _validate_state_name(state_name: str) -> None:
        if state_name not in ALLOWED_STATES:
            allowed = ", ".join(sorted(ALLOWED_STATES))
            raise ValueError(
                f"Invalid state_name '{state_name}'. Allowed states: {allowed}."
            )


DEFAULT_FSM = FSM()


def add_new_state(state_name: str) -> State:
    return DEFAULT_FSM.add_new_state(state_name)
