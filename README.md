# Prototype mô tả vật thể bằng tiếng Việt

Luồng hiện tại: **camera điện thoại → DroidCam → OpenCV → YOLO11s trên máy tính → câu tiếng Việt → TTS Windows → loa/tai nghe máy tính**. Chương trình mô tả loại vật thể và vị trí trong ảnh. Âm thanh không tự truyền về điện thoại qua DroidCam.

Đã triển khai camera tự kết nối lại, nhận diện bất đồng bộ, nhãn Unicode, tạo câu, quản lý lời đọc và ghi số đo. Mức kiểm chứng thực tế được ghi tại [báo cáo kiểm chứng](docs/verification.md). Chưa có bằng chứng chạy toàn luồng với điện thoại và nghe tiếng Việt thành công trên máy này.

## Chuẩn bị môi trường

Windows x64, CPython 3.11–3.14, DroidCam app/client tương thích. Dùng môi trường `.venv` đang có; chỉ tạo khi chưa tồn tại:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
```

[requirements.txt](requirements.txt) cố định phiên bản dependency trực tiếp, gồm cặp torch/torchvision tương ứng. Đây chưa phải lock đầy đủ dependency bắc cầu. Sau khi cài thành công, có thể lưu môi trường đã resolve bằng `python -m pip freeze > requirements-resolved.txt` và kiểm tra trước khi dùng trên máy khác. Không cài `opencv-python-headless` cho cửa sổ video. TTS dùng Windows PowerShell 5.1 và API giọng có sẵn, không cần `pyttsx3` hoặc dịch vụ cloud. Chương trình không cần API key.

Nếu pip lỗi, xem [chẩn đoán cài thư viện](docs/phase-1-phone-camera-yolo.md#34-xử-lý-pip-bị-kẹt-khi-cài-thư-viện). Không tạo lại `.venv`, xóa cache hoặc đổi Python khi chưa đọc lỗi cụ thể.

## Chạy theo từng bước

1. Mở DroidCam trên điện thoại và client Windows, xác nhận preview chuyển động. Dùng Wi-Fi nội bộ hoặc USB, chỉ bật video. Xem [hướng dẫn kết nối](docs/phase-1-phone-camera-yolo.md).
2. Xác định nguồn OpenCV thực tế. **Số `1` bên dưới chỉ là ví dụ**, không phải port DroidCam. Mỗi lần chỉ chạy một phiên; nhấn `q` trước khi đổi nguồn.

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --no-detect
```

3. Chuẩn bị model một lần khi có Internet; camera không tự tải model:

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --download
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolo11s.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --classes yolo11s.pt
```

Model mặc định `yolo11s.pt` (chọn bằng benchmark, xem bên dưới); `--name yolo11m.pt` hoặc `yolo11n.pt` để đổi cỡ. Model được tải từ release `v8.3.0` của [Ultralytics assets](https://github.com/ultralytics/assets/releases/tag/v8.3.0); công cụ ghi nguồn, kích thước, SHA-256 đo được và giấy phép vào `models/manifest.json`. SHA đo sau tải chưa phải so sánh với checksum độc lập của nhà phát hành; có thể thêm `--sha256 HEX` khi có digest đáng tin cậy. Nếu đã có model, dùng `--inspect`, kiểm tra nguồn/giấy phép và truyền đường dẫn bằng `--model`. `--classes` cần dependency inference và nạp model để liệt kê lớp thực tế, khác với `--inspect` chỉ đọc byte. Chỉ nạp `.pt` từ nguồn đáng tin cậy. Xem [ghi chú model](models/README.md).

4. Kiểm tra nhận diện và câu chữ khi tắt tiếng:

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolo11s.pt --mute
```

