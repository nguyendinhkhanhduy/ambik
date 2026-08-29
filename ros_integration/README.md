# AmbiK Neuro-Symbolic ROS Integration Guide

Hướng dẫn tích hợp Backend AmbiK (Xử lý mơ hồ ngôn ngữ & Kiểm chứng An toàn LTL) với Mô phỏng Robot trong ROS (Gazebo / RViz / MoveIt).

## 1. Khởi động AmbiK Backend Server
```bash
python -m uvicorn main:app --reload --port 8000
```
API Documentation: `http://localhost:8000/docs`

## 2. Kết nối từ ROS Node
Chạy script cầu nối mẫu:
```bash
python ros_integration/ambik_ros_bridge.py
```

## 3. Cấu trúc Kế hoạch Hành động gửi cho ROS
- `FindObject`: Điều hướng Robot tới vị trí đối tượng (`MoveBaseGoal`).
- `PickUp`: Gắp vật thể bằng cánh tay Robot (`MoveIt Pick Goal`).
- `CookObject` / `Operate`: Kích hoạt thiết bị nhà bếp.
- `PutObject`: Đặt vật thể lên vị trí mục tiêu (`MoveIt Place Goal`).
