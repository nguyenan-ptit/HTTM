# Giai đoạn 1: DroidCam → YOLOv8n → text và giọng tiếng Việt

## 1. Phạm vi và tình trạng kiểm chứng

Prototype chạy trên máy tính Windows. Điện thoại chỉ cung cấp hình qua DroidCam; OpenCV nhận webcam ảo, YOLO trả lớp/hộp bao/confidence, `narration.py` tạo câu tiếng Việt và Windows TTS đọc qua loa/tai nghe máy tính. DroidCam không tự chuyển lời cảnh báo về điện thoại.

Chưa triển khai inference trên điện thoại, GPS, định tuyến, OCR, STT, SOS, đo mét hoặc quyết định hướng tránh. Không có phát hiện không có nghĩa đường trống. `traffic light` không cho biết màu đèn; model COCO không nhận đầy đủ biển báo Việt Nam.

**Trạng thái phần cứng:** Wi-Fi DroidCam, USB DroidCam và việc nghe giọng tiếng Việt thật chưa được kiểm chứng trong lần tạo prototype. Kiểm thử bằng ảnh/hộp bao và engine giả không thay thế các bước nghiệm thu bên dưới. Ghi kết quả thật sau khi có thiết bị; không đánh dấu đạt trước khi thử.

## 2. Chuẩn bị camera

