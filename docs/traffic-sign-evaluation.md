# Đánh giá và bổ sung nhận diện biển báo

## Khả năng hiện tại

YOLOv8n pretrained COCO có lớp `stop sign` và `traffic light`; không có đủ các lớp biển báo Việt Nam hoặc lớp màu đỏ/vàng/xanh của đèn. Sau khi chuẩn bị model, dùng `--inspect` để tính checksum/kích thước mà không nạp model. Dùng `--classes` để đọc danh sách lớp từ model thực tế:

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolov8n.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --classes yolov8n.pt
```

`--classes` cần các dependency inference đã cài và **nạp tệp model cục bộ**; chỉ dùng với `.pt` có nguồn đáng tin cậy. Output gồm `class_id`, `label`, `label_vi` và thông tin các lớp nền cần kiểm tra. Danh sách lớp cho biết khả năng biểu diễn của model, chưa chứng minh độ chính xác nhận diện. Trong lần tạo prototype chưa chạy kiểm tra này với model thật vì chưa tải được model.

Đối chiếu output `--classes` với [cấu hình lớp COCO chính thức](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/datasets/coco.yaml) và [YOLOv8](https://docs.ultralytics.com/models/yolov8/). Thêm tên biển vào bảng dịch không tạo ra khả năng nhận diện lớp đó.

| Công việc | Đầu ra | Trạng thái hiện tại |
| --- | --- | --- |
| Phát hiện biển/đèn | Vị trí hộp bao và lớp model hỗ trợ | Có thể thử `stop sign`/`traffic light`, chưa đánh giá camera thật |
| Phân loại ý nghĩa từng biển Việt Nam | Nhãn riêng được huấn luyện/đánh giá | Chưa triển khai |
| Đọc chữ trên biển | Văn bản OCR | Ngoài mốc hiện tại |
| Nhận màu/trạng thái đèn | Kết quả riêng và bằng chứng chất lượng | Chưa triển khai |

Thông báo hiện tại chỉ như “Có biển báo dừng ở bên phải.” hoặc “Có đèn giao thông ở giữa ảnh.” khi có detection phù hợp. Không biến nó thành lệnh dừng/rẽ/sang đường hay kết luận an toàn.

## Kế hoạch đánh giá giai đoạn 1C

Chỉ chuyển sang bước này sau khi camera → YOLO → text → TTS tiếng Việt đã chạy và được kiểm chứng. Chưa có bộ dữ liệu hoặc số liệu đánh giá biển báo trong repository; bảng bên dưới là kế hoạch, không phải kết quả.

1. Chốt danh sách biển cần hỗ trợ theo tình huống sử dụng. Mỗi lớp ghi tên/ý nghĩa rõ, nguồn tham chiếu và lớp model hiện có có đáp ứng không. Không tự quy mọi biển có hình tương tự vào `stop sign`.
2. Chuẩn bị ảnh/video có quyền sử dụng, không chứa dữ liệu riêng tư không cần thiết. Bao phủ ánh sáng, góc nhìn, kích thước trong ảnh, che khuất, rung/nhòe và các vật dễ nhầm. Ghi nhãn bbox/lớp theo quy ước được kiểm tra.
3. Tách train/validation/test theo phiên quay hoặc địa điểm để ảnh gần nhau không nằm ở nhiều tập. Giữ tập test độc lập; không chọn ngưỡng trên chính tập báo cáo cuối.
4. Đo baseline model hiện tại với cấu hình đã ghi (checksum, thư viện, `imgsz`, confidence, IoU). Ghi đúng lớp không có trong model là thiếu khả năng, không chỉ là confidence thấp.
5. Với lớp thiếu, đánh giá model có nguồn/giấy phép phù hợp hoặc huấn luyện bổ sung. Chỉ tích hợp model mới sau khi có artifact thật, danh sách lớp/checksum và kết quả test riêng. Không ghi đã huấn luyện hoặc đạt độ chính xác khi chưa thực hiện.
6. So sánh bỏ sót/báo nhầm theo lớp và điều kiện; ghi precision/recall hoặc AP nếu có quy trình phù hợp, số mẫu, tiêu chí ghép bbox và ngưỡng. Đo cả thời gian inference và độ trễ/tuổi ảnh trong prototype với cùng điều kiện.
7. Kiểm tra bảng dịch, các lớp chưa dịch, câu vị trí và hủy lời cũ sau khi thay model. Kiểm tra biển nhỏ trên `imgsz 320` so với cấu hình cao hơn bằng dữ liệu thật trước khi chọn.

## Biểu mẫu ghi kết quả

| Trường | Nội dung cần điền sau khi thử |
| --- | --- |
| Ngày và người kiểm tra | Chưa thực hiện |
| Model / checksum / nguồn / giấy phép | Theo artifact thực tế |
| Thiết bị / Windows / runtime / backend | Theo máy thử |
| Dataset / quyền sử dụng / cách chia tập / số mẫu | Theo dữ liệu đã chuẩn bị |
| Lớp mục tiêu và lớp thiếu | Theo danh sách model và yêu cầu đã chốt |
| `imgsz` / confidence / IoU / độ phân giải | Theo cấu hình thử |
| Bỏ sót / báo nhầm / chỉ số theo lớp | Chưa có kết quả |
| Camera FPS / YOLO FPS / inference / tuổi ảnh | Chưa có số đo thực tế |
| Giới hạn và quyết định tiếp theo | Dựa trên bằng chứng sau thử |

Thử trong môi trường kiểm soát và ghi rõ giới hạn. Prototype hỗ trợ mô tả vật thể trong ảnh, chưa bảo đảm tránh va chạm hay quyết định thời điểm sang đường. Xem [hướng dẫn nghiệm thu giai đoạn 1](phase-1-phone-camera-yolo.md#5-nghiệm-thu-thực-tế).
