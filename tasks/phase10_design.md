# Bảng Thiết Kế Thực Thi Phase 10 — Behavior Layer (Blueprint-safe)

**Phiên bản:** 1.0
**Ngày:** 2026-04-05
**Trạng thái:** Designed — Ready for Implementation
**Nguồn dữ liệu:**
- `spec/blueprint.md` (§8–§15: Kiến trúc hành vi, tích hợp, hiệu năng, mô hình xác định, anti-detect, an toàn, day/night, đồng bộ)
- `spec/.github/SPEC-6-Native-AI-Workflow.md` (§10.1–§10.8: Architecture, FSM Context, CRITICAL_SECTION, SAFE ZONE, NO-DELAY, Action-Aware Delay, Non-Interference, Phase 9 Alignment)

---

## Tổng quan Phase 10

**Mục tiêu tổng quát:** Thêm behavioral delay vào worker execution layer, mô phỏng hành vi người dùng thực (typing, click, hesitation) mà KHÔNG thay đổi control logic, scaling, hoặc orchestration.

**Nguyên tắc bất biến:**
1. Wrapper pattern only — inject tại worker function, không can thiệp runtime loop/rollout/monitor.
2. Zero delay tại CRITICAL_SECTION — payment submit, VBV/3DS, API wait, page reload.
3. Delay chỉ tại SAFE ZONE — UI interaction, non-critical steps.
4. Deterministic — seed-based `random.Random(seed)`, reproducible + testable.
5. Hard constraints — max 1.8s/action, max 5.0s/hesitation, total ≤7.0s/step, ≥3s watchdog headroom.
6. Non-interference — FSM flow giữ nguyên 100%, outcome không đổi.

**Module đích:** `modules/delay/` (thư mục mới theo đặc tả, không thêm module ngoài phạm vi).

---

## Bảng Thiết Kế Thực Thi

### Task 10.1 — PersonaProfile (Nhân Cách Worker)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.1 |
| **Tên Task** | PersonaProfile — Seed-Based Persona Generation |
| **Mục tiêu** | Tạo module sinh hồ sơ nhân cách cho worker dựa trên seed, cung cấp các thuộc tính hành vi cố định suốt cycle. Mỗi worker có bộ thuộc tính riêng biệt, đảm bảo đa dạng hành vi giữa các worker. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Deterministic: `rnd = random.Random(seed)` — cùng seed → cùng profile (Blueprint §11, SPEC §10.6). • Thread-safe: `threading.Lock` bảo vệ mọi shared state (SPEC-6 §1.4 Cách ly tuyệt đối). • Zero cross-module imports: không import từ module khác ngoài stdlib (Guard 3.4, SPEC-6 §2 Phase 2). • Vòng đời cố định: profile không thay đổi khi swap thẻ trong cycle (Blueprint §8). • Isolated random instance: mỗi worker có `random.Random` riêng, không chia sẻ state (Blueprint §11). |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/persona.py` (≤200 dòng). **Class/API:** `PersonaProfile(seed: int)` với các thuộc tính: `typing_speed` (float, phân bố từ seed), `typo_rate` (float, 0.02–0.05 theo seed — Blueprint §4), `hesitation_pattern` (dict chứa min/max delay — Blueprint §5), `persona_type` (str — Blueprint §2: phân loại theo nhân khẩu học, mỗi type có profile hành vi riêng biệt ảnh hưởng tốc độ gõ và mức ngập ngừng), `active_hours` (tuple khung giờ ưa thích — Blueprint §14), `fatigue_threshold` (int, ngưỡng cycles trước khi session fatigue — Blueprint §14), `night_penalty_factor` (float, 0.15–0.30 — Blueprint §14). **Method:** `get_typing_delay(group_index: int) → float`, `get_hesitation_delay() → float`, `get_typo_probability() → float`, `to_dict() → dict`. **Tests:** `tests/test_persona_profile.py` — deterministic output, boundary values, thread-safety. |

---

### Task 10.2 — BehaviorState FSM (Máy Trạng Thái Ngữ Cảnh)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.2 |
| **Tên Task** | BehaviorState — Context-Aware State Machine |
| **Mục tiêu** | Tạo FSM theo dõi ngữ cảnh hiện tại của worker trong cycle, cung cấp thông tin cho delay engine quyết định loại và mức delay phù hợp. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • 5 trạng thái BẮT BUỘC (SPEC §10.2): `IDLE`, `FILLING_FORM`, `PAYMENT`, `VBV`, `POST_ACTION`. • Delay decision PHẢI dựa trên BehaviorState hiện tại (SPEC §10.2 Rule). • Thread-safe: `threading.Lock` cho state transitions. • Strict transitions: chỉ các chuyển đổi hợp lệ được phép (Blueprint §8). • Tương thích Phase 9: KHÔNG xung đột với `ALLOWED_WORKER_STATES` (`IDLE`, `IN_CYCLE`, `CRITICAL_SECTION`, `SAFE_POINT`) — hai hệ thống state hoạt động song song ở tầng khác nhau. |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/state.py` (≤200 dòng). **Constants:** `BEHAVIOR_STATES = {"IDLE", "FILLING_FORM", "PAYMENT", "VBV", "POST_ACTION"}`, `_VALID_BEHAVIOR_TRANSITIONS` dict. **Class/API:** `BehaviorStateMachine(initial_state="IDLE")` với methods: `transition(new_state: str) → bool`, `get_state() → str`, `is_critical_context() → bool` (True khi `VBV` hoặc `POST_ACTION`), `is_safe_for_delay() → bool` (True khi `IDLE`, `FILLING_FORM`, `PAYMENT` và KHÔNG trong CRITICAL_SECTION), `reset() → None`. **Tests:** `tests/test_behavior_state.py` — transition validity, thread-safety, reset behavior, critical context detection. |

