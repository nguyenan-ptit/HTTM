from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from prototype.main import build_parser, run, select_view
from prototype.types import Detection, DetectionResult, Frame


class Image:
    shape = (480, 640, 3)


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.frame = Frame("s", 1, 10.0, Image())
        self.camera = SimpleNamespace(frame=Frame("s", 2, 10.1, Image()), healthy=True, session_id="s")
        self.result = DetectionResult(self.frame, (Detection(0, "person", .9, (0, 0, 100, 400)),), 100, 10.1)
        self.pipeline = SimpleNamespace(result=self.result)

    def select(self, **kw):
        defaults = dict(no_detect=False, now=10.2, max_age=2, confidence=.45)
        defaults.update(kw)
        return select_view(self.camera, self.pipeline, **defaults)

    def test_boxes_use_exact_processed_frame(self):
        view = self.select()
        self.assertIs(view.frame, self.frame)
        self.assertIn("Có người", view.text)
        self.assertTrue(view.valid_detection)

    def test_stale_result_falls_back_raw_without_boxes(self):
        self.camera.frame = Frame("s", 5, 12.0, Image())
        view = self.select(now=12.1)
        self.assertIs(view.frame, self.camera.frame)
        self.assertEqual(view.detections, ())
        self.assertIsNone(view.narration)
        self.assertFalse(view.valid_detection)

    def test_no_result_from_previous_session(self):
        self.camera.session_id = "new"
        self.camera.frame = Frame("new", 1, 10.1, Image())
        view = self.select()
        self.assertEqual(view.detections, ())
        self.assertIsNone(view.narration)

    def test_camera_loss_blocks_current_result(self):
        self.camera.healthy = False
        self.assertIsNone(self.select().frame)
        self.assertIsNone(self.select().narration)

    def test_no_detect_skips_narration(self):
        self.assertIs(self.select(no_detect=True).frame, self.camera.frame)
        self.assertIsNone(self.select(no_detect=True).narration)

    def test_empty_result_never_claims_safe(self):
        self.pipeline.result = DetectionResult(self.frame, (), 100, 10.1)
        self.assertEqual(self.select().text, "Chưa có đối tượng đủ điều kiện mô tả.")

    def test_cli_options(self):
        args = build_parser().parse_args(["--source", "1", "--mute", "--rotation", "90", "--mirror"])
        self.assertEqual(args.source, 1)
        self.assertTrue(args.mute)
        self.assertEqual(args.rotation, 90)


class MainLoopTests(unittest.TestCase):
    def test_unmute_error_does_not_stop_video_and_all_workers_close(self):
        from prototype.camera import CameraSnapshot
        from prototype.pipeline import PipelineSnapshot

        frame = Frame("integration-io-fake", 1, time.monotonic(), Image())
        result = DetectionResult(frame, (Detection(0, "person", .9, (0, 0, 100, 300)),), 3, time.monotonic())

        class Camera:
            closed = False
            def start(self): pass
            def snapshot(self):
                return CameraSnapshot(frame, "Camera giả đang chạy", frame.session_id, 20, True)
            def close(self): self.closed = True

        class Pipeline:
            closed = False
            def start(self): pass
            def snapshot(self): return PipelineSnapshot(result, "YOLO giả đang chạy", 10)
            def close(self): self.closed = True

        class Engine:
            closed = False
            def start(self, text): raise RuntimeError("TTS lỗi kiểm thử")
            def poll(self): return None
            def stop(self): pass
            def close(self): self.closed = True

        class Display:
            def __init__(self):
                self.renders = []
                self.closed = False
            def render(self, *args, **kwargs): self.renders.append((args, kwargs))
            def key(self):
                time.sleep(.005)
                if len(self.renders) == 1: return ord("m")
                if "TTS lỗi kiểm thử" in self.renders[-1][1]["audio_status"] or len(self.renders) > 200:
                    return ord("q")
                return -1
            def close(self): self.closed = True

        camera, pipeline, engine, display = Camera(), Pipeline(), Engine(), Display()
        args = build_parser().parse_args(["--source", "0", "--mute"])
        with patch("prototype.camera.CameraWorker", return_value=camera), \
             patch("prototype.pipeline.PipelineWorker", return_value=pipeline), \
             patch("prototype.speech.FastSpeechEngine", return_value=engine), \
             patch("prototype.display.Display", return_value=display):
            self.assertEqual(run(args), 0)
        self.assertIn("TTS lỗi kiểm thử", display.renders[-1][1]["audio_status"])
        self.assertIs(display.renders[-1][0][0], frame)
        self.assertIn("Có người", display.renders[-1][1]["narration_text"])
        self.assertTrue(all(worker.closed for worker in (camera, pipeline, engine, display)))


if __name__ == "__main__":
    unittest.main()
