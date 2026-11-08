# Hệ Thống Thông Minh Hỗ Trợ Người Khiếm Thị (HTTM)

Hệ thống nhận diện vật cản thời gian thực từ camera điện thoại (qua DroidCam) hoặc webcam, phân tích vùng an toàn bằng **YOLO11 (`yolo11n.pt`)** và phát âm thanh **đề xuất lối đi bằng tiếng Việt** qua giọng đọc cục bộ Windows hoặc **VieNeu Cloud API** (giọng `"Nhật Phong"`).

Luồng xử lý:
**Camera điện thoại (DroidCam) → OpenCV → YOLO11n → Phân vùng vật cản (Trái / Giữa / Phải) → Đề xuất hướng đi → Phát giọng nói (RAM Cache)**.

---

## Tính năng nổi bật

- **Đồng nhất mọi đối tượng thành `"vật cản"`:** Toàn bộ 80 lớp COCO đều được quy về `"vật cản"` trên cả khung hình hiển thị lẫn âm thanh cảnh báo.
- **Đề xuất lối đi trực tiếp:**
  | Vị trí có vật cản | Câu hướng dẫn phát ra |
  | --- | --- |
  | Chỉ bên trái | *"Có vật cản ở bên trái, đi sang phải."* |
  | Chỉ bên phải | *"Có vật cản ở bên phải, đi sang trái."* |
  | Chỉ ở giữa | *"Có vật cản phía trước, đi sang trái hoặc phải."* |
  | Bên trái + ở giữa | *"Có vật cản bên trái và phía trước, đi sang phải."* |
  | Ở giữa + bên phải | *"Có vật cản phía trước và bên phải, đi sang trái."* |
  | Hai bên trái & phải (ở giữa trống) | *"Có vật cản hai bên, đi thẳng."* |
  | Cả 3 vùng (trái + giữa + phải) | *"Có vật cản chắn lối, dừng lại."* |
  | Không có vật cản | Giữ im lặng (không báo "an toàn" giả) |
- **Chống rung camera khi di chuyển:**
  - **Đọc trọn câu (`finish_utterance=True`):** Khi đã bắt đầu phát cảnh báo, hệ thống đọc hết câu hướng dẫn mà không bị ngắt quãng nếu tay cầm điện thoại bị rung làm mất dấu tạm thời.
  - **Giữ trạng thái hiển thị (`--hold-seconds 0.8`):** Giữ câu hướng dẫn trên màn hình thêm 0.8 giây qua các khung hình nhòe.
  - **Ngưỡng nhạy cao hơn (`--conf 0.35`):** Giúp bắt được vật cản ngay cả khi ảnh hơi mờ do bước đi.
- **Phát âm thanh tức thì với RAM Cache:**
  - Âm thanh WAV sau lần tổng hợp đầu tiên được lưu trong RAM và phát lại trực tiếp qua `winmm` (độ trễ **< 0.02 giây**), không tốn thời gian gọi lại API hay mở lại tiến trình PowerShell.

---

## 1. Cài đặt môi trường

Yêu cầu: Windows x64, Python 3.11–3.14.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt
```

---

## 2. Chuẩn bị Model (`yolo11n.pt`)

Tải model `yolo11n.pt` (hoặc `yolo11s.pt`, `yolov8n.pt`) về máy trước khi chạy:

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --download
```

Kiểm tra checksum hoặc danh sách lớp của model:
```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolo11n.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --classes yolo11n.pt
```

---

## 3. Hướng dẫn chạy chương trình

### Bước 1: Kiểm tra cổng camera (DroidCam / Webcam)
Mở DroidCam trên điện thoại và máy tính, sau đó thử xem camera ở cổng số mấy (`0` hoặc `1`):
```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --no-detect
```
*(Nhấn `q` để đóng cửa sổ sau khi kiểm tra).*

### Bước 2: Chạy hệ thống nhận diện và dẫn đường

#### Cách A — Dùng giọng `"Nhật Phong"` qua VieNeu Cloud API
Đặt biến môi trường `VIENEU_API_KEY` và chạy với `--tts vieneu`:

```powershell
$env:VIENEU_API_KEY = "vn_sk_điền_mã_api_key_của_bạn_vào_đây"
.\.venv\Scripts\python.exe -m prototype.main --source 1 --tts vieneu
```