5. Sau khi thoát cửa sổ, kiểm tra riêng giọng. Lệnh đầu chỉ kiểm kê/tổng hợp RAM; lệnh thứ hai **phát mẫu qua loa/tai nghe máy tính**:

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --list-voices
.\.venv\Scripts\python.exe -m prototype.speech --test
```

Phân biệt giọng đã cài, API thấy giọng, tổng hợp được và người nghe xác nhận. Xem [chẩn đoán tiếng Việt Windows](docs/windows-vietnamese-voice.md). Lần chẩn đoán đầu có lỗi WinRT/OneCore; sau đó người dùng xác nhận nghe được câu test. Không dùng kết quả chẩn đoán cũ để kết luận âm thanh hiện tại vẫn lỗi, và không tự chuyển sang giọng Anh.

6. Chạy toàn luồng khi các bước trên đã đạt:

```powershell
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolo11s.pt --metrics reports/session.jsonl
```

Nhấn **`m`** để bật/tắt tiếng, **`q`** hoặc đóng cửa sổ để thoát. `--no-detect` không phát giọng. Khi TTS lỗi, video và câu mô tả tiếp tục; sau khi khắc phục nguyên nhân có thể tắt rồi bật lại bằng `m` để thử lại. Không chạy nhiều phiên chiếm cùng camera.

Nếu `speech --test` nghe được nhưng cửa sổ camera không có tiếng, xem câu mô tả và trạng thái âm thanh. Bản sửa bộ điều phối giữ câu đang đọc khi ảnh mới tiếp tục xác nhận các loại/vị trí trong câu; TTL vẫn là 2 giây kể từ **bằng chứng xác nhận mới nhất**, không kéo dài chỉ vì thời gian xử lý. Nhóm đang đọc biến mất, ảnh hết hạn, camera/model lỗi, đổi phiên hoặc mute vẫn hủy lời. Chống lặp tính từ lúc worker hoàn tất thành công; một lần khởi động bị hủy không khóa câu đó thêm 6 giây.

Bạn có thể dùng lại cùng đường dẫn, ví dụ `--metrics reports/session-audio.jsonl`: khi tệp đã có, chương trình tự tạo `session-audio-1.jsonl`, `session-audio-2.jsonl`… và in đường dẫn thực tế trong terminal. Log cũ được giữ nguyên. Các trường `speech_started`, `speech_completed`, `speech_cancelled`, `speech_last_event`, `speech_evidence_age_ms` giúp phân biệt khởi động, hoàn tất và bị hủy; không lưu text hay nhãn chi tiết. `speech_completed` là worker/API báo hoàn tất, chưa phải người dùng xác nhận nghe. Nếu test có chọn `--backend onecore`, lệnh camera cần chọn tương ứng bằng `--speech-backend onecore`.

## Tùy chỉnh và dữ liệu

Chạy `python -m prototype.main --help` để xem toàn bộ tùy chọn. Các mục thường dùng:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--backend auto/dshow/msmf` | Backend camera, thay khi driver không tương thích. |
| `--rotation 90`, `--mirror` | Xoay trước, lật ngang sau; nhận diện/mô tả cùng ảnh đã biến đổi. Kiểm chứng trái/phải thực tế. |
| `--imgsz 640`, `--conf 0.30`, `--iou 0.45` | Mặc định mới. 320 từng bỏ sót vật; conf thấp được bù bằng tracker (chỉ báo vật đã xác nhận qua ≥2 ảnh). |
| `--device auto/cpu/0` | `auto` dùng GPU CUDA nếu có, không thì CPU. |
| `--no-track`, `--walking-only`, `--no-enhance` | Tắt theo dõi ByteTrack; chỉ giữ lớp COCO liên quan người đi bộ (mặc định đọc cả 80 lớp, gồm đồ vật trong nhà); tắt cân bằng sáng tự động cho ảnh tối. |
| `--max-age 2` | Thời hạn tối đa tính từ ngay sau `OpenCV.read()`, không phải từ lúc inference xong. |
| `--freeze-after 5` | Tạm dừng mô tả nếu ảnh lặp tuyệt đối 5 giây; có thể báo nhầm cảnh tĩnh hoàn toàn. `0` tắt kiểm tra này và không phát hiện được kiểu đứng ảnh đó. |
| `--speech-backend auto/winrt/sapi/onecore` | `auto` = worker WinRT chạy sẵn, đọc trong ~20 ms sau khi có câu; `winrt/sapi/onecore` = engine cũ, mỗi câu một tiến trình PowerShell (chậm 1–2 giây). Chỉ chọn `vi`/`vi-VN`. |
| `--voice-id ID`, `--font PATH` | Chọn giọng Việt đã kiểm kê hoặc phông Unicode hỗ trợ tiếng Việt. |
| `--metrics PATH` | JSONL số đo mỗi giây và thống kê cuối phiên. Tự thêm số vào tên khi trùng, giữ nguyên tệp cũ; không lưu ảnh hoặc nội dung lời đọc. |

