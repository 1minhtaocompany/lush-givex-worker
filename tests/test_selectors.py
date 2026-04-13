"""Tests for modules/cdp/selectors.py — URL and selector constants registry."""

import unittest
import modules.cdp.selectors as sel


# All URL constants
_URL_CONSTANTS = [
    ("URL_HOME", sel.URL_HOME),
    ("URL_EGIFT_PAGE", sel.URL_EGIFT_PAGE),
    ("URL_CART", sel.URL_CART),
    ("URL_CHECKOUT", sel.URL_CHECKOUT),
    ("URL_PAYMENT", sel.URL_PAYMENT),
]

# All selector constants
_SEL_CONSTANTS = [
    ("SEL_COOKIE_ACCEPT", sel.SEL_COOKIE_ACCEPT),
    ("SEL_BUY_EGIFT", sel.SEL_BUY_EGIFT),
    ("SEL_GREETING_MSG", sel.SEL_GREETING_MSG),
    ("SEL_AMOUNT", sel.SEL_AMOUNT),
    ("SEL_RECIPIENT_NAME", sel.SEL_RECIPIENT_NAME),
    ("SEL_RECIP_EMAIL", sel.SEL_RECIP_EMAIL),
    ("SEL_CONFIRM_EMAIL", sel.SEL_CONFIRM_EMAIL),
    ("SEL_FROM_NAME", sel.SEL_FROM_NAME),
    ("SEL_ADD_TO_CART", sel.SEL_ADD_TO_CART),
    ("SEL_REVIEW_CHECKOUT", sel.SEL_REVIEW_CHECKOUT),
    ("SEL_BEGIN_CHECKOUT", sel.SEL_BEGIN_CHECKOUT),
    ("SEL_GUEST_EMAIL", sel.SEL_GUEST_EMAIL),
    ("SEL_GUEST_CONTINUE", sel.SEL_GUEST_CONTINUE),
    ("SEL_CC_NAME", sel.SEL_CC_NAME),
    ("SEL_CC_NUM", sel.SEL_CC_NUM),
    ("SEL_CC_EXP_MON", sel.SEL_CC_EXP_MON),
    ("SEL_CC_EXP_YR", sel.SEL_CC_EXP_YR),
    ("SEL_CC_CVV", sel.SEL_CC_CVV),
    ("SEL_BILLING_ADDR1", sel.SEL_BILLING_ADDR1),
    ("SEL_BILLING_COUNTRY", sel.SEL_BILLING_COUNTRY),
    ("SEL_BILLING_PROVINCE", sel.SEL_BILLING_PROVINCE),
    ("SEL_BILLING_CITY", sel.SEL_BILLING_CITY),
    ("SEL_BILLING_POSTAL", sel.SEL_BILLING_POSTAL),
    ("SEL_BILLING_PHONE", sel.SEL_BILLING_PHONE),
    ("SEL_COMPLETE_PURCHASE", sel.SEL_COMPLETE_PURCHASE),
]

_GIVEX_BASE = "https://wwws-usa2.givex.com/cws4.0/lushusa"


class TestURLConstants(unittest.TestCase):
    def test_all_urls_are_strings(self):
        for name, val in _URL_CONSTANTS:
            self.assertIsInstance(val, str, f"{name} must be a str")

    def test_all_urls_non_empty(self):
        for name, val in _URL_CONSTANTS:
            self.assertTrue(val.strip(), f"{name} must not be empty")

    def test_all_urls_start_with_https(self):
        for name, val in _URL_CONSTANTS:
            self.assertTrue(val.startswith("https://"), f"{name} must start with https://")

    def test_all_urls_point_to_givex_lushusa(self):
        for name, val in _URL_CONSTANTS:
            self.assertIn(_GIVEX_BASE, val, f"{name} must contain givex lushusa base path")

    def test_url_order(self):
        """URLs must follow blueprint flow order: home → egift → cart → checkout → payment."""
        urls = [v for _, v in _URL_CONSTANTS]
        self.assertEqual(urls[0], sel.URL_HOME)
        self.assertEqual(urls[1], sel.URL_EGIFT_PAGE)
        self.assertEqual(urls[2], sel.URL_CART)
        self.assertEqual(urls[3], sel.URL_CHECKOUT)
        self.assertEqual(urls[4], sel.URL_PAYMENT)

    def test_payment_url_contains_guest_path(self):
        self.assertIn("/guest/payment", sel.URL_PAYMENT)

    def test_cart_url_contains_shopping_cart(self):
        self.assertIn("shopping-cart", sel.URL_CART)


