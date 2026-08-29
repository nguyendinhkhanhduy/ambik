# 📖 HƯỚNG DẪN HUẤN LUYỆN MÔ HÌNH AMBIK SIÊU TỐC TRÊN GOOGLE COLAB

Tài liệu này hướng dẫn cách chạy file Notebook **`train_ambik_classifier.ipynb`** trên Google Colab với tính năng **Tùy chỉnh số câu train (Train siêu tốc trong 10-30 giây)** và **Đổi mô hình 1-Click**.

---

## 📂 1. CÁC TỆP CẦN TẢI LÊN GOOGLE COLAB

1. 📓 **File Notebook:** `colab/train_ambik_classifier.ipynb`
2. 📄 **File Dữ liệu:** `AmbiK-dataset/AmbiK_data.csv`

---

## ⚡ 2. CÁCH CHỈNH SỐ CÂU TRAIN & ĐỔI TÊN MÔ HÌNH (TẠI CELL 2)

Mở Notebook trên Colab, tại **Khối lệnh số 2 (Cell 2)**, bạn có thể tùy chỉnh:

```python
# 1. TÊN MÔ HÌNH BẠN MUỐN DÙNG:
MODEL_NAME = "microsoft/deberta-v3-base"

# 2. SỐ CÂU DỮ LIỆU MUỐN TRAIN (TÙY CHỈNH TẠI ĐÂY):
# 👉 Đặt 100 hoặc 200 câu để train SIÊU NHANH trong 10 - 30 giây!
# 👉 Đặt None nếu muốn train toàn bộ 2.000 câu.
MAX_SAMPLES = 200

# 3. SỐ EPOCHS (Chu kỳ huấn luyện):
NUM_EPOCHS = 2
```

👉 **Hệ thống sẽ tự động trích xuất đúng số câu bạn yêu cầu, chia đều cân bằng giữa 4 nhóm nhãn và chạy train siêu tốc trên GPU T4!**

---

## 🚀 3. CÁC BƯỚC THỰC HIỆN TRÊN GOOGLE COLAB

1. **Bước 1:** Truy cập [https://colab.research.google.com/](https://colab.research.google.com/) $\rightarrow$ Chọn tab **Upload** $\rightarrow$ Chọn file `train_ambik_classifier.ipynb`.
2. **Bước 2:** Bật GPU: Menu **Runtime** $\rightarrow$ **Change runtime type** $\rightarrow$ Chọn **T4 GPU** $\rightarrow$ Bấm **Save**.
3. **Bước 3:** Bấm vào biểu tượng **📁 Files (bên trái)** $\rightarrow$ Kéo thả file `AmbiK_data.csv` vào.
4. **Bước 4:** Chỉnh số câu `MAX_SAMPLES = 100` hoặc `200` ở Cell 2 $\rightarrow$ Bấm **`Ctrl + F9`** (Run All).
5. **Bước 5:** Sau khi train xong (~20 giây), file `ambik_custom_model.zip` sẽ tự động tải về máy tính của bạn!
