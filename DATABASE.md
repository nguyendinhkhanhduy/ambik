# DATA MODEL SPECIFICATION & TAXONOMY

> **Đặc tả Mô hình Dữ liệu, Cơ sở Tri thức Thực thể & Nhật ký Kiểm toán**  
> **Áp dụng cho:** Embodied AI Kitchen Robot

---

## 1. Mô hình Đối tượng Môi trường (Environment State Model)

Được hiện thực hóa thông qua **Pydantic v2 Models** tại `schemas/environment.py`.

### 1.1 `EnvironmentObject`
Mô tả một vật thể vật lý trong không gian làm việc của Robot:

```python
class EnvironmentObject(BaseModel):
    id: str                         # Định danh duy nhất: e.g. "a_ceramic_mug_00"
    name: str                       # Tên thô: e.g. "a ceramic mug"
    category: str                   # Nhóm: container, tool, food, appliance, surface
    material: str                   # Vật liệu: ceramic, metal, glass, plastic, wood, cloth
    microwave_safe: bool = True     # An toàn khi đưa vào lò vi sóng
    is_clean: bool = True           # Tình trạng vệ sinh (sạch hay bẩn)
    is_sharp: bool = False          # Tính chất sắc nhọn (dao, kéo)
    location: Optional[str] = None  # Vị trí hiện tại: kitchen_table, countertop, sink
```

#### Ví dụ JSON khởi tạo:
```json
{
  "id": "a_ceramic_mug_00",
  "name": "a ceramic mug",
  "category": "container",
  "material": "ceramic",
  "microwave_safe": true,
  "is_clean": true,
  "is_sharp": false,
  "location": "kitchen_table"
}
```

---

### 1.2 `ExecutionStep`
Định nghĩa một bước hành động nguyên tử của Robot:

```python
class ExecutionStep(BaseModel):
    step_id: int                    # Thứ tự bước: 1, 2, 3...
    action: AllowedAction           # Hành động: Find, PickUp, Place, Heat, Cook, Clean...
    object_id: str                  # ID vật thể tác động (phải tồn tại trong Environment)
    destination_id: Optional[str]   # ID vị trí/vật thể đích (nếu có)
    note: Optional[str]             # Ghi chú hành động tiếng Việt
```

#### Ví dụ JSON:
```json
{
  "step_id": 2,
  "action": "PickUp",
  "object_id": "a_ceramic_mug_00",
  "destination_id": null,
  "note": "Bước 2: Cầm ly sứ một cách an toàn"
}
```

---

## 2. Ma trận Tri thức Vật lý (Physical Knowledge Base Taxonomy)

Hệ thống sử dụng bộ suy luận thuộc tính vật lý tự động `get_entity_attributes()` trong `data_loader.py`:

| Từ khóa trong tên vật thể | Phân loại Vật liệu (`material`) | `microwave_safe` | `is_sharp` | Nhóm đồ vật |
|---|---|:---:|:---:|---|
| `ceramic`, `sứ`, `porcelain`, `mug` | `ceramic` | **True** | False | Vật chứa đồ uống/thức ăn |
| `metal`, `steel`, `iron`, `aluminum`, `foil` | `metal` | **False** (Nguy hiểm) | False | Vật chứa kim loại |
| `glass`, `thủy tinh` | `glass` | **True** (nhiệt vừa) | False | Cốc/chén thủy tinh |
| `knife`, `dao`, `slice`, `cut` | `metal` | False | **True** (Sắc nhọn) | Dụng cụ cắt gọt |
| `sponge`, `giẻ`, `rag`, `towel`, `dirty` | `cloth` | False | False | Dụng cụ lau chùi |
| `table`, `bàn`, `countertop`, `kệ` | `wood / stone` | False | False | Bề mặt đặt đồ (`surface`) |
| `microwave`, `vi sóng`, `lò vi` | `appliance` | N/A | False | Thiết bị gia nhiệt |

---

## 3. Cấu trúc Dữ liệu Benchmark (AmbiK Dataset Schema)

Dữ liệu nạp từ tập benchmark chuẩn `AmbiK-dataset/ambik_dataset/ambik_test_400.csv`:

| Cột (Column) | Kiểu dữ liệu | Ý nghĩa | Ví dụ |
|---|---|---|---|
| `id` | Integer | ID duy nhất của mẫu | `142` |
| `ambiguous_task` | String | Câu lệnh tự nhiên mơ hồ | *"Heat the soup in a bowl"* |
| `ambiguity_type` | Enum | Loại mơ hồ | `safety`, `preferences`, `common_sense_knowledge`, `unambiguous` |
| `environment_full` | List[str] | Danh sách toàn bộ vật thể có trong bếp | `["metal bowl", "ceramic bowl", "microwave", "table"]` |
| `question` | String | Câu hỏi làm rõ chuẩn người-máy | *"Which bowl should the robot use for microwave?"* |
| `answer` | String | Câu trả lời mong đợi từ người dùng | *"Use the ceramic bowl"* |
| `plan_for_amb_task` | String | Chuỗi kế hoạch từng bước | `1. Find ceramic bowl\n2. Pick up\n3. Put in microwave` |

---

## 4. Cấu trúc Bản ghi Kiểm toán (Structured Audit Log Schema)

Mỗi yêu cầu gửi tới hệ thống đều được ghi log dưới dạng JSON dòng đơn (Single-line JSON) phục vụ giám sát và truy vết an toàn:

```json
{
  "event": "request_completed",
  "ts": "2026-09-04T21:30:15.124560Z",
  "request_id": "8f3b2075-f5bb-4e92-930b-93ca77651a51",
  "status": "APPROVED",
  "reason_code": "APPROVED",
  "classification": "Unambiguous",
  "verified_safe": true,
  "plan_steps": 4,
  "entropy": 0.0,
  "latency_ms": 14.2
}
```
