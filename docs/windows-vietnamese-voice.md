# Giọng tiếng Việt trên Windows

## Phạm vi

Prototype dùng giọng cục bộ qua WinRT, SAPI hoặc SAPI-OneCore; không dùng cloud TTS hoặc giọng tiếng Anh để đọc tiếng Việt. Microsoft liệt kê giọng tiếng Việt **An** trong danh sách giọng Windows; tên trong API có thể kèm tiền tố/hậu tố. Chỉ chọn voice có ngôn ngữ `vi`/`vi-VN`, không chọn dựa riêng vào tên. [Danh sách giọng Microsoft và cách thêm giọng](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices).

Âm thanh ra loa/tai nghe **máy tính**. DroidCam truyền video và không tự đưa lời cảnh báo về điện thoại. Trong lần tạo prototype chưa nghe thử giọng thật; kiểm kê thành công hoặc engine giả không được ghi thành đã nghe tiếng Việt.

**Cập nhật từ người dùng:** sau lần kiểm tra ban đầu, người dùng đã xác nhận lệnh test âm thanh có tiếng, nhưng luồng camera chưa phát tiếng. Bảng chẩn đoán ban đầu bên dưới là kết quả tại ngữ cảnh/thời điểm đã ghi, không phải kết luận rằng mọi lần chạy hiện tại đều không phát được giọng. Với trường hợp test có tiếng, kiểm tra điều phối/TTL và backend của lệnh camera trước khi thay đổi gói giọng.

### Kết quả chẩn đoán tại máy ngày 22/10/2026

Đã chạy kiểm kê và tổng hợp thử vào RAM, **không phát loa**:

| Thành phần | Quan sát thực tế |
| --- | --- |
| Giọng đã cài | Có Microsoft An `vi-VN` trong OneCore; `vietnameseInstalled: true`, có tệp dữ liệu/engine tương ứng |
| WinRT | Liệt kê `AllVoices` lỗi `0x800455A0`, thông báo “Internal Speech Error”; chưa truy cập thành công |
| SAPI thường | Truy cập API/liệt kê được, không thấy giọng `vi` |
| SAPI-OneCore | Liệt kê được giọng Việt; tổng hợp vào RAM lỗi `0x80045040` (`SPERR_INVALID_REGISTRY_KEY`) |
| Phát và nghe | Chưa thử phát; chưa nghe thực tế; chưa tổng hợp tiếng Việt thành công |

