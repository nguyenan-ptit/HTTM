import hashlib
import contextlib
import io
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from prototype.model_tools import download_model, main, sha256_file


class ModelToolsTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(__file__).resolve().parents[1] / ".tmp" / ("model-test-" + uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
        self.output = self.directory / "model.pt"
        self.manifest = self.directory / "manifest.json"
        # Dữ liệu giả chỉ để thử tải/checksum, không bao giờ nạp làm model.
        self.payload = b"synthetic-model-tool-test\0" * 50000

    def tearDown(self):
        allowed = Path(__file__).resolve().parents[1] / ".tmp"
        if not self.directory.resolve().is_relative_to(allowed.resolve()):
            raise RuntimeError("Từ chối xóa ngoài thư mục tạm kiểm thử")
        shutil.rmtree(self.directory)

    def test_download_records_real_digest_and_fixed_provenance(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(self.payload)):
            record = download_model(self.output, self.manifest)
        self.assertEqual(sha256_file(self.output), hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(record["sha256"], json.loads(self.manifest.read_text(encoding="utf-8"))["sha256"])
        self.assertEqual(record["checksum_verification"], "measured-after-download")
        self.assertIn("/ultralytics/assets/releases/download/v8.3.0/", record["source"])

    def test_mismatched_hash_never_publishes_model(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(self.payload)):
            with self.assertRaises(ValueError):
                download_model(self.output, self.manifest, "0" * 64)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.output.with_suffix(".pt.partial").exists())

    def test_existing_model_never_overwritten(self):
        self.output.write_bytes(b"user model")
        with self.assertRaises(FileExistsError):
            download_model(self.output, self.manifest)
        self.assertEqual(self.output.read_bytes(), b"user model")

    def test_manifest_cannot_alias_model_or_partial(self):
        for alias in (self.output, self.output.with_suffix(".pt.partial")):
            with patch("urllib.request.urlopen") as network:
                with self.assertRaises(ValueError):
                    download_model(self.output, alias)
                network.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_existing_manifest_and_partial_are_preserved(self):
        self.manifest.write_text("user manifest", encoding="utf-8")
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(FileExistsError):
                download_model(self.output, self.manifest)
            network.assert_not_called()
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), "user manifest")
        self.manifest.unlink()
        partial = self.output.with_suffix(".pt.partial")
        partial.write_bytes(b"other download")
        with self.assertRaises(FileExistsError):
            download_model(self.output, self.manifest)
        self.assertEqual(partial.read_bytes(), b"other download")

    def test_partial_created_by_other_process_is_not_removed(self):
        partial = self.output.with_suffix(".pt.partial")
        original_open = Path.open

        def racing_open(path, mode="r", *args, **kwargs):
            if path == partial and mode == "xb":
                with original_open(path, "wb") as handle:
                    handle.write(b"other process")
                raise FileExistsError("Created by another download")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", racing_open):
            with self.assertRaises(FileExistsError):
                download_model(self.output, self.manifest)
        self.assertEqual(partial.read_bytes(), b"other process")

    def test_classes_uses_actual_model_names_and_translates_without_adding_classes(self):
        self.output.write_bytes(b"synthetic file; detector is mocked")
        fake_detector = type("FakeDetector", (), {"class_names": {0: "person", 11: "custom sign"}})()
        output = io.StringIO()
        with patch("prototype.detector.YoloDetector", return_value=fake_detector), contextlib.redirect_stdout(output):
            self.assertEqual(main(["--classes", str(self.output)]), 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["classes"][0]["label_vi"], "người")
        self.assertFalse(record["baseline_labels"]["stop sign"])
        self.assertEqual(record["classes"][1]["label"], "custom sign")


if __name__ == "__main__":
    unittest.main()
