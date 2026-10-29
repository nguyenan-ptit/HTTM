"""YOLO adapter. Ultralytics handles letterbox reversal and NMS exactly once."""

from __future__ import annotations

import math
import os
from pathlib import Path
import time
from typing import Any

from .types import Detection, DetectionResult, Frame

# Lớp COCO liên quan người đi bộ; bỏ đồ ăn, dụng cụ... vì chỉ gây báo nhầm.
WALKING_CLASSES = frozenset({
    "person", "bicycle", "car", "motorcycle", "bus", "train", "truck", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "cat", "dog", "horse", "cow",
    "suitcase", "chair", "couch", "potted plant", "bed", "dining table",
})
DARK_LUMA = 80  # Độ sáng trung bình (0-255) dưới mức này thì cân bằng sáng trước khi nhận diện.


def enhance_dark(image: Any) -> Any:
    """CLAHE trên kênh sáng cho ảnh tối; ảnh đủ sáng giữ nguyên. Không sửa ảnh gốc."""
    import cv2

    # Lấy mẫu thưa để ảnh sáng không tốn chuyển màu mỗi khung hình.
    if image[::8, ::8].mean() >= DARK_LUMA:
        return image
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def parse_detections(result: Any, frame: Frame, conf: float, require_track: bool = False) -> tuple[Detection, ...]:
    """Validate boxes that Ultralytics already mapped to the original source image.

    ``require_track`` drops boxes the tracker has not confirmed yet (no id), so a
    one-frame flicker is never reported.
    """
    original_shape = getattr(result, "orig_shape", None)
    if original_shape is not None and tuple(original_shape[:2]) != (frame.height, frame.width):
        raise ValueError("Kích thước kết quả model không khớp ảnh nguồn.")
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return ()
    coordinates = boxes.xyxy.tolist()
    scores, classes = boxes.conf.tolist(), boxes.cls.tolist()
    if not (len(coordinates) == len(scores) == len(classes)):
        raise ValueError("Kết quả model có số lượng hộp và nhãn không khớp.")
    raw_ids = getattr(boxes, "id", None)
    ids = raw_ids.tolist() if raw_ids is not None else [None] * len(coordinates)
    if len(ids) != len(coordinates):
        raise ValueError("Kết quả model có số lượng hộp và mã theo dõi không khớp.")
    names = getattr(result, "names", {})
    detections = []
    for xyxy, raw_score, raw_class, raw_id in zip(coordinates, scores, classes, ids):
        if len(xyxy) != 4:
            continue
        if require_track and raw_id is None:
            continue
        try:
            score, class_number = float(raw_score), float(raw_class)
            x1, y1, x2, y2 = (float(value) for value in xyxy)
        except (TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) for value in (score, class_number, x1, y1, x2, y2)):
            continue
        if not conf <= score <= 1.0 or class_number < 0 or not class_number.is_integer():
            continue
        class_id = int(class_number)
        x1, x2 = max(0.0, min(frame.width, x1)), max(0.0, min(frame.width, x2))
        y1, y2 = max(0.0, min(frame.height, y1)), max(0.0, min(frame.height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        if isinstance(names, dict):
            label = names.get(class_id, f"class {class_id}")
        elif isinstance(names, (list, tuple)) and class_id < len(names):
            label = names[class_id]
        else:
            label = f"class {class_id}"
        track_id = int(raw_id) if raw_id is not None else None
        detections.append(Detection(class_id, str(label), score, (x1, y1, x2, y2), track_id))
    return tuple(detections)


class YoloDetector:
    def __init__(
        self,
        model_path: str | Path,
        imgsz: int = 640,
        conf: float = 0.30,
        iou: float = 0.45,
        device: str = "cpu",
        *,
        track: bool = True,
        walking_only: bool = False,
        enhance: bool = True,
    ) -> None:
        if imgsz <= 0 or imgsz % 32:
            raise ValueError("Kích thước inference phải là bội số dương của 32.")
        if not math.isfinite(conf) or not 0 < conf <= 1 or not math.isfinite(iou) or not 0 < iou <= 1:
            raise ValueError("Confidence và IoU phải trong khoảng (0, 1].")
        path = Path(model_path)
        if not path.is_file() or path.suffix.lower() != ".pt":
            raise FileNotFoundError("Chưa có model .pt cục bộ; chuẩn bị model theo README trước khi chạy.")
        # This initialization runs in PipelineWorker, never on the display loop.
        # Pin the library's mutable settings inside this repository by default.
        default_config = Path(__file__).resolve().parents[1] / ".tmp" / "ultralytics"
        config_dir = Path(os.environ.setdefault("YOLO_CONFIG_DIR", str(default_config)))
        if config_dir == default_config:
            config_dir.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_AUTOINSTALL"] = "false"
        os.environ["YOLO_OFFLINE"] = "true"
        # Verify before import/construction so Ultralytics cannot silently download it.
        from ultralytics import YOLO

        if track:
            import lap  # noqa: F401  # ByteTrack cần; YOLO_AUTOINSTALL tắt nên báo thiếu thay vì tải ngầm.

        self._model = YOLO(str(path.resolve()), task="detect")
        self.imgsz, self.conf, self.iou, self.device = imgsz, conf, iou, device
        self.track, self.enhance, self._session = track, enhance, None
        # Model tùy chỉnh không có tên COCO nào khớp thì không lọc lớp.
        names = getattr(self._model, "names", None)
        ids = [i for i, n in names.items() if n in WALKING_CLASSES] if walking_only and isinstance(names, dict) else []
        self._classes = ids or None

    @property
    def class_names(self) -> dict[int, str]:
        """Return the loaded model's actual names, including custom class maps."""
        names = self._model.names
        if isinstance(names, (list, tuple)):
            return {class_id: str(label) for class_id, label in enumerate(names)}
        if not isinstance(names, dict):
            raise ValueError("Model không cung cấp danh sách lớp hợp lệ.")
        normalized = {}
        for raw_id, label in names.items():
            try:
                numeric_id = float(raw_id)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Model có mã lớp không hợp lệ.") from exc
            if not math.isfinite(numeric_id) or numeric_id < 0 or not numeric_id.is_integer():
                raise ValueError("Model có mã lớp không hợp lệ.")
            class_id = int(numeric_id)
            if class_id in normalized:
                raise ValueError("Model có mã lớp trùng sau chuẩn hóa.")
            normalized[class_id] = str(label)
        return normalized

    def predict(self, frame: Frame) -> DetectionResult:
        started_at = time.monotonic()
        options = dict(
            source=enhance_dark(frame.image) if self.enhance else frame.image,
            imgsz=self.imgsz,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            classes=self._classes,
            stream=False,
            verbose=False,
            save=False,
            show=False,
        )
        if self.track:
            # Phiên camera mới thì persist=False để bỏ track của phiên trước.
            options["persist"] = frame.session_id == self._session
            self._session = frame.session_id
            results = self._model.track(tracker="bytetrack.yaml", **options)
        else:
            results = self._model.predict(**options)
        if len(results) != 1:
            raise ValueError("Model không trả đúng một kết quả cho ảnh nguồn.")
        detections = parse_detections(results[0], frame, self.conf, require_track=self.track)
        completed_at = time.monotonic()
        return DetectionResult(frame, detections, (completed_at - started_at) * 1000.0, completed_at)
