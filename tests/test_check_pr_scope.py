import unittest
from unittest.mock import patch, MagicMock
import subprocess

from ci.check_pr_scope import (
    _normalize,
    _is_excluded,
    module_from_path,
    get_numstat,
    check,
    main,
    _resolve_change_class,
    _enforce_emergency_governance,
    EXCLUDED_PREFIXES,
    MAX_CHANGED_LINES,
)


class NormalizeTests(unittest.TestCase):
    def test_strip_dot_slash(self):
        self.assertEqual(_normalize("./src/app.py"), "src/app.py")

    def test_backslash(self):
        self.assertEqual(_normalize("ci\\script.py"), "ci/script.py")

    def test_already_normalized(self):
        self.assertEqual(_normalize("modules/fsm/main.py"), "modules/fsm/main.py")


class IsExcludedTests(unittest.TestCase):
    def test_tests_dir(self):
        self.assertTrue(_is_excluded("tests/test_fsm.py"))

    def test_ci_dir(self):
        self.assertTrue(_is_excluded("ci/check_pr_scope.py"))

    def test_modules_not_excluded(self):
        self.assertFalse(_is_excluded("modules/fsm/main.py"))

    def test_spec_not_excluded(self):
        self.assertFalse(_is_excluded("spec/schema.py"))

    def test_root_file(self):
        self.assertFalse(_is_excluded("README.md"))


class ModuleFromPathTests(unittest.TestCase):
    def test_module_path(self):
        self.assertEqual(module_from_path("modules/fsm/main.py"), "fsm")

    def test_non_module_path(self):
        self.assertIsNone(module_from_path("ci/check_pr_scope.py"))

    def test_bare_modules(self):
        self.assertIsNone(module_from_path("modules/"))

    def test_spec(self):
        self.assertIsNone(module_from_path("spec/schema.py"))


class CheckTests(unittest.TestCase):
    """Test the check() function with mocked git output."""

    def _mock_numstat(self, lines: list[str]):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "\n".join(lines) + "\n"
        result.stderr = ""
        return result

    @patch("ci.check_pr_scope.get_numstat")
    def test_pass_under_limit(self, mock_numstat):
        mock_numstat.return_value = [
            (50, 10, "modules/fsm/main.py"),
        ]
        self.assertEqual(check("fake...range"), 0)

    @patch("ci.check_pr_scope.get_numstat")
    def test_fail_over_limit(self, mock_numstat):
        mock_numstat.return_value = [
            (150, 60, "modules/fsm/main.py"),
        ]
        self.assertEqual(check("fake...range"), 1)

    @patch("ci.check_pr_scope.get_numstat")
    def test_excluded_dirs_not_counted(self, mock_numstat):
        mock_numstat.return_value = [
            (50, 10, "modules/fsm/main.py"),
            (300, 100, "tests/test_fsm.py"),
            (200, 50, "ci/check_pr_scope.py"),
        ]
        self.assertEqual(check("fake...range"), 0)

    @patch("ci.check_pr_scope.get_numstat")
    def test_fail_multiple_modules(self, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/auth/main.py"),
        ]
        self.assertEqual(check("fake...range"), 1)

    @patch("ci.check_pr_scope.get_numstat")
    def test_single_module_pass(self, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/fsm/helpers.py"),
        ]
        self.assertEqual(check("fake...range"), 0)

    @patch("ci.check_pr_scope.get_numstat")
    def test_exactly_at_limit(self, mock_numstat):
        mock_numstat.return_value = [
            (100, 100, "modules/fsm/main.py"),
        ]
        self.assertEqual(check("fake...range"), 0)

    @patch("ci.check_pr_scope.get_numstat")
    def test_no_changes(self, mock_numstat):
        mock_numstat.return_value = []
        self.assertEqual(check("fake...range"), 0)

    @patch("ci.check_pr_scope.get_numstat")
    def test_only_excluded_changes(self, mock_numstat):
        mock_numstat.return_value = [
            (500, 200, "ci/check_pr_scope.py"),
            (300, 100, "tests/test_check_pr_scope.py"),
        ]
        self.assertEqual(check("fake...range"), 0)


class ConstantsTests(unittest.TestCase):
    def test_max_lines(self):
        self.assertEqual(MAX_CHANGED_LINES, 200)

    def test_excluded_prefixes(self):
        self.assertIn("tests/", EXCLUDED_PREFIXES)
        self.assertIn("ci/", EXCLUDED_PREFIXES)


