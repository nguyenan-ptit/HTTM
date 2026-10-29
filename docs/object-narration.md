# Luồng mô tả vật thể bằng tiếng Việt

## Dữ liệu và trách nhiệm

```text
DroidCam → OpenCV → Frame của phiên camera
    → YOLOv8n → DetectionResult (lớp, confidence, bbox)
        ├→ ảnh nguồn + hộp bao + nhãn tiếng Việt + confidence
        └→ narration.narrate(...) → Narration còn hạn
            → FeedbackManager → WindowsSpeechEngine → loa/tai nghe máy tính
```

YOLO trả kết quả phát hiện; `narration.py` dùng bảng nhãn và mẫu câu để tạo text. TTS đọc đúng text đó. Đây không phải OCR, dịch trực tuyến hoặc văn bản do LLM tạo. Không có nhận diện màu đèn, khoảng cách, hướng tránh hay quyết định sang đường.

Các kiểu dữ liệu trong `prototype/types.py` giữ câu gắn với nguồn:

| Kiểu | Nội dung dùng trong luồng |
| --- | --- |
| `Frame` | `session_id`, `frame_id`, `captured_at`, ảnh và kích thước |
| `Detection` | `class_id`, `label`, `score`, `bbox=(x1,y1,x2,y2)` |
| `DetectionResult` | Ảnh nguồn, danh sách detection, thời gian inference/hoàn tất và lỗi |
| `Narration` | `text`, `groups`, phiên/frame, thời điểm ảnh nguồn, `expires_at`, `dedup_key` |

`captured_at` do máy tính ghi sau khi đọc ảnh bằng đồng hồ đơn điệu. Nó không đo thời điểm điện thoại thu ảnh và không loại được toàn bộ độ trễ DroidCam/driver. Mọi phép tính tuổi/TTL trong ứng dụng phải cùng đồng hồ này.

## Tạo câu

`label_vi(label)` dịch đủ 80 tên lớp COCO và chuẩn hóa viết hoa, khoảng trắng, dấu gạch dưới. Ví dụ `person` → “người”, `car` → “ô tô”, `stop sign` → “biển báo dừng”. Danh sách thực sự được model hỗ trợ vẫn lấy từ model; bảng dịch không thêm khả năng nhận diện. [Danh sách COCO trong cấu hình Ultralytics](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/datasets/coco.yaml).

`narrate(result, session_id=..., now=...)` chỉ nhận kết quả không lỗi, đúng phiên, có tuổi `0 <= now - captured_at < max_age` và bbox/score hợp lệ. Ngưỡng mặc định `min_confidence=0.45`, tuổi tối đa `2` giây, tối đa `3` nhóm và `180` ký tự; đây là cấu hình ban đầu cần đánh giá. Bbox rỗng, đảo chiều, ngoài ảnh, không hữu hạn hoặc score ngoài `[0,1]` bị loại.

Vị trí lấy từ tâm hộp bao theo chiều rộng **ảnh mà detector thực sự nhận**, sau rotation/mirror của camera và trước resize/letterbox nội bộ YOLO:

| Tâm hộp bao | Cụm từ |
| --- | --- |
| Nhỏ hơn `width/3` | “ở bên trái” |
| Từ `width/3` đến nhỏ hơn `2*width/3` | “ở giữa ảnh” |
| Từ `2*width/3` trở lên | “ở bên phải” |

Ví dụ khi có detection phù hợp: “Có người ở bên trái.”, “Có ô tô ở giữa ảnh.”, “Có biển báo dừng ở bên phải.” Đây là ví dụ quy tắc, chưa phải phát hiện thật.

Các bbox cùng nhãn/vị trí tạo một câu. Không đọc số lượng từ số bbox vì nhiều bbox không nhất thiết là nhiều vật thật. Ưu tiên người, phương tiện, biển/đèn rồi các lớp khác; trong cùng mức ưu tiên chọn confidence cao hơn. Đây là thứ tự mô tả, không phải đánh giá nguy hiểm hoặc cảnh báo khẩn P1. Chỉ thêm câu trọn vẹn nằm trong giới hạn độ dài.

