"""QA dump for authority product final video."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import cv2

from src.media_pipeline.translator.normalize import flatten_ocr_chinese

ROOT = Path(__file__).resolve().parents[1] / "tmp_e2e_authority_product"
VID = ROOT / "final_complete.mp4"
AUTH = json.loads((ROOT / "ocr_authority.json").read_text(encoding="utf-8"))
VI = json.loads((ROOT / "vi_texts.json").read_text(encoding="utf-8"))


def main() -> None:
    cap = cv2.VideoCapture(str(VID))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    print(f"video {w}x{h} fps={fps} frames={n} size={VID.stat().st_size}")

    qa = ROOT / "qa_frames"
    qa.mkdir(exist_ok=True)
    times_ms = [0, 1167, 2000, 2500, 5000, 10333, 18500, 23833, 27500]
    for t in times_ms:
        idx = int(round(t / 1000.0 * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if not ok:
            continue
        out = qa / f"t{t:05d}.jpg"
        cv2.imwrite(str(out), fr)
        nearest = min(AUTH["frames"], key=lambda f: abs(int(f.get("time_ms") or 0) - t))
        boxes = nearest.get("boxes") or []
        print(
            f"t={t} auth_ms={nearest.get('time_ms')} "
            f"state={nearest.get('frame_state')} boxes={len(boxes)}"
        )
        for b in boxes[:8]:
            text = str(b.get("text") or "")[:40]
            print(
                " ",
                repr(text),
                "xywh",
                round(float(b.get("x") or 0), 3),
                round(float(b.get("y") or 0), 3),
                round(float(b.get("w") or 0), 3),
                round(float(b.get("h") or 0), 3),
                "cover",
                b.get("cover_bounds") is not None,
                "cover_only",
                bool(b.get("cover_only")),
            )
    cap.release()

    vals = list(VI.values())
    print(
        "vi",
        len(vals),
        "ellipsis",
        sum(1 for v in vals if v == "..."),
        "real",
        sum(1 for v in vals if v not in ("...", "")),
    )
    flat = flatten_ocr_chinese(AUTH)
    miss = [(k, zh) for k, zh in flat.items() if VI.get(k, "...") in ("...", "")]
    print("missing unique zh", len({zh for _, zh in miss}))
    print(Counter(zh for _, zh in miss).most_common(20))

    frames = AUTH["frames"]
    nonempty = [f for f in frames if f.get("boxes")]
    print("frames", len(frames), "nonempty", len(nonempty))
    streak = 0
    maxs = 0
    for f in frames:
        if not f.get("boxes"):
            streak += 1
            maxs = max(maxs, streak)
        else:
            streak = 0
    print("max blank streak frames", maxs)

    # Overlay segment count / dense_ui
    from src.media_pipeline.video_renderer.overlays import overlays_from_ocr_payload

    overlays = overlays_from_ocr_payload(AUTH, VI, hold_ms=500)
    kinds = Counter(o.kind for o in overlays)
    with_vi = sum(1 for o in overlays if (o.text_vi or "").strip())
    print("overlays", len(overlays), "kinds", dict(kinds), "with_vi", with_vi)


if __name__ == "__main__":
    main()
