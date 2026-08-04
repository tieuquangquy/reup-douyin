"""Step 4: ROI Telea inpaint cleaner + professional ASS subtitles.

Input: source video + Step-3 JSON
  ``{ "MM:SS.mmm": [ {original_box_coords, original_text, vietnamese_text}, ... ] }``

Output: ``cleaned_video.mp4`` (Chinese removed) + ``vietnamese_sub.ass`` (not burned in).

Does **not** replace production ``render_video_single_pass`` (blur-cover + Pillow VI).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)

DEFAULT_HOLD_S = 2.0
ROI_PAD_PX = 10
DILATE_KERNEL = np.ones((5, 5), dtype=np.uint8)
MISSING_VI = "..."
_TS_RE = re.compile(
    r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?$|^(\d+)(?:\.(\d{1,3}))?$"
)


@dataclass(frozen=True)
class TimedBoxEvent:
    start_ms: int
    end_ms: int
    xyxy: tuple[int, int, int, int]  # x0,y0,x1,y1 in pixels (after resolve)
    vietnamese_text: str
    original_text: str = ""
    # Raw coords before pixel resolve (may be normalized); resolved in process()
    raw_coords: tuple[float, ...] = ()


def parse_timestamp_to_ms(key: str) -> int:
    """Parse ``MM:SS.mmm``, ``H:MM:SS.mm``, or bare seconds → milliseconds."""
    raw = str(key or "").strip()
    if not raw:
        return 0
    m = _TS_RE.match(raw)
    if not m:
        try:
            return int(round(float(raw) * 1000.0))
        except ValueError:
            return 0
    if m.group(5) is not None:
        sec = int(m.group(5))
        frac = (m.group(6) or "0").ljust(3, "0")[:3]
        return sec * 1000 + int(frac)
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    frac = (m.group(4) or "0").ljust(3, "0")[:3]
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + int(frac)


def ms_to_ass_time(ms: int) -> str:
    """ASS time ``H:MM:SS.cs`` (centiseconds)."""
    ms = max(0, int(ms))
    cs_total = ms // 10
    cs = cs_total % 100
    s_total = cs_total // 100
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def quad_or_xyxy_to_xyxy(coords: Sequence[float]) -> tuple[float, float, float, float]:
    vals = [float(v) for v in coords]
    if len(vals) >= 8:
        xs = vals[0:8:2]
        ys = vals[1:8:2]
        return min(xs), min(ys), max(xs), max(ys)
    if len(vals) >= 4:
        x0, y0, x1, y1 = vals[0], vals[1], vals[2], vals[3]
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    return 0.0, 0.0, 0.0, 0.0


def coords_look_normalized(coords: Sequence[float]) -> bool:
    vals = [float(v) for v in coords]
    if not vals:
        return False
    return max(abs(v) for v in vals) <= 1.5


def resolve_xyxy_pixels(
    coords: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = quad_or_xyxy_to_xyxy(coords)
    if coords_look_normalized(coords):
        x0 *= frame_w
        x1 *= frame_w
        y0 *= frame_h
        y1 *= frame_h
    ix0 = int(max(0, min(frame_w - 1, round(x0))))
    iy0 = int(max(0, min(frame_h - 1, round(y0))))
    ix1 = int(max(ix0 + 1, min(frame_w, round(x1))))
    iy1 = int(max(iy0 + 1, min(frame_h, round(y1))))
    return ix0, iy0, ix1, iy1


def parse_step3_events(
    step3: Mapping[str, Any],
    *,
    default_hold_s: float = DEFAULT_HOLD_S,
    video_duration_s: float | None = None,
) -> list[TimedBoxEvent]:
    """
    Flatten Step-3 JSON into timed box events.

    End = ``min(next_timestamp, start + hold)``, never stretched across a long gap
    (that caused wrong VI to stick on later scenes).
    """
    hold_ms = max(100, int(round(float(default_hold_s) * 1000.0)))
    duration_ms = (
        int(round(float(video_duration_s) * 1000.0))
        if video_duration_s is not None and video_duration_s > 0
        else None
    )

    stamped: list[tuple[int, str, list[Any]]] = []
    for key, hits in step3.items():
        if not isinstance(hits, list):
            continue
        stamped.append((parse_timestamp_to_ms(str(key)), str(key), hits))
    stamped.sort(key=lambda row: row[0])

    events: list[TimedBoxEvent] = []
    for idx, (start_ms, _key, hits) in enumerate(stamped):
        hold_end = start_ms + hold_ms
        if idx + 1 < len(stamped):
            end_ms = min(stamped[idx + 1][0], hold_end)
        else:
            end_ms = hold_end
        if end_ms <= start_ms:
            end_ms = hold_end
        if duration_ms is not None:
            end_ms = min(end_ms, duration_ms)
            if end_ms <= start_ms:
                continue

        for hit in hits:
            if not isinstance(hit, Mapping):
                continue
            coords = hit.get("original_box_coords") or hit.get("box") or []
            if not isinstance(coords, (list, tuple)) or len(coords) < 4:
                continue
            vi = str(hit.get("vietnamese_text") or "").strip() or MISSING_VI
            zh = str(hit.get("original_text") or hit.get("text") or "").strip()
            raw = tuple(float(v) for v in coords)
            x0, y0, x1, y1 = quad_or_xyxy_to_xyxy(raw)
            # Placeholder pixel box; process() re-resolves with frame size.
            events.append(
                TimedBoxEvent(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    xyxy=(int(x0), int(y0), int(max(x0 + 1, x1)), int(max(y0 + 1, y1))),
                    vietnamese_text=vi,
                    original_text=zh,
                    raw_coords=raw,
                )
            )
    return events


def is_burnable_vi_text(text: str) -> bool:
    """False for dry-map leftovers / placeholders that must not appear on video."""
    raw = str(text or "").strip()
    if not raw or raw == MISSING_VI:
        return False
    if raw.startswith("[vi]"):
        return False
    if raw.startswith("[") and raw.endswith("]"):
        return False
    return True


def escape_ass_text(text: str) -> str:
    out = str(text or "")
    out = out.replace("\\", r"\\")
    out = out.replace("{", r"\{").replace("}", r"\}")
    out = out.replace("\n", r"\N")
    return out


def write_ass(
    events: Sequence[TimedBoxEvent],
    *,
    video_w: int,
    video_h: int,
    path: str | Path,
    style_name: str = "ReupVI",
) -> Path:
    """Write ASS with white fill, black outline+shadow; skip dry ``[vi]`` junk."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Fontsize 36 + Alignment=2 (bottom-center) — less edge clipping than center@48.
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {int(video_w)}\n"
        f"PlayResY: {int(video_h)}\n"
        "YCbCr Matrix: None\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: {style_name},Arial,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]
    margin = 48
    for ev in events:
        if not is_burnable_vi_text(ev.vietnamese_text):
            continue
        x0, y0, x1, y1 = ev.xyxy
        if ev.raw_coords:
            x0, y0, x1, y1 = resolve_xyxy_pixels(
                ev.raw_coords, frame_w=video_w, frame_h=video_h
            )
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2
        cx = int(max(margin, min(video_w - margin, cx)))
        cy = int(max(margin, min(video_h - margin, cy)))
        text = escape_ass_text(ev.vietnamese_text)
        start = ms_to_ass_time(ev.start_ms)
        end = ms_to_ass_time(ev.end_ms)
        lines.append(
            f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,"
            f"{{\\an5\\pos({cx},{cy})}}{text}\n"
        )
    dest.write_text("".join(lines), encoding="utf-8")
    return dest


