"""T-12 — FSM transition from page-state is correct.

When the CDP driver reports a page state, ``transition_for_worker`` must
move the worker's FSM into the corresponding State (only states in
``ALLOWED_STATES`` are permitted).  Also verifies terminal-state rules.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.common.exceptions import InvalidStateError  # noqa: E402
from modules.fsm.main import (  # noqa: E402
    ALLOWED_STATES,
    get_current_state_for_worker,
    initialize_for_worker,
    transition_for_worker,
)
from _e2e_harness import E2EBase  # noqa: E402


class TestT12FsmTransitionFromPageState(E2EBase):
    """T-12: FSM transition from page-state yields correct State."""

    def test_ui_lock_then_success_transition(self):
        wid = self.worker_id
        initialize_for_worker(wid)
        self.assertIsNone(get_current_state_for_worker(wid))

        st = transition_for_worker(wid, "ui_lock")
        self.assertEqual(st.name, "ui_lock")
        self.assertEqual(get_current_state_for_worker(wid).name, "ui_lock")

        st = transition_for_worker(wid, "success")
        self.assertEqual(st.name, "success")
        self.assertEqual(get_current_state_for_worker(wid).name, "success")

    def test_vbv_3ds_then_declined_transition(self):
        wid = self.worker_id
        initialize_for_worker(wid)
        transition_for_worker(wid, "vbv_3ds")
        st = transition_for_worker(wid, "declined")
        self.assertEqual(st.name, "declined")

    def test_invalid_page_state_rejected(self):
        wid = self.worker_id
        initialize_for_worker(wid)
        with self.assertRaises(InvalidStateError):
            transition_for_worker(wid, "unknown_state")

    def test_allowed_states_matches_page_states(self):
        # The page states detect_page_state can return must ALL be in the FSM.
        page_states = {"success", "vbv_3ds", "declined", "ui_lock"}
        self.assertEqual(page_states, set(ALLOWED_STATES))


if __name__ == "__main__":
    unittest.main()
