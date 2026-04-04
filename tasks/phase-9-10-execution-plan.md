# Phase 9–10 — Spec Review & Execution Redesign

**Date:** 2026-04-04
**Status:** Analysis Complete — Ready for Implementation Planning
**Scope:** Review-only. No code changes. No spec changes. No new features.

---

## 1. ANALYSIS SUMMARY

### 1.1 What Was Reviewed

| Component | Location | Phase | Status |
|-----------|----------|-------|--------|
| Behavior Decision Engine | `modules/behavior/main.py` | Phase 9 Task 1 | ✅ Implemented |
| Scaling Execution Layer | `integration/runtime.py` | Phase 9 Task 2 | ✅ Implemented |
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

### 2.3 Phase 9 Verdict

Phase 9 implementation is **correct within its own scope**. The behavior decision engine and scaling execution layer work as specified. However, Phase 9 **did not establish the prerequisite infrastructure** that Phase 10 explicitly depends on:

1. Worker execution states (CRITICAL_SECTION, SAFE_POINT) — referenced in Phase 10 §10.3, §10.4, §10.8
2. Delay module foundation — referenced in Phase 10 §Constraints

These are **missing prerequisites**, not implementation bugs.

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
Phase 9 (Existing)          Phase 9 (Gap)              Phase 10
┌─────────────────┐         ┌────────────────────┐     ┌───────────────────┐
│ Task 9.1        │         │ Task 9.3           │     │ Task 10.1         │
│ Behavior Engine │ ✅ Done  │ Worker Exec States │ ──► │ Delay Module      │
│ (Pure Logic)    │         │ (CRITICAL_SECTION, │     │ (Pure Logic)      │
└─────────────────┘         │  SAFE_POINT)       │     └────────┬──────────┘
                            └────────┬───────────┘              │
┌─────────────────┐                  │              ┌───────────▼──────────┐
│ Task 9.2        │                  │              │ Task 10.2            │
│ Scaling Exec    │ ✅ Done           │              │ BehaviorState        │
│ (Integration)   │                  │              │ Context Definition   │
└─────────────────┘                  │              └───────────┬──────────┘
                                     │                          │
                                     │              ┌───────────▼──────────┐
                                     └─────────────►│ Task 10.3            │
                                                    │ Behavior Wrapper     │
                                                    │ (Integration)        │
                                                    └───────────┬──────────┘
                                                                │
                                                    ┌───────────▼──────────┐
                                                    │ Task 10.4            │
                                                    │ Guard Validation     │
                                                    │ (NO-DELAY Zones)     │
                                                    └──────────────────────┘
```

### 5.2 Execution Sequence (Strict Order)

```
STEP 1: Task 9.3  — Worker Execution States (prerequisite gap-fill)
STEP 2: Task 10.1 — Delay Module (pure logic, can parallel with 10.2)
STEP 2: Task 10.2 — BehaviorState Context (pure definition, can parallel with 10.1)
STEP 3: Task 10.3 — Behavior Wrapper (integration — depends on 9.3, 10.1, 10.2)
STEP 4: Task 10.4 — Guard Validation (depends on 10.3)
```

---

## 6. TASK BREAKDOWN

### TASK 9.3 — Worker Execution States (Safe Point Architecture)

**Objective:**
Add worker-level execution state tracking to `integration/runtime.py` so that each worker can declare whether it is in a CRITICAL_SECTION (no external interference allowed) or SAFE_POINT (safe for control operations and delay injection).

**Scope:**
- File: `integration/runtime.py`
- Add: `ALLOWED_WORKER_STATES = {"IDLE", "IN_CYCLE", "CRITICAL_SECTION", "SAFE_POINT"}`
- Add: `_worker_states: dict` — maps worker_id → current execution state
- Add: `set_worker_state(worker_id, state)` — validated state transitions
- Add: `get_worker_state(worker_id)` → current state
- Add: `is_safe_to_control()` → True only when all workers are IDLE or SAFE_POINT
- Modify: `_worker_fn()` to use `_transition_worker_state_locked()` for state changes
- Modify: `start_worker()` to initialize worker state at registration

**Constraints:**
- NO changes to scaling logic (behavior.evaluate routing unchanged)
- NO changes to lifecycle states (INIT/RUNNING/STOPPING/STOPPED unchanged)
- Worker states are SEPARATE from lifecycle states
- Thread-safe via existing `_lock`

**Completion Criteria:**
- [ ] `ALLOWED_WORKER_STATES` defined with strict transition rules
- [ ] `set_worker_state()` raises `ValueError` for invalid transitions
- [ ] `is_safe_to_control()` returns `True` only when all workers IDLE/SAFE_POINT
- [ ] `_worker_fn()` transitions through states: IDLE → IN_CYCLE → (CRITICAL_SECTION ↔ SAFE_POINT) → IDLE
- [ ] Missing worker state treated as unsafe by `is_safe_to_control()`
- [ ] Tests: state transitions, invalid transition rejection, is_safe_to_control logic
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
- Delay values MUST NOT exceed watchdog timeout headroom (max single delay < 5s to preserve 10s watchdog budget)
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

**Dependencies:** None (pure module, independent of all other tasks)

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

**Dependencies:** None (definition only, no runtime integration)

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
| **9.3** Worker States | — (none) | — | 10.3 |
| **10.1** Delay Module | — (none) | 9.3, 10.2 | 10.3 |
| **10.2** BehaviorState | — (none) | 9.3, 10.1 | 10.3 |
| **10.3** Behavior Wrapper | 9.3, 10.1, 10.2 | — | 10.4 |
| **10.4** Guard Validation | 10.3 | — | — (final) |

### Parallelization Opportunities

```
WAVE 1 (parallel):  Task 9.3  ║  Task 10.1  ║  Task 10.2
                        │              │              │
                        └──────────────┼──────────────┘
                                       │
WAVE 2 (sequential):           Task 10.3
                                       │
WAVE 3 (sequential):           Task 10.4
```

---

## 8. RISK ASSESSMENT

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

### Problems Identified

1. **Phase 10 depends on worker execution states (CRITICAL_SECTION, SAFE_POINT) that Phase 9 did not implement** — Phase 10 §10.3 references "CRITICAL_SECTION (defined in Phase 9)" but no such infrastructure exists in the codebase.

2. **Phase 10 assumes `modules/delay/` exists** — The constraint "uses existing modules/delay/" cannot be met because the module does not exist.

3. **BehaviorState (Phase 10) relationship to existing FSM is undefined** — Two state machines (outcome states vs. execution context) need clear separation.

4. **Delay timing bounds not explicitly mapped to Blueprint values** — Phase 10 spec references Blueprint sections but does not bind specific delay ranges.

5. **Worker wrapper injection point is ambiguous** — The spec says "worker_fn → wrap(task_fn)" but doesn't specify exactly where in the code the wrapping occurs.

### Redesigned Execution Order

1. **Task 9.3** — Fill the Phase 9 prerequisite gap: add worker execution states
2. **Task 10.1** — Create delay module (pure logic, Blueprint-aligned timing)
3. **Task 10.2** — Define BehaviorState context (separate from existing FSM)
4. **Task 10.3** — Build behavior wrapper (integration point for delays)
5. **Task 10.4** — Validate NO-DELAY zone guards

### Key Principles

- Bottom-up: pure logic first, integration last
- No cross-layer contamination
- Each task independently testable and deployable
- Blueprint timing is the source of truth for delay bounds
- Phase 9 scaling logic remains completely untouched
