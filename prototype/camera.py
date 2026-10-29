"""One camera owner, latest-frame storage, and conservative liveness checks.

``captured_at`` is the monotonic time immediately after OpenCV returns a frame,
not the time the phone exposed its sensor. Consumers must treat frame.image as
read-only. Exact duplicate detection cannot distinguish a frozen stream from a
perfectly static scene; it deliberately suppresses narration in either case.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import math
import threading
import time
from typing import Any, Callable
import uuid

from .types import Frame


@dataclass(frozen=True)
class CameraSnapshot:
    frame: Frame | None
    status: str
    session_id: str | None
    fps: float
    healthy: bool


def transform_image(image: Any, rotation: int, mirror: bool, cv: Any = None) -> Any:
    """Rotate clockwise, then mirror the displayed/detected source once."""
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Góc xoay phải là 0, 90, 180 hoặc 270 độ.")
    if rotation or mirror:
        if cv is None:
            import cv2 as cv
        if rotation:
            constants = {
                90: cv.ROTATE_90_CLOCKWISE,
                180: cv.ROTATE_180,
                270: cv.ROTATE_90_COUNTERCLOCKWISE,
            }
            image = cv.rotate(image, constants[rotation])
        if mirror:
            image = cv.flip(image, 1)
    # Some capture backends reuse their buffer on the next read.
    return image.copy()


class CameraWorker:
    def __init__(
        self,
        source: int | str,
        backend: str = "auto",
        width: int = 640,
        height: int = 480,
        rotation: int = 0,
        mirror: bool = False,
        stale_after: float = 2.0,
        freeze_after: float = 5.0,
        *,
        capture_factory: Callable[[int | str, str, int, int], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        retry_delay: float = 1.0,
    ) -> None:
        if isinstance(source, bool) or not isinstance(source, (int, str)):
            raise ValueError("Nguồn camera phải là số thiết bị hoặc URL đã kiểm tra.")
        if (isinstance(source, int) and source < 0) or (isinstance(source, str) and not source.strip()):
            raise ValueError("Nguồn camera không hợp lệ.")
        if backend not in ("auto", "dshow", "msmf"):
            raise ValueError("Backend camera phải là auto, dshow hoặc msmf.")
        if width <= 0 or height <= 0 or rotation not in (0, 90, 180, 270):
            raise ValueError("Độ phân giải hoặc góc xoay camera không hợp lệ.")
        if not math.isfinite(stale_after) or stale_after <= 0:
            raise ValueError("Thời hạn ảnh phải lớn hơn 0.")
        if not math.isfinite(freeze_after) or freeze_after < 0:
            raise ValueError("Thời gian phát hiện ảnh đứng phải không âm.")
        if not math.isfinite(retry_delay) or retry_delay <= 0:
            raise ValueError("Thời gian thử kết nối lại phải lớn hơn 0.")
        self.source, self.backend = source, backend
        self.width, self.height = width, height
        self.rotation, self.mirror = rotation, mirror
        self.stale_after, self.freeze_after = stale_after, freeze_after
        self._factory = capture_factory or self._open_capture
        self._clock, self._retry_delay = clock, retry_delay
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None
        self._frame: Frame | None = None
        self._session_id: str | None = None
        self._status = "Camera chưa khởi động."
        self._samples: deque[float] = deque(maxlen=240)
        self._fingerprint: bytes | None = None
        self._changed_at: float | None = None

    @staticmethod
    def _open_capture(source: int | str, backend: str, width: int, height: int) -> Any:
        import cv2

        api = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}[backend]
        # Never put the source or backend exception in our application status/log.
        capture = cv2.VideoCapture(source, api)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    def start(self) -> None:
        if self._thread is not None:
            return
        self._status = "Đang mở camera…"
        self._started_at = self._clock()
        # A driver may block forever in open/read. It must not trap application exit.
        self._thread = threading.Thread(target=self._run, name="camera-owner", daemon=True)
        self._thread.start()

    def _invalidate(self, status: str) -> None:
        with self._lock:
            self._frame = None
            self._session_id = None
            self._samples.clear()
            self._status = status

    def _run(self) -> None:
        while not self._stop.is_set():
            capture = None
            try:
                capture = self._factory(self.source, self.backend, self.width, self.height)
                if not capture.isOpened():
                    self._invalidate("Không mở được camera; đang thử kết nối lại.")
                else:
                    session_id = uuid.uuid4().hex
                    frame_id = 0
                    while not self._stop.is_set():
                        ok, image = capture.read()
                        received_at = self._clock()
                        if self._stop.is_set():
                            break
                        if not ok or image is None or not getattr(image, "size", 0):
                            self._invalidate("Mất dữ liệu camera; đang thử kết nối lại.")
                            break
                        image = transform_image(image, self.rotation, self.mirror)
                        if self.freeze_after:
                            fingerprint = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
                            if fingerprint != self._fingerprint:
                                self._fingerprint = fingerprint
                                self._changed_at = received_at
                            elif self._changed_at is not None and received_at - self._changed_at >= self.freeze_after:
                                self._invalidate("Ảnh camera không thay đổi; tạm dừng mô tả và đang kết nối lại.")
                                break
                        frame_id += 1
                        frame = Frame(session_id, frame_id, received_at, image)
                        with self._lock:
                            self._frame, self._session_id = frame, session_id
                            self._status = "Camera đang nhận hình."
                            self._samples.append(received_at)
                            while self._samples and received_at - self._samples[0] > 2.0:
                                self._samples.popleft()
            except ImportError:
                self._invalidate("Thiếu OpenCV; hãy cài thư viện theo README.")
                return
            except Exception:
                # URLs can include passwords. Do not expose exception text.
                self._invalidate("Lỗi đọc camera; kiểm tra client, quyền và nguồn camera.")
            finally:
                if capture is not None:
                    try:
                        capture.release()
                    except Exception:
                        pass
            if not self._stop.is_set():
                self._stop.wait(self._retry_delay)
        self._invalidate("Camera đã dừng.")

    def snapshot(self) -> CameraSnapshot:
        now = self._clock()
        with self._lock:
            frame, status, session_id = self._frame, self._status, self._session_id
            samples = tuple(self._samples)
        if self._stop.is_set():
            return CameraSnapshot(None, "Camera đã dừng.", None, 0.0, False)
        if frame is None:
            if status == "Đang mở camera…" and self._started_at is not None and now - self._started_at > self.stale_after:
                status = "Chưa nhận được ảnh camera; kiểm tra nguồn và kết nối."
            return CameraSnapshot(None, status, session_id, 0.0, False)
        age = now - frame.captured_at
        if age < 0 or age > self.stale_after:
            return CameraSnapshot(None, "Không có ảnh camera mới; đã tạm dừng mô tả.", None, 0.0, False)
        elapsed = samples[-1] - samples[0] if len(samples) > 1 else 0.0
        fps = (len(samples) - 1) / elapsed if elapsed > 0 else 0.0
        return CameraSnapshot(frame, status, session_id, fps, True)

    def close(self) -> None:
        self._stop.set()
        self._invalidate("Camera đã dừng.")
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.3)