Giao diện hiển thị kết quả YOLO trên **đúng ảnh nguồn của kết quả**, vì vậy tốc độ ảnh có hộp bao phụ thuộc inference. Camera vẫn lấy ảnh mới trên worker riêng. Khi chưa có kết quả mới/hết hạn, giao diện trở về ảnh camera còn mới và bỏ hộp bao. Hàng đợi không tích ảnh cũ. Nếu driver treo khi đọc, UI vẫn báo mất dữ liệu và hủy lời; ứng dụng không mở camera thứ hai tranh chấp với driver đang treo.

Camera FPS, YOLO FPS là tốc độ đo ở máy tính; `inference_ms` là thời gian toàn lời gọi predict và adapter hậu xử lý. Tuổi ảnh không bao gồm độ trễ chưa biết của điện thoại/DroidCam. Summary p50/p95 chỉ tính tối đa 10000 kết quả khác nhau được hiển thị cuối phiên; không phải độ trễ đầu cuối đến âm thanh.

Không lưu/tải ảnh camera hoặc ghi âm mặc định. File số đo chỉ tạo khi truyền `--metrics`. Không đưa URL có mật khẩu, khóa hoặc dữ liệu riêng tư vào repository. YOLO/TTS hoạt động cục bộ sau khi chuẩn bị model/gói giọng; DroidCam vẫn cần kết nối Wi-Fi nội bộ hoặc USB đã chọn.

## Đánh giá nhận diện

Số đo trên máy dev (CPU, không GPU; ảnh mẫu `bus.jpg`/`zidane.jpg` của Ultralytics, 4 người + 1 xe buýt; chỉ là chỉ báo tương đối, chưa phải độ chính xác trên đường thật):

| Cấu hình | ms/ảnh | Kết quả `bus.jpg` |
| --- | --- | --- |
| yolov8n, 320 (cũ) | 31 | bỏ sót 1 người |
| yolov8n, 640 | 55 | đủ, độ tin cậy thấp hơn |
| **yolo11s, 640 (mới)** | 109 | đủ, confidence cao |
| yolo11m, 640 | 247 | đủ, chậm ~4 ảnh/s |

Chạy toàn luồng (camera+tracking+câu) với video giả đạt ~5 ảnh/s do camera tranh CPU. Cân bằng sáng chỉ có lợi khi ảnh rất tối (độ sáng nhân ≤0.1). Tự đo lại bằng ảnh của bạn: `python -m tools.benchmark --images a.jpg --models yolo11n.pt yolo11s.pt --imgsz 320 640`.

Chưa kiểm chứng: camera DroidCam thật, vật cản ngoài COCO (cột, bậc, hố), biển Việt Nam. Muốn nhận các vật đó cần fine-tune với ảnh tự gán nhãn.

## Kiểm thử và cấu trúc

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q prototype tests
```

Kiểm thử tự động dùng camera/model/engine giả để kiểm tra phiên, tọa độ, tuổi ảnh và hủy; không chứng minh thiết bị thật hoạt động. Kiểm thử có OpenCV/Pillow có thể bỏ qua nếu thiếu dependency và phải được ghi rõ.

```text
prototype/camera.py       một chủ sở hữu camera, ảnh mới nhất, reconnect
prototype/detector.py     adapter YOLO, bbox trên ảnh nguồn
prototype/pipeline.py     inference worker, loại kết quả cũ/sai phiên
prototype/narration.py    ánh xạ 80 nhãn COCO và câu tiếng Việt
prototype/feedback.py     chống lặp, TTL, hủy, một câu chờ mới nhất
prototype/speech.py       engine/CLI TTS và worker windows_speech.ps1
prototype/display.py      video, hộp bao và chữ Unicode
prototype/main.py         CLI, ghép luồng, số đo
prototype/model_tools.py  tải có chủ đích và checksum model
tests/                    kiểm thử hành vi
docs/                     hướng dẫn và kết quả kiểm chứng
```

Luồng tạo câu được mô tả tại [object-narration.md](docs/object-narration.md). Việc đánh giá `stop sign`, `traffic light` và biển Việt Nam còn thiếu nằm tại [traffic-sign-evaluation.md](docs/traffic-sign-evaluation.md). Chưa nhận biết màu đèn, mọi biển báo Việt Nam, khoảng cách hay hướng tránh. Các phần Android, GPS, OCR, STT, SOS và INT8 chưa triển khai trong nhiệm vụ này.
#   H T T M  
 