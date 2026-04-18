# Addendum — CDP Driver Method Audit (U-03)

**Source:** `modules/cdp/driver.py` — `fill_payment_and_billing`,
`submit_purchase`, `detect_page_state`.

## Navigation calls

None of the three methods contains any `driver.get(...)` or
`driver.navigate(...)` call. Only `preflight_geo_check` (`URL_GEO_CHECK`) and
`navigate_to_egift` (`URL_BASE`) navigate, both outside this audit scope.

## Selectors / URLs

- `fill_payment_and_billing`: `SEL_CARD_NAME`, `SEL_CARD_NUMBER`,
  `SEL_CARD_EXPIRY_MONTH`, `SEL_CARD_EXPIRY_YEAR`, `SEL_CARD_CVV`,
  `SEL_BILLING_ADDRESS`, `SEL_BILLING_COUNTRY`, `SEL_BILLING_STATE`,
  `SEL_BILLING_CITY`, `SEL_BILLING_ZIP`, `SEL_BILLING_PHONE`.
- `submit_purchase`: `SEL_COMPLETE_PURCHASE` (via `_hesitate_before_submit` and
  `bounding_box_click`).
- `detect_page_state`: `SEL_CONFIRMATION_EL`, `SEL_VBV_IFRAME`,
  `SEL_DECLINED_MSG`, `SEL_UI_LOCK_SPINNER`; URL fragments
  `URL_CONFIRM_FRAGMENTS`; text scan `"declined"`, `"transaction failed"`.

All selectors match Blueprint §4–§6 exactly. No undisclosed selectors or URLs.

**Verdict: CLEARED.**
