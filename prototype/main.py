"""CLI và vòng hiển thị; camera, inference và TTS chạy ở worker riêng."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

from .narration import narrate
from .types import Frame, Detection, Narration


def source_value(value: str) -> int | str:
    return int(value) if value.isdecimal() else value


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Giá trị phải hữu hạn và lớn hơn 0.")
    return number


def probability(value):
    number = positive_float(value)
    if number > 1:
        raise argparse.ArgumentTypeError("Giá trị phải thuộc (0, 1].")
    return number


def resolve_device(device):
    if device != "auto":
        return device
    import torch
    return "0" if torch.cuda.is_available() else "cpu"


def build_parser():
    parser = argparse.ArgumentParser(description="Camera DroidCam → YOLO → mô tả và giọng tiếng Việt.")
    parser.add_argument("--source", required=True, type=source_value,
                        help="Số nguồn OpenCV thực tế, hoặc tệp/URL video đã kiểm tra")
    parser.add_argument("--no-detect", action="store_true", help="Chỉ xem camera, không nạp model hoặc phát giọng")
    parser.add_argument("--mute", action="store_true", help="Khởi động với âm thanh tắt")
    parser.add_argument("--model", default="yolo11s.pt", help="Tệp model .pt cục bộ")
    parser.add_argument("--imgsz", type=int, default=640, help="Kích thước inference, bội số dương của 32")
    parser.add_argument("--conf", type=probability, default=0.30,
                        help="Ngưỡng confidence; tracker lọc báo nhầm một ảnh nên có thể thấp")
    parser.add_argument("--iou", type=probability, default=0.45, help="Ngưỡng IoU cho NMS trong Ultralytics")
    parser.add_argument("--device", default="auto", help="Thiết bị Ultralytics; auto = GPU CUDA nếu có, không thì cpu")
    parser.add_argument("--no-track", action="store_true", help="Tắt theo dõi đối tượng (mất lọc nhấp nháy đa ảnh)")
    parser.add_argument("--walking-only", action="store_true", help="Chỉ giữ lớp COCO liên quan người đi bộ (ít báo nhầm nhưng bỏ sót đồ vật trong nhà)")
    parser.add_argument("--no-enhance", action="store_true", help="Tắt cân bằng sáng tự động khi ảnh tối")
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf"), default="auto", help="Backend camera OpenCV")
    parser.add_argument("--width", type=int, default=1280, help="Chiều rộng camera yêu cầu; driver có thể chọn khác")
    parser.add_argument("--height", type=int, default=720, help="Chiều cao camera yêu cầu")
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), default=0, help="Xoay ảnh trước nhận diện")
    parser.add_argument("--mirror", action="store_true", help="Lật ngang ảnh trước nhận diện và mô tả")
    parser.add_argument("--max-age", type=positive_float, default=2.0, help="Tuổi tối đa của ảnh/kết quả, giây")
    parser.add_argument("--freeze-after", type=float, default=5.0, help="Hủy dữ liệu khi ảnh lặp tuyệt đối quá số giây này; 0 tắt")
    parser.add_argument("--font", help="Phông .ttf/.ttc hỗ trợ tiếng Việt")
    parser.add_argument("--speech-backend", choices=("auto", "winrt", "sapi", "onecore"), default="auto")
    parser.add_argument("--voice-id", help="ID giọng vi/vi-VN từ --list-voices")
    parser.add_argument("--metrics", type=Path, help="Ghi số đo JSONL; tự thêm số vào tên nếu tệp đã tồn tại")
    return parser


@dataclass(frozen=True)
class View:
    frame: Frame | None
    detections: tuple[Detection, ...]
    narration: Narration | None
    text: str
    valid_detection: bool
    inference_ms: float | None


def select_view(camera, pipeline, *, no_detect: bool, now: float, max_age: float,
                confidence: float) -> View:
    """Chỉ vẽ box lên đúng ảnh mà model đã xử lý, và chặn phiên/ảnh cũ lần cuối."""
    frame = camera.frame
    camera_fresh = (camera.healthy and frame is not None and
                    frame.session_id == camera.session_id and 0 <= now - frame.captured_at < max_age)
    if not camera_fresh:
        return View(None, (), None, "Không có dữ liệu camera còn mới.", False, None)
    if no_detect:
        return View(frame, (), None, "Đang xem camera; nhận diện đã tắt.", False, None)
    result = pipeline.result if pipeline else None
    if (result is None or result.error or result.frame.session_id != camera.session_id or
            not 0 <= now - result.frame.captured_at < max_age):
        return View(frame, (), None, "Đang chờ kết quả nhận diện còn mới.", False, None)
    narration = narrate(result, session_id=camera.session_id, now=now,
                        min_confidence=confidence, max_age=max_age)
    return View(result.frame, result.detections, narration,
                narration.text if narration else "Chưa có đối tượng đủ điều kiện mô tả.",
                True, result.inference_ms)


class Metrics:
    def __init__(self, path, args):
        self.started_at = time.monotonic()
        self.handle = None
        self.path = None
        self.next_sample = 0.0
        self.inferences = []
        self.ages = []
        self.seen = None
        if path:
            model_path = Path(args.model).resolve()
            protected_paths = {model_path}
            if path.resolve() == model_path:
                raise ValueError("Đường dẫn metrics phải khác tệp model.")
            if isinstance(args.source, str) and "://" not in args.source:
                source_path = Path(args.source).resolve()
                protected_paths.add(source_path)
                if path.resolve() == source_path:
                    raise ValueError("Đường dẫn metrics phải khác tệp video nguồn.")
            path.parent.mkdir(parents=True, exist_ok=True)
            versions = {}
            for name in ("numpy", "opencv-python", "Pillow", "torch", "torchvision", "ultralytics"):
                try:
                    versions[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    versions[name] = None
            from .model_tools import sha256_file
            model = Path(args.model)
            record = {"type": "run", "started_at": datetime.now(timezone.utc).isoformat(),
                        "os": platform.platform(), "processor": platform.processor(),
                        "python": platform.python_version(), "versions": versions,
                        "source_kind": "camera-index" if isinstance(args.source, int) else "file-or-url",
                        "camera_index": args.source if isinstance(args.source, int) else None,
                        "model": model.name, "model_sha256": sha256_file(model) if model.is_file() and not args.no_detect else None,
                        "device": args.device, "imgsz": args.imgsz, "conf": args.conf, "iou": args.iou,
                        "speech_backend": args.speech_backend,
                        "camera_backend": args.backend, "rotation": args.rotation, "mirror": args.mirror,
                        "max_age_s": args.max_age, "freeze_after_s": args.freeze_after,
                        "timing_origin": "time.monotonic ngay sau OpenCV.read; không đo truyền hình từ điện thoại"}
            candidate, number = path, 0
            while True:
                # Exclusive creation preserves existing logs even if another
                # process picks the same candidate at the same instant.
                if candidate.resolve() not in protected_paths:
                    try:
                        self.handle = candidate.open("x", encoding="utf-8", buffering=1)
                        self.path = candidate
                        break
                    except FileExistsError:
                        pass
                number += 1
                candidate = path.with_name(f"{path.stem}-{number}{path.suffix}")
            record["metrics_file"] = str(self.path)
            try:
                self.write(record)
            except Exception:
                self.handle.close()
                self.handle = None
                raise

    def write(self, record):
        if self.handle:
            self.handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def record(self, now, camera, pipeline, view, audio):
        if not self.handle:
            return
        age = (now - view.frame.captured_at) * 1000 if view.frame else None
        key = (view.frame.session_id, view.frame.frame_id) if view.frame else None
        if view.valid_detection and key != self.seen:
            self.seen = key
            self.inferences.append(view.inference_ms)
            self.ages.append(age)
            # Bộ nhớ giới hạn cho phiên dài; summary ghi rõ cửa sổ tối đa.
            self.inferences = self.inferences[-10000:]
            self.ages = self.ages[-10000:]
        if now >= self.next_sample:
            self.next_sample = now + 1
            evidence_at = getattr(audio, "evidence_captured_at", None)
            self.write({"type": "sample", "monotonic_s": now, "camera_fps": camera.fps,
                        "elapsed_s": now - self.started_at, "camera_session_id": camera.session_id,
                        "yolo_fps": pipeline.fps if pipeline else 0.0,
                        "inference_ms": view.inference_ms, "display_frame_age_ms": age,
                        "resolution": [view.frame.width, view.frame.height] if view.frame else None,
                        "camera_healthy": camera.healthy, "valid_detection": view.valid_detection,
                        "camera_status": camera.status, "model_status": pipeline.status if pipeline else "Đã tắt",
                        "audio_status": audio.status, "pending_speech": audio.pending_count,
                        "audio_enabled": getattr(audio, "enabled", None),
                        "has_narration": view.narration is not None,
                        "narration_group_count": len(view.narration.groups) if view.narration else 0,
                        "speech_started": getattr(audio, "utterances_started", 0),
                        "speech_completed": getattr(audio, "utterances_completed", 0),
                        "speech_cancelled": getattr(audio, "utterances_cancelled", 0),
                        "speech_last_event": getattr(audio, "last_event", ""),
                        "speech_evidence_frame_id": getattr(audio, "evidence_frame_id", None),
                        "speech_evidence_age_ms": (now - evidence_at) * 1000 if evidence_at is not None else None})

    def close(self):
        if self.handle:
            def stats(values):
                values = sorted(values)
                return {"count": len(values), "p50": statistics.median(values),
                        "p95": values[max(0, math.ceil(len(values) * 0.95) - 1)]} if values else None
            self.write({"type": "summary", "window": "Tối đa 10000 kết quả khác nhau được hiển thị cuối phiên",
                        "duration_s": time.monotonic() - self.started_at,
                        "inference_ms": stats(self.inferences), "display_frame_age_ms": stats(self.ages),
                        "audio_playback_heard": "Chưa được người nghe xác nhận bằng số đo này"})
            self.handle.close()


def run(args):
    from .camera import CameraWorker
    from .detector import YoloDetector
    from .display import Display
    from .feedback import FeedbackManager
    from .pipeline import PipelineWorker
    from .speech import FastSpeechEngine, WindowsSpeechEngine

    display = camera = pipeline = feedback = metrics = None
    try:
        display = Display(args.font)  # Kiểm tra GUI/phông trước khi chiếm camera.
        metrics = Metrics(args.metrics, args)
        if metrics.path:
            print("Ghi số đo: " + str(metrics.path), flush=True)
        camera = CameraWorker(args.source, backend=args.backend, width=args.width,
                              height=args.height, rotation=args.rotation, mirror=args.mirror,
                              stale_after=args.max_age, freeze_after=args.freeze_after)
        # auto = worker WinRT chạy sẵn (nhanh); winrt/sapi/onecore = engine cũ, mỗi câu một tiến trình.
        engine = (FastSpeechEngine(voice_id=args.voice_id) if args.speech_backend == "auto"
                  else WindowsSpeechEngine(backend=args.speech_backend, voice_id=args.voice_id))
        feedback = FeedbackManager(engine, enabled=not (args.mute or args.no_detect))
        camera.start()
        if not args.no_detect:
            # Import torch trong worker nạp model, không chặn vòng hiển thị.
            pipeline = PipelineWorker(
                camera, lambda: YoloDetector(args.model, args.imgsz, args.conf, args.iou,
                                             resolve_device(args.device),
                                             track=not args.no_track, walking_only=args.walking_only,
                                             enhance=not args.no_enhance), max_age=args.max_age)
            pipeline.start()
        last_key = None
        last_audio_error = None
        while True:
            camera_state = camera.snapshot()
            pipeline_state = pipeline.snapshot() if pipeline else None
            now = time.monotonic()
            view = select_view(camera_state, pipeline_state, no_detect=args.no_detect,
                               now=now, max_age=args.max_age, confidence=args.conf)
            feedback.set_context(camera_state.session_id, view.valid_detection)
            key = (view.frame.session_id, view.frame.frame_id) if view.frame and view.valid_detection else None
            if key != last_key:
                feedback.submit(view.narration)
                last_key = key
            audio = feedback.snapshot()
            if audio.error and audio.error != last_audio_error:
                print("Lỗi âm thanh: " + audio.error, file=sys.stderr)
            last_audio_error = audio.error
            age_ms = (now - view.frame.captured_at) * 1000 if view.frame else None
            display.render(view.frame, view.detections, camera_status=camera_state.status,
                           model_status=pipeline_state.status if pipeline_state else "Đã tắt nhận diện",
                           audio_status=audio.status, narration_text=view.text, speaking_text=audio.speaking_text,
                           camera_fps=camera_state.fps, yolo_fps=pipeline_state.fps if pipeline_state else 0,
                           inference_ms=view.inference_ms, age_ms=age_ms)
            metrics.record(now, camera_state, pipeline_state, view, audio)
            key_pressed = display.key()
            if key_pressed == ord("q"):
                break
            if key_pressed == ord("m") and not args.no_detect:
                feedback.set_enabled(not audio.enabled)
                last_key = None
        return 0
    except KeyboardInterrupt:
        return 0
    except ImportError as exc:
        print(f"Thiếu thư viện {exc.name}. Cài requirements.txt trong .venv theo README.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Không chạy được prototype ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    finally:
        if feedback:
            feedback.close()
        if pipeline:
            pipeline.close()
        if camera:
            camera.close()
        if display:
            display.close()
        if metrics:
            metrics.close()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.imgsz <= 0 or args.imgsz % 32:
        parser.error("--imgsz phải là bội số dương của 32.")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width và --height phải lớn hơn 0.")
    if not math.isfinite(args.freeze_after) or args.freeze_after < 0:
        parser.error("--freeze-after phải hữu hạn và không âm.")
    if isinstance(args.source, str) and args.source.startswith("-"):
        parser.error("Nguồn camera không hợp lệ.")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
