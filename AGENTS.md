# AGENTS.md — Ứng dụng AI hỗ trợ dẫn đường cho người khiếm thị

## 0. Ưu tiên hiện tại: DroidCam → YOLO → chữ tiếng Việt → giọng cảnh báo tiếng Việt

Người dùng chọn prototype trên máy tính: điện thoại thu hình qua DroidCam; Python + OpenCV + YOLO11s trên máy tính nhận diện vật thể, tạo câu tiếng Việt có dấu và đọc câu đó để thông báo cho người khiếm thị. **Nội dung hiển thị và giọng đọc dùng tiếng Việt.** Chưa triển khai ứng dụng Android hoặc inference trên điện thoại.

- Đọc [hướng dẫn giai đoạn 1](docs/phase-1-phone-camera-yolo.md), [luồng mô tả vật thể](docs/object-narration.md) và [giọng tiếng Việt trên Windows](docs/windows-vietnamese-voice.md). Tài liệu giai đoạn 1 mô tả mốc nền 1A–1B; yêu cầu hiện tại bổ sung text và TTS theo mục này.
- Thứ tự: xem được camera thật qua DroidCam → nhận diện bằng YOLO11s → chuyển kết quả thành câu tiếng Việt → đọc bằng giọng tiếng Việt → đánh giá/bổ sung nhận diện biển báo còn thiếu.
- Đầu ra gồm một vùng video có hộp bao, nhãn và confidence; câu mô tả tiếng Việt; trạng thái camera/model/âm thanh và chỉ số hiệu năng đo được. TTS chạy bất đồng bộ để video tiếp tục cập nhật.
- Cảnh báo hiện tại là thông báo loại vật thể và vị trí trong ảnh. Không suy khoảng cách, mức nguy hiểm, hướng tránh hoặc thời điểm sang đường chỉ từ kết quả YOLO.
- YOLO11s pretrained COCO hỗ trợ một số đối tượng phổ biến, có `stop sign` và `traffic light`; chưa nhận đầy đủ biển báo Việt Nam hoặc màu đèn. Phân biệt phát hiện biển, phân loại ý nghĩa biển và OCR đọc chữ.
- Chưa yêu cầu GPS, định tuyến, SOS, đo khoảng cách, OCR, STT, tối ưu INT8 hoặc xây dựng mobile trong mốc hiện tại.
- AI và TTS chạy trên máy tính; âm thanh phát qua loa/tai nghe của máy tính. DroidCam không tự chuyển âm thanh cảnh báo về điện thoại. Đích sản phẩm cuối vẫn là xử lý trên điện thoại.

### 0.1. Kết nối camera bằng DroidCam

Ưu tiên dùng DroidCam làm webcam ảo để OpenCV đọc như camera thông thường. Giữ nguồn camera đã chạy được nếu người dùng đang dùng ứng dụng khác; không buộc đổi driver chỉ để khớp ví dụ.

