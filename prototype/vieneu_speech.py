"""Engine TTS gọi VieNeu Cloud API (tương thích OpenAI /audio/speech).

Cùng giao diện với WindowsSpeechEngine để FeedbackManager dùng thay thế được:
start() không chờ mạng, poll() trả None hoặc 'done' đúng một lần hoặc ném
SpeechError, stop() hủy cả tải âm thanh lẫn phát. Khóa API lấy từ biến môi
trường VIENEU_API_KEY, không bao giờ đưa vào tham số dòng lệnh hay thông báo lỗi.

Lưu ý riêng tư: văn bản mô tả cảnh được gửi tới máy chủ bên thứ ba.
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import wave
from typing import Any, Callable, Protocol

from .speech import MAX_TEXT_LENGTH, SpeechError

DEFAULT_BASE_URL = "https://api.vieneu.io/api/v1"
DEFAULT_VOICE = "Nhật Phong"
API_KEY_ENV = "VIENEU_API_KEY"
MAX_AUDIO_BYTES = 10 * 1024 * 1024

_SND_ASYNC, _SND_MEMORY, _SND_NODEFAULT, _SND_PURGE = 0x1, 0x4, 0x2, 0x40


class Player(Protocol):
    def play(self, wav: bytes) -> None: ...
    def stop(self) -> None: ...


class WinmmPlayer:
    """Phát WAV từ RAM bằng winmm; không ghi tệp tạm."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise SpeechError("Trình phát này cần Windows.")
        self._winmm = ctypes.windll.winmm
        self._buffer: Any = None  # Phải còn sống trong lúc phát bất đồng bộ.

    def play(self, wav: bytes) -> None:
        self._buffer = ctypes.create_string_buffer(wav, len(wav))
        if not self._winmm.PlaySoundW(self._buffer, None, _SND_MEMORY | _SND_ASYNC | _SND_NODEFAULT):
            self._buffer = None
            raise SpeechError("Windows không phát được âm thanh WAV.")

    def stop(self) -> None:
        self._winmm.PlaySoundW(None, None, _SND_PURGE)
        self._buffer = None


