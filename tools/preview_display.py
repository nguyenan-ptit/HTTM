"""Tạo ảnh QA bằng dữ liệu tổng hợp; không camera/model/loa. Chạy từ gốc repo."""

from pathlib import Path
import time

import cv2
import numpy as np

from prototype.display import Display
from prototype.types import Detection, Frame


def main():
    image = np.full((480, 640, 3), (60, 50, 35), dtype=np.uint8)
    cv2.rectangle(image, (25, 60), (160, 420), (90, 130, 160), -1)
    cv2.rectangle(image, (240, 220), (415, 420), (120, 110, 80), -1)
    cv2.rectangle(image, (480, 75), (620, 210), (70, 60, 150), -1)
    display = Display(show_window=False)
    try:
        output = display.render(
            Frame("qa-only", 1, time.monotonic(), image),
            (Detection(0, "person", .91, (25, 60, 160, 420)),
             Detection(2, "car", .88, (240, 220, 415, 420)),
             Detection(11, "stop sign", .85, (480, 75, 620, 210))),
            camera_status="ẢNH MẪU KIỂM THỬ — chưa mở camera thật",
            model_status="Hộp bao giả để kiểm tra hiển thị, không phải kết quả YOLO",
            audio_status="Không tổng hợp được tiếng Việt. WinRT: 0x800455A0; OneCore: 0x80045040. Video và text tiếp tục.",
            narration_text="Có người ở bên trái. Có ô tô ở giữa ảnh. Có biển báo dừng ở bên phải.",
            speaking_text="", camera_fps=0, yolo_fps=0, inference_ms=None, age_ms=None)
        path = Path(".tmp/display-preview.png")
        path.parent.mkdir(exist_ok=True)
        if not cv2.imwrite(str(path), output):
            raise RuntimeError("Không lưu được ảnh QA")
        print(path)
    finally:
        display.close()


if __name__ == "__main__":
    main()
