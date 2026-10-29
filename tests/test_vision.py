"""Lifecycle, geometry and freshness tests; no device or ML dependency needed."""

from __future__ import annotations

from pathlib import Path
import os
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prototype.camera import CameraSnapshot, CameraWorker, transform_image
from prototype.detector import YoloDetector, parse_detections
from prototype.pipeline import PipelineWorker
from prototype.types import DetectionResult, Frame


class Image:
    """Small immutable-in-use stand-in for a BGR ndarray."""

    def __init__(self, pixels=None):
        self.pixels = pixels or [[1, 2, 3], [4, 5, 6]]
        self.shape = (len(self.pixels), len(self.pixels[0]), 3)
        self.size = self.shape[0] * self.shape[1] * 3

    def copy(self):
        return Image([row[:] for row in self.pixels])

    def tobytes(self):
        return bytes(value for row in self.pixels for value in row)


class FakeCV:
    ROTATE_90_CLOCKWISE = 90
    ROTATE_180 = 180
    ROTATE_90_COUNTERCLOCKWISE = 270

    @staticmethod
    def rotate(image, mode):
        rows = image.pixels
        if mode == 90:
            return Image([list(row) for row in zip(*rows[::-1])])
        if mode == 180:
            return Image([row[::-1] for row in rows[::-1]])
        return Image([list(row) for row in zip(*rows)][::-1])

    @staticmethod
    def flip(image, axis):
        if axis != 1:
            raise AssertionError("Expected horizontal mirroring")
        return Image([row[::-1] for row in image.pixels])


def eventually(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.002)
    raise AssertionError("Worker did not reach the expected state")


class BlockingCapture:
    def __init__(self, image=None, disconnect=None):
        self.image = image or Image()
        self.disconnect = disconnect or threading.Event()
        self.first = True
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        if self.first:
            self.first = False
            return True, self.image
        self.disconnect.wait(5)
        return False, None

    def release(self):
        self.released = True


class CameraTests(unittest.TestCase):
    def test_rotation_then_mirror_and_owned_copy(self):
        source = Image()
        rotated = transform_image(source, 90, True, FakeCV)
        self.assertEqual(rotated.pixels, [[1, 4], [2, 5], [3, 6]])
        self.assertEqual(rotated.shape, (3, 2, 3))
        self.assertEqual(transform_image(source, 180, False, FakeCV).pixels, [[6, 5, 4], [3, 2, 1]])
        self.assertEqual(transform_image(source, 270, False, FakeCV).pixels, [[3, 6], [2, 5], [1, 4]])
        plain = transform_image(source, 0, False)
        plain.pixels[0][0] = 9
        self.assertEqual(source.pixels[0][0], 1)

    def test_stuck_read_expires_and_close_does_not_hang(self):
        now = [10.0]
        capture = BlockingCapture()
        worker = CameraWorker(1, capture_factory=lambda *args: capture, clock=lambda: now[0])
        worker.start()
        try:
            eventually(lambda: worker.snapshot().healthy)
            now[0] = 13.0
            self.assertFalse(worker.snapshot().healthy)
            self.assertIsNone(worker.snapshot().frame)
            started = time.monotonic()
            worker.close()
            self.assertLess(time.monotonic() - started, 0.7)
            self.assertIsNone(worker.snapshot().frame)
        finally:
            capture.disconnect.set()
            worker.close()
        eventually(lambda: capture.released)

    def test_disconnect_reconnect_changes_session(self):
        first, second = BlockingCapture(), BlockingCapture(Image([[7, 8], [9, 10]]))
        captures = iter([first, second])
        worker = CameraWorker(1, capture_factory=lambda *args: next(captures), retry_delay=0.01)
        worker.start()
        try:
            eventually(lambda: worker.snapshot().healthy)
            initial = worker.snapshot()
            first.disconnect.set()
            eventually(lambda: worker.snapshot().healthy and worker.snapshot().session_id != initial.session_id)
            after = worker.snapshot()
            self.assertTrue(first.released)
            self.assertNotEqual(initial.session_id, after.session_id)
            self.assertEqual(after.frame.frame_id, 1)
            self.assertEqual(after.frame.image.pixels, second.image.pixels)
        finally:
            second.disconnect.set()
            worker.close()

    def test_identical_stream_is_suppressed_even_after_reopen(self):
        now = [0.0]

        class IdenticalCapture:
            def isOpened(self):
                return True

            def read(self):
                now[0] += 1.0
                return True, Image()

            def release(self):
                pass

        worker = CameraWorker(1, freeze_after=2.0, capture_factory=lambda *args: IdenticalCapture(),
                              clock=lambda: now[0], retry_delay=0.01)
        worker.start()
        try:
            eventually(lambda: "không thay đổi" in worker.snapshot().status)
            self.assertIsNone(worker.snapshot().frame)
            eventually(lambda: now[0] >= 4.0)
            self.assertFalse(worker.snapshot().healthy)
        finally:
            worker.close()

    def test_status_does_not_echo_source_or_exception_credentials(self):
        secret = "http://user:password@example.invalid/live?token=secret"

        def fail(*args):
            raise RuntimeError(secret)

        worker = CameraWorker(secret, capture_factory=fail)
        worker.start()
        try:
            eventually(lambda: "Lỗi đọc" in worker.snapshot().status)
            self.assertNotIn("password", worker.snapshot().status)
            self.assertNotIn("secret", worker.snapshot().status)
        finally:
            worker.close()

    def test_blocked_open_reports_missing_data_without_opening_second_capture(self):
        now = [10.0]
        entered, resume = threading.Event(), threading.Event()
        calls = []

        def blocked(*args):
            calls.append(args)
            entered.set()
            resume.wait(2)
            return BlockingCapture()

        worker = CameraWorker(1, capture_factory=blocked, clock=lambda: now[0])
        worker.start()
        self.assertTrue(entered.wait(1))
        now[0] = 13.0
        self.assertIn("Chưa nhận", worker.snapshot().status)
        self.assertFalse(worker.snapshot().healthy)
        self.assertEqual(len(calls), 1)
        worker.close()
        resume.set()
        eventually(lambda: not worker._thread.is_alive())


