# Addendum — Selenium Flavor Pin (U-06)

**Pinned:** `selenium-wire==5.1.0` in `requirements.txt`.

Rationale: the orchestrator's Total Watchdog uses `driver.add_cdp_listener` to
intercept `Network.responseReceived` events — a method provided by
`selenium-wire` (not by stock `selenium`). Neither flavor was pinned before.
`selenium-wire==5.1.0` is the latest stable at audit time; no known advisories.

## Startup probe

`probe_cdp_listener_support(driver_obj)` in `integration/runtime.py`:
- Verifies `hasattr(driver_obj, "add_cdp_listener")` and callable.
- Raises `RuntimeError` with a clear operator message otherwise.
- Exported as public helper. Not wired in `runtime.py` today because no driver
  is constructed there (F-01 unfixed). A TODO directs PR-04 (F-01) to invoke it
  at `task_fn` bring-up.

Unit test: `tests/verification/test_selenium_flavor_probe.py`.

**Verdict: CLEARED.**
