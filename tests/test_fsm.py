"""Tests for ci/check_spec_lock.py helper functions."""
from __future__ import annotations

import os
import unittest

from ci.check_spec_lock import is_spec_change_authorized, is_spec_path, normalize_path


class TestNormalizePath(unittest.TestCase):
    def test_forward_slash(self) -> None:
        self.assertEqual(normalize_path("spec/interface.md"), "spec/interface.md")

    def test_backslash(self) -> None:
        self.assertEqual(normalize_path("spec\\interface.md"), "spec/interface.md")

    def test_dot_slash_prefix(self) -> None:
        self.assertEqual(normalize_path("./spec/interface.md"), "spec/interface.md")

    def test_no_prefix(self) -> None:
        self.assertEqual(normalize_path("modules/fsm/main.py"), "modules/fsm/main.py")


class TestIsSpecPath(unittest.TestCase):
    def test_spec_file(self) -> None:
        self.assertTrue(is_spec_path("spec/interface.md"))

    def test_spec_dir_only(self) -> None:
        self.assertTrue(is_spec_path("spec"))

    def test_spec_nested(self) -> None:
        self.assertTrue(is_spec_path("spec/sub/file.md"))

    def test_non_spec_file(self) -> None:
        self.assertFalse(is_spec_path("modules/fsm/main.py"))

    def test_spec_prefix_not_dir(self) -> None:
        self.assertFalse(is_spec_path("spectrum/data.txt"))

    def test_backslash_spec(self) -> None:
        self.assertTrue(is_spec_path("spec\\interface.md"))

    def test_dot_slash_spec(self) -> None:
        self.assertTrue(is_spec_path("./spec/interface.md"))


class TestIsSpecChangeAuthorized(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = os.environ.get("ALLOW_SPEC_MODIFICATION")

    def tearDown(self) -> None:
        if self._orig is None:
            os.environ.pop("ALLOW_SPEC_MODIFICATION", None)
        else:
            os.environ["ALLOW_SPEC_MODIFICATION"] = self._orig

    def test_not_set(self) -> None:
        os.environ.pop("ALLOW_SPEC_MODIFICATION", None)
        self.assertFalse(is_spec_change_authorized())

    def test_empty(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = ""
        self.assertFalse(is_spec_change_authorized())

    def test_false_string(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = "false"
        self.assertFalse(is_spec_change_authorized())

    def test_true_lowercase(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = "true"
        self.assertTrue(is_spec_change_authorized())

    def test_true_uppercase(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = "TRUE"
        self.assertTrue(is_spec_change_authorized())

    def test_true_with_whitespace(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = "  true  "
        self.assertTrue(is_spec_change_authorized())

    def test_random_string(self) -> None:
        os.environ["ALLOW_SPEC_MODIFICATION"] = "yes"
        self.assertFalse(is_spec_change_authorized())


if __name__ == "__main__":
    unittest.main()
