# Model cho prototype

Model mặc định: Ultralytics **YOLO11s detection**, pretrained COCO 80 lớp, định dạng `.pt`. Không thêm tên lớp để giả lập khả năng nhận diện biển mới.

Nguồn cố định: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --download            # hoặc --name yolo11m.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolo11s.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --classes yolo11s.pt
```

Sau tải thành công, `models/manifest.json` ghi release, URL, SHA-256 thực đo, số byte và thời điểm. Repository không ghi checksum giả khi chưa tải được tệp. Có thể đối chiếu digest độc lập bằng `--sha256 HEX`. Nếu tải ngoài công cụ này, cần lưu nguồn/phiên bản/giấy phép/checksum thực tế riêng; `--inspect` không chứng minh nguồn model và không thực thi/nạp model.

`--classes` nạp model `.pt` cục bộ tin cậy (cần dependency inference) và liệt kê `class_id`, tên gốc, bản dịch, khả năng có nhãn `stop sign`/`traffic light`. Đây là kiểm kê lớp, chưa phải đánh giá nhận diện thực tế. Công cụ tải không ghi đè model, manifest hoặc tệp tải dở có sẵn.

[Giấy phép Ultralytics](https://www.ultralytics.com/license): AGPL-3.0 hoặc Enterprise tùy điều kiện sử dụng; đọc điều kiện của nhà phát hành trước khi phân phối sản phẩm/model. Dữ liệu COCO và các thư viện liên quan có điều kiện riêng; xem [trang dữ liệu COCO của Ultralytics](https://docs.ultralytics.com/datasets/detect/coco/). Công cụ này không đóng gói model hoặc cấp lại quyền sử dụng.

YOLO11s COCO có `stop sign` và `traffic light`. Phát hiện `traffic light` không phân loại màu đèn; COCO chưa bao quát hệ thống biển Việt Nam. Kiểm chứng chất lượng riêng trên dữ liệu có quyền sử dụng trước khi bổ sung model.
