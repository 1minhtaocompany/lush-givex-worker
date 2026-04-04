# Phase 9 — Execution Design (Clean State)

**Date:** 2026-04-04
**Status:** Ready for Implementation
**Scope:** Execution design only. No implementation code. No spec changes. No Blueprint changes.
**Base State:** Post-rollback clean state (340 tests, no Phase 9 code)

---

## 0. CURRENT SYSTEM STATE (Post-Rollback)

### 0.1 Clean State Confirmation

| Component | Status | Evidence |
|-----------|--------|----------|
| `integration/runtime.py` | ✅ Pre-Phase-9 | No behavior imports, no scaling integration, no worker states |
| `modules/behavior/` | ✅ Does not exist | Directory removed by rollback |
| `modules/delay/` | ✅ Does not exist | Never created |
| `tests/test_behavior.py` | ✅ Does not exist | Removed by rollback |
| `tests/test_scaling_execution.py` | ✅ Does not exist | Removed by rollback |
| Test baseline | ✅ 340 tests passing | Pre-Phase-9 count, CI green |

### 0.2 Runtime State (Current)

```python
# integration/runtime.py — current state:
ALLOWED_STATES = {"INIT", "RUNNING", "STOPPING", "STOPPED"}  # lifecycle only
_runtime_loop:
    metrics = monitor.get_metrics()
    target, action, reasons = rollout.try_scale_up()
    _apply_scale(target, task_fn)  # ← unconditional, no behavior engine
```

**No Phase 9 code exists. System is clean, stable, safe.**

### 0.3 Why Previous Integration Failed

```
WHAT HAPPENED (sai):                    CORRECT ORDER (đúng):
──────────────────                      ────────────────────
1. Behavior Engine      ✅              1. Safe Point Architecture   ← PHẢI ĐI TRƯỚC
2. Scaling Integration  ⚠️ PREMATURE    2. Behavior Engine           ← pure logic
3. Safe Point           ❌ CLOSED       3. Scaling Integration       ← CHỈ SAU safe point
```

**Lesson:** Safe point architecture MUST exist before ANY scaling integration touches runtime.

---

## 1. SPEC ALIGNMENT — Phase 9 Requirements

Source: `spec/.github/SPEC-6-Native-AI-Workflow.md` Phase 9

### 1.1 Required Components (from Spec)

| Spec Component | Description | Priority |
|----------------|-------------|----------|
| **Safe Point Model** | SAFE_POINT, CRITICAL_SECTION — worker execution boundaries | 🔴 MUST BE FIRST |
| **Scaling Rule** | behavior.evaluate() → SCALE_UP / SCALE_DOWN / HOLD | Rule-based decisions |
| **Graceful Shutdown** | Workers MUST complete current operation before stopping | Respects safe points |
| **FSM Requirement** | CRITICAL_SECTION protects payment, VBV, API wait | Phase 10 dependency |
| **Billing Consistency** | No interruption during payment flow | Blueprint §5, §6 alignment |

### 1.2 Phase 10 Dependencies on Phase 9

Phase 10 §10.3 references "CRITICAL_SECTION (defined in Phase 9)"
Phase 10 §10.4 references "SAFE_POINT"
Phase 10 §10.8 references "Phase 9 alignment"

→ Phase 9 MUST define these BEFORE Phase 10 can proceed.

---

## 2. BLUEPRINT ALIGNMENT — Constraints

Source: `spec/blueprint.md` §8–§13

### 2.1 Blueprint §9 (Execution Integration)

> Behavior được inject tại worker execution layer thông qua pattern wrapper.
> KHÔNG can thiệp vào: Runtime loop, Rollout/Scaling, Monitor, FSM.

→ **Scaling MUST NOT disrupt worker execution.** Control layer applies ONLY at safe points.

### 2.2 Blueprint §13 (Safety Alignment)

> Behavior layer KHÔNG can thiệp CRITICAL_SECTION:
> - Payment submit (§5, §6)
> - VBV/3DS handling (§6)
> - API wait (§5 Watchdog)
> - Page reload (§6)

→ **CRITICAL_SECTION must be defined in Phase 9.** Scaling MUST respect these boundaries.

### 2.3 Blueprint §10 (Performance Control)

> total_behavioral_delay_per_step ≤ 7.0s (≥3s headroom for watchdog 10s)

→ Safe point model must enable delay boundaries to be enforced.

---

## 3. EXECUTION PRINCIPLES (MANDATORY)