Lớp chưa dịch dùng “vật thể chưa có bản dịch”; không lộ chuỗi model tùy ý thành nội dung như thể đã dịch chính xác. `groups` vẫn lưu tên lớp chuẩn hóa và vị trí, ví dụ `person:left`; `dedup_key` ổn định với cùng tập nhóm kể cả thứ tự detection/confidence thay đổi. Nếu không có nhóm hợp lệ, trả `None`; UI thông báo tình trạng riêng và không đọc “đường an toàn”.

## Hiển thị và âm thanh

UI dùng nhãn từ cùng `label_vi`, phông Unicode hỗ trợ dấu, hiện đúng câu được chuyển cho `FeedbackManager`. Một thành phần sở hữu camera; inference và TTS chạy ngoài vòng hiển thị. Hàng đợi video/inference ưu tiên ảnh mới, không tích lũy ảnh cũ.

`FeedbackManager` sở hữu việc đọc: tối đa một câu đang phát và một câu chờ mới nhất; thay câu chờ cũ, chống lặp và kiểm tra TTL từ ảnh nguồn. Không gọi TTS từ từng detection hoặc vòng vẽ ảnh. Mute, ảnh cũ, mất camera, đổi phiên, lỗi model hoặc thoát phải hủy câu hết hiệu lực; callback muộn không được phát lại câu đã hủy. Khi không truy cập/phát được giọng Việt, video và text tiếp tục cùng trạng thái âm thanh rõ ràng.

Câu đang gửi engine và bằng chứng xác nhận tiếp diễn là hai dữ liệu riêng. Một frame **mới hơn, còn hạn, đúng phiên**, xác nhận đầy đủ các nhóm loại/vị trí đang đọc có thể thay bằng chứng tiếp diễn; text và nguồn gốc câu đã gửi không bị sửa. Thêm nhóm khác không làm câu cũ sai. Đổi thứ tự confidence cũng không cần khởi động lại lời đọc. Không gia hạn từ cùng frame, từ timestamp cũ hơn hoặc phục hồi câu đã hết hạn. Nếu một nhóm đang đọc mất xác nhận hoặc không có mô tả hợp lệ thì hủy; khi mất camera/model, đổi phiên hoặc mute cũng hủy ngay. Không có bằng chứng mới thì hết hạn sau `max_age` của bằng chứng cuối.

Khoảng chống lặp mặc định 6 giây bắt đầu sau khi engine báo hoàn tất thành công, không phải ngay khi mở tiến trình PowerShell. Nhờ đó lần khởi tạo giọng bị hủy trước âm thanh không bị tính là đã đọc xong. Log số đo ghi số lần bắt đầu/hoàn tất/hủy và lý do sự kiện gần nhất, không ghi nội dung câu.

TTS dùng Windows WinRT/SAPI/OneCore và chỉ chọn giọng `vi`/`vi-VN`. Không tự dùng giọng Anh, cloud TTS hoặc thêm engine khác khi backend lỗi. [Chẩn đoán giọng tiếng Việt](windows-vietnamese-voice.md).

## Kiểm chứng

`tests/test_narration.py` dùng bbox và thời gian tổng hợp để kiểm tra ánh xạ, vị trí/ranh giới, nhóm trùng, confidence thấp, không có phát hiện, lớp chưa dịch, phiên khác, ảnh cũ/tương lai, lỗi model, bbox/score lỗi, giới hạn độ dài và TTL theo ảnh nguồn. Kết quả kiểm thử này không chứng minh độ chính xác YOLO hay chất lượng giọng trên máy thật.

Khi nghiệm thu, đặt vật có lớp model hỗ trợ ở trái/giữa/phải; kiểm tra ảnh lật/xoay, câu hiện và câu nghe. Thử mute, mất kết nối, model lỗi, engine lỗi, đổi phiên và thoát trong lúc đang đọc. Ghi riêng những gì đã kiểm chứng bằng test, video thật và nghe thật theo [hướng dẫn giai đoạn 1](phase-1-phone-camera-yolo.md).