def inpaint_frame_rois(
    frame_bgr: np.ndarray,
    boxes_xyxy: Sequence[tuple[int, int, int, int]],
    *,
    pad_px: int = ROI_PAD_PX,
) -> np.ndarray:
    """
    ROI-only Telea inpaint: dilate + Gaussian feather mask, pad crop, paste back.

    Kept for unit tests / light glyphs. Production clean uses ``cover_frame_rois``.
    """
    if frame_bgr is None or frame_bgr.size == 0 or not boxes_xyxy:
        return frame_bgr
    out = frame_bgr.copy()
    h, w = out.shape[:2]
    for x0, y0, x1, y1 in boxes_xyxy:
        x0 = int(max(0, min(w - 1, x0)))
        y0 = int(max(0, min(h - 1, y0)))
        x1 = int(max(x0 + 1, min(w, x1)))
        y1 = int(max(y0 + 1, min(h, y1)))

        rx0 = max(0, x0 - pad_px)
        ry0 = max(0, y0 - pad_px)
        rx1 = min(w, x1 + pad_px)
        ry1 = min(h, y1 + pad_px)
        if rx1 <= rx0 + 1 or ry1 <= ry0 + 1:
            continue

        roi = out[ry0:ry1, rx0:rx1].copy()
        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        # Box relative to ROI
        bx0, by0 = x0 - rx0, y0 - ry0
        bx1, by1 = x1 - rx0, y1 - ry0
        mask[by0:by1, bx0:bx1] = 255
        mask = cv2.dilate(mask, DILATE_KERNEL, iterations=1)
        mask = cv2.GaussianBlur(mask, (7, 7), 0)
        _, mask_bin = cv2.threshold(mask, 16, 255, cv2.THRESH_BINARY)
        if int(mask_bin.max()) == 0:
            continue
        cleaned = cv2.inpaint(roi, mask_bin, 3, cv2.INPAINT_TELEA)
        out[ry0:ry1, rx0:rx1] = cleaned
    return out