### Principle 1: Safe Point FIRST

**Rule:** Worker execution state model (SAFE_POINT, CRITICAL_SECTION) MUST be implemented BEFORE any scaling integration touches _runtime_loop.

**Rationale:** Without safe points, scaling decisions execute unconditionally → workers killed mid-payment.

### Principle 2: Control Layer Separation

**Rule:** Behavior Decision Engine is pure logic. It MUST NOT trigger runtime actions directly.

**Implementation:** `behavior.evaluate()` returns (action, reasons). Runtime reads the result and applies it ONLY at safe points.

### Principle 3: Scaling ONLY at Safe Points

**Rule:** `_apply_scale()` MUST be gated by `is_safe_to_control()`.

**Implementation:** `_runtime_loop` checks `is_safe_to_control()` before calling `_apply_scale()`. If unsafe → defer to next tick.

### Principle 4: No Blueprint Disruption

**Rule:** Scaling MUST NOT interrupt:
- Payment submit (Complete Purchase)
- VBV/3DS iframe handling
- API wait (CDP Network.responseReceived)
- Page reload operations

### Principle 5: Graceful Shutdown

**Rule:** `stop_worker()` MUST NOT kill workers in CRITICAL_SECTION. Workers complete current critical operation, transition to SAFE_POINT or IDLE, then stop.

---

## 4. TASK BREAKDOWN

### Task 9.1 — Safe Point Architecture (Worker Execution States)

**Objective:**
Add worker-level execution state tracking to `integration/runtime.py`. Define IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT with strict validated transitions. This is the foundation that ALL subsequent Phase 9 and Phase 10 work depends on.

**Scope:**
- File: `integration/runtime.py`
- Add: `ALLOWED_WORKER_STATES = {"IDLE", "IN_CYCLE", "CRITICAL_SECTION", "SAFE_POINT"}`
- Add: `_worker_states: dict` — maps worker_id → current execution state
- Add: `set_worker_state(worker_id, state)` — validated state transitions
- Add: `get_worker_state(worker_id)` → current state
- Add: `get_all_worker_states()` → snapshot of all worker states
- Add: `is_safe_to_control()` → True ONLY when all workers are IDLE or SAFE_POINT
- Add: `_VALID_TRANSITIONS` — strict transition rules (see below)
- Modify: `start_worker()` — initialize worker state to IDLE at registration
- Modify: `_worker_fn()` — transition through states during execution
- Modify: cleanup paths (finally blocks, `stop_worker()`) — remove worker state on exit

**Valid Worker State Transitions:**
```
IDLE → IN_CYCLE            (worker starts executing task_fn)
IN_CYCLE → CRITICAL_SECTION (worker enters payment/VBV/API wait)
IN_CYCLE → SAFE_POINT       (worker at safe point between actions)
CRITICAL_SECTION → IN_CYCLE (worker exits critical section)
SAFE_POINT → IN_CYCLE       (worker resumes from safe point)
IN_CYCLE → IDLE             (worker completes one cycle iteration)
```

**Safety Rules:**
- `set_worker_state()` MUST validate transition against `_VALID_TRANSITIONS`
- `set_worker_state()` MUST validate worker_id exists in `_workers`
- Invalid transitions → `ValueError`
- `is_safe_to_control()` treats missing state entries as UNSAFE
- Thread-safe via existing `_lock`
- Worker states are SEPARATE from lifecycle states (INIT/RUNNING/STOPPING/STOPPED)

**Constraints:**
- NO changes to lifecycle states
- NO changes to `_runtime_loop` (scaling integration comes later)
- NO changes to `_apply_scale()` (scaling integration comes later)
- NO cross-module imports
- Worker states stored alongside worker registration in existing `_lock` scope
- ≤200 lines (excluding tests)

**Completion Criteria:**
- [ ] `ALLOWED_WORKER_STATES` defined with 4 states
- [ ] `_VALID_TRANSITIONS` enforces strict transition rules
- [ ] `set_worker_state()` validates transitions, raises `ValueError` on invalid
- [ ] `set_worker_state()` validates worker_id exists in `_workers`
- [ ] `get_worker_state()` returns current state or raises for unknown worker
- [ ] `get_all_worker_states()` returns snapshot dict
- [ ] `is_safe_to_control()` returns True ONLY when all workers IDLE/SAFE_POINT
- [ ] `is_safe_to_control()` treats missing state as UNSAFE
- [ ] `start_worker()` initializes state to IDLE
- [ ] `_worker_fn()` transitions: IDLE → IN_CYCLE → ... → IDLE
- [ ] Worker state removed on exit (finally block)
- [ ] Tests: all transitions, invalid transitions, is_safe_to_control logic
- [ ] CI pass, 340 baseline tests unaffected
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** None (first task)

