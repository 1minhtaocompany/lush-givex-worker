"""Tests for modules.delay.main — behavioral delay injection.

Validates that the delay module:
  - Produces delays within defined bounds
  - Generates burst, long_gap, and normal patterns
  - Varies delay based on runtime state
  - Maintains bounded history
  - Is thread-safe under concurrent use
  - Resets cleanly for testing
"""

import threading
import time
import unittest
from unittest.mock import patch

from modules.delay.main import (
    BURST_DELAY_MAX,
    BURST_DELAY_MIN,
    BURST_PROBABILITY,
    LONG_GAP_DELAY_MAX,
    LONG_GAP_DELAY_MIN,
    LONG_GAP_PROBABILITY,
    MAX_DELAY,
    MIN_DELAY,
    _MAX_HISTORY,
    apply_delay,
    compute_delay,
    get_delay_history,
    get_last_delay,
    get_status,
    reset,
)


class DelayResetMixin:
    """Common setUp/tearDown for delay tests."""

    def setUp(self):
        reset()

    def tearDown(self):
        reset()


# ── Delay bounds ─────────────────────────────────────────────────


class TestComputeDelayBounds(DelayResetMixin, unittest.TestCase):
    """Computed delays must lie within absolute bounds."""

    def test_delay_within_bounds(self):
        for _ in range(200):
            d, _ = compute_delay()
            self.assertGreaterEqual(d, BURST_DELAY_MIN)
            self.assertLessEqual(d, LONG_GAP_DELAY_MAX)

    def test_delay_within_bounds_with_init_state(self):
        for _ in range(100):
            d, _ = compute_delay(runtime_state="INIT")
            self.assertGreaterEqual(d, BURST_DELAY_MIN)
            self.assertLessEqual(d, LONG_GAP_DELAY_MAX)

    def test_delay_within_bounds_with_stopping_state(self):
        for _ in range(100):
            d, _ = compute_delay(runtime_state="STOPPING")
            self.assertGreaterEqual(d, BURST_DELAY_MIN)
            self.assertLessEqual(d, LONG_GAP_DELAY_MAX)


# ── Pattern types ────────────────────────────────────────────────


class TestPatternTypes(DelayResetMixin, unittest.TestCase):
    """Delay patterns must be one of the known types."""

    def test_pattern_names(self):
        patterns = set()
        for _ in range(500):
            _, p = compute_delay()
            patterns.add(p)
        self.assertTrue(patterns.issubset({"burst", "long_gap", "normal"}))

    def test_burst_pattern_values(self):
        """Burst delays must be short."""
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.0  # < BURST_PROBABILITY
            mock_rng.randint.return_value = 0  # no extra burst
            mock_rng.uniform.return_value = (BURST_DELAY_MIN + BURST_DELAY_MAX) / 2
            d, p = compute_delay()
            self.assertEqual(p, "burst")
            self.assertGreaterEqual(d, BURST_DELAY_MIN)
            self.assertLessEqual(d, BURST_DELAY_MAX)

    def test_long_gap_pattern_values(self):
        """Long-gap delays must be long."""
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = BURST_PROBABILITY + 0.01
            mock_rng.uniform.return_value = (LONG_GAP_DELAY_MIN + LONG_GAP_DELAY_MAX) / 2
            d, p = compute_delay()
            self.assertEqual(p, "long_gap")
            self.assertGreaterEqual(d, LONG_GAP_DELAY_MIN)
            self.assertLessEqual(d, LONG_GAP_DELAY_MAX)

    def test_normal_pattern_values(self):
        """Normal delays fall within the normal range."""
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.99  # normal branch
            mock_rng.uniform.return_value = (MIN_DELAY + MAX_DELAY) / 2
            d, p = compute_delay()
            self.assertEqual(p, "normal")
            self.assertGreaterEqual(d, BURST_DELAY_MIN)
            self.assertLessEqual(d, LONG_GAP_DELAY_MAX)


# ── Burst sequence ───────────────────────────────────────────────


class TestBurstSequence(DelayResetMixin, unittest.TestCase):
    """Starting a burst should produce multiple consecutive burst entries."""

    def test_burst_sequence(self):
        with patch("modules.delay.main.random") as mock_rng:
            # First call triggers burst with 3 remaining
            mock_rng.random.return_value = 0.0
            mock_rng.randint.return_value = 3
            mock_rng.uniform.return_value = BURST_DELAY_MIN
            d1, p1 = compute_delay()
            self.assertEqual(p1, "burst")

            # Next 3 should also be burst (burst_remaining > 0)
            for _ in range(3):
                d, p = compute_delay()
                self.assertEqual(p, "burst")

            status = get_status()
            self.assertEqual(status["burst_remaining"], 0)


# ── Runtime state variation ──────────────────────────────────────


