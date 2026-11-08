# Model cho hệ thống HTTM

Model mặc định: Ultralytics **YOLO11n detection (`yolo11n.pt`)**, pretrained COCO 80 lớp, định dạng `.pt` (hỗ trợ cả `yolo11s.pt`, `yolov8n.pt`, `yolov8s.pt`).

Nguồn cố định: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt

```powershell
.\.venv\Scripts\python.exe -m prototype.model_tools --download
.\.venv\Scripts\python.exe -m prototype.model_tools --inspect yolo11n.pt
.\.venv\Scripts\python.exe -m prototype.model_tools --classes yolo11n.pt
```

Sau khi tải thành công, `models/manifest.json` ghi release, URL, SHA-256 thực đo, kích thước và thời điểm tải. Có thể đối chiếu digest độc lập bằng `--sha256 HEX`.

- `--inspect`: tính SHA-256 mà không thực thi hay nạp pickle/model.
- `--classes`: nạp model `.pt` cục bộ tin cậy và liệt kê `class_id`, tên gốc và bản dịch tiếng Việt.

[Giấy phép Ultralytics](https://www.ultralytics.com/license): AGPL-3.0 hoặc Enterprise tùy điều kiện sử dụng.