---

### Task 10.3 — Delay Engine (Lõi Tính Toán Delay)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.3 |
| **Tên Task** | DelayEngine — Action-Aware Bounded Delay Calculator |
| **Mục tiêu** | Tạo engine tính toán delay dựa trên loại hành động (typing/click/thinking), ngữ cảnh BehaviorState, và PersonaProfile. Đảm bảo mọi delay bị clamp bởi hard constraints trước khi áp dụng. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Action-aware (SPEC §10.6): `typing` → 0.6–1.8s/group 4 số, `click` → spatial offset only (không time delay đáng kể), `thinking` → 3–5s hover/scroll. • Hard constraints (Blueprint §10): `max_delay_per_action ≤ 1.8s`, `max_delay_per_hesitation ≤ 5.0s`, `total_behavioral_delay_per_step ≤ 7.0s`, headroom ≥3s cho watchdog 10s. • CRITICAL_SECTION bypass (SPEC §10.3): nếu trong CRITICAL_SECTION → return 0.0 (zero delay). • SAFE ZONE only (SPEC §10.4): delay chỉ inject tại UI interaction, non-critical steps. • NO-DELAY zone (SPEC §10.5): payment submit, watchdog checks, network wait, VBV iframe, page reload → zero delay. • Typing và thinking loại trừ lẫn nhau trong cùng một bước cycle (Blueprint §10). • Deterministic: sử dụng `random.Random` instance từ PersonaProfile (Blueprint §11). • Clamp TRƯỚC khi áp dụng — không bao giờ vượt max (Blueprint §10). |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/engine.py` (≤200 dòng). **Constants:** `MAX_TYPING_DELAY = 1.8`, `MAX_HESITATION_DELAY = 5.0`, `MAX_STEP_DELAY = 7.0`, `WATCHDOG_HEADROOM = 3.0`. **Class/API:** `DelayEngine(persona: PersonaProfile, state_machine: BehaviorStateMachine)` với methods: `calculate_typing_delay(group_index: int) → float` (0.6–1.8s, clamped), `calculate_click_delay() → float` (≈0, spatial only), `calculate_thinking_delay() → float` (3–5s, clamped), `calculate_delay(action_type: str) → float` (dispatcher), `get_step_accumulated_delay() → float`, `reset_step_accumulator() → None`, `is_delay_permitted() → bool`. **Tests:** `tests/test_delay_engine.py` — clamp validation, CRITICAL_SECTION bypass, accumulator limit, deterministic output, boundary conditions. |

---

### Task 10.4 — Day/Night Temporal Model (Mô Phỏng Ngày/Đêm)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.4 |
| **Tên Task** | TemporalModel — Day/Night Behavior Differentiation |
| **Mục tiêu** | Tạo module mô phỏng chu kỳ sinh học theo thời gian, điều chỉnh hành vi worker giữa chế độ ngày (DAY: 06:00–21:59) và đêm (NIGHT: 22:00–05:59) dựa trên timezone từ proxy IP. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • DAY/NIGHT phân biệt (Blueprint §14): NIGHT → typing chậm hơn 15–30%, hesitation tăng 20–40%, typo rate tăng 1–2%, inter-action delay variance cao hơn. • Tất cả delay vẫn BỊ CLAMP bởi hard constraints §10 (Blueprint §14 quy tắc an toàn). • Gradual drift: hành vi thay đổi từ từ, không nhảy đột ngột (Blueprint §14 Temporal Variation). • Micro-variation: ±5–10% nhiễu mỗi thao tác từ `rnd` (Blueprint §14). • Session fatigue: sau `fatigue_threshold` cycles, hesitation tăng nhẹ (Blueprint §14). • KHÔNG can thiệp CRITICAL_SECTION, KHÔNG phá watchdog, KHÔNG thay đổi FSM flow, KHÔNG thay đổi outcome (Blueprint §14 quy tắc an toàn). • Deterministic: tất cả variation từ `rnd = random.Random(seed)` (Blueprint §14). |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/temporal.py` (≤200 dòng). **Constants:** `DAY_START = 6`, `DAY_END = 21`, `NIGHT_SPEED_PENALTY_RANGE = (0.15, 0.30)`, `NIGHT_HESITATION_INCREASE_RANGE = (0.20, 0.40)`, `NIGHT_TYPO_INCREASE = 0.02`. **Class/API:** `TemporalModel(persona: PersonaProfile)` với methods: `get_time_state(utc_offset_hours: int) → str` ("DAY"/"NIGHT"), `apply_temporal_modifier(base_delay: float, action_type: str) → float` (áp dụng day/night scaling, vẫn clamped), `apply_fatigue(base_delay: float, cycle_count: int) → float`, `apply_micro_variation(base_delay: float) → float` (±5–10%), `get_current_modifiers() → dict`. **Tests:** `tests/test_temporal_model.py` — day/night switching, fatigue accumulation, clamp enforcement, deterministic behavior, micro-variation bounds. |

