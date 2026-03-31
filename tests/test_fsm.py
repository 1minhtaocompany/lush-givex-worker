import threading
import unittest
from dataclasses import FrozenInstanceError
from queue import Queue

import modules.fsm.main as fsm
from spec.schema import State

ALLOWED_STATES = fsm.ALLOWED_STATES


def first_allowed_state() -> str:
    if not ALLOWED_STATES:
        raise ValueError("ALLOWED_STATES is empty")
    return next(iter(ALLOWED_STATES))


def valid_state_name() -> str:
    return "success" if "success" in ALLOWED_STATES else first_allowed_state()


def invalid_state_name() -> str:
    candidate = "invalid_state"
    counter = 0
    while candidate in ALLOWED_STATES:
        counter += 1
        candidate = f"invalid_state_{counter}"
    return candidate


class AddNewStateTests(unittest.TestCase):
    THREADS_PER_STATE = 2

    def setUp(self):
        self.fsm = fsm
        self.fsm.reset_states()

    def test_add_valid_state(self):
        valid_state = valid_state_name()
        result = self.fsm.add_new_state(valid_state)
        self.assertEqual(State(name=valid_state), result)

    def test_add_all_allowed_states(self):
        self.assertGreater(len(ALLOWED_STATES), 0)
        results = [self.fsm.add_new_state(state_name) for state_name in ALLOWED_STATES]
        expected_states = [State(name=state_name) for state_name in ALLOWED_STATES]
        self.assertCountEqual(results, expected_states)

    def test_add_duplicate_raises(self):
        valid_state = valid_state_name()
        self.fsm.add_new_state(valid_state)
        with self.assertRaises(ValueError):
            self.fsm.add_new_state(valid_state)

    def test_add_invalid_state_raises(self):
        with self.assertRaises(ValueError):
            self.fsm.add_new_state(invalid_state_name())

    def test_state_is_frozen(self):
        valid_state = valid_state_name()
        state = self.fsm.add_new_state(valid_state)
        with self.assertRaises(FrozenInstanceError):
            state.name = "declined"

    def test_thread_safety(self):
        max_items = len(ALLOWED_STATES) * self.THREADS_PER_STATE
        results = Queue(maxsize=max_items)
        errors = Queue(maxsize=max_items)

        def worker(state_name: str):
            try:
                results.put(self.fsm.add_new_state(state_name))
            except Exception as exc:
                errors.put(exc)

        threads = []
        for state_name in ALLOWED_STATES:
            for _ in range(self.THREADS_PER_STATE):
                thread = threading.Thread(target=worker, args=(state_name,))
                threads.append(thread)
                thread.start()

        for thread in threads:
            thread.join()

        result_states = []
        while not results.empty():
            result_states.append(results.get())

        error_list = []
        while not errors.empty():
            error_list.append(errors.get())

        self.assertCountEqual([state.name for state in result_states], ALLOWED_STATES)
        self.assertEqual(len(ALLOWED_STATES), len(result_states))
        invalid_results = [
            state for state in result_states if not isinstance(state, State)
        ]
        self.assertEqual([], invalid_results)
        expected_errors = len(ALLOWED_STATES) * (self.THREADS_PER_STATE - 1)
        self.assertEqual(expected_errors, len(error_list))
        non_value_errors = [
            error for error in error_list if not isinstance(error, ValueError)
        ]
        self.assertEqual([], non_value_errors)


if __name__ == "__main__":
    unittest.main()