Cài app DroidCam trên điện thoại và [client Windows tương thích](https://droidcam.app/windows/). Nhánh Android hiện tại và Classic dùng app/client riêng. Cho phép camera và quyền kết nối cần thiết; chỉ lấy video, để `Enable Audio` tắt. Giữ nguồn camera khác đã chạy tốt nếu đang dùng.

### 2.1. Wi-Fi

1. Cho điện thoại và máy tính vào cùng mạng nội bộ; máy tính có thể dùng Ethernet. Mở app và client.
2. Client hiện tại: `Add > DroidCam` → `Refresh Device List`; nếu không tìm thấy, dùng `Use WiFi IP` với IP trên app.
3. Classic: chọn `WiFi/LAN`, nhập IP và port thật trên app rồi `Start`. [Hướng dẫn Classic](https://www.dev47apps.com/droidcam/connect/) mô tả giao diện riêng.
4. Xác nhận preview client có chuyển động trước khi chạy Python. Tên mục có thể đổi theo phiên bản. [Nguồn thao tác và xử lý kết nối](https://droidcam.app/help/).

### 2.2. USB

Dùng cáp truyền dữ liệu. Android: bật Developer Options/USB Debugging, chấp nhận cho phép máy tính trên điện thoại; cài driver đúng hãng nếu Windows chưa nhận. Trong client thêm/chọn thiết bị USB và làm mới danh sách. iPhone dùng driver Apple và thao tác `Trust`; không dùng USB Debugging của Android. Xác nhận preview client trước. [Thiết lập USB chính thức](https://droidcam.app/help/#usb).

### 2.3. Nguồn OpenCV và hướng ảnh

Số `--source` là chỉ số camera của OpenCV, không phải port DroidCam. Không mặc định nó luôn là `0` hay `1`. Ví dụ phía dưới dùng `1`; thay bằng nguồn đã xác nhận trên máy.

Thử từng nguồn bằng `--no-detect`, thoát bằng `q` trước khi thử nguồn tiếp theo. Không chạy hai phiên chiếm cùng camera. Dùng vật quen thuộc và chuyển động điện thoại để xác nhận đúng nguồn. Nếu cần, chọn `--backend dshow` hoặc `--backend msmf` thay cho `auto`; kết quả phụ thuộc driver. [OpenCV VideoCapture](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).

Kiểm tra vật nằm trái/phải ảnh và tư thế lắp điện thoại. Chỉ dùng `--rotation 0/90/180/270` và `--mirror` khi cần; sau khi đổi phải kiểm tra lại hướng. Trái/phải là vị trí trong ảnh sau biến đổi đã cấu hình, chưa phải hướng tránh vật cản.

## 3. Môi trường, thư viện và model

### 3.1. Python

Chạy trong thư mục gốc dự án. Giữ `.venv` hiện có. Chỉ tạo môi trường mới theo README khi chưa có môi trường; không tạo lại vì pip đang tải chậm. Xem [README](../README.md) để biết cấu hình và phiên bản dependency thực tế.

```powershell
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
```

### 3.2. Chuẩn bị YOLOv8n

Lệnh tải cần mạng và tạo `yolov8n.pt` cùng thông tin trong `models/manifest.json`. Chỉ dùng model từ nguồn tin cậy; không nạp tệp `.pt` không rõ nguồn.

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --download
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolov8n.pt
```

Kiểm tra nguồn, release model, checksum và giấy phép trong manifest trước khi phân phối. Phiên bản dependency trực tiếp nằm trong `requirements.txt`; phiên bản thực tế của các thư viện được ghi trong record `run` khi dùng `--metrics`. Checksum nhận diện đúng tệp đã dùng; không tự chứng minh model đạt yêu cầu sử dụng. `--inspect` chỉ tính checksum/kích thước, không nạp model hoặc liệt kê lớp. Tham khảo [YOLOv8 chính thức](https://docs.ultralytics.com/models/yolov8/) và [giấy phép Ultralytics](https://www.ultralytics.com/license).

### 3.3. Cấu hình thử trên CPU

Bắt đầu với `--device cpu --imgsz 320`. Ảnh inference nhỏ hơn có thể giảm tải CPU nhưng cũng làm khó nhận vật nhỏ; cần so sánh bằng dữ liệu thật. `--conf 0.45` và `--iou 0.45` là cấu hình thử, không phải ngưỡng đúng cho mọi cảnh. Không thêm NMS lần hai ngoài thư viện chỉ để khớp sơ đồ.

### 3.4. Xử lý pip bị kẹt khi cài thư viện

- `Downloading` còn tăng dung lượng: đang tải; `Retrying`: yêu cầu mạng thất bại; `Building wheel`: đang biên dịch. Đọc log trước khi kết luận.
- Traceback qua `tempfile`, `adjacent_tmp_file`, `pip/_internal/network/cache.py` cho thấy thao tác file tạm cache HTTP liên quan; dùng `--no-cache-dir` để bỏ qua cache đó.
- `--only-binary=:all:` tránh biên dịch từ nguồn và sẽ báo lỗi nếu không có wheel phù hợp. Nó không sửa kẹt ghi cache.
- Dừng lệnh đang kẹt trước khi thử lại. Không chạy nhiều pip cùng môi trường, xóa cache, đổi pip toàn cục hoặc cài lại Python khi chưa có bằng chứng cần làm.
- Nếu không có wheel tương thích, ghi Python/kiến trúc và tên package báo lỗi, đối chiếu phiên bản trong README; không quy ngay cho một phiên bản Python cụ thể.

## 4. Chạy theo từng bước

Chỉ chạy camera và lệnh phát âm thanh khi đang triển khai/kiểm chứng tương ứng. `q` thoát; `m` bật/tắt âm thanh. Đóng phiên trước trước khi mở phiên mới.

**Bước 1 — chỉ xem camera:**

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --no-detect
```

**Bước 2 — YOLO và câu tiếng Việt, tắt tiếng:**

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolov8n.pt --device cpu --imgsz 320 --mute
```

**Bước 3 — kiểm kê và thử tổng hợp giọng vào RAM, không phát loa:**

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --list-voices
```

**Bước 4 — lệnh này phát câu mẫu qua loa/tai nghe máy tính:**

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --test
```

**Bước 5 — chạy toàn luồng:**

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolov8n.pt --device cpu --imgsz 320 --max-age 2 --freeze-after 5 --metrics .tmp/metrics.jsonl
```

`--max-age` giới hạn tuổi ảnh nguồn được dùng cho mô tả; timestamp bắt đầu sau khi máy tính đọc ảnh, không phải lúc cảm biến điện thoại thu hình. `--freeze-after` là ngưỡng phát hiện ảnh lặp hoàn toàn; cảnh thật đứng yên cũng có thể kích hoạt, còn ảnh có overlay thay đổi có thể che mất tình trạng đóng băng. Đây không phải bằng chứng tuyệt đối về kết nối. Khi bị báo ảnh không đổi, kiểm tra preview DroidCam và chuyển động thật. Đặt `--freeze-after 0` sẽ tắt kiểm tra này và mất khả năng phát hiện kiểu ảnh đóng băng đó.

Video hiển thị hộp bao/nhãn tiếng Việt/confidence, câu gửi TTS, trạng thái camera/model/âm thanh và số đo. `--font` chọn tệp phông Unicode khi phông mặc định không hiển thị đủ dấu. Không dùng confidence như xác suất an toàn.

Khi cần cố định backend giọng, dùng `--speech-backend winrt`, `--speech-backend sapi` hoặc `--speech-backend onecore`, cùng `--voice-id` nếu cần; `--backend` của CLI chính chọn backend camera. Chỉ dùng ID đã liệt kê trên máy theo [hướng dẫn giọng Việt](windows-vietnamese-voice.md).

## 5. Nghiệm thu thực tế

| Hạng mục | Cách kiểm tra và bằng chứng cần ghi | Trạng thái ban đầu |
| --- | --- | --- |
| Nguồn camera | Hình đang chuyển động từ đúng điện thoại, chỉ số nguồn, backend, hướng ảnh | Chưa kiểm chứng |
| Wi-Fi | Ngắt/kết nối lại mạng; trạng thái mất dữ liệu và lời cũ bị hủy | Chưa kiểm chứng |
| USB | Rút/cắm lại cáp; trạng thái mất dữ liệu và lời cũ bị hủy | Chưa kiểm chứng |
| YOLO | Hộp bao/nhãn/confidence thuộc đúng ảnh, không dùng kết quả phiên cũ | Chưa kiểm chứng với camera thật |
| Text | Tiếng Việt có dấu; trái/giữa/phải khớp vật; không lặp mọi frame | Cần thử cùng ảnh thật |
| Giọng | Đúng `vi`/`vi-VN`, câu nghe khớp câu hiện, đúng loa/tai nghe | Chưa nghe thực tế |
| Hủy và lỗi | Thử `m`, `--mute`, mất camera, model lỗi, engine lỗi, thoát; video/text tiếp tục khi TTS lỗi | Cần thử tích hợp |
| Hiệu năng | Ghi Camera FPS, YOLO FPS, inference ms, tuổi ảnh, cấu hình và thời lượng | Chưa có số đo camera thật |

Chỉ cần thử phương thức kết nối đang dùng; phương thức chưa thử phải giữ trạng thái chưa kiểm chứng. Thử trong môi trường kiểm soát, chưa dùng luồng chưa nghiệm thu để chỉ dẫn đi bộ.

Trong báo cáo ghi Windows, điện thoại, phiên bản app/client, phương thức kết nối, model/checksum, runtime/backend, độ phân giải, `imgsz`, confidence/IoU, thời lượng và điều kiện ánh sáng. Tách Camera FPS khỏi YOLO FPS; `inference_ms` là thời gian lời gọi predict và adapter, chưa phải đo riêng kernel GPU hoặc độ trễ toàn luồng. Metrics JSONL ghi theo chu kỳ khoảng một giây và có bản tổng kết cuối phiên, không ghi ảnh hay chi tiết từng nhãn. Có thể chạy lại cùng đường dẫn metrics: chương trình tự thêm `-1`, `-2`… khi tệp đã có và in tên tệp thực tế, giữ nguyên log cũ. Nếu đo đến âm thanh, nêu rõ mốc đầu/cuối và cách đo; không báo p50/p95 từ dữ liệu chưa thu.

## 6. Khi không có hình hoặc có lỗi

Kiểm tra preview client trước rồi mới OpenCV. Xem lại IP/mạng, cáp/quyền, nguồn camera, app/client còn chạy và ứng dụng khác có chiếm camera không. Với Windows kiểm tra quyền camera cho ứng dụng desktop. Khi preview đã tốt mà Python chưa đọc được, thử backend/source phù hợp; không quy lỗi cho YOLO trước khi có ảnh.

Nếu giật, so sánh `--no-detect` với nhận diện; giảm cấu hình video hoặc thử USB rồi đo lại. Không hứa mức FPS. Nếu giọng lỗi, dùng `--mute` để kiểm tra video/text và đọc [hướng dẫn giọng Việt](windows-vietnamese-voice.md). Xem [luồng mô tả](object-narration.md) và [kế hoạch đánh giá biển báo](traffic-sign-evaluation.md) cho các giới hạn tiếp theo.
