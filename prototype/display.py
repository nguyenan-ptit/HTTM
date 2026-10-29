"""Hiển thị Unicode tiếng Việt bằng Pillow; không gọi model hoặc TTS."""

import os
from pathlib import Path


def find_font(explicit: str | None = None) -> str:
    candidates = ([explicit] if explicit else []) + [
        str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"),
        str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    if explicit and not Path(explicit).is_file():
        raise FileNotFoundError("Không tìm thấy tệp --font.")
    for path in candidates:
        if Path(path).is_file():
            return path
    raise FileNotFoundError("Không tìm thấy phông Unicode. Chọn tệp .ttf hỗ trợ tiếng Việt bằng --font.")


class Display:
    window = "HTTM2 - Camera YOLO"

    def __init__(self, font_path=None, *, show_window=True):
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        self.cv2, self.np = cv2, np
        self.Image, self.ImageDraw = Image, ImageDraw
        font_path = find_font(font_path)
        self.font = ImageFont.truetype(font_path, 22)
        self.small = ImageFont.truetype(font_path, 18)
        self.title = ImageFont.truetype(font_path, 26)
        self.width, self.video_height = 960, 540
        self.show_window = show_window
        if show_window:
            cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window, self.width, 900)

    def _wrapped(self, draw, text, x, y, *, width, font, fill, lines=3):
        row, rows = "", []
        for word in text.split():
            candidate = (row + " " + word).strip()
            if row and draw.textlength(candidate, font=font) > width:
                rows.append(row)
                row = word
            else:
                row = candidate
        if row:
            rows.append(row)
        if len(rows) > lines:
            rows = rows[:lines]
            rows[-1] = rows[-1][:max(1, len(rows[-1]) - 2)] + "…"
        for row in rows:
            draw.text((x, y), row, fill=fill, font=font)
            y += 29
        return y

    def render(self, frame, detections, *, camera_status, model_status, audio_status,
               narration_text, speaking_text, camera_fps, yolo_fps, inference_ms, age_ms):
        canvas = self.Image.new("RGB", (self.width, 900), (15, 23, 42))
        draw = self.ImageDraw.Draw(canvas)
        draw.text((16, 8), "Nhận diện và mô tả vật thể", font=self.title, fill="white")
        if frame is not None:
            rgb = self.cv2.cvtColor(frame.image, self.cv2.COLOR_BGR2RGB)
            video = self.Image.fromarray(rgb)
            scale = min(self.width / frame.width, self.video_height / frame.height)
            vw, vh = int(frame.width * scale), int(frame.height * scale)
            left, top = (self.width - vw) // 2, 50 + (self.video_height - vh) // 2
            canvas.paste(video.resize((vw, vh)), (left, top))
            from .narration import label_vi
            for detection in detections:
                x1, y1, x2, y2 = detection.bbox
                box = (left + x1 * scale, top + y1 * scale,
                       left + x2 * scale, top + y2 * scale)
                draw.rectangle(box, outline=(52, 211, 153), width=3)
                label = f"{label_vi(detection.label)} {detection.score:.0%}"
                tx, ty = box[0], max(top, box[1] - 26)
                tw = draw.textlength(label, font=self.small)
                tx = max(left, min(tx, left + vw - tw - 8))
                draw.rectangle((tx, ty, tx + tw + 8, ty + 26), fill=(4, 50, 40))
                draw.text((tx + 4, ty), label, font=self.small, fill="white")
        else:
            draw.text((220, 280), "Đang chờ dữ liệu camera còn mới", font=self.title, fill=(251, 191, 36))
        y = 600
        draw.text((16, y), f"Camera: {camera_status}", font=self.small, fill="white")
        y += 25
        draw.text((16, y), f"Model: {model_status}", font=self.small, fill="white")
        y += 25
        y = self._wrapped(draw, "Âm thanh: " + audio_status, 16, y, width=928,
                          font=self.small, fill=(147, 197, 253), lines=2)
        y = self._wrapped(draw, "Mô tả: " + narration_text, 16, y, width=928,
                          font=self.font, fill="white", lines=2)
        if speaking_text:
            y = self._wrapped(draw, "Đang gửi TTS: " + speaking_text, 16, y, width=928,
                              font=self.small, fill=(110, 231, 183), lines=2)
        inference = f"{inference_ms:.0f} ms" if inference_ms is not None else "—"
        age = f"{age_ms:.0f} ms" if age_ms is not None else "—"
        draw.rectangle((0, 842, 960, 900), fill=(30, 41, 59))
        draw.text((16, 845), f"Camera {camera_fps:.1f} FPS | YOLO {yolo_fps:.1f} FPS | Inference {inference} | Tuổi ảnh {age}",
                  font=self.small, fill="white")
        draw.text((16, 872), "m: bật/tắt tiếng    q: thoát    Vị trí được mô tả theo ảnh hiển thị.",
                  font=self.small, fill="white")
        output = self.cv2.cvtColor(self.np.asarray(canvas), self.cv2.COLOR_RGB2BGR)
        if self.show_window:
            self.cv2.imshow(self.window, output)
        return output

    def key(self):
        key = self.cv2.waitKey(15) & 0xFF
        if self.cv2.getWindowProperty(self.window, self.cv2.WND_PROP_VISIBLE) < 1:
            return ord("q")
        return key

    def close(self):
        if self.show_window:
            self.cv2.destroyAllWindows()
