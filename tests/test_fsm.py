import importlib
import unittest

import modules.fsm.main as fsm_main


def reload_fsm_module():
    return importlib.reload(fsm_main)


class TestAddNewState(unittest.TestCase):
    def test_add_new_state_success(self):
        fsm = reload_fsm_module()
        state = fsm.add_new_state("ui_lock")
        self.assertEqual(state.name, "ui_lock")

    def test_add_new_state_duplicate(self):
        fsm = reload_fsm_module()
        fsm.add_new_state("success")
        with self.assertRaisesRegex(ValueError, "already exists"):
            fsm.add_new_state("success")

    def test_add_new_state_invalid(self):
        fsm = reload_fsm_module()
        with self.assertRaisesRegex(ValueError, "Allowed states"):
            fsm.add_new_state("pending")