class TestSelectorConstants(unittest.TestCase):
    def test_all_selectors_are_strings(self):
        for name, val in _SEL_CONSTANTS:
            self.assertIsInstance(val, str, f"{name} must be a str")

    def test_all_selectors_non_empty(self):
        for name, val in _SEL_CONSTANTS:
            self.assertTrue(val.strip(), f"{name} must not be empty")

    def test_id_selectors_start_with_hash(self):
        id_selectors = [
            sel.SEL_COOKIE_ACCEPT,
            sel.SEL_GREETING_MSG,
            sel.SEL_AMOUNT,
            sel.SEL_RECIPIENT_NAME,
            sel.SEL_RECIP_EMAIL,
            sel.SEL_CONFIRM_EMAIL,
            sel.SEL_FROM_NAME,
            sel.SEL_REVIEW_CHECKOUT,
            sel.SEL_BEGIN_CHECKOUT,
            sel.SEL_GUEST_EMAIL,
            sel.SEL_GUEST_CONTINUE,
            sel.SEL_CC_NAME,
            sel.SEL_CC_NUM,
            sel.SEL_CC_EXP_MON,
            sel.SEL_CC_EXP_YR,
            sel.SEL_CC_CVV,
            sel.SEL_BILLING_ADDR1,
            sel.SEL_BILLING_COUNTRY,
            sel.SEL_BILLING_PROVINCE,
            sel.SEL_BILLING_CITY,
            sel.SEL_BILLING_POSTAL,
            sel.SEL_BILLING_PHONE,
            sel.SEL_COMPLETE_PURCHASE,
        ]
        for s in id_selectors:
            self.assertTrue(s.startswith("#"), f"ID selector '{s}' must start with #")

    def test_cws_field_naming_convention(self):
        """All form field selectors must follow cws_ naming convention."""
        cws_selectors = [
            sel.SEL_GREETING_MSG, sel.SEL_AMOUNT, sel.SEL_RECIPIENT_NAME,
            sel.SEL_RECIP_EMAIL, sel.SEL_CONFIRM_EMAIL, sel.SEL_FROM_NAME,
            sel.SEL_ADD_TO_CART, sel.SEL_REVIEW_CHECKOUT, sel.SEL_BEGIN_CHECKOUT,
            sel.SEL_GUEST_EMAIL, sel.SEL_GUEST_CONTINUE,
            sel.SEL_CC_NAME, sel.SEL_CC_NUM, sel.SEL_CC_EXP_MON,
            sel.SEL_CC_EXP_YR, sel.SEL_CC_CVV,
            sel.SEL_BILLING_ADDR1, sel.SEL_BILLING_COUNTRY, sel.SEL_BILLING_PROVINCE,
            sel.SEL_BILLING_CITY, sel.SEL_BILLING_POSTAL, sel.SEL_BILLING_PHONE,
            sel.SEL_COMPLETE_PURCHASE,
        ]
        for s in cws_selectors:
            self.assertIn("cws_", s, f"Selector '{s}' must contain cws_ prefix")

    def test_buy_egift_selector_contains_cardforeground(self):
        self.assertIn("cardForeground", sel.SEL_BUY_EGIFT)

    def test_add_to_cart_has_child_combinator(self):
        """ADD TO CART targets the inner span via child combinator."""
        self.assertIn("> span", sel.SEL_ADD_TO_CART)

    def test_complete_purchase_is_critical_selector(self):
        """COMPLETE PURCHASE selector must be present and non-empty (CRITICAL_SECTION)."""
        self.assertTrue(sel.SEL_COMPLETE_PURCHASE)
        self.assertTrue(sel.SEL_COMPLETE_PURCHASE.startswith("#"))

