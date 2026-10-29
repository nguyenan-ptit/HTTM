"""Vietnamese descriptions derived only from fresh, valid detections.

No speech or image processing runs here. Bounding boxes use the coordinate
system of ``result.frame.image`` after the camera's configured transforms.
"""

from __future__ import annotations

import math

from .types import DetectionResult, Narration


COCO_LABELS_VI: dict[str, str] = {
    "person": "người",
    "bicycle": "xe đạp",
    "car": "ô tô",
    "motorcycle": "xe máy",
    "airplane": "máy bay",
    "bus": "xe buýt",
    "train": "tàu hỏa",
    "truck": "xe tải",
    "boat": "thuyền",
    "traffic light": "đèn giao thông",
    "fire hydrant": "trụ nước chữa cháy",
    "stop sign": "biển báo dừng",
    "parking meter": "máy thu phí đỗ xe",
    "bench": "ghế băng",
    "bird": "chim",
    "cat": "mèo",
    "dog": "chó",
    "horse": "ngựa",
    "sheep": "cừu",
    "cow": "bò",
    "elephant": "voi",
    "bear": "gấu",
    "zebra": "ngựa vằn",
    "giraffe": "hươu cao cổ",
    "backpack": "ba lô",
    "umbrella": "ô che",
    "handbag": "túi xách",
    "tie": "cà vạt",
    "suitcase": "va li",
    "frisbee": "đĩa ném",
    "skis": "ván trượt tuyết đôi",
    "snowboard": "ván trượt tuyết đơn",
    "sports ball": "bóng thể thao",
    "kite": "diều",
    "baseball bat": "gậy bóng chày",
    "baseball glove": "găng tay bóng chày",
    "skateboard": "ván trượt",
    "surfboard": "ván lướt sóng",
    "tennis racket": "vợt quần vợt",
    "bottle": "chai",
    "wine glass": "ly rượu vang",
    "cup": "cốc",
    "fork": "nĩa",
    "knife": "dao",
    "spoon": "thìa",
    "bowl": "bát",
    "banana": "chuối",
    "apple": "táo",
    "sandwich": "bánh mì kẹp",
    "orange": "cam",
    "broccoli": "bông cải xanh",
    "carrot": "cà rốt",
    "hot dog": "bánh mì kẹp xúc xích",
    "pizza": "bánh pizza",
    "donut": "bánh vòng",
    "cake": "bánh ngọt",
    "chair": "ghế",
    "couch": "ghế sofa",
    "potted plant": "chậu cây",
    "bed": "giường",
    "dining table": "bàn ăn",
    "toilet": "bồn cầu",
    "tv": "ti vi",
    "laptop": "máy tính xách tay",
    "mouse": "chuột máy tính",
    "remote": "điều khiển từ xa",
    "keyboard": "bàn phím",
    "cell phone": "điện thoại di động",
    "microwave": "lò vi sóng",
    "oven": "lò nướng",
    "toaster": "máy nướng bánh mì",
    "sink": "bồn rửa",
    "refrigerator": "tủ lạnh",
    "book": "sách",
    "clock": "đồng hồ",
    "vase": "bình hoa",
    "scissors": "kéo",
    "teddy bear": "gấu bông",
    "hair drier": "máy sấy tóc",
    "toothbrush": "bàn chải đánh răng",
}

