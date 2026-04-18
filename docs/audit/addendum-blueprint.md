# Addendum — Blueprint Reconciliation (U-04)

**Source:** `spec/blueprint.md` §6–§11.

| Blueprint §6 item | Status |
|---|---|
| Ngã rẽ 1 — UI-lock focus-shift retry | PRESENT (`detect_page_state` → `"ui_lock"`) |
| Ngã rẽ 2 — `/confirmation` success | PRESENT (`URL_CONFIRM_FRAGMENTS`, `SEL_CONFIRMATION_EL`) |
| Ngã rẽ 3 — VBV/3DS iframe detection | PRESENT (`SEL_VBV_IFRAME` → `"await_3ds"`) |
| Ngã rẽ 3 — Dynamic 8–12 s iframe wait | NOT FOUND — follow-up |
| Ngã rẽ 3 — CDP iframe absolute-coord cancel click | NOT FOUND (`SEL_VBV_CANCEL_BTN` defined but no handler) — follow-up |
| Ngã rẽ 4 — Ctrl+A + Backspace CDP card-clear | NOT FOUND (`clear_card_fields()` is best-effort only) — follow-up |
| Ngã rẽ 4 — Swap from OrderQueue | PRESENT (`retry_new_card`) |
| Retry cap = OrderQueue size | PRESENT (caller-controlled) |

§7 end-of-cycle cleanup: BitBrowser profile return not yet wired (F-01 scope).
§8–§11 (Behavior / Anti-detect / Day-Night / Sync matrix): all ✓ ĐỒNG BỘ.

## Spawned follow-up issue titles

1. "Implement VBV/3DS 8–12 s dynamic wait in iframe handler"
2. "Implement CDP iframe absolute-coordinate cancel-click for VBV/3DS (Blueprint §6 Ngã rẽ 3)"
3. "Implement Ctrl+A + Backspace CDP clear in card-swap flow (Blueprint §6 Ngã rẽ 4)"

**Verdict: REMAINS_OPEN** — three §6 gaps documented; do not fix here.
