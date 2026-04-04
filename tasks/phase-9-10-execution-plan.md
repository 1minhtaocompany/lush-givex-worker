# Phase 9–10 — Spec Review & Execution Redesign

**Date:** 2026-04-04
**Status:** Analysis Complete — Ready for Implementation Planning
**Scope:** Review, audit, and implementation planning. No implementation code changes. Includes spec/documentation updates. No new features.

---

## 0. MANDATORY CONTEXT — PR HISTORY & "SAI CÁCH TÍCH HỢP"

### 0.1 PR Merge History (Chronological)

| # | PR | Status | Content |
|---|---|--------|---------|
| 1 | Phase 9: Scope PR to Task 1 only — revert premature runtime integration | ✅ Merged | Rollback of incorrect early integration attempt |
| 2 | Phase 9: Behavior decision engine for scaling intelligence | ✅ Merged | Task 1 — pure logic `modules/behavior/main.py` |
| 3 | Integrate behavior decision engine into runtime scaling loop | ✅ Merged | Task 2 — connected `behavior.evaluate()` into `_runtime_loop` |
| 4 | Phase 9 Task 1: Safe Point Architecture — worker-level state model | ❌ **CLOSED** | Task 9.3 — attempted but NOT merged |

### 0.2 Root Cause: Wrong Execution Order

The integration was done **out of order**:

```
WHAT HAPPENED (wrong):                    WHAT SHOULD HAVE HAPPENED (correct):
──────────────────────────                ─────────────────────────────────────
1. Behavior Engine (pure)    ✅ OK        1. Behavior Engine (pure)    ✅ OK
2. Scaling Integration       ⚠️ PREMATURE  2. Safe Point Architecture   ← SHOULD BE FIRST
3. Safe Point Architecture   ❌ CLOSED     3. Scaling Integration       ← ONLY after safe points
```

**Consequence:** The scaling loop (`_runtime_loop`) currently makes SCALE_UP/SCALE_DOWN decisions and calls `_apply_scale()` → `start_worker()`/`stop_worker()` **without checking whether workers are in safe states**. This means:
- Workers can be killed mid-payment-flow
- New workers can be started while existing workers are in CRITICAL_SECTION
- No guard prevents scaling during VBV/3DS handling or API waits

### 0.3 The 5 "SAI CÁCH TÍCH HỢP" Problems

| # | Problem | Description | Blueprint Impact |
|---|---------|-------------|-----------------|
| 1 | **CONTROL vs EXECUTION CONFLICT** | Phase 9 control layer (scaling) can interfere with Blueprint execution flow (FSM payment). Control can act at wrong timing. | Scaling during payment → broken checkout flow |
| 2 | **MISSING SAFE POINT MODEL** | Runtime has no safe point concept. Scaling decisions execute immediately regardless of worker state. | Workers killed during VBV/3DS → lost session |
| 3 | **NO CRITICAL_SECTION PROTECTION** | No guard protects VBV, payment submit, or API wait from being interrupted by scaling. | Payment submit interrupted → SessionFlaggedError |
| 4 | **LAYER VIOLATION** | Control layer (behavior/scaling) directly manipulates execution layer without respecting execution boundaries. | Architecture principle violated |
| 5 | **EXECUTION ORDER WRONG** | Scaling integration was merged BEFORE safe point architecture. Safe point PR was closed, not merged. | System operates without safety boundaries |

---

## 1. ANALYSIS SUMMARY

### 1.1 What Was Reviewed

| Component | Location | Phase | Status |
|-----------|----------|-------|--------|
| Behavior Decision Engine | `modules/behavior/main.py` | Phase 9 Task 1 | ✅ Implemented — KEEP |
| Scaling Execution Layer | `integration/runtime.py` | Phase 9 Task 2 | ⚠️ Implemented — NEEDS ADJUSTMENT |
| Safe Point Architecture | (not in codebase) | Phase 9 Task 3 | ❌ CLOSED — MUST BE IMPLEMENTED |
| Behavior Layer Design | SPEC-6 §Phase 10 | Phase 10 | 📋 Designed only |
| Blueprint (Master) | `spec/blueprint.md` | Reference | ✅ Locked |
| FSM Module | `modules/fsm/main.py` | Core | ✅ Implemented |
| Worker Lifecycle | `integration/runtime.py` | Core | ✅ Implemented |

### 1.2 Current Test Baseline

- **386 tests passing** (340 baseline + 33 behavior + 13 scaling execution)
- CI fully green
- No regressions

---

## 2. PHASE 9 REVIEW — Behavior & Scaling Intelligence

### 2.1 What Is Correct (Đúng Spec)

| Component | Assessment | Evidence |
|-----------|-----------|----------|
| `behavior.evaluate()` pure logic | ✅ Correct | No cross-module imports, thread-safe via `_lock` |
| Decision rules (Rules 0–5) | ✅ Correct | Match spec exactly: cooldown, error_rate, restarts, success_drop, healthy, min_scale |
| Output actions (SCALE_UP/DOWN/HOLD) | ✅ Correct | Match spec contract |
| Cooldown guard (30s) | ✅ Correct | `_in_cooldown()` with `COOLDOWN_SECONDS = 30` |
| Decision history (bounded 100) | ✅ Correct | `_decision_history[:] = _decision_history[-100:]` |
| Scaling execution routing | ✅ Correct | `_runtime_loop` routes decisions to `rollout.try_scale_up()` / `force_rollback()` |
| Consecutive rollback tracking | ✅ Correct | Incremented on rollback, cleared only on `scaled_up` |
| Module isolation | ✅ Correct | `integration/` imports from `modules/` (allowed by architecture) |
| Lifecycle preservation | ✅ Correct | INIT/RUNNING/STOPPING/STOPPED unchanged |

### 2.2 What Is Missing (Sai Cách Tích Hợp)

