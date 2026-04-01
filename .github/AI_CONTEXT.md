## 🤖 NATIVE AI WORKFLOW (GitHub Copilot Business)

Hệ thống vận hành theo kiến trúc 3 tầng bản địa (Native 3-Tier), lấy Pull Request (PR) và Issue làm Single Source of Truth. Tuyệt đối không sử dụng AI bên ngoài hệ sinh thái GitHub (Zero-External AI) để duy trì tính toàn vẹn của Copilot Memory Index.

---

### 1. Tầng Định hướng (Human – Supreme Commander)
* **Vai trò:** Ra quyết định chiến lược, không can thiệp chiến thuật.
* **Nhiệm vụ:**
  - Tạo Issue mô tả yêu cầu (What), giao việc bằng `@github-copilot` trên Web.
  - Không tự viết Prompt kỹ thuật, không copy-paste giữa các AI.
  - Ra quyết định `Merge` cuối cùng sau khi CI pass + Review approve.
  - Kích hoạt Cross-Inspector khi cần phân xử xung đột.

### 2. Tầng Thiết kế & Kiểm duyệt (GitHub Web Interface)
* **Architect (Anthropic Claude Opus 4.6):**
  - Kích hoạt qua `@github-copilot` comment trên Issue/PR.
  - Đọc `AI_CONTEXT.md` + toàn bộ repo context từ Copilot Memory Index.
  - Phân tích yêu cầu, vạch Spec chi tiết (Function/Input/Output/Constraints/Forbidden).
  - Output: Spec comment trực tiếp trên Issue/PR (không cần file trung gian).
* **Reviewer (OpenAI GPT-5.4):**
  - Tự động kích hoạt qua PR Ruleset khi có PR mới hoặc push mới.
  - Đối chiếu code với Spec trong `spec/`, kiểm tra tuân thủ `AI_CONTEXT.md`.
  - Tham chiếu kết quả CodeQL Code Scanning + Copilot Autofix suggestions.
  - Output: `APPROVED` hoặc `CHANGES_REQUESTED` kèm comment cụ thể.
* **Cross-Inspector (Google Gemini 3.1 Pro):**
  - Kích hoạt thủ công bởi Human khi: (a) PR phức tạp cao, (b) xung đột logic giữa modules, (c) Escalation từ Rule 3.
  - Thanh tra chéo độc lập, không bị ảnh hưởng bởi context của Architect/Reviewer.

### 3. Tầng Thực thi (IDE – Copilot Coding Agent)
* **Developer (OpenAI GPT-5.2-Codex):**
  - Kích hoạt qua Copilot Coding Agent (assign task trên Issue hoặc `@github-copilot` trong PR).
  - Đọc Spec từ Issue/PR comment do Architect chốt + toàn bộ repo context từ Memory Index.
  - Tự động sinh code, viết unit test, tạo branch, commit, push và mở PR.
  - Tự động chạy CI trước khi request review.

### 4. Giao thức Kết nối & Xử lý Ngoại lệ (Hard Rules)

* **Rule 1 – Ngữ cảnh Bất biến (Immutable Context):**
  Mọi task giao cho Developer phải xuất phát từ một Issue/PR có Spec đã được Architect chốt. Developer đọc context trực tiếp từ GitHub (Issue body, PR comments, repo files) – không qua kênh trung gian. Cú pháp: Assign Copilot vào Issue, hoặc comment `@github-copilot implement the spec from Issue #[ID]` trên PR.

* **Rule 2 – Vòng lặp Tự sửa (Auto-Fix Loop):**
  Khi Reviewer đánh `CHANGES_REQUESTED`, Human **không** copy lỗi thủ công. Human comment trên PR: `@github-copilot Fix the review comments above`. Codex tự đọc review comments từ PR API, sửa code, push commit mới. Vòng lặp tự động: Push → Review → Fix → Push.

* **Rule 3 – Ngắt mạch ba lần (Circuit Breaker):**
  Nếu PR bị Reviewer reject ≥3 lần **vì cùng một lỗi gốc**, quy trình tự động dừng (Circuit Open). Human triệu hồi **Gemini 3.1 Pro** vào PR comment để: (a) Root-cause analysis, (b) Đề xuất giải pháp cụ thể hoặc viết code chốt hạ. Sau khi Gemini chốt, Human giao lại cho Codex implement.

* **Rule 4 – CI Failure Auto-Recovery:**
  Khi CI fail trên PR, Copilot Autofix tự động đề xuất fix cho CodeQL alerts. Với CI check failures khác (import scope, signature, spec lock), Human comment: `@github-copilot CI failed. Read the CI logs and fix the failing checks`. Codex tự đọc log từ GitHub Actions API và sửa.

* **Rule 5 – Security Gate:**
  Mọi PR phải pass toàn bộ security pipeline trước khi merge:
  - CodeQL Code Scanning: Không có alert severity `high` hoặc `critical`.
  - Dependabot: Không có vulnerability `high`+ chưa được address.
  - Secret Scanning + Push Protection: Không có secret nào bị leak.
  - Copilot Autofix: Các suggestion phải được review và apply/dismiss.

### 5. Hạ tầng Bảo mật & Tự động hóa (Security Infrastructure)

| Tính năng | Cấu hình | Vai trò trong Workflow |
|---|---|---|
| **Copilot Memory Index** | Index toàn bộ repo | Cung cấp context cho tất cả AI agents |
| **CodeQL Code Scanning** | Bật trên mọi PR | Phát hiện lỗ hổng bảo mật tự động |
| **Copilot Autofix** | Bật | Tự động đề xuất fix cho CodeQL alerts |
| **Push Protection** | Bật | Chặn commit chứa secrets trước khi push |
| **Secret Scanning** | Validity checks + Non-provider patterns | Quét mở rộng, kiểm tra tính hợp lệ |
| **Dependabot** | Security + Grouped + Version updates | Tự động tạo PR cập nhật dependencies |
| **PR Rulesets** | Require PR + Copilot Review + CI pass | Ép buộc quy trình qua cơ chế máy |
| **Admin Bypass** | Always Bypass cho Admin | Escape hatch cho trường hợp khẩn cấp |

### 6. CI Pipeline tích hợp (SPEC-6 CI)

```
PR Created/Updated
    │
    ├── check_import_scope  → Cấm import chéo module
    ├── check_signature     → Function phải match spec/interface.md
    ├── check_pr_scope      → ≤200 dòng, scope đơn module
    ├── check_spec_lock     → Cấm sửa /spec/* (trừ Architect được bypass)
    ├── Unit Tests          → python -m unittest discover tests
    ├── Schema Import       → Validate spec.schema importable
    │
    ├── CodeQL Scanning     → Tự động qua GitHub Advanced Security
    ├── Copilot Autofix     → Đề xuất fix cho CodeQL alerts
    ├── Dependabot Check    → Kiểm tra dependency vulnerabilities
    └── Secret Scanning     → Quét secrets trong diff
        │
        ▼
    Copilot PR Review (GPT-5.4) → APPROVED / CHANGES_REQUESTED
        │
        ▼
    Human → Merge Decision
