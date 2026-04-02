# CURRENT SYSTEM STATE

**Audit Date:** 2026-04-02
**Repository:** 1minhtaocompany/lush-givex-worker
**Base Commit:** 3eb5eb6 (Merge pull request #86 from hotfix/cleanup-audit-findings)

---

## Spec Status

| Spec File | Version | Exists | Notes |
|-----------|---------|--------|-------|
| `spec/core/interface.md` | 2.0 | ✅ | Core FSM contract — 4 functions (add_new_state, get_current_state, transition_to, reset_states) |
| `spec/integration/interface.md` | 2.0 | ✅ | Integration contract — 6 functions (enable_network_monitor, wait_for_total, select_profile, detect_page_state, fill_card, fill_billing, clear_card_fields) |
| `spec/interface.md` (aggregated) | 2.0 | ✅ | Backward-compatible aggregation of core + integration. 10 functions total. |
| `spec/fsm.md` | 1.0 | ✅ | FSM behavioral spec — ALLOWED_STATES: ui_lock, success, vbv_3ds, declined |
| `spec/watchdog.md` | 1.0 | ✅ | Watchdog behavioral spec — Total Watchdog lifecycle, threading model |
| `spec/VERSIONING.md` | 1.0 | ✅ | Versioning rules — MAJOR.MINOR format, migration rules documented |
| `spec/blueprint.md` | N/A | ✅ | Master blueprint — full operational scenario for 1 cycle (7 stages) |
| `spec/schema.py` | N/A | ✅ | DEPRECATED — contract-only reference. Runtime code must import from modules.common |
| `spec/.github/SPEC-6-Native-AI-Workflow.md` | 2.0 | ✅ | Execution workflow — phases, AI tiers, CI checks, security gates |

**Spec Consistency:** All spec-version headers match VERSIONING.md table. Aggregated spec is consistent with segmented files (verified by check_spec_consistency).

**v2.0 Breaking Changes (completed):**
- Exception types moved from `spec.schema` → `modules.common.exceptions`
- Data types moved from `spec.schema` → `modules.common.types`
- `spec/` is no longer a runtime dependency

---

## Modules Status

| Module | Path | Public Functions | Implementation | Imports Correct |
|--------|------|-----------------|----------------|-----------------|
| **fsm** | `modules/fsm/main.py` | `add_new_state(state_name)`, `get_current_state()`, `transition_to(target_state)`, `reset_states()` | ✅ FULL | ✅ Uses `modules.common.exceptions`, `modules.common.types` |
| **watchdog** | `modules/watchdog/main.py` | `enable_network_monitor()`, `wait_for_total(timeout)` | ✅ FULL | ✅ Uses `modules.common.exceptions` |
| **billing** | `modules/billing/main.py` | `select_profile(zip_code)` | ⚠️ STUB (`raise NotImplementedError`) | ✅ No imports needed |
| **cdp** | `modules/cdp/main.py` | `detect_page_state()`, `fill_card(card_info)`, `fill_billing(billing_profile)`, `clear_card_fields()` | ⚠️ STUB (`raise NotImplementedError`) | ✅ No imports needed |
| **common** | `modules/common/` | N/A (shared library) | ✅ FULL | N/A |

**Shared Library (`modules/common/`):**
- `modules/common/exceptions.py` — `SessionFlaggedError`, `CycleExhaustedError`, `InvalidStateError`, `InvalidTransitionError`
- `modules/common/types.py` — `State`, `CardInfo`, `BillingProfile`, `WorkerTask`

**Thread Safety:**
- `modules/fsm/main.py` — Uses `threading.Lock` for `_states` registry and `_current_state`
- `modules/watchdog/main.py` — Uses `threading.Lock` + `threading.Event` for monitor state

**Module Isolation:** Zero cross-module imports. `modules/common` is the only shared dependency. `spec/` is not imported at runtime.

---

## CI Status

### Workflow: `.github/workflows/ci.yml`

| Step | Script | Status | Purpose |
|------|--------|--------|---------|
| 1 | `actions/checkout@v4` | ✅ Active | Checkout with `fetch-depth: 0` |
| 2 | `actions/setup-python@v5` | ✅ Active | Python 3.11 |
| 3 | `pip install pytest` | ✅ Active | Install test runner |
| 4 | `ci/check_import_scope.py` | ✅ Active | No cross-module imports; blocks `spec/` imports from `modules/` |
| 5 | `ci/check_signature.py` | ✅ Active | Function signatures match spec (multi-file aware, cross-file duplicate detection) |
| 6 | Fetch PR review state | ✅ Active | Reads APPROVED review count via `gh api` |
| 7 | `ci/check_pr_scope.py` | ✅ Active | ≤200 lines, ≤1 module, CHANGE_CLASS governance |
| 8 | `ci/check_spec_consistency.py` | ✅ Active | Aggregated spec ↔ segmented files must not diverge |
| 9 | `ci/check_version_consistency.py` | ✅ Active | spec-version headers match VERSIONING.md table |
| 10 | `ci/check_spec_lock.py` | ✅ Active | Blocks spec/ modifications unless CHANGE_CLASS=spec_sync authorized |
| 11 | `python -m unittest discover tests` | ✅ Active | Unit tests |

**Trigger:** `pull_request` on `branches: [main]`
**Permissions:** `contents: read`, `pull-requests: read`
**Environment:** `production`

### Known Issue in check_signature.py

`compare_signatures()` return value is discarded at line 578. Only `validate_signatures()` result is enforced. The `compare_signatures` function uses positional index-based matching while `validate_signatures` uses name-based matching. Both parse spec differently. This is a legacy artifact — the name-based validator (`validate_signatures`) is the authoritative check.

---

## Test Status

| Test File | Tests | Target | Status |
|-----------|-------|--------|--------|
| `tests/test_fsm.py` | 55 lines | `modules/fsm/main.py` | ✅ PASS |
| `tests/test_watchdog.py` | 80 lines | `modules/watchdog/main.py` | ✅ PASS |
| `tests/test_check_pr_scope.py` | 631 lines | `ci/check_pr_scope.py` | ✅ PASS |
| `tests/test_check_spec_consistency.py` | 48 lines | `ci/check_spec_consistency.py` | ✅ PASS |
| `tests/test_check_version_consistency.py` | 41 lines | `ci/check_version_consistency.py` | ✅ PASS |

**Total:** 109 tests, all passing (0.151s runtime)

**Coverage Gaps:**
- No tests for `ci/check_import_scope.py`
- No tests for `ci/check_signature.py`
- No tests for `ci/check_spec_lock.py`
- No tests for `modules/billing/main.py` (stub only)
- No tests for `modules/cdp/main.py` (stub only)

---

# IDENTIFIED PHASES

## Phase 1 — Spec Lock & Infrastructure

**Purpose:** Freeze specifications, set up repository structure, CI skeleton, security configuration.

**Files Involved:**
- `spec/fsm.md` — FSM behavioral spec
- `spec/watchdog.md` — Watchdog behavioral spec
- `spec/interface.md` — Aggregated interface contract
- `spec/schema.py` — Type and exception definitions (original location)
- `spec/blueprint.md` — Master operational blueprint
- `spec/VERSIONING.md` — Versioning rules
- `.github/workflows/ci.yml` — CI pipeline
- `.editorconfig` — Editor configuration
- `.gitignore` — Git ignore rules

**Completion Status:** ✅ DONE

---

## Phase 2 — Module Isolation & CI Enforcement

**Purpose:** Create 4 module directories, implement CI enforcement scripts, security gates, PR rulesets.

**Files Involved:**
- `modules/fsm/__init__.py` — Module package
- `modules/watchdog/__init__.py` — Module package
- `modules/billing/__init__.py` — Module package
- `modules/cdp/__init__.py` — Module package
- `modules/common/__init__.py` — Shared library package
- `modules/common/exceptions.py` — Shared exception types
- `modules/common/types.py` — Shared data types
- `ci/check_import_scope.py` — Cross-module import enforcement
- `ci/check_signature.py` — Function signature validation
- `ci/check_pr_scope.py` — PR scope + CHANGE_CLASS governance
- `ci/check_spec_lock.py` — Spec file modification lock
- `ci/check_spec_consistency.py` — Aggregated ↔ segmented divergence guard
- `ci/check_version_consistency.py` — Spec version header validation
- `tests/test_check_pr_scope.py` — PR scope governance tests (631 lines)
- `tests/test_check_spec_consistency.py` — Spec consistency tests
- `tests/test_check_version_consistency.py` — Version consistency tests
- `spec/core/interface.md` — Segmented core spec (v2.0)
- `spec/integration/interface.md` — Segmented integration spec (v2.0)
- `spec/.github/SPEC-6-Native-AI-Workflow.md` — AI workflow spec (v2.0)
- `.github/AI_CONTEXT.md` — AI context and hard rules
- `.github/copilot-instructions.md` — Copilot instructions
- `.github/dependabot-auto-merge.yml` — Dependabot auto-merge config

**Completion Status:** ✅ DONE

---

## Phase 3 — Implementation

**Purpose:** Implement all 4 modules (fsm, cdp, billing, watchdog) with unit tests per spec.

**Files Involved:**
- `modules/fsm/main.py` — FSM implementation (4 functions)
- `modules/watchdog/main.py` — Watchdog implementation (2 public + 2 internal functions)
- `modules/billing/main.py` — Billing stub (1 function)
- `modules/cdp/main.py` — CDP stub (4 functions)
- `tests/test_fsm.py` — FSM unit tests
- `tests/test_watchdog.py` — Watchdog unit tests
- `tasks/add_new_state_spec.md` — Task spec for add_new_state
- `tasks/add_new_state_summary.md` — Task summary (empty)

**Completion Status:** ⚠️ PARTIAL

| Sub-task | Status |
|----------|--------|
| FSM implementation | ✅ DONE — all 4 functions implemented and tested |
| Watchdog implementation | ✅ DONE — 2 public + 2 internal functions implemented and tested |
| Billing implementation | ❌ MISSING — `select_profile()` is a stub (`raise NotImplementedError`) |
| CDP implementation | ❌ MISSING — all 4 functions are stubs (`raise NotImplementedError`) |
| Billing unit tests | ❌ MISSING |
| CDP unit tests | ❌ MISSING |

---

## Phase 4 — Integration & Staging Validation

**Purpose:** Full module integration, staging environment testing, rollout validation.

**Files Involved:** None yet.

**Completion Status:** ❌ MISSING — No integration code, no staging configuration, no smoke tests.

---

## Phase 5 — Production Deployment

**Purpose:** Production rollout with kill-switch and monitoring.

**Files Involved:** None yet.

**Completion Status:** ❌ MISSING — Not started.

---

# ACTIVE CONSTRAINTS

## CI Rules Currently Enforced

| Rule | Enforcement | Failure Mode |
|------|-------------|-------------|
| **No cross-module imports** | `check_import_scope.py` — blocks `modules.X` importing `modules.Y` (except `modules.common`) | CI FAIL |
| **No spec imports from modules** | `check_import_scope.py` — blocks `import spec` or `from spec import` in `modules/` | CI FAIL |
| **Function signatures match spec** | `check_signature.py` — name-based parameter validation against spec | CI FAIL |
| **PR scope: ≤200 lines** | `check_pr_scope.py` — excludes `tests/` and `ci/` from count | CI FAIL |
| **PR scope: ≤1 module** | `check_pr_scope.py` — counts distinct modules under `modules/` | CI FAIL |
| **Spec files locked** | `check_spec_lock.py` — blocks `spec/` modifications unless `spec_sync` authorized | CI FAIL |
| **Spec consistency** | `check_spec_consistency.py` — aggregated must match segmented union | CI FAIL |
| **Version consistency** | `check_version_consistency.py` — file headers must match VERSIONING.md table | CI FAIL |
| **Unit tests pass** | `python -m unittest discover tests` | CI FAIL |

## Governance Rules Detected

| Rule | Description | Implementation |
|------|-------------|----------------|
| **CHANGE_CLASS required** | Every PR gets a CHANGE_CLASS (auto-detected or explicit) | `check_pr_scope.py` — auto-detects from PR title `[emergency]`/`[spec-sync]`/`[infra]` and changed files |
| **Authorization for overrides** | Non-normal CHANGE_CLASS requires: PR label `approved-override` OR `CHANGE_CLASS_APPROVED=true` | `check_pr_scope.py` `_check_authorization()` |
| **Emergency requires review** | `emergency_override` additionally requires at least 1 APPROVED review | `check_pr_scope.py` via `PR_REVIEW_STATE` env |
| **Context binding** | CHANGE_CLASS must match PR content (e.g., `spec_sync` requires `spec/` files changed) | `check_pr_scope.py` `_check_context_binding()` |
| **Audit trail** | All override usage logged as structured JSON to stdout | `check_pr_scope.py` `_emit_audit_log()` |
| **Spec lock bypass** | Only `spec_sync` + authorized can modify `spec/` | `check_spec_lock.py` |
| **ALLOW_MULTI_MODULE deprecated** | Legacy flag no longer present in codebase | Fully removed |

## Security Gates (Configured at Repository Level)

Per `spec/.github/SPEC-6-Native-AI-Workflow.md` §3.9 and `.github/AI_CONTEXT.md` Rule 4:

| Gate | Requirement |
|------|-------------|
| CodeQL | No High/Critical alerts |
| Dependabot | No High+ unaddressed vulnerabilities |
| Secret Scanning + Push Protection | No leaked secrets |
| Copilot Autofix | Suggestions reviewed (accept or dismiss with reason) |

## AI Workflow Rules (Hard Rules from AI_CONTEXT.md)

| Rule | Description |
|------|-------------|
| Rule 1 — Assign-to-Deploy | Tasks via Issue Assign, not `@workspace` |
| Rule 2 — Auto-Fix Loop | Agent reads review comments and auto-fixes |
| Rule 3 — Circuit Breaker | ≥3 rejects → Gemini 3.1 Pro arbitration |
| Rule 4 — Security Gate | 4-gate security check before merge |
| Rule 5 — CI Failure Recovery | Agent reads CI logs, auto-fixes; ≥2 same failures → human intervention |
