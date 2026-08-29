#!/usr/bin/env python3
"""
ambik_ros_bridge.py
=============================================================================
Bridge Node kết nối giữa Mô phỏng Robot trong ROS (ROS 1 / ROS 2) và 
Backend AmbiK Neuro-Symbolic Disambiguation Engine.
=============================================================================
"""

import sys
import json
import time
import requests
from typing import List, Dict, Any

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AMBIK_API_URL = "http://localhost:8000/api/analyze"

class AmbiKRobotBridge:
    def __init__(self, api_url: str = AMBIK_API_URL):
        self.api_url = api_url
        print(f"[AmbiK-ROS-Bridge] Khởi tạo kết nối tới: {self.api_url}")

    def execute_nlp_command(self, voice_text: str, environment_objects: List[str]) -> Dict[str, Any]:
        """
        Gửi câu lệnh giọng nói/văn bản và trạng thái môi trường tới AmbiK Backend.
        """
        print(f"\n[AmbiK-ROS-Bridge] 🎙️ Đang gửi câu lệnh: \"{voice_text}\"")
        print(f"[AmbiK-ROS-Bridge] 🍳 Môi trường bếp: {environment_objects}")

        payload = {
            "input_type": "text",
            "input_content": voice_text,
            "environment": environment_objects
        }

        try:
            start_time = time.time()
            response = requests.post(self.api_url, json=payload, timeout=10.0)
            latency = (time.time() - start_time) * 1000.0

            if response.status_code != 200:
                print(f"[AmbiK-ROS-Bridge] ❌ Lỗi HTTP {response.status_code}: {response.text}")
                return {"success": False, "error": response.text}

            data = response.json()
            request_id = data.get("request_id", "unknown")
            status = data.get("status", "UNKNOWN")
            reason_code = data.get("reason_code", "UNKNOWN")
            analysis = data.get("analysis", {})

            print(f"[AmbiK-ROS-Bridge] 📨 Response [Request ID: {request_id} | Status: {status} | Reason: {reason_code}]")

            # 1. REJECTED: Vi phạm an toàn hoặc điều kiện tiên quyết không thỏa mãn
            if status == "REJECTED":
                print(f"\n[AmbiK-ROS-Bridge] 🚫 CẢNH BÁO AN TOÀN: Yêu cầu bị từ chối! Reason: {reason_code}")
                return {
                    "success": False,
                    "status": "REJECTED",
                    "reason_code": reason_code,
                    "request_id": request_id,
                    "safe": False,
                    "plan": []
                }

            # 2. NEEDS_CLARIFICATION: Câu lệnh mơ hồ, cần hỏi lại người dùng
            if status == "NEEDS_CLARIFICATION":
                entropy = analysis.get("entropy_score", 0.0)
                k_choice = analysis.get("k_choice_question", {})
                print(f"\n[AmbiK-ROS-Bridge] ❓ PHÁT HIỆN MƠ HỒ (Reason: {reason_code} | Entropy H={entropy:.2f}):")
                if k_choice and k_choice.get("question"):
                    print(f"   -> Câu hỏi HRI: {k_choice.get('question')}")
                    for opt in k_choice.get("options", []):
                        print(f"      [Lựa chọn {opt.get('key')}]: {opt.get('label')}")
                return {
                    "success": True,
                    "status": "NEEDS_CLARIFICATION",
                    "reason_code": reason_code,
                    "request_id": request_id,
                    "needs_clarification": True,
                    "question": k_choice.get("question") if k_choice else "Cần làm rõ yêu cầu",
                    "options": k_choice.get("options", []) if k_choice else [],
                    "plan": []
                }

            # 3. APPROVED: Kiểm tra các điều kiện an toàn trước khi chấp thuận kế hoạch
            is_safe = analysis.get("verified_safe", False)
            plan = analysis.get("safe_execution_plan", [])

            if status == "APPROVED":
                if not is_safe or len(plan) == 0:
                    print(f"[AmbiK-ROS-Bridge] ❌ Lỗi bất biến: Status APPROVED nhưng verified_safe={is_safe}, steps={len(plan)}!")
                    return {
                        "success": False,
                        "status": "REJECTED",
                        "reason_code": "INVARIANT_VIOLATION",
                        "request_id": request_id,
                        "safe": False,
                        "plan": []
                    }

                print(f"\n[AmbiK-ROS-Bridge] ✅ ĐÃ PHÊ DUYỆT KẾ HOẠCH AN TOÀN ({len(plan)} bước) [Độ trễ: {latency:.1f}ms]:")
                for step in plan:
                    print(f"   Step {step.get('step')}: [{step.get('action')}] -> Target: {step.get('target')} ({step.get('note', '')})")

                return {
                    "success": True,
                    "status": "APPROVED",
                    "reason_code": reason_code,
                    "request_id": request_id,
                    "safe": True,
                    "needs_clarification": False,
                    "plan": plan,
                    "classification": analysis.get("overall_classification"),
                    "entropy_score": analysis.get("entropy_score", 0.0)
                }

            return {
                "success": False,
                "status": status,
                "reason_code": reason_code,
                "request_id": request_id,
                "error": f"Unknown status: {status}"
            }

        except Exception as e:
            print(f"[AmbiK-ROS-Bridge] ❌ Lỗi kết nối mạng: {e}")
            return {"success": False, "error": str(e)}

    def dispatch_to_gazebo_sim(self, plan: List[Dict[str, Any]]):
        """
        Mô phỏng gửi từng bước hành động tới ROS Action Server / MoveBase / MoveIt.
        """
        print("\n[AmbiK-ROS-Bridge] 🚀 BẮT ĐẦU ĐIỀU KHIỂN ROBOT TRONG MÔ PHỎNG (GAZEBO/RVIZ):")
        for step in plan:
            action = step.get("action")
            target = step.get("target")
            print(f"   ▶️ [ROS Action] Robot executing: {action} on '{target}'...")
            time.sleep(0.5)
        print("   🏁 [ROS Action] ĐÃ HOÀN TẤT KẾ HOẠCH AN TOÀN TRÊN ROBOT!")


if __name__ == "__main__":
    bridge = AmbiKRobotBridge()
    env = ["a ceramic mug", "a glass mug", "coffee machine", "kitchen table"]

    print("=" * 60)
    print("DEMO 1: CÂU LỆNH RÕ RÀNG (UNAMBIGUOUS FAST ROUTE)")
    print("=" * 60)
    res1 = bridge.execute_nlp_command("Lấy ly sứ trên bàn giúp tôi", env)
    if res1.get("safe") and res1.get("plan"):
        bridge.dispatch_to_gazebo_sim(res1.get("plan"))

    print("\n" + "=" * 60)
    print("DEMO 2: CÂU LỆNH MƠ HỒ CẦN GIẢI NGHĨA (PREFERENCES)")
    print("=" * 60)
    res2 = bridge.execute_nlp_command("Pha cho tôi 1 ly cà phê", env)
