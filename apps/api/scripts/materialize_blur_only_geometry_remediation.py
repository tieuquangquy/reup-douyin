"""Rebind reviewed same-source geometry as blur-only QA remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must be an object")
    return payload


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("reviewed_contract", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    reviewed_path = args.reviewed_contract.resolve()
    current = _load(root / "phase4_blur_only_input.json")
    reviewed = _load(reviewed_path)
    current_source = str(
        dict(dict(current.get("refs") or {}).get("source_video_ref") or {}).get(
            "sha256"
        )
        or ""
    )
    reviewed_source = str(
        dict(dict(reviewed.get("refs") or {}).get("source_video_ref") or {}).get(
            "sha256"
        )
        or ""
    )
    if len(current_source) != 64 or current_source != reviewed_source:
        raise RuntimeError("Reviewed geometry is not bound to the current source hash")

    reviewed_tracks = [
        dict(row)
        for row in list(reviewed.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    if not reviewed_tracks:
        raise RuntimeError("Reviewed geometry contains no render tracks")

    # OCR-V27.1 encoded-output QA found a real untracked caption interval
    # between the reviewed tracks ending at 1363 and starting at 1522.  Bind a
    # cover-only lane to the local OCR geometry instead of extending a guessed
    # neighboring sentence.  The full-width observation at frame 1395 is
    # temporally confirmed on its adjacent source frame.
    previous_caption = next(
        (
            dict(row)
            for row in reviewed_tracks
            if str(row.get("text_id") or "") == "sub_209"
        ),
        None,
    )
    if previous_caption is None:
        raise RuntimeError("Reviewed caption lane authority sub_209 is missing")
    residual_gap_track = {
        "text_id": "ocrv27_residual_caption_gap_1364_1521",
        "content_id": None,
        "start_frame": 1364,
        "end_frame": 1521,
        "best_frame_index": 1395,
        "start_ms": 45467,
        "end_ms": 50733,
        # Use the reviewed stable lane as the render base; the explicit
        # coverage geometry below binds the all-frame OCR observation.
        "geometry": dict(previous_caption.get("geometry") or {}),
        "hit_frames": [1394, 1395, 1396],
        "boundary_evidence": {
            "status": "sampled_window_confirmed",
            "method": "ocr_v27_encoded_output_residual_cjk",
            "observed_first_frame": 1394,
            "observed_last_frame": 1396,
            "sampled_frames": 3,
            "hit_count": 3,
            "hit_density": 1.0,
        },
        "coverage_authority": {
            "text_id": "ocrv27_residual_caption_gap_1364_1521",
            "policy_version": "ocr_v27_residual_caption_gap_v1",
            "presence_ranges": [[1364, 1521]],
            "geometry_keyframes": [
                {
                    "frame_index": 1394,
                    "geometry": {
                        "x": 0.0,
                        "y": 0.7415,
                        "width": 1.0,
                        "height": 0.0395,
                    },
                },
                {
                    "frame_index": 1396,
                    "geometry": {
                        "x": 0.0,
                        "y": 0.7415,
                        "width": 1.0,
                        "height": 0.0395,
                    },
                },
            ],
            "confidence": 0.995,
            "fail_closed": True,
        },
        "roles": ["hardsub"],
        "kind": str(previous_caption.get("kind") or "hardsub"),
        "text_vi": "",
        "translation_status": "COVER_ONLY_OCR_V27_RESIDUAL",
        "cover_only": True,
        "visual_provenance": {
            "classification": "EDITOR_OVERLAY",
            "confidence": 0.995,
            "policy_version": "ocr_v27_encoded_output_residual_cjk_v1",
            "reasons": [
                "full_width_bottom_caption_lane",
                "high_confidence_local_cjk",
                "adjacent_frame_temporal_confirmation",
            ],
        },
    }
    residual_gap_track["render_policy"] = dict(
        previous_caption.get("render_policy") or {}
    )
    prior_policy = dict(residual_gap_track["render_policy"])
    prior_context = dict(prior_policy.get("context") or {})
    prior_cover = dict(prior_policy.get("cover") or {})
    prior_context.update(
        {
            "supplemental_cover_only": True,
            "residual_gap_authority": "ocr_v27_frame_1395_temporal_confirmed",
        }
    )
    prior_cover["roi"] = {
        "x": 0.0,
        "y": 0.735,
        "width": 1.0,
        "height": 0.0525,
    }
    prior_cover["geometry_mode"] = "stable_caption_envelope"
    prior_policy["context"] = prior_context
    prior_policy["cover"] = prior_cover
    residual_gap_track["render_policy"] = prior_policy
    reviewed_tracks.append(residual_gap_track)

    # Same-source visual review established that this short micro-UI track is
    # print on a handheld mirror/prop, not an editor-added overlay.  It follows
    # the object plane across adjacent frames and must therefore be protected,
    # never covered.  Keep the decision hash-bound to this reviewed contract;
    # the production classifier remains provenance-driven and contains no
    # global coordinate/frame exception.
    protected_object_text_ids = {"sub_382"}
    reviewed_object_tracks = [
        dict(row)
        for row in reviewed_tracks
        if str(row.get("text_id") or "") in protected_object_text_ids
    ]
    if {str(row.get("text_id") or "") for row in reviewed_object_tracks} != (
        protected_object_text_ids
    ):
        raise RuntimeError("Reviewed source-object text authority is missing")
    reviewed_tracks = [
        row
        for row in reviewed_tracks
        if str(row.get("text_id") or "") not in protected_object_text_ids
    ]
    for row in reviewed_tracks:
        row["text_vi"] = ""
        row["cover_only"] = True
        row["content_id"] = None
        row["translation_status"] = "COVER_ONLY_SAME_SOURCE_REVIEWED_GEOMETRY"
        row.pop("duplicate_transition_canonical", None)
        context = dict(dict(row.get("render_policy") or {}).get("context") or {})
        for key in ("soft_cover_epoch_members", "caption_cover_group_members"):
            if isinstance(context.get(key), list):
                context[key] = [
                    value
                    for value in context[key]
                    if str(value) not in protected_object_text_ids
                ]
        if context:
            policy = dict(row.get("render_policy") or {})
            policy["context"] = context
            row["render_policy"] = policy
    protected = [
        dict(row)
        for row in list(reviewed.get("protected_source_tracks") or [])
        if isinstance(row, Mapping)
    ]
    protected_ids = {str(row.get("text_id") or "") for row in protected}
    for track in reviewed_object_tracks:
        text_id = str(track.get("text_id") or "")
        if text_id in protected_ids:
            continue
        protected.append(
            {
                "text_id": text_id,
                "start_frame": int(track.get("start_frame") or 0),
                "end_frame": int(track.get("end_frame") or 0),
                "geometry": dict(track.get("geometry") or {}),
                "classification": "SOURCE_INTRINSIC_PANEL",
                "action": "PRESERVE_SOURCE_PIXELS",
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC",
                    "confidence": 1.0,
                    "policy_version": "same_source_object_plane_review_v1",
                    "reasons": [
                        "text_printed_on_handheld_mirror_or_prop",
                        "temporal_geometry_follows_object_plane",
                        "not_editor_overlay",
                    ],
                },
                "coverage_authority": dict(track.get("coverage_authority") or {}),
            }
        )
        protected_ids.add(text_id)
    refs = dict(current.get("refs") or {})
    refs["reviewed_geometry_remediation_ref"] = {
        "path": reviewed_path.name,
        "sha256": _sha(reviewed_path),
        "source_video_sha256": reviewed_source,
        "usage": "geometry_and_protected_source_only",
    }
    counts = dict(current.get("counts") or {})
    counts.update(
        {
            "render_tracks": len(reviewed_tracks),
            "localized_tracks": 0,
            "cover_only_tracks": len(reviewed_tracks),
            "protected_source_tracks": len(protected),
            "qa_geometry_remediation_tracks": len(reviewed_tracks),
        }
    )
    output = dict(reviewed)
    output.update(
        {
            "schema_version": "phase4_blur_only_input_v1",
            "status": "READY_FOR_PHASE4",
            "refs": refs,
            "video": dict(current.get("video") or {}),
            "counts": counts,
            "render_tracks": reviewed_tracks,
            "protected_source_tracks": protected,
            "dense_ui_panels": [],
            "soft_cover_epochs": [],
            "authorities": dict(current.get("authorities") or {}),
            "final_render_gate": "BLUR_ONLY_NO_TRANSLATION",
        }
    )
    # Reassert the current production cover profile without recomputing the
    # reviewed track geometry/timing partition.  ``render_adaptive_video`` also
    # enforces this at runtime; persisting it here keeps QA and artifact review
    # explicit and prevents an old v19 strategy from becoming documentary
    # authority in the blur-only run.
    from src.media_pipeline.video_renderer.render_policy import (
        enforce_unified_editor_cover_contract,
    )

    output = enforce_unified_editor_cover_contract(output)
    output["dense_ui_panels"] = []
    for row in list(output.get("render_tracks") or []):
        row["text_vi"] = ""
        row["cover_only"] = True
        policy = dict(row.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        cover = dict(policy.get("cover") or {})
        timing = dict(context.get("cover_timing_authority") or {})
        observed = list(timing.get("observed_range") or [])
        raw_cover_start = row.get("cover_start_frame")
        cover_start = (
            int(raw_cover_start) if raw_cover_start is not None else None
        )
        if (
            cover_start is not None
            and 0 < cover_start <= 3
            and int(row.get("start_frame") or 0) < cover_start
            and len(observed) == 2
            and int(observed[0]) == cover_start
        ):
            # A generic transition hold may extend a newly appearing label
            # backwards before frame zero.  At the opening boundary there is
            # no prior-frame evidence to justify that pre-roll, so it creates
            # a visible empty plate. Start concealment at the first observed
            # glyph instead; forward boundary protection remains unchanged.
            cover["transition_hold_frames"] = 0
            context["opening_preroll_suppressed"] = True
            policy["cover"] = cover
            policy["context"] = context
            row["render_policy"] = policy
        geometry = dict(row.get("geometry") or {})
        if (
            int(row.get("start_frame") or 0) == 0
            and str(row.get("kind") or "") == "hardsub"
            and float(geometry.get("height") or 0.0) >= 0.10
        ):
            # Large outlined opening titles have thick shadow/stroke pixels
            # beyond the OCR content box.  Feathering exactly at that box can
            # leave a one-pixel coloured crown visible after encoding. Expand
            # the plate by a glyph-relative safety margin while keeping it
            # bounded to the title rather than promoting a full-width mask.
            policy = dict(row.get("render_policy") or {})
            cover = dict(policy.get("cover") or {})
            roi = dict(cover.get("roi") or geometry)
            left = max(0.0, float(roi.get("x") or 0.0))
            top = max(0.0, float(roi.get("y") or 0.0) - 0.012)
            right = min(
                1.0,
                float(roi.get("x") or 0.0)
                + float(roi.get("width") or 0.0),
            )
            bottom = min(
                1.0,
                float(roi.get("y") or 0.0)
                + float(roi.get("height") or 0.0),
            )
            cover["roi"] = {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top,
            }
            cover["geometry_mode"] = "opening_title_stroke_envelope"
            policy["cover"] = cover
            context = dict(policy.get("context") or {})
            context["opening_title_stroke_envelope"] = True
            policy["context"] = context
            budget = dict(policy.get("damage_budget") or {})
            title_roi_area = (right - left) * (bottom - top)
            budget["max_frame_change_fraction"] = max(
                float(budget.get("max_frame_change_fraction") or 0.0),
                min(0.14, title_roi_area * 1.02),
            )
            policy["damage_budget"] = budget
            row["render_policy"] = policy
    _write(root / "phase4_render_input.json", output)
    _write(root / "phase4_blur_only_remediated_input.json", output)
    meta = {
        "schema_version": "blur_only_geometry_remediation_meta_v1",
        "source_video_sha256": current_source,
        "reviewed_contract_sha256": _sha(reviewed_path),
        "render_track_count": len(reviewed_tracks),
        "protected_source_track_count": len(protected),
        "translation_inserted": False,
        "dense_ui_panels": 0,
        "reason": [
            "fresh_scan_output_qa_residual_cjk",
            "fresh_scan_geometry_incomplete_for_long_caption_edges",
            "reuse_only_hash_bound_same_source_reviewed_geometry",
            "preserve_reviewed_source_object_print",
        ],
    }
    _write(root / "blur_only_geometry_remediation_meta.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
