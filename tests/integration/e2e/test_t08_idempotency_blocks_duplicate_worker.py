"""T-08 — Two concurrent workers on same task_id: idempotency blocks worker #2.

Worker A calls ``is_duplicate(task_id)`` first and proceeds.  Worker B,
arriving later with the same task_id, must see ``is_duplicate → True`` and
exit immediately with ``("complete", None, None)`` — i.e. a no-op "already
handled" result — without invoking ``run_payment_step`` at all.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modules.cdp.main as _cdp_main  # noqa: E402
from integration.orchestrator import run_cycle  # noqa: E402
from _e2e_harness import (  # noqa: E402
    E2EBase,
    _StubGivexDriver,
    make_mock_billing,
    make_task,
)


class TestT08IdempotencyBlocksSecondWorker(E2EBase):
    """T-08: concurrent workers w/ same task_id — idempotency blocks #2."""

    def test_second_worker_blocked_by_idempotency(self):
        task = make_task(task_id="t08-concurrent-001")

        # Worker A: first call, not a duplicate.  Worker B: duplicate.
        store = MagicMock()
        store.is_duplicate.side_effect = [False, True]

        # Worker A — runs normally, completes successfully.
        stub_a = _StubGivexDriver("worker-A", final_state="success", dom_total="50.00")
        _cdp_main.register_driver("worker-A", stub_a)
        try:
            with patch("integration.orchestrator.billing", make_mock_billing()), \
                 patch("integration.orchestrator._get_idempotency_store",
                       return_value=store), \
                 patch("integration.orchestrator._notify_success"):
                action_a, _state_a, _total_a = run_cycle(task, worker_id="worker-A")
        finally:
            _cdp_main.unregister_driver("worker-A")

        self.assertEqual(action_a, "complete")

        # Worker B — blocked immediately; no driver needed because
        # run_payment_step must NOT be reached.
        with patch("integration.orchestrator.billing", make_mock_billing()), \
             patch("integration.orchestrator._get_idempotency_store",
                   return_value=store), \
             patch("integration.orchestrator.run_payment_step") as mock_run_step:
            action_b, state_b, total_b = run_cycle(task, worker_id="worker-B")

        self.assertEqual(action_b, "complete")
        self.assertIsNone(state_b)
        self.assertIsNone(total_b)
        mock_run_step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
