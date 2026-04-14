"""Tests for modules/cdp/keyboard.py — per-character typing, typo simulation.

Covers:
- adjacent_char: determinism, fallback for unknown chars, neighbor validity.
- type_value: per-character dispatch, typo injection, correction cycle,
  burst delays, determinism under fixed seed, strict-mode warning path.
"""

import random
import unittest
from unittest.mock import MagicMock, call, patch

from modules.cdp.keyboard import adjacent_char, type_value, _ADJACENT, _BACKSPACE


def _rnd(seed: int = 42) -> random.Random:
    return random.Random(seed)


class TestAdjacentChar(unittest.TestCase):
    """adjacent_char returns a valid neighbor or the original char."""

    def test_known_char_returns_neighbor(self):
        neighbors = _ADJACENT['a']
        result = adjacent_char('a', _rnd())
        self.assertIn(result, neighbors)

    def test_unknown_char_returns_self(self):
        self.assertEqual(adjacent_char('@', _rnd()), '@')

    def test_digit_returns_neighbor(self):
        neighbors = _ADJACENT['5']
        result = adjacent_char('5', _rnd())
        self.assertIn(result, neighbors)

    def test_case_insensitive_lookup(self):
        # Uppercase 'A' should find neighbors via lowercase key.
        neighbors = _ADJACENT['a']
        result = adjacent_char('A', _rnd())
        self.assertIn(result, neighbors)

    def test_deterministic_under_fixed_seed(self):
        r1 = adjacent_char('s', _rnd(0))
        r2 = adjacent_char('s', _rnd(0))
        self.assertEqual(r1, r2)

    def test_different_seeds_may_differ(self):
        results = {adjacent_char('f', _rnd(seed)) for seed in range(20)}
        self.assertGreater(len(results), 1)


class TestTypeValueBasic(unittest.TestCase):
    """type_value dispatches each character individually."""

    def test_chars_dispatched_per_character(self):
        el = MagicMock()
        value = "hello"
        with patch("time.sleep"):
            result = type_value(el, value, _rnd(), typo_rate=0.0)
        self.assertEqual(result["typed_chars"], len(value))
        calls = [c.args[0] for c in el.send_keys.call_args_list]
        for char in value:
            self.assertIn(char, calls)

    def test_returns_mode_per_char(self):
        el = MagicMock()
        with patch("time.sleep"):
            result = type_value(el, "abc", _rnd(), typo_rate=0.0)
        self.assertEqual(result["mode"], "per_char")

    def test_element_cleared_before_typing(self):
        el = MagicMock()
        with patch("time.sleep"):
            type_value(el, "x", _rnd(), typo_rate=0.0)
        el.clear.assert_called_once()

    def test_no_typos_when_typo_rate_zero(self):
        el = MagicMock()
        with patch("time.sleep"):
            result = type_value(el, "test123", _rnd(), typo_rate=0.0)
        self.assertEqual(result["typos_injected"], 0)
        self.assertEqual(result["corrections_made"], 0)

    def test_delays_used_when_provided(self):
        el = MagicMock()
        delays = [0.1, 0.2, 0.3]
        slept = []
        with patch("time.sleep", side_effect=slept.append):
            type_value(el, "abc", _rnd(), typo_rate=0.0, delays=delays)
        self.assertIn(0.1, slept)
        self.assertIn(0.2, slept)
        self.assertIn(0.3, slept)

    def test_fallback_delay_when_delays_none(self):
        el = MagicMock()
        slept = []
        with patch("time.sleep", side_effect=slept.append):
            type_value(el, "ab", _rnd(), typo_rate=0.0, delays=None)
        # Each char gets 0.05 fallback delay.
        self.assertTrue(all(d == 0.05 for d in slept))