def cover_frame_rois(
    frame_bgr: np.ndarray,
    boxes_xyxy: Sequence[tuple[int, int, int, int]],
    *,
    pad_px: int = ROI_PAD_PX,
) -> np.ndarray:
    """Hardsub clean via production ``apply_blur_cover`` (ring fill + soft blur)."""
    from src.media_pipeline.video_renderer.inpaint_render import apply_blur_cover

    if frame_bgr is None or frame_bgr.size == 0 or not boxes_xyxy:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for x0, y0, x1, y1 in boxes_xyxy:
        x0 = int(max(0, min(w - 1, x0 - pad_px)))
        y0 = int(max(0, min(h - 1, y0 - pad_px)))
        x1 = int(max(x0 + 1, min(w, x1 + pad_px)))
        y1 = int(max(y0 + 1, min(h, y1 + pad_px)))
        mask[y0:y1, x0:x1] = 255
    if int(mask.max()) == 0:
        return frame_bgr
    mask = cv2.dilate(mask, DILATE_KERNEL, iterations=1)
    return apply_blur_cover(frame_bgr, mask)


def _events_active_at(events: Sequence[TimedBoxEvent], time_ms: int) -> list[TimedBoxEvent]:
    return [e for e in events if e.start_ms <= time_ms < e.end_ms]


class MagicVideoCleaner:
    """Clean Chinese burn-ins via blur cover + emit positioned Vietnamese ASS."""

    def __init__(self, *, default_hold_s: float = DEFAULT_HOLD_S) -> None:
        self.default_hold_s = float(default_hold_s)

    def process(
        self,
        video_path: str | Path,
        step3_json: Mapping[str, Any] | str | Path,
        out_dir: str | Path,
    ) -> tuple[Path, Path]:
        source = Path(video_path)
        if not source.is_file():
            raise FileNotFoundError(f"Video not found: {source}")

        if isinstance(step3_json, (str, Path)) and Path(step3_json).is_file():
            payload = json.loads(Path(step3_json).read_text(encoding="utf-8"))
        elif isinstance(step3_json, Mapping):
            payload = dict(step3_json)
        else:
            raise TypeError("step3_json must be a mapping or path to JSON file")

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        cleaned_path = out / "cleaned_video.mp4"
        ass_path = out / "vietnamese_sub.ass"

        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {source}")

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_s = (frame_count / fps) if fps > 0 and frame_count > 0 else None

            events = parse_step3_events(
                payload,
                default_hold_s=self.default_hold_s,
                video_duration_s=duration_s,
            )
            # Resolve pixel boxes with known frame size
            resolved: list[TimedBoxEvent] = []
            for ev in events:
                coords = ev.raw_coords or (
                    float(ev.xyxy[0]),
                    float(ev.xyxy[1]),
                    float(ev.xyxy[2]),
                    float(ev.xyxy[3]),
                )
                xyxy = resolve_xyxy_pixels(coords, frame_w=width, frame_h=height)
                resolved.append(
                    TimedBoxEvent(
                        start_ms=ev.start_ms,
                        end_ms=ev.end_ms,
                        xyxy=xyxy,
                        vietnamese_text=ev.vietnamese_text,
                        original_text=ev.original_text,
                        raw_coords=tuple(coords),
                    )
                )
            write_ass(resolved, video_w=width, video_h=height, path=ass_path)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(cleaned_path), fourcc, fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError(f"Failed to open VideoWriter: {cleaned_path}")

            total = frame_count if frame_count > 0 else None
            index = 0
            try:
                with tqdm(total=total, desc="ROI blur cover", unit="frame") as bar:
                    while True:
                        ok, frame = cap.read()
                        if not ok or frame is None:
                            break
                        time_ms = int(round(index * 1000.0 / fps))
                        active = _events_active_at(resolved, time_ms)
                        if active:
                            boxes = [e.xyxy for e in active]
                            frame = cover_frame_rois(frame, boxes)
                        writer.write(frame)
                        index += 1
                        bar.update(1)
            finally:
                writer.release()
        finally:
            cap.release()

        logger.info(
            "magic_cleaner_done cleaned=%s ass=%s events=%s",
            cleaned_path,
            ass_path,
            len(events),
        )
        return cleaned_path, ass_path


