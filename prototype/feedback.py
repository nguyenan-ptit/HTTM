"""Một worker sở hữu TTS; API giao diện không chờ thao tác của engine."""

from collections import OrderedDict
from dataclasses import dataclass
import math
import threading
import time
from typing import Callable, Protocol

from .types import Narration


def _labels(groups) -> set[str]:
    """'người:left' → 'người'; nhóm không có vị trí giữ nguyên."""
    return {group.rsplit(":", 1)[0] for group in groups}


class SpeechEngine(Protocol):
    def start(self, text: str) -> None: ...
    def poll(self) -> str | None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class FeedbackSnapshot:
    enabled: bool
    status: str
    speaking_text: str
    pending_count: int
    error: str | None
    utterances_started: int = 0
    utterances_completed: int = 0
    utterances_cancelled: int = 0
    last_event: str = ""
    evidence_captured_at: float | None = None
    evidence_frame_id: int | None = None


class FeedbackManager:
    def __init__(self, engine: SpeechEngine, *, enabled: bool = True,
                 repeat_interval: float = 6.0, clock: Callable[[], float] = time.monotonic,
                 autostart: bool = True):
        if not math.isfinite(repeat_interval) or repeat_interval < 0:
            raise ValueError("Khoảng chống đọc lặp phải không âm.")
        self._engine = engine
        self._clock = clock
        self._repeat_interval = repeat_interval
        self._condition = threading.Condition(threading.RLock())
        # Only the worker executes engine IO. This also protects deterministic
        # _step calls from accidentally running alongside a worker or each other.
        self._io_lock = threading.Lock()
        self._enabled = enabled
        self._session: str | None = None
        self._healthy = False
        self._pending: Narration | None = None
        self._active: Narration | None = None
        # The text/source originally dispatched to the engine stays immutable.
        # Fresh detections may separately confirm that its claims still apply.
        self._active_evidence: Narration | None = None
        self._active_epoch: int | None = None
        self._active_started = False
        self._epoch = 0
        self._cancel = False
        self._cancel_reason = ""
        self._utterances_started = 0
        self._utterances_completed = 0
        self._utterances_cancelled = 0
        self._last_event = ""
        self._engine_uncertain = False
        self._closed = False
        self._error: str | None = None
        self._status = "Sẵn sàng" if enabled else "Đã tắt tiếng"
        self._last_frame = -1
        self._completed: OrderedDict[str, float] = OrderedDict()
        self._thread: threading.Thread | None = None
        if autostart:
            self._thread = threading.Thread(target=self._run, name="feedback", daemon=True)
            self._thread.start()

    def _cancel_locked(self, reason: str) -> None:
        self._epoch += 1
        self._cancel = True
        self._cancel_reason = reason
        self._last_event = "cancel_requested:" + reason if self._active else reason
        if self._active:
            self._status = "Đang dừng"

    def set_context(self, session_id: str | None, healthy: bool) -> None:
        with self._condition:
            changed = session_id != self._session
            if changed:
                self._last_frame = -1
                self._completed.clear()
            if changed or (self._healthy and not healthy):
                self._pending = None
                self._cancel_locked("session_changed" if changed else "camera_or_model_unavailable")
            self._session = session_id
            self._healthy = healthy
            self._condition.notify_all()

    def set_enabled(self, enabled: bool) -> None:
        with self._condition:
            if enabled != self._enabled:
                self._pending = None
                self._cancel_locked("unmuted" if enabled else "muted")
                self._completed.clear()
                # A failed stop must be resolved before another start is allowed.
                if not self._engine_uncertain:
                    self._error = None
                self._enabled = enabled
                if enabled:
                    # A user-requested unmute may replay the current frame,
                    # provided it still passes source-age/session validation.
                    self._last_frame = -1
                if not self._active:
                    self._status = "Sẵn sàng" if enabled else "Đã tắt tiếng"
            self._condition.notify_all()

    def submit(self, narration: Narration | None) -> bool:
        with self._condition:
            if self._closed:
                return False
            if narration is None:
                if self._pending or self._active:
                    self._cancel_locked("no_detection")
                self._pending = None
                self._condition.notify_all()
                return False
            now = self._clock()
            if not self._valid(narration, now) or narration.frame_id <= self._last_frame:
                return False
            self._last_frame = narration.frame_id
            if self._active and not self._cancel and self._active_epoch == self._epoch:
                evidence = self._active_evidence
                if evidence is None or not self._valid(evidence, now):
                    # A new frame can start a new utterance, but cannot revive
                    # an utterance whose last supporting evidence has expired.
                    self._cancel_locked("ttl")
                elif not self._active.groups or not _labels(self._active.groups).issubset(_labels(narration.groups)):
                    # Chỉ hủy khi một vật đang được đọc biến mất; vật chỉ đổi vị trí thì đọc tiếp
                    # (hủy liên tục làm không câu nào nghe trọn).
                    self._cancel_locked("scene_changed")
                elif (narration.session_id == self._active.session_id and
                      narration.frame_id > evidence.frame_id and
                      narration.source_captured_at > evidence.source_captured_at):
                    self._active_evidence = narration
            self._pending = narration
            self._condition.notify_all()
            return True

    def _valid(self, item: Narration, now: float) -> bool:
        return (self._enabled and self._healthy and not self._closed and
                item.session_id == self._session and bool(item.text.strip()) and
                all(math.isfinite(t) for t in (item.source_captured_at, item.expires_at, now)) and
                item.source_captured_at <= now < item.expires_at)

    def snapshot(self) -> FeedbackSnapshot:
        with self._condition:
            evidence = self._active_evidence
            return FeedbackSnapshot(self._enabled, self._status,
                                    self._active.text if self._active else "",
                                    int(self._pending is not None), self._error,
                                    self._utterances_started, self._utterances_completed,
                                    self._utterances_cancelled, self._last_event,
                                    evidence.source_captured_at if evidence else None,
                                    evidence.frame_id if evidence else None)

    def _active_valid_locked(self, item: Narration, epoch: int, now: float) -> bool:
        return (self._active is item and self._active_epoch == epoch == self._epoch and
                not self._cancel and self._active_evidence is not None and
                self._valid(self._active_evidence, now))

    def _clear_active_locked(self, *, cancelled: bool = False, reason: str = "") -> None:
        if cancelled and self._active_started:
            self._utterances_cancelled += 1
            self._last_event = "cancelled:" + reason
        self._active = None
        self._active_evidence = None
        self._active_epoch = None
        self._active_started = False

    def _refresh_status_locked(self) -> None:
        if self._error:
            self._status = "Lỗi âm thanh: " + self._error
        elif self._closed:
            self._status = "Âm thanh đã dừng"
        elif self._cancel and self._active:
            self._status = "Đang dừng"
        elif not self._enabled:
            self._status = "Đã tắt tiếng"
        elif self._active:
            self._status = "Đang đọc tiếng Việt"
        elif not self._healthy:
            self._status = "Chờ dữ liệu còn mới"
        else:
            self._status = "Sẵn sàng"

    def _stop_engine(self) -> bool:
        """Called only with _io_lock, never with the UI/state lock held."""
        with self._condition:
            epoch = self._epoch
            was_uncertain = self._engine_uncertain
            reason = self._cancel_reason
            self._status = "Đang dừng"
        try:
            self._engine.stop()
        except Exception as exc:
            with self._condition:
                self._engine_uncertain = True
                self._cancel = True
                self._pending = None
                self._error = "Chưa xác nhận engine đã dừng: " + str(exc)
                self._last_event = "stop_failed:" + reason
                self._refresh_status_locked()
            return False
        with self._condition:
            self._clear_active_locked(cancelled=True, reason=reason)
            self._engine_uncertain = False
            if was_uncertain:
                self._error = None
            # A newer public cancellation arriving during stop remains pending.
            if self._epoch == epoch:
                self._cancel = False
            self._refresh_status_locked()
        return True

    def _engine_failed(self, exc: Exception) -> None:
        with self._condition:
            self._error = str(exc)
            self._pending = None
            self._cancel_locked("engine_error")
        self._stop_engine()

    def _step(self) -> None:
        """One engine-owner step; also usable with a fake clock/engine in tests."""
        if not self._io_lock.acquire(blocking=False):
            return
        try:
            with self._condition:
                now = self._clock()
                if self._active and not self._cancel and not self._active_valid_locked(self._active, self._epoch, now):
                    self._cancel_locked("ttl")
                must_stop = self._cancel or self._engine_uncertain
            if must_stop and not self._stop_engine():
                return

            with self._condition:
                active = self._active
                active_epoch = self._active_epoch
                should_poll = active is not None and not self._cancel
            if should_poll:
                try:
                    finished = self._engine.poll() == "done"
                except Exception as exc:
                    self._engine_failed(exc)
                    return
                with self._condition:
                    if finished and self._active is active:
                        now = self._clock()
                        if self._active_valid_locked(active, active_epoch, now):
                            self._completed[active.dedup_key] = now
                            self._completed.move_to_end(active.dedup_key)
                            while len(self._completed) > 64:
                                self._completed.popitem(last=False)
                            self._utterances_completed += 1
                            self._last_event = "completed"
                            self._clear_active_locked()
                        else:
                            if not self._cancel:
                                self._cancel_locked("ttl")
                            self._clear_active_locked(cancelled=True, reason=self._cancel_reason)

            with self._condition:
                now = self._clock()
                if self._pending and not self._valid(self._pending, now):
                    self._pending = None
                if (self._active or self._cancel or self._engine_uncertain or
                        self._error or self._closed or self._pending is None):
                    self._refresh_status_locked()
                    return
                item, self._pending = self._pending, None
                if now - self._completed.get(item.dedup_key, -math.inf) < self._repeat_interval:
                    self._refresh_status_locked()
                    return
                # Reserve the item before IO: concurrent scene/context changes
                # can invalidate an engine.start that has not yet returned.
                epoch = self._epoch
                self._active, self._active_epoch = item, epoch
                self._active_evidence = item
                self._active_started = False
                self._status = "Đang chuẩn bị giọng tiếng Việt"

            # Check directly before IO and again afterwards. Cancellation can
            # arrive while the underlying OS process/API is being started.
            with self._condition:
                valid = self._active_valid_locked(item, epoch, self._clock())
                if not valid:
                    if not self._cancel:
                        self._cancel_locked("ttl")
                    self._clear_active_locked()
                    self._refresh_status_locked()
                    return
            try:
                self._engine.start(item.text)
            except Exception as exc:
                self._engine_failed(exc)
                return
            with self._condition:
                self._utterances_started += 1
                self._active_started = True
                valid = self._active_valid_locked(item, epoch, self._clock())
                if valid:
                    self._last_event = "started"
                elif not self._cancel:
                    self._cancel_locked("ttl")
                self._refresh_status_locked()
            if not valid:
                self._stop_engine()
        finally:
            self._io_lock.release()

    def _close_engine(self) -> None:
        with self._io_lock:
            try:
                self._engine.close()
            except Exception as exc:
                with self._condition:
                    self._error = "Không đóng được engine: " + str(exc)
            finally:
                with self._condition:
                    self._clear_active_locked(cancelled=True, reason=self._cancel_reason or "closed")
                    self._pending = None
                    self._refresh_status_locked()

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    if self._closed:
                        break
                self._step()
                with self._condition:
                    if not self._closed:
                        self._condition.wait(timeout=0.03)
        finally:
            self._close_engine()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._healthy = False
            self._pending = None
            self._cancel_locked("closed")
            self._condition.notify_all()
        if self._thread:
            self._thread.join(timeout=3)
        else:
            self._step()
            self._close_engine()
