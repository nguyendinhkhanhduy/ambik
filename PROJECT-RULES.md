# PROJECT RULES & CONVENTIONS

> **Phiên bản:** 3.0.0  
> **Dự án:** Embodied AI Kitchen Robot (Neuro-Symbolic AmbiK)  
> **Áp dụng cho:** Toàn bộ thành viên phát triển Backend AI, Frontend HRI và Kỹ sư Nhúng ROS.

---

## 1. Triết lý Thiết kế Cốt lõi (Core Philosophy)

### 🔴 Nguyên tắc Bất biến số 1: FAIL-CLOSED (Đóng kín khi có lỗi)
Trong Robot vật lý thế giới thực, **một lỗi phần mềm có thể gây nổ lò vi sóng hoặc gây thương tích**. Do đó:
* **Mọi trường hợp không chắc chắn, lỗi parse, thiếu dữ liệu hoặc vi phạm an toàn đều phải chuyển về trạng thái AN TOÀN:**
  - status: "NEEDS_CLARIFICATION" (nếu thiếu thông tin ngữ cảnh).
  - status: "REJECTED" (nếu vi phạm an toàn hoặc lỗi cấu trúc).
* **Tuyệt đối KHÔNG BAO GIỜ nuốt lỗi ngầm:** CẤM sử dụng except: pass hoặc except Exception: return [] mà không log và không đổi trạng thái sang REJECTED.
* **Bất biến Phê duyệt (Approval Invariant):**
  \text{status} == \text{"APPROVED"} \iff \left(\text{verified\_safe} == \text{True} \land \operatorname{len}(\text{safe\_execution\_plan}) > 0\right)

---

## 2. Quy ước Code Python (Python Coding Standards)

* **Chuẩn cú pháp:** Tuân thủ PEP 8, sử dụng Type Hints cho 100% hàm và method (	yping.List, 	yping.Dict, 	yping.Optional).
* **Data Modeling:** Toàn bộ dữ liệu truyền nhận bắt buộc phải đi qua **Pydantic v2 Models** (schemas/environment.py). Không truyền dictionary vô danh (dict) thiếu kiểm soát.
* **Action Allowlist:** LLM chỉ được phép sinh các hành động thuộc tập cho phép:
  \text{Action} \in \{\text{Find}, \text{PickUp}, \text{Place}, \text{Heat}, \text{Mix}, \text{Pour}, \text{Clean}, \text{Open}, \text{Close}\}
* **Grounding Constraint:** Tuyệt đối không để LLM "bịa" (hallucinate) tên đồ vật ảo. Mọi 	arget và destination trong kế hoạch bắt buộc phải ánh xạ được vào danh sách thực thể môi trường (EnvironmentState).

---

## 3. Quy ước Bảo mật & Dữ liệu Nhạy cảm (Security & Secrets)

* **API Key Management:** 
  - API Key chỉ lưu tạm trong bộ nhớ RAM (_SERVER_API_KEY), mất đi khi tắt server.
  - Tuyệt đối KHÔNG commit file .env, file cấu hình chứa key thật lên GitHub.
  - Mọi bản ghi log kiểm toán (Audit Logs) chỉ được hiển thị 8 ký tự đầu đã che (AIzaSyD5...).
* **Frontend XSS Prevention:** Mọi dữ liệu từ LLM hiển thị lên Web UI bắt buộc phải bọc qua hàm escapeHtml() hoặc dùng document.createTextNode().

---

## 4. Quy ước Git & Commit Message (Conventional Commits)

Cấu trúc commit: <type>(<scope>): <subject>

| Type | Ý nghĩa | Ví dụ |
|---|---|---|
| eat | Thêm tính năng mới | eat(ctl): add knife cutting board safety invariant |
| ix | Sửa lỗi kỹ thuật | ix(schema): fail-closed on step conversion exception |
| docs | Viết tài liệu | docs(api): add curl examples to API_SPEC.md |
| efactor | Tái cấu trúc mã nguồn | efactor(routing): clean up Tier 1 heuristic checks |
| 	est | Bổ sung bài kiểm thử | 	est(integration): add test suite for microwave hazards |
| chore | Cập nhật cấu hình/dọn dẹp | chore(gitignore): exclude cache and third-party datasets |

---

## 5. Quy trình Kiểm thử Bắt buộc trước khi Merge (Pre-flight Checklist)

Trước khi commit bất kỳ thay đổi nào vào nhánh main, bắt buộc phải chạy và vượt qua 100% các bài test:
1. python scratch/test_integration.py $\rightarrow$ Đạt ALL TESTS PASSED (9/9) ✓.
2. python evaluate_benchmark.py $\rightarrow$ Đạt Safety False-Negative Rate: 0.0% ✓.
