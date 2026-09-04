# API SPECIFICATION & CONTRACT (FE - BE - ROS)

> **Giao thức Kết nối Chuẩn Hóa giữa Giao diện Web, Backend AI và Robot ROS**  
> **Phiên bản:** 3.0.0 (Fail-Closed Architecture)  
> **Base URL:** `http://localhost:8000` (hoặc `http://<IP_HOST>:8000`)

---

## 1. Danh sách Endpoints (API Directory)

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/api/analyze` | **Endpoint chính:** Phân tích câu lệnh, tính Entropy, kiểm tra an toàn & xuất kế hoạch. |
| `POST` | `/api/set-key` | Nạp Gemini API Key vào bộ nhớ RAM của Server (không ghi đĩa). |
| `GET` | `/api/key-status` | Kiểm tra trạng thái Key hiện tại (live hay mock mode). |
| `GET` | `/api/samples` | Lấy danh sách mẫu câu lệnh benchmark từ bộ dữ liệu AmbiK. |
| `GET` | `/` | Trả về giao diện Web Dashboard chính (`index.html`). |

---

## 2. Đặc tả Chi tiết Endpoint Cốt lõi: `POST /api/analyze`

### 📥 2.1 Request Payload
Content-Type: `application/json`

```json
{
  "input_type": "text",
  "input_content": "Pha cho tôi 1 ly cà phê",
  "environment": [
    "a ceramic mug",
    "a glass mug",
    "coffee machine",
    "kitchen table"
  ],
  "model_name": "gemini-2.5-flash",
  "chat_history": []
}
```

#### Quy tắc xác thực (Pydantic Constraints):
* `input_type` (*string*, bắt buộc): Phải thuộc `["plan_amb_task", "text", "chat", "instruction"]`.
* `input_content` (*string*, bắt buộc): Độ dài từ 2 đến 2000 ký tự. Không được chứa toàn khoảng trắng.
* `environment` (*list[string]*, bắt buộc): Danh sách tên vật thể quan sát được trong phòng bếp. **Không được để rỗng (HTTP 422 nếu rỗng)**.

---

### 📤 2.2 Response Payloads (3 Trạng thái Chuẩn)

#### TRƯỜNG HỢP 1: `status: "APPROVED"` (Lệnh rõ ràng hoặc đã giải nghĩa an toàn)
```json
{
  "request_id": "8f3b2075-f5bb-4e92-930b-93ca77651a51",
  "status": "APPROVED",
  "reason_code": "APPROVED",
  "input_type": "text",
  "input_content": "[Người dùng chọn A]: Dùng a ceramic mug\nPha cho tôi 1 ly cà phê",
  "environment": ["a ceramic mug", "a glass mug", "coffee machine", "kitchen table"],
  "analysis": {
    "overall_classification": "Unambiguous",
    "entropy_score": 0.0,
    "verified_safe": true,
    "lifted_nl": "The robot should prop_1 and then prop_2 and then prop_3 and then prop_4.",
    "proposition_mapping": {
      "prop_1": "FindObject(coffee_machine)",
      "prop_2": "PickUp(a_ceramic_mug)",
      "prop_3": "CookObject(coffee_machine)",
      "prop_4": "PutObject(kitchen_table)"
    },
    "ltl_plan": "AG(!unsafe_microwave) & AG(!dirty_sponge) & AG(!knife_without_board)",
    "safe_execution_plan": [
      {
        "step": 1,
        "action": "FindObject",
        "target": "coffee_machine",
        "note": "Bước 1: Tìm máy pha cà phê"
      },
      {
        "step": 2,
        "action": "PickUp",
        "target": "a_ceramic_mug",
        "note": "Bước 2: Cầm ly sứ an toàn"
      },
      {
        "step": 3,
        "action": "CookObject",
        "target": "coffee_machine",
        "note": "Bước 3: Thực hiện pha cà phê"
      },
      {
        "step": 4,
        "action": "PutObject",
        "target": "kitchen_table",
        "note": "Bước 4: Đặt lên bàn ăn"
      }
    ],
    "k_choice_question": {
      "question": "",
      "options": []
    },
    "chat_reply": "Dạ tuyệt vời! Tôi đã ghi nhận bạn chọn ly sứ và bắt đầu pha cà phê ngay ạ!"
  }
}
```

#### TRƯỜNG HỢP 2: `status: "NEEDS_CLARIFICATION"` (Mơ hồ - Robot dừng lại hỏi)
```json
{
  "request_id": "71a938b2-32a1-43ef-b23a-cc3b21698a31",
  "status": "NEEDS_CLARIFICATION",
  "reason_code": "NEEDS_CLARIFICATION",
  "analysis": {
    "overall_classification": "Preferences",
    "entropy_score": 0.85,
    "verified_safe": false,
    "safe_execution_plan": [],
    "execution_plan": [],
    "k_choice_question": {
      "question": "Bạn muốn Robot sử dụng loại ly/cốc nào (Ly sứ hay Ly thủy tinh) để phục vụ cà phê?",
      "options": [
        {
          "key": "A",
          "label": "Dùng Ly sứ (a ceramic mug)",
          "target": "a ceramic mug"
        },
        {
          "key": "B",
          "label": "Dùng Ly thủy tinh (a glass mug)",
          "target": "a glass mug"
        }
      ]
    },
    "chat_reply": "Dạ, để chuẩn bị cà phê đúng ý bạn, tôi nên dùng ly sứ hay ly thủy tinh ạ?"
  }
}
```

#### TRƯỜNG HỢP 3: `status: "REJECTED"` (Vi phạm An toàn Vật lý)
```json
{
  "request_id": "9bb231a4-9b11-40fa-8a89-1065e81d7f44",
  "status": "REJECTED",
  "reason_code": "UNSAFE_MICROWAVE_MATERIAL",
  "analysis": {
    "overall_classification": "Safety",
    "entropy_score": 0.72,
    "verified_safe": false,
    "safe_execution_plan": [],
    "execution_plan": [],
    "chat_reply": "⚠️ Yêu cầu bị từ chối vì lý do an toàn: Không được đưa vật liệu kim loại ('metal bowl') vào lò vi sóng. Nguy cơ cháy nổ!"
  }
}
```

---

## 3. Bảng Mã Lỗi & Lý do (Reason Codes)

| Reason Code | HTTP Code | Ý nghĩa | Hành vi của Robot / ROS |
|---|:---:|---|---|
| `APPROVED` | 200 | Kế hoạch an toàn 100%, được phép thực thi. | Nạp bước hành động vào MoveIt/Nav2. |
| `NEEDS_CLARIFICATION` | 200 | Mơ hồ (Preferences hoặc Safety options). | Dừng robot, phát câu hỏi ra loa / hiển thị màn hình. |
| `UNSAFE_MICROWAVE_MATERIAL` | 200 | Kim loại/nhựa không chịu nhiệt trong vi sóng. | Khóa chuyển động, báo động đỏ. |
| `DIRTY_TOOL_ON_CLEAN_SURFACE`| 200 | Giẻ lau bẩn chạm vào thức ăn/đĩa sạch. | Dừng thao tác lập tức. |
| `KNIFE_WITHOUT_CUTTING_BOARD` | 200 | Cắt gọt bằng dao nhưng không có thớt. | Chặn thực thi. |
| `OBJECT_NOT_IN_ENVIRONMENT` | 200 | LLM ảo giác sinh ra vật thể không có trong bếp. | Bác bỏ kế hoạch (Fail-closed). |
| `CLASSIFICATION_INCONCLUSIVE` | 200 | Không đủ căn cứ kết luận hành động. | Yêu cầu người dùng miêu tả rõ hơn. |
| `VALIDATION_ERROR` | 422 | Payload rỗng hoặc `environment = []`. | Không thực hiện phân tích. |

---

## 4. Ví dụ Gọi API Bằng cURL & Python

### cURL:
```bash
curl -X POST "http://localhost:8000/api/analyze" \
     -H "Content-Type: application/json" \
     -d '{
       "input_type": "text",
       "input_content": "Pha cho tôi một ly cà phê",
       "environment": ["a ceramic mug", "a glass mug", "coffee machine", "kitchen table"]
     }'
```

### Python:
```python
import requests

payload = {
    "input_type": "text",
    "input_content": "Lấy ly sứ trên bàn giúp tôi",
    "environment": ["a ceramic mug", "kitchen table", "microwave"]
}
res = requests.post("http://localhost:8000/api/analyze", json=payload, timeout=10.0)
data = res.json()

if data["status"] == "APPROVED":
    print("Robot bắt đầu thực thi:", data["analysis"]["safe_execution_plan"])
elif data["status"] == "NEEDS_CLARIFICATION":
    print("Hỏi lại người dùng:", data["analysis"]["k_choice_question"]["question"])
```
