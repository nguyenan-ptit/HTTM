"""So sánh model/imgsz/conf trên ảnh thật: thời gian và số phát hiện. Không phát âm thanh, không mở camera.

Ví dụ: python -m tools.benchmark --images a.jpg b.jpg --models yolov8n.pt yolov8s.pt --imgsz 320 640
"""

import argparse
from pathlib import Path
import time

import cv2

from prototype.detector import YoloDetector
from prototype.types import Frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", type=Path, required=True)
    parser.add_argument("--models", nargs="+", type=Path, required=True)
    parser.add_argument("--imgsz", nargs="+", type=int, default=[640])
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--darken", type=float, default=1.0, help="Nhân độ sáng ảnh (0.25 = tối) để thử cân bằng sáng")
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    images = [(path, cv2.convertScaleAbs(cv2.imread(str(path)), alpha=args.darken)) for path in args.images]
    for model in args.models:
        for imgsz in args.imgsz:
            # track=False: ảnh rời nhau, không có chuỗi thời gian.
            detector = YoloDetector(model, imgsz, args.conf, track=False, enhance=not args.no_enhance)
            detector.predict(Frame("w", 0, time.monotonic(), images[0][1]))
            times, summary = [], []
            for path, image in images:
                for i in range(args.repeat):
                    result = detector.predict(Frame("s", i, time.monotonic(), image))
                    times.append(result.inference_ms)
                labels = sorted(f"{d.label}:{d.score:.2f}" for d in result.detections)
                summary.append(f"{path.name}={len(labels)} [{' '.join(labels)}]")
            print(f"{model.name} imgsz={imgsz}: {sum(times) / len(times):.0f} ms/ảnh | " + " | ".join(summary), flush=True)


if __name__ == "__main__":
    main()