---

### Task 9.2 — Behavior Decision Engine (Pure Logic Module)

**Objective:**
Create `modules/behavior/main.py` — pure rule-based scaling decision engine. Returns (action, reasons) based on metrics. Zero integration concerns.

**Scope:**
- File: `modules/behavior/main.py` (NEW)
- Pure function: `evaluate(metrics, current_step_index, max_step_index) → (action, reasons)`
- Output actions: SCALE_UP, SCALE_DOWN, HOLD
- Decision rules:
  - Rule 0 — Cooldown guard: 30s minimum between decisions → HOLD
  - Rule 1 — error_rate > 5% → SCALE_DOWN
  - Rule 2 — restarts > 3/hr → SCALE_DOWN
  - Rule 3 — success_rate drop > 10% from baseline → SCALE_DOWN
  - Rule 4 — all metrics healthy + success_rate ≥ 70% + not at max → SCALE_UP
  - Rule 5 — already at min scale (step 0) → HOLD
- Supporting APIs:
  - `get_decision_history()` — bounded to 100 entries
  - `get_last_decision_time()` — epoch timestamp
  - `get_status()` — thresholds + decision count snapshot
  - `reset()` — clear state for testing

**Constraints:**
- PURE logic — zero cross-module imports
- NO integration with runtime
- NO references to runtime, rollout, monitor, or any other module
- Thread-safe via `threading.Lock`
- Decision history bounded (max 100 entries)
- ≤200 lines (excluding tests)

**Completion Criteria:**
- [ ] `evaluate()` returns valid (action, reasons) for all metric combinations
- [ ] All 6 decision rules implemented and individually testable
- [ ] Cooldown guard prevents rapid decisions
- [ ] Decision history bounded to 100
- [ ] Thread-safe under concurrent evaluation
- [ ] Zero cross-module imports
- [ ] `reset()` clears all state
- [ ] Tests: each rule, cooldown, history bounding, thread safety, reset
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** None (pure module, can parallel with Task 9.1)

---

### Task 9.3 — Scaling Integration with Safe Guard

**Objective:**
Connect `behavior.evaluate()` into `_runtime_loop` WITH the `is_safe_to_control()` guard built in from the start. This is the integration that was done prematurely before — now done correctly with safe point protection.

**Scope:**
- File: `integration/runtime.py` (modify existing)
- Import: `from modules.behavior import main as behavior`
- Modify `_runtime_loop()`:
  1. Call `behavior.evaluate(metrics, step_index, max_step_index)` each tick
  2. Route decision: SCALE_UP → `rollout.try_scale_up()`, SCALE_DOWN → `rollout.force_rollback()`, HOLD → keep
  3. **BEFORE** calling `_apply_scale()`: check `is_safe_to_control()`
  4. If UNSAFE → log "scaling_deferred", skip this tick
  5. If SAFE → proceed with `_apply_scale()`
- Add: consecutive rollback tracking (increment on rollback, clear on scaled_up)
- Modify: `runtime.reset()` to include `behavior.reset()`

**Integration Flow (pseudocode):**
```python
def _runtime_loop(task_fn, interval):
    while _state == "RUNNING":
        metrics = monitor.get_metrics()
        step_index = rollout.get_current_step_index()
        max_step_index = len(rollout.SCALE_STEPS) - 1

        decision, reasons = behavior.evaluate(metrics, step_index, max_step_index)

        if decision == behavior.SCALE_DOWN:
            target = rollout.force_rollback(reason="; ".join(reasons))
            action = "rollback"
        elif decision == behavior.SCALE_UP:
            target, action, _ = rollout.try_scale_up()
        else:  # HOLD
            target = rollout.get_current_workers()
            action = "hold"

        # ← SAFE GUARD (this was MISSING in previous integration)
        current_count = len(get_active_workers())
        if target != current_count:
            if not is_safe_to_control():
                _log_event("runtime", "deferred", "scaling_deferred", {...})
                _safe_sleep(interval)
                continue  # Skip this tick, retry next interval

        _apply_scale(target, task_fn)
        _safe_sleep(interval)
```