UNKNOWN_LABEL_VI = "vật thể không rõ loại"
NEAR_AREA = 0.2  # Hộp chiếm ≥20% ảnh thì nói "có vẻ gần"; chỉ là gợi ý theo cỡ hộp, không phải khoảng cách đo.
_VEHICLES = frozenset(
    {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
)
_SIGNS = frozenset({"traffic light", "stop sign"})
_POSITION_TEXT = {
    "left": "ở bên trái",
    "center": "ở giữa ảnh",
    "right": "ở bên phải",
}
_POSITION_ORDER = {"left": 0, "center": 1, "right": 2}


def _canonical_label(label: str) -> str:
    return " ".join(label.casefold().replace("_", " ").split())


def label_vi(label: str) -> str:
    """Translate a supported model label without inventing a new detector class."""
    return COCO_LABELS_VI.get(_canonical_label(label), UNKNOWN_LABEL_VI)


def _priority(label: str) -> int:
    if label == "person":
        return 0
    if label in _VEHICLES:
        return 1
    if label in _SIGNS:
        return 2
    return 3


def narrate(
    result: DetectionResult,
    *,
    session_id: str,
    now: float,
    min_confidence: float = 0.45,
    max_age: float = 2.0,
    max_groups: int = 3,
    max_chars: int = 180,
) -> Narration | None:
    """Build complete Vietnamese sentences and preserve their source context.

    ``now`` and ``frame.captured_at`` must use the same monotonic clock.
    Empty/expired/failed results produce no description; absence of detection
    never becomes a claim that the path is safe. Invalid configuration raises
    ``ValueError``. Individual invalid detections are ignored.
    """
    if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence phải nằm trong khoảng [0, 1].")
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("max_age phải là số hữu hạn lớn hơn 0.")
    if max_groups < 1 or max_chars < 1:
        raise ValueError("max_groups và max_chars phải lớn hơn 0.")

    frame = result.frame
    if result.error is not None or frame.session_id != session_id:
        return None
    if not math.isfinite(now) or not math.isfinite(frame.captured_at):
        return None
    age = now - frame.captured_at
    if not 0 <= age < max_age:
        return None
    width, height = frame.width, frame.height
    if width <= 0 or height <= 0:
        return None

    # A group holds the best confidence, rather than a count: multiple boxes
    # do not prove how many physical objects exist.
    grouped: dict[tuple[str, str], float] = {}
    near: set[tuple[str, str]] = set()
    for detection in result.detections:
        if not math.isfinite(detection.score) or not min_confidence <= detection.score <= 1:
            continue
        if len(detection.bbox) != 4 or not all(math.isfinite(v) for v in detection.bbox):
            continue
        x1, y1, x2, y2 = detection.bbox
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            continue
        center_x = (x1 + x2) / 2
        position = "left" if center_x < width / 3 else (
            "right" if center_x >= 2 * width / 3 else "center"
        )
        key = (_canonical_label(detection.label), position)
        grouped[key] = max(grouped.get(key, 0), detection.score)
        if (x2 - x1) * (y2 - y1) >= NEAR_AREA * width * height:
            near.add(key)

    # Mỗi nhãn một lượt chọn: nhiều người ở nhiều vị trí không được chiếm hết chỗ của đồ vật khác.
    # Vật có vẻ gần được đọc trước, rồi theo ưu tiên và độ tin cậy.
    labels: dict[str, list[str]] = {}
    for key in grouped:
        labels.setdefault(key[0], []).append(key[1])
    ranked = sorted(
        labels,
        key=lambda label: (
            not any((label, pos) in near for pos in labels[label]), _priority(label),
            -max(grouped[(label, pos)] for pos in labels[label]), label,
        ),
    )

    def phrase(label: str, positions: list[str], suffix: str = "") -> str:
        parts = [_POSITION_TEXT[pos] for pos in sorted(positions, key=_POSITION_ORDER.get)]
        where = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " và " + parts[-1]
        return f"Có {label_vi(label)} {where}{suffix}."

    selected: list[tuple[str, str]] = []
    sentences: list[str] = []
    chosen = 0
    for label in ranked:
        # Một câu mỗi nhãn cho ngắn; "có vẻ gần" nếu bất kỳ vị trí nào của nhãn đó có hộp lớn.
        close = any((label, pos) in near for pos in labels[label])
        new = [phrase(label, labels[label], ", có vẻ gần" if close else "")]
        candidate = " ".join([*sentences, *new])
        if len(candidate) > max_chars:
            continue
        selected.extend((label, pos) for pos in labels[label])
        sentences.extend(new)
        chosen += 1
        if chosen == max_groups:
            break
    if not selected:
        return None

    # Canonical order gives the same dedup key to the same set of groups even
    # when confidence ordering changes between otherwise equivalent frames.
    groups = tuple(
        f"{label}:{position}"
        for label, position in sorted(
            selected, key=lambda key: (_priority(key[0]), key[0], _POSITION_ORDER[key[1]])
        )
    )
    return Narration(
        text=" ".join(sentences),
        groups=groups,
        session_id=frame.session_id,
        frame_id=frame.frame_id,
        source_captured_at=frame.captured_at,
        expires_at=frame.captured_at + max_age,
    )