class Values:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


def yolo_result(coordinates, scores, classes, names=None, shape=(2, 3)):
    boxes = SimpleNamespace(xyxy=Values(coordinates), conf=Values(scores), cls=Values(classes))
    return SimpleNamespace(boxes=boxes, names=names or {0: "person", 11: "stop sign"}, orig_shape=shape)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.frame = Frame("session", 1, 10.0, Image())

    def test_original_coordinates_remain_original_without_second_nms(self):
        source = yolo_result([[0.5, 0.25, 2.5, 1.5], [0.5, 0.25, 2.5, 1.5]], [0.9, 0.8], [0, 11])
        detections = parse_detections(source, self.frame, 0.45)
        self.assertEqual(len(detections), 2)
        self.assertEqual(detections[0].bbox, (0.5, 0.25, 2.5, 1.5))
        self.assertEqual(detections[1].label, "stop sign")

    def test_class_names_are_actual_custom_names_independent_of_coco_ids(self):
        detector = YoloDetector.__new__(YoloDetector)
        detector._model = SimpleNamespace(names={"0": "custom obstacle", 11: "custom marker"})
        names = detector.class_names
        self.assertEqual(names, {0: "custom obstacle", 11: "custom marker"})
        self.assertNotIn("person", names.values())
        self.assertNotIn("stop sign", names.values())
        names[0] = "changed caller copy"
        self.assertEqual(detector.class_names[0], "custom obstacle")
        detector._model = SimpleNamespace(names=["custom first", "traffic light"])
        self.assertEqual(detector.class_names, {0: "custom first", 1: "traffic light"})

    def test_invalid_model_class_identifiers_are_rejected(self):
        detector = YoloDetector.__new__(YoloDetector)
        for names in ({"class": "object"}, {-1: "object"}, {0.5: "object"}, None):
            detector._model = SimpleNamespace(names=names)
            with self.assertRaises(ValueError):
                _ = detector.class_names

    def test_invalid_boxes_scores_and_classes_are_filtered(self):
        source = yolo_result(
            [[-1, -1, 4, 3], [0, 0, 1, 1], [0, 0, float("nan"), 1], [2, 1, 1, 2],
             [9, 0, 10, 1], [0, 0, 1, 1], [0, 0, 1, 1], [0, 0, 1, 1]],
            [0.9, 0.1, 0.9, 0.9, 0.9, float("inf"), 0.9, 1.1],
            [0, 0, 0, 0, 0, 0, 0.5, 0],
        )
        detections = parse_detections(source, self.frame, 0.45)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].bbox, (0.0, 0.0, 3, 2))

    def test_missing_model_class_is_preserved_as_unknown_id(self):
        source = yolo_result([[0, 0, 1, 1]], [0.9], [99])
        self.assertEqual(parse_detections(source, self.frame, 0.45)[0].label, "class 99")

    def test_mismatched_original_shape_rejected(self):
        with self.assertRaises(ValueError):
            parse_detections(yolo_result([], [], [], shape=(640, 480)), self.frame, 0.45)

    def test_nonexistent_model_rejected_before_loading(self):
        with patch.object(Path, "is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                YoloDetector(Path("missing") / "yolov8n.pt")

    def test_predict_passes_full_transformed_source_and_one_nms_configuration(self):
        calls = {}

        class Model:
            def __init__(self, path, **options):
                calls["load"] = (path, options)

            def predict(self, **options):
                calls["predict"] = options
                return [yolo_result([[0, 0, 1, 1]], [0.9], [0])]

        model_path = Path("fake_model_for_unit_test.pt")
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "mkdir"), patch.dict(os.environ):
            with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Model)}):
                result = YoloDetector(model_path, track=False, enhance=False).predict(self.frame)
        self.assertEqual(calls["load"], (str(model_path.resolve()), {"task": "detect"}))
        self.assertIs(calls["predict"]["source"], self.frame.image)
        self.assertEqual(calls["predict"]["iou"], 0.45)
        self.assertFalse(calls["predict"]["save"])
        self.assertEqual(result.frame, self.frame)
        self.assertGreaterEqual(result.inference_ms, 0)

    def test_tracker_confirmation_filters_flicker_and_resets_on_new_session(self):
        calls = []

        def tracked(ids):
            result = yolo_result([[0, 0, 1, 1], [1, 0, 2, 1]], [0.9, 0.8], [0, 0])
            result.boxes.id = None if ids is None else Values(ids)
            return result

        outputs = iter([tracked([7, 8]), tracked(None)])

        class Model:
            names = {0: "person", 1: "bicycle", 46: "banana"}

            def __init__(self, *args, **kwargs):
                pass

            def track(self, **options):
                calls.append(options)
                return [next(outputs)]

        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "mkdir"), patch.dict(os.environ):
            with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Model)}):
                detector = YoloDetector("fake_model_for_unit_test.pt", walking_only=True, enhance=False)
        self.assertEqual(sorted(detector._classes), [0, 1])  # banana bị loại
        first = detector.predict(self.frame)
        self.assertEqual([d.track_id for d in first.detections], [7, 8])
        self.assertEqual(calls[0]["classes"], detector._classes)
        self.assertFalse(calls[0]["persist"])  # phiên đầu: tracker mới
        again = detector.predict(Frame("session", 2, 10.1, Image()))
        self.assertEqual(again.detections, ())  # chưa xác nhận thì không báo
        self.assertTrue(calls[1]["persist"])
        outputs = iter([tracked([1, 2])])
        detector.predict(Frame("other", 1, 10.2, Image()))
        self.assertFalse(calls[2]["persist"])  # phiên mới: bỏ track cũ

    def test_custom_model_keeps_all_classes(self):
        class Model:
            names = {0: "custom obstacle"}

            def __init__(self, *args, **kwargs):
                pass

        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "mkdir"), patch.dict(os.environ):
            with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Model)}):
                self.assertIsNone(YoloDetector("fake_model_for_unit_test.pt")._classes)

    def test_yolo_environment_is_configured_before_import_and_loading(self):
        captured = {}

        class Model:
            def __init__(self, *args, **kwargs):
                captured.update({key: os.environ.get(key) for key in
                                 ("YOLO_CONFIG_DIR", "YOLO_AUTOINSTALL", "YOLO_OFFLINE")})

        with patch.dict(os.environ, {"YOLO_AUTOINSTALL": "true", "YOLO_OFFLINE": "false"}):
            os.environ.pop("YOLO_CONFIG_DIR", None)
            with patch.object(Path, "is_file", return_value=True), patch.object(Path, "mkdir") as mkdir:
                with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Model)}):
                    YoloDetector("fake_model_for_unit_test.pt")
            mkdir.assert_called_once_with(parents=True, exist_ok=True)
        self.assertEqual(captured["YOLO_AUTOINSTALL"], "false")
        self.assertEqual(captured["YOLO_OFFLINE"], "true")
        expected = Path(__file__).resolve().parents[1] / ".tmp" / "ultralytics"
        self.assertEqual(Path(captured["YOLO_CONFIG_DIR"]), expected)

    def test_explicit_yolo_config_directory_is_preserved(self):
        with patch.dict(os.environ, {"YOLO_CONFIG_DIR": "user-chosen-config"}):
            with patch.object(Path, "is_file", return_value=True), patch.object(Path, "mkdir") as mkdir:
                with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=lambda *args, **kwargs: None)}):
                    YoloDetector("fake_model_for_unit_test.pt")
            self.assertEqual(os.environ["YOLO_CONFIG_DIR"], "user-chosen-config")
            mkdir.assert_not_called()