---

### Task 10.5 — Behavior Wrapper (Bọc Hành Vi)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.5 |
| **Tên Task** | BehaviorWrapper — Task Function Decorator |
| **Mục tiêu** | Tạo wrapper function bọc `task_fn` gốc, inject delay tại các điểm an toàn (SAFE ZONE) mà KHÔNG thay đổi execution logic. Đây là điểm tích hợp duy nhất giữa behavior layer và worker execution. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Wrapper pattern only (SPEC §10.1): `task_fn = wrap(task_fn, persona)` — Blueprint §9. • KHÔNG inject vào runtime loop, scaling logic, orchestration flow (SPEC §10.1). • KHÔNG thay đổi execution outcome — cùng input → cùng kết quả logic (SPEC §10.7, Blueprint §9). • Delay chỉ tại SAFE ZONE (SPEC §10.4): UI interaction, non-critical steps. • Non-blocking: delay bằng `time.sleep()` không chặn luồng chính (Blueprint §10). • Stagger start TÁCH BIỆT (SPEC §10.4): stagger hoạt động giữa worker launches, behavior delay trong cycle — hai cơ chế không can thiệp nhau. • VBV 8–12s wait là OPERATIONAL wait, KHÔNG phải behavioral delay (SPEC §10.5 Clarification). |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/wrapper.py` (≤200 dòng). **Function:** `wrap(task_fn: Callable, persona: PersonaProfile) → Callable` — trả về wrapped function giữ nguyên signature. **Internal flow:** (1) Khởi tạo `BehaviorStateMachine` + `DelayEngine` + `TemporalModel` từ persona, (2) Trước mỗi action trong task_fn: kiểm tra `is_delay_permitted()` → nếu True: `calculate_delay(action_type)` → `apply_temporal_modifier()` → `apply_micro_variation()` → clamp → `time.sleep(delay)`, (3) Sau action: `reset_step_accumulator()` nếu bước mới. **Tests:** `tests/test_behavior_wrapper.py` — wrap preserves return value, wrap adds measurable delay, CRITICAL_SECTION bypass, deterministic with same seed. |

---

### Task 10.6 — Anti-Detection Biometrics (Sinh Trắc Học Chống Phát Hiện)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.6 |
| **Tên Task** | Biometrics — Behavioral Anti-Detection Layer (Tầng 2) |
| **Mục tiêu** | Tạo module bổ sung nhiễu sinh trắc học lên trên delay engine, mô phỏng hành vi typing tự nhiên (burst typing, inter-keystroke variability, temporal noise) để chống fingerprint hành vi. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Tầng 2 KHÔNG phá Tầng 1 — bổ sung lên environment, không thay thế (Blueprint §12). • Tầng 2 KHÔNG thay đổi execution outcome (Blueprint §12). • Temporal noise: phân bố log-normal hoặc gaussian cho inter-keystroke delay (Blueprint §12). • Burst typing: gõ nhanh → dừng → gõ nhanh, kết hợp quy tắc 4×4 (Blueprint §12, §4). • Mỗi worker có distribution riêng dựa trên PersonaProfile seed (Blueprint §12). • Non-periodic: kết hợp burst + hesitation → không có pattern lặp (Blueprint §12). • Deterministic: tất cả từ `random.Random(seed)` (Blueprint §11). • Tất cả delay vẫn BỊ CLAMP bởi hard constraints (Blueprint §10). |
| **Đầu ra (Deliverables)** | **File:** `modules/delay/biometrics.py` (≤200 dòng). **Class/API:** `BiometricProfile(persona: PersonaProfile)` với methods: `generate_keystroke_delay(char_index: int) → float` (inter-keystroke delay, log-normal distribution, clamped), `generate_burst_pattern(total_chars: int) → list[float]` (danh sách delay cho mỗi ký tự, có burst rhythm), `generate_4x4_pattern() → list[float]` (16 delay values cho 16 số thẻ theo quy tắc 4×4: 4 ký tự gõ nhanh → pause 0.6–1.8s → 4 ký tự gõ nhanh → pause — Blueprint §4), `apply_noise(base_delay: float) → float` (gaussian noise ±10%). **Tests:** `tests/test_biometrics.py` — distribution validation, burst pattern structure, 4×4 pattern compliance, deterministic output, clamp enforcement. |

---

### Task 10.7 — Integration Layer (Tích Hợp Vào Runtime)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.7 |
| **Tên Task** | Runtime Integration — Wire Behavior Wrapper into Worker |
| **Mục tiêu** | Tích hợp behavior wrapper vào `_worker_fn` trong `integration/runtime.py`, đảm bảo wrapper được áp dụng đúng tại worker execution layer và tương thích hoàn toàn với Phase 9 (SAFE_POINT, CRITICAL_SECTION). |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Integration/ imports từ modules/ (cho phép bởi kiến trúc — SPEC-6 §2 Phase 2). • KHÔNG inject vào runtime loop, KHÔNG inject vào scaling logic, KHÔNG modify orchestration flow (SPEC §10.1). • Respect SAFE_POINT: behavior hoạt động trong safe boundaries only (SPEC §10.8). • Respect CRITICAL_SECTION: zero interference khi worker trong CRITICAL_SECTION (SPEC §10.8). • Phase 10 MUST NOT operate outside permitted scope (SPEC §10.8). • Không thay đổi worker lifecycle states (INIT/RUNNING/STOPPING/STOPPED) — Blueprint §9. • Không thay đổi worker state transitions (IDLE → IN_CYCLE → CRITICAL_SECTION → SAFE_POINT) — Phase 9 alignment. • PR scope: ≤200 dòng thay đổi, chỉ 1 module (Guard 3.4). • Overhead trung bình ≤15% so với cycle không có behavior (Blueprint §10). |
| **Đầu ra (Deliverables)** | **Thay đổi file:** `integration/runtime.py` — thêm import `from modules.delay.wrapper import wrap`, thêm logic trong `_worker_fn`: `wrapped_task = wrap(task_fn, persona)` trước khi gọi task. **Thay đổi file:** `integration/runtime.py` — thêm persona seed generation trong `start_worker()`. **Tests:** `tests/test_runtime_behavior_integration.py` — wrapper applied correctly, CRITICAL_SECTION respected, SAFE_POINT honored, lifecycle states unchanged, no scaling interference, overhead within 15%. |

---

### Task 10.8 — Safety Validation & Comprehensive Tests (Xác Thực An Toàn)

| Mục | Chi tiết |
|-----|----------|
| **Mã Task** | 10.8 |
| **Tên Task** | Safety Validation — End-to-End Non-Interference Proof |
| **Mục tiêu** | Xác thực toàn diện rằng behavior layer KHÔNG vi phạm bất kỳ quy tắc an toàn nào: không phá CRITICAL_SECTION, không phá watchdog, không thay đổi FSM flow, không thay đổi outcome, và tương thích hoàn toàn với Phase 9. |
| **Ràng buộc & Tiêu chí (SPEC-6)** | • Non-Interference Rule (SPEC §10.7): (1) Không delay trong CRITICAL_SECTION, (2) Không disrupt FSM flow, (3) Không gây side-effects ngoài behavior, (4) Không thay đổi execution order, (5) Không thay đổi success/failure outcome. • Phase 9 Alignment (SPEC §10.8): SAFE_POINT respected, CRITICAL_SECTION zero interference. • Watchdog headroom (Blueprint §10): tổng delay/step ≤ 7.0s, headroom ≥ 3s. • Blueprint → Test Binding (Guard 3.1): mỗi yêu cầu kỹ thuật có ít nhất 1 test case. • Stagger tách biệt: stagger start ≠ behavior delay — hai cơ chế không can thiệp nhau (SPEC §10.4). • VBV operational wait tách biệt: 8–12s VBV wait ≠ behavioral delay (SPEC §10.5). • Traceability (Guard 3.5): log 6-field format `timestamp | worker_id | trace_id | state | action | status`. |
| **Đầu ra (Deliverables)** | **File:** `tests/test_phase10_safety.py` — bộ test toàn diện bao gồm: (1) CRITICAL_SECTION zero-delay proof (payment submit, VBV, API wait, page reload), (2) SAFE_POINT compatibility test (delay chỉ tại IDLE/SAFE_POINT), (3) Watchdog headroom test (accumulated delay < 7.0s, headroom ≥ 3s), (4) FSM flow invariant test (cùng input → cùng state sequence), (5) Outcome invariant test (cùng input → cùng success/failure), (6) Execution order invariant test (step sequence không đổi), (7) Stagger isolation test (stagger ≠ behavior delay), (8) VBV operational wait isolation test, (9) Concurrent thread-safety test (nhiều worker chạy song song), (10) Deterministic reproducibility test (cùng seed → cùng delays). **File:** `tests/test_phase10_integration.py` — integration tests kết hợp tất cả modules delay. |

---

## Ma Trận Đối Chiếu Task ↔ SPEC-6 ↔ Blueprint

| Task | SPEC-6 Reference | Blueprint Reference | Trạng thái đồng bộ |
|------|-------------------|---------------------|---------------------|
| 10.1 — PersonaProfile | §10.6 (Deterministic, Seed-based) | §8 (PersonaProfile), §11 (Deterministic Model), §14 (Day/Night attributes) | ✓ Đồng bộ |
| 10.2 — BehaviorState | §10.2 (FSM Context, MANDATORY) | §8 (BehaviorState 5 states) | ✓ Đồng bộ |
| 10.3 — Delay Engine | §10.3 (CRITICAL_SECTION), §10.4 (SAFE ZONE), §10.5 (NO-DELAY), §10.6 (Action-Aware Delay) | §10 (Performance Control), §13 (Safety Alignment) | ✓ Đồng bộ |
| 10.4 — Temporal Model | §10.6 (Deterministic) | §14 (Day/Night Simulation) | ✓ Đồng bộ |
| 10.5 — Wrapper | §10.1 (Architecture: wrapper only) | §9 (Execution Integration) | ✓ Đồng bộ |
| 10.6 — Biometrics | §10.6 (Action-Aware, typing bounds) | §12 (Anti-Detect Layer Tầng 2) | ✓ Đồng bộ |
| 10.7 — Integration | §10.1 (KHÔNG inject runtime/scaling), §10.8 (Phase 9 Alignment) | §9 (inject tại worker function) | ✓ Đồng bộ |
| 10.8 — Safety | §10.3, §10.4, §10.5, §10.7, §10.8 (tất cả safety rules) | §13 (Safety Alignment), §15 (Sync Matrix) | ✓ Đồng bộ |

---

## Thứ Tự Thực Thi Đề Xuất

```
10.1 (PersonaProfile) ─────┐
                            ├──► 10.3 (Delay Engine) ──► 10.5 (Wrapper) ──► 10.7 (Integration)
