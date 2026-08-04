"""Build hash-bound triage evidence for failed Phase 4 visual previews."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.run_phase4_adaptive import _source_path
from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
    _roi_pixels,
)
from src.media_pipeline.video_renderer.adaptive_video import (
    _seed_reference_plates,
    _seed_representative_masks,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    apply_visual_remediation,
)

MASK_FAILURE_RE = re.compile(
    r"Adaptive frame blocked at index (?P<frame>\d+): "
    r"Mask quality blocked for (?P<text_id>[^\s]+)"
)
REFERENCE_PLATE_FAILURE_RE = re.compile(
    r"Adaptive frame blocked at index (?P<frame>\d+): "
    r"Reference plate alignment failed for (?P<text_id>[^\s]+)"
)
OUTPUT_QA_FAILURE_RE = re.compile(
    r"Visual preview output QA failed \((?P<checks>[^)]*)\)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def classify_failure(log_text: str) -> dict[str, Any] | None:
    value = str(log_text or "")
    mask_matches = list(MASK_FAILURE_RE.finditer(value))
    reference_matches = list(REFERENCE_PLATE_FAILURE_RE.finditer(value))
    output_matches = list(OUTPUT_QA_FAILURE_RE.finditer(value))
    visual_matches = [
        *((match, "MASK_QUALITY_BLOCKED") for match in mask_matches),
        *((match, "REFERENCE_PLATE_ALIGNMENT_BLOCKED") for match in reference_matches),
    ]
    visual = max(visual_matches, key=lambda item: item[0].start()) if visual_matches else None
    output_qa = output_matches[-1] if output_matches else None
    if visual is not None and (
        output_qa is None or visual[0].start() > output_qa.start()
    ):
        return {
            "failure_class": visual[1],
            "frame_index": int(visual[0].group("frame")),
            "text_id": visual[0].group("text_id"),
        }
    if output_qa:
        return {
            "failure_class": "ENCODED_OUTPUT_QA_FAILED",
            "failed_checks": [
                item.strip()
                for item in output_qa.group("checks").split(",")
                if item.strip()
            ],
        }
    return None


def _relative_ref(run_root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(run_root.resolve()).as_posix(),
        "sha256": _sha256_file(path),
    }


def _geometry_overlap_over_smaller(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    def rect(value: Mapping[str, Any]) -> tuple[float, float, float, float]:
        x = float(value.get("x") or 0.0)
        y = float(value.get("y") or 0.0)
        width = float(value.get("width") or 0.0)
        height = float(value.get("height") or 0.0)
        return x, y, x + width, y + height

    a = rect(left)
    b = rect(right)
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min(
        max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1]),
        max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]),
    )
    return intersection / smaller if smaller > 0 else 0.0


def _duplicate_output_residual_tracks(
    target: Mapping[str, Any],
    *,
    tracks: Sequence[Mapping[str, Any]],
    frame_index: int,
) -> list[dict[str, Any]]:
    target_coverage = dict(target.get("output_residual_coverage") or {})
    source_text = str(target_coverage.get("source_text") or "").strip()
    vi_text = str(target.get("text_vi") or "").strip()
    if (
        not str(target.get("text_id") or "").startswith("p4out_")
        or not source_text
        or not vi_text
        or not str(target_coverage.get("status") or "").startswith(
            "OPERATOR_APPROVED_SOURCE_"
        )
    ):
        return []
    candidates: list[tuple[float, dict[str, Any]]] = []
    for raw in tracks:
        row = dict(raw)
        if (
            str(row.get("text_id") or "")
            == str(target.get("text_id") or "")
            or not (
                int(row.get("start_frame") or 0)
                <= int(frame_index)
                <= int(row.get("end_frame") or -1)
            )
            or str(row.get("text_vi") or "").strip() != vi_text
        ):
            continue
        coverage = dict(row.get("output_residual_coverage") or {})
        if (
            str(coverage.get("source_text") or "").strip() != source_text
            or not str(coverage.get("status") or "").startswith(
                "OPERATOR_APPROVED_SOURCE_"
            )
        ):
            continue
        overlap = _geometry_overlap_over_smaller(
            dict(target.get("geometry") or {}),
            dict(row.get("geometry") or {}),
        )
        if overlap >= 0.70:
            candidates.append((overlap, row))
    return [
        {
            "text_id": duplicate.get("text_id"),
            "content_id": duplicate.get("content_id"),
            "source_text": source_text,
            "text_vi": vi_text,
            "geometry_overlap_over_smaller": round(overlap, 6),
            "span": [duplicate.get("start_frame"), duplicate.get("end_frame")],
            "coverage_status": dict(
                duplicate.get("output_residual_coverage") or {}
            ).get("status"),
            "geometry_aligned": bool(
                dict(
                    dict(duplicate.get("render_policy") or {}).get("context")
                    or {}
                ).get("output_residual_geometry_aligned")
            ),
        }
        for overlap, duplicate in sorted(
            candidates, key=lambda item: (-item[0], str(item[1].get("text_id") or ""))
        )
    ]


def _duplicate_output_residual_track(
    target: Mapping[str, Any],
    *,
    tracks: Sequence[Mapping[str, Any]],
    frame_index: int,
) -> dict[str, Any] | None:
    rows = _duplicate_output_residual_tracks(
        target, tracks=tracks, frame_index=frame_index
    )
    return rows[0] if rows else None


def _duplicate_output_residual_track_group(
    target: Mapping[str, Any],
    duplicate_tracks: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if len(duplicate_tracks) <= 1:
        return None
    target_context = dict(
        dict(target.get("render_policy") or {}).get("context") or {}
    )
    group_rows = [
        {
            "text_id": target.get("text_id"),
            "geometry_aligned": bool(
                target_context.get("output_residual_geometry_aligned")
            ),
            "span": [target.get("start_frame"), target.get("end_frame")],
        },
        *[dict(row) for row in duplicate_tracks],
    ]
    canonical = max(
        group_rows,
        key=lambda row: (
            bool(row.get("geometry_aligned")),
            int(list(row.get("span") or [0, -1])[1])
            - int(list(row.get("span") or [0, -1])[0]),
            str(row.get("text_id") or ""),
        ),
    )
    canonical_id = str(canonical.get("text_id") or "")
    return {
        "canonical_track_id": canonical_id,
        "drop_track_ids": sorted(
            str(row.get("text_id") or "")
            for row in group_rows
            if str(row.get("text_id") or "") != canonical_id
        ),
        "tracks": group_rows,
    }


def _mask_recommendation(
    *, track: Mapping[str, Any], diagnostics: Mapping[str, Any]
) -> str:
    rows = list(diagnostics.get("tracks") or [])
    mask = dict(dict(rows[-1] if rows else {}).get("mask") or {})
    temporal = dict(dict(rows[-1] if rows else {}).get("temporal") or {})
    context = dict(dict(dict(track.get("render_policy") or {}).get("context") or {}))
    if (
        str(mask.get("fallback") or "") == "reference_plate"
        and str(temporal.get("mode") or "") == "spatial_fallback"
        and bool(context.get("micro_ui"))
        and bool(context.get("output_residual_bounded_dense_mask"))
    ):
        return "CANDIDATE_BOUNDED_MICRO_UI_SPATIAL_FALLBACK"
    reasons = {str(value) for value in list(mask.get("blocked_reasons") or [])}
    if not str(track.get("text_vi") or "").strip():
        return "REVIEW_DROP_OR_EXPLICIT_COVER_ONLY_AUTHORITY"
    if "mask_empty" in reasons:
        return "REVIEW_TRACK_TIMING_GEOMETRY_OR_REFERENCE_PLATE"
    if reasons & {"mask_too_dense_for_ink", "mask_frame_fraction"}:
        return "CANDIDATE_DYNAMIC_MASK_OR_CAPTION_PANEL_FALLBACK"
    if "mask_outside_cover_roi" in reasons:
        return "REVIEW_COVER_ROI_PADDING"
    return "REVIEW_MASK_POLICY_WITHOUT_THRESHOLD_RELAXATION"


def _build_mask_case(
    run_root: Path,
    case_root: Path,
    failure: Mapping[str, Any],
) -> dict[str, Any]:
    import cv2
    import numpy as np

    contract_path = case_root / "phase4_render_input.json"
    raw_contract = _load_object(contract_path)
    contract, remediation_ref = apply_visual_remediation(
        case_root,
        raw_contract,
        contract_path=contract_path,
    )
    text_id = str(failure["text_id"])
    frame_index = int(failure["frame_index"])
    tracks = [
        dict(item)
        for item in list(contract.get("render_tracks") or [])
        if isinstance(item, Mapping) and str(item.get("text_id") or "") == text_id
    ]
    if len(tracks) != 1:
        raise ValueError(f"Expected one render track for {case_root.name}/{text_id}")
    track = tracks[0]
    duplicate_tracks = _duplicate_output_residual_tracks(
        track,
        tracks=list(contract.get("render_tracks") or []),
        frame_index=frame_index,
    )
    duplicate_track = duplicate_tracks[0] if duplicate_tracks else None
    duplicate_group = _duplicate_output_residual_track_group(
        track, duplicate_tracks
    )
    source = _source_path(case_root)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Cannot open source for {case_root.name}")
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError(f"Cannot decode frame {frame_index} for {case_root.name}")

    renderer = AdaptiveFrameRenderer()
    _seed_reference_plates(source, contract, renderer)
    _seed_representative_masks(source, contract, renderer)
    try:
        _rendered, diagnostics = renderer.render_frame(frame, [track])
    except AdaptiveRenderBlocked as exc:
        diagnostics = dict(exc.diagnostics or {})
    policy = dict(track.get("render_policy") or {})
    roi = dict(dict(policy.get("cover") or {}).get("roi") or {})
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = _roi_pixels(
        roi,
        frame_width=width,
        frame_height=height,
    )
    mask = renderer.mask_builder(frame, track)
    overlay = frame.copy()
    green = np.zeros_like(frame)
    green[:, :, 1] = 255
    selected = mask > 0
    overlay[selected] = np.clip(
        frame[selected].astype(np.float32) * 0.45
        + green[selected].astype(np.float32) * 0.55,
        0,
        255,
    ).astype(np.uint8)
    cv2.rectangle(overlay, (x0, y0), (max(x0, x1 - 1), max(y0, y1 - 1)), (0, 0, 255), 2)
    pad = 32
    cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
    cx1, cy1 = min(width, x1 + pad), min(height, y1 + pad)
    evidence_dir = case_root / "qa" / "phase4_mask_failure_triage"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    source_path = evidence_dir / f"{text_id}_frame_{frame_index:06d}_source.jpg"
    overlay_path = evidence_dir / f"{text_id}_frame_{frame_index:06d}_mask.jpg"
    if not cv2.imwrite(str(source_path), frame[cy0:cy1, cx0:cx1]):
        raise ValueError("Cannot write mask source evidence")
    if not cv2.imwrite(str(overlay_path), overlay[cy0:cy1, cx0:cx1]):
        raise ValueError("Cannot write mask overlay evidence")
    failure_class = str(failure.get("failure_class") or "")
    if (
        str(dict(dict(list(diagnostics.get("tracks") or [{}])[-1]).get("mask") or {}).get("fallback") or "")
        == "reference_plate"
        and str(dict(dict(list(diagnostics.get("tracks") or [{}])[-1]).get("temporal") or {}).get("mode") or "")
        == "spatial_fallback"
    ):
        failure_class = "REFERENCE_PLATE_ALIGNMENT_BLOCKED"
    return {
        "case_id": case_root.name,
        **dict(failure),
        "failure_class": failure_class,
        "authority_refs": {
            "phase4_input": _relative_ref(run_root, contract_path),
            "visual_remediation": remediation_ref,
        },
        "track": {
            "text_id": text_id,
            "content_id": track.get("content_id"),
            "text_vi": track.get("text_vi"),
            "kind": track.get("kind"),
            "start_frame": track.get("start_frame"),
            "end_frame": track.get("end_frame"),
            "geometry": dict(track.get("geometry") or {}),
            "render_policy": policy,
        },
        "diagnostics": diagnostics,
        "recommendation": (
            "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP"
            if duplicate_group is not None
            else "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK"
            if duplicate_track is not None
            else _mask_recommendation(
                track=track,
                diagnostics=diagnostics,
            )
        ),
        **(
            {"duplicate_output_residual_track": duplicate_track}
            if duplicate_track is not None
            else {}
        ),
        **(
            {"duplicate_output_residual_track_group": duplicate_group}
            if duplicate_group is not None
            else {}
        ),
        "evidence": {
            "source_crop": _relative_ref(run_root, source_path),
            "mask_overlay": _relative_ref(run_root, overlay_path),
        },
    }


def _build_output_qa_case(
    run_root: Path,
    case_root: Path,
    failure: Mapping[str, Any],
) -> dict[str, Any]:
    qa_path = case_root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    qa = _load_object(qa_path)
    residual = dict(qa.get("residual_cjk") or {})
    contact_sheet = (
        case_root
        / "qa"
        / "phase4_adaptive_visual_preview_output_qa"
        / str(dict(qa.get("artifacts") or {}).get("contact_sheet") or "")
    )
    evidence: dict[str, Any] = {"output_qa": _relative_ref(run_root, qa_path)}
    if contact_sheet.is_file():
        evidence["contact_sheet"] = _relative_ref(run_root, contact_sheet)
    return {
        "case_id": case_root.name,
        **dict(failure),
        "output_qa": {
            "status": qa.get("status"),
            "failed_checks": list(qa.get("failed_checks") or []),
            "max_extra_flicker": dict(qa.get("temporal_flicker") or {}).get(
                "max_extra_flicker"
            ),
            "blocking_residual_cjk_count": len(
                list(residual.get("detections") or [])
            ),
            "blocking_residual_cjk": list(residual.get("detections") or []),
        },
        "recommendation": "UPSTREAM_GEOMETRY_REMEDIATION_THEN_RERENDER",
        "evidence": evidence,
    }


def build_triage(
    run_root: str | Path,
    *,
    output_stem: str = "phase4_visual_failure_triage_v22_4",
    include_visual_qa_failed: bool = False,
    mask_failure_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    output_qa_failure_overrides: Sequence[str] = (),
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    state_path = root / "batch_regression_state.json"
    state = _load_object(state_path)
    cases: list[dict[str, Any]] = []
    explicit_case_ids = {
        *(
            str(case_id)
            for case_id in dict(mask_failure_overrides or {}).keys()
        ),
        *(str(case_id) for case_id in output_qa_failure_overrides),
    }
    for raw in list(state.get("cases") or []):
        allowed_statuses = {"FAILED"}
        if include_visual_qa_failed:
            allowed_statuses.add("VISUAL_PREVIEW_QA_FAILED")
        if (
            not isinstance(raw, Mapping)
            or str(raw.get("status") or "") not in allowed_statuses
        ):
            continue
        if explicit_case_ids and str(raw.get("case_id") or "") not in explicit_case_ids:
            continue
        case_root = root / str(raw.get("case_id") or "")
        log_path = case_root / "logs" / "phase4_visual.log"
        if not log_path.is_file():
            continue
        override = dict(
            dict(mask_failure_overrides or {}).get(str(raw.get("case_id") or ""))
            or {}
        )
        output_override = str(raw.get("case_id") or "") in {
            str(value) for value in output_qa_failure_overrides
        }
        if override and output_override:
            raise ValueError("Case cannot have both mask and Output QA overrides")
        if output_override:
            qa = _load_object(
                case_root
                / "qa"
                / "phase4_adaptive_visual_preview_output_qa.json"
            )
            failure = {
                "failure_class": "ENCODED_OUTPUT_QA_FAILED",
                "failed_checks": list(qa.get("failed_checks") or []),
            }
        else:
            failure = (
                {
                    "failure_class": "MASK_QUALITY_BLOCKED",
                    "frame_index": int(override.get("frame_index") or 0),
                    "text_id": str(override.get("text_id") or ""),
                }
                if override
                else classify_failure(log_path.read_text(encoding="utf-8"))
            )
        if failure is None:
            continue
        if failure["failure_class"] in {
            "MASK_QUALITY_BLOCKED",
            "REFERENCE_PLATE_ALIGNMENT_BLOCKED",
        }:
            row = _build_mask_case(root, case_root, failure)
        else:
            row = _build_output_qa_case(root, case_root, failure)
        row["log_ref"] = _relative_ref(root, log_path)
        if override or output_override:
            row["failure_observation"] = {
                "source": "direct_phase4_rerun",
                **(
                    {
                        "frame_index": int(override.get("frame_index") or 0),
                        "text_id": str(override.get("text_id") or ""),
                    }
                    if override
                    else {"failed_checks": list(failure.get("failed_checks") or [])}
                ),
            }
        cases.append(row)
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_failure_triage_v1",
        "status": "REMEDIATION_PROPOSAL_REQUIRED",
        "created_at": _now(),
        "batch_state_ref": _relative_ref(root, state_path),
        "counts": {
            "failed_cases": len(cases),
            "mask_quality_blocked": sum(
                row["failure_class"] == "MASK_QUALITY_BLOCKED" for row in cases
            ),
            "reference_plate_alignment_blocked": sum(
                row["failure_class"] == "REFERENCE_PLATE_ALIGNMENT_BLOCKED"
                for row in cases
            ),
            "encoded_output_qa_failed": sum(
                row["failure_class"] == "ENCODED_OUTPUT_QA_FAILED" for row in cases
            ),
        },
        "cases": cases,
        "automatic_policy_changes_applied": False,
        "operator_approval_required": True,
    }
    payload["artifact_sha256"] = _sha256_json(payload)
    json_path = root / f"{output_stem}.json"
    _write_json_atomic(json_path, payload)
    lines = [
        "# Phase 4 Visual Failure Triage V22.4",
        "",
        f"- Status: `{payload['status']}`",
        f"- Failed cases: `{payload['counts']['failed_cases']}`",
        f"- Mask-quality blocks: `{payload['counts']['mask_quality_blocked']}`",
        f"- Reference-plate alignment blocks: "
        f"`{payload['counts']['reference_plate_alignment_blocked']}`",
        f"- Encoded-output QA failures: `{payload['counts']['encoded_output_qa_failed']}`",
        f"- Artifact SHA-256: `{payload['artifact_sha256']}`",
        "- Automatic policy changes applied: `false`",
        "",
        "| Case | Class | Frame/Checks | Track | Recommendation | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for row in cases:
        detail = (
            str(row.get("frame_index"))
            if row["failure_class"] == "MASK_QUALITY_BLOCKED"
            else ", ".join(row.get("failed_checks") or [])
        )
        track = str(row.get("text_id") or "-")
        evidence = dict(row.get("evidence") or {})
        evidence_path = str(
            dict(evidence.get("mask_overlay") or evidence.get("contact_sheet") or {}).get(
                "path"
            )
            or "-"
        )
        evidence_link = f"[open]({evidence_path})" if evidence_path != "-" else "-"
        lines.append(
            f"| `{row['case_id']}` | `{row['failure_class']}` | `{detail}` | "
            f"`{track}` | `{row['recommendation']}` | {evidence_link} |"
        )
    markdown_path = root / f"{output_stem.upper()}.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_visual_failure_triage"
    )
    parser.add_argument("run_root")
    parser.add_argument(
        "--output-stem", default="phase4_visual_failure_triage_v22_4"
    )
    parser.add_argument(
        "--include-visual-qa-failed", action="store_true"
    )
    parser.add_argument(
        "--mask-failure",
        action="append",
        default=[],
        help="Direct rerun observation formatted as case_id:frame_index:text_id.",
    )
    parser.add_argument(
        "--output-qa-failure",
        action="append",
        default=[],
        help="Case id whose latest direct rerun reached encoded Output QA failure.",
    )
    args = parser.parse_args()
    try:
        overrides: dict[str, dict[str, Any]] = {}
        for raw in list(args.mask_failure or []):
            parts = str(raw).split(":")
            if (
                len(parts) != 3
                or not parts[0]
                or not parts[1].isdigit()
                or not parts[2]
            ):
                raise ValueError("Invalid --mask-failure value")
            if parts[0] in overrides:
                raise ValueError("Duplicate --mask-failure case")
            overrides[parts[0]] = {
                "frame_index": int(parts[1]),
                "text_id": parts[2],
            }
        result = build_triage(
            args.run_root,
            output_stem=args.output_stem,
            include_visual_qa_failed=bool(args.include_visual_qa_failed),
            mask_failure_overrides=overrides,
            output_qa_failure_overrides=list(args.output_qa_failure or []),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[PHASE4-VISUAL-FAILURE-TRIAGE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "counts": result["counts"],
                "artifact_sha256": result["artifact_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
