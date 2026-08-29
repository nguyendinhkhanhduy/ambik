# AmbiK AI Backend <-> ROS Robot Bridge: API Contract Specification

**Phiên bản:** 3.0.0 (Fail-Closed Architecture)
**Tác giả:** Đội ngũ AI Engine AmbiK
**Đối tượng:** Đội ngũ Tích hợp ROS / Robot Điều khiển (MoveIt, Gazebo, Navigation)

---

## 1. Phân định Trách nhiệm (Role Boundaries)

| Thành phần | Vai trò & Trách nhiệm |
|---|---|
| **AmbiK AI Backend** | - Tiếp nhận câu lệnh ngôn ngữ tự nhiên (Tiếng Việt / Tiếng Anh).<br>- Phân loại và lượng hóa mơ hồ (Semantic Entropy, Conformal Prediction).<br>- Sinh câu hỏi làm rõ (HRI Clarification) khi mơ hồ.<br>- Trừu tượng hóa mệnh đề và kiểm chứng an toàn hình thức (LTL + Deterministic Safety Policy Engine).<br>- **Chỉ phê duyệt (APPROVED) kế hoạch khi 100% an toàn.** |
| **ROS Bridge & Controller** | - Thu thập trạng thái môi trường từ cảm biến/camera/TF (environment_objects).<br>- Gửi yêu cầu phân tích tới API Endpoint /api/analyze.<br>- **Tuân thủ quy tắc kiểm tra điều kiện tiên quyết (Dispatch Preconditions) trước khi gửi lệnh tới robot.**<br>- Ánh xạ các bước hành động nguyên tử (ExecutionStep) thành các ROS Action Goals (MoveIt, Nav2). |

---

## 2. API Endpoint Specification

### POST /api/analyze

- **URL:** http://localhost:8000/api/analyze
- **Method:** POST
- **Headers:** Content-Type: application/json
- **Timeout khuyến nghị:** 10.0 giây

---

## 3. Cấu trúc Dữ liệu Đầu vào (Request Payload)

`json
{
  "input_type": "plan_amb_task",
  "input_content": "Lấy ly sứ trên bàn giúp tôi",
  "environment": [
    "a ceramic mug",
    "a glass mug",
    "coffee machine",
    "kitchen table"
  ],
  "chat_history": []
}
`

### Chi tiết các trường:
- input_type (*string*, bắt buộc): Loại đầu vào ("plan_amb_task", "text", "chat", "instruction").
- input_content (*string*, bắt buộc): Câu lệnh từ người dùng (độ dài: 2 đến 2000 ký tự).
- environment (*list[string]*, bắt buộc): Danh sách tên/ID vật thể hiện có trong không gian làm việc. **Không được để rỗng (HTTP 422 nếu rỗng).**

---

## 4. Cấu trúc Dữ liệu Đầu ra (Response Payload)

Mọi phản hồi từ backend luôn chứa 3 trường chuẩn ở cấp cao nhất:

`json
{
  "request_id": "f3cc9986-5e18-4eeb-9fcd-6972d81e97b4",
  "status": "APPROVED",
  "reason_code": "APPROVED",
  "analysis": {
    "overall_classification": "Unambiguous",
    "entropy_score": 0.0,
    "verified_safe": true,
    "safe_execution_plan": [
      {
        "step": 1,
        "action": "Find",
        "target": "a ceramic mug",
        "destination": null,
        "note": "Locate target object in kitchen environment"
      },
      {
        "step": 2,
        "action": "PickUp",
        "target": "a ceramic mug",
        "destination": null,
        "note": "Grasp target object safely"
      }
    ],
    "k_choice_question": null,
    "chat_reply": "Đang thực hiện lấy ly sứ..."
  }
}
`

---

## 5. Bảng Mã Trạng thái (status) và Mã Lý do (eason_code)

| status | Ý nghĩa | Hành động của ROS Node |
|---|---|---|
| APPROVED | Kế hoạch an toàn, đã kiểm chứng toán học. | Thực thi các bước hành động trên Robot. |
| NEEDS_CLARIFICATION | Câu lệnh mơ hồ hoặc có nhiều ứng viên vật thể. | Hiển thị câu hỏi k_choice_question cho người dùng, **KHÔNG di chuyển robot**. |
| REJECTED | Vi phạm an toàn vật lý hoặc dữ liệu không hợp lệ. | Dừng khẩn cấp, hiển thị cảnh báo vi phạm an toàn, **KHÔNG di chuyển robot**. |

### Danh sách eason_code phổ biến:
- APPROVED: Phê duyệt thực thi.
- UNSAFE_MICROWAVE_MATERIAL: Vật liệu không an toàn (kim loại, nhựa không chịu nhiệt) đưa vào lò vi sóng.
- DIRTY_TOOL_ON_CLEAN_SURFACE: Dùng dụng cụ bẩn (giẻ bẩn) trên bề mặt/thực phẩm sạch.
- KNIFE_WITHOUT_SAFETY_SURFACE: Thao tác dao khi không có thớt an toàn.
- MULTIPLE_CANDIDATES: Nhiều vật thể khớp với câu lệnh mơ hồ (Preferences).
- CLASSIFICATION_INCONCLUSIVE: Không đủ căn cứ để kết luận hành động rõ ràng.

---

## 6. Quy tắc Phê duyệt Thực thi (Strict Dispatch Preconditions)

ROS Node **CHỈ ĐƯỢC PHÉP** gửi mục tiêu điều khiển (Action Goals) tới cánh tay/bánh xe robot khi và chỉ khi thỏa mãn **TẤT CẢ** các điều kiện sau:

1. status == "APPROVED"
2. erified_safe == true
3. len(safe_execution_plan) > 0
4. 
eeds_clarification == false

Nếu bất kỳ điều kiện nào sai -> **Hủy lệnh ngay lập tức (Fail-Closed).**

---

## 7. Ánh xạ Hành động Nguyên tử sang ROS Actions

| ction | ROS 2 / ROS 1 Package | Action Type / Service |
|---|---|---|
| Find | 
av2_msgs / move_base | NavigateToPose (Di chuyển robot tới gần vật thể) |
| PickUp | moveit_msgs | PickupAction / GraspAction (Kẹp vật thể) |
| Place | moveit_msgs | PlaceAction (Đặt vật thể xuống vị trí đích) |
| Heat | Custom ROS Service | kitchen_appliances/HeatService (Bật lò vi sóng) |
| Clean | moveit_msgs | TrajectoryAction (Chuyển động lau chùi bề mặt) |
| Open / Close | moveit_msgs | GripperCommand (Mở/đóng cửa tủ, lò) |
