import unittest

from modules.fsm import main as fsm


class AddNewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        fsm._clear_states()

    def test_add_state_success(self) -> None:
        self.assertTrue(fsm.add_new_state("new_state"))

    def test_add_state_duplicate(self) -> None:
        self.assertTrue(fsm.add_new_state("duplicate"))
        self.assertFalse(fsm.add_new_state("duplicate"))

    def test_add_state_invalid_characters(self) -> None:
        self.assertFalse(fsm.add_new_state("invalid-name"))

    def test_add_state_reserved_name_case_insensitive(self) -> None:
        self.assertFalse(fsm.add_new_state("initial"))
        self.assertFalse(fsm.add_new_state("Initial"))
        self.assertFalse(fsm.add_new_state("INITIAL"))


if __name__ == "__main__":
    unittest.main()