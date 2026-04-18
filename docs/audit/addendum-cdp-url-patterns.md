# Addendum — CDP Network URL Patterns (U-05)

**Source:** `integration/orchestrator.py`

```python
_CDP_NETWORK_URL_PATTERNS = ("/checkout/total", "/api/tax", "/api/checkout", "cws4.0")
```

| Pattern | Rationale | Required endpoint coverage |
|---|---|---|
| `/checkout/total` | substring match for `/api/checkout/total` | ✓ `/api/checkout/total` |
| `/api/tax` | exact substring for tax endpoint | ✓ `/api/tax` |
| `/api/checkout` | prefix covering checkout endpoints | ✓ (redundant) |
| `cws4.0` | Givex base domain path | ✓ all Givex URLs |

`/api/checkout/total` and `/api/tax` are both covered. No gaps.

Lock-in test: `tests/verification/test_cdp_url_patterns.py` asserts exact membership.

**Verdict: CLEARED.**