| Issue | Spec Reference | Current State | Impact |
|-------|---------------|---------------|--------|
| **No Worker State Machine** | Phase 10 §10.3 references "CRITICAL_SECTION (defined in Phase 9)" | Runtime only tracks lifecycle states (INIT/RUNNING/STOPPING/STOPPED), not worker-level execution states | Phase 10 cannot determine when a worker is in a critical section vs. safe zone |
| **No Safe Point Architecture** | Phase 10 §10.4 references "SAFE_POINT" and §10.8 "Phase 9 alignment" | No SAFE_POINT/SAFE_ZONE concept in current runtime | Phase 10 behavior wrapper has no safe/unsafe boundary to operate within |
| **No `modules/delay/` module** | Phase 10 §Constraints: "uses existing modules/delay/" | Module directory does not exist in current codebase | Phase 10 cannot "use existing" delay module — it must be created first |
| **Naming Confusion** | Phase 9 = "Behavior Decision Engine", Phase 10 = "Behavior Layer" | Both use "behavior" terminology for different purposes | Implementors may conflate scaling behavior (Phase 9) with execution behavior (Phase 10) |

### 2.3 Phase 9 Verdict — KEEP vs ADJUST

#### ✅ KEEP (No changes needed)

| Component | Reason |
|-----------|--------|
| `modules/behavior/main.py` (entire file) | Pure decision logic. No integration concerns. Thread-safe. Correct rules. |
| `behavior.evaluate()` contract | Input/output contract is sound: `(metrics, step, max) → (action, reasons)` |
| Decision rules 0–5 | Correctly implement spec: cooldown, error_rate, restarts, success_drop, healthy, min_scale |
| `get_decision_history()`, `get_status()`, `reset()` | Supporting APIs are clean and well-tested |

#### ⚠️ NEEDS ADJUSTMENT (Integration layer)

| Component | Problem | Required Fix |
|-----------|---------|-------------|
| `_runtime_loop()` scaling execution | Calls `_apply_scale()` immediately after `behavior.evaluate()` without checking worker execution states | **MUST** check `is_safe_to_control()` before applying scaling decisions |
| `_apply_scale()` → `stop_worker()` | Stops workers without verifying they are in a safe state (IDLE or SAFE_POINT) | **MUST** only stop workers that are in safe states; defer others |
| `_apply_scale()` → `start_worker()` | Starts workers unconditionally | Lower risk but should respect system-wide safe state |

**Critical insight:** The behavior decision engine (Task 1) is **correct and should be kept unchanged**. The integration (Task 2) is **functionally correct but architecturally premature** — it was merged before the safe point model that should have constrained its execution. The fix is NOT to rewrite the integration but to **add the missing safe point guard** that prevents scaling from executing at unsafe times.

#### ❌ MUST BE IMPLEMENTED (Missing prerequisite)

| Component | Status | Why It's Needed |
|-----------|--------|-----------------|
| Safe Point Architecture | PR was CLOSED | Without worker execution states, the control layer cannot know when it's safe to scale |
| Worker state model (IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT) | Not in codebase | Phase 10 §10.3, §10.4, §10.8 all depend on this |
| `is_safe_to_control()` guard | Not in codebase | `_runtime_loop` must call this before `_apply_scale()` |

---

## 3. PHASE 10 REVIEW — Behavior Layer (Blueprint-safe)

### 3.1 What Is Correct (Đúng Spec)

| Component | Assessment | Evidence |
|-----------|-----------|----------|
| Architecture principle (wrapper only) | ✅ Correct | §10.1: "worker_fn → wrap(task_fn)" — no orchestration changes |
| SAFE_ZONE vs CRITICAL_SECTION split | ✅ Correct design | §10.3, §10.4: clear boundary between delay-permitted and delay-forbidden zones |
| NO-DELAY zones | ✅ Correct | §10.5: payment submit, watchdog, network wait, VBV, page reload |
| Non-interference rule | ✅ Correct | §10.7: no break timing, no disrupt FSM, no side-effects, no alter order, no change outcome |
| Phase 9 alignment constraint | ✅ Correct intent | §10.8: respect SAFE_POINT and CRITICAL_SECTION |
| Blueprint delay mappings | ✅ Correct | §10.6 maps to Blueprint §4 (CDP typing 4x4), §4 (bounding box), §5 (hesitation) |

### 3.2 What Is Problematic (Sai Cách Tích Hợp)

#### Problem 1: CRITICAL_SECTION Dependency on Nonexistent Infrastructure

**Spec says (§10.3):**
> CRITICAL_SECTION (defined in Phase 9):
> - Payment submit (Complete Purchase execution)
> - VBV/3DS handling (iframe interaction + wait)
> - API wait (CDP Network.responseReceived pending)

**Reality:** Phase 9 does NOT define CRITICAL_SECTION as a worker execution state. Phase 9 only defines scaling logic (SCALE_UP/DOWN/HOLD). There is no mechanism in the current codebase for a worker to declare "I am now in a critical section."

**Impact:** Phase 10 behavior wrapper cannot check `if current_state == CRITICAL_SECTION` because this state does not exist anywhere.

#### Problem 2: BehaviorState FSM vs Existing FSM Collision

**Spec says (§10.2):**
> BehaviorState MUST include: IDLE, FILLING_FORM, PAYMENT, VBV, POST_ACTION

**Existing FSM (modules/fsm/main.py):**
> ALLOWED_STATES = {"ui_lock", "success", "vbv_3ds", "declined"}

**Conflict:** These are two completely different state machines serving different purposes:
- Existing FSM = **outcome states** (what happened after an action)
- BehaviorState = **execution context** (what the worker is doing right now)

The spec does not clarify:
- Whether BehaviorState is a new FSM or extends the existing one
- How BehaviorState maps to the existing FSM transitions
- Whether both FSMs run in parallel or if one replaces the other

**Impact:** Implementing BehaviorState without resolving this will create two competing state machines with no clear relationship.

#### Problem 3: Delay Module Assumed to Exist

