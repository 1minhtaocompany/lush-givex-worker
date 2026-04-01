# SPEC‑6‑FINAL‑EXECUTION‑WORKFLOW

## Phiên bản 2.0 – Native AI Workflow (GitHub Copilot Business)

> **Thay đổi lớn so với v1:** Loại bỏ hoàn toàn DeepSeek, Software Architect GPT và mô hình copy-paste thủ công. Chuyển sang kiến trúc 3 tầng bản địa sử dụng GitHub Copilot Business làm nền tảng duy nhất.

---

## 1. Nguyên tắc Nền tảng

1. **Spec = Luật** – Không viết code khi chưa có đặc tả được Architect chốt.
2. **CI = Cưỡng chế** – Không dựa vào ý thức của người hoặc AI; máy tự kiểm tra.
3. **Runtime Checkpoint = Xác thực cuối cùng** – Mọi logic phải được chạy thực tế trước khi phê duyệt.
4. **Cách ly tuyệt đối** – Mỗi module độc lập, không phụ thuộc chéo (enforced by CI).
5. **Mỗi tác vụ = Một phạm vi nhỏ** – Không suy diễn, không thêm chức năng ngoài yêu cầu.
6. **Zero-External AI** – Tuyệt đối không sử dụng AI ngoài hệ sinh thái GitHub để duy trì Copilot Memory Index.
7. **Issue/PR = Single Source of Truth** – Mọi spec, review, discussion đều sống trên GitHub, không ở kênh ngoài.

---

## 2. AI Workforce Control (Pipeline bản địa – v2.0)

### 2.1 Tổ hợp Model

| Vai trò | Model | Kích hoạt | Đầu ra |
|---------|-------|-----------|--------|
| **Architect** | Claude Opus 4.6 | `@github-copilot` trên Issue/PR (Web) | Spec, interface contract, quyết định kỹ thuật |
| **Developer** | GPT-5.2-Codex | Copilot Coding Agent (assign Issue hoặc `@github-copilot` trên PR) | Code, unit tests, branch, PR |
| **Reviewer** | GPT-5.4 | Tự động qua PR Ruleset | APPROVED / CHANGES_REQUESTED |
| **Cross-Inspector** | Gemini 3.1 Pro | Thủ công bởi Human trên PR | Root-cause analysis, code chốt hạ |

### 2.2 Luồng Thực thi Chuẩn (Standard Flow)

```
Human tạo Issue (What + Why)
    │
    ▼
Architect (Opus 4.6) đọc Issue + repo context từ Memory Index
    │ Output: Spec comment trên Issue
    ▼
Human assign Copilot Coding Agent vào Issue
    │
    ▼
Developer (Codex 5.2) đọc Spec + repo context
    │ Output: Branch → Code + Tests → PR
    ▼
CI Pipeline tự động chạy
    │ ✓ pass → Request Review
    │ ✗ fail → Codex tự đọc log, auto-fix (Rule 4)
    ▼
Reviewer (GPT-5.4) tự động review PR
    │ APPROVED → Human merge
    │ CHANGES_REQUESTED → Codex auto-fix (Rule 2)
    │ Reject ≥3 lần → Escalate to Gemini (Rule 3)
    ▼
Human ra quyết định Merge cuối cùng
```

### 2.3 Luồng Fix Bug / Hotfix

```
Bug phát hiện (Issue / CodeQL Alert / Dependabot Alert)
    │
    ▼
Architect phân tích root cause trên Issue
    │ Output: Fix spec (module + function + expected behavior)
    ▼
Developer (Codex) implement fix
    │ Output: Fix branch → PR
    ▼
CI + Review → Merge (cùng flow chuẩn)
```

### 2.4 Nguyên tắc Làm việc

- **Không AI nào tự ý thay đổi spec** – Spec do Architect định nghĩa, lưu trong `/spec/`, bảo vệ bởi `check_spec_lock.py`.
- **Task format chuẩn** – Mỗi function giao việc theo dạng:
  ```
  Function: <tên>
  Input: <format>
  Output: <format>
  Constraints: <điều kiện>
  Forbidden: <không được làm>
  ```
