import unittest

from ci.check_version_consistency import (
    _extract_version,
    check_versions,
    SPEC_DIR,
)


class ExtractVersionTests(unittest.TestCase):
    def test_core_interface_has_version(self):
        path = SPEC_DIR / "core" / "interface.md"
        version = _extract_version(path)
        self.assertIsNotNone(version)
        self.assertRegex(version, r"^\d+\.\d+$")

    def test_integration_interface_has_version(self):
        path = SPEC_DIR / "integration" / "interface.md"
        version = _extract_version(path)
        self.assertIsNotNone(version)

    def test_aggregated_interface_has_version(self):
        path = SPEC_DIR / "interface.md"
        version = _extract_version(path)
        self.assertIsNotNone(version)

    def test_nonexistent_returns_none(self):
        path = SPEC_DIR / "nonexistent.md"
        version = _extract_version(path)
        self.assertIsNone(version)


class VersionConsistencyTests(unittest.TestCase):
    def test_current_versions_are_consistent(self):
        """All tracked spec files should have consistent versions."""
        errors = check_versions()
        self.assertEqual(errors, [], f"Version inconsistency: {errors}")


if __name__ == "__main__":
    unittest.main()