**Critical Difference from Previous Integration:**
The previous integration called `_apply_scale()` UNCONDITIONALLY. This design adds `is_safe_to_control()` as a mandatory gate. Scaling is DEFERRED (not lost) when workers are in unsafe states.

**Constraints:**
- NO changes to `behavior.evaluate()` logic (engine unchanged)
- NO changes to `rollout.try_scale_up()`/`force_rollback()` (rollout unchanged)
- NO changes to lifecycle states (INIT/RUNNING/STOPPING/STOPPED)
- NO changes to worker state model (defined in Task 9.1)
- `is_safe_to_control()` MUST be called before `_apply_scale()` when target ≠ current
- `_apply_scale()` internal logic unchanged
- Thread-safe via existing `_lock`
- ≤200 lines (excluding tests)

**Completion Criteria:**
- [ ] `behavior.evaluate()` called each tick in `_runtime_loop`
- [ ] Decision routing: SCALE_UP/DOWN/HOLD → correct rollout call
- [ ] `is_safe_to_control()` checked BEFORE `_apply_scale()` when scaling changes
- [ ] Scaling deferred when unsafe (not lost — retry next tick)
- [ ] "scaling_deferred" logged when deferral occurs
- [ ] Consecutive rollback tracking (increment on rollback, clear on scaled_up)
- [ ] `behavior.reset()` in `runtime.reset()`
- [ ] Tests: decision routing, safe guard deferral, consecutive rollback tracking
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** Task 9.1 (safe point architecture) AND Task 9.2 (behavior engine)

---

### Task 9.4 — Graceful Shutdown Enhancement

**Objective:**
Enhance `stop_worker()` to respect worker execution states. Workers in CRITICAL_SECTION are not forcefully stopped — they complete the critical operation first.

**Scope:**
- File: `integration/runtime.py` (modify existing)
- Modify `stop_worker()`:
  1. Check worker state via `get_worker_state()`
  2. If CRITICAL_SECTION → wait for transition to SAFE_POINT or IDLE (with timeout)
  3. If IDLE or SAFE_POINT → stop immediately (current behavior)
  4. If IN_CYCLE → mark for stop, let `_worker_fn` handle at next safe point
- Modify `stop()` (runtime shutdown):
  1. Set `_state = "STOPPING"` (existing)
  2. Workers check `_should_stop_worker()` at safe points (existing loop break)
  3. Final timeout enforces hard stop if worker doesn't reach safe point

**Constraints:**
- NO changes to decision engine or scaling logic
- Existing timeout behavior preserved as fallback
- Workers MUST NOT hang indefinitely in CRITICAL_SECTION
- Hard timeout still enforces eventual stop
- ≤200 lines (excluding tests)

**Completion Criteria:**
- [ ] `stop_worker()` waits for CRITICAL_SECTION to complete (up to timeout)
- [ ] Workers in IDLE/SAFE_POINT stop immediately
- [ ] Hard timeout prevents indefinite hang
- [ ] Runtime `stop()` respects worker states during graceful shutdown
- [ ] Tests: stop during safe state (immediate), stop during critical section (wait), timeout fallback
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** Task 9.1 (worker states must exist), Task 9.3 (scaling integration)

---

## 5. EXECUTION ORDER (Strict — No Skipping)

### 5.1 Dependency Graph

```
┌─────────────────────────┐  ┌─────────────────────────┐
│ Task 9.1                │  │ Task 9.2                │
│ Safe Point Architecture │  │ Behavior Decision Engine│
│ (Worker Exec States)    │  │ (Pure Logic Module)     │
│ integration/runtime.py  │  │ modules/behavior/main.py│
└────────────┬────────────┘  └────────────┬────────────┘
             │  MUST BE FIRST              │  CAN PARALLEL
             │                             │
             └──────────┬──────────────────┘
                        │
              ┌─────────▼──────────┐
              │ Task 9.3           │
              │ Scaling Integration│
              │ WITH Safe Guard    │
              │ (Connect to runtime│
              │  with is_safe_to_  │
              │  control() gate)   │
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │ Task 9.4           │
              │ Graceful Shutdown  │
              │ Enhancement        │
              └────────────────────┘
```

### 5.2 Execution Waves

```
WAVE 0 (parallel):    Task 9.1  ║  Task 9.2
                         │              │
                         │  Safe Point  │  Behavior Engine
                         │  (runtime)   │  (pure module)
                         │              │
                         └──────┬───────┘
                                │
WAVE 1 (sequential):   Task 9.3  — Scaling Integration WITH Safe Guard
                                │
WAVE 2 (sequential):   Task 9.4  — Graceful Shutdown Enhancement
```