10.2 (BehaviorState) ──────┘         │                                            │
                                     │                                            │
10.4 (Temporal Model) ──────────────┘                                            │
                                                                                  │
10.6 (Biometrics) ──────────────────────────────────────────────────────────────┘
                                                                                  │
                                                                           10.8 (Safety Validation)
```

**Phụ thuộc:**
- Task 10.1, 10.2 có thể làm song song (không phụ thuộc nhau).
- Task 10.3 phụ thuộc 10.1 + 10.2 (cần PersonaProfile và BehaviorState).
- Task 10.4 phụ thuộc 10.1 (cần PersonaProfile).
- Task 10.5 phụ thuộc 10.3 + 10.4 (cần engine + temporal model).
- Task 10.6 phụ thuộc 10.1 (cần PersonaProfile).
- Task 10.7 phụ thuộc 10.5 + 10.6 (cần wrapper hoàn chỉnh).
- Task 10.8 phụ thuộc tất cả tasks trước (validation toàn diện).

---

## Ràng Buộc Chung Cho Tất Cả Tasks

| # | Ràng buộc | Nguồn |
|---|-----------|-------|
| 1 | Mỗi PR ≤ 200 dòng thay đổi (không tính test) | Guard 3.4, SPEC-6 §5.3 |
| 2 | Mỗi PR chỉ ảnh hưởng 1 module | Guard 3.4, SPEC-6 §5.3 |
| 3 | Zero cross-module imports | SPEC-6 §2 Phase 2, Guard check_import_scope |
| 4 | Thread-safe: `threading.Lock` cho mọi shared state | SPEC-6 §1.4, AI_CONTEXT quy tắc #2 |
| 5 | Chỉ dùng Python stdlib — không thêm dependency mới | SPEC-6 §1.5, Phase 10 constraints |
| 6 | Deterministic: `random.Random(seed)`, không dùng `random` module-level | Blueprint §11 |
| 7 | Function signature PHẢI match spec | Guard check_signature, SPEC-6 §5.3 |
| 8 | Log 6-field structured format | Guard 3.5 |
| 9 | CI pass: check_import_scope + check_signature + check_pr_scope + unit tests | SPEC-6 §5.3 |
| 10 | Security gates: CodeQL + Dependabot + Secret Scanning + Copilot Autofix | Guard 3.9 |

---

## Milestone Phase 10

> **Behavior layer designed, Blueprint-safe, Phase 9 aligned, ready for implementation.**

**Chỉ số đo lường hoàn thành:**
- [ ] 8 tasks hoàn thành, mỗi task ≤200 dòng production code.
- [ ] Tất cả tests pass (baseline + Phase 10 tests).
- [ ] Zero CRITICAL_SECTION delay violations.
- [ ] Watchdog headroom ≥ 3s cho mọi test scenario.
- [ ] Deterministic: cùng seed → cùng delay sequence qua 3 lần chạy.
- [ ] Overhead trung bình ≤ 15% so với cycle không behavior.
- [ ] CI fully green: import scope, signature, PR scope, unit tests, security gates.
- [ ] Zero cross-module imports trong `modules/delay/`.
- [ ] Ma trận đồng bộ SPEC-6 ↔ Blueprint: zero mismatch.