class AllowMultiModuleTests(unittest.TestCase):
    """Test the ALLOW_MULTI_MODULE env var bypass (deprecated alias)."""

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "true"})
    def test_bypass_allows_multi_module(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
            (10, 5, "modules/billing/main.py"),
            (10, 5, "modules/cdp/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "true"})
    def test_bypass_still_enforces_line_limit(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (150, 60, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "false"})
    def test_no_bypass_when_false(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 1)


class ResolveChangeClassTests(unittest.TestCase):
    """Test _resolve_change_class() — CHANGE_CLASS + ALLOW_MULTI_MODULE alias."""

    @patch.dict("os.environ", {"CHANGE_CLASS": "spec_sync"}, clear=False)
    def test_change_class_returned_as_is(self):
        self.assertEqual(_resolve_change_class(), "spec_sync")

    @patch.dict("os.environ", {"CHANGE_CLASS": "EMERGENCY_OVERRIDE"}, clear=False)
    def test_change_class_lowercased(self):
        self.assertEqual(_resolve_change_class(), "emergency_override")

    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "true", "CHANGE_CLASS": ""},
                clear=False)
    def test_allow_multi_alias_when_no_change_class(self):
        self.assertEqual(_resolve_change_class(), "spec_sync")

    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "true", "CHANGE_CLASS": "infra_change"},
                clear=False)
    def test_change_class_takes_precedence_over_allow_multi(self):
        # CHANGE_CLASS is already set; ALLOW_MULTI_MODULE does not override it
        self.assertEqual(_resolve_change_class(), "infra_change")

    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "false", "CHANGE_CLASS": ""},
                clear=False)
    def test_allow_multi_false_no_alias(self):
        self.assertEqual(_resolve_change_class(), "")

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_returns_empty(self):
        self.assertEqual(_resolve_change_class(), "")


class EnforceEmergencyGovernanceTests(unittest.TestCase):
    """Test _enforce_emergency_governance() governance validation."""

    @patch.dict("os.environ", {"PR_TITLE": "[emergency] hotfix", "PR_LABELS": ""},
                clear=False)
    def test_title_prefix_passes(self):
        self.assertTrue(_enforce_emergency_governance())

    @patch.dict("os.environ", {"PR_TITLE": "[EMERGENCY] hotfix", "PR_LABELS": ""},
                clear=False)
    def test_title_prefix_case_insensitive(self):
        self.assertTrue(_enforce_emergency_governance())

    @patch.dict("os.environ", {"PR_TITLE": "normal PR", "PR_LABELS": "emergency"},
                clear=False)
    def test_label_passes(self):
        self.assertTrue(_enforce_emergency_governance())

    @patch.dict("os.environ", {"PR_TITLE": "normal PR", "PR_LABELS": "bug,emergency,ci"},
                clear=False)
    def test_label_among_multiple_passes(self):
        self.assertTrue(_enforce_emergency_governance())

    @patch.dict("os.environ", {"PR_TITLE": "fix something", "PR_LABELS": ""},
                clear=False)
    def test_no_governance_fails(self):
        self.assertFalse(_enforce_emergency_governance())

    @patch.dict("os.environ", {"PR_TITLE": "", "PR_LABELS": "bug,ci"},
                clear=False)
    def test_wrong_labels_fails(self):
        self.assertFalse(_enforce_emergency_governance())


class ChangeClassTests(unittest.TestCase):
    """Test main() behaviour for each CHANGE_CLASS value."""

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ",
                {"CHANGE_CLASS": "emergency_override",
                 "PR_TITLE": "[emergency] bypass all",
                 "PR_LABELS": "emergency"},
                clear=False)
    def test_emergency_override_with_governance_passes(self, mock_resolve, mock_numstat):
        # No numstat needed — all checks bypassed
        self.assertEqual(main(), 0)
        mock_numstat.assert_not_called()

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ",
                {"CHANGE_CLASS": "emergency_override",
                 "PR_TITLE": "normal PR",
                 "PR_LABELS": ""},
                clear=False)
    def test_emergency_override_without_governance_fails(self, mock_resolve, mock_numstat):
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"CHANGE_CLASS": "spec_sync"}, clear=False)
    def test_spec_sync_allows_multi_module(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"CHANGE_CLASS": "spec_sync"}, clear=False)
    def test_spec_sync_still_enforces_line_limit(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (150, 60, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"CHANGE_CLASS": "infra_change"}, clear=False)
    def test_infra_change_allows_large_single_module(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (500, 200, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"CHANGE_CLASS": "infra_change"}, clear=False)
    def test_infra_change_still_enforces_single_module(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (500, 200, "modules/fsm/main.py"),
            (100, 50, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {"CHANGE_CLASS": "unknown_value"}, clear=False)
    def test_unknown_change_class_fails(self, mock_resolve, mock_numstat):
        self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
