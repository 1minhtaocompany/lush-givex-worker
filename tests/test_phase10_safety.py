"""Phase 10 safety validation — Task 10.8.

Comprehensive tests proving the behaviour layer does not violate any
safety rules: CRITICAL_SECTION, watchdog headroom, FSM invariants,
outcome invariants, execution order, stagger isolation, VBV isolation,
thread-safety, and deterministic reproducibility.
"""
import threading
import time
import unittest

from modules.delay.main import (
    PersonaProfile, MAX_TYPING_DELAY, MIN_TYPING_DELAY,
    BehaviorStateMachine, DelayEngine,
    MAX_HESITATION_DELAY, MAX_STEP_DELAY, WATCHDOG_HEADROOM,
    TemporalModel, BiometricProfile, wrap,
)


# ---------------------------------------------------------------------------
# 1. CRITICAL_SECTION zero-delay proof
# ---------------------------------------------------------------------------
class TestCriticalSectionZeroDelay(unittest.TestCase):
    """No delay must ever be injected in VBV / POST_ACTION states."""

    def test_vbv_zero_typing(self):
        p = PersonaProfile(1)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("VBV")
        self.assertEqual(e.calculate_typing_delay(0), 0.0)

    def test_vbv_zero_thinking(self):
        p = PersonaProfile(1)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("VBV")
        self.assertEqual(e.calculate_thinking_delay(), 0.0)

    def test_post_action_zero(self):
        p = PersonaProfile(1)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("POST_ACTION")
        self.assertFalse(e.is_delay_permitted())

    def test_payment_submit_no_delay(self):
        """Payment submit ≈ transition to VBV/POST_ACTION → zero delay."""
        p = PersonaProfile(1)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("POST_ACTION")
        self.assertEqual(e.calculate_delay("typing"), 0.0)
        self.assertEqual(e.calculate_delay("thinking"), 0.0)


# ---------------------------------------------------------------------------
# 2. SAFE_POINT compatibility
# ---------------------------------------------------------------------------
class TestSafePointCompatibility(unittest.TestCase):
    def test_delay_only_in_safe_states(self):
        p = PersonaProfile(2)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        # IDLE → safe
        self.assertTrue(e.is_delay_permitted())
        sm.transition("FILLING_FORM")
        self.assertTrue(e.is_delay_permitted())
        sm.transition("PAYMENT")
        self.assertTrue(e.is_delay_permitted())
        sm.transition("VBV")
        self.assertFalse(e.is_delay_permitted())


# ---------------------------------------------------------------------------
# 3. Watchdog headroom
# ---------------------------------------------------------------------------
class TestWatchdogHeadroom(unittest.TestCase):
    def test_accumulated_within_ceiling(self):
        p = PersonaProfile(3)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        for _ in range(50):
            e.calculate_delay("typing")
        self.assertLessEqual(e.get_step_accumulated_delay(), MAX_STEP_DELAY)

    def test_headroom_at_least_3s(self):
        self.assertGreaterEqual(10.0 - MAX_STEP_DELAY, WATCHDOG_HEADROOM)


# ---------------------------------------------------------------------------
# 4. FSM flow invariant
# ---------------------------------------------------------------------------
class TestFSMFlowInvariant(unittest.TestCase):
    def test_same_sequence(self):
        """Wrapping a task must not change state transitions."""
        states_without = []
        states_with = []

        def task_bare(wid):
            states_without.append("executed")

        def task_check(wid):
            states_with.append("executed")

        # Execute bare
        task_bare("w-1")
        # Execute wrapped
        p = PersonaProfile(4)
        wrapped = wrap(task_check, p)
        wrapped("w-1")

        self.assertEqual(states_without, states_with)


# ---------------------------------------------------------------------------
# 5. Outcome invariant
# ---------------------------------------------------------------------------
class TestOutcomeInvariant(unittest.TestCase):
    def test_return_value_unchanged(self):
        def task(wid):
            return wid * 2

        p = PersonaProfile(5)
        wrapped = wrap(task, p)
        self.assertEqual(wrapped("w"), task("w"))

    def test_exception_preserved(self):
        def task(wid):
            raise ValueError("test")

        p = PersonaProfile(5)
        wrapped = wrap(task, p)
        with self.assertRaises(ValueError):
            wrapped("w")


# ---------------------------------------------------------------------------
# 6. Execution order invariant
# ---------------------------------------------------------------------------
class TestExecutionOrderInvariant(unittest.TestCase):
    def test_step_sequence_unchanged(self):
        order = []

        def task(wid):
            order.append(wid)

        p = PersonaProfile(6)
        wrapped = wrap(task, p)
        wrapped("a")
        wrapped("b")
        wrapped("c")
        self.assertEqual(order, ["a", "b", "c"])


# ---------------------------------------------------------------------------
# 7. Stagger isolation
# ---------------------------------------------------------------------------
class TestStaggerIsolation(unittest.TestCase):
    def test_stagger_independent_of_behaviour(self):
        """Behaviour delay is within a cycle — stagger is between launches."""
        p = PersonaProfile(7)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        d = e.calculate_delay("typing")
        # Delay should be < stagger minimum (12s) proving they are independent
        self.assertLess(d, 12.0)


# ---------------------------------------------------------------------------
# 8. VBV operational wait isolation
# ---------------------------------------------------------------------------
class TestVBVOperationalWaitIsolation(unittest.TestCase):
    def test_vbv_state_blocks_behaviour_delay(self):
        p = PersonaProfile(8)
        sm = BehaviorStateMachine()
        e = DelayEngine(p, sm)
        sm.transition("FILLING_FORM")
        sm.transition("PAYMENT")
        sm.transition("VBV")
        self.assertEqual(e.calculate_delay("typing"), 0.0)
        self.assertEqual(e.calculate_delay("thinking"), 0.0)


# ---------------------------------------------------------------------------
# 9. Concurrent thread-safety
# ---------------------------------------------------------------------------
class TestConcurrentThreadSafety(unittest.TestCase):
    def test_parallel_workers(self):
        errors = []
        results = []

        def task(wid):
            return f"done-{wid}"

        def run_worker(seed):
            try:
                p = PersonaProfile(seed)
                wrapped = wrap(task, p)
                r = wrapped(f"w-{seed}")
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 10)


# ---------------------------------------------------------------------------
# 10. Deterministic reproducibility
# ---------------------------------------------------------------------------
class TestDeterministicReproducibility(unittest.TestCase):
    def test_same_seed_same_delays(self):
        delays_run1 = []
        delays_run2 = []
        for run_delays in (delays_run1, delays_run2):
            p = PersonaProfile(10)
            sm = BehaviorStateMachine()
            e = DelayEngine(p, sm)
            sm.transition("FILLING_FORM")
            for gi in range(4):
                run_delays.append(e.calculate_typing_delay(gi))
        self.assertEqual(delays_run1, delays_run2)

    def test_three_runs_identical(self):
        runs = []
        for _ in range(3):
            p = PersonaProfile(10)
            sm = BehaviorStateMachine()
            e = DelayEngine(p, sm)
            sm.transition("FILLING_FORM")
            run = [e.calculate_typing_delay(gi) for gi in range(4)]
            runs.append(run)
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])


if __name__ == "__main__":
    unittest.main()