class VieNeuSpeechEngine:
    def __init__(self, api_key: str | None = None, voice: str = DEFAULT_VOICE, *,
                 base_url: str = DEFAULT_BASE_URL, model: str = "tts-1", speed: float = 1.0,
                 timeout: float = 30.0, opener: Callable[..., Any] = urllib.request.urlopen,
                 player: Player | None = None) -> None:
        key = api_key or os.environ.get(API_KEY_ENV)
        if not key:
            raise SpeechError(f"Thiếu khóa API: đặt biến môi trường {API_KEY_ENV}.")
        if not base_url.startswith("https://"):
            raise ValueError("base_url phải dùng https.")
        if timeout <= 0 or timeout > 120:
            raise ValueError("timeout phải lớn hơn 0 và không quá 120 giây")
        if not voice.strip():
            raise ValueError("Tên giọng không được rỗng.")
        self._key, self.voice, self.model, self.speed = key, voice, model, speed
        self._base = base_url.rstrip("/")
        self._url = self._base + "/audio/speech"
        self.timeout = timeout
        self._opener = opener
        self._player = player or WinmmPlayer()
        self._lock = threading.Lock()
        self._cache: dict[str, bytes] = {}
        self._generation = 0
        self._phase = "idle"  # idle | fetching | playing
        self._wav: bytes | None = None
        self._error: str | None = None
        self._started_at = 0.0
        self._play_until = 0.0
        self.status = "Chưa dùng giọng VieNeu"
        self.last_result: dict[str, Any] | None = None

    # -- mạng -------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._key, "Authorization": "Bearer " + self._key,
                "Content-Type": "application/json"}

    def _fetch_job_wav(self, text: str, deadline: float) -> bytes:
        req = urllib.request.Request(
            self._base + "/tts", method="POST", headers=self._headers(),
            data=json.dumps({"text": text, "voiceId": self.voice, "format": "wav"}, ensure_ascii=False).encode("utf-8"))
        with self._opener(req, timeout=min(10.0, max(1.0, deadline - time.monotonic()))) as resp:
            job = json.loads(resp.read(65536).decode("utf-8"))
        job_id = job.get("jobId")
        if not job_id:
            raise ValueError("API /v1/tts không trả về jobId.")
        while time.monotonic() < deadline:
            with self._lock:
                if self._phase != "fetching":
                    raise InterruptedError
            poll_req = urllib.request.Request(f"{self._base}/tts/{job_id}", headers=self._headers())
            with self._opener(poll_req, timeout=min(10.0, max(1.0, deadline - time.monotonic()))) as resp:
                data = json.loads(resp.read(65536).decode("utf-8"))
            status = data.get("status")
            if status == "completed":
                audio_url = data.get("audioUrl", "")
                if not str(audio_url).startswith("https://"):
                    raise ValueError("audioUrl không hợp lệ.")
                with self._opener(audio_url, timeout=min(10.0, max(1.0, deadline - time.monotonic()))) as audio_resp:
                    return audio_resp.read(MAX_AUDIO_BYTES + 1)
            if status == "failed":
                raise RuntimeError("Server báo tổng hợp giọng thất bại.")
            time.sleep(0.5)
        raise TimeoutError("Hết thời gian chờ job TTS.")

    def _fetch(self, generation: int, text: str) -> None:
        deadline = time.monotonic() + self.timeout
        payload = {"model": self.model, "input": text, "voice": self.voice,
                   "response_format": "wav", "speed": self.speed}
        request = urllib.request.Request(
            self._url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST", headers=self._headers())
        wav, error = None, None
        try:
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    wav = response.read(MAX_AUDIO_BYTES + 1)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    wav = self._fetch_job_wav(text, deadline)
                else:
                    raise
            if len(wav) > MAX_AUDIO_BYTES:
                wav, error = None, "Âm thanh trả về vượt giới hạn kích thước."
            elif not wav.startswith(b"RIFF"):
                wav, error = None, "API không trả về WAV hợp lệ."
        except InterruptedError:
            return
        except urllib.error.HTTPError as exc:
            exc.close()
            error = {401: "Khóa API không hợp lệ.", 403: "Khóa API không có quyền.",
                     429: "Vượt hạn mức API."}.get(exc.code, f"API trả mã lỗi {exc.code}.")
        except Exception as exc:  # Không đưa thông điệp thô vào lỗi: có thể chứa URL/khóa.
            error = f"Không gọi được API giọng nói ({type(exc).__name__})."
        with self._lock:
            if wav is not None and error is None:
                if len(self._cache) >= 64:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[text] = wav
            if generation != self._generation:
                return  # Đã bị stop() hoặc câu mới; bỏ kết quả muộn.
            self._wav, self._error = wav, error

    def _begin_playback_locked(self, wav: bytes, now: float) -> None:
        with wave.open(io.BytesIO(wav)) as handle:
            duration = handle.getnframes() / float(handle.getframerate())
        self._player.play(wav)
        self._phase, self._play_until = "playing", now + duration + 0.05
        self.status = "Đang đọc bằng VieNeu API"

    # -- giao diện engine -------------------------------------------------
    def start(self, text: str) -> None:
        if not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise SpeechError(f"Câu đọc phải có 1–{MAX_TEXT_LENGTH} ký tự.")
        with self._lock:
            if self._phase != "idle":
                raise SpeechError("Engine đang đọc; FeedbackManager cần dừng hoặc đợi câu hiện tại.")
            self._generation += 1
            generation = self._generation
            self._wav, self._error = None, None
            self._started_at = time.monotonic()
            self.last_result = None
            cached = self._cache.get(text)
            if cached is not None:
                try:
                    self._begin_playback_locked(cached, self._started_at)
                    return
                except (wave.Error, EOFError, ZeroDivisionError, SpeechError) as exc:
                    self._cache.pop(text, None)
                    self._fail_locked(f"Không phát được âm thanh: {exc}")
            self._phase = "fetching"
            self.status = "Đang lấy giọng từ VieNeu API"
        threading.Thread(target=self._fetch, args=(generation, text), name="vieneu-tts", daemon=True).start()

    def poll(self) -> str | None:
        with self._lock:
            phase = self._phase
            if phase == "idle":
                return None
            now = time.monotonic()
            if phase == "fetching":
                if self._error:
                    return self._fail_locked(self._error)
                if self._wav is None:
                    if now - self._started_at > self.timeout + 1.0:
                        return self._fail_locked("Hết thời gian chờ API giọng nói.")
                    return None
                wav, self._wav = self._wav, None
                try:
                    self._begin_playback_locked(wav, now)
                except (wave.Error, EOFError, ZeroDivisionError, SpeechError) as exc:
                    return self._fail_locked(f"Không phát được âm thanh: {exc}")
                return None
            if now < self._play_until:
                return None
            self._phase = "idle"
            self.last_result = {"ok": True, "backend": "vieneu", "voice": self.voice,
                                "playbackCompleted": True, "heardConfirmed": None}
            self.status = f"Đã phát xong: {self.voice} (chưa xác nhận nghe)"
            return "done"

    def _fail_locked(self, message: str) -> None:
        self._generation += 1
        self._phase, self._wav, self._error = "idle", None, None
        self._player.stop()
        self.status = "Lỗi âm thanh: " + message
        raise SpeechError(message)

    def stop(self) -> None:
        with self._lock:
            self._generation += 1  # Vô hiệu hóa tải đang chạy.
            self._phase, self._wav, self._error = "idle", None, None
            self._player.stop()
            self.status = "Âm thanh đã dừng"

    def close(self) -> None:
        self.stop()
