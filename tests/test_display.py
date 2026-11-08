import importlib.util
import unittest

HAS_RENDER_DEPS = all(importlib.util.find_spec(name) for name in ("cv2", "numpy", "PIL"))


@unittest.skipUnless(HAS_RENDER_DEPS, "Cần OpenCV, NumPy và Pillow để kiểm tra render thực")
class DisplayTests(unittest.TestCase):
    def test_unicode_boxes_preserve_camera_pixels_and_render_without_window(self):
        import numpy as np
        from prototype.display import Display
        from prototype.types import Detection, Frame
        pixels = np.zeros((480, 640, 3), dtype=np.uint8)
        original = pixels.copy()
        display = Display(show_window=False)
        try:
            result = display.render(
                Frame("synthetic-test", 1, 10, pixels),
                (Detection(0, "person", .91, (0, 0, 100, 300)),
                 Detection(11, "stop sign", .85, (500, 30, 640, 200))),
                camera_status="Ảnh mẫu kiểm thử — không phải camera thật",
                model_status="Hộp bao mẫu — không phải nhận diện thật",
                audio_status="Đã tắt tiếng", narration_text="Có người ở bên trái. Có biển báo dừng ở bên phải.",
                speaking_text="", camera_fps=0, yolo_fps=0, inference_ms=None, age_ms=None)
            self.assertEqual(result.shape, (900, 960, 3))
            np.testing.assert_array_equal(pixels, original)
            self.assertTrue(np.any(result[600:840] != (15, 23, 42)))
        finally:
            display.close()


if __name__ == "__main__":
    unittest.main()
