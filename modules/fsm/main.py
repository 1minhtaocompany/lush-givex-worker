class State:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"State(name='{self.name}')"

    def __eq__(self, other):
        if isinstance(other, State):
            return self.name == other.name
        return NotImplemented

    def __hash__(self):
        return hash(self.name)


class FSM:
    def __init__(self):
        self._states: dict[str, State] = {}

    def add_new_state(self, state_name: str) -> State:
        if state_name in self._states:
            raise ValueError(f"State '{state_name}' already exists")
        state = State(state_name)
        self._states[state_name] = state
        return state
