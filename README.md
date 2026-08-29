# 🤖 Embodied AI Kitchen Robot: Neuro-Symbolic AmbiK Pipeline

> **Hệ thống Xử lý Mơ hồ Ngôn ngữ Tự nhiên & Kiểm chứng An toàn Hình thức cho Robot Nhà Bếp**
> 
> *Tích hợp Semantic Entropy, Conformal Prediction (KnowNo), Formal Safety Verification (CTL Model Checking) và ROS Bridge.*

---

## 📌 1. Tổng quan Dự án (Project Overview)

Dự án phát triển hệ thống điều khiển nhận thức (Cognitive Controller) cho Robot Nhà Bếp dựa trên kiến trúc **Neuro-Symbolic AI**, giải quyết bài toán cốt lõi:
* **Xử lý sự mơ hồ trong câu lệnh tự nhiên:** Khi con người ra lệnh không đầy đủ (*"Pha cà phê"*, *"Hâm nóng súp"*), hệ thống tự động lượng hóa mức độ mơ hồ bằng **Semantic Entropy** ($H(X)$) và **Conformal Prediction** ($1-\alpha=95\%$).
* **Tương tác làm rõ Người - Robot (HRI Clarification):** Chủ động dừng lại và hỏi lại người dùng bằng câu hỏi trắc nghiệm $k$-Choice khi phát hiện mơ hồ về **Sở thích (Preferences)** hoặc **An toàn (Safety)**.
* **Tấm khiên An toàn Toán học Hình thức:** Kiểm chứng bất biến an toàn vật lý bằng **Computation Tree Logic (CTL)** trên cấu trúc Kripke và **SafetyPolicyEngine** tiền điều kiện xác định trước khi cấp phép thực thi cho Robot.
* **Đầu ra Hình thức (LTL/CTL Action Plan):** Xuất chuỗi kế hoạch trừu tượng hóa mệnh đề (Lifted NL: `prop_1 -> prop_2 -> ...`) và ánh xạ sang các ROS Action Goals.

---

## 🏗️ 2. Kiến trúc Pipeline 5 Bước (5-Stage Architecture)

```mermaid
graph TD
    A["1. Input: Lệnh giọng nói / Văn bản + Môi trường bếp"] --> B["Stage 1: Semantic Grounding & Ánh xạ Thực thể"]
    B --> C["Stage 2: Adaptive 2-Tier Early Routing (Conformal Fast Route)"]
    C -->|Rõ ràng: Bypass N=5| E["Stage 4: Disambiguation & Propositional Lifting"]
    C -->|Mơ hồ / Nguy cơ| D["Stage 3: Semantic Entropy (Shannon H)"]
    D --> E
    E --> F["Stage 5: Formal CTL Model Checking & Safety Policy Engine"]
    F -->|APPROVED| G["Output: Kế hoạch An toàn + Chuỗi LTL + ROS Actions"]
    F -->|REJECTED / NEEDS_CLARIFICATION| H["HRI: Hỏi làm rõ / Khóa an toàn"]
```

---

## 🚀 3. Hướng dẫn Cài đặt & Chạy (Quick Start)

### Yêu cầu hệ thống:
* Python 3.10+
* Windows / Linux (Ubuntu) / macOS

### Bước 1: Cài đặt thư viện & Tải Dataset
```bash
# 1. Cài đặt các gói phụ thuộc
pip install -r requirements.txt

# 2. Tải Dataset AmbiK từ repository gốc (nếu chưa có)
python scripts/setup_dataset.py
```

### Bước 2: Khởi động Server AI
```bash
python main.py
```
* Giao diện Web: Truy cập **`http://localhost:8000`**
* Endpoint API Backend: **`http://localhost:8000/api/analyze`**

---

## 🤖 4. Tích hợp Robot / ROS (Embedded Integration)

Toàn bộ tài liệu đặc tả API và mã nguồn kết nối Robot nằm trong thư mục `ros_integration/`:
* **[`ros_integration/API_CONTRACT.md`](./ros_integration/API_CONTRACT.md):** Tài liệu đặc tả hợp đồng dữ liệu chuẩn JSON cho đội ngũ nhúng.
* **[`ros_integration/ambik_ros_bridge.py`](./ros_integration/ambik_ros_bridge.py):** Node cầu nối mẫu bằng Python để kiểm tra điều khiển robot.

### Chạy thử nghiệm ROS Bridge:
```bash
python ros_integration/ambik_ros_bridge.py
```

---

