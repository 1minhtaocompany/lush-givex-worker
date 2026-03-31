import threading
from functools import lru_cache
from pathlib import Path

from spec.schema import State

SPEC_FSM_PATH = Path(__file__).resolve().parents[2] / "spec" / "fsm.md"


def _load_allowed_states() -> frozenset[str]:
    lines = SPEC_FSM_PATH.read_text(encoding="utf-8").splitlines()
    allowed_states: list[str] = []
    in_section = False
    found_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ALLOWED_STATES"):
            found_section = True
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section and stripped.startswith("- "):
            allowed_states.append(stripped[2:].strip())
    if not allowed_states:
        if not found_section:
            raise ValueError(
                f"ALLOWED_STATES section not found in {SPEC_FSM_PATH}"
            )
        raise ValueError(
            f"No allowed states found in ALLOWED_STATES section of {SPEC_FSM_PATH}"
        )
    return frozenset(allowed_states)


ALLOWED_STATES = _load_allowed_states()


@lru_cache(maxsize=1)
def _allowed_states_str() -> str:
    return ", ".join(sorted(ALLOWED_STATES))

_states: dict[str, State] = {}
_states_lock = threading.Lock()


def add_new_state(state_name: str) -> State:
    if not isinstance(state_name, str):
        raise ValueError("state_name must be a string")
    if state_name not in ALLOWED_STATES:
        raise ValueError(
            f"state_name '{state_name}' is not allowed. Allowed states: {_allowed_states_str()}"
        )
    with _states_lock:
        if state_name in _states:
            raise ValueError(f"state '{state_name}' already exists")
        state = State(name=state_name)
        _states[state_name] = state
        return state
