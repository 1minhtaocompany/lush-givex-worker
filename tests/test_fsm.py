import unittest

import modules.fsm.main as fsm_main


class TestAddNewState(unittest.TestCase):
    def setUp(self):
        fsm_main._reset_states_for_test()

    def test_add_new_state_success(self):
        state = fsm_main.add_new_state("ui_lock")
        self.assertEqual(state.name, "ui_lock")

    def test_add_new_state_duplicate(self):
        fsm_main.add_new_state("success")
        with self.assertRaisesRegex(ValueError, "already exists"):
            fsm_main.add_new_state("success")

    def test_add_new_state_invalid(self):
        with self.assertRaisesRegex(ValueError, "Allowed states"):
            fsm_main.add_new_state("pending")

    def test_fsm_add_new_state(self):
        fsm = fsm_main.FSM()
        state = fsm.add_new_state("declined")
        self.assertEqual(state.name, "declined")
        with self.assertRaisesRegex(ValueError, "already exists"):
            fsm.add_new_state("declined")
