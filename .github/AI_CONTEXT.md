## 🤖 NATIVE AI WORKFLOW (GitHub Copilot Business)

Hệ thống vận hành theo kiến trúc 3 tầng bản địa, lấy Pull Request (PR) và Issue làm trung tâm điều phối. Tuyệt đối không sử dụng AI bên ngoài (Zero-External AI) để duy trì tính toàn vẹn của Copilot Memory.

### 1. Tầng Định hướng (Human)
* **Vai trò:** Supreme Commander (Chỉ huy tối cao).
* **Nhiệm vụ:** Chỉ định Task qua Issue/PR, giao việc bằng tag `@github-copilot`, không tự viết Prompt kỹ thuật, ra quyết định `Merge` cuối cùng.

### 2. Tầng Thiết kế & Kiểm duyệt (GitHub Web)
* **Architect (Anthropic Claude Opus 4.6):** Kích hoạt qua comment trên giao diện Web. Đọc `AI_CONTEXT.md` từ Memory, phân tích Issue và vạch ra Spec (các bước thực thi chi tiết).
* **Reviewer (OpenAI GPT-5.4):** Tự động kích hoạt qua Ruleset khi có PR. Sử dụng dữ liệu phân tích từ CodeQL, đối chiếu với Spec để cấp `APPROVED` hoặc `REJECTED`.
* **Cross-Inspector (Google Gemini 3.1 Pro):** Kích hoạt thủ công trên Web khi có xung đột logic hoặc PR độ khó cao để thanh tra chéo (Cross-check) độc lập.

### 3. Tầng Thực thi (IDE / Copilot Workspace)
* **Developer (OpenAI GPT-5.2-Codex):** Kích hoạt bằng `@workspace` trong IDE. Nhận Spec từ Architect, tự động sinh code, refactor và đẩy (Push) thay đổi lên PR.

### 4. Giao thức Kết nối & Xử lý Ngoại lệ (Hard Rules)
* **Rule 1 - Định danh tuyệt đối (Absolute Targeting):** Mọi lệnh giao việc cho Developer (Codex) trong IDE bắt buộc phải gắn kèm ID của Issue/PR. Cú pháp chuẩn: `@workspace Thực thi Spec từ Issue #[ID] do Architect đã chốt`.
* **Rule 2 - Vòng lặp REJECT (Auto-Fix Loop):** Khi GPT-5.4 đánh `REJECTED`, Human tuyệt đối không copy lỗi thủ công. Human gõ lệnh vào IDE: `@workspace Đọc comment review mới nhất tại PR #[ID] và tự động sửa lỗi`.
* **Rule 3 - Quy tắc quá tam ba bận (Rule of Three):** Nếu PR bị GPT-5.4 `REJECTED` quá 3 lần vì cùng một lỗi, quy trình tự động dừng. Human triệu hồi **Gemini 3.1 Pro** vào PR đó để phân xử, tìm nguyên nhân gốc rễ và đưa ra mã code chốt hạ.
