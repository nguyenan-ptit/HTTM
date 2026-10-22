import contextlib
import io
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from prototype.main import Metrics, View, build_parser, run
from prototype.types import Frame


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.allowed = Path(__file__).resolve().parents[1] / ".tmp"
        self.directory = self.allowed / ("metrics-test-" + uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
        self.args = build_parser().parse_args(["--source", "0", "--model", str(self.directory / "test.pt")])

    def tearDown(self):
        if not self.directory.resolve().is_relative_to(self.allowed.resolve()):
            raise RuntimeError("Từ chối xóa ngoài thư mục tạm kiểm thử")
        shutil.rmtree(self.directory)

    def test_refuses_alias_of_model_and_source(self):
        model = Path(self.args.model)
        model.write_bytes(b"original model")
        with self.assertRaises(ValueError):
            Metrics(model, self.args)
        self.assertEqual(model.read_bytes(), b"original model")
        video = self.directory / "video.mp4"
        video.write_bytes(b"original video")
        self.args.source = str(video)
        with self.assertRaises(ValueError):
            Metrics(video, self.args)
        self.assertEqual(video.read_bytes(), b"original video")

    def test_existing_metrics_are_never_overwritten_or_appended(self):
        path = self.directory / "existing.jsonl"
        path.write_bytes(b"user data")
        metrics = Metrics(path, self.args)
        try:
            self.assertEqual(metrics.path, self.directory / "existing-1.jsonl")
        finally:
            metrics.close()
        self.assertEqual(path.read_bytes(), b"user data")

    def test_same_command_can_restart_twice_without_losing_old_log(self):
        from prototype.camera import CameraSnapshot
        from prototype.pipeline import PipelineSnapshot
        from prototype.types import DetectionResult

        path = self.directory / "session.jsonl"
        path.write_bytes(b"original user log")
        args = build_parser().parse_args(["--source", "1", "--mute", "--metrics", str(path)])
        now = time.monotonic()
        frame = Frame("fake-io-restart", 1, now, SimpleNamespace(shape=(480, 640, 3)))
        camera, pipeline, display, engine = Mock(), Mock(), Mock(), Mock()
        camera.snapshot.return_value = CameraSnapshot(frame, "Camera giả", frame.session_id, 20, True)
        pipeline.snapshot.return_value = PipelineSnapshot(DetectionResult(frame, (), 1, now), "Model giả", 10)
        display.key.return_value = ord("q")
        with patch("prototype.camera.CameraWorker", return_value=camera), \
             patch("prototype.pipeline.PipelineWorker", return_value=pipeline), \
             patch("prototype.display.Display", return_value=display), \
             patch("prototype.speech.WindowsSpeechEngine", return_value=engine), \
             contextlib.redirect_stdout(io.StringIO()) as console:
            self.assertEqual(run(args), 0)
            self.assertEqual(run(args), 0)
        self.assertIn("session-1.jsonl", console.getvalue())
        self.assertIn("session-2.jsonl", console.getvalue())
        self.assertEqual(camera.start.call_count, 2)
        self.assertEqual(display.render.call_count, 2)
        self.assertEqual(path.read_bytes(), b"original user log")
        for name in ("session-1.jsonl", "session-2.jsonl"):
            records = [json.loads(line) for line in (self.directory / name).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record["type"] for record in records], ["run", "sample", "summary"])

    def test_renamed_log_cannot_take_model_path(self):
        path = self.directory / "session.pt"
        path.write_bytes(b"old log")
        self.args.model = str(self.directory / "session-1.pt")
        metrics = Metrics(path, self.args)
        try:
            self.assertEqual(metrics.path, self.directory / "session-2.pt")
            self.assertFalse(Path(self.args.model).exists())
        finally:
            metrics.close()

    def test_unique_result_summary_and_no_narration_in_log(self):
        path = self.directory / "new.jsonl"
        metrics = Metrics(path, self.args)
        now = time.monotonic()
        frame = Frame("test-session", 1, now - .1, SimpleNamespace(shape=(480, 640, 3)))
        view = View(frame, (), None, "Nội dung riêng không được lưu", True, 12.0)
        camera = SimpleNamespace(fps=20, session_id="test-session", healthy=True, status="Đang chạy")
        pipeline = SimpleNamespace(fps=10, status="Đang chạy")
        audio = SimpleNamespace(status="Đã tắt tiếng", pending_count=0, enabled=False,
                                utterances_started=3, utterances_completed=1,
                                utterances_cancelled=2, last_event="cancelled:ttl",
                                evidence_captured_at=now - .1, evidence_frame_id=1)
        try:
            metrics.record(now, camera, pipeline, view, audio)
            metrics.record(now + .01, camera, pipeline, view, audio)
        finally:
            metrics.close()
        contents = path.read_text(encoding="utf-8")
        records = [json.loads(line) for line in contents.splitlines()]
        self.assertEqual([record["type"] for record in records], ["run", "sample", "summary"])
        self.assertEqual(records[-1]["inference_ms"]["count"], 1)
        self.assertEqual(records[-1]["inference_ms"]["p95"], 12)
        sample = records[1]
        self.assertFalse(sample["audio_enabled"])
        self.assertEqual(sample["speech_started"], 3)
        self.assertEqual(sample["speech_completed"], 1)
        self.assertEqual(sample["speech_cancelled"], 2)
        self.assertEqual(sample["speech_last_event"], "cancelled:ttl")
        self.assertAlmostEqual(sample["speech_evidence_age_ms"], 100, delta=.01)
        self.assertNotIn("Nội dung riêng", contents)


if __name__ == "__main__":
    unittest.main()
