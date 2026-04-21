<!-- lint disable no-shortcut-reference-link no-undefined-references -->
# Canary Rollout Runbook — lush-givex-worker (P2-5)

This is the **final gate** before enabling the bot against the real
`orderQueue` with live Telegram / BitBrowser / Givex APIs. Every canary
step below must PASS — and be observed for **24 h** — before the next
step is attempted. A FAIL at any step triggers the procedure in
`docs/rollback.md`.

> Prerequisites: P0-1..P0-6, P1-1..P1-5, P2-1..P2-4 merged; the 14 E2E
> tests added in P2-4 green in CI against mocks.

---

## 1. The five canary steps

Each step reuses the same production binary; only the scope of traffic
(`WORKER_COUNT`, billing-pool size, Givex task feed) changes between
steps.

### Step 1 — Smoke test (1 worker, 1 TEST Visa)

- Setup
  - `WORKER_COUNT=1`
  - Single TEST card `4111 1111 1111 1111` in `billing_pool/`
  - `GIVEX_EGIFT_URL` / `GIVEX_PAYMENT_URL` → **staging** sandbox URLs
  - `ENABLE_PRODUCTION_TASK_FN=1`
- Run: a single purchase cycle via `python -m app`.
- PASS criteria
  - No uncaught exception in `worker.log`.
  - Full journey trace present:
    `preflight → navigate → egift → cart → guest → payment → popup`.
  - Trace line format matches `timestamp | worker_id | trace_id | state | action | status`.
  - `modules/monitor/main.py::get_metrics()` reports the cycle exactly
    once (no duplicate idempotency writes).

### Step 2 — Mini-canary (1 worker, 1 real card, $5 order)

- Setup: same as Step 1, but
  - 1 **real** card in `billing_pool/`.
  - 1 tiny real order ($5) fed into `orderQueue`.
  - `GIVEX_EGIFT_URL` / `GIVEX_PAYMENT_URL` → **production** URLs.
- Run: one cycle end-to-end.
- PASS criteria
  - Givex records the transaction with the expected amount.
  - Telegram receives a **blurred** PNG screenshot (the blur filter in
    `modules/notification/screenshot_blur.py` is applied — no raw PAN,
    CVV, or expiry pixels visible).
  - `grep -E '(4[0-9]{3}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}|cvv=)' worker.log`
    returns **zero** matches.
  - `.idempotency_store.json` contains exactly one `completed` entry
    for the task_id.

### Step 3 — Single-worker soak (1 worker, 5 cards)

- Setup: same as Step 2 but 5 cards chained in the billing pool; some
  of them expected to decline (e.g. low-balance gift cards).
- Run: 5 consecutive cycles.
- PASS criteria
  - ≥1 decline → automatic swap to next card via the P0-2 retry loop.
  - ≥1 success.
  - Per-`trace_id` `swap_count` ≤ 2 everywhere in the log
    (`grep 'swap_count=' worker.log | sort -t= -k2 -n | tail`).
  - **No double-charge**: for every `task_id` there is at most one
    `completed` record and at most one Givex transaction of the
    expected amount. Reconcile `.idempotency_store.json` against
    Givex admin export before proceeding.

### Step 4 — Multi-worker (3 workers parallel)

- Setup: `WORKER_COUNT=3`, 3 cards per worker.
- Run: 3 parallel cycles.
- PASS criteria
  - No `task_id` assigned to more than one worker at a time
    (`_in_flight_task_ids` invariant; no log line matching
    `duplicate.*task_id`).
  - No BitBrowser profile corruption (each worker owns a distinct
    profile directory).
  - No race condition in the billing pool: the same card is never
    claimed by two workers in the same minute.
  - Metrics aggregate cleanly: `success_rate`, `swap_rate`, and
    `cdp_timeout_rate` remain within their baselines (see §2).

### Step 5 — Full production

Only after Steps 1–4 have each been observed for 24 h with PASS:

- Setup: `WORKER_COUNT` at its configured production value; full
  `orderQueue` enabled.
- PASS criteria
  - `success_rate` ≥ baseline captured in Step 3.
  - No rollback trigger from `docs/rollback.md` §1 fires for 24 h.

---

## 2. Monitoring dashboard

The monitoring dashboard must surface these three rates per worker and
in aggregate. Each is derived from counters that already exist in the
codebase; wire them into your preferred metrics backend (Prometheus /
Datadog / Grafana — this repo is backend-agnostic).

| Metric | Source | Target (canary PASS) |
|---|---|---|
| `success_rate` | `modules/monitor/main.py::get_metrics()["success_rate"]` (wraps `get_success_rate()` = `success_count / (success_count + error_count)`) | ≥ `baseline_success_rate` − 5 pp |
| `swap_rate` | Count of `swap_count=` log events ÷ total cycles, per 5-min window | ≤ 0.5 (i.e. at most one swap every two cycles on average) |
| `cdp_timeout_rate` | Count of `cdp.*timeout` log events ÷ total cycles, per 5-min window | ≤ 0.05 |

Additional gauges that must be visible on the dashboard:

- `baseline_success_rate` (pin the value captured at start of Step 3).
- `in_flight_task_ids` size (must stay < `WORKER_COUNT`).
- `completed_task_ids` size (monotonically non-decreasing within a
  retention window).
- Restart counter: `modules/monitor/main.py::get_metrics()["restarts_last_hour"]`.

## 3. Abort criteria (shared with `docs/rollback.md` §1)

Trigger rollback **immediately** on any of:

- Success-rate drop > 10 pp below baseline for 2 consecutive windows.
- Any `swap_count` > 2 for a single `trace_id`.
- Any PAN / CVV / Givex token visible in logs or in a Telegram PNG.
- `cdp_timeout_rate` > 5% for a 5-minute window.
- Any suspected double-charge.
- Any unhandled exception that escapes `run_cycle`.

## 4. Observation window

Between every canary step, observe the metrics above for a **24 h**
window with no new deploys. Only advance to the next step if every
PASS criterion in this doc **and** every "must not trigger" row in
`docs/rollback.md` §1 holds for the full window.

## 5. Operator checklist

Tick each item only after the previous step's 24 h observation has
elapsed without triggering any abort criterion:

- [ ] Step 1 — Smoke test PASS, 24 h observation complete.
- [ ] Step 2 — Mini-canary PASS, 24 h observation complete.
- [ ] Step 3 — Single-worker soak PASS, 24 h observation complete.
- [ ] Step 4 — Multi-worker PASS, 24 h observation complete.
- [ ] Step 5 — Full production enabled; `success_rate`, `swap_rate`,
  `cdp_timeout_rate` all within target for the first 24 h.
- [ ] P2-4 E2E suite (14 tests) executed against real staging APIs
  and all tests PASS.

## 6. Links

- Rollback procedure: `docs/rollback.md`
- Operator runbook (day-to-day): `docs/operations/RUNBOOK.md`
- Staging checklist: `docs/staging/PHASE4_CHECKLIST.md`
- Feature-flag defaults: `integration/orchestrator.py` (§"ENABLE_*"),
  `integration/runtime.py`.
