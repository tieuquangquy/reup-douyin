"""Local smoke: PaddleOCR detect_frame must not crash oneDNN."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_onednn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"

from PIL import Image, ImageDraw

from src.ocr_pipeline.providers import PaddleOcrProvider


def main() -> None:
    img = Image.new("RGB", (640, 360), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 280, 600, 340), fill=(0, 0, 0))
    draw.text((60, 295), "OCR smoke 字幕", fill=(255, 255, 255))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "frame.jpg"
        img.save(path, quality=95)
        provider = PaddleOcrProvider()
        result = provider.detect_frame(path, frame_time_ms=0)
        print("OK boxes=", len(result.boxes))
        for box in result.boxes[:8]:
            print(f"  y={box.y:.3f} h={box.height:.3f} text={box.text!r} conf={box.confidence:.3f}")


if __name__ == "__main__":
    main()