def burn_ass_onto_video(
    video_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    *,
    audio_from: str | Path | None = None,
    ffmpeg_binary: str = "ffmpeg",
) -> Path:
    """
    Burn ASS onto video → one complete MP4 (libass).

    Uses subtitle basename + ``cwd`` so Windows drive ``:`` never enters the filter graph.
    If ``audio_from`` is set (e.g. original source), mux that audio onto the cleaned picture.
    """
    video = Path(video_path)
    ass = Path(ass_path)
    dest = Path(output_path)
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    if not ass.is_file():
        raise FileNotFoundError(f"ASS not found: {ass}")
    if shutil.which(ffmpeg_binary) is None:
        raise RuntimeError(f"{ffmpeg_binary} not found on PATH")

    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = f"ass={ass.name}"
    audio_src = Path(audio_from) if audio_from is not None else None
    if audio_src is not None and audio_src.is_file():
        cmd = [
            ffmpeg_binary,
            "-y",
            "-i",
            str(video.resolve()),
            "-i",
            str(audio_src.resolve()),
            "-vf",
            vf,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(dest.resolve()),
        ]
    else:
        cmd = [
            ffmpeg_binary,
            "-y",
            "-i",
            str(video.resolve()),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-an",
            "-movflags",
            "+faststart",
            str(dest.resolve()),
        ]
    completed = subprocess.run(
        cmd,
        cwd=str(ass.resolve().parent),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not dest.is_file():
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"ffmpeg ASS burn failed: {err[-800:]}")
    return dest.resolve()


if __name__ == "__main__":
    api_root = Path(__file__).resolve().parents[3]
    out_dir = api_root / "tmp_step4_cleaner"
    out_dir.mkdir(parents=True, exist_ok=True)
    video_path = out_dir / "dummy_source.mp4"

    # Synthetic 2s clip @10fps with a bright subtitle bar.
    fps = 10.0
    w, h = 320, 240
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h),
    )
    for i in range(20):
        frame = np.full((h, w, 3), 36, dtype=np.uint8)
        if i < 12:
            frame[180:210, 40:280] = 245
            cv2.putText(
                frame,
                "ZH",
                (120, 205),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (10, 10, 10),
                2,
            )
        writer.write(frame)
    writer.release()

    step3 = {
        "00:00.000": [
            {
                "original_box_coords": [
                    40.0,
                    180.0,
                    280.0,
                    180.0,
                    280.0,
                    210.0,
                    40.0,
                    210.0,
                ],
                "original_text": "这件衣服太帅了",
                "vietnamese_text": "Áo này quá chất",
            }
        ],
        "00:01.200": [
            {
                "original_box_coords": [
                    40.0,
                    180.0,
                    280.0,
                    180.0,
                    280.0,
                    210.0,
                    40.0,
                    210.0,
                ],
                "original_text": "家人们赶紧去冲吧",
                "vietnamese_text": "Anh em tranh thủ mua",
            }
        ],
    }
    (out_dir / "step3.json").write_text(
        json.dumps(step3, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cleaned, ass = MagicVideoCleaner(default_hold_s=1.0).process(
        video_path,
        step3,
        out_dir,
    )
    print(f"cleaned={cleaned}")
    print(f"ass={ass}")