### 5.3 Why This Order

1. **Task 9.1 and 9.2 CAN be parallel** because:
   - Task 9.1 modifies `integration/runtime.py` (adds worker states)
   - Task 9.2 creates `modules/behavior/main.py` (new file, different directory)
   - No file conflicts, no dependency between them
   - Both are prerequisites for Task 9.3

2. **Task 9.3 MUST wait for both 9.1 AND 9.2** because:
   - It imports `behavior.evaluate()` from Task 9.2
   - It calls `is_safe_to_control()` from Task 9.1
   - This is the integration point — BOTH dependencies must exist first
   - **This prevents the "SAI CÁCH TÍCH HỢP" — safe guard exists BEFORE integration**

3. **Task 9.4 MUST wait for 9.3** because:
   - Graceful shutdown enhancement depends on scaling integration being in place
   - The shutdown logic must work with the complete integrated system
   - Task 9.1 provides worker states; Task 9.3 provides the scaling context

---

## 6. DEPENDENCY MATRIX

| Task | Depends On | Can Parallel With | Must Complete Before |
|------|-----------|-------------------|---------------------|
| **9.1** Safe Point Architecture | — (none) | 9.2 | 9.3, 9.4 |
| **9.2** Behavior Decision Engine | — (none) | 9.1 | 9.3 |
| **9.3** Scaling Integration + Safe Guard | 9.1, 9.2 | — | 9.4, Phase 10 |
| **9.4** Graceful Shutdown | 9.1, 9.3 | — | Phase 10 |

---

## 7. INTEGRATION RULES

### Rule 1: No Direct Runtime Trigger

```
❌ WRONG:  behavior.evaluate() → directly calls _apply_scale()
✅ CORRECT: behavior.evaluate() → returns (action, reasons) → runtime reads → checks safe → applies
```

The behavior decision engine MUST NOT have any reference to runtime, rollout, or any integration module.

### Rule 2: Safe Guard is Mandatory

```
❌ WRONG:  _runtime_loop: ... → _apply_scale(target, task_fn)
✅ CORRECT: _runtime_loop: ... → if is_safe_to_control() → _apply_scale(target, task_fn)
                                  else → log("scaling_deferred") → continue
```

`_apply_scale()` MUST NEVER be called without checking `is_safe_to_control()` when target ≠ current.

### Rule 3: Worker State Transitions are Strict

```
❌ WRONG:  set_worker_state(wid, "CRITICAL_SECTION")  # from any state
✅ CORRECT: set_worker_state(wid, "CRITICAL_SECTION")  # only from IN_CYCLE → ValueError otherwise
```

All state transitions validated against `_VALID_TRANSITIONS`. Invalid transitions raise `ValueError`.

### Rule 4: Layer Separation

```
modules/behavior/main.py  →  PURE logic, zero imports from integration/
integration/runtime.py     →  Imports from modules/, orchestrates everything
```

Control decisions (modules/) are SEPARATE from control execution (integration/).

### Rule 5: Graceful Stop

```
❌ WRONG:  stop_worker(wid) → immediately kill thread
✅ CORRECT: stop_worker(wid) → check state → if CRITICAL_SECTION → wait → then stop
```

Workers in CRITICAL_SECTION complete their operation before being stopped.

---

## 8. SAFETY GUARANTEES

After Phase 9 is correctly implemented:

| Guarantee | Mechanism |
|-----------|-----------|
| No kill during payment | `is_safe_to_control()` blocks scaling when ANY worker in CRITICAL_SECTION |
| No kill during VBV/3DS | CRITICAL_SECTION covers VBV iframe handling |
| No kill during API wait | CRITICAL_SECTION covers CDP Network.responseReceived pending |
| No kill during page reload | CRITICAL_SECTION covers page reload operations |
| Scaling eventually applies | Deferred scaling retried each tick until workers reach safe state |
| Graceful shutdown | `stop_worker()` waits for CRITICAL_SECTION to complete |
| Decision engine unaffected | Pure logic module with zero integration dependencies |
| Blueprint flow preserved | FSM transitions unchanged, execution order unchanged |

---

## 9. RISK ASSESSMENT

### 9.1 High: Repeat of "SAI CÁCH TÍCH HỢP"

**Risk:** Task 9.3 could be attempted before Task 9.1, recreating the original problem.

