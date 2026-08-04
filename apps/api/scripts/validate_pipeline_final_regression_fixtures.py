"""Validate hash-bound Phase 4 final regression fixtures against real artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from src.media_pipeline.video_renderer.adaptive_render import AdaptiveFrameRenderer
from src.media_pipeline.video_renderer.adaptive_typography import plan_dense_grid_layouts
from src.media_pipeline.video_renderer.render_policy import (
    normalize_render_text,
    select_text_render_tracks,
)
from src.media_pipeline.video_renderer.visual_remediation import apply_visual_remediation


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = API_ROOT.parents[1]


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _resolve_workspace_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (WORKSPACE_ROOT / path).resolve()


def _read_frame(video: Path, frame_index: int) -> np.ndarray:
    capture = cv2.VideoCapture(str(video))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError(f"Cannot decode frame {frame_index} from {video.name}")
    return frame


def _roi_pixels(roi: Mapping[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    x0 = max(0, int(round(float(roi.get("x") or 0.0) * width)))
    y0 = max(0, int(round(float(roi.get("y") or 0.0) * height)))
    x1 = min(width, int(round((float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0)) * width)))
    y1 = min(height, int(round((float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)) * height)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Fixture ROI is empty")
    return x0, y0, x1, y1


def _check_case(case: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    root = _resolve_workspace_path(str(case.get("artifact_root") or ""))
    contract_path = root / "phase4_render_input.json"
    contract = _load(contract_path)
    effective, remediation_ref = apply_visual_remediation(
        root, contract, contract_path=contract_path
    )
    meta = _load(root / "phase4_adaptive_render_meta.json")
    output_qa = _load(root / "qa" / "phase4_adaptive_final_output_qa.json")
    final_video = root / "phase4_adaptive_final.mp4"
    phase1_meta = _load(root / "phase1_meta.json")
    source_video = _resolve_workspace_path(str(phase1_meta.get("video") or ""))
    assertions = dict(case.get("assertions") or {})
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **evidence: Any) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", **evidence})

    add(
        "final_output_qa",
        str(meta.get("status") or "") == "FINAL_RENDERED"
        and str(meta.get("output_qa_status") or "") == "PASS"
        and str(output_qa.get("status") or "") == "PASS"
        and not list(output_qa.get("failed_checks") or []),
        render_status=meta.get("status"),
        output_qa_status=output_qa.get("status"),
    )

    source_rule = dict(assertions.get("source_intrinsic") or {})
    region_id = str(source_rule.get("region_id") or "")
    regions = [
        dict(row)
        for row in list(effective.get("source_scene_text_regions") or [])
        if str(dict(row).get("region_id") or "") == region_id
    ]
    expected_source_ids = {str(value) for value in list(source_rule.get("track_ids") or [])}
    render_ids = {
        str(row.get("text_id") or "")
        for row in list(effective.get("render_tracks") or [])
    }
    classified_ids = {
        str(row.get("text_id") or "")
        for row in list(effective.get("source_scene_text_tracks") or [])
        if str(row.get("region_id") or "") == region_id
    }
    add(
        "source_intrinsic_authority",
        len(regions) == 1
        and expected_source_ids.issubset(classified_ids)
        and not expected_source_ids.intersection(render_ids),
        region_id=region_id,
        expected_track_count=len(expected_source_ids),
        classified_track_count=len(classified_ids),
        leaked_render_track_ids=sorted(expected_source_ids.intersection(render_ids)),
        remediation_ref=remediation_ref,
    )

    pixel_rows: list[dict[str, Any]] = []
    roi = dict(source_rule.get("roi") or {})
    max_mad = float(source_rule.get("max_mean_abs_delta") or 3.0)
    max_changed = float(source_rule.get("max_changed_fraction_gt12") or 0.001)
    for frame_index in [int(value) for value in list(source_rule.get("sample_frames") or [])]:
        source = _read_frame(source_video, frame_index)
        rendered = _read_frame(final_video, frame_index)
        if source.shape != rendered.shape:
            raise ValueError("Source/final frame dimensions differ")
        x0, y0, x1, y1 = _roi_pixels(roi, source.shape[1], source.shape[0])
        delta = np.abs(
            source[y0:y1, x0:x1].astype(np.int16)
            - rendered[y0:y1, x0:x1].astype(np.int16)
        )
        pixel_rows.append(
            {
                "frame_index": frame_index,
                "mean_abs_delta": round(float(delta.mean()), 6),
                "p95_abs_delta": round(float(np.percentile(delta, 95)), 6),
                "changed_fraction_gt12": round(
                    float((delta.max(axis=2) > 12).mean()), 8
                ),
            }
        )
    add(
        "source_intrinsic_pixel_preservation",
        bool(pixel_rows)
        and all(row["mean_abs_delta"] <= max_mad for row in pixel_rows)
        and all(row["changed_fraction_gt12"] <= max_changed for row in pixel_rows),
        thresholds={
            "max_mean_abs_delta": max_mad,
            "max_changed_fraction_gt12": max_changed,
        },
        frames=pixel_rows,
    )

    semantic_rule = dict(assertions.get("semantic_duplicate") or {})
    semantic_key = normalize_render_text(semantic_rule.get("text"))
    start_frame, end_frame = [int(value) for value in semantic_rule.get("frame_window", [0, -1])]
    max_labels = 0
    violation_frames: list[int] = []
    tracks = [dict(row) for row in list(effective.get("render_tracks") or [])]
    for frame_index in range(start_frame, end_frame + 1):
        active = [
            row
            for row in tracks
            if int(row.get("start_frame") or 0)
            <= frame_index
            <= int(row.get("end_frame") or -1)
        ]
        count = sum(
            normalize_render_text(row.get("text_vi")) == semantic_key
            for row in select_text_render_tracks(active)
        )
        max_labels = max(max_labels, count)
        if count > int(semantic_rule.get("max_rendered_labels") or 0):
            violation_frames.append(frame_index)
    add(
        "semantic_duplicate_window",
        not violation_frames,
        frame_window=[start_frame, end_frame],
        max_rendered_labels=max_labels,
        violation_frames=violation_frames,
    )

    group_rule = dict(assertions.get("dense_group_layout") or {})
    group_ids = [str(value) for value in list(group_rule.get("track_ids") or [])]
    group_tracks = [row for row in tracks if str(row.get("text_id") or "") in group_ids]
    renderer = AdaptiveFrameRenderer()
    renderer.seed_dense_layout_authority(group_tracks)
    authority = renderer._dense_slot_authority
    ordered_by_source_y = sorted(
        group_tracks,
        key=lambda row: float(dict(row.get("geometry") or {}).get("y") or 0.0),
    )
    slots = [int(authority[str(row.get("text_id"))]["slot_index"]) for row in ordered_by_source_y]
    sides = {str(authority[text_id]["side"]) for text_id in group_ids if text_id in authority}
    video = dict(contract.get("video") or {})
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    items = [
        {
            "text_id": row.get("text_id"),
            "content_id": row.get("content_id"),
            "text": row.get("text_vi"),
            "geometry": dict(row.get("geometry") or {}),
            "side": authority[str(row.get("text_id"))]["side"],
            "stable_slot": authority[str(row.get("text_id"))],
        }
        for row in group_tracks
    ]
    first_policy = dict(group_tracks[0].get("render_policy") or {}) if group_tracks else {}
    safe_area = dict(dict(first_policy.get("layout") or {}).get("safe_area") or {})
    layouts = plan_dense_grid_layouts(
        items,
        safe_area=safe_area,
        frame_width=frame_width,
        frame_height=frame_height,
        fontfile=renderer.fontfile,
        background_bgr=np.full((frame_height, frame_width, 3), 128, dtype=np.uint8),
    ) if items else []
    placement_modes = {str(row.get("placement_mode") or "") for row in layouts}
    source_y0 = min(float(dict(row.get("geometry") or {}).get("y") or 0.0) for row in group_tracks)
    source_y1 = max(
        float(dict(row.get("geometry") or {}).get("y") or 0.0)
        + float(dict(row.get("geometry") or {}).get("height") or 0.0)
        for row in group_tracks
    )
    rendered_y0 = min(row["layout"].y0 / frame_height for row in layouts)
    rendered_y1 = max((row["layout"].y0 + row["layout"].height) / frame_height for row in layouts)
    span_ratio = (rendered_y1 - rendered_y0) / max(1e-9, source_y1 - source_y0)
    add(
        "dense_group_source_relative_layout",
        len(group_tracks) == len(group_ids)
        and sides == {str(group_rule.get("expected_side") or "left")}
        and slots == sorted(slots)
        and placement_modes == {"source_relative"}
        and span_ratio <= float(group_rule.get("max_span_ratio") or 1.2),
        sides=sorted(sides),
        source_order_slots=slots,
        placement_modes=sorted(placement_modes),
        source_span=round(source_y1 - source_y0, 6),
        rendered_span=round(rendered_y1 - rendered_y0, 6),
        span_ratio=round(span_ratio, 6),
    )

    audio_rule = dict(assertions.get("audio") or {})
    audio_mix = dict(meta.get("audio_mix") or {})
    source_duration = float(dict(output_qa.get("media") or {}).get("source_duration_seconds") or 0.0)
    rendered_duration = float(dict(output_qa.get("media") or {}).get("rendered_duration_seconds") or 0.0)
    add(
        "audio_duration_and_background",
        bool(audio_mix.get("narration_complete"))
        and float(audio_mix.get("narration_atempo") or 0.0)
        <= float(audio_rule.get("max_atempo") or 1.2)
        and float(audio_mix.get("background_gain") or 0.0)
        == float(audio_rule.get("background_gain") or 1.0)
        and abs(source_duration - rendered_duration)
        <= float(audio_rule.get("duration_tolerance_seconds") or 0.08),
        audio_mix=audio_mix,
        source_duration_seconds=source_duration,
        rendered_duration_seconds=rendered_duration,
    )

    failed = [row["check"] for row in checks if row["status"] != "PASS"]
    return {
        "case_id": case.get("case_id"),
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "checks": checks,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def validate_fixture_manifest(path: Path) -> dict[str, Any]:
    manifest = _load(path)
    unsigned = dict(manifest)
    claimed = str(unsigned.pop("fixture_sha256", "") or "")
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise ValueError("Fixture manifest self-hash is invalid")
    cases = [_check_case(dict(row)) for row in list(manifest.get("cases") or [])]
    failed_count = sum(row["status"] != "PASS" for row in cases)
    return {
        "schema_version": "pipeline_final_regression_fixture_report_v1",
        "status": "PASS" if not failed_count else "FAIL",
        "fixture_ref": {
            "path": path.relative_to(WORKSPACE_ROOT).as_posix(),
            "fixture_sha256": claimed,
        },
        "case_count": len(cases),
        "passed_count": len(cases) - failed_count,
        "failed_count": failed_count,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    report = validate_fixture_manifest(args.fixture_json.resolve())
    report["report_sha256"] = _sha256_json(report)
    args.output_json.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "case_count": report["case_count"],
                "passed_count": report["passed_count"],
                "failed_count": report["failed_count"],
                "report_sha256": report["report_sha256"],
            }
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
