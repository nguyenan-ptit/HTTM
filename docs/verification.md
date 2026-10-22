# Báo cáo triển khai và kiểm chứng ngày 22/10/2026

## Phạm vi đã triển khai

Prototype Python trên máy tính: DroidCam/OpenCV → YOLOv8n → hộp bao/nhãn/confidence → câu tiếng Việt → FeedbackManager → TTS Windows. Có điều khiển `m`/`q`, `--mute`/`--no-detect`, trạng thái lỗi và ghi số đo JSONL tùy chọn. Chưa triển khai Android, GPS, đo mét, đánh giá nguy cơ, OCR, STT, SOS hoặc INT8.

Camera có một worker sở hữu thiết bị, chỉ giữ ảnh mới nhất, tự thử lại khi đọc lỗi và đổi phiên khi reconnect. Inference kiểm tra tuổi/phiên trước và sau xử lý; UI chỉ ghép hộp bao lên đúng ảnh đã nhận diện. Driver đọc bị treo làm dữ liệu hết hạn; không mở camera thứ hai cạnh tranh. Kiểm tra ảnh lặp tuyệt đối mặc định 5 giây có thể báo nhầm cảnh tĩnh và có thể bỏ sót khi overlay vẫn đổi; không chứng minh toàn bộ kết nối đang tốt.

Narration dịch đủ 80 nhãn COCO, gộp loại/vị trí và tạo câu tiếng Việt có dấu. Lớp model tùy chỉnh lấy tên từ model, không suy theo số class COCO; lớp chưa dịch được mô tả chung. TTS có WinRT/SAPI/OneCore, chỉ chọn `vi`/`vi-VN`. Worker âm thanh riêng; mọi phát âm thanh, kể cả câu mẫu CLI, đi qua FeedbackManager. Có TTL từ ảnh nguồn, chống lặp, thay câu chờ, hủy và chống callback/tiến trình cũ phát lại.

## Môi trường và kiểm thử đã chạy

Máy Windows 10 build 19045, AMD64, CPython **3.14.0**. Đã tạo `.venv` vì ban đầu chưa có; bootstrap pip **25.2** thành công sau khi xử lý giới hạn thư mục tạm trong tiến trình cài đặt. Không thay cài đặt Python, giọng hoặc registry của Windows.