Đây là kết quả của máy và thời điểm trên, chưa phải chẩn đoán nguyên nhân gốc. Đặc biệt, giọng đã cài mà API/tổng hợp lỗi không đủ để kết luận thiếu gói tiếng Việt. Mã `0x80045040` chỉ ra khóa mà API sử dụng không hợp lệ theo [tài liệu mã lỗi Speech của Microsoft](https://learn.microsoft.com/en-us/previous-versions/office/developer/speech-technologies/jj127491%28v%3Dmsdn.10%29); nó không chỉ rõ khóa nào hoặc cho phép tự suy rằng cần sửa/copy registry. Giữ nguyên hệ thống và xem lỗi theo từng bước bên dưới.

## Bốn mức bằng chứng

| Mức | Bằng chứng | Chưa kết luận được |
| --- | --- | --- |
| Giọng đã cài | `vietnameseInstalled`, `installedVoices` từ kiểm kê | API đang chạy có dùng được giọng hay không |
| API truy cập được | `apiAccessible` và danh sách `voices` từng backend | Có tổng hợp được dữ liệu hay không |
| Tổng hợp thành công | `synthesisSucceeded`, số `audioBytes` có dữ liệu | Loa/tai nghe đã phát và người thử đã nghe |
| Phát và nghe | API phát hoàn tất, người thử xác nhận đầu ra/câu/ngôn ngữ | Chất lượng trong mọi môi trường hoặc khả năng offline chưa thử |

WinRT tách việc tổng hợp stream và việc phát stream; vì thế tạo được dữ liệu chưa đủ chứng minh nghe được. [Microsoft SpeechSynthesizer](https://learn.microsoft.com/en-us/uwp/api/windows.media.speechsynthesis.speechsynthesizer).

## Chẩn đoán không phát loa

Chạy tại thư mục gốc dự án trong `.venv` hiện có:

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --list-voices
```

Lệnh này kiểm kê registry theo chế độ chỉ đọc, truy cập API và có thể tổng hợp câu ngắn vào RAM cho các backend. **Không phát qua loa.** Kết quả JSON gồm `vietnameseInstalled`, `installedVoices`, `voices` và mảng `backends`; mỗi backend có `apiAccessible`, `voices`, `synthesisSucceeded`, `audioBytes` và `error` khi lỗi.

`ok: true` của công cụ chỉ xác nhận tác vụ chẩn đoán chạy xong. Xem `synthesisSucceeded` của backend để biết tổng hợp được hay chưa. `playbackAttempted: false`, `playbackCompleted: null`, `heardConfirmed: null` không phải lỗi: lệnh kiểm kê chưa thử phát/nghe.

Có thể cô lập từng backend; các lệnh sau cũng không phát loa:

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --list-voices --backend winrt
.\.venv\Scripts\python.exe -m prototype.speech --list-voices --backend sapi
.\.venv\Scripts\python.exe -m prototype.speech --list-voices --backend onecore
```

Lựa chọn của `prototype.speech --backend` là `auto`, `winrt`, `sapi`, `onecore`. `prototype.main --backend` chọn backend **camera** (`auto/dshow/msmf`); CLI chính dùng `--speech-backend` để chọn backend giọng và `--voice-id` để chỉ định giọng. Các tên tùy chọn thuộc hai CLI khác nhau.

## Nghe thử qua máy tính

Lệnh sau **phát âm thanh thật**. Chuẩn bị loa/tai nghe và mức âm lượng phù hợp trước khi chạy:

```powershell
.\.venv\Scripts\python.exe -m prototype.speech --test
```

Khi cần kiểm tra một giọng cụ thể, sao chép chính xác ID từ kết quả `--list-voices` của backend tương ứng, truyền bằng `--voice-id`. Không lấy ID minh họa làm ID trên máy:

```powershell
# Thay ID_GIONG_THUC_TE bằng ID đã kiểm tra, lệnh này phát loa.
.\.venv\Scripts\python.exe -m prototype.speech --test --backend onecore --voice-id 'ID_GIONG_THUC_TE'
```

`playbackCompleted: true` chỉ có nghĩa API báo phát hoàn tất; `heardConfirmed` không tự chuyển thành xác nhận của con người. Người thử ghi riêng: ngày, Windows, backend/voice ID/ngôn ngữ, đầu ra loa/tai nghe, câu nghe được và dấu/tên vật có rõ không. Sau khi chuẩn bị model và giọng, muốn kết luận offline thì thử không có Internet; Wi-Fi nội bộ DroidCam vẫn cần kết nối nếu dùng phương thức đó.

## Khi thiếu giọng hoặc có lỗi

Nếu chưa có giọng tiếng Việt trong kiểm kê và Windows Settings, dùng phần quản lý giọng của Windows để thêm tiếng Việt. Microsoft hướng dẫn vào Narrator settings, thêm legacy voices rồi `Manage voices > Add voices`; vị trí có thể khác giữa Windows 10/11. Có giọng trong Narrator vẫn cần kiểm tra lại khả năng truy cập của từng API. [Hướng dẫn Microsoft](https://support.microsoft.com/en-us/accessibility/windows/narrator/appendix-a-supported-languages-and-voices).

Nếu đã thấy An/tiếng Việt nhưng không tổng hợp/phát được:

1. Giữ JSON lỗi đầy đủ: `backend`, `stage`, `message`, `hresults`, voice ID/ngôn ngữ và kiến trúc tiến trình. So sánh cùng giọng qua từng backend bằng `--list-voices`.
2. Phân biệt lỗi kiểm kê/API, chọn giọng, tổng hợp hay phát. WinRT lỗi không đủ kết luận thiếu gói tiếng Việt; backend khác truy cập được là bằng chứng cần xem xét riêng.
3. Nếu tổng hợp có dữ liệu mà không nghe, kiểm tra output device Windows, âm lượng ứng dụng, mute và tai nghe; thử lại bằng `--test` chỉ sau khi đã xác định đúng giọng.
4. Giữ video/text bằng `--mute` trong lúc sửa âm thanh. Không copy/sửa registry, cài lại Python hoặc đổi sang giọng Anh chỉ vì một backend thất bại.

Ví dụ ý nghĩa mã HRESULT phổ biến dưới đây là gợi ý xác định bước lỗi, không phải chẩn đoán máy hiện tại:

| Mã | Ý nghĩa Microsoft | Việc cần kiểm tra |
| --- | --- | --- |
| `0x80070005` | Từ chối truy cập | Giai đoạn/API và ngữ cảnh tiến trình, không suy ngay thiếu giọng |
| `0x80070057` | Tham số không hợp lệ | Voice ID, ngôn ngữ, tham số chuyển vào API |
| `0x80004005` | Lỗi không xác định | Xem thông báo gốc và backend/stage, không đoán nguyên nhân |
| `0x80000013` | Đối tượng đã đóng | Vòng đời/hủy/callback muộn khi đang tổng hợp/phát |

Tra nghĩa mã và giữ nguyên thông báo gốc theo [bảng lỗi COM/WinRT của Microsoft](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-1). Không có mã trong bảng này thì tra tài liệu chính thức cho đúng API; không thay bằng một nguyên nhân suy đoán.

## Kiểm tra luồng đầy đủ

Khi test giọng nghe được mà camera không đọc, bản sửa điều phối cho phép frame mới còn xác nhận cùng các nhóm duy trì bằng chứng hợp lệ cho câu đang đọc. Trước đây tiến trình có thể bị hủy sau 2 giây từ ảnh đầu, dù cùng vật vẫn được nhận diện, trong khi test riêng có TTL 30 giây. Không giải quyết bằng cách bỏ kiểm tra ảnh cũ hoặc tăng mọi TTL lên 30 giây. Ghi log bằng `--metrics reports/session-audio.jsonl`; khi tên đã có, chương trình tự thêm số để tạo log mới. Xem `speech_started`/`speech_completed`/`speech_cancelled`/`speech_last_event` và tuổi bằng chứng. Nếu test đã dùng `--backend` hoặc `--voice-id`, truyền tương ứng `--speech-backend`/`--voice-id` cho `prototype.main`.

Sau khi nghe mẫu thành công, chạy [các bước giai đoạn 1](phase-1-phone-camera-yolo.md#4-chạy-theo-từng-bước). Trong video thật, so sánh câu hiện với câu nghe; thử `m`, mất camera, model lỗi và thoát khi đang đọc. Chỉ có một câu đang phát, câu chờ cũ được thay bằng mới; lời từ ảnh cũ/phiên cũ phải bị hủy. Khi TTS lỗi, video và text tiếp tục, trạng thái âm thanh báo lỗi. Không coi test dùng engine giả là bằng chứng engine Windows đã phát thành công.