**Mitigation:** Task 9.3 PR MUST fail CI if `is_safe_to_control()` doesn't exist. Task 9.3 MUST import and call `is_safe_to_control()` — this function only exists after Task 9.1 is merged.

### 9.2 Medium: Worker State Threading Complexity

**Risk:** Worker execution states add shared mutable state.

**Mitigation:** Use existing `_lock` in runtime.py. Follow same pattern as worker registration. Validated transitions prevent invalid state combinations.

### 9.3 Medium: Scaling Deferral Starvation

**Risk:** If workers are always in CRITICAL_SECTION, scaling is permanently deferred.

**Mitigation:** Workers cycle through states. CRITICAL_SECTION is bounded by operation (payment submit, VBV wait, API call). Workers transition back to IN_CYCLE → SAFE_POINT → IDLE. Hard timeout in graceful shutdown prevents infinite hang.

### 9.4 Low: BehaviorState vs Worker State Confusion

**Risk:** Phase 9 worker states (IDLE/IN_CYCLE/CRITICAL_SECTION/SAFE_POINT) may be confused with Phase 10 BehaviorState (IDLE/FILLING_FORM/PAYMENT/VBV/POST_ACTION).

**Mitigation:** Different purposes, different locations:
- Worker states (Phase 9) → `integration/runtime.py` — controls scaling safety
- BehaviorState (Phase 10) → `modules/common/types.py` — controls delay injection

---

## 10. VALIDATION CHECKLIST (Per Task)

Every task PR MUST satisfy:

- [ ] CI pipeline passes (all existing 340 tests + new tests)
- [ ] No code-quality warnings introduced
- [ ] No cross-module import violations
- [ ] PR scope ≤ 200 lines (excluding tests)
- [ ] Single module/layer touched per PR
- [ ] Blueprint timing constraints respected (where applicable)
- [ ] Lifecycle states (INIT/RUNNING/STOPPING/STOPPED) unchanged
- [ ] Thread safety verified (concurrent test or reasoning)
- [ ] No Phase 1-8 functionality affected

---

## 11. TRANSITION TO PHASE 10

After Phase 9 completion (all 4 tasks merged, CI green), the system provides:

| Phase 10 Dependency | Provided By |
|---------------------|-------------|
| `CRITICAL_SECTION` worker state | Task 9.1 |
| `SAFE_POINT` worker state | Task 9.1 |
| `is_safe_to_control()` | Task 9.1 |
| `behavior.evaluate()` scaling decisions | Task 9.2 |
| Safe scaling in `_runtime_loop` | Task 9.3 |
| Graceful shutdown respecting worker states | Task 9.4 |

Phase 10 can then proceed with:
- Task 10.1 — Delay Module (pure logic)
- Task 10.2 — BehaviorState Context (pure definition)
- Task 10.3 — Behavior Wrapper (integration)
- Task 10.4 — NO-DELAY Zone Guard Validation

---

## 12. SUMMARY

### Execution Order (Correct — No "SAI CÁCH TÍCH HỢP")

```
WAVE 0:  Task 9.1 ║ Task 9.2  — Safe Point + Behavior Engine (parallel, no conflict)
WAVE 1:  Task 9.3             — Scaling Integration WITH Safe Guard (depends on 9.1 + 9.2)
WAVE 2:  Task 9.4             — Graceful Shutdown Enhancement (depends on 9.1 + 9.3)
```

### Key Differences from Failed Previous Attempt

| Aspect | Previous (Failed) | Current (Correct) |
|--------|-------------------|-------------------|
| Order | Engine → Integration → Safe Point (closed) | Safe Point ║ Engine → Integration (with guard) → Shutdown |
| Safe guard | Missing — added after integration | Built into integration from the start |
| `is_safe_to_control()` | Did not exist when scaling was integrated | Exists BEFORE scaling integration touches runtime |
| Worker states | Never implemented | Task 9.1 — implemented FIRST |
| `_apply_scale()` | Called unconditionally | Gated by `is_safe_to_control()` |
| Graceful shutdown | Not addressed | Task 9.4 — workers complete critical ops before stop |

### Principles

1. **Safe point FIRST** — worker execution states exist before ANY scaling integration
2. **Control layer reads, runtime applies** — behavior.evaluate() returns decisions, runtime gates execution
3. **Scaling ONLY at safe points** — `is_safe_to_control()` is a mandatory gate
4. **Blueprint preserved** — FSM flow, execution order, outcomes unchanged
5. **Each task testable** — 1 PR, ≤200 lines, independent CI validation
