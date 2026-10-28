"""Hợp đồng dữ liệu; mọi timestamp dùng time.monotonic()."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Frame:
    session_id: str
    frame_id: int
    captured_at: float  # Ngay sau OpenCV.read(), không phải lúc điện thoại thu ảnh.
    image: Any  # Mảng BGR, chỉ đọc sau khi được công bố.

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


@dataclass(frozen=True)
class Detection:
    class_id: int
    label: str
    score: float
    bbox: tuple[float, float, float, float]
    track_id: int | None = None  # Chỉ có khi tracker đã xác nhận đối tượng qua nhiều ảnh.


@dataclass(frozen=True)
class DetectionResult:
    frame: Frame
    detections: tuple[Detection, ...]
    inference_ms: float
    completed_at: float
    error: str | None = None


@dataclass(frozen=True)
class Narration:
    text: str
    groups: tuple[str, ...]
    session_id: str
    frame_id: int
    source_captured_at: float
    expires_at: float

    @property
    def dedup_key(self) -> str:
        return "|".join(self.groups)