class TestTypeValueTypo(unittest.TestCase):
    """type_value injects typo + correction cycle when typo triggers."""

    def _run_with_high_typo_rate(self, value="a"):
        """Force a typo by using rate=1.0 and a char with known neighbors."""
        el = MagicMock()
        rnd = _rnd(0)
        with patch("time.sleep"):
            result = type_value(el, value, rnd, typo_rate=1.0)
        return el, result

    def test_typo_injected_at_rate_one(self):
        _el, result = self._run_with_high_typo_rate("a")
        self.assertGreater(result["typos_injected"], 0)

    def test_correction_follows_typo(self):
        el, result = self._run_with_high_typo_rate("a")
        self.assertEqual(result["corrections_made"], result["typos_injected"])

    def test_backspace_sent_for_each_correction(self):
        el, result = self._run_with_high_typo_rate("a")
        calls = [c.args[0] for c in el.send_keys.call_args_list]
        backspace_count = calls.count(_BACKSPACE)
        self.assertEqual(backspace_count, result["corrections_made"])

    def test_wrong_char_then_backspace_then_correct_order(self):
        """Verify send_keys call order: wrong → backspace → correct."""
        el = MagicMock()
        # Use seed that reliably produces a neighbor different from 'a'.
        rnd = random.Random(0)
        with patch("time.sleep"):
            type_value(el, "a", rnd, typo_rate=1.0)
        calls = [c.args[0] for c in el.send_keys.call_args_list]
        # Last non-backspace should be 'a' (correct char).
        non_backspace = [c for c in calls if c != _BACKSPACE]
        self.assertEqual(non_backspace[-1], 'a')
        # There should be at least one backspace.
        self.assertIn(_BACKSPACE, calls)

    def test_deterministic_typo_under_fixed_seed(self):
        el1, res1 = self._run_with_high_typo_rate("s")
        el2, res2 = self._run_with_high_typo_rate("s")
        calls1 = [c.args[0] for c in el1.send_keys.call_args_list]
        calls2 = [c.args[0] for c in el2.send_keys.call_args_list]
        self.assertEqual(calls1, calls2)

    def test_different_seeds_may_produce_different_typos(self):
        wrong_chars = set()
        for seed in range(10):
            el = MagicMock()
            with patch("time.sleep"):
                type_value(el, "f", random.Random(seed), typo_rate=1.0)
            calls = [c.args[0] for c in el.send_keys.call_args_list]
            wrong_chars.update(c for c in calls if c not in ('f', _BACKSPACE))
        self.assertGreater(len(wrong_chars), 0)


class TestTypeValueBurstDelays(unittest.TestCase):
    """type_value uses burst-style delays when a delays list is provided."""

    def test_burst_delays_grouped(self):
        el = MagicMock()
        # 4x4 pattern: 4 fast + 1 pause (repeated), 19 total for 16 chars.
        delays = [0.04] * 4 + [0.8] + [0.04] * 4 + [0.8] + [0.04] * 4 + [0.8] + [0.04] * 4
        value = "1234567890123456"
        slept = []
        with patch("time.sleep", side_effect=slept.append):
            type_value(el, value, _rnd(), typo_rate=0.0, delays=delays)
        # The 3 inter-group pauses (0.8 s) should be observable.
        long_delays = [d for d in slept if d >= 0.8]
        self.assertGreaterEqual(len(long_delays), 3)

    def test_short_delays_between_chars(self):
        el = MagicMock()
        delays = [0.04] * 5
        slept = []
        with patch("time.sleep", side_effect=slept.append):
            type_value(el, "abcde", _rnd(), typo_rate=0.0, delays=delays)
        fast = [d for d in slept if d < 0.1]
        self.assertEqual(len(fast), 5)


class TestTypeValueStrictMode(unittest.TestCase):
    """type_value logs warning (not just debug) on failures when strict=True."""

    def test_strict_warns_on_send_keys_failure(self):
        el = MagicMock()
        el.send_keys.side_effect = RuntimeError("driver gone")
        with patch("time.sleep"):
            with self.assertLogs("modules.cdp.keyboard", level="WARNING") as cm:
                type_value(el, "x", _rnd(), strict=True)
        self.assertTrue(any("send_keys failed" in msg for msg in cm.output))

    def test_non_strict_does_not_warn_on_send_keys_failure(self):
        el = MagicMock()
        el.send_keys.side_effect = RuntimeError("driver gone")
        # Should not raise and should not emit WARNING.
        with patch("time.sleep"):
            with self.assertLogs("modules.cdp.keyboard", level="DEBUG"):
                type_value(el, "x", _rnd(), strict=False)


if __name__ == "__main__":
    unittest.main()