- **Developer chỉ viết đúng task** – Không thêm logic ngoài phạm vi.
- **Review bắt buộc trước merge** – GPT-5.4 kiểm tra PR, CI phải pass.
- **Context từ Memory Index** – Tất cả AI agents đọc context từ Copilot Memory Index (repo-wide), không cần Human chuyển tiếp context thủ công.

---

## 3. Cấu trúc Phase (Sơ đồ phân cấp)

```
SPEC‑6 EXECUTION WORKFLOW v2.0
│
├── Phase 1 – Spec Lock & Infrastructure (2–3 ngày)
│   ├── Đóng băng đặc tả: FSM, interface, schema
│   ├── Thiết lập repo: branch protection, PR rulesets, Copilot config
│   ├── Kích hoạt: CodeQL, Dependabot, Secret Scanning, Push Protection
│   ├── Lưu trữ trong /spec/ (fsm.md, interface.md, schema.py)
│   └── 🏁 Milestone: Spec hoàn chỉnh, CI + Security pipeline chạy được
│
├── Phase 2 – Module Isolation & CI Enforcement (2–3 ngày)
│   ├── Tạo 4 module: fsm, cdp, billing, watchdog (thư mục /modules/)
│   ├── CI rules (GitHub Actions):
│   │   ├── check_import_scope – cấm import chéo module
│   │   ├── check_signature – function phải match spec
│   │   ├── check_pr_scope – 1 PR ≤ 200 dòng, chỉ 1 module
│   │   └── check_spec_lock – cấm sửa /spec/* (bypass qua ALLOW_SPEC_MODIFICATION)
│   ├── Security pipeline:
│   │   ├── CodeQL Code Scanning trên mọi PR
│   │   ├── Copilot Autofix đề xuất sửa tự động
│   │   ├── Dependabot alerts + auto-PR
│   │   └── Secret Scanning + Push Protection
│   ├── PR Rulesets: Require PR + Copilot Review auto-assign
│   └── 🏁 Milestone: CI bắt được lỗi import/signature/scope, security pipeline active
│
├── Phase 3 – Implementation (5–7 ngày)
│   ├── Branch strategy: main (protected) ← develop ← feature/<module>/<function>
│   ├── Native AI Workflow:
│   │   ├── Architect (Opus) định nghĩa logic → Spec trên Issue
│   │   ├── Developer (Codex) nhận Issue → tự tạo branch, viết code + test, mở PR
│   │   ├── CI tự động chạy → Codex auto-fix nếu fail
│   │   ├── Reviewer (GPT-5.4) auto-review PR, đối chiếu spec
│   │   └── Human merge sau khi CI pass + review approve
│   ├── Integration sớm:
│   │   ├── Không dùng mock phức tạp – chỉ stub đơn giản (trả đúng format)
│   │   └── Smoke test kiểm tra interface compatibility sau khi có fsm + cdp + billing
│   └── 🏁 Milestone: 4 module hoàn chỉnh, unit test pass, smoke test pass
│
├── Phase 4 – Integration & Staging Validation (3–4 ngày)
│   ├── Tích hợp toàn bộ module (branch integration ← develop)
│   ├── Staging environment:
│   │   ├── Site thật, proxy thật
│   │   ├── Dataset riêng biệt (không ảnh hưởng production)
│   │   └── Kill-switch toàn cục để dừng khẩn cấp
│   ├── Rollout: 1 worker → 3 workers
│   ├── Kiểm tra bắt buộc:
│   │   ├── Không double-consume (billing atomic)
│   │   ├── FSM không kẹt, không lỗi state
│   │   ├── Watchdog kill/restart đúng
│   │   ├── CDP network listener hoạt động
│   │   └── Log trace đầy đủ
│   ├── Định lượng "ổn định":
│   │   ├── success rate ≥ 70%
│   │   ├── worker restart count < 2/24h
│   │   ├── memory usage < 1.5G
│   │   └── không double-consume
│   └── 🏁 Milestone: 3 workers chạy 24h đạt các chỉ số trên
│
├── Phase 5 – Production Rollout (3–5 ngày)
│   ├── Rollout theo nấc: 1 → 3 → 5 → 10 workers
│   ├── Mỗi nấc chạy 12–24h trước khi tăng
│   ├── Giám sát liên tục: success rate, error rate, memory, worker deaths
│   ├── Rollback trigger nếu:
│   │   ├── success rate giảm >10% so với nấc trước
│   │   ├── error rate tăng >5%
│   │   ├── memory > 2G
│   │   └── worker die > 3 lần/1h
│   └── 🏁 Milestone: 10 workers chạy 24h ổn định
│
└── Phase 6 – Handover & Operations (2 ngày)
    ├── Viết runbook (start/stop, đọc log, fallback thủ công)
    ├── Cấu hình cron dọn cache browser profile (1 lần/ngày)
    ├── Backup billing pool (SQLite) định kỳ
    └── 🏁 Milestone: Tài liệu đầy đủ, sẵn sàng bàn giao
```