*(Nếu muốn lưu cố định API key vào Windows để các lần sau không cần nhập lại)*:
```powershell
[Environment]::SetEnvironmentVariable("VIENEU_API_KEY", "vn_sk_điền_mã_api_key_của_bạn_vào_đây", "User")
```

#### Cách B — Dùng giọng tiếng Việt có sẵn của Windows (Offline, không cần API key)
```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --tts windows
```

Kiểm tra riêng giọng Windows trên máy:
```powershell
.\.venv\Scripts\python.exe -m prototype.speech --list-voices
.\.venv\Scripts\python.exe -m prototype.speech --test
```

### Phím tắt trên cửa sổ hiển thị
- **`m`**: Bật / tắt âm thanh đọc.
- **`q`**: Thoát chương trình.

---

## 4. Các tham số dòng lệnh thường dùng

Chạy `.\.venv\Scripts\python.exe -m prototype.main --help` để xem đầy đủ.

| Tham số | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `--source` | *(Bắt buộc)* | Số thứ tự camera OpenCV (`0`, `1`...) hoặc đường dẫn video/URL. |
| `--model` | `yolo11n.pt` | Đường dẫn tệp model `.pt` cục bộ (`yolo11n.pt`, `yolo11s.pt`, `yolov8n.pt`). |
| `--imgsz` | `320` | Kích thước ảnh đưa vào YOLO (bội số của 32; tăng lên `480` hoặc `640` để bắt vật ở xa tốt hơn). |
| `--conf` | `0.35` | Ngưỡng độ tự tin nhận diện `(0, 1]`. |
| `--tts` | `windows` | Nguồn giọng đọc: `windows` (cục bộ) hoặc `vieneu` (VieNeu Cloud API). |
| `--vieneu-voice` | `Nhật Phong` | Tên giọng đọc khi dùng `--tts vieneu`. |
| `--vieneu-speed` | `1.0` | Tốc độ đọc VieNeu (`0.5` – `3.0`). |
| `--hold-seconds` | `0.8` | Thời gian (giây) giữ thông báo khi camera rung làm mất dấu tạm thời. |
| `--repeat-interval` | `2.5` | Khoảng thời gian (giây) chờ trước khi nhắc lại cùng một câu hướng dẫn. |
| `--rotation` | `0` | Xoay ảnh trước khi nhận diện (`0`, `90`, `180`, `270`). |
| `--mirror` | `False` | Lật ngang ảnh trước khi nhận diện và mô tả. |
| `--mute` | `False` | Khởi động ở chế độ tắt tiếng (bấm `m` để bật lại). |
| `--metrics` | `None` | Đường dẫn xuất log số đo hiệu năng dạng JSONL (VD: `reports/session.jsonl`). |

---

## 5. Cấu trúc mã nguồn & Kiểm thử

```text
prototype/
├── camera.py          # Luồng đọc camera riêng biệt, tự kết nối lại khi đứt quãng
├── detector.py        # Adapter YOLO11/YOLOv8, ánh xạ tọa độ khung bao về ảnh gốc
├── pipeline.py        # Worker nhận diện khung hình mới nhất, tự phục hồi khi lỗi tạm thời
├── narration.py       # Quy đổi vật cản theo vùng Trái/Giữa/Phải và tạo câu đề xuất lối đi
├── feedback.py        # Quản lý phát giọng nói, chống rung, đọc trọn câu và chống lặp
├── speech.py          # Engine TTS Windows cục bộ (kèm RAM cache) và công cụ kiểm tra giọng
├── vieneu_speech.py   # Engine TTS gọi VieNeu Cloud API (giọng Nhật Phong, kèm RAM cache)
├── display.py         # Giao diện OpenCV + Pillow hiển thị khung "vật cản" và thông số
├── main.py            # CLI chính, kết nối các worker và ghi nhận số đo
└── model_tools.py     # Tải model từ release cố định và kiểm tra SHA-256
tests/                 # Bộ 102 unit & integration tests
docs/                  # Tài liệu thiết kế và báo cáo kiểm chứng
```

Chạy toàn bộ bộ kiểm thử tự động:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
