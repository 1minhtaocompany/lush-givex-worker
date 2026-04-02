import os
import tempfile
import unittest
from unittest.mock import patch

from modules.billing import main as billing
from modules.common.exceptions import CycleExhaustedError
from modules.common.types import BillingProfile


class BillingTests(unittest.TestCase):
    def setUp(self):
        billing._reset_state()

    def tearDown(self):
        billing._reset_state()

    def _set_profiles(self, profiles, cursor=0):
        with billing._lock:
            billing._profiles = profiles
            billing._cursor = cursor

    def test_select_profile_valid_input_returns_profile(self):
        profile = BillingProfile(
            first_name="Ana",
            last_name="Bell",
            address="123 Main St",
            city="New York",
            state="NY",
            zip_code="10001",
            phone="2125550100",
            email="ana.bell@example.com",
        )
        self._set_profiles([profile], cursor=0)

        result = billing.select_profile("10001")

        self.assertIsInstance(result, BillingProfile)
        self.assertEqual(result, profile)

    def test_select_profile_empty_pool_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"BILLING_POOL_DIR": tmpdir}):
                with self.assertRaises(CycleExhaustedError):
                    billing.select_profile("12345")

    def test_select_profile_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            billing.select_profile({"zip": "10001"})


if __name__ == "__main__":
    unittest.main()