## 📁 5. Cấu trúc Thư mục (Directory Structure)

```text
.
├── main.py                     # FastAPI Backend Server chính
├── ambik_analyzer.py           # Bộ lõi phân tích Neuro-Symbolic & Pipeline 5 bước
├── safety_policy.py            # Động cơ kiểm tra 6 luật an toàn vật lý cứng
├── conformal_calibrator.py     # Bộ tính toán thống kê Conformal Prediction
├── ambik_calib_scores.json     # Bảng điểm Calibration chuẩn
├── data_loader.py              # Module nạp và bóc tách mẫu Dataset AmbiK
├── evaluate_benchmark.py       # Bộ đánh giá định lượng Benchmark Suite (A/B/C)
├── requirements.txt            # Danh sách gói phụ thuộc Python
├── Dockerfile                  # Cấu hình container hóa Docker
├── LICENSE                     # Giấy phép nguồn mở MIT License
├── scripts/
│   ├── setup_dataset.py        # Script tự động clone dataset từ repo tác giả gốc
│   └── run_calibration.py      # Script chạy calibration Conformal
├── schemas/                    # Pydantic Schemas (EnvironmentState, ExecutionStep)
│   ├── __init__.py
│   └── environment.py
├── static/                     # Giao diện Web UI, CSS, JS & Slide báo cáo
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── presentation.html
└── ros_integration/           # Bộ công cụ tích hợp Robot & ROS
    ├── API_CONTRACT.md
    ├── README.md
    └── ambik_ros_bridge.py
```

---

## 📚 6. Nguồn Dữ liệu & Bản quyền Bên thứ ba (Third-Party Attribution)

Dự án này sử dụng và đánh giá thực nghiệm dựa trên tập dữ liệu chuẩn **AmbiK Benchmark**:
* **Tác giả:** Anastasia Ivanova, Eva Bakaeva, Zoya Volovikova, Alexey Kovalev, and Aleksandr Panov.
* **Bài báo:** *"AmbiK: Dataset of Ambiguous Tasks in Kitchen Environment."* Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (**ACL 2025**).
* **Repository gốc:** [https://github.com/cog-model/AmbiK-dataset](https://github.com/cog-model/AmbiK-dataset)
* **arXiv Preprint:** [arXiv:2506.04089](https://arxiv.org/abs/2506.04089)

```bibtex
@inproceedings{ivanova-etal-2025-ambik,
    title = "{A}mbi{K}: Dataset of Ambiguous Tasks in Kitchen Environment",
    author = "Ivanova, Anastasia  and
      Bakaeva, Eva  and
      Volovikova, Zoya  and
      Kovalev, Alexey  and
      Panov, Aleksandr",
    booktitle = "Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics",
    year = "2025"
}
```

> **Phân định đóng góp (Contributions):**
> * **Phần mã nguồn của dự án này:** Toàn bộ kiến trúc nhận thức Neuro-Symbolic (FastAPI Backend, Adaptive Early Routing, Semantic Entropy Clustering, Deterministic Safety Policy Engine, Formal CTL Model Checking, Dynamic Propositional Lifting, ROS Bridge và Web HRI Interface) được thiết kế và hiện thực bởi nhóm tác giả của repository này.
> * **Tập dữ liệu Benchmark:** Thuộc bản quyền và công trình nghiên cứu của nhóm tác giả AmbiK (ACL 2025).

---

## 📄 7. Tham khảo Khoa học Liên quan (Related Literature)

* **KnowNo (Conformal Prediction):** Ren et al., *"Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners"*, Conference on Robot Learning (**CoRL 2023 - Best Student Paper**).
* **Semantic Entropy:** Kuhn et al., *"Detecting hallucinations in large language models using semantic entropy"*, **Nature 2024** & ICLR 2023.
* **AutoTAMP (Formal TAMP):** Chen et al., *"AutoTAMP: Autoregressive Task and Motion Planning with LLMs as Translators and Checkers"*, **ICRA 2024**.
* **SayCan:** Ahn et al., *"Do As I Can, Not As I Say: Grounding Language in Robotic Affordances"*, **CoRL 2022**.

---

## ⚖️ 8. Giấy phép (License)

* Toàn bộ mã nguồn do nhóm phát triển được phát hành theo giấy phép [MIT License](./LICENSE).
* Tập dữ liệu AmbiK tuân thủ theo điều khoản và bản quyền của nhóm tác giả gốc ([cog-model/AmbiK-dataset](https://github.com/cog-model/AmbiK-dataset)).