**Spec says (§Constraints):**
> KHÔNG thêm module mới (uses existing modules/delay/)

**Reality:** `modules/delay/` does not exist in the current codebase. There are no files matching `*delay*` in the modules directory.

**Impact:** The constraint "uses existing modules/delay/" cannot be satisfied. The module must be created, which contradicts the "no new module" constraint. This needs clarification: either the delay module must be created as a prerequisite (Phase 9 gap), or the constraint wording needs correction.

#### Problem 4: Worker Wrapper Injection Point Unclear

**Spec says (§10.1):**
> Behavior wrapper ONLY at worker execution layer: worker_fn → wrap(task_fn)

**Current runtime (_worker_fn in integration/runtime.py):**
```python
def _worker_fn(worker_id, task_fn):
    ...
    while True:
        task_fn(worker_id)  # Direct call, no wrapper
```

**Unclear:** The spec doesn't specify:
- Is the wrapper applied in `start_worker()` before passing to `_worker_fn`?
- Is the wrapper applied inside `_worker_fn` around the `task_fn(worker_id)` call?
- Does the wrapper receive the worker_id for per-worker seed generation?

**Impact:** Different injection points create different integration patterns and different test strategies.

#### Problem 5: Blueprint Timing Constraints Not Bounded

The Blueprint defines specific timings that the delay module must respect:

| Blueprint Action | Timing | Blueprint §Reference |
|-----------------|--------|---------------------|
| Typing 4x4 (card number) | 0.6–1.8s hesitation per 4-digit group | §4: CDP gõ phím, quy tắc 4x4 |
| Bounding Box Click | Offset (x±15, y±5) — no significant time delay | §4: Bounding Box Click |
| Pre-purchase hesitation | 3–5s hover/scroll near "Complete Purchase" | §5: Hesitation |
| VBV iframe wait | 8–12s (random) | §6: Ngã rẽ 3 |
| Watchdog timeout | 10s hard deadline | §5: Total Watchdog |
| Stagger start | 12–25s between worker launches | §1: Stagger Start |

**Problem:** Phase 10 §10.6 mentions these categories (typing, click, thinking) but does not bind them to specific Blueprint timing values. The delay module must be implemented with these exact Blueprint ranges, but the mapping is implicit, not explicit.

**Impact:** An implementor reading only Phase 10 spec without cross-referencing the Blueprint may implement different timing ranges.

---

## 4. INTEGRATION CONFLICTS WITH BLUEPRINT

### 4.1 Conflict: Delay Must Not Exceed Watchdog Timeout

- Blueprint §5: Watchdog timeout = 10s
- Phase 10 §10.6: "MUST NOT affect watchdog timeout or system-level deadlines"
- **Risk:** If typing delay (0.6–1.8s × 4 groups) + hesitation (3–5s) accumulates, total delay could approach or exceed watchdog window
- **Resolution needed:** Total accumulated delay per cycle step MUST be bounded to leave sufficient headroom for network operations within watchdog timeout

### 4.2 Conflict: Stagger Start vs Behavior Delay

- Blueprint §1: Stagger start = random.uniform(12, 25)s between worker launches
- Phase 10 behavior delay is per-action within a worker cycle
- **Clarification needed:** Stagger start is a SEPARATE mechanism from behavioral delay. Phase 10 behavior delay operates WITHIN a cycle, not between worker launches. These must not interfere.

### 4.3 Conflict: VBV Wait — Behavioral vs Operational

- Blueprint §6 (Ngã rẽ 3): VBV wait = 8–12s for iframe to load
- Phase 10 §10.5: VBV iframe load/interaction is in NO-DELAY zone
- **Clarification:** The 8–12s VBV wait is an OPERATIONAL wait (waiting for iframe to load), NOT a behavioral delay. Phase 10 correctly marks VBV as NO-DELAY, but implementors must not confuse the Blueprint's operational wait with behavioral delay injection.

### 4.4 Non-Conflict: Seed-Based Determinism

- Blueprint §2: "Gắn Seed Hành Vi" — each worker gets a personality seed
- Phase 10 §10.6: "Deterministic: Seed-based random (Blueprint §2)"
- **Status:** Aligned. No conflict. Seed determines typing speed, typo rate, hesitation patterns.

---

## 5. CORRECT EXECUTION ORDER

### 5.1 Dependency Graph

```
Phase 9 (Existing — KEEP)   Phase 9 (Gap — CRITICAL)     Phase 10
┌─────────────────┐         ┌─────────────────────────┐
│ Task 9.1        │         │ Task 9.3                │
│ Behavior Engine │ ✅ KEEP  │ Safe Point Architecture │ ◄── MUST BE FIRST
│ (Pure Logic)    │         │ + Safe Guard in runtime  │
└─────────────────┘         │ (CRITICAL_SECTION,      │
                            │  SAFE_POINT, is_safe_to_ │
┌─────────────────┐         │  control() guard in     │
│ Task 9.2        │         │  _runtime_loop)         │
│ Scaling Exec    │ ✅ KEEP  └────────┬────────────────┘
│ (Integration)   │ + PATCH           │
└─────────────────┘                   │
        ▲                             │
        │ (Task 9.3 patches           │
        │  _runtime_loop to           ├─────────────────────────┐
        │  check is_safe_to_          │                         │
        │  control() before           │                         │
        │  _apply_scale())            │                         │
                            ┌─────────▼──────────┐  ┌──────────▼─────────┐
                            │ Task 10.1          │  │ Task 10.2          │
                            │ Delay Module       │  │ BehaviorState      │
                            │ (Pure Logic)       │  │ Context Definition │
                            └─────────┬──────────┘  └──────────┬─────────┘
                                      │                        │
                                      └────────────┬───────────┘
                                                   │
                                         ┌─────────▼──────────┐
                                         │ Task 10.3          │
                                         │ Behavior Wrapper   │
                                         │ (Integration)      │
                                         └─────────┬──────────┘
                                                   │
                                         ┌─────────▼──────────┐
                                         │ Task 10.4          │
                                         │ Guard Validation   │
                                         │ (NO-DELAY Zones)   │
                                         └────────────────────┘
```