**Chuẩn bị:** cài ứng dụng DroidCam trên điện thoại và [DroidCam Client cho Windows](https://droidcam.app/windows/) trên máy tính. Dùng app/client tương thích; trên Android, nhánh DroidCam hiện tại và DroidCam Classic là hai nhánh riêng. Nếu dùng Classic, theo [hướng dẫn kết nối Classic](https://www.dev47apps.com/droidcam/connect/). Cấp quyền camera và các quyền kết nối/thông báo mà ứng dụng cần. Chỉ truyền video; không bật `Enable Audio` để thu micro khi chưa có yêu cầu.

**Qua Wi-Fi:**

1. Cho điện thoại và máy tính vào cùng mạng nội bộ; máy tính có thể nối Ethernet tới mạng đó. Mở DroidCam trên điện thoại và DroidCam Client trên máy tính.
2. Với client hiện tại, chọn `Add > DroidCam`, dùng `Refresh Device List` rồi thêm điện thoại. Nếu không dò được, dùng `Use WiFi IP` và địa chỉ hiển thị trên app.
3. Với Classic, chọn `WiFi/LAN`, nhập đúng IP và port hiển thị trên điện thoại rồi nhấn `Start`. Không dùng IP/port minh họa làm địa chỉ thật.
4. Xác nhận preview trong client có hình đang chuyển động trước khi chạy Python.

Nguồn thao tác: [DroidCam Windows Client](https://droidcam.app/windows/), [DroidCam Help](https://droidcam.app/help/) và [Classic Connect](https://www.dev47apps.com/droidcam/connect/). Tên mục có thể đổi theo phiên bản.

**Qua USB:** dùng cáp truyền dữ liệu. Với Android, bật Developer Options và USB Debugging theo [mục USB Setup của DroidCam](https://droidcam.app/help/), kết nối cáp và chấp nhận yêu cầu cho phép máy tính trên điện thoại. Cài driver USB đúng hãng nếu Windows chưa nhận thiết bị. Trong client, thêm/chọn thiết bị USB và làm mới danh sách; Classic có mục kết nối USB riêng. Với iPhone, cần driver Apple phù hợp và thao tác `Trust` khi được hỏi; không áp dụng USB Debugging của Android cho iOS. Xác nhận preview trước khi mở OpenCV.

**Chọn nguồn trong Python:**

```powershell
# Ví dụ nguồn 1; thay bằng nguồn DroidCam thực tế trên máy.
.\.venv\Scripts\python.exe -m prototype.main --source 1 --no-detect
```

- Số `--source` là nguồn OpenCV, không phải port DroidCam. Không mặc định DroidCam luôn là `0`, `1` hoặc `1401` trên mọi máy.
- Nếu chưa biết nguồn, thử từng nguồn phù hợp bằng `--no-detect`, thoát lần chạy trước bằng `q` rồi đổi nguồn; xác nhận ảnh thực sự đến từ điện thoại. Chỉ hướng dẫn tùy chọn liệt kê camera khi CLI đã triển khai tùy chọn đó.
- Giữ DroidCam app/client hoạt động; đóng ứng dụng xem camera khác nếu nó đang chiếm thiết bị. Kiểm tra quyền Windows cho ứng dụng desktop truy cập camera khi không mở được nguồn.
- Khi mất hình: kiểm tra preview trong client trước, sau đó mới kiểm tra OpenCV. Kiểm tra mạng/IP, cáp, quyền và nguồn camera; không quy lỗi cho YOLO khi chưa nhận được ảnh.
- Nếu bị giật, so sánh `--no-detect` với nhận diện để tách nghẽn truyền hình và nghẽn inference. Có thể giảm cấu hình video DroidCam hoặc thử USB; đo lại, không hứa một mức FPS.
- Khi app/client đóng hoặc kết nối mất, chương trình phải báo mất dữ liệu và hủy lời đọc từ ảnh cũ; không tiếp tục cảnh báo như camera vẫn hoạt động.
- Chỉ dùng URL video khi đúng phiên bản app cung cấp và đã kiểm tra được. Không lấy URL mẫu của IP Webcam làm URL DroidCam một cách mặc định.

### 0.2. YOLO → text tiếng Việt → âm thanh cảnh báo

Luồng bắt buộc của prototype:

```text
Camera điện thoại → DroidCam (Wi-Fi/USB) → Webcam ảo → OpenCV
    → YOLO11s → Detection của đúng khung hình còn mới
        ├→ Video: hộp bao + nhãn tiếng Việt + confidence
        └→ Narration: loại vật thể + vị trí trong ảnh → câu tiếng Việt có dấu
            → FeedbackManager → TTS tiếng Việt → loa/tai nghe máy tính
```

- YOLO trả lớp, confidence và hộp bao. Module `narration.py` ánh xạ nhãn của model sang tiếng Việt và tạo câu theo mẫu; TTS trong `speech.py` đọc câu đã tạo. Không mô tả YOLO là bộ tự sinh văn bản hoặc giọng nói.
- Text này là mô tả từ kết quả phát hiện, không phải OCR đọc chữ trên vật thể. Không thêm OCR, LLM, dịch trực tuyến hoặc cloud TTS khi nhiệm vụ chưa yêu cầu.
- Dùng ánh xạ nhãn nhất quán, ví dụ `person` → “người”, `car` → “ô tô”, `stop sign` → “biển báo dừng”. Không thêm tên lớp để giả lập khả năng nhận diện mới. Nhãn tùy chỉnh chưa dịch phải có cách mô tả chung rõ ràng.
- Chỉ tạo câu từ kết quả đủ confidence, thuộc phiên camera hiện tại và chưa hết tuổi. Vị trí trái/giữa/phải lấy từ hộp bao trong ảnh gốc; kiểm tra ảnh lật gương, xoay và tư thế đặt điện thoại.
- Câu mẫu khi có phát hiện tương ứng: “Có người ở bên trái.”, “Có ô tô ở giữa ảnh.”, “Có biển báo dừng ở bên phải.” Đây là ví dụ nội dung, không phải kết quả đo hoặc phát hiện thật.
- “Ở giữa ảnh” không chứng minh vật đang chắn đường. Không tự đọc “cách 2 mét”, “đèn xanh”, “rẽ trái”, “đường an toàn” hoặc “sang đường” nếu chưa có chức năng và bằng chứng phù hợp.
- Hiện đúng câu tiếng Việt được gửi cho TTS; dùng Unicode và phông hỗ trợ dấu. Không đọc mọi nhãn/confidence ở mỗi frame; ưu tiên nhóm cần thông báo, gộp vật cùng loại/vị trí, giới hạn độ dài và chống đọc lặp.
- `FeedbackManager` sở hữu việc đọc, hàng đợi, hủy, TTL và chống lặp. Không gọi TTS trực tiếp từ vòng vẽ ảnh hoặc từng detection. Chỉ giữ câu đang đọc và câu chờ mới nhất; mất camera, ảnh cũ, lỗi model hoặc tắt tiếng phải hủy lời không còn hiệu lực.
- Không nâng mọi phát hiện thành cảnh báo khẩn P1. Bản hiện tại mô tả đối tượng; đánh giá nguy cơ và điều phối ưu tiên đầy đủ thuộc giai đoạn mở rộng.
- Chọn rõ giọng ngôn ngữ `vi`/`vi-VN`; không dùng giọng tiếng Anh mặc định để đọc tiếng Việt. Trên Windows dùng backend hiện có WinRT/SAPI/SAPI-OneCore, kiểm tra giọng Microsoft An nếu đã cài; không thêm `pyttsx3` chỉ để thay tên thư viện.
- Phân biệt **giọng đã cài**, **API truy cập được**, **tổng hợp được dữ liệu** và **đã nghe phát thành công**. `vietnameseInstalled: true` chưa chứng minh phát được; lỗi WinRT không đủ để kết luận thiếu gói tiếng Việt.
- Khi TTS lỗi, video và text vẫn chạy, trạng thái âm thanh báo rõ. Đọc chi tiết mã lỗi theo [hướng dẫn giọng Việt](docs/windows-vietnamese-voice.md); không tự sửa/copy registry, cài lại Python hoặc chuyển sang giọng Anh khi chưa xác định nguyên nhân.

### 0.3. Chạy và kiểm tra từng bước

Giữ môi trường `.venv` đã dùng. Chỉ chạy các lệnh sau khi thực hiện nhiệm vụ triển khai/kiểm chứng tương ứng; yêu cầu chỉ sửa tài liệu không tự khởi động camera hoặc phát âm thanh.

```powershell
# 1. Xem camera DroidCam; số 1 chỉ là ví dụ.
.\.venv\Scripts\python.exe -m prototype.main --source 1 --no-detect

# 2. Thoát bước 1, kiểm tra YOLO và câu chữ trước.
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolo11s.pt --mute

# 3. Kiểm tra giọng; không phát qua loa (có thể tổng hợp mẫu vào RAM).
.\.venv\Scripts\python.exe -m prototype.speech --list-voices

# 4. Lệnh này phát câu mẫu tiếng Việt qua loa/tai nghe máy tính.
.\.venv\Scripts\python.exe -m prototype.speech --test

# 5. Chạy đầy đủ camera → YOLO → text → giọng tiếng Việt.
.\.venv\Scripts\python.exe -m prototype.main --source 1 --model yolo11s.pt
```

Nhấn `m` để bật/tắt âm thanh và `q` để thoát cửa sổ prototype. Không chạy đồng thời nhiều phiên chiếm cùng camera. `--imgsz 640` là mặc định (320 từng bỏ sót vật nhỏ; hạ xuống nếu CPU không đủ nhanh); cần đánh giá bằng dữ liệu thật.

## 1. Mục tiêu và phạm vi

Đích sản phẩm sau prototype là ứng dụng di động dùng camera, GPS và cảm biến điện thoại để hỗ trợ nhận biết vật cản, đọc văn bản, định hướng và gọi trợ giúp. Ưu tiên xử lý trên thiết bị, phản hồi bằng tiếng Việt và giao diện dùng được với trình đọc màn hình.

- Đây là hướng dẫn cho agent phát triển phần mềm; không phải mô tả một hệ thống đã hoàn thiện.
- Sản phẩm hỗ trợ người dùng kết hợp với gậy dò đường. Không tuyên bố thay thế gậy, bảo đảm tránh va chạm hoặc tự quyết định thời điểm sang đường.
- Làm đúng nhiệm vụ người dùng đang yêu cầu. Nếu chỉ được yêu cầu sửa tài liệu, không tự khởi tạo ứng dụng hoặc triển khai dịch vụ.
- Khi được yêu cầu xây dựng hệ thống, hoàn thành từng chức năng có thể chạy và kiểm chứng; không chỉ tạo giao diện mẫu hoặc các lớp rỗng.
- Giao tiếp, tài liệu và nội dung người dùng bằng tiếng Việt; tên lớp, hàm, biến dùng tiếng Anh nhất quán.

## 2. Cách bắt đầu công việc

1. Đọc hướng dẫn áp dụng trong repository, README, cấu hình build, mã nguồn và kiểm thử hiện có.
2. Giữ cấu trúc và công nghệ đã được nhóm lựa chọn; không chuyển framework chỉ vì tài liệu này có phương án mặc định.
3. Với repository mới, bắt đầu bằng prototype Python nhận camera điện thoại theo mục 0. Khi chuyển sang mobile, dùng Android Kotlin làm mặc định nếu nhóm chưa lựa chọn công nghệ khác.
4. Ghi các lựa chọn còn thiếu thành giả định có thể điều chỉnh; tự giải quyết việc triển khai thông thường. Chỉ hỏi khi thiếu thông tin thực sự chặn công việc hoặc thay đổi đáng kể phạm vi.
5. Phân biệt rõ: đề xuất, đã triển khai, đã thử trên máy tính, đã kiểm chứng trên điện thoại.
6. Số liệu và kết quả mô phỏng không được trình bày như kết quả từ thiết bị thực. Không bịa dữ liệu, model, API response hay kết quả kiểm thử.

## 3. Phạm vi triển khai theo giai đoạn

| Giai đoạn | Kết quả cần đạt |
| --- | --- |
| 1A — Kết nối camera, làm trước | DroidCam truyền video từ điện thoại qua Wi-Fi nội bộ hoặc USB; Python/OpenCV nhận webcam ảo, hiển thị và xử lý mất kết nối. |
| 1B — Nhận diện cơ bản | YOLO11s trên máy tính; video có hộp bao, nhãn, confidence; ghi đúng lớp hỗ trợ và các chỉ số đo được. |
| 1B mở rộng — Text và giọng tiếng Việt | Chuyển kết quả YOLO thành câu tiếng Việt có dấu; hiển thị và đọc bằng TTS tiếng Việt; xử lý lỗi giọng, dữ liệu cũ, hủy và chống đọc lặp. |
| 1C — Biển báo | Kiểm tra stop sign/traffic light của model có sẵn; xác định các lớp biển cần bổ sung, huấn luyện hoặc chọn model phù hợp và đánh giá riêng. |
| 2 — Nền tảng mobile | Sau prototype: camera và AI trực tiếp trên điện thoại, quyền, giao diện tiếp cận, TTS và trạng thái lỗi. |
| 3 — Cảnh báo | Bổ sung ước lượng khoảng cách có điều kiện, đánh giá nguy cơ và phản hồi tập trung; kiểm thử trước khi thử di chuyển. |
| OCR và lệnh | Đọc chữ theo yêu cầu; hỗ trợ nút bấm và lệnh giọng nói; cảnh báo khẩn có thể ngắt OCR. |
| Điều hướng | Chọn điểm đến, lấy tuyến đi bộ, theo dõi tiến trình bằng GPS và hướng thiết bị; xử lý mất mạng và lệch tuyến. |
| SOS và hoàn thiện | Liên hệ khẩn cấp, gửi vị trí/gọi theo thao tác người dùng, tối ưu hiệu năng và thử nghiệm có kiểm soát. |
| Nghiên cứu mở rộng | Chiều sâu tương đối, nhận biết địa hình, phân vùng lối đi; chỉ tích hợp khi có phương pháp và đánh giá riêng. |

Không bắt buộc hoàn thành mọi giai đoạn trong một lần sửa. Hoàn thành và kiểm chứng luồng 1A → 1B → text/TTS tiếng Việt trước khi thêm các chức năng khác; không coi đó là đã nhận diện mọi biển báo hoặc bảo đảm tránh va chạm. MiDaS và tự động chọn hướng tránh vật cản nằm ngoài MVP.

## 4. Công nghệ dự kiến và cách lựa chọn

Hiện tại: DroidCam + Python + OpenCV + thư viện Ultralytics, model YOLO11s dạng `.pt` trên máy tính; `narration.py` tạo câu tiếng Việt, Pillow/phông Unicode hiển thị chữ và worker Windows đọc TTS cục bộ. CPU chạy được trước, GPU chỉ dùng khi môi trường hỗ trợ. Dùng các backend giọng hiện có, không cài thêm engine chỉ vì thư viện khác cũng hỗ trợ TTS. Bảng dưới là định hướng khi chuyển sang mobile, không phải danh sách dependency cần cài ngay.

| Chức năng | Mặc định cho dự án mới |
| --- | --- |
| Ứng dụng | Android Kotlin; giao diện Compose; tác vụ bất đồng bộ bằng Coroutines/Flow. |
| Camera | CameraX hoặc adapter camera tương đương của codebase. |
| Phát hiện đối tượng | YOLOv8-nano; thử nghiệm model float trước, so sánh INT8 sau. |
| Chạy mô hình | LiteRT/TFLite cho Android; ONNX Runtime là phương án thay thế khi có lý do về tương thích hoặc phép đo. |
| OCR | Google ML Kit Text Recognition v2, nhận dạng Latin; kiểm chứng tiếng Việt có dấu. |
| Vị trí và hướng | API vị trí Android và bộ cảm biến hướng/chuyển động có sẵn trên thiết bị. |
| Lệnh và giọng nói | Adapter STT và Native TTS; kiểm tra khả năng tiếng Việt, model và chế độ ngoại tuyến. |
| Lập tuyến | Adapter RouteProvider; dự kiến Google Maps Routes API cho yêu cầu lập/tính lại tuyến. |
| Dữ liệu cục bộ | SQLite; có thể dùng Room trên Android cho dữ liệu có cấu trúc. |
| Đối chiếu prototype máy tính | Python + OpenCV + YOLO11s; tạo câu tiếng Việt và dùng worker WinRT/SAPI/SAPI-OneCore hiện có, chưa phải runtime TTS của Android. |

- Nếu đã chọn Flutter, giữ Flutter cho ứng dụng và tích hợp camera, cảm biến, inference qua adapter/plugin native khi cần. Không gọi Flutter là Android native Kotlin.
- Không triển khai đồng thời TFLite và ONNX chỉ để có đủ tên công nghệ.
- TFLite/ONNX là định dạng triển khai; NMS là thuật toán hậu xử lý. Chúng không thay thế nhau.
- Không mặc định INT8 hoặc model export sẽ chạy trên NPU. Kiểm tra runtime, toán tử, phần cứng hỗ trợ và hành vi fallback.
- NNAPI đã deprecated; không lấy NNAPI làm nền tảng tăng tốc mặc định cho dự án mới. Kiểm tra tài liệu runtime hiện hành trước khi chọn backend.
- Chọn phiên bản thư viện tương thích, lưu phiên bản cố định/lockfile. Ghi nguồn, phiên bản, checksum và giấy phép của model; kiểm tra điều kiện phân phối trước khi đóng gói.
- Không thêm LLM/cloud vision hoặc dịch vụ hội thoại vào luồng cảnh báo cốt lõi nếu nhiệm vụ không yêu cầu.

## 5. Kiến trúc và chiều dữ liệu

Luồng của giai đoạn hiện tại (các tác vụ nặng chạy độc lập, không chặn vòng hiển thị):

```text
Camera điện thoại → DroidCam qua Wi-Fi/USB → Webcam ảo → Python/OpenCV
    → YOLO11s → Giải mã/NMS trong thư viện → Detection còn hiệu lực
        ├→ Hiển thị ảnh nguồn + hộp bao + nhãn + confidence
        └→ Narration → Text tiếng Việt có dấu → FeedbackManager
            → TTS tiếng Việt → Loa/tai nghe máy tính
```

Sơ đồ dưới là kiến trúc đích sau khi mở rộng; không tạo các service chưa cần cho prototype.

Các luồng dưới đây là luồng dữ liệu/kết quả. Chúng không có nghĩa mọi tác vụ chạy nối tiếp trên một luồng thực thi.

```text
Camera → ObjectDetector → DistanceEstimator + RiskAssessor → CoreOrchestrator
Camera → OcrService                                      → CoreOrchestrator
Mic → SpeechRecognizer → IntentParser                    → CoreOrchestrator
GPS + OrientationTracker + dữ liệu tuyến → Navigation     → CoreOrchestrator

CoreOrchestrator → FeedbackManager → TTS / âm báo / rung

Navigation ↔ RouteProvider (Cloud khi cần)
Navigation ↔ RouteRepository (dữ liệu cục bộ được phép lưu)
```

Luồng điều khiển được tách rõ khỏi kết quả:

- Người dùng yêu cầu đọc chữ → CoreOrchestrator gửi ReadText → OcrService → trả OcrResult.
- Người dùng bắt đầu/dừng dẫn đường → CoreOrchestrator gửi StartNavigation/StopNavigation → Navigation.
- Nút hoặc lệnh SOS → CoreOrchestrator → SosService; phản hồi trạng thái quay lại bộ điều phối.
- Dừng dẫn đường không tự động tắt cảnh báo vật cản; quản lý riêng phiên điều hướng, nhận diện và OCR.
- OCR nhận ảnh trực tiếp từ nguồn camera, không đặt nối tiếp sau RiskAssessor.
- FeedbackManager chỉ quản lý phản hồi; không gửi lệnh định vị hoặc lập tuyến.
- CoreOrchestrator điều phối trạng thái và sự kiện, không thực hiện inference nặng hay chờ mạng trên luồng xử lý sự kiện.
- Tách thuật toán thuần khỏi API Android để kiểm thử bằng dữ liệu giả và đồng hồ giả. Có thể tổ chức bằng package trước, không bắt buộc nhiều Gradle module.

## 6. Hợp đồng dữ liệu, trạng thái và bất đồng bộ

Định nghĩa kiểu dữ liệu rõ ràng; không truyền chuỗi JSON tùy ý giữa các mô-đun nội bộ.

- Detection: frameId, thời điểm thu ảnh, classId/label, score, boundingBox và hệ tọa độ; trackId khi có liên kết đối tượng.
- Mô tả cảnh trong prototype: văn bản tiếng Việt, nhóm đối tượng/vị trí trong ảnh, frameId/phiên và thời điểm ảnh nguồn; giữ kiểu dữ liệu hiện có. Không để câu chữ tách khỏi nguồn dữ liệu dùng để kiểm tra tuổi và hủy lời đọc.
- DistanceEstimate: khoảng cách tùy chọn, đơn vị, phương pháp, chất lượng và lý do không hợp lệ. Không biểu diễn unknown bằng 0 mét.
- LocationFix: tọa độ, độ chính xác, tuổi dữ liệu; Heading: góc, hệ quy chiếu Bắc và chất lượng cảm biến.
- NavigationState: sessionId, routeVersion, bước hiện tại và trạng thái active/offRoute/locationUncertain/stopped.
- AudioEvent: id, source, priority, text hoặc cue, sourceCapturedAt, createdAt, expiresAt nếu có, dedupKey và contextId.
- Thời gian đo độ trễ/TTL dùng đồng hồ đơn điệu cùng hệ quy chiếu. Quy đổi timestamp cảm biến khi cần; không dùng giờ hệ thống dễ bị chỉnh.
- Hàng đợi phải có giới hạn. Với video, bỏ ảnh cũ và ưu tiên ảnh mới; không để inference/OCR chậm tạo backlog.
- Một thành phần sở hữu camera và phân phối ảnh. Quy định quyền sở hữu, sao chép và giải phóng khung hình; không đóng ImageProxy khi tác vụ bất đồng bộ còn sử dụng. OCR không mở phiên camera cạnh tranh với luồng nhận diện.
- Kết quả của phiên đã hủy hoặc tuyến đã thay đổi phải bị loại. Dùng session/request id để chặn callback muộn.
- Hủy tác vụ và giải phóng camera, microphone, sensor listener, model, TTS đúng vòng đời; tái khởi tạo không tạo listener trùng.
- Tuân thủ yêu cầu thread của API nền tảng. Tính toán nặng không chạy trên UI thread.
- Lỗi OCR hoặc lỗi mạng không được làm sập luồng nhận diện và cảnh báo cục bộ.

## 7. Quy tắc thuật toán

### 7.1. Phát hiện đối tượng

- Luồng: ảnh → resize/letterbox đúng tỉ lệ → tiền xử lý đúng model → inference → giải mã → NMS nếu cần → lọc nhóm mục tiêu.
- Kiểm tra input dtype, kích thước, thứ tự màu, scale/zero-point của INT8; không áp dụng chuẩn hóa [0,1] máy móc cho mọi model.
- Xác định NMS nằm trong model export hay trong hậu xử lý; không áp dụng hai lần.
- Chuyển hộp bao về đúng hệ tọa độ ảnh gốc sau padding/resize/rotation.
- Confidence, IoU và danh sách lớp là cấu hình được đánh giá; không xem IoU 0.45 hoặc “16 nhãn” là chân lý cố định.
- Model pretrained không tự nhận biết mọi vật cản, hố hoặc bậc thang. Ghi đúng các lớp được hỗ trợ.
- Biển giao thông ngoài tập lớp hiện có cần model phù hợp; không thêm tên vào danh sách nhãn để giả lập khả năng nhận diện. OCR chỉ phục vụ đọc chữ, không thay thế phân loại biển ký hiệu.
- RiskAssessor kết hợp vị trí trong ảnh, chất lượng kết quả và khoảng cách nếu hợp lệ. Không mặc định mọi vật thể phát hiện đều nguy hiểm.
- Không phát hiện được vật thể không đồng nghĩa đường trống hoặc an toàn. Không sinh lệnh tránh trái/phải chỉ từ một bounding box nếu chưa đánh giá không gian có thể đi.

### 7.2. Khoảng cách và đánh giá nguy cơ

```text
D ≈ H_ref × f_px / h_bbox_px
D_filtered(t) = median(các giá trị hợp lệ gần nhất của cùng một đối tượng)
```

- Đây là ước lượng theo mô hình pinhole và kích thước tham chiếu, không phải phép đo chính xác cho mọi vật thể.
- Hiệu chuẩn camera; f và h phải cùng hệ tọa độ và độ phân giải. Xử lý h ≤ 0, NaN, vật bị cắt/che khuất và kích thước không đáng tin cậy.
- Không có dữ liệu phù hợp thì trả unknown và có thể thông báo loại/vị trí tương đối; không đọc số mét giả chính xác.
- Chỉ lọc chuỗi của cùng trackId hoặc liên kết đã được xác thực; xóa lịch sử khi track mất hoặc đổi đối tượng.
- Giới hạn cả số lượng và tuổi mẫu trong cửa sổ lọc; xóa lịch sử sau gián đoạn quá lâu. Không gán độ mới của mẫu hiện tại cho ước lượng vẫn bị chi phối bởi dữ liệu cũ.
- k = 5 là cấu hình thử nghiệm. Median giảm nhiễu nhưng không khử hết outlier; không ghi “trễ 5 frame” chỉ vì dùng 5 mẫu.
- Nếu dùng tốc độ tiếp cận, tính (D_trước − D_hiện_tại) / Δt thực, kiểm tra Δt và độ tin cậy của track. Không dùng ngưỡng mét/khung hình khi FPS thay đổi.
- Đường cảnh báo nhanh phải kiểm tra độ tin cậy; không bỏ qua mọi kiểm tra chỉ vì một khoảng cách thô giảm đột ngột.
- MiDaS chỉ cung cấp chiều sâu tương đối trong phương án nghiên cứu; không dùng như bộ đo mét hay bộ xác nhận bậc thang/hố.

### 7.3. Định vị, hướng và tuyến đường

- GPS cung cấp vị trí; cảm biến hướng cung cấp hướng thiết bị. Hướng thiết bị khác hướng mặt và hướng bước chân.
- Ghi rõ tư thế cầm/gắn điện thoại dự kiến; chuyển trục theo hướng màn hình/camera. Thiết bị thiếu cảm biến hoặc bị nhiễu phải có trạng thái giảm khả năng.
- Dùng sensor fusion phù hợp với phần cứng, không hứa magnetometer đơn lẻ luôn chính xác.
- Haversine: dùng vĩ độ/kinh độ theo radian, bảo vệ sai số số học của tham số trung gian. Bearing tính bằng atan2 phải đổi sang độ.
- Quy đổi về cùng hệ quy chiếu Bắc trước khi so sánh; không trực tiếp trừ bearing theo Bắc thực với heading theo Bắc từ.

```text
theta = bearing mục tiêu theo độ, chuẩn hóa về [0, 360)
psi   = heading thiết bị theo độ, cùng hệ quy chiếu
delta = ((theta - psi + 540) mod 360) - 180
delta thuộc [-180, 180)
```

- delta âm: mục tiêu lệch trái; dương: lệch phải; -180 biểu diễn hướng đối diện. Không ép chọn trái/phải duy nhất ở đúng 180 độ.
- Đây là góc lệch mục tiêu, không phải bằng chứng về ngã rẽ hay việc người dùng đang đi ngược tuyến.
- Chọn mục tiêu theo đoạn tuyến và bước dẫn đường hiện tại; không hướng người dùng đi thẳng qua vật cản hoặc công trình để tới waypoint.
- Gần điểm rẽ chỉ tạo nhắc trước. Không tự chuyển bước chỉ vì d ≤ 15 m; xét tiến trình tuyến, thao tác rẽ và sai số GPS.
- Khi vị trí/hướng không đủ tin cậy, ngừng chỉ dẫn rẽ cụ thể và phản hồi trạng thái phù hợp. Không tiếp tục lệnh từ tọa độ cũ.
- Lập/tính lại tuyến đi bộ cần RouteProvider; có timeout, giới hạn retry và xử lý kết quả lỗi. Không tự tạo “tuyến mới” bằng cách nối thẳng các tọa độ.

### 7.4. OCR theo yêu cầu

- CoreOrchestrator nhận yêu cầu đọc chữ và kích hoạt OcrService; OcrService trả văn bản/trạng thái, không tự gọi TTS.
- Chỉ báo sơ bộ độ nét: S = Var(Laplacian(I_gray)). Giữ tiền xử lý nhất quán khi chọn ngưỡng.
- Ngưỡng như 100 phải hiệu chỉnh theo ảnh và thiết bị. Ảnh ít chi tiết có thể điểm thấp, nhiễu có thể điểm cao; không coi điểm này là xác suất đọc đúng.
- Thử khung hình mới với số lần/thời gian chờ có giới hạn; giảm lặp lời nhắc giữ máy. Cho phép hủy yêu cầu.
- Đọc kết quả theo bố cục hợp lý, chia văn bản dài thành đoạn để dễ ngắt và tiếp tục.
- Không tự bịa chữ khi không nhận dạng được; không khẳng định chữ gần mép ảnh chắc chắn đã bị cắt.
- Chuẩn bị model OCR trước khi cần dùng offline. Không ghi kiến trúc nội bộ hoặc số đo tốc độ ML Kit nếu chưa có bằng chứng.

## 8. Điều phối phản hồi và âm thanh

Mọi âm thanh do ứng dụng chủ động phát đi qua FeedbackManager. Quy tắc này không nhằm tắt âm thanh hệ thống hoặc trình đọc màn hình. Trong prototype hiện tại, áp dụng ngay việc đọc tiếng Việt bất đồng bộ, giới hạn hàng đợi, TTL, hủy và chống lặp theo mục 0.2. Các quy tắc P1/P2/P3 dưới đây áp dụng khi triển khai thêm cảnh báo nguy cơ, dẫn đường hoặc OCR; không mặc định bộ phân ưu tiên đầy đủ đã tồn tại.

- P1: cảnh báo khẩn; P2: dẫn đường; P3: OCR/hội thoại. P1 có quyền ngắt P2/P3.
- Một hàng đợi ưu tiên cộng mutex chưa đủ: quản lý trạng thái idle/speaking/stopping, utteranceId và callback hoàn tất/lỗi.
- Khi ngắt, xử lý kết quả stop và callback cũ để không phát hai nội dung hoặc tự khởi động lại thông báo đã hủy.
- Trước khi phát hoặc tiếp tục, kiểm tra tuổi dữ liệu gốc, phiên hiện tại, bước dẫn đường, yêu cầu OCR và ngữ cảnh còn hiệu lực.
- TTL theo loại thông báo; không áp dụng 3 giây cho tất cả. P1 và P2 cũng có thể trở nên lỗi thời.
- Nội dung OCR do người dùng yêu cầu có thể tiếp tục nếu yêu cầu còn hiệu lực; không tự đọc lại hết từ đầu sau mọi lần ngắt.
- Gộp/thay thế thông báo trùng, giới hạn lặp và độ dài hàng đợi; không để spam OCR hoặc cảnh báo lặp chặn phản hồi khác vô hạn.
- Dùng thông báo ngắn, rõ, đủ nghe; phối hợp audio focus với cuộc gọi, tai nghe và trình đọc màn hình.
- TTS có tiếng Việt và offline hay không phụ thuộc engine/gói giọng. Kiểm tra thực tế, cung cấp trạng thái và phương án âm báo/rung khi không phát giọng được.
- Kiểm tra STT trên thiết bị trước khi hứa offline. Có thao tác bằng nút khi không nhận dạng được giọng nói.
- Tránh microphone nhận chính giọng TTS thành lệnh; phối hợp chế độ nghe/nói và kiểm thử lệnh dừng.

## 9. Ngoại tuyến, năng lượng và trạng thái suy giảm

Các yêu cầu on-device dưới đây áp dụng cho ứng dụng mobile. Với prototype hiện tại, AI và TTS chạy trên máy tính; video qua DroidCam phụ thuộc kết nối Wi-Fi nội bộ hoặc USB đã chọn. Cần mạng để chuẩn bị model/gói giọng nếu chưa có; không suy việc tải được giọng thành khả năng phát ngoại tuyến đã kiểm chứng.

- Phát hiện đối tượng, OCR và xử lý cảm biến phải chạy cục bộ sau khi model cần thiết đã sẵn sàng.
- Route cache không phải bản đồ offline và không bảo đảm tính lại tuyến khi mất mạng.
- Với Google Maps, kiểm tra chính sách dịch vụ trước khi lưu NavStep, polyline hoặc nội dung tuyến. Không mặc định được lưu toàn bộ API response.
- Nếu cần offline mà nhà cung cấp không cho lưu đủ dữ liệu, ghi rõ giới hạn và đề xuất nguồn dữ liệu/giải pháp có quyền sử dụng phù hợp.
- Dữ liệu tuyến được phép lưu phải gắn phiên, nguồn và thời hạn. Mất mạng chỉ theo tuyến hiện có khi dữ liệu và vị trí còn hợp lệ; lệch tuyến cần phản hồi rõ.
- GPS có thể còn hoạt động khi mất Internet, nhưng vẫn phải xét chất lượng và tuổi vị trí.
- Adaptive FPS điều chỉnh tần suất xử lý theo chuyển động, tải máy và nhiệt độ. Không tắt hoàn toàn theo dõi vật cản chỉ vì người dùng đứng yên.
- Không có dữ liệu mới, camera bị che, model lỗi hoặc cảm biến thiếu phải chuyển trạng thái rõ ràng; không mô phỏng hoạt động bình thường.
- Camera, model và cảm biến hoạt động nền phải tuân thủ lifecycle, quyền và giới hạn phiên bản Android mục tiêu.

## 10. Giao diện, dữ liệu cá nhân và SOS

- Các thao tác bắt đầu/dừng, đọc chữ, chọn điểm đến, nhắc lại và SOS phải dùng được với TalkBack, không phụ thuộc nhìn màn hình hoặc phân biệt màu.
- Có nhãn tiếp cận, thứ tự focus, vùng chạm phù hợp, cỡ chữ co giãn; hiển thị rõ chức năng nào đang hoạt động.
- Không lấy tông màu slide làm yêu cầu bắt buộc của giao diện sản phẩm; ưu tiên khả năng sử dụng.
- Xin camera/microphone/location theo chức năng, xử lý từ chối và thu hồi quyền. Không mặc định cần quyền định vị nền.
- Không lưu hoặc tải ảnh camera, bản ghi âm, văn bản OCR và lịch sử vị trí lên máy chủ mặc định. Log phục vụ debug phải giảm dữ liệu nhận dạng.
- Không commit API key, token, số điện thoại thật hoặc tọa độ thật vào repository. Cấu hình bí mật ở môi trường phù hợp; bí mật máy chủ không đặt trong APK.
- Nếu API cần bí mật máy chủ, dùng backend tối thiểu có xác thực và hạn mức; không mở proxy công khai. Việc thêm backend không chuyển inference cảnh báo lên cloud.
- SOS do người dùng chủ động kích hoạt, có cơ chế chống bấm nhầm và hủy phù hợp khả năng tiếp cận; gửi đúng liên hệ đã cấu hình.
- Khi vị trí cũ, ghi thời điểm/độ chính xác hoặc báo chưa xác định được vị trí. Phân biệt mở ứng dụng nhắn tin, đã gửi và đã nhận.
- SMS/cuộc gọi qua thiết bị và SMS Gateway là hai phương án khác nhau; không mặc định gửi SMS cần cloud. Chọn theo quyền và nền tảng.
- Chế độ kiểm thử dùng adapter giả cho SMS/cuộc gọi; không gửi thật đến người thân hoặc dịch vụ khẩn cấp trong kiểm thử tự động.

## 11. Kiểm thử và tiêu chí hoàn thành

Ưu tiên kiểm thử hành vi có thể gây kết quả sai. Mỗi thay đổi thuật toán hoặc phối hợp trạng thái phải có kiểm chứng tương ứng.

Giai đoạn hiện tại kiểm thử kết nối DroidCam, nhận diện YOLO, tạo text và phát tiếng Việt. Các ca GPS, OCR, SOS, phân ưu tiên âm thanh đầy đủ và hiệu năng mobile áp dụng khi triển khai chức năng tương ứng.

Tiêu chí bắt buộc cho luồng hiện tại:

- Camera: nhận hình thật qua DroidCam; xác định đúng nguồn và hướng ảnh; thử ngắt/kết nối lại Wi-Fi hoặc USB theo phương thức dùng thực tế. Chưa thử phương thức nào thì ghi rõ chưa kiểm chứng phương thức đó.
- Nhận diện: hộp bao/nhãn đúng ảnh nguồn, confidence và lớp lấy từ model; báo trạng thái khi model lỗi. Không ghép kết quả cũ lên camera mới.
- Khi sửa detector hoặc hậu xử lý: kiểm tra letterbox/rotation, tọa độ hộp bao trả về, NMS trùng và trường hợp model không có lớp mong đợi.
- Text: ánh xạ đúng nhãn tiếng Việt có dấu; kiểm tra trái/giữa/phải, nhiều vật cùng nhóm, không có phát hiện, lớp chưa dịch, confidence thấp, ảnh cũ và đổi phiên.
- TTS: nghe thử câu tiếng Việt qua đúng đầu ra âm thanh của máy tính, kiểm tra có dấu/tên vật; xác nhận không đọc bằng giọng Anh mặc định. Tách kết quả nghe thật khỏi kiểm thử dùng engine giả hoặc chỉ tổng hợp vào RAM.
- Điều phối: chỉ một câu đang phát, thay câu chờ cũ bằng mới; kiểm tra chống lặp, TTL, `m`/`--mute`, mất camera, lỗi model, callback muộn, thoát chương trình và lỗi engine. Video/text vẫn hoạt động khi không đọc được giọng Việt.
- Hiệu năng: ghi Camera FPS, YOLO FPS, thời gian inference và tuổi ảnh trên máy tính theo triển khai hiện có. Nếu đo thêm độ trễ đến âm thanh, ghi rõ mốc bắt đầu/kết thúc; timestamp sau `OpenCV.read()` chưa phải thời điểm điện thoại thu hình.

Các ca cho giai đoạn mở rộng:
- Khoảng cách: hiệu chuẩn biết trước, h = 0, ảnh cắt vật, outlier, đổi track, mất track, FPS thay đổi.
- Góc: 0, ±180, 359 → 1, 1 → 359, đứng cùng điểm mục tiêu, quy đổi độ/radian và Bắc từ/Bắc thực.
- Điều hướng: GPS nhảy hoặc cũ, thiếu heading, waypoint gần nhau, chưa rẽ, lệch tuyến, mất mạng, kết quả trả về sau khi dừng.
- OCR: ảnh mờ/nhiễu/ít chi tiết, không có chữ, tiếng Việt có dấu, hủy khi đang xử lý, đọc dài bị ngắt.
- Âm thanh: P1 ngắt P3, TTL hết hạn, ngữ cảnh đổi dù chưa hết TTL, callback muộn, thông báo trùng, lỗi TTS/audio focus.
- Thiết bị: từ chối quyền, camera bị chiếm, thiếu gói giọng/model/cảm biến, quay màn hình, background/foreground, mất tai nghe.
- SOS: không có liên hệ, không có vị trí mới, mất mạng/SIM, gửi lỗi và không gửi lặp.
- Đo trên điện thoại thật: độ trễ từ lúc thu dữ liệu đến lúc bắt đầu phản hồi (p50/p95), tỉ lệ bỏ sót/báo nhầm, sai số khoảng cách, OCR, pin và nhiệt độ.
- Báo cáo kèm thiết bị, OS, model/checksum, runtime/backend, độ phân giải, thời lượng thử và dữ liệu đầu vào. Không suy tốc độ toàn hệ thống từ thời gian inference riêng.
- Kiểm thử trong môi trường kiểm soát trước; các bài thử đi bộ có người hỗ trợ, không dùng người khiếm thị để thử trực tiếp một luồng cảnh báo chưa được kiểm chứng.

Hoàn thành một chức năng khi: luồng thật chạy được, có xử lý lỗi, kiểm thử phù hợp đã chạy, tài liệu phản ánh đúng và phần chưa kiểm chứng được nêu rõ. Emulator hoặc demo Python không đủ để kết luận độ trễ cảm biến, pin hay an toàn thực tế.

## 12. Tổ chức repository và lệnh kiểm tra

Nếu repository đã có cấu trúc, dùng cấu trúc hiện có. Với dự án mới, có thể tổ chức:

```text
AGENTS.md
README.md
prototype/               DroidCam + YOLO + text và TTS tiếng Việt trên máy tính
android/                 ứng dụng Kotlin; chỉ tạo khi chuyển sang mobile
docs/                    kiến trúc, quyết định công nghệ, hướng dẫn thử nghiệm
models/                  model hoặc chỉ dẫn tải kèm nguồn và checksum
test-data/               dữ liệu kiểm thử có quyền sử dụng, không chứa dữ liệu riêng tư
```

- Trong ứng dụng, tách các vùng camera, vision, ocr, navigation, speech, feedback, sos, data và orchestration; thuật toán không phụ thuộc trực tiếp UI.
- Prototype hiện có dùng `camera.py`/`pipeline.py` nhận và xử lý ảnh, `detector.py` bọc YOLO, `narration.py` tạo text tiếng Việt, `speech.py` điều phối TTS và các worker `.ps1` giao tiếp Windows. Giữ các trách nhiệm này, không đưa inference hoặc lời gọi TTS chặn vào vòng UI.
- README phải ghi lệnh setup/build/test thực tế và các bước chuẩn bị model/API key. Không tạo thư mục, dependency hoặc service chỉ để khớp sơ đồ.
- Không di chuyển/xóa báo cáo, ảnh hoặc mã người dùng có sẵn khi khởi tạo dự án.
- Trên Windows, sau khi xác nhận Gradle wrapper và module app tồn tại, chạy các tác vụ phù hợp từ thư mục dự án Android: `./gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`.
- Chỉ chạy `connectedDebugAndroidTest` khi đã có thiết bị/emulator và cấu hình; thử nghiệm cảm biến và hiệu năng cần điện thoại thật.
- Nếu dự án là Flutter, dùng lệnh analyze/test/build đúng cấu hình đang có. Python dùng môi trường và test runner đã khai báo.
- Không báo kiểm thử thành công khi chưa chạy. Nếu thiếu SDK, model, khóa hoặc thiết bị, ghi chính xác kiểm chứng nào bị thiếu và tiếp tục phần độc lập.
- Với yêu cầu chỉ sửa tài liệu, kiểm tra tính nhất quán, đường dẫn và định dạng; không chạy build hoặc tạo test ứng dụng không liên quan.
- Kết thúc mỗi lần làm việc: nêu thay đổi, kiểm chứng đã thực hiện, giới hạn còn lại và bước tiếp theo nếu có.

### 12.1. Cài thư viện Python trên Windows

- Với prototype Windows, dùng `python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt` theo README và tài liệu giai đoạn 1.
- Giữ môi trường ảo đang hoạt động; không tạo lại `.venv` chỉ vì cài thư viện chậm.
- Đọc log để phân biệt `Downloading` còn tăng dung lượng, `Retrying` do yêu cầu mạng thất bại và `Building wheel` đang biên dịch; không xem mọi lần chờ là cùng một lỗi.
- `--only-binary=:all:` chỉ tránh biên dịch từ mã nguồn; không xử lý tình trạng kẹt ghi cache và sẽ báo lỗi nếu không có wheel phù hợp.
- Nếu traceback đi qua `tempfile`, `adjacent_tmp_file` và `pip/_internal/network/cache.py`, xác định thao tác tạo file tạm cho cache HTTP đang bị kẹt; dùng `--no-cache-dir` để bỏ qua cache này.
- Không khẳng định nguyên nhân là Python 3.14, cache hỏng hoặc quyền thư mục khi chưa có bằng chứng tương ứng.
- Không xóa cache, đổi cấu hình pip toàn cục hoặc chạy nhiều lệnh pip đồng thời trên cùng môi trường khi chưa cần; dừng lệnh đang kẹt trước khi thử lại.
- Sau cài, kiểm tra `python -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"`; xem [hướng dẫn xử lý pip bị kẹt](docs/phase-1-phone-camera-yolo.md#34-xử-lý-pip-bị-kẹt-khi-cài-thư-viện) để chẩn đoán tiếp nếu cần.

## 13. Tài liệu tham chiếu

Đối chiếu tài liệu chính thức khi triển khai; các điều kiện API, runtime và giấy phép có thể thay đổi.

- [YOLOv8: mô hình và nhiệm vụ](https://docs.ultralytics.com/models/yolov8)
- [YOLO: inference và hậu xử lý](https://docs.ultralytics.com/modes/predict)
- [OpenCV: đọc camera và luồng video](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html)
- [DroidCam: client Windows và webcam ảo](https://droidcam.app/windows/)
- [DroidCam: Wi-Fi, USB và xử lý kết nối](https://droidcam.app/help/)
- [DroidCam Classic: Wi-Fi/USB và IP Cam](https://www.dev47apps.com/droidcam/connect/)
- [IP Webcam: một lựa chọn truyền camera Android qua Wi-Fi](https://play.google.com/store/apps/details?id=com.pas.webcam)
- [Luồng text và TTS của repository](docs/object-narration.md)
- [Cài, kiểm tra và chẩn đoán giọng tiếng Việt trên Windows](docs/windows-vietnamese-voice.md)
- [LiteRT: lượng tử hóa và kiểm tra độ chính xác](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_quantization)
- [Android: trạng thái NNAPI](https://developer.android.com/ndk/guides/neuralnetworks)
- [ML Kit OCR trên Android](https://developers.google.com/ml-kit/vision/text-recognition/v2/android)
- [Android: cảm biến hướng](https://developer.android.com/develop/sensors-and-location/sensors/sensors_position)
- [Google Routes: lập tuyến](https://developers.google.com/maps/documentation/routes/compute-route-over)
- [Google Routes: chính sách dữ liệu và lưu trữ](https://developers.google.com/maps/documentation/routes/policies)
- [Android: TTS Voice và yêu cầu mạng](https://developer.android.com/reference/android/speech/tts/Voice)
- [Android: SpeechRecognizer](https://developer.android.com/reference/android/speech/SpeechRecognizer)
- [MiDaS: chiều sâu tương đối](https://github.com/isl-org/MiDaS#applications)
- [OpenAI: hướng dẫn AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

