"""Latest-only inference, with session and source-age checks on both boundaries."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import threading
import time
from typing import Any, Callable

from .types import DetectionResult


@dataclass(frozen=True)
class PipelineSnapshot:
    result: DetectionResult | None
    status: str
    fps: float


class PipelineWorker:
    def __init__(
        self,
        camera: Any,
        detector_factory: Callable[[], Any],
        max_age: float = 2.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError("Thời hạn kết quả nhận diện phải lớn hơn 0.")
        self.camera, self.detector_factory, self.max_age = camera, detector_factory, max_age
        self._clock = clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._result: DetectionResult | None = None
        self._status = "Model chưa khởi động."
        self._samples: deque[float] = deque(maxlen=240)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._status = "Đang nạp model…"
        self._thread = threading.Thread(target=self._run, name="yolo-worker", daemon=True)
        self._thread.start()

    def _publish(self, result: DetectionResult | None, status: str) -> None:
        with self._lock:
            self._result, self._status = result, status
            if result is None:
                self._samples.clear()

    def _run(self) -> None:
        try:
            detector = self.detector_factory()
        except FileNotFoundError:
            self._publish(None, "Chưa có model .pt cục bộ; xem hướng dẫn chuẩn bị model.")
            return
        except ImportError:
            self._publish(None, "Thiếu thư viện YOLO; hãy cài dependency theo README.")
            return
        except Exception:
            self._publish(None, "Không nạp được model; kiểm tra tệp và cấu hình.")
            return
        last_key = None
        while not self._stop.is_set():
            camera_state = self.camera.snapshot()
            frame = camera_state.frame
            if not camera_state.healthy or frame is None:
                self._publish(None, "Đang chờ ảnh camera mới.")
                self._stop.wait(0.01)
                continue
            key = (frame.session_id, frame.frame_id)
            age = self._clock() - frame.captured_at
            if age < 0 or age > self.max_age:
                self._publish(None, "Ảnh nguồn đã cũ; bỏ qua nhận diện.")
                self._stop.wait(0.01)
                continue
            if key == last_key:
                self._stop.wait(0.005)
                continue
            last_key = key
            try:
                result = detector.predict(frame)
                if result.error:
                    self._publish(None, "Model báo lỗi khi nhận diện; đã tạm dừng mô tả.")
                    return
                if (result.frame.session_id, result.frame.frame_id) != key:
                    self._publish(None, "Kết quả model không khớp ảnh nguồn; đã tạm dừng mô tả.")
                    return
            except Exception:
                self._publish(None, "Lỗi model khi nhận diện; đã tạm dừng mô tả.")
                return
            if self._stop.is_set():
                break
            camera_after = self.camera.snapshot()
            age_after = self._clock() - frame.captured_at
            if not camera_after.healthy or camera_after.session_id != frame.session_id:
                self._publish(None, "Đã bỏ kết quả của camera mất kết nối hoặc phiên cũ.")
                continue
            if age_after < 0 or age_after > self.max_age:
                self._publish(None, "Nhận diện hoàn tất nhưng ảnh nguồn đã cũ.")
                continue
            now = self._clock()
            with self._lock:
                self._result, self._status = result, "YOLO đang nhận diện."
                self._samples.append(now)
                while self._samples and now - self._samples[0] > 2.0:
                    self._samples.popleft()

    def snapshot(self) -> PipelineSnapshot:
        with self._lock:
            result, status, samples = self._result, self._status, tuple(self._samples)
        if self._stop.is_set():
            return PipelineSnapshot(None, "Nhận diện đã dừng.", 0.0)
        if result is not None:
            camera_state = self.camera.snapshot()
            age = self._clock() - result.frame.captured_at
            if not camera_state.healthy or camera_state.session_id != result.frame.session_id:
                return PipelineSnapshot(None, "Không có kết quả thuộc phiên camera hiện tại.", 0.0)
            if age < 0 or age > self.max_age:
                return PipelineSnapshot(None, "Kết quả nhận diện đã cũ; tạm dừng mô tả.", 0.0)
        span = samples[-1] - samples[0] if len(samples) > 1 else 0.0
        fps = (len(samples) - 1) / span if span > 0 else 0.0
        if samples and self._clock() - samples[-1] > 2.0:
            fps = 0.0
        return PipelineSnapshot(result, status, fps)

    def close(self) -> None:
        self._stop.set()
        self._publish(None, "Nhận diện đã dừng.")
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.3)