### 5.2 Execution Sequence (Strict Order — No Skipping)

```
STEP 1: Task 9.3  — Safe Point Architecture + Safe Guard in _runtime_loop
                    (MANDATORY FIRST — fixes "SAI CÁCH TÍCH HỢP")
                    This task BOTH adds worker states AND patches _runtime_loop
                    to call is_safe_to_control() before _apply_scale().

STEP 2: Task 10.1 — Delay Module (pure logic, can parallel with 10.2)
STEP 2: Task 10.2 — BehaviorState Context (pure definition, can parallel with 10.1)

STEP 3: Task 10.3 — Behavior Wrapper (integration — depends on 9.3, 10.1, 10.2)

STEP 4: Task 10.4 — Guard Validation (depends on 10.3)
```

### 5.3 Why This Order Is Mandatory

1. **Task 9.3 MUST be first** because:
   - The current `_runtime_loop` calls `_apply_scale()` without any safe guard
   - Workers can be killed mid-payment-flow RIGHT NOW
   - Until `is_safe_to_control()` is added, every scaling decision is a potential Blueprint violation
   - Phase 10 tasks (10.1, 10.2, 10.3) all depend on CRITICAL_SECTION and SAFE_POINT existing

2. **Tasks 10.1 and 10.2 can be parallel** because:
   - Both are pure definitions with no integration dependencies
   - 10.1 (delay module) is a new `modules/delay/` file — no existing file conflicts
   - 10.2 (BehaviorState) extends `modules/common/types.py` — different file from 10.1

3. **Task 10.3 MUST wait for all of Wave 1+2** because:
   - It integrates delay module (10.1) with BehaviorState context (10.2)
   - It injects the wrapper into `_worker_fn` which must respect safe point states (9.3)

4. **Task 10.4 is final validation** — tests the complete integrated system

---

## 6. TASK BREAKDOWN

### TASK 9.3 — Safe Point Architecture + Runtime Safe Guard

**Objective:**
Add worker-level execution state tracking to `integration/runtime.py` AND patch the existing `_runtime_loop` so that scaling decisions only execute when workers are in safe states. This fixes the "SAI CÁCH TÍCH HỢP" by adding the missing safety layer between the control layer (scaling) and the execution layer (worker payment flow).

**Scope:**
- File: `integration/runtime.py`
- **Part A — Worker State Model:**
  - Add: `ALLOWED_WORKER_STATES = {"IDLE", "IN_CYCLE", "CRITICAL_SECTION", "SAFE_POINT"}`
  - Add: `_worker_states: dict` — maps worker_id → current execution state
  - Add: `set_worker_state(worker_id, state)` — validated state transitions
  - Add: `get_worker_state(worker_id)` → current state
  - Add: `get_all_worker_states()` → snapshot of all worker states
  - Add: `is_safe_to_control()` → True only when all workers are IDLE or SAFE_POINT
  - Add: `_transition_worker_state_locked()` for internal validated transitions
  - Modify: `start_worker()` to initialize worker state at registration (IDLE)
  - Modify: `_worker_fn()` to transition through states during execution
  - Modify: cleanup (finally blocks, stop_worker) to remove worker state on exit

- **Part B — Safe Guard in _runtime_loop (fixes "SAI CÁCH TÍCH HỢP"):**
  - Patch `_runtime_loop`: after `behavior.evaluate()` returns a scaling decision, call `is_safe_to_control()` BEFORE calling `_apply_scale()`
  - If `is_safe_to_control()` returns False → log "scaling_deferred" and SKIP this tick (keep current workers, do not scale)
  - If `is_safe_to_control()` returns True → proceed with `_apply_scale()` as before
  - This ensures: **scaling NEVER happens while any worker is in CRITICAL_SECTION or IN_CYCLE**

**Constraints:**
- NO changes to `behavior.evaluate()` logic (decision engine unchanged)
- NO changes to `rollout.try_scale_up()`/`force_rollback()` (rollout module unchanged)
- NO changes to lifecycle states (INIT/RUNNING/STOPPING/STOPPED unchanged)
- Worker states are SEPARATE from lifecycle states
- Thread-safe via existing `_lock`
- `_apply_scale()` internal logic unchanged — only gated by new guard

**Valid Worker State Transitions:**
```
IDLE → IN_CYCLE            (worker starts executing task_fn)
IN_CYCLE → CRITICAL_SECTION (worker enters payment/VBV/API wait)
IN_CYCLE → SAFE_POINT       (worker at safe point between actions)
CRITICAL_SECTION → IN_CYCLE (worker exits critical section)
SAFE_POINT → IN_CYCLE       (worker resumes from safe point)
IN_CYCLE → IDLE             (worker completes one cycle iteration)
```

**_runtime_loop patch (pseudocode):**
```python
# EXISTING (in _runtime_loop, after behavior.evaluate):
decision, reasons = behavior.evaluate(metrics, step, max)
# ... route decision to target ...
_apply_scale(target, task_fn)  # ← CURRENTLY UNCONDITIONAL

# PATCHED:
decision, reasons = behavior.evaluate(metrics, step, max)
# ... route decision to target ...
if target != current_count:     # Only check when scaling actually changes
    if not is_safe_to_control():
        _log_event("runtime", "deferred", "scaling_deferred", {...})
        continue                 # Skip this tick, retry next interval
_apply_scale(target, task_fn)   # ← NOW GATED BY SAFE GUARD
```