class MutableCamera:
    def __init__(self, frame):
        self.state = CameraSnapshot(frame, "Camera đang nhận hình.", frame.session_id, 10.0, True)

    def snapshot(self):
        return self.state


class ControlledDetector:
    def __init__(self, block=False, error=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []
        self.block, self.error = block, error

    def predict(self, frame):
        self.calls.append(frame)
        self.started.set()
        if self.block:
            self.release.wait(2)
        if self.error:
            raise RuntimeError("private detail")
        return DetectionResult(frame, (), 3.0, frame.captured_at + 0.003)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.frame = Frame("old", 1, 10.0, Image())
        self.camera = MutableCamera(self.frame)

    def worker(self, detector):
        worker = PipelineWorker(self.camera, lambda: detector, clock=lambda: self.now[0])
        self.addCleanup(worker.close)
        worker.start()
        return worker

    def test_same_frame_inferred_once_then_latest_frame_only(self):
        detector = ControlledDetector()
        worker = self.worker(detector)
        eventually(lambda: worker.snapshot().result is not None)
        time.sleep(0.03)
        self.assertEqual(len(detector.calls), 1)
        newer = Frame("old", 50, 10.0, Image())
        self.camera.state = CameraSnapshot(newer, "ok", "old", 20.0, True)
        eventually(lambda: worker.snapshot().result.frame.frame_id == 50)
        self.assertEqual([frame.frame_id for frame in detector.calls], [1, 50])

    def test_late_old_session_result_discarded(self):
        detector = ControlledDetector(block=True)
        worker = self.worker(detector)
        self.assertTrue(detector.started.wait(1))
        self.camera.state = CameraSnapshot(None, "mất kết nối", "new", 0.0, False)
        detector.release.set()
        eventually(lambda: "chờ" in worker.snapshot().status or "phiên cũ" in worker.snapshot().status)
        self.assertIsNone(worker.snapshot().result)

    def test_slow_inference_uses_source_age_not_completion_time(self):
        detector = ControlledDetector(block=True)
        worker = self.worker(detector)
        self.assertTrue(detector.started.wait(1))
        self.now[0] = 13.0
        detector.release.set()
        eventually(lambda: "cũ" in worker.snapshot().status)
        self.assertIsNone(worker.snapshot().result)

    def test_snapshot_immediately_rejects_camera_change_and_expired_result(self):
        detector = ControlledDetector()
        worker = self.worker(detector)
        eventually(lambda: worker.snapshot().result is not None)
        self.now[0] = 13.0
        self.assertIsNone(worker.snapshot().result)
        self.now[0] = 10.0
        self.camera.state = CameraSnapshot(self.frame, "ok", "new", 1.0, True)
        self.assertIsNone(worker.snapshot().result)

    def test_model_failure_does_not_raise_on_ui_thread(self):
        worker = self.worker(ControlledDetector(error=True))
        eventually(lambda: "Lỗi model" in worker.snapshot().status)
        self.assertIsNone(worker.snapshot().result)
        self.assertNotIn("private", worker.snapshot().status)

    def test_model_loading_failure_is_reported(self):
        def fail():
            raise FileNotFoundError("private path")

        worker = PipelineWorker(self.camera, fail)
        self.addCleanup(worker.close)
        worker.start()
        eventually(lambda: "Chưa có model" in worker.snapshot().status)
        self.assertIsNone(worker.snapshot().result)

    def test_close_rejects_inflight_result(self):
        detector = ControlledDetector(block=True)
        worker = self.worker(detector)
        self.assertTrue(detector.started.wait(1))
        worker.close()
        detector.release.set()
        eventually(lambda: not worker._thread.is_alive())
        self.assertIsNone(worker.snapshot().result)


if __name__ == "__main__":
    unittest.main()