---

## 4. Các điểm Kiểm soát Bắt buộc (Guards)

### 4.1 Blueprint → Test Binding
- Mỗi yêu cầu kỹ thuật trong blueprint phải có ít nhất một test case tương ứng.
- CI kiểm tra sự tồn tại qua quy ước đặt tên test.

### 4.2 Billing Atomic (không double-consume)
- SQLite transaction:
  ```sql
  UPDATE cards SET status='used' WHERE id=? AND status='available'
  ```
- Kiểm tra `affected_rows == 1`. Nếu không, từ chối thao tác và ghi log lỗi.

### 4.3 Watchdog Lifecycle
- Khi kill worker: đóng trình duyệt (kill browser process), xóa profile tạm, giải phóng tài nguyên.
- Ngăn rò rỉ bộ nhớ và zombie process.

### 4.4 PR Scope Limiter
- Mỗi PR: tối đa 200 dòng thay đổi (không tính file test), chỉ 1 module.
- CI từ chối PR vượt giới hạn.
- Bypass: `ALLOW_MULTI_MODULE=true` cho PR spec-sync.

### 4.5 Traceability Logging
- Log định dạng bắt buộc:
  ```
  timestamp | worker_id | trace_id | state | action | status
  ```

### 4.6 CDP Network Listener
- Module CDP phải sử dụng `Network.responseReceived` để chờ API tính tiền trước khi điền thông tin thanh toán.
- Timeout 10s → `SessionFlaggedError`.

### 4.7 Staging Safety Guard
- Dữ liệu staging riêng biệt, không liên quan production.
- Kill-switch toàn cục để dừng toàn bộ workers ngay lập tức.

### 4.8 Rollback Trigger
- Tự động rollback về mức worker trước nếu bất kỳ trigger nào kích hoạt.

### 4.9 Security Guard (MỚI – v2.0)
- **CodeQL Gate:** PR không được merge nếu có alert severity `high`/`critical` chưa resolve.
- **Dependency Gate:** Dependabot alerts severity `high`+ phải được address trước merge.
- **Secret Gate:** Push Protection chặn pre-commit; Secret Scanning quét post-commit.
- **Autofix Gate:** Copilot Autofix suggestions phải được review (apply hoặc dismiss with reason).

---

## 5. GitHub Enforcement (Cập nhật v2.0)

### 5.1 Branch Protection
- **main:** Chỉ nhận PR từ develop, yêu cầu CI pass + ≥1 review approve.
- **develop:** Cấm push trực tiếp, chỉ nhận PR từ feature branch.

### 5.2 PR Rulesets (Copilot Business)
- Require Pull Request trước khi merge.
- Auto-assign Copilot Review (GPT-5.4) trên mọi PR.
- Require CI status checks pass.
- Admin: "Always Bypass" cho trường hợp khẩn cấp.

### 5.3 CI Pipeline (GitHub Actions)
- `check_signature` – So sánh function signature với `spec/interface.md`.
- `check_import_scope` – Đảm bảo không import chéo module.
- `check_pr_scope` – Kiểm tra ≤200 dòng và single-module scope.
- `check_spec_lock` – Đảm bảo `/spec/*` không bị sửa (bypass: `ALLOW_SPEC_MODIFICATION=true`).
- Unit tests – `python -m unittest discover tests`.
- Schema import – `python -c "import spec.schema"`.