**Completion Criteria:**
- [ ] `ALLOWED_WORKER_STATES` defined with strict transition rules
- [ ] `set_worker_state()` raises `ValueError` for invalid transitions
- [ ] `is_safe_to_control()` returns `True` only when all workers IDLE/SAFE_POINT
- [ ] `_worker_fn()` transitions through states: IDLE → IN_CYCLE → (CRITICAL_SECTION ↔ SAFE_POINT) → IDLE
- [ ] Missing worker state treated as unsafe by `is_safe_to_control()`
- [ ] `_runtime_loop` checks `is_safe_to_control()` before `_apply_scale()` when scaling changes
- [ ] Scaling is deferred (not lost) when workers are in unsafe states
- [ ] Tests: state transitions, invalid transition rejection, is_safe_to_control logic, scaling deferral
- [ ] CI pass, no regressions to existing 386 tests
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** None (builds on existing runtime infrastructure)

---

### TASK 10.1 — Behavioral Delay Module (Pure Logic)

**Objective:**
Create `modules/delay/main.py` with a `compute_delay(action_type, seed, context)` function that returns bounded delay values based on Blueprint timing specifications.

**Scope:**
- File: `modules/delay/main.py` (NEW — this fills the gap referenced by Phase 10 §Constraints)
- Pure function: `compute_delay(action_type, seed, context) → (delay_seconds, pattern_name)`
- Action types and Blueprint-aligned delay ranges:
  - `typing`: per-key delay + 0.6–1.8s hesitation per 4-digit group (Blueprint §4: 4x4 rule)
  - `click`: minimal delay (bounding box offset is spatial, not temporal) (Blueprint §4)
  - `thinking`: 3–5s hesitation before critical action (Blueprint §5)
- Seed-based determinism: same seed → same delay sequence (Blueprint §2)
- Thread-safe via `threading.Lock`
- NO cross-module imports (zero external dependencies)

**Constraints:**
- NO integration with runtime (pure module)
- Delay values MUST NOT exceed watchdog timeout headroom (max single delay call < 5s; `compute_delay('typing', ...)` returns per-4-digit-group delay, not per-card total)
- Deterministic: seed-based random.Random instance (not global random state)
- Bounded: all delay values have min/max limits

**Completion Criteria:**
- [ ] `compute_delay()` returns valid delay for all action types
- [ ] Delay ranges match Blueprint specifications
- [ ] Seed determinism: same (action_type, seed, context) → same output
- [ ] Thread-safe: concurrent calls don't interfere
- [ ] No cross-module imports
- [ ] Tests: each action type, seed determinism, boundary values, thread safety
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** Task 9.3 (execution follows dependency matrix; module itself is pure with no runtime imports)

---

### TASK 10.2 — BehaviorState Context Definition

**Objective:**
Define the `BehaviorState` context enumeration that describes what a worker is currently doing within a cycle. This maps Phase 10 §10.2 FSM Context to a concrete type definition.

**Scope:**
- File: `modules/common/types.py` (extend existing types module)
- Add: `BehaviorState` — either a set of string constants or a simple class
- States: `IDLE`, `FILLING_FORM`, `PAYMENT`, `VBV`, `POST_ACTION`
- Add: Classification helpers:
  - `CRITICAL_STATES` = {`PAYMENT`, `VBV`, `POST_ACTION`} — NO delay permitted
  - `SAFE_STATES` = {`IDLE`, `FILLING_FORM`} — delay permitted
  - `is_safe_for_delay(state) → bool`

**Relationship to existing FSM:**
- BehaviorState is SEPARATE from existing FSM states (ui_lock, success, vbv_3ds, declined)
- Existing FSM = **outcome classification** (what happened)
- BehaviorState = **execution context** (what the worker is doing now)
- They operate in parallel — a worker can be in BehaviorState.PAYMENT while FSM has no active state yet
- No modification to existing `modules/fsm/main.py`

**Constraints:**
- NO changes to existing FSM module
- NO cross-module imports beyond `modules/common/`
- Definition only — no integration with runtime

**Completion Criteria:**
- [ ] BehaviorState constants defined in `modules/common/types.py`
- [ ] CRITICAL_STATES and SAFE_STATES clearly classified
- [ ] `is_safe_for_delay()` function works correctly
- [ ] No changes to existing FSM module
- [ ] Tests: state classification, is_safe_for_delay for all states
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:** Task 9.3 (definition only, no runtime integration)

---

### TASK 10.3 — Behavior Wrapper (Integration Layer)

**Objective:**
Create the behavior wrapper that injects delays at the worker execution layer, respecting CRITICAL_SECTION and SAFE_ZONE boundaries.

**Scope:**
- File: `integration/runtime.py` (extend worker execution path)
- Add: `_wrap_with_behavior(task_fn, worker_id, seed)` → wrapped function
- The wrapper:
  1. Before `task_fn(worker_id)` call: check BehaviorState
  2. If in SAFE_STATE: compute and inject delay via `delay.compute_delay()`
  3. If in CRITICAL_STATE: zero delay, proceed immediately
  4. After `task_fn(worker_id)` call: no modification
- Integration point: Applied in `start_worker()` or `_worker_fn()`
- Worker seed: derived from worker_id for deterministic behavior

**Constraints:**
- Wrapper pattern ONLY — no changes to `_runtime_loop` or scaling logic
- NO side effects outside behavior layer
- NO alteration of execution order
- NO change to success/failure outcome
- Delay ONLY in SAFE_ZONE (Task 10.2 classification)
- Zero delay in CRITICAL_SECTION (Task 9.3 worker states)
- Deterministic via seed (Task 10.1 delay module)

**Completion Criteria:**
- [ ] Wrapper correctly injects delay during SAFE_ZONE operations
- [ ] Zero delay during CRITICAL_SECTION operations
- [ ] Worker execution order unchanged
- [ ] Success/failure outcomes unchanged
- [ ] Scaling logic (Phase 9) unaffected
- [ ] Lifecycle states unaffected
- [ ] Tests: delay injection in safe zone, no delay in critical section, non-interference with scaling
- [ ] CI pass, no regressions
- [ ] 1 PR, ≤200 lines (excluding tests)

