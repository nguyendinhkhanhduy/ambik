"""
schemas/environment.py
Chuẩn hóa dữ liệu đầu vào cho môi trường nhà bếp và kế hoạch thực thi.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# 1. Action allowlist — LLM chỉ được dùng các action này
# ──────────────────────────────────────────────
class AllowedAction(str, Enum):
    Find    = "Find"
    PickUp  = "PickUp"
    Place   = "Place"
    Pour    = "Pour"
    Mix     = "Mix"
    Heat    = "Heat"
    Clean   = "Clean"
    Open    = "Open"
    Close   = "Close"


# ──────────────────────────────────────────────
# 2. Environment Object — có id duy nhất, thuộc tính từ structured data
# ──────────────────────────────────────────────
class EnvironmentObject(BaseModel):
    id: str = Field(..., description="ID duy nhất, ví dụ 'ceramic_mug_01'")
    name: str = Field(..., description="Tên hiển thị, ví dụ 'ceramic mug'")
    type: str = Field(default="object", description="Loại: container, appliance, tool, food...")
    material: str = Field(default="unknown", description="ceramic|glass|metal|plastic|unknown")
    location: str = Field(default="unknown", description="Vị trí trong bếp")
    is_clean: bool = Field(default=True)
    microwave_safe: bool = Field(default=False)
    food_safe: bool = Field(default=True)
    temperature_c: float = Field(default=25.0)

    @field_validator("material")
    @classmethod
    def validate_material(cls, v: str) -> str:
        allowed = {"ceramic", "glass", "metal", "plastic", "wood", "unknown"}
        return v if v in allowed else "unknown"

    @classmethod
    def from_string(cls, raw: str, index: int = 0) -> "EnvironmentObject":
        """
        Backward-compat: tạo EnvironmentObject từ chuỗi tự do (ví dụ "a ceramic mug").
        Thuộc tính suy luận từ keyword — CHỈ dùng khi chưa có structured data.
        Đánh dấu requires_grounding=True để hệ thống biết đây là dữ liệu chưa xác minh.
        """
        name_lower = raw.lower().strip()
        obj_id = raw.lower().replace(" ", "_").replace("'", "")[:40] + f"_{index:02d}"

        is_metal   = any(k in name_lower for k in ["metal","steel","iron","aluminum","foil","knife","fork","pan","pot","spoon","can","tin","skillet"])
        is_plastic = any(k in name_lower for k in ["plastic","bag","wrap"])
        is_glass   = any(k in name_lower for k in ["glass","jar"])
        is_ceramic = any(k in name_lower for k in ["ceramic","porcelain","mug","plate","bowl","dish"])
        # Expanded dirty keywords: rag, cloth, towel, sponge are always treated as potentially dirty
        is_dirty   = any(k in name_lower for k in ["dirty","used","unwashed","soiled","rag","cloth","towel","sponge"])
        # Food-safe surfaces: any surface that contacts food
        is_food_surface = any(k in name_lower for k in [
            "food", "fruit", "vegetable", "bowl", "plate", "dish", "cutting board",
            "thớt", "clean", "salad", "ingredient"
        ])

        material = "metal" if is_metal else ("plastic" if is_plastic else ("glass" if is_glass else ("ceramic" if is_ceramic else "unknown")))
        microwave_safe = not (is_metal or (is_plastic and "microwave" not in name_lower))

        return cls(
            id=obj_id,
            name=raw.strip(),
            material=material,
            location="unknown",            # không hardcode "kitchen_table"
            is_clean=not is_dirty,
            microwave_safe=microwave_safe,
            food_safe=is_food_surface,     # True if surface contacts food
        )


class EnvironmentState(BaseModel):
    objects: List[EnvironmentObject] = []

    def get_by_id(self, obj_id: str) -> Optional[EnvironmentObject]:
        for obj in self.objects:
            if obj.id == obj_id:
                return obj
        return None

    def find_by_name(self, name: str) -> List[EnvironmentObject]:
        name_lower = name.lower()
        return [o for o in self.objects if name_lower in o.name.lower() or o.name.lower() in name_lower]

    def ids(self) -> List[str]:
        return [o.id for o in self.objects]

    @classmethod
    def from_string_list(cls, raw_list: List[str]) -> "EnvironmentState":
        """Backward-compat: chuyển List[str] sang EnvironmentState."""
        objects = [EnvironmentObject.from_string(s, i) for i, s in enumerate(raw_list)]
        return cls(objects=objects)


# ──────────────────────────────────────────────
# 3. Execution Step — dùng object_id, không dùng string tự do
# ──────────────────────────────────────────────
class ExecutionStep(BaseModel):
    step_id: int
    action: AllowedAction
    object_id: str
    destination_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    note: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def validate_action(cls, v):
        # Mapping từ legacy action names
        legacy_map = {
            "findobject": "Find", "find": "Find",
            "pickup": "PickUp", "pick": "PickUp",
            "putobject": "Place", "place": "Place", "put": "Place",
            "cookobject": "Heat", "cook": "Heat", "heat": "Heat",
            "mixingredients": "Mix", "mix": "Mix",
            "inspectobject": "Find", "inspect": "Find",
            "pour": "Pour", "clean": "Clean", "open": "Open", "close": "Close",
        }
        v_norm = str(v).lower().strip()
        if v_norm in legacy_map:
            return legacy_map[v_norm]
        return v  # pydantic sẽ validate enum


# ──────────────────────────────────────────────
# 4. Response Status & Reason Codes
# ──────────────────────────────────────────────
class ResponseStatus(str, Enum):
    APPROVED              = "APPROVED"
    NEEDS_CLARIFICATION   = "NEEDS_CLARIFICATION"
    REJECTED              = "REJECTED"


class ReasonCode(str, Enum):
    # Thành công
    APPROVED                    = "APPROVED"
    # Cần làm rõ
    MULTIPLE_CANDIDATES         = "MULTIPLE_CONTAINER_CANDIDATES"
    CLASSIFICATION_INCONCLUSIVE = "CLASSIFICATION_INCONCLUSIVE"
    MISSING_OBJECT_CONTEXT      = "MISSING_OBJECT_CONTEXT"
    # Từ chối
    OBJECT_NOT_IN_ENVIRONMENT   = "OBJECT_NOT_IN_ENVIRONMENT"
    NO_OBJECT_MATCHED           = "NO_OBJECT_MATCHED"
    INVALID_ACTION              = "INVALID_ACTION"
    MISSING_REQUIRED_PARAMETER  = "MISSING_REQUIRED_PARAMETER"
    UNSAFE_MICROWAVE_MATERIAL   = "UNSAFE_MICROWAVE_MATERIAL"
    DIRTY_TOOL_ON_CLEAN_SURFACE = "DIRTY_TOOL_ON_CLEAN_SURFACE"
    KNIFE_WITHOUT_CUTTING_BOARD = "KNIFE_WITHOUT_CUTTING_BOARD"
    HOT_LIQUID_UNSAFE_CONTAINER = "HOT_LIQUID_UNSAFE_CONTAINER"
    UNKNOWN_OBJECT_LOCATION     = "UNKNOWN_OBJECT_LOCATION"
    SAFETY_INVARIANT_VIOLATED   = "SAFETY_INVARIANT_VIOLATED"
