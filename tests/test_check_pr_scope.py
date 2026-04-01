import unittest
from unittest.mock import patch, MagicMock
import subprocess

from ci.check_pr_scope import (
    _normalize,
    _is_excluded,
    _resolve_change_class,
    _check_authorization,
    _check_context_binding,
    module_from_path,
    get_numstat,
    check,
    main,
    EXCLUDED_PREFIXES,
    MAX_CHANGED_LINES,
    VALID_CHANGE_CLASSES,
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


class ResolveChangeClassTests(unittest.TestCase):
    """Test _resolve_change_class — CHANGE_CLASS is REQUIRED."""

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_returns_none(self):
        self.assertIsNone(_resolve_change_class())

    @patch.dict("os.environ", {"CHANGE_CLASS": ""}, clear=True)
    def test_empty_returns_none(self):
        self.assertIsNone(_resolve_change_class())

    @patch.dict("os.environ", {"CHANGE_CLASS": "emergency_override"}, clear=True)
    def test_reads_change_class(self):
        self.assertEqual(_resolve_change_class(), "emergency_override")

    @patch.dict("os.environ", {"CHANGE_CLASS": "  Spec_Sync  "}, clear=True)
    def test_normalizes_whitespace_and_case(self):
        self.assertEqual(_resolve_change_class(), "spec_sync")

    @patch.dict("os.environ", {"ALLOW_MULTI_MODULE": "true"}, clear=True)
    def test_legacy_allow_multi_module_ignored(self):
        """ALLOW_MULTI_MODULE is no longer recognized."""
        self.assertIsNone(_resolve_change_class())


class AuthorizationTests(unittest.TestCase):
    """Test _check_authorization — override requires approval signal."""

    def test_normal_needs_no_authorization(self):
        self.assertEqual(_check_authorization("normal"), [])

    @patch.dict("os.environ", {"PR_LABELS": "", "CHANGE_CLASS_APPROVED": "", "PR_REVIEW_STATE": ""}, clear=True)
    def test_override_without_approval_fails(self):
        errors = _check_authorization("spec_sync")
        self.assertEqual(len(errors), 1)
        self.assertIn("requires explicit authorization", errors[0])

    @patch.dict("os.environ", {"PR_LABELS": "approved-override,bug", "PR_REVIEW_STATE": ""}, clear=True)
    def test_pr_label_grants_authorization(self):
        self.assertEqual(_check_authorization("spec_sync"), [])

    @patch.dict("os.environ", {"CHANGE_CLASS_APPROVED": "true", "PR_LABELS": "", "PR_REVIEW_STATE": ""}, clear=True)
    def test_admin_approved_grants_authorization(self):
        self.assertEqual(_check_authorization("infra_change"), [])

    @patch.dict("os.environ", {"PR_LABELS": "Approved-Override", "PR_REVIEW_STATE": ""}, clear=True)
    def test_label_check_is_case_insensitive(self):
        self.assertEqual(_check_authorization("spec_sync"), [])

    @patch.dict("os.environ", {"PR_LABELS": "approved-override", "PR_REVIEW_STATE": ""}, clear=True)
    def test_emergency_without_review_fails(self):
        errors = _check_authorization("emergency_override")
        self.assertEqual(len(errors), 1)
        self.assertIn("APPROVED review", errors[0])

    @patch.dict("os.environ", {"PR_LABELS": "approved-override", "PR_REVIEW_STATE": "APPROVED"}, clear=True)
    def test_emergency_with_review_passes(self):
        self.assertEqual(_check_authorization("emergency_override"), [])

    @patch.dict("os.environ", {"PR_LABELS": "", "CHANGE_CLASS_APPROVED": "", "PR_REVIEW_STATE": "APPROVED"}, clear=True)
    def test_emergency_without_label_or_admin_fails(self):
        """Even with review, still needs label or admin approval."""
        errors = _check_authorization("emergency_override")
        self.assertEqual(len(errors), 1)
        self.assertIn("requires explicit authorization", errors[0])


class ContextBindingTests(unittest.TestCase):
    """Test _check_context_binding — CHANGE_CLASS must match PR content."""

    @patch.dict("os.environ", {"PR_TITLE": "[emergency] hotfix"}, clear=True)
    def test_emergency_with_correct_title(self):
        self.assertEqual(
            _check_context_binding("emergency_override", ["modules/fsm/main.py"]),
            [],
        )

    @patch.dict("os.environ", {"PR_TITLE": "normal PR"}, clear=True)
    def test_emergency_without_title_tag_fails(self):
        errors = _check_context_binding("emergency_override", ["modules/fsm/main.py"])
        self.assertEqual(len(errors), 1)
        self.assertIn("[emergency]", errors[0])

    @patch.dict("os.environ", {"PR_TITLE": "update spec"}, clear=True)
    def test_spec_sync_with_spec_changes(self):
        self.assertEqual(
            _check_context_binding("spec_sync", ["spec/fsm.md", "modules/fsm/main.py"]),
            [],
        )

    @patch.dict("os.environ", {"PR_TITLE": "update code"}, clear=True)
    def test_spec_sync_without_spec_changes_fails(self):
        errors = _check_context_binding("spec_sync", ["modules/fsm/main.py"])
        self.assertEqual(len(errors), 1)
        self.assertIn("spec/", errors[0])

    @patch.dict("os.environ", {"PR_TITLE": "update CI"}, clear=True)
    def test_infra_change_with_ci_changes(self):
        self.assertEqual(
            _check_context_binding("infra_change", ["ci/check_pr_scope.py"]),
            [],
        )

    @patch.dict("os.environ", {"PR_TITLE": "update CI"}, clear=True)
    def test_infra_change_with_github_changes(self):
        self.assertEqual(
            _check_context_binding("infra_change", [".github/workflows/ci.yml"]),
            [],
        )

    @patch.dict("os.environ", {"PR_TITLE": "update code"}, clear=True)
    def test_infra_change_without_ci_changes_fails(self):
        errors = _check_context_binding("infra_change", ["modules/fsm/main.py"])
        self.assertEqual(len(errors), 1)
        self.assertIn("ci/", errors[0])

    def test_normal_always_passes(self):
        self.assertEqual(_check_context_binding("normal", []), [])


class ChangeClassIntegrationTests(unittest.TestCase):
    """End-to-end tests for CHANGE_CLASS through main()."""

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_change_class_fails(self):
        """CHANGE_CLASS is REQUIRED — missing = FAIL."""
        self.assertEqual(main(), 1)

    @patch.dict("os.environ", {"CHANGE_CLASS": ""}, clear=True)
    def test_empty_change_class_fails(self):
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "normal",
    }, clear=False)
    def test_normal_enforces_both_limits(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (150, 60, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "normal",
    }, clear=False)
    def test_normal_passes_under_limit(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (50, 10, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "emergency_override",
        "PR_TITLE": "[emergency] hotfix",
        "PR_LABELS": "approved-override",
        "PR_REVIEW_STATE": "APPROVED",
    }, clear=False)
    def test_emergency_override_full_bypass(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (200, 100, "modules/fsm/main.py"),
            (200, 100, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch.dict("os.environ", {
        "CHANGE_CLASS": "emergency_override",
        "PR_TITLE": "[emergency] hotfix",
        "PR_LABELS": "",
        "CHANGE_CLASS_APPROVED": "",
        "PR_REVIEW_STATE": "APPROVED",
    }, clear=False)
    def test_emergency_without_label_fails(self):
        self.assertEqual(main(), 1)

    @patch.dict("os.environ", {
        "CHANGE_CLASS": "emergency_override",
        "PR_TITLE": "[emergency] hotfix",
        "PR_LABELS": "approved-override",
        "PR_REVIEW_STATE": "PENDING",
    }, clear=False)
    def test_emergency_without_review_fails(self):
        self.assertEqual(main(), 1)

    @patch.dict("os.environ", {
        "CHANGE_CLASS": "emergency_override",
        "PR_TITLE": "normal PR",
        "PR_LABELS": "approved-override",
        "CHANGE_CLASS_APPROVED": "",
        "PR_REVIEW_STATE": "APPROVED",
    }, clear=False)
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch("ci.check_pr_scope.get_numstat", return_value=[(10, 5, "modules/fsm/main.py")])
    def test_emergency_without_title_tag_fails(self, mock_numstat, mock_resolve):
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "spec_sync",
        "PR_TITLE": "update interfaces",
        "CHANGE_CLASS_APPROVED": "true",
    }, clear=False)
    def test_spec_sync_bypasses_both_limits(self, mock_resolve, mock_numstat):
        """spec_sync skips line limit AND module limit."""
        mock_numstat.return_value = [
            (200, 100, "spec/fsm.md"),
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "spec_sync",
        "PR_TITLE": "update interfaces",
        "CHANGE_CLASS_APPROVED": "true",
    }, clear=False)
    def test_spec_sync_without_spec_files_fails(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "infra_change",
        "PR_TITLE": "update CI scripts",
        "PR_LABELS": "approved-override",
    }, clear=False)
    def test_infra_bypasses_line_limit_only(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (300, 200, "ci/check_pr_scope.py"),
        ]
        self.assertEqual(main(), 0)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "infra_change",
        "PR_TITLE": "update CI",
        "PR_LABELS": "approved-override",
    }, clear=False)
    def test_infra_still_enforces_module_limit(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (10, 5, "ci/check_pr_scope.py"),
            (10, 5, "modules/fsm/main.py"),
            (10, 5, "modules/watchdog/main.py"),
        ]
        self.assertEqual(main(), 1)

    @patch.dict("os.environ", {"CHANGE_CLASS": "invalid_class"}, clear=False)
    def test_invalid_change_class_fails(self):
        self.assertEqual(main(), 1)

    @patch("ci.check_pr_scope.get_numstat")
    @patch("ci.check_pr_scope.resolve_diff_range", return_value="fake...range")
    @patch.dict("os.environ", {
        "CHANGE_CLASS": "emergency_override",
        "PR_TITLE": "[emergency] hotfix",
        "CHANGE_CLASS_APPROVED": "true",
        "PR_REVIEW_STATE": "APPROVED",
    }, clear=False)
    def test_admin_approved_grants_access(self, mock_resolve, mock_numstat):
        mock_numstat.return_value = [
            (200, 100, "modules/fsm/main.py"),
        ]
        self.assertEqual(main(), 0)


class ConstantsTests(unittest.TestCase):
    def test_max_lines(self):
        self.assertEqual(MAX_CHANGED_LINES, 200)

    def test_excluded_prefixes(self):
        self.assertIn("tests/", EXCLUDED_PREFIXES)
        self.assertIn("ci/", EXCLUDED_PREFIXES)

    def test_valid_change_classes_includes_normal(self):
        self.assertIn("normal", VALID_CHANGE_CLASSES)
        self.assertIn("emergency_override", VALID_CHANGE_CLASSES)
        self.assertIn("spec_sync", VALID_CHANGE_CLASSES)
        self.assertIn("infra_change", VALID_CHANGE_CLASSES)


if __name__ == "__main__":
    unittest.main()