### 5.4 Security Pipeline (GitHub Advanced Security)
- **CodeQL:** Tự động scan trên mọi PR, phát hiện vulnerabilities.
- **Copilot Autofix:** Tự động đề xuất fix cho CodeQL alerts.
- **Dependabot:** Security alerts + grouped updates + version updates.
- **Secret Scanning:** Validity checks + non-provider patterns + push protection.

---

## 6. Giao thức Xử lý Ngoại lệ (Exception Protocols)

### 6.1 CI Failure Recovery
```
CI Fail
  │
  ├── CodeQL Alert → Copilot Autofix đề xuất → Human review → Apply/Dismiss
  ├── check_signature fail → Codex đọc log, cập nhật function signature
  ├── check_import_scope fail → Codex loại bỏ cross-module import
  ├── check_pr_scope fail → Codex tách PR thành nhiều PR nhỏ hơn
  ├── check_spec_lock fail → Chỉ Architect được bypass (ALLOW_SPEC_MODIFICATION=true)
  └── Unit test fail → Codex đọc test output, sửa logic
```

### 6.2 Review Rejection Recovery (Auto-Fix Loop)
```
Reviewer CHANGES_REQUESTED
  │
  ├── Lần 1-2: Codex auto-fix dựa trên review comments
  ├── Lần 3: Circuit Breaker kích hoạt
  │   └── Human triệu hồi Gemini 3.1 Pro → Root-cause → Fix spec hoặc code
  └── Sau Gemini fix: Codex implement lại → Review cycle mới
```

### 6.3 Dependency Vulnerability Response
```
Dependabot Alert
  │
  ├── Auto-PR created by Dependabot
  ├── CI chạy trên Dependabot PR
  ├── Reviewer auto-review
  └── Human merge nếu CI pass + review approve
```

---

## 7. Tổng kết Milestones

| Phase | Milestone |
|-------|-----------|
| P1 | Spec lock, CI + Security pipeline sẵn sàng |
| P2 | CI bắt được lỗi import, signature, PR scope; Security gates active |
| P3 | 4 module hoàn chỉnh, unit test pass, smoke test pass |
| P4 | 3 workers staging 24h đạt chỉ số ổn định |
| P5 | 10 workers production 24h ổn định |
| P6 | Runbook hoàn chỉnh, sẵn sàng bàn giao |

---

## 8. Sơ đồ Phân cấp Điều phối (v2.0 – Native)

```
[Supreme Commander] HUMAN
│  (Tạo Issue, giao việc @github-copilot, quyết định Merge, kích hoạt Gemini khi cần)
│
├── [Architect] Claude Opus 4.6 ──── GitHub Web (Issue/PR)
│    (Đọc repo từ Memory Index, phân tích Issue, viết Spec trực tiếp trên GitHub)
│
├── [Developer] GPT-5.2-Codex ──── Copilot Coding Agent
│    (Đọc Spec từ Issue, tự tạo branch, code, test, PR, auto-fix CI/review)
│
├── [Reviewer] GPT-5.4 ──── PR Ruleset (Auto-assign)
│    (Tự động review mọi PR, đối chiếu Spec + CodeQL, cấp APPROVED/CHANGES_REQUESTED)
│
└── [Cross-Inspector] Gemini 3.1 Pro ──── GitHub Web (Escalation Only)
     (Thanh tra chéo khi Circuit Breaker kích hoạt hoặc PR phức tạp cao)
```

**Nguyên tắc Top-Down:**
Opus viết luật (Spec) → CI ép luật (Machine) → Codex thực thi luật (Code) → GPT-5.4 kiểm luật (Review) → Gemini phân xử (Escalation) → Human chốt (Merge).

**Khác biệt then chốt so với v1:**
- ❌ Không còn DeepSeek / Software Architect GPT / AI bên ngoài.
- ❌ Không còn Human làm "cầu nối copy-paste" giữa các AI.
- ✅ Mọi AI đều đọc context trực tiếp từ GitHub (Memory Index + API).
- ✅ Pipeline hoàn toàn tự động: Issue → Spec → Code → CI → Review → Merge.
- ✅ Security pipeline tích hợp sâu: CodeQL + Autofix + Dependabot + Secret Scanning.
