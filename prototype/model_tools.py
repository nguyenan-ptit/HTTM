"""Tải model rõ ràng từ release cố định và ghi checksum, không tải trong vòng camera."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
LICENSE_URL = "https://www.ultralytics.com/license"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_model(output: Path, manifest: Path, expected_sha256: str | None = None) -> dict:
    partial = output.with_suffix(output.suffix + ".partial")
    if manifest.resolve() in (output.resolve(), partial.resolve()):
        raise ValueError("Đường dẫn manifest phải khác model và tệp .partial.")
    if output.exists():
        raise FileExistsError("Tệp model đã tồn tại; không ghi đè. Dùng --inspect để kiểm tra.")
    if manifest.exists():
        raise FileExistsError("Manifest đã tồn tại; chọn đường dẫn mới, không ghi đè thông tin model cũ.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if partial.exists():
        raise FileExistsError("Có tệp .partial từ lần trước; kiểm tra tệp đó trước khi tải lại.")
    owns_partial = False
    owns_output = False
    try:
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "HTTM2-prototype/0.1"})
        with partial.open("xb") as handle:
            owns_partial = True
            with urllib.request.urlopen(request, timeout=30) as response:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > 50 * 1024 * 1024:
                        raise ValueError("Tệp vượt giới hạn 50 MiB cho YOLOv8n.")
                    handle.write(block)
        if size < 1024 * 1024:
            raise ValueError("Tệp tải về quá nhỏ; có thể không phải model YOLOv8n.")
        digest = sha256_file(partial)
        if expected_sha256 and digest != expected_sha256.lower():
            raise ValueError("Checksum khác SHA-256 mong đợi; không sử dụng tệp tải về.")
        # Exclusive creation also protects a file created by another process
        # after the initial existence check, on Windows and other platforms.
        with output.open("xb") as target:
            owns_output = True
            with partial.open("rb") as source:
                shutil.copyfileobj(source, target)
    except BaseException:
        if owns_output and output.is_file():
            output.unlink()
        raise
    finally:
        if owns_partial and partial.is_file():
            partial.unlink()
    record = {
        "model": "YOLOv8n", "task": "detect", "dataset": "COCO (80 lớp)",
        "source": MODEL_URL, "release": "v8.3.0", "file": str(output),
        "size_bytes": size, "sha256": digest,
        "checksum_verification": "compared-to-user-supplied-digest" if expected_sha256 else "measured-after-download",
        "license": "Ultralytics AGPL-3.0 hoặc Enterprise; xem điều kiện tại nguồn",
        "license_url": LICENSE_URL,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chuẩn bị và kiểm tra model YOLOv8n cục bộ.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--download", action="store_true", help="Tải model từ release Ultralytics cố định")
    mode.add_argument("--inspect", type=Path, metavar="FILE", help="Tính SHA-256; không nạp pickle/model")
    mode.add_argument("--classes", type=Path, metavar="FILE", help="Nạp model .pt tin cậy cục bộ để kiểm kê lớp thực tế")
    parser.add_argument("--output", type=Path, default=Path("yolov8n.pt"), help="Tệp model sẽ tải")
    parser.add_argument("--manifest", type=Path, default=Path("models/manifest.json"))
    parser.add_argument("--sha256", help="SHA-256 mong đợi từ nguồn đáng tin cậy, nếu có")
    args = parser.parse_args(argv)
    if args.sha256 and (len(args.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in args.sha256)):
        parser.error("--sha256 phải gồm 64 ký tự hex.")
    try:
        if args.download:
            record = download_model(args.output, args.manifest, args.sha256)
        elif args.classes:
            if args.sha256 and sha256_file(args.classes) != args.sha256.lower():
                raise ValueError("Checksum khác SHA-256 mong đợi; không nạp model.")
            from .detector import YoloDetector
            from .narration import label_vi
            names = YoloDetector(args.classes).class_names
            record = {"file": str(args.classes), "sha256": sha256_file(args.classes),
                      "classes": [{"class_id": class_id, "label": label, "label_vi": label_vi(label)}
                                  for class_id, label in sorted(names.items())],
                      "baseline_labels": {label: label in names.values() for label in ("stop sign", "traffic light")},
                      "evaluation": "Chỉ kiểm kê lớp; chưa đánh giá độ chính xác hoặc màu đèn."}
        else:
            digest = sha256_file(args.inspect)
            record = {"file": str(args.inspect), "sha256": digest,
                      "size_bytes": args.inspect.stat().st_size,
                      "provenance": "Chưa xác minh nguồn chỉ bằng checksum cục bộ."}
            if args.sha256:
                record["matches_expected"] = digest == args.sha256.lower()
                if not record["matches_expected"]:
                    print(json.dumps(record, ensure_ascii=False, indent=2))
                    return 1
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Không chuẩn bị được model ({type(exc).__name__}). Kiểm tra kết nối, quyền ghi và README.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