class TestRuntimeStateVariation(DelayResetMixin, unittest.TestCase):
    """Runtime state modifies computed delay."""

    def test_stopping_reduces_delay(self):
        """STOPPING state should halve the base delay."""
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.uniform.return_value = 4.0
            d_normal, _ = compute_delay(runtime_state="RUNNING")
        reset()
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.uniform.return_value = 4.0
            d_stopping, _ = compute_delay(runtime_state="STOPPING")
        self.assertLess(d_stopping, d_normal)

    def test_init_increases_delay(self):
        """INIT state should increase the base delay."""
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.uniform.return_value = 2.0
            d_running, _ = compute_delay(runtime_state="RUNNING")
        reset()
        with patch("modules.delay.main.random") as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.uniform.return_value = 2.0
            d_init, _ = compute_delay(runtime_state="INIT")
        self.assertGreater(d_init, d_running)

    def test_none_state_accepted(self):
        d, p = compute_delay(runtime_state=None)
        self.assertGreaterEqual(d, BURST_DELAY_MIN)


# ── History ──────────────────────────────────────────────────────


class TestDelayHistory(DelayResetMixin, unittest.TestCase):
    """Delay history must be recorded and bounded."""

    def test_history_records(self):
        compute_delay()
        h = get_delay_history()
        self.assertEqual(len(h), 1)
        self.assertIn("delay", h[0])
        self.assertIn("pattern", h[0])
        self.assertIn("time", h[0])
        self.assertIn("call_count", h[0])

    def test_history_bounded(self):
        for _ in range(_MAX_HISTORY + 20):
            compute_delay()
        h = get_delay_history()
        self.assertLessEqual(len(h), _MAX_HISTORY)

    def test_history_returns_copy(self):
        compute_delay()
        h1 = get_delay_history()
        h2 = get_delay_history()
        self.assertEqual(h1, h2)
        self.assertIsNot(h1, h2)


# ── Status & last_delay ─────────────────────────────────────────


class TestStatusAndLastDelay(DelayResetMixin, unittest.TestCase):

    def test_initial_status(self):
        s = get_status()
        self.assertEqual(s["call_count"], 0)
        self.assertEqual(s["last_delay"], 0.0)
        self.assertEqual(s["burst_remaining"], 0)
        self.assertEqual(s["history_size"], 0)

    def test_status_after_compute(self):
        compute_delay()
        s = get_status()
        self.assertEqual(s["call_count"], 1)
        self.assertGreater(s["last_delay"], 0)
        self.assertEqual(s["history_size"], 1)

    def test_get_last_delay(self):
        self.assertEqual(get_last_delay(), 0.0)
        compute_delay()
        self.assertGreater(get_last_delay(), 0)


# ── Reset ────────────────────────────────────────────────────────


class TestReset(DelayResetMixin, unittest.TestCase):

    def test_reset_clears_state(self):
        for _ in range(10):
            compute_delay()
        reset()
        s = get_status()
        self.assertEqual(s["call_count"], 0)
        self.assertEqual(s["last_delay"], 0.0)
        self.assertEqual(s["burst_remaining"], 0)
        self.assertEqual(s["history_size"], 0)
        self.assertEqual(get_delay_history(), [])


# ── apply_delay ──────────────────────────────────────────────────


class TestApplyDelay(DelayResetMixin, unittest.TestCase):
    """apply_delay must sleep for the computed duration."""

    def test_apply_delay_sleeps(self):
        with patch("modules.delay.main.time.sleep") as mock_sleep:
            d, p = apply_delay()
            mock_sleep.assert_called_once_with(d)

    def test_apply_delay_returns_tuple(self):
        with patch("modules.delay.main.time.sleep"):
            result = apply_delay(runtime_state="RUNNING")
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)


# ── Thread safety ────────────────────────────────────────────────


class TestThreadSafety(DelayResetMixin, unittest.TestCase):

    def test_concurrent_compute(self):
        """Multiple threads calling compute_delay must not raise."""
        errors = []

        def _call():
            try:
                for _ in range(50):
                    compute_delay()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_call) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        s = get_status()
        self.assertEqual(s["call_count"], 400)

    def test_concurrent_history_bounded(self):
        """History stays bounded under concurrent writes."""
        def _call():
            for _ in range(30):
                compute_delay()

        threads = [threading.Thread(target=_call) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        h = get_delay_history()
        self.assertLessEqual(len(h), _MAX_HISTORY)


# ── Non-uniformity ───────────────────────────────────────────────


class TestNonUniformity(DelayResetMixin, unittest.TestCase):
    """Delays must not be uniform — different values expected."""

    def test_delays_are_varied(self):
        delays = set()
        for _ in range(50):
            d, _ = compute_delay()
            delays.add(round(d, 4))
        self.assertGreater(len(delays), 1, "All delays were identical")


if __name__ == "__main__":
    unittest.main()
