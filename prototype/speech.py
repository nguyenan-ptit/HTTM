"""Giọng tiếng Việt cục bộ của Windows; mọi âm thanh nằm trong tiến trình con.

FeedbackManager là nơi gọi engine này. Worker chỉ sống cho một câu, vì vậy
stop() có thể hủy cả tổng hợp và phát âm thanh mà không có callback muộn.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, BinaryIO

BACKENDS = ("auto", "winrt", "sapi", "onecore")
SAMPLE_TEXT = "Có người ở bên trái. Có ô tô ở giữa ảnh. Có biển báo dừng ở bên phải."
MAX_TEXT_LENGTH = 400


class SpeechError(RuntimeError):
    """Lỗi có thể hiển thị mà không làm dừng video hoặc câu mô tả."""


def is_vietnamese_language(language: str) -> bool:
    """Chấp nhận mã ngôn ngữ, không suy từ tên giọng như 'Microsoft An'."""
    return language.strip().lower().replace("_", "-") in {"vi", "vi-vn"}


def _command() -> list[str]:
    if os.name != "nt":
        raise SpeechError("TTS này cần Windows; video và text vẫn có thể chạy khi tắt tiếng.")
    # Windows PowerShell/.NET Framework supports the WinRT projection. Prefer
    # its absolute system path over pwsh (which has a different .NET runtime).
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    executable = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    executable_name = str(executable) if executable.is_file() else shutil.which("powershell.exe")
    if not executable_name:
        raise SpeechError("Không tìm thấy Windows PowerShell để truy cập giọng tiếng Việt.")
    return [executable_name, "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
            "-ExecutionPolicy", "Bypass", "-File", str(Path(__file__).with_name("windows_speech.ps1"))]


def _decode_result(stdout: bytes, stderr: bytes, returncode: int) -> dict[str, Any]:
    try:
        result = json.loads(stdout.decode("utf-8-sig"))
        if not isinstance(result, dict):
            raise ValueError("JSON phải là object")
    except (ValueError, UnicodeDecodeError) as exc:
        detail = stderr.decode("utf-8", errors="replace").strip()[:1200]
        raise SpeechError(f"Worker giọng không trả JSON hợp lệ (mã {returncode}). {detail}") from exc
    if not result.get("ok") or returncode:
        errors = result.get("errors") or [result.get("error") or "Không có giọng tiếng Việt khả dụng."]
        descriptions = []
        for error in errors:
            if isinstance(error, dict):
                codes = ", ".join(str(code) for code in error.get("hresults", []))
                suffix = f" [{codes}]" if codes else ""
                descriptions.append(f"{error.get('backend', 'worker')}: {error.get('message', error)}{suffix}")
            else:
                descriptions.append(str(error))
        raise SpeechError("Không đọc được tiếng Việt. " + " | ".join(descriptions))
    return result


def list_voices(*, backend: str = "auto", voice_id: str | None = None,
                timeout: float = 45.0) -> dict[str, Any]:
    """Liệt kê + thử tổng hợp vào RAM; tuyệt đối không mở đầu ra âm thanh.

    vietnameseInstalled, apiAccessible, synthesisSucceeded và
    playbackCompleted là các kết quả khác nhau. heardConfirmed luôn None:
    chương trình không thể tự xác nhận rằng một người đã nghe được.
    """
    if backend not in BACKENDS:
        raise ValueError(f"Backend không hợp lệ: {backend}")
    payload = {"action": "probe", "backend": backend, "voiceId": voice_id,
               "text": "Có người ở bên trái.", "timeoutMs": 10000}
    try:
        completed = subprocess.run(_command(), input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    except subprocess.TimeoutExpired as exc:
        raise SpeechError("Hết thời gian kiểm tra API giọng; chưa kết luận thiếu giọng tiếng Việt.") from exc
    except OSError as exc:
        raise SpeechError(f"Không mở được worker giọng: {exc}") from exc
    return _decode_result(completed.stdout, completed.stderr, completed.returncode)


class WindowsSpeechEngine:
    """Một câu mỗi lần; start/poll/stop không chờ tổng hợp hoặc phát hết câu.

    poll() trả None khi đang chạy/idle, 'done' đúng một lần sau khi hoàn tất,
    hoặc ném SpeechError. Không có hàng đợi trong engine.
    """

    def __init__(self, backend: str = "auto", voice_id: str | None = None,
                 timeout: float = 30.0) -> None:
        if backend not in BACKENDS:
            raise ValueError(f"Backend không hợp lệ: {backend}")
        if timeout <= 0 or timeout > 120:
            raise ValueError("timeout phải lớn hơn 0 và không quá 120 giây")
        self.backend = backend
        self.voice_id = voice_id
        self.timeout = timeout
        self.status = "Chưa kiểm tra giọng tiếng Việt"
        self.last_result: dict[str, Any] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout: BinaryIO | None = None
        self._stderr: BinaryIO | None = None
        self._started_at = 0.0

    def start(self, text: str) -> None:
        if not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise SpeechError(f"Câu đọc phải có 1–{MAX_TEXT_LENGTH} ký tự.")
        if self._process is not None:
            raise SpeechError("Engine đang đọc; FeedbackManager cần dừng hoặc đợi câu hiện tại.")
        payload = {"action": "speak", "backend": self.backend, "voiceId": self.voice_id,
                   "text": text, "timeoutMs": min(20000, int(self.timeout * 1000))}
        try:
            command = _command()
            # TemporaryFile avoids stdout/stderr pipe backpressure. No camera
            # image, text or audio is persisted in named application files.
            self._stdout = tempfile.TemporaryFile()
            self._stderr = tempfile.TemporaryFile()
            self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=self._stdout,
                                             stderr=self._stderr,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert self._process.stdin is not None
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            self._process.stdin.close()
            self._started_at = time.monotonic()
            self.last_result = None
            self.status = "Đang chuẩn bị/đọc bằng giọng tiếng Việt"
        except (OSError, SpeechError) as exc:
            self.stop()
            self.status = f"Lỗi âm thanh: {exc}"
            if isinstance(exc, SpeechError):
                raise
            raise SpeechError(self.status) from exc

    def poll(self) -> str | None:
        process = self._process
        if process is None:
            return None
        returncode = process.poll()
        if returncode is None:
            if time.monotonic() - self._started_at > self.timeout:
                self.stop()
                self.status = "Lỗi âm thanh: hết thời gian tổng hợp/phát"
                raise SpeechError(self.status)
            return None
        assert self._stdout is not None and self._stderr is not None
        self._stdout.seek(0)
        self._stderr.seek(0)
        stdout, stderr = self._stdout.read(), self._stderr.read()
        self._process = None
        self._close_files()
        try:
            self.last_result = _decode_result(stdout, stderr, returncode)
        except SpeechError as exc:
            self.status = f"Lỗi âm thanh: {exc}"
            raise
        selected = self.last_result.get("selectedVoice") or {}
        self.status = f"Đã phát xong: {selected.get('name', 'giọng tiếng Việt')} (chưa xác nhận nghe)"
        return "done"

    def _close_files(self) -> None:
        for stream in (self._stdout, self._stderr):
            if stream is not None:
                stream.close()
        self._stdout = self._stderr = None

    def stop(self) -> None:
        process = self._process
        if process is not None:
            # SoundPlayer and SAPI both belong to this worker process, with no
            # detached player, so terminating it also releases playback.
            if process.poll() is None:
                try:
                    process.kill()
                except OSError as exc:
                    # It may have finished between poll() and kill(). Any
                    # other failure retains the handle and forbids start().
                    if process.poll() is None:
                        self.status = f"Lỗi âm thanh: không hủy được worker: {exc}"
                        raise SpeechError(self.status) from exc
            try:
                process.wait(timeout=1.0)
            except (subprocess.TimeoutExpired, OSError) as exc:
                self.status = "Lỗi âm thanh: chưa xác nhận worker đã dừng"
                # Keep ownership so a subsequent close() can retry instead of
                # forgetting a worker whose termination is not confirmed.
                raise SpeechError(self.status) from exc
        self._process = None
        self._close_files()
        self.status = "Âm thanh đã dừng"

    def close(self) -> None:
        self.stop()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Kiểm tra giọng tiếng Việt cục bộ trên Windows.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list-voices", action="store_true", help="Liệt kê và tổng hợp RAM; không phát loa.")
    action.add_argument("--test", action="store_true", help="Phát câu mẫu tiếng Việt qua loa/tai nghe máy tính.")
    parser.add_argument("--backend", choices=BACKENDS, default="auto")
    parser.add_argument("--voice-id", help="ID chính xác từ --list-voices, chỉ nhận giọng vi/vi-VN.")
    args = parser.parse_args(argv)
    try:
        if args.list_voices:
            result = list_voices(backend=args.backend, voice_id=args.voice_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        # The diagnostic sample also goes through the single audio owner.
        # Local imports keep voice inventory independent of the camera stack.
        from .feedback import FeedbackManager
        from .types import Narration

        engine = WindowsSpeechEngine(args.backend, args.voice_id, timeout=30.0)
        manager = FeedbackManager(engine)
        try:
            created_at = time.monotonic()
            deadline = created_at + 30.0
            manager.set_context("speech-test", healthy=True)
            sample = Narration(text=SAMPLE_TEXT, groups=("speech-test",),
                               session_id="speech-test", frame_id=0,
                               source_captured_at=created_at, expires_at=deadline)
            print("Đang phát câu mẫu kiểm tra giọng; đây không phải kết quả nhận diện camera.")
            if not manager.submit(sample):
                raise SpeechError("Không gửi được câu mẫu tới bộ quản lý âm thanh.")
            while True:
                snapshot = manager.snapshot()
                if snapshot.error:
                    raise SpeechError(snapshot.error)
                if engine.last_result is not None:
                    break
                if time.monotonic() >= deadline:
                    raise SpeechError("Hết thời gian phát câu mẫu tiếng Việt.")
                time.sleep(0.05)
            print(json.dumps(engine.last_result, ensure_ascii=False, indent=2))
            print("Hãy xác nhận bằng nghe thực tế; playbackCompleted không chứng minh đã nghe thành công.")
        finally:
            manager.close()
        return 0
    except (SpeechError, KeyboardInterrupt) as exc:
        print(f"Lỗi âm thanh: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
