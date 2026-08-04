"""E2E product run: Step1 SKE + Step2 local OCR on a real Douyin video."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.smart_keyframe_extractor import SmartKeyframeExtractor
from src.media_pipeline.ocr_filtering.analyze_ocr import (
    CloudOCRAnalyzer,
    export_analyze_result,
    format_timestamp_key,
    load_crop_items_from_ske_dir,
)

API_ROOT = Path(__file__).resolve().parents[1]
OUT = API_ROOT / "tmp_e2e_product"
STORAGE = API_ROOT.parents[1] / "data" / "storage"


def _find_video() -> Path:
    matches = list(STORAGE.rglob("*7657906958829468523*.mp4"))
    if not matches:
        raise FileNotFoundError("Real test video not found under data/storage")
    return matches[0]


def main() -> int:
    video = _find_video()
    if OUT.exists():
        shutil.rmtree(OUT)
    ske_dir = OUT / "step1_ske"
    ocr_dir = OUT / "step2_ocr"
    product_dir = OUT / "product_images"
    crop_gallery = product_dir / "crops_bw"
    ske_dir.mkdir(parents=True)
    ocr_dir.mkdir(parents=True)
    product_dir.mkdir(parents=True)
    crop_gallery.mkdir(parents=True)

    print(f"[1] video_id=7657906958829468523 path_ok={video.is_file()}", flush=True)
    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    dur = (nframes / fps) if fps else 0.0
    print(f"[1] meta={width}x{height} fps={fps} frames={nframes} dur_s={dur:.2f}", flush=True)

    t0 = time.perf_counter()
    extractor = SmartKeyframeExtractor()
    results = extractor.extract(video)
    print(f"[1] keyframes={len(results)} elapsed_s={time.perf_counter() - t0:.1f}", flush=True)

    summary: dict = {
        "video": str(video),
        "video_name": video.name,
        "fps": fps,
        "frame_count": nframes,
        "duration_s": dur,
        "keyframe_count": len(results),
        "keyframes": [],
    }
    for i, kf in enumerate(results):
        frame_name = f"keyframe_{i:03d}_f{kf.frame_index:06d}.jpg"
        boxed_name = f"keyframe_{i:03d}_f{kf.frame_index:06d}_boxed.jpg"
        cv2.imwrite(str(ske_dir / frame_name), kf.frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        overlay = kf.frame_bgr.copy()
        boxes_json = []
        crop_files: list[str] = []
        for j, box in enumerate(kf.boxes):
            x0, y0, x1, y1 = (
                int(round(box.x0)),
                int(round(box.y0)),
                int(round(box.x1)),
                int(round(box.y1)),
            )
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2.putText(
                overlay,
                str(j),
                (x0, max(18, y0 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )
            boxes_json.append({"x0": box.x0, "y0": box.y0, "x1": box.x1, "y1": box.y1})
            if j < len(kf.enhanced_crops):
                crop_name = f"keyframe_{i:03d}_f{kf.frame_index:06d}_crop{j:02d}.png"
                cv2.imwrite(str(ske_dir / crop_name), kf.enhanced_crops[j])
                crop_files.append(crop_name)
        cv2.imwrite(str(ske_dir / boxed_name), overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        summary["keyframes"].append(
            {
                "index": i,
                "frame_index": kf.frame_index,
                "approx_time_s": round(kf.frame_index / fps, 3) if fps else None,
                "boxes": boxes_json,
                "n_crops": len(kf.enhanced_crops),
                "frame_file": frame_name,
                "crop_files": crop_files,
                "boxed_file": boxed_name,
            }
        )
    (ske_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[1] wrote_ske={ske_dir}", flush=True)

    crops = load_crop_items_from_ske_dir(ske_dir)
    print(f"[2] crops={len(crops)} endpoint=http://127.0.0.1:8080/predict", flush=True)
    t1 = time.perf_counter()
    analyzer = CloudOCRAnalyzer(
        endpoint_url="http://127.0.0.1:8080/predict",
        concurrency=2,
        max_retries=2,
        timeout_seconds=90,
    )
    grouped = analyzer.analyze_sync(crops)
    hit_count = sum(len(v) for v in grouped.values())
    print(
        f"[2] hits={hit_count} timestamps={len(grouped)} "
        f"elapsed_s={time.perf_counter() - t1:.1f}",
        flush=True,
    )
    export_analyze_result(
        grouped,
        ocr_dir,
        meta={
            "source": str(ske_dir),
            "endpoint": analyzer.endpoint,
            "crop_count": len(crops),
        },
    )

    annotated = 0
    for kf in summary["keyframes"]:
        ts_key = format_timestamp_key(float(kf["approx_time_s"] or 0.0))
        hits = grouped.get(ts_key) or []
        boxed_path = ske_dir / kf["boxed_file"]
        shutil.copy2(boxed_path, product_dir / kf["boxed_file"])
        img = cv2.imread(str(boxed_path))
        if img is None or not hits:
            continue
        for hit in hits:
            box = hit.get("box") or []
            if len(box) < 8:
                continue
            pts = np.array(
                [
                    [box[0], box[1]],
                    [box[2], box[3]],
                    [box[4], box[5]],
                    [box[6], box[7]],
                ],
                dtype=np.int32,
            )
            cv2.polylines(img, [pts], True, (0, 0, 255), 2)
            x0, y0 = int(box[0]), int(box[1])
            # ASCII-safe label on image (Chinese may not render with Hershey).
            raw = str(hit.get("text") or "")
            label = raw.encode("ascii", "replace").decode("ascii")[:24] or "?"
            cv2.putText(
                img,
                label,
                (x0, max(24, y0 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
        out_name = f"ocr_{kf['boxed_file']}"
        cv2.imwrite(str(product_dir / out_name), img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        annotated += 1

    copied = 0
    for kf in summary["keyframes"]:
        for crop_name in kf.get("crop_files") or []:
            shutil.copy2(ske_dir / crop_name, crop_gallery / crop_name)
            copied += 1
            if copied >= 12:
                break
        if copied >= 12:
            break

    manifest = {
        "video_name": video.name,
        "duration_s": dur,
        "step1_keyframes": len(results),
        "step2_crops": len(crops),
        "step2_hits": hit_count,
        "product_dir": str(product_dir),
        "ocr_texts": {k: [h["text"] for h in v] for k, v in grouped.items()},
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[OK] product_dir={product_dir} boxed={len(list(product_dir.glob('*_boxed.jpg')))} "
        f"ocr_annot={annotated}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
