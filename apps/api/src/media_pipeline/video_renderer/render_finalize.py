"""Pre-render finalize: track-level overlays, VI burn gate, QA fossils.

Authority when ``ocr_payload.master_timeline`` is present: one OverlaySegment
per ``text_id`` spanning ``start_frame``→``end_frame`` (not per stamped sample).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.ocr_filtering.types import DetectedTextBox
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_HOLD_MS,
    OverlaySegment,
    gate_vi_for_burn,
    overlays_from_ocr_payload,
)

logger = logging.getLogger(__name__)


def _frame_ms(frame_index: int, fps: float) -> int:
    from src.media_pipeline.video_renderer.render_runtime import frame_index_to_ms

    return frame_index_to_ms(frame_index, fps)


def _norm_xywh_from_coords(
    coords: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[float, float, float, float]:
    w = max(1, int(frame_w))
    h = max(1, int(frame_h))
    x0, y0, x1, y1 = (float(coords[i]) for i in range(4))
    nx = max(0.0, min(1.0, x0 / float(w)))
    ny = max(0.0, min(1.0, y0 / float(h)))
    nw = max(0.0, min(1.0 - nx, (x1 - x0) / float(w)))
    nh = max(0.0, min(1.0 - ny, (y1 - y0) / float(h)))
    return nx, ny, max(0.01, nw), max(0.01, nh)


def build_text_id_to_vi(
    payload: Mapping[str, Any],
    vi_texts: Mapping[Any, str],
) -> dict[str, str]:
    """
    Map ``text_id`` → VI using the same ``{time_ms}#{box_index}`` contract as flatten.
    """
    out: dict[str, str] = {}
    for frame in list(payload.get("frames") or []):
        if not isinstance(frame, Mapping):
            continue
        time_ms = int(frame.get("time_ms") or 0)
        box_index = 0
        for box in list(frame.get("boxes") or []):
            if not isinstance(box, Mapping):
                continue
            if bool(box.get("cover_only")):
                continue
            if box.get("translate_ready") is False:
                continue
            text = str(box.get("text") or "").strip()
            if not text or not contains_cjk(text):
                continue
            tid = str(box.get("text_id") or "").strip()
            key = f"{time_ms}#{box_index}"
            vi = ""
            if key in vi_texts:
                vi = str(vi_texts[key] or "")
            elif str(time_ms) in vi_texts and box_index == 0:
                vi = str(vi_texts[str(time_ms)] or "")
            elif time_ms in vi_texts and box_index == 0:
                vi = str(vi_texts[time_ms] or "")
            if tid and tid not in out and vi:
                out[tid] = vi
            box_index += 1
    return out


def overlays_from_master_timeline(
    payload: Mapping[str, Any],
    vi_texts: Mapping[Any, str],
    *,
    hold_ms: int = DEFAULT_HOLD_MS,
    video_duration_ms: int | None = None,
) -> tuple[list[OverlaySegment], dict[str, Any]]:
    """
    One continuous overlay per master track (``text_id``).

    Returns ``(overlays, stats)``.
    """
    from src.media_pipeline.ocr_filtering.overlay_zones import overlay_kind_for_box

    timeline = list(payload.get("master_timeline") or [])
    fps = float(payload.get("fps") or 30.0)
    frame_w = int(payload.get("frame_width") or 1080)
    frame_h = int(payload.get("frame_height") or 1920)
    frame_count = int(payload.get("frame_count") or 0)
    if video_duration_ms is not None and int(video_duration_ms) > 0:
        duration_ms = int(video_duration_ms)
    elif frame_count > 0:
        duration_ms = _frame_ms(frame_count, fps)
    else:
        duration_ms = 0

    vi_by_id = build_text_id_to_vi(payload, vi_texts)
    overlays: list[OverlaySegment] = []
    vi_dropped = 0
    cover_only_n = 0
    deterministic_n = 0

    for raw in timeline:
        if not isinstance(raw, Mapping):
            continue
        coords = list(raw.get("box_coords") or [])
        if len(coords) < 4:
            continue
        tid = str(raw.get("text_id") or "").strip()
        start_f = int(raw.get("start_frame") or 0)
        end_f = int(raw.get("end_frame") or start_f)
        start_ms = _frame_ms(start_f, fps)
        # Inclusive end_frame → exclusive ms end (cover last frame).
        end_ms = _frame_ms(end_f + 1, fps)
        if duration_ms > 0:
            end_ms = min(end_ms, duration_ms)
        if end_ms <= start_ms:
            end_ms = start_ms + max(int(hold_ms), 50)

        x, y, w, h = _norm_xywh_from_coords(coords, frame_w=frame_w, frame_h=frame_h)
        zh = str(raw.get("ocr_text") or raw.get("text") or "").strip()
        translate_ready = raw.get("translate_ready")
        deterministic_text = str(raw.get("render_text_approved") or "").strip()
        is_deterministic = bool(deterministic_text) and str(
            raw.get("localization_mode") or ""
        ) == "deterministic"
        is_cover = (
            (not zh)
            or ((translate_ready is False) and not is_deterministic)
            or bool(raw.get("cover_only"))
        )

        text_vi = ""
        if is_deterministic and not is_cover:
            text_vi = gate_vi_for_burn(deterministic_text)
            if text_vi:
                deterministic_n += 1
            else:
                vi_dropped += 1
        elif not is_cover:
            raw_vi = str(vi_by_id.get(tid) or "").strip()
            if not raw_vi:
                # Fallback: start stamp key.
                raw_vi = str(
                    vi_texts.get(f"{start_ms}#0")
                    or vi_texts.get(str(start_ms))
                    or ""
                ).strip()
            gated = gate_vi_for_burn(raw_vi)
            if raw_vi and not gated:
                vi_dropped += 1
            text_vi = gated
        else:
            cover_only_n += 1

        detected = DetectedTextBox(
            x=x,
            y=y,
            width=w,
            height=h,
            text=zh or "cover",
            confidence=0.99 if zh else 0.0,
        )
        kind = "ui" if is_cover else overlay_kind_for_box(detected)
        overlays.append(
            OverlaySegment(
                start_ms=start_ms,
                end_ms=end_ms,
                x=x,
                y=y,
                width=w,
                height=h,
                text_vi=text_vi,
                kind=kind,
                authority_bounds=(x, y, w, h),
            )
        )

    stats: dict[str, Any] = {
        "source": "master_timeline",
        "tracks": len(timeline),
        "segments": len(overlays),
        "cover_only": cover_only_n,
        "deterministic": deterministic_n,
        "vi_dropped": vi_dropped,
        "coalesced": True,
    }
    return overlays, stats


def write_overlay_fossils(
    artifact_dir: str | Path,
    overlays: Sequence[OverlaySegment],
    stats: Mapping[str, Any],
) -> dict[str, str]:
    """Persist ``overlays.json`` + ``overlay_stats.json`` for pre-render QA."""
    root = Path(artifact_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "start_ms": int(seg.start_ms),
            "end_ms": int(seg.end_ms),
            "x": float(seg.x),
            "y": float(seg.y),
            "width": float(seg.width),
            "height": float(seg.height),
            "text_vi": str(seg.text_vi or ""),
            "kind": str(seg.kind or ""),
        }
        for seg in overlays
    ]
    paths = {
        "overlays": root / "overlays.json",
        "overlay_stats": root / "overlay_stats.json",
    }
    paths["overlays"].write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["overlay_stats"].write_text(
        json.dumps(dict(stats), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "overlay_fossils segments=%s source=%s dir=%s",
        len(rows),
        stats.get("source"),
        root.as_posix(),
    )
    return {name: path.as_posix() for name, path in paths.items()}


def finalize_overlays_for_render(
    ocr_payload: Mapping[str, Any] | list[Mapping[str, Any]],
    vi_texts: Mapping[Any, str],
    *,
    hold_ms: int = DEFAULT_HOLD_MS,
    video_duration_ms: int | None = None,
    artifact_dir: str | Path | None = None,
) -> tuple[list[OverlaySegment], dict[str, Any]]:
    """
    Last gate before Phase 4: prefer track SSOT, gate VI burn, optional fossils.

    Returns ``(overlays, stats)``.
    """
    if isinstance(ocr_payload, Mapping) and list(ocr_payload.get("master_timeline") or []):
        overlays, stats = overlays_from_master_timeline(
            ocr_payload,
            vi_texts,
            hold_ms=hold_ms,
            video_duration_ms=video_duration_ms,
        )
    else:
        raw = overlays_from_ocr_payload(
            ocr_payload,
            vi_texts,
            hold_ms=hold_ms,
            video_duration_ms=video_duration_ms,
        )
        # Re-gate VI on legacy stamp path (defense in depth).
        overlays = []
        dropped = 0
        for seg in raw:
            gated = gate_vi_for_burn(seg.text_vi)
            if seg.text_vi and not gated:
                dropped += 1
            overlays.append(
                OverlaySegment(
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    x=seg.x,
                    y=seg.y,
                    width=seg.width,
                    height=seg.height,
                    text_vi=gated,
                    kind=seg.kind,
                    authority_bounds=seg.authority_bounds,
                )
            )
        stats = {
            "source": "frame_stamps",
            "segments": len(overlays),
            "cover_only": sum(1 for s in overlays if not s.text_vi),
            "vi_dropped": dropped,
            "coalesced": False,
        }

    if not overlays:
        from src.media_pipeline.video_renderer.errors import (
            VideoRendererError,
            VideoRendererErrorCode,
        )

        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "finalize_overlays_for_render produced no segments",
        )

    if artifact_dir is not None:
        write_overlay_fossils(artifact_dir, overlays, stats)
    return overlays, stats