**Dependencies:**
- Task 9.3 (worker execution states — determines CRITICAL_SECTION boundaries)
- Task 10.1 (delay module — provides compute_delay function)
- Task 10.2 (BehaviorState — provides state classification)

---

### TASK 10.4 — NO-DELAY Zone Guard Validation

**Objective:**
Add explicit guard tests and runtime checks that validate the NO-DELAY zones defined in Phase 10 §10.5 are never violated.

**Scope:**
- File: tests (new test file for guard validation)
- Validate that delay is NEVER injected during:
  - Payment submit (Complete Purchase click event)
  - Watchdog timeout checks
  - Network wait (CDP Network.responseReceived)
  - VBV iframe load/interaction
  - Page reload operations
- Validate that accumulated delay within a single step never exceeds safe threshold

**Constraints:**
- Test-only task — no production code changes
- Tests must verify the contract established by Tasks 9.3, 10.1, 10.2, 10.3

**Completion Criteria:**
- [ ] Test coverage for every NO-DELAY zone listed in Phase 10 §10.5
- [ ] Accumulated delay boundary test (total delay < watchdog headroom)
- [ ] Non-interference test (delay doesn't change task outcome)
- [ ] CI pass, all tests green
- [ ] 1 PR

**Dependencies:**
- Task 10.3 (behavior wrapper must be implemented to test against)

---

## 7. DEPENDENCY MATRIX

| Task | Depends On | Can Parallel With | Must Complete Before |
|------|-----------|-------------------|---------------------|
| **9.3** Safe Point + Safe Guard | — (none) | — (MUST be first) | 10.1, 10.2, 10.3, 10.4 |
| **10.1** Delay Module | 9.3 | 10.2 | 10.3 |
| **10.2** BehaviorState | 9.3 | 10.1 | 10.3 |
| **10.3** Behavior Wrapper | 9.3, 10.1, 10.2 | — | 10.4 |
| **10.4** Guard Validation | 10.3 | — | — (final) |

### Parallelization Opportunities

```
WAVE 0 (MANDATORY FIRST): Task 9.3 (Safe Point + Safe Guard)
                               │
                               │  ← Fixes "SAI CÁCH TÍCH HỢP"
                               │  ← Scaling now gated by is_safe_to_control()
                               │
WAVE 1 (parallel):         Task 10.1  ║  Task 10.2
                               │              │
                               └──────┬───────┘
                                      │
WAVE 2 (sequential):          Task 10.3
                                      │
WAVE 3 (sequential):          Task 10.4
```

**CRITICAL CHANGE vs previous plan:** Task 9.3 is now Wave 0 (strictly first, NOT parallel with 10.1/10.2). This is because:
1. Tasks 10.1 and 10.2 depend on CRITICAL_SECTION/SAFE_POINT concepts being defined (by 9.3)
2. The current runtime is operating without safety boundaries — this must be fixed before ANY new features

---

## 8. RISK ASSESSMENT

### 8.0 CRITICAL Risk: Scaling Without Safe Guard (CURRENT STATE)

**Risk:** The `_runtime_loop` currently calls `_apply_scale()` unconditionally after `behavior.evaluate()`. This means `stop_worker()` can be called on a worker that is in the middle of a payment submit, VBV/3DS handling, or API wait. This is the core "SAI CÁCH TÍCH HỢP" — the control layer interferes with the execution layer at unsafe times.

**Current Impact:**
- Workers can be killed mid-payment → broken checkout, lost session
- Workers can be killed during VBV/3DS → iframe stuck, session flagged
- Workers can be killed during API wait → timeout, SessionFlaggedError
- New workers can start while system is in an inconsistent state

**Mitigation:** Task 9.3 MUST be implemented first. It adds `is_safe_to_control()` as a gate in `_runtime_loop` before `_apply_scale()`. Until this is done, no other Phase 10 work should proceed.

### 8.1 High Risk: BehaviorState ↔ Existing FSM Confusion

**Risk:** Implementors may attempt to add BehaviorState to `modules/fsm/main.py` instead of keeping it separate.

**Mitigation:** Task 10.2 explicitly states BehaviorState goes in `modules/common/types.py`. The existing FSM module (`modules/fsm/main.py`) MUST NOT be modified.

### 8.2 Medium Risk: Delay Accumulation Exceeding Watchdog Budget

**Risk:** Multiple behavioral delays within a single step (typing + thinking) could accumulate to near or above the 10s watchdog timeout.

**Mitigation:** Task 10.1 must bound individual delays AND Task 10.4 must validate total accumulated delay stays within safe threshold (recommend max 5s total behavioral delay per step to leave 5s for actual operations).

### 8.3 Medium Risk: Worker State Threading Complexity

**Risk:** Adding worker execution states (Task 9.3) introduces additional shared state that must be correctly synchronized.

**Mitigation:** Use existing `_lock` in runtime.py. Worker states follow same pattern as worker registration. Validate transitions prevent invalid state combinations.

### 8.4 Low Risk: Naming Confusion (Behavior × 2)

**Risk:** Phase 9 "Behavior Decision Engine" and Phase 10 "Behavior Layer" use similar terminology.

**Mitigation:** Documentation clarity. Phase 9 behavior = scaling decisions (SCALE_UP/DOWN/HOLD). Phase 10 behavior = execution simulation (typing delay, click offset, hesitation). Different layers, different concerns.

---

## 9. VALIDATION CHECKLIST (Per Task)

Every task PR must satisfy:

- [ ] CI pipeline passes (all existing tests + new tests)
- [ ] No code-quality warnings introduced
- [ ] No cross-module import violations
- [ ] PR scope ≤ 200 lines (excluding tests)
- [ ] Single module/layer touched per PR
- [ ] Blueprint timing constraints respected (where applicable)
- [ ] Phase 9 scaling logic unaffected (verify `behavior.evaluate()` routing unchanged)
- [ ] Lifecycle states (INIT/RUNNING/STOPPING/STOPPED) unchanged
- [ ] Thread safety verified (concurrent test or reasoning)

---

## 10. SUMMARY

### Root Cause: "SAI CÁCH TÍCH HỢP"

The scaling integration (Task 9.2) was merged BEFORE the safe point architecture (Task 9.3). Task 9.3's PR was subsequently closed without merge. As a result, the runtime's `_runtime_loop` makes scaling decisions and applies them immediately — without any guard to prevent scaling during critical operations (payment, VBV, API waits).

### What To KEEP (No Changes)

| Component | File | Reason |
|-----------|------|--------|
| Behavior Decision Engine | `modules/behavior/main.py` | Pure logic, correct rules, well-tested, no integration issues |
| Decision routing in `_runtime_loop` | `integration/runtime.py` lines 146-163 | Logic for routing SCALE_UP/DOWN/HOLD to rollout is correct |
| Consecutive rollback tracking | `integration/runtime.py` | Correct safety mechanism |
| All existing tests (386) | `tests/` | No regressions allowed |

### What NEEDS ADJUSTMENT

| Component | File | Required Change |
|-----------|------|----------------|
| `_runtime_loop` scaling execution | `integration/runtime.py` | Add `is_safe_to_control()` guard BEFORE `_apply_scale()` |
| Worker lifecycle tracking | `integration/runtime.py` | Add worker execution states (IDLE/IN_CYCLE/CRITICAL_SECTION/SAFE_POINT) |

### Problems Identified (Updated with PR History Context)

1. **"SAI CÁCH TÍCH HỢP" — Wrong execution order:** Scaling integration merged before safe point architecture. Control layer operates without execution boundaries.

2. **No CRITICAL_SECTION protection:** Workers can be killed during payment submit, VBV/3DS handling, or API waits. No guard prevents this.

3. **No SAFE_POINT model:** Runtime cannot determine when it's safe to scale. `_apply_scale()` executes unconditionally.

4. **Phase 10 depends on nonexistent infrastructure:** CRITICAL_SECTION, SAFE_POINT, `modules/delay/`, BehaviorState — all referenced by Phase 10 spec but not implemented.

5. **Layer violation:** Control layer (scaling) directly manipulates execution layer without respecting execution flow boundaries defined in Blueprint.

### Redesigned Execution Order (Corrected)

```
WAVE 0:  Task 9.3  — Safe Point Architecture + Safe Guard (MANDATORY FIRST)
WAVE 1:  Task 10.1 ║ Task 10.2 — Delay Module + BehaviorState (parallel)
WAVE 2:  Task 10.3 — Behavior Wrapper (integration)
WAVE 3:  Task 10.4 — NO-DELAY Zone Guard Validation
```

### Key Principles

- **Safe point FIRST** — no other work until control layer respects execution boundaries
- Control layer (Phase 9) only acts at safe points — never during critical operations
- Execution layer (Phase 10) only injects delays at safe zones — never during critical sections
- Blueprint timing is the source of truth for delay bounds
- Behavior decision engine (`modules/behavior/main.py`) remains completely untouched
- Each task independently testable and deployable via 1 PR ≤ 200 lines

---

## 11. PHASE 9 MERGED PR AUDIT REPORT

**Date:** 2026-04-04
**Scope:** Audit all 3 merged Phase 9 PRs for Spec compliance, Blueprint compliance, integration correctness, and system safety.

---

### 11.1 PR #1: "Phase 9: Scope PR to Task 1 only — revert premature runtime integration"

**Purpose:** Rollback a premature attempt to integrate behavior decision engine directly into runtime before proper scoping.

**Scope of Changes:**
- Reverted integration code from `integration/runtime.py`
- Restored runtime to pre-Phase-9 state
- Ensured behavior module remained separate

**Assessment:**

| Criterion | Result | Detail |
|-----------|--------|--------|
| Spec compliance | ✅ OK | Correctly enforced "1 PR = 1 task" scope rule (Guard 3.4) |
| Blueprint compliance | ✅ OK | No Blueprint timing affected — purely structural change |
| Integration correctness | ✅ OK | Clean revert; no residual artifacts |
| Layer integrity | ✅ OK | Restored proper separation between decision engine and runtime |
| Missing guard/constraint | ✅ N/A | Revert PR — no new functionality to guard |

**Classification: ✅ OK (keep as-is)**

**Impact:** Positive — this PR corrected a premature integration mistake. No ongoing risk.

---

### 11.2 PR #2: "Phase 9: Behavior decision engine for scaling intelligence"

**Purpose:** Implement `modules/behavior/main.py` — pure rule-based scaling decision engine.

**Scope of Changes:**
- New file: `modules/behavior/main.py`
- New file: `tests/test_behavior.py` (33 tests)
- Pure decision logic: `evaluate(metrics, step_index, max_step_index) → (action, reasons)`
- Actions: SCALE_UP, SCALE_DOWN, HOLD
- Decision rules 0–5 (cooldown, error_rate, restarts, success_drop, healthy, min_scale)
- Thread-safe via `threading.Lock`
- Zero cross-module imports

**Assessment:**

| Criterion | Result | Detail |
|-----------|--------|--------|
| Spec compliance | ✅ OK | Matches Phase 9 Task 1 spec exactly — all 6 decision rules implemented |
| Blueprint compliance | ✅ OK | Pure logic module — no direct Blueprint interaction |
| Integration correctness | ✅ OK | No integration code — pure module, zero external dependencies |
| Layer integrity | ✅ OK | `modules/behavior/` only — no integration layer changes |
| Thread safety | ✅ OK | All shared state guarded by `_lock` |
| Decision history | ✅ OK | Bounded to 100 entries (no memory leak) |
| Cooldown enforcement | ✅ OK | 30s minimum between decisions via `_in_cooldown()` |
| Test coverage | ✅ OK | 33 tests covering all rules, cooldown, history, thread safety, reset |
| Missing guard/constraint | ✅ N/A | Pure logic — no integration concerns |

**Classification: ✅ OK (keep as-is)**

**Impact:** Zero risk. This is correct, well-tested, and properly isolated. No changes needed.

---

### 11.3 PR #3: "Integrate behavior decision engine into runtime scaling loop"

**Purpose:** Connect `behavior.evaluate()` into `_runtime_loop` so scaling decisions are made automatically based on runtime metrics.

**Scope of Changes:**
- Modified: `integration/runtime.py` — `_runtime_loop()` now calls `behavior.evaluate()` each tick
- Decision routing: SCALE_UP → `rollout.try_scale_up()`, SCALE_DOWN → `rollout.force_rollback()`, HOLD → no change
- Added consecutive rollback tracking (increment on rollback, clear on scaled_up)
- Added `behavior.reset()` to `runtime.reset()`
- New file: `tests/test_scaling_execution.py` (13 tests)

**Assessment:**

| Criterion | Result | Detail |
|-----------|--------|--------|
| Spec compliance | ⚠️ NEEDS ADJUSTMENT | Spec Phase 10 §10.3 says "CRITICAL_SECTION (defined in Phase 9)" — but this PR does NOT define CRITICAL_SECTION. The scaling execution was merged without the prerequisite safe point architecture. |
| Blueprint compliance | ⚠️ NEEDS ADJUSTMENT | Blueprint defines critical timing windows (VBV 8-12s, payment submit, API wait). Scaling can currently interrupt these windows because there is no `is_safe_to_control()` guard. |
| Integration correctness | ⚠️ FUNCTIONALLY CORRECT, ARCHITECTURALLY PREMATURE | The decision routing logic (SCALE_UP/DOWN/HOLD → rollout calls) is correct. But `_apply_scale()` is called unconditionally — no check for worker execution state. |
| Layer integrity | ⚠️ VIOLATION | Control layer (scaling) directly manipulates execution layer (start/stop workers) without checking execution boundaries. Workers can be killed mid-payment. |
| Thread safety | ✅ OK | Uses existing `_lock` for shared state |
| Consecutive rollback tracking | ✅ OK | Correctly incremented/cleared; warning at threshold |
| Test coverage | ✅ OK | 13 tests covering routing, tracking, lifecycle, concurrency |

**Specific Issues Found:**

| # | Issue | Severity | Location | Description |
|---|-------|----------|----------|-------------|
| 1 | No safe guard before `_apply_scale()` | 🔴 CRITICAL | `_runtime_loop()` line 162 | `_apply_scale(target, task_fn)` called unconditionally after `behavior.evaluate()`. Should check `is_safe_to_control()` first. |
| 2 | `stop_worker()` during CRITICAL_SECTION | 🔴 CRITICAL | `_apply_scale()` → `stop_worker()` | When scaling down, workers are stopped without checking if they are in payment/VBV/API wait. |
| 3 | No worker execution states | 🟡 HIGH | `integration/runtime.py` | Only lifecycle states (INIT/RUNNING/STOPPING/STOPPED) exist. No IDLE/IN_CYCLE/CRITICAL_SECTION/SAFE_POINT. Workers cannot signal their execution context. |
| 4 | Execution order violation | 🟡 HIGH | PR merge sequence | This PR should have been merged AFTER safe point architecture, not before. |

**Classification: ⚠️ NEEDS ADJUSTMENT**

**Required Fix (Task 9.3):**
1. Add worker execution state model (IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT)
2. Patch `_runtime_loop()`: call `is_safe_to_control()` before `_apply_scale()` when target ≠ current
3. If unsafe: log "scaling_deferred", skip this tick, retry next interval
4. If safe: proceed with `_apply_scale()` as before

**What to KEEP from this PR:**
- ✅ `behavior.evaluate()` call in loop — correct
- ✅ Decision routing (SCALE_UP → try_scale_up, etc.) — correct
- ✅ Consecutive rollback tracking — correct
- ✅ `behavior.reset()` in `runtime.reset()` — correct

**What to ADD (not remove):**
- ❌ `is_safe_to_control()` guard before `_apply_scale()` — MISSING
- ❌ Worker execution state tracking — MISSING

---

### 11.4 OVERALL SYSTEM ASSESSMENT

| Question | Answer |
|----------|--------|
| Is the system currently safe? | ⚠️ **NO** — scaling can interrupt critical operations |
| What is the root cause? | Wrong execution order: scaling integrated before safe point architecture |
| Are existing merged components correct? | ✅ YES — behavior engine and decision routing logic are correct |
| What is missing? | Safe point architecture (worker states + `is_safe_to_control()` guard) |
| Is there data loss risk? | 🔴 YES — workers killed mid-payment can lose sessions |
| Is there Blueprint violation? | 🔴 YES — control layer can disrupt Blueprint execution timing |

### 11.5 AUDIT CONCLUSION

| PR | Classification | Action Required |
|----|---------------|----------------|
| PR #1 (Scope revert) | ✅ OK | None |
| PR #2 (Behavior engine) | ✅ OK | None |
| PR #3 (Scaling integration) | ⚠️ NEEDS ADJUSTMENT | Task 9.3: Add safe point guard |

**Summary:**

The behavior decision engine (PR #2) is **correct and safe** — pure logic with zero integration concerns.

The scaling integration (PR #3) is **functionally correct but architecturally premature**. The decision routing works correctly, but the missing `is_safe_to_control()` guard means scaling actions execute without checking worker execution state. This creates a window where workers can be killed during payment, VBV/3DS, or API waits — violating Blueprint execution timing requirements.

**The fix is NOT to revert PR #3.** The integration logic is sound. The fix is to implement Task 9.3 (Safe Point Architecture), which:
1. Adds worker execution states (IDLE, IN_CYCLE, CRITICAL_SECTION, SAFE_POINT)
2. Adds `is_safe_to_control()` guard in `_runtime_loop` before `_apply_scale()`
3. Defers scaling when workers are in unsafe states

Until Task 9.3 is implemented, the system operates without safety boundaries between the control layer and execution layer.
