# Addendum — Runtime Wiring Posture (U-02, U-08)

**Source:** `integration/runtime.py` (all functions in scope).

## U-02 — CDP / BitBrowser registration calls

None of `cdp.register_driver`, `cdp._register_pid`, `cdp.register_browser_profile`,
`BitBrowserSession(...)`, or `get_bitbrowser_client()` appears anywhere in
`integration/runtime.py`. The only `cdp` usage is `cdp.get_browser_profile()`
(read-only) in `get_worker_browser_profile()` and the module imports on lines
25–26. No driver is constructed, no PID registered, no browser profile
registered, no BitBrowser session opened. F-01/F-03 wiring is not yet present.

**Verdict: CLEARED.** Lock-in test `tests/verification/test_runtime_wiring_posture.py`
breaks if silent wiring is added before F-01/F-03 PRs are reviewed.

## U-08 — Stagger-start delay between worker launches

`start_worker` applies an exponential `_restart_delay` only when
`_pending_restarts > 0` (a restart backoff, not a stagger). `_apply_scale` calls
`start_worker` in a tight loop with no inter-launch sleep. No `random.uniform(12, 25)`
exists in the module.

Blueprint §2 requires `random.uniform(12, 25)` s between worker launches.

**Verdict: REMAINS_OPEN.** Follow-up issue to be filed:
*"Implement stagger-start delay (random.uniform 12–25 s) between worker launches
per Blueprint §2"*. Do not fix here.