| Kiểm chứng | Kết quả thực tế |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests -q` | **80 ca: 79 đạt, 1 bỏ qua** do `.venv` thiếu OpenCV/NumPy/Pillow cho render; không có ca lỗi |
| `py -3.14 -m unittest discover -s tests -q` | **80/80 đạt**, dùng các thư viện render đã có ở Python ngoài `.venv` |
| `python -m compileall -q prototype tests tools` | Đạt trong `.venv`; kiểm tra cú pháp, không phải chạy thiết bị |
| CLI `prototype.main --help`, `prototype.model_tools --help`, `prototype.speech --help` | Đã chạy, hiển thị các tùy chọn; đã sửa lỗi encoding của trợ giúp giọng trên Windows |
| `py -3.14 -m tools.preview_display` | Render PNG bằng dữ liệu tổng hợp; đã xem ảnh và kiểm tra dấu tiếng Việt, hộp bao/nhãn/confidence và vùng trạng thái |
| `prototype.speech --list-voices` | Chạy thật API Windows, kiểm kê/tổng hợp RAM; **không phát loa**, có lỗi tổng hợp như bảng dưới |
| Cài `requirements.txt` vào `.venv` | Chưa thành công: pip không trả phiên bản phù hợp (`No matching distribution found`), kể cả khi chỉ định PyPI; chưa kết luận do phiên bản Python |
| `prototype.model_tools --download` | Chưa thành công: `URLError`; yêu cầu mạng từ shell nhận lỗi kết nối bị từ chối. Chưa có model/checksum/manifest thực tế |
| DroidCam Wi-Fi/USB, YOLO trên ảnh thật, phát/nghe tiếng Việt | **Chưa kiểm chứng** |

Thư viện dùng để render ở Python ngoài `.venv`: OpenCV **4.13.0**, NumPy **2.4.4**, Pillow **12.2.0**. Chúng khác bộ pin trong `requirements.txt`; kết quả render không chứng minh đã cài/kiểm thử thành công toàn bộ bộ dependency đã pin. Chưa có torch/Ultralytics ở môi trường đã kiểm tra.

Các kiểm thử camera/detector/TTS dùng IO giả, không mở camera, tải model hoặc phát loa. Chúng bao phủ:

- Hướng ảnh, original bbox, lọc score/tọa độ lỗi, không NMS lần hai, lớp model tùy chỉnh.
- Ảnh cũ/tương lai, mất dữ liệu, đổi phiên, inference muộn, lấy ảnh mới nhất và thoát khi driver giả bị treo.
- Câu Việt, trái/giữa/phải và ranh giới, gộp nhóm, confidence thấp, không phát hiện, lớp chưa dịch, giới hạn độ dài.
- Chỉ một câu đang phát; thay câu chờ, chống lặp, TTL, mute/unmute, context đổi trong lúc start/poll/stop, giữ handle khi hủy lỗi.
- Ghép luồng camera/pipeline/narration/feedback và vòng UI: lỗi TTS vẫn còn video/text; mất dữ liệu hủy lời cũ.
- Công cụ model và metrics không ghi đè model/video/manifest/tệp có sẵn; cleanup không xóa tệp tải dở của tiến trình khác.

Không có số đo Camera FPS, YOLO FPS hoặc độ trễ âm thanh thật trong báo cáo này. Thời gian chạy unittest không phải hiệu năng ứng dụng.

## Kết quả giọng thực tế

| Mức kiểm tra | Quan sát |
| --- | --- |
| Giọng đã cài | Microsoft An, `vi-VN`, OneCore; `vietnameseInstalled: true` |
| WinRT | Liệt kê `AllVoices` lỗi **`0x800455A0`**, “Internal Speech Error” |
| SAPI thường | API truy cập được, không liệt kê được giọng Việt |
| SAPI-OneCore | API liệt kê được An; tổng hợp RAM lỗi **`0x80045040`** |
| Dữ liệu tổng hợp | Chưa tạo thành công dữ liệu âm thanh tiếng Việt |
| Phát/nghe | Chưa phát thử; chưa có xác nhận nghe |

Các mã lỗi chưa xác định nguyên nhân gốc và không đủ kết luận thiếu gói tiếng Việt. Không sửa/copy registry, cài lại Python hoặc chuyển giọng Anh. Xem [hướng dẫn giọng Windows](windows-vietnamese-voice.md) để chẩn đoán theo backend/stage.

## Những bước còn cần để nghiệm thu trên thiết bị

1. Cài thành công dependency trong `.venv` khi có nguồn wheel/mạng sử dụng được; tải model từ nguồn cố định, ghi SHA-256 thực và kiểm kê bằng `--classes`. Công cụ `--inspect` chỉ tính hash/size, không nạp model; `--classes` cần model tin cậy và dependency inference.
2. Mở DroidCam app/client, xác nhận preview đang chuyển động và nguồn OpenCV thực tế. Thử `--no-detect`, hướng ảnh và ngắt/kết nối lại phương thức đang dùng. Nguồn `1` trong hướng dẫn chỉ là ví dụ.
3. Chạy YOLO/text với `--mute`; kiểm tra hộp bao, lớp, trái/giữa/phải trên ảnh thật. Đo FPS/inference/tuổi ảnh bằng `--metrics`; có thể dùng lại đường dẫn, chương trình tự thêm số vào tên để giữ log riêng cho mỗi phiên. Log không đo thời điểm cảm biến điện thoại thu hình hoặc độ trễ đầu cuối đến âm thanh.
4. Khắc phục lỗi API/tổng hợp giọng dựa trên chẩn đoán thực tế. Sau khi tổng hợp thành công, chạy `prototype.speech --test` để phát mẫu và ghi xác nhận nghe qua loa/tai nghe máy tính.
5. Chạy toàn luồng, thử mute, camera mất hình, model/engine lỗi và thoát khi đang đọc. Ghi thiết bị, cấu hình, thời lượng, nguồn/checksum và phần chưa thử theo [bảng nghiệm thu](phase-1-phone-camera-yolo.md#5-nghiệm-thu-thực-tế).
6. Kiểm kê và đánh giá `stop sign`/`traffic light` theo [kế hoạch biển báo](traffic-sign-evaluation.md). Hiện chỉ có công cụ/quy trình; chưa có dữ liệu hoặc số đo nhận diện biển thật, chưa huấn luyện model mới.

Hướng dẫn chạy và cấu trúc mã nằm trong [README](../README.md).

## Cập nhật: test giọng có tiếng, luồng camera không phát

Người dùng đã xác nhận nghe được test âm thanh sau lần kiểm tra ban đầu. Dependency đã có trong `.venv` đúng bộ pin, cùng `yolov8n.pt`; các giới hạn cài đặt/model ở phần trên là lịch sử của lần triển khai đầu, không còn mô tả trạng thái chuẩn bị hiện tại.

Đã đọc log thực tế `reports/session.jsonl` của lần chạy `--source 1 --imgsz 320`: phiên dài khoảng 45,63 giây, một phiên camera, 366 kết quả nhận diện được hiển thị. Tuổi ảnh p50 khoảng 147,6 ms, p95 khoảng 311,5 ms; thời gian lời gọi inference p50 khoảng 86,6 ms, p95 khoảng 244,2 ms. Sau khởi động, camera/model có dữ liệu mới. Log có các trạng thái đang đọc/dừng/sẵn sàng/tắt tiếng nhưng không có lỗi TTS. Trạng thái “Đang đọc” của bản cũ chỉ cho biết đã mở worker, không chứng minh âm thanh đã phát. Log cũ chưa có lý do hủy hoặc số lần hoàn tất, nên không đủ xác định mọi lần im tiếng.

Lỗi điều phối đã tái hiện bằng engine giả khởi động chậm: dù liên tục nhận frame mới cùng các nhóm ở 10 Hz, câu bị TTL 2 giây tính từ ảnh đầu hủy trước mốc phát 2,5 giây. Chống lặp còn được đánh dấu ngay lúc khởi chạy, nên một câu chưa phát xong bị chặn thêm. Test giọng riêng dùng TTL 30 giây không gặp cùng điều kiện này.

Bản sửa tách câu đã gửi khỏi bằng chứng tiếp diễn. Chỉ ảnh mới còn hạn xác nhận đầy đủ các nhóm đang đọc mới duy trì được lời; TTL vẫn tính từ timestamp bằng chứng, không phải từ thời điểm xử lý. Không sửa text đang đọc, không gia hạn bằng frame cũ và không phục hồi câu đã hết hạn. Mất camera/model, đổi phiên, mute hoặc mất nhóm đang đọc vẫn hủy. Chống lặp được ghi sau khi worker báo hoàn tất thành công. Metrics mới thêm số lần bắt đầu/hoàn tất/hủy, lý do gần nhất và tuổi bằng chứng, không lưu nội dung câu.

Ngoài kiểm thử bằng engine giả, đã nạp model YOLOv8n thật trong `.venv`, chạy trên `bus.jpg` đi kèm Ultralytics: có 4 detection thuộc `person`/`bus`, tạo được câu tiếng Việt. Đây là ảnh mẫu có sẵn, không phải lần mở camera điện thoại. Chưa xác nhận nghe lại luồng camera sau bản sửa; cần chạy lại với tệp metrics mới, ví dụ `reports/session-audio.jsonl`.

Kiểm chứng sau bản sửa: **90/90 kiểm thử đạt trong `.venv`**, không có ca bỏ qua; `compileall` cho `prototype`/`tests` đạt. Trong đó 23 ca feedback bao gồm engine khởi động 2,5 giây với bằng chứng mới liên tục, hết hạn sau bằng chứng cuối, cùng frame không gia hạn, thứ tự câu thay đổi, thêm/mất nhóm, cập nhật trong lúc `poll()` chậm và callback sau hủy. Đây là bằng chứng kiểm thử logic, chưa phải xác nhận tiếng qua loa ở luồng camera thật.

## Cập nhật: chạy lại cùng đường dẫn log

Người dùng xác nhận lỗi chặn chạy lại là `FileExistsError` tại `reports/session-audio.jsonl`. Nguyên nhân là bản trước yêu cầu tạo tệp mới bằng chế độ `x` nhưng chưa tự chọn tên khác khi tệp đã có. Không có bằng chứng từ lỗi này rằng việc nhắn tin làm dừng camera.

Đã sửa để chạy lại cùng lệnh: giữ nguyên tệp cũ, thử lần lượt `session-audio-1.jsonl`, `session-audio-2.jsonl`… bằng phép tạo độc quyền để tránh ghi đè kể cả khi trùng tên đồng thời. Terminal in đường dẫn log thực tế; record `run` cũng ghi `metrics_file`. Vẫn từ chối ghi metrics trùng model/video và bỏ qua tên thay thế có thể trùng các đường dẫn đó.

Kiểm thử dùng IO giả chạy vòng main hai lần liên tiếp cùng `--metrics` đã qua bước khởi động camera/hiển thị cả hai lần, tạo hai log riêng và giữ nguyên byte của log cũ. Không mở camera thật hoặc phát tiếng trong kiểm thử này.
