"""Ghép camera/pipeline/narration/feedback thật với IO giả; không đo thiết bị."""

import threading
import time
import unittest

from prototype.camera import CameraWorker
from prototype.feedback import FeedbackManager
from prototype.main import select_view
from prototype.pipeline import PipelineWorker
from prototype.types import Detection, DetectionResult


class Pixels:
    size = 640 * 480 * 3
    shape = (480, 640, 3)

    def __init__(self, value=0):
        self.value = value

    def copy(self):
        return Pixels(self.value)

    def tobytes(self):
        return str(self.value).encode()


class Capture:
    def __init__(self, alive):
        self.alive = alive
        self.frame = 0

    def isOpened(self):
        return True

    def read(self):
        time.sleep(.005)
        self.frame += 1
        return (True, Pixels(self.frame)) if self.alive.is_set() else (False, None)

    def release(self):
        pass


class Detector:
    def predict(self, frame):
        return DetectionResult(frame, (Detection(0, "person", .9, (10, 0, 100, 400)),), .5, time.monotonic())


class Speech:
    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.text = ""
        self.busy = False

    def start(self, text):
        self.text = text
        self.busy = True
        self.started.set()

    def poll(self):
        return None

    def stop(self):
        if self.busy:
            self.stopped.set()
        self.busy = False

    def close(self):
        self.stop()


class IntegrationTests(unittest.TestCase):
    def test_camera_loss_cancels_sentence_from_yolo_without_blocking_view(self):
        alive = threading.Event()
        alive.set()
        camera = CameraWorker(0, capture_factory=lambda *args: Capture(alive), retry_delay=.01)
        pipeline = PipelineWorker(camera, Detector)
        engine = Speech()
        feedback = FeedbackManager(engine)
        try:
            camera.start()
            pipeline.start()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not engine.started.is_set():
                state = camera.snapshot()
                view = select_view(state, pipeline.snapshot(), no_detect=False,
                                   now=time.monotonic(), max_age=2, confidence=.45)
                feedback.set_context(state.session_id, view.valid_detection)
                if view.narration:
                    feedback.submit(view.narration)
                time.sleep(.005)
            self.assertTrue(engine.started.is_set(), "Chưa ghép được câu từ pipeline sang feedback")
            self.assertEqual(engine.text, "Có người ở bên trái.")
            alive.clear()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not engine.stopped.is_set():
                state = camera.snapshot()
                view = select_view(state, pipeline.snapshot(), no_detect=False,
                                   now=time.monotonic(), max_age=2, confidence=.45)
                feedback.set_context(state.session_id, view.valid_detection)
                time.sleep(.005)
            self.assertTrue(engine.stopped.is_set(), "Lời từ ảnh cũ chưa bị hủy khi mất dữ liệu")
        finally:
            feedback.close()
            pipeline.close()
            camera.close()


if __name__ == "__main__":
    unittest.main()
