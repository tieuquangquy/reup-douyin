"""Build a Phase-4 blur-only contract from a fresh local OCR scan.

The contract intentionally has no translation or typography authority.  Only
Phase-1 ``EDITOR_OVERLAY`` tracks that survive Phase-2 temporal/content
reconciliation are rendered; every other track is preserved fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.render_policy import (
    enrich_phase4_render_policies,
)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must be a JSON object")
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"{path.name} must be a JSON array")
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _probe_video(source: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            (
                "stream=codec_name,width,height,pix_fmt,sample_aspect_ratio,"
                "display_aspect_ratio,color_range,color_space,color_transfer,"
                "color_primaries,field_order,avg_frame_rate,r_frame_rate,time_base"
            ),
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffprobe failed for the Phase-1 source video")
    payload = json.loads(completed.stdout or "{}")
    streams = list(payload.get("streams") or [])
    if not streams:
        raise RuntimeError("Source video stream metadata is unavailable")
    return dict(streams[0])


def _geometry(row: Mapping[str, Any], width: int, height: int) -> dict[str, float]:
    coords = list(row.get("box_coords") or [])
    if len(coords) != 4:
        raise RuntimeError(f"Missing box_coords for {row.get('text_id')}")
    x0, y0, x1, y1 = (float(value) for value in coords)
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0 or x1 > width or y1 > height:
        raise RuntimeError(f"Invalid source geometry for {row.get('text_id')}")
    return {
        "x": x0 / width,
        "y": y0 / height,
        "width": (x1 - x0) / width,
        "height": (y1 - y0) / height,
    }


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    phase1_meta = _load_object(root / "phase1_meta.json")
    phase2 = _load_object(root / "phase2_ocr_timeline.json")
    master = _load_list(root / "master_timeline.json")
    source = Path(str(phase1_meta.get("video") or ""))
    if not source.is_file():
        raise RuntimeError("Phase-1 source video is missing")

    width = int(phase1_meta.get("frame_width") or 0)
    height = int(phase1_meta.get("frame_height") or 0)
    frame_count = int(phase1_meta.get("frame_count") or 0)
    fps = float(phase1_meta.get("fps") or 0.0)
    if width < 2 or height < 2 or frame_count < 1 or fps <= 0:
        raise RuntimeError("Phase-1 raster/timebase metadata is invalid")

    enrichments = {
        str(row.get("text_id") or ""): dict(row)
        for row in list(phase2.get("track_enrichments") or [])
        if isinstance(row, Mapping) and str(row.get("text_id") or "")
    }
    contents = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(phase2.get("content_objects") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    phase1_editor_ids = {
        str(row.get("text_id") or "")
        for row in master
        if str(dict(row.get("visual_provenance") or {}).get("classification") or "")
        == "EDITOR_OVERLAY"
    }
    # Phase 2 removes empty temporal shadows before content authority.  Keep
    # that reconciliation for compact/ambiguous tracks, but a provenance-
    # approved sequential caption lane is geometry authority even if a single
    # representative OCR crop fails.  Requiring OCR text here used to discard
    # the very cover-only rows needed to conceal low-contrast outlined captions.
    caption_lane_editor_ids = {
        str(row.get("text_id") or "")
        for row in master
        if str(dict(row.get("visual_provenance") or {}).get("classification") or "")
        == "EDITOR_OVERLAY"
        and (
            "sequential_screen_locked_caption_lane"
            in set(dict(row.get("visual_provenance") or {}).get("reasons") or [])
            or "caption_lane_provenance_overrides_dense_source_context"
            in set(dict(row.get("visual_provenance") or {}).get("reasons") or [])
        )
    }
    blur_ids = (phase1_editor_ids & set(enrichments)) | caption_lane_editor_ids
    suppressed_editor_ids = sorted(phase1_editor_ids - blur_ids)

    coverage_by_id = {
        text_id: dict(row.get("coverage_authority") or {})
        for text_id, row in enrichments.items()
    }
    for row in list(phase2.get("protected_source_tracks") or []):
        if not isinstance(row, Mapping):
            continue
        text_id = str(row.get("text_id") or "")
        if text_id and isinstance(row.get("coverage_authority"), Mapping):
            coverage_by_id[text_id] = dict(row.get("coverage_authority") or {})

    render_tracks: list[dict[str, Any]] = []
    protected_tracks: list[dict[str, Any]] = []
    for source_row in master:
        row = dict(source_row)
        text_id = str(row.get("text_id") or "")
        start = int(row.get("start_frame") or 0)
        end = int(row.get("end_frame") or start)
        if not text_id or start < 0 or end < start or end >= frame_count:
            raise RuntimeError(f"Invalid track timing for {text_id or 'unknown'}")
        geometry = _geometry(row, width, height)
        if text_id in blur_ids:
            enrichment = enrichments.get(text_id, {})
            content = contents.get(str(enrichment.get("content_id") or ""), {})
            render_tracks.append(
                {
                    "text_id": text_id,
                    "content_id": None,
                    "start_frame": start,
                    "end_frame": end,
                    "best_frame_index": int(
                        row.get("best_frame_index")
                        if row.get("best_frame_index") is not None
                        else (start + end) // 2
                    ),
                    "start_ms": int(round(start * 1000.0 / fps)),
                    "end_ms": int(round((end + 1) * 1000.0 / fps)),
                    "geometry": geometry,
                    "hit_frames": [
                        int(value)
                        for value in list(row.get("hit_frames") or [])
                        if isinstance(value, (int, float))
                    ],
                    "boundary_evidence": dict(row.get("boundary_evidence") or {}),
                    "coverage_authority": dict(coverage_by_id.get(text_id) or {}),
                    "roles": [str(value) for value in list(content.get("roles") or [])],
                    "kind": "ui",
                    "text_vi": "",
                    "translation_status": "COVER_ONLY_FRESH_LOCAL_SCAN",
                    "cover_only": True,
                    "visual_provenance": dict(row.get("visual_provenance") or {}),
                    "editor_card_panel_box": list(
                        dict(row.get("visual_provenance") or {}).get(
                            "editor_card_panel_box"
                        )
                        or []
                    ),
                    "editor_card_panel_geometry": {
                        "x": float(
                            dict(row.get("visual_provenance") or {})[
                                "editor_card_panel_box"
                            ][0]
                        )
                        / width,
                        "y": float(
                            dict(row.get("visual_provenance") or {})[
                                "editor_card_panel_box"
                            ][1]
                        )
                        / height,
                        "width": (
                            float(
                                dict(row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][2]
                            )
                            - float(
                                dict(row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][0]
                            )
                        )
                        / width,
                        "height": (
                            float(
                                dict(row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][3]
                            )
                            - float(
                                dict(row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][1]
                            )
                        )
                        / height,
                    }
                    if len(
                        list(
                            dict(row.get("visual_provenance") or {}).get(
                                "editor_card_panel_box"
                            )
                            or []
                        )
                    )
                    == 4
                    else {},
                }
            )
            continue

        provenance = dict(row.get("visual_provenance") or {})
        if text_id in suppressed_editor_ids:
            provenance = {
                "classification": "UNCERTAIN",
                "confidence": 0.5,
                "policy_version": "blur_only_phase2_shadow_fail_closed_v1",
                "reasons": [
                    "phase1_editor_candidate",
                    "phase2_temporal_content_reconciliation_removed_empty_shadow",
                    "preserve_source_pixels_instead_of_guessing",
                ],
            }
        protected_tracks.append(
            {
                "text_id": text_id,
                "start_frame": start,
                "end_frame": end,
                "geometry": geometry,
                "classification": str(provenance.get("classification") or "UNCERTAIN"),
                "action": "PRESERVE_SOURCE_PIXELS",
                "visual_provenance": provenance,
                "coverage_authority": dict(coverage_by_id.get(text_id) or {}),
            }
        )

    render_tracks.sort(key=lambda row: (row["start_frame"], row["text_id"]))
    protected_tracks.sort(key=lambda row: (row["start_frame"], row["text_id"]))
    stream = _probe_video(source)
    source_sha256 = _sha256_file(source)
    phase1_ref = root / "master_timeline.json"
    phase2_ref = root / "phase2_ocr_timeline.json"
    coverage_ref = root / "phase1_track_coverage_v2.json"
    contract = enrich_phase4_render_policies(
        {
            "schema_version": "phase4_blur_only_input_v1",
            "status": "READY_FOR_PHASE4",
            "refs": {
                "phase1_ref": {"path": phase1_ref.name, "sha256": _sha256_file(phase1_ref)},
                "phase2_ref": {"path": phase2_ref.name, "sha256": _sha256_file(phase2_ref)},
                "phase1_coverage_ref": {
                    "path": coverage_ref.name,
                    "sha256": _sha256_file(coverage_ref),
                },
                "source_video_ref": {"path": source.name, "sha256": source_sha256},
            },
            "video": {
                "frame_width": width,
                "frame_height": height,
                "frame_count": frame_count,
                "fps": fps,
            },
            "counts": {
                "phase1_tracks": len(master),
                "phase1_editor_candidates": len(phase1_editor_ids),
                "render_tracks": len(render_tracks),
                "localized_tracks": 0,
                "cover_only_tracks": len(render_tracks),
                "protected_source_tracks": len(protected_tracks),
                "suppressed_editor_shadows": len(suppressed_editor_ids),
            },
            "render_tracks": render_tracks,
            "protected_source_tracks": protected_tracks,
            "dense_ui_panels": [],
            "authorities": {
                "timebase": {
                    "status": "READY",
                    "mode": "CFR",
                    "frame_timestamps": frame_count,
                    "nominal_frame_duration_seconds": round(1.0 / fps, 9),
                    "nominal_fps": fps,
                    "source_time_base": stream.get("time_base"),
                },
                "audio": {"status": "SOURCE_AUDIO_PREVIEW", "strategy": "preserve_source_audio"},
                "color": {
                    "codec": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "pixel_format": stream.get("pix_fmt"),
                    "sample_aspect_ratio": stream.get("sample_aspect_ratio"),
                    "display_aspect_ratio": stream.get("display_aspect_ratio"),
                    "color_range": stream.get("color_range"),
                    "color_space": stream.get("color_space"),
                    "color_transfer": stream.get("color_transfer"),
                    "color_primaries": stream.get("color_primaries"),
                    "field_order": stream.get("field_order"),
                },
            },
            "final_render_gate": "BLUR_ONLY_NO_TRANSLATION",
        }
    )
    contract["status"] = "READY_FOR_PHASE4"
    contract["dense_ui_panels"] = []
    for track in list(contract.get("render_tracks") or []):
        track["text_vi"] = ""
        track["cover_only"] = True
    return {
        "contract": contract,
        "source": source,
        "source_sha256": source_sha256,
        "phase1_editor_ids": sorted(phase1_editor_ids),
        "caption_lane_editor_ids": sorted(caption_lane_editor_ids),
        "blur_ids": sorted(blur_ids),
        "suppressed_editor_ids": suppressed_editor_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = build(args.root)
    root = args.root.resolve()
    contract_path = root / "phase4_blur_only_input.json"
    _write_json(contract_path, result["contract"])
    # The adaptive runner consumes this stable filename.  This run directory is
    # dedicated to blur-only output, so no historical Phase-4 input is replaced.
    _write_json(root / "phase4_render_input.json", result["contract"])
    meta = {
        "schema_version": "blur_only_contract_meta_v1",
        "source_video_sha256": result["source_sha256"],
        "phase1_editor_ids": result["phase1_editor_ids"],
        "caption_lane_editor_ids": result["caption_lane_editor_ids"],
        "blur_track_ids": result["blur_ids"],
        "suppressed_editor_shadow_ids": result["suppressed_editor_ids"],
        "render_track_count": len(result["blur_ids"]),
        "protected_track_count": len(result["contract"].get("protected_source_tracks") or []),
        "translation_inserted": False,
        "source_audio_preserved": True,
        "contract_path": contract_path.name,
        "contract_sha256": _sha256_file(contract_path),
    }
    _write_json(root / "blur_only_contract_meta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
