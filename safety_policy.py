"""
safety_policy.py
Safety Policy Engine — luật xác định độc lập với LLM.
Kiểm tra từng ExecutionStep trước khi chấp nhận kế hoạch.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from schemas.environment import (
    EnvironmentObject, EnvironmentState, ExecutionStep,
    AllowedAction, ReasonCode, ResponseStatus
)


@dataclass
class PolicyViolation:
    step_id: int
    reason_code: ReasonCode
    message: str


@dataclass
class WorldState:
    """Trạng thái thế giới sau mỗi bước thực thi."""
    objects: Dict[str, EnvironmentObject] = field(default_factory=dict)
    robot_holding: Optional[str] = None          # object_id đang cầm
    in_microwave: Optional[str] = None           # object_id đang trong lò vi sóng

    def get(self, obj_id: str) -> Optional[EnvironmentObject]:
        return self.objects.get(obj_id)


@dataclass
class PolicyResult:
    status: ResponseStatus
    violations: List[PolicyViolation] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return self.status == ResponseStatus.APPROVED

    def first_rejection(self) -> Optional[PolicyViolation]:
        return self.violations[0] if self.violations else None


class SafetyPolicyEngine:
    """
    Deterministic safety rule engine. Chạy sau LLM, trước khi xuất kế hoạch.
    Không bao giờ gọi LLM. Kết quả hoàn toàn tái lập (reproducible).
    """

    # ─── Precondition checkers ───────────────────────────────────────────────

    def _check_object_exists(self, step: ExecutionStep, env: EnvironmentState) -> Optional[PolicyViolation]:
        if not env.get_by_id(step.object_id):
            return PolicyViolation(
                step_id=step.step_id,
                reason_code=ReasonCode.OBJECT_NOT_IN_ENVIRONMENT,
                message=f"Vật thể '{step.object_id}' không tồn tại trong môi trường hiện tại."
            )
        return None

    def _check_destination_exists(self, step: ExecutionStep, env: EnvironmentState) -> Optional[PolicyViolation]:
        if step.destination_id and not env.get_by_id(step.destination_id):
            return PolicyViolation(
                step_id=step.step_id,
                reason_code=ReasonCode.OBJECT_NOT_IN_ENVIRONMENT,
                message=f"Vị trí đích '{step.destination_id}' không tồn tại trong môi trường hiện tại."
            )
        return None

    def _check_microwave_safety(self, step: ExecutionStep, env: EnvironmentState, world: WorldState) -> Optional[PolicyViolation]:
        """Rule: Lò vi sóng chỉ nhận vật thể có microwave_safe=True."""
        if step.action == AllowedAction.Heat:
            dest = env.get_by_id(step.destination_id) if step.destination_id else None
            obj  = env.get_by_id(step.object_id)
            # Case 1: destination is explicitly a microwave
            dest_is_microwave = dest and "microwave" in dest.name.lower()
            # Case 2: no destination but env has a microwave AND object is unsafe
            # (legacy plans from parse_clean_atomic_steps may not set destination_id)
            env_has_microwave = any("microwave" in o.name.lower() for o in env.objects)
            obj_is_unsafe = obj and not obj.microwave_safe

            if (dest_is_microwave or (env_has_microwave and not step.destination_id)) and obj_is_unsafe:
                return PolicyViolation(
                    step_id=step.step_id,
                    reason_code=ReasonCode.UNSAFE_MICROWAVE_MATERIAL,
                    message=f"Không được đưa '{obj.name}' (vật liệu: {obj.material}) vào lò vi sóng. Vật liệu không an toàn."
                )
        return None

    def _check_dirty_tool(self, step: ExecutionStep, env: EnvironmentState, world: WorldState) -> Optional[PolicyViolation]:
        """
        Rule: Không dùng dụng cụ bẩn tiếp xúc thực phẩm hoặc đồ sạch.
        Case 1: Explicit action (Clean/Mix/Pour) with destination = food-safe surface.
        Case 2: Proactive — PickUp a dirty tool when env has food-safe surfaces
                (legacy plans may not set destination_id, but intent is clear from env).
        """
        obj = env.get_by_id(step.object_id)
        if not obj or obj.is_clean:
            return None

        # Case 1: Explicit contact action
        if step.action in (AllowedAction.Clean, AllowedAction.Mix, AllowedAction.Pour):
            dest = env.get_by_id(step.destination_id) if step.destination_id else None
            if dest and (dest.food_safe or dest.is_clean):
                return PolicyViolation(
                    step_id=step.step_id,
                    reason_code=ReasonCode.DIRTY_TOOL_ON_CLEAN_SURFACE,
                    message=f"Không được dùng '{obj.name}' (bẩn) tiếp xúc với '{dest.name}' (sạch/thực phẩm)."
                )

        # Case 2: Proactive — PickUp dirty tool when food-safe surface exists in env
        # This catches legacy plans that pick up dirty rags/sponges in food environments
        if step.action == AllowedAction.PickUp:
            env_has_food_surface = any(
                o.food_safe and o.id != step.object_id for o in env.objects
            )
            if env_has_food_surface:
                return PolicyViolation(
                    step_id=step.step_id,
                    reason_code=ReasonCode.DIRTY_TOOL_ON_CLEAN_SURFACE,
                    message=f"Không thể dùng '{obj.name}' (bẩn) trong môi trường có bề mặt thực phẩm. Nguy cơ lây nhiễm."
                )
        return None

    def _check_knife_safety(self, step: ExecutionStep, env: EnvironmentState, world: WorldState) -> Optional[PolicyViolation]:
        """Rule: PickUp dao/vật sắc cần xác minh có thớt trong environment."""
        if step.action == AllowedAction.PickUp:
            obj = env.get_by_id(step.object_id)
            if obj and any(k in obj.name.lower() for k in ["knife", "dao", "blade", "sharp", "cutter"]):
                has_cutting_board = any(
                    any(k in o.name.lower() for k in ["cutting board", "thớt", "chopping"])
                    for o in env.objects
                )
                if not has_cutting_board:
                    return PolicyViolation(
                        step_id=step.step_id,
                        reason_code=ReasonCode.KNIFE_WITHOUT_CUTTING_BOARD,
                        message=f"Không thể lấy '{obj.name}' khi không có thớt/khu vực thao tác hợp lệ trong môi trường."
                    )
        return None

    def _check_location_known(self, step: ExecutionStep, env: EnvironmentState) -> Optional[PolicyViolation]:
        """
        Rule: Không PickUp/Place vật thể nếu location đã được thiết lập rõ ràng nhưng không hợp lệ.
        NOTE: Bỏ qua nếu TOÀN BỘ objects trong env đều có location='unknown'
        (backward-compat mode từ List[str] — location chưa có structured data).
        """
        # In backward-compat mode, all objects have location='unknown' by default.
        # Only enforce this rule when at least one object has an explicit known location.
        all_unknown = all(o.location == "unknown" for o in env.objects)
        if all_unknown:
            return None  # Not enough structured data to enforce location check

        if step.action in (AllowedAction.PickUp, AllowedAction.Place):
            obj = env.get_by_id(step.object_id)
            if obj and obj.location == "unknown":
                return PolicyViolation(
                    step_id=step.step_id,
                    reason_code=ReasonCode.UNKNOWN_OBJECT_LOCATION,
                    message=f"Không thể thực hiện '{step.action}' với '{obj.name}' vì vị trí chưa được xác định."
                )
        return None

    def _check_heat_parameters(self, step: ExecutionStep, env: EnvironmentState) -> Optional[PolicyViolation]:
        """Rule: Heat vào lò vi sóng hoặc lò nướng phải có temperature_c hoặc duration_s."""
        if step.action == AllowedAction.Heat and step.destination_id:
            dest = env.get_by_id(step.destination_id)
            # Only enforce if destination is an explicit heating appliance
            is_heating_appliance = dest and any(
                k in dest.name.lower() for k in ["microwave", "oven", "lò", "nướng"]
            )
            if is_heating_appliance:
                has_temp = "temperature_c" in step.parameters
                has_dur  = "duration_s" in step.parameters
                if not has_temp and not has_dur:
                    return PolicyViolation(
                        step_id=step.step_id,
                        reason_code=ReasonCode.MISSING_REQUIRED_PARAMETER,
                        message="Hành động 'Heat' vào thiết bị gia nhiệt phải chỉ định ít nhất một trong: temperature_c hoặc duration_s."
                    )
        return None

    def _check_robot_holds_one(self, step: ExecutionStep, world: WorldState) -> Optional[PolicyViolation]:
        """Invariant: Robot chỉ cầm tối đa 1 vật thể."""
        if step.action == AllowedAction.PickUp and world.robot_holding is not None:
            return PolicyViolation(
                step_id=step.step_id,
                reason_code=ReasonCode.SAFETY_INVARIANT_VIOLATED,
                message=f"Robot đang cầm '{world.robot_holding}', không thể cầm thêm '{step.object_id}'."
            )
        return None

    # ─── State transition ─────────────────────────────────────────────────────

    def _apply_step(self, step: ExecutionStep, world: WorldState) -> WorldState:
        """Cập nhật world state sau mỗi step. Không kiểm tra an toàn ở đây."""
        if step.action == AllowedAction.PickUp:
            world.robot_holding = step.object_id
        elif step.action == AllowedAction.Place:
            if world.robot_holding == step.object_id:
                world.robot_holding = None
        elif step.action == AllowedAction.Heat:
            if step.destination_id and "microwave" in (step.destination_id or ""):
                world.in_microwave = step.object_id
        return world

    # ─── Main check entry point ────────────────────────────────────────────────

    def check(self, steps: List[ExecutionStep], env: EnvironmentState) -> PolicyResult:
        """
        Kiểm tra toàn bộ chuỗi bước hành động. Dừng ngay tại vi phạm đầu tiên.
        """
        if not steps:
            return PolicyResult(status=ResponseStatus.APPROVED)

        world = WorldState(objects={o.id: o for o in env.objects})
        violations: List[PolicyViolation] = []

        for step in steps:
            # Danh sách rule kiểm tra theo thứ tự ưu tiên
            rules = [
                self._check_object_exists(step, env),
                self._check_destination_exists(step, env),
                self._check_microwave_safety(step, env, world),
                self._check_dirty_tool(step, env, world),
                self._check_knife_safety(step, env, world),
                self._check_location_known(step, env),
                self._check_heat_parameters(step, env),
                self._check_robot_holds_one(step, world),
            ]

            step_violations = [r for r in rules if r is not None]
            if step_violations:
                violations.extend(step_violations)
                # Fail-closed: dừng ngay tại vi phạm đầu tiên
                return PolicyResult(
                    status=ResponseStatus.REJECTED,
                    violations=violations
                )

            # Áp dụng state transition
            world = self._apply_step(step, world)

        return PolicyResult(status=ResponseStatus.APPROVED)


# ─── Singleton ───────────────────────────────────────────────────────────────
_safety_engine: Optional[SafetyPolicyEngine] = None

def get_safety_engine() -> SafetyPolicyEngine:
    global _safety_engine
    if _safety_engine is None:
        _safety_engine = SafetyPolicyEngine()
    return _safety_engine
