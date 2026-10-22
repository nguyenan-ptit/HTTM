"""Contract tests use invented boxes, not claims about real model accuracy."""

import math
import unittest
from types import SimpleNamespace

from prototype.narration import COCO_LABELS_VI, UNKNOWN_LABEL_VI, label_vi, narrate
from prototype.types import Detection, DetectionResult, Frame


def make_result(detections=(), *, session_id="camera-a", captured_at=10.0, error=None):
    image = SimpleNamespace(shape=(300, 900, 3))
    frame = Frame(session_id, 7, captured_at, image)
    return DetectionResult(frame, tuple(detections), 20.0, 10.02, error)


def detect(label="person", bbox=(0, 0, 100, 100), score=0.9, class_id=0):
    return Detection(class_id, label, score, bbox)


class NarrationTests(unittest.TestCase):
    def narrate(self, result, **kwargs):
        return narrate(result, session_id="camera-a", now=10.1, **kwargs)

    def test_all_eighty_coco_labels_have_vietnamese_translation(self):
        self.assertEqual(len(COCO_LABELS_VI), 80)
        self.assertTrue(all(value and value != UNKNOWN_LABEL_VI for value in COCO_LABELS_VI.values()))
        self.assertEqual(label_vi("person"), "người")
        self.assertEqual(label_vi("car"), "ô tô")
        self.assertEqual(label_vi("stop sign"), "biển báo dừng")
        self.assertEqual(label_vi(" TRAFFIC_LIGHT "), "đèn giao thông")

    def test_describes_left_center_and_right_in_original_frame_coordinates(self):
        cases = [
            ((0, 0, 100, 100), "Có người ở bên trái.", "person:left"),
            ((350, 0, 550, 100), "Có người ở giữa ảnh.", "person:center"),
            ((800, 0, 900, 100), "Có người ở bên phải.", "person:right"),
        ]
        for bbox, text, group in cases:
            with self.subTest(bbox=bbox):
                description = self.narrate(make_result([detect(bbox=bbox)]))
                self.assertIsNotNone(description)
                self.assertEqual(description.text, text)
                self.assertEqual(description.groups, (group,))

    def test_boundaries_are_center_then_right(self):
        result = make_result([
            detect(bbox=(250, 0, 350, 100)),
            detect(bbox=(550, 0, 650, 100)),
        ])
        self.assertEqual(self.narrate(result).groups, ("person:center", "person:right"))

    def test_groups_duplicates_without_claiming_object_count(self):
        result = make_result([detect(), detect(bbox=(110, 0, 210, 100))])
        description = self.narrate(result)
        self.assertEqual(description.text, "Có người ở bên trái.")
        self.assertEqual(description.groups, ("person:left",))

    def test_empty_or_low_confidence_produces_no_safe_path_claim(self):
        self.assertIsNone(self.narrate(make_result()))
        self.assertIsNone(self.narrate(make_result([detect(score=0.44)])))
        self.assertIsNotNone(self.narrate(make_result([detect(score=0.45)])))

    def test_unknown_class_has_explicit_generic_description(self):
        description = self.narrate(make_result([detect(label="custom object", class_id=200)]))
        self.assertEqual(description.text, "Có vật thể chưa có bản dịch ở bên trái.")
        self.assertEqual(label_vi(""), UNKNOWN_LABEL_VI)

    def test_uses_labels_instead_of_assuming_custom_class_ids_are_coco(self):
        description = self.narrate(make_result([detect(label="car", class_id=0)]))
        self.assertEqual(description.text, "Có ô tô ở bên trái.")

    def test_rejects_other_session_stale_future_and_failed_frames(self):
        for result in [
            make_result([detect()], session_id="camera-b"),
            make_result([detect()], captured_at=8.1),
            make_result([detect()], captured_at=10.2),
            make_result([detect()], captured_at=math.nan),
            make_result([detect()], error="model error"),
        ]:
            with self.subTest(result=result):
                self.assertIsNone(self.narrate(result))

    def test_expiry_is_based_on_source_frame_not_inference_completion(self):
        description = self.narrate(make_result([detect()]), max_age=2)
        self.assertEqual(description.source_captured_at, 10.0)
        self.assertEqual(description.expires_at, 12.0)
        self.assertEqual(description.session_id, "camera-a")
        self.assertEqual(description.frame_id, 7)

    def test_invalid_scores_and_boxes_are_ignored(self):
        invalid = [
            detect(score=math.nan), detect(score=math.inf), detect(score=1.1),
            detect(bbox=(0, 0, 0, 100)), detect(bbox=(100, 0, 0, 100)),
            detect(bbox=(-1, 0, 100, 100)), detect(bbox=(0, 0, 901, 100)),
            detect(bbox=(0, 0, 100, 301)), detect(bbox=(0, math.nan, 100, 100)),
        ]
        self.assertIsNone(self.narrate(make_result(invalid)))
        self.assertEqual(self.narrate(make_result([*invalid, detect()])).groups, ("person:left",))

    def test_prioritizes_people_vehicles_and_signs_with_group_limit(self):
        result = make_result([
            detect("chair", score=0.99), detect("stop sign", score=0.8),
            detect("car", score=0.8), detect("person", score=0.6),
        ])
        description = self.narrate(result, max_groups=3)
        self.assertEqual(description.groups, ("person:left", "car:left", "stop sign:left"))
        self.assertNotIn("ghế", description.text)

    def test_length_limit_keeps_complete_sentences_and_matching_groups(self):
        result = make_result([detect(), detect("car")])
        description = self.narrate(result, max_chars=len("Có người ở bên trái."))
        self.assertEqual(description.text, "Có người ở bên trái.")
        self.assertEqual(description.groups, ("person:left",))
        self.assertIsNone(self.narrate(result, max_chars=1))

    def test_dedup_key_does_not_depend_on_detector_order_or_confidence_order(self):
        first = self.narrate(make_result([detect("car", score=0.9), detect("bus", score=0.8)]))
        second = self.narrate(make_result([detect("bus", score=0.95), detect("car", score=0.7)]))
        self.assertEqual(first.dedup_key, second.dedup_key)

    def test_configuration_errors_are_explicit(self):
        for kwargs in [
            {"min_confidence": -0.1}, {"min_confidence": math.nan},
            {"max_age": 0}, {"max_age": math.inf}, {"max_groups": 0}, {"max_chars": 0},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.narrate(make_result(), **kwargs)


if __name__ == "__main__":
    unittest.main()
