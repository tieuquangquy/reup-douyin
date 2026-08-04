"""Build a hash-bound, proposal-only dense UI panel remediation artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.run_phase4_adaptive import _source_path
from src.media_pipeline.video_renderer.visual_remediation import (
    apply_visual_remediation,
)


SCHEMA_VERSION = "phase4_dense_ui_panel_proposal_v1"
ACTION = "DENSE_UI_PANEL_FALLBACK"


class DenseUiPanelProposalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DenseUiPanelProposalError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise DenseUiPanelProposalError(f"{path.name} must contain an object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _merge_intervals(intervals: Sequence[tuple[int, int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def select_dense_epoch(
    contract: Mapping[str, Any],
    residual_frames: Sequence[int],
    *,
    max_epoch_frames: int = 120,
) -> tuple[list[int], list[dict[str, Any]]]:
    tracks: list[dict[str, Any]] = []
    intervals: list[tuple[int, int]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        track = dict(raw)
        context = dict(
            dict(track.get("render_policy") or {}).get("context") or {}
        )
        if (
            not isinstance(track.get("output_residual_coverage"), Mapping)
            or not bool(context.get("dense_ui"))
            or int(context.get("simultaneous_count") or 0) < 20
        ):
            continue
        start = int(track.get("start_frame") or 0)
        end = int(track.get("end_frame") or -1)
        if end < start:
            continue
        tracks.append(track)
        intervals.append((start, end))
    frames = [int(value) for value in residual_frames]
    candidates = [
        interval
        for interval in _merge_intervals(intervals)
        if interval[1] - interval[0] + 1 <= max_epoch_frames
        and any(interval[0] <= frame <= interval[1] for frame in frames)
    ]
    if not candidates:
        raise DenseUiPanelProposalError("No bounded dense UI epoch covers residuals")
    epoch = max(
        candidates,
        key=lambda row: sum(row[0] <= frame <= row[1] for frame in frames),
    )
    epoch_tracks = [
        track
        for track in tracks
        if int(track.get("start_frame") or 0) <= epoch[1]
        and int(track.get("end_frame") or -1) >= epoch[0]
    ]
    return epoch, epoch_tracks


def panel_roi_from_detections(
    detections: Sequence[Mapping[str, Any]],
    *,
    frame_span: Sequence[int],
    pad_x: float = 0.02,
    pad_y: float = 0.02,
) -> dict[str, float]:
    start, end = int(frame_span[0]), int(frame_span[1])
    rows = [
        dict(row.get("geometry") or {})
        for row in detections
        if start <= int(row.get("frame_index") or 0) <= end
        and isinstance(row.get("geometry"), Mapping)
    ]
    if not rows:
        raise DenseUiPanelProposalError("Dense epoch has no residual geometry")
    x0 = max(0.0, min(float(row.get("x") or 0.0) for row in rows) - pad_x)
    y0 = max(0.0, min(float(row.get("y") or 0.0) for row in rows) - pad_y)
    x1 = min(
        1.0,
        max(float(row.get("x") or 0.0) + float(row.get("width") or 0.0) for row in rows)
        + pad_x,
    )
    y1 = min(
        1.0,
        max(float(row.get("y") or 0.0) + float(row.get("height") or 0.0) for row in rows)
        + pad_y,
    )
    if x1 <= x0 or y1 <= y0:
        raise DenseUiPanelProposalError("Dense panel ROI is empty")
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _track_damage_budget(track: Mapping[str, Any]) -> float:
    return float(
        dict(dict(track.get("render_policy") or {}).get("damage_budget") or {}).get(
            "max_frame_change_fraction"
        )
        or 0.0
    )


def build_proposal(
    run_root: str | Path,
    *,
    proposal_version: str = "V22_47",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    version = str(proposal_version or "").strip().upper()
    if not re.fullmatch(r"V[0-9]+(?:_[0-9]+)*", version):
        raise DenseUiPanelProposalError("Invalid proposal version")
    contract_path = root / "phase4_render_input.json"
    qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    meta_path = root / "phase4_adaptive_render_meta.json"
    raw_contract = _load_object(contract_path)
    qa = _load_object(qa_path)
    meta = _load_object(meta_path)
    contract, remediation_ref = apply_visual_remediation(
        root, raw_contract, contract_path=contract_path
    )
    if remediation_ref != meta.get("visual_remediation_ref"):
        raise DenseUiPanelProposalError("Rendered remediation authority is stale")
    if (
        str(qa.get("status") or "") != "FAIL"
        or "residual_cjk" not in list(qa.get("failed_checks") or [])
    ):
        raise DenseUiPanelProposalError("Encoded output is not panel-proposal eligible")
    sample = dict(qa.get("sample") or {})
    if (
        int(sample.get("count") or 0) < 50
        or "bounded_dense_ui" not in str(sample.get("strategy") or "")
    ):
        raise DenseUiPanelProposalError("Bounded dense UI exhaustive QA is required")
    detections = [
        dict(row)
        for row in list(dict(qa.get("residual_cjk") or {}).get("detections") or [])
        if isinstance(row, Mapping)
    ]
    if len(detections) < 8:
        raise DenseUiPanelProposalError("Residual count does not justify panel fallback")
    epoch, epoch_tracks = select_dense_epoch(
        contract, [int(row.get("frame_index") or 0) for row in detections]
    )
    roi = panel_roi_from_detections(detections, frame_span=epoch)
    roi_area = float(roi["width"]) * float(roi["height"])
    canonical = max(
        epoch_tracks,
        key=lambda row: (
            int(
                dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                    "simultaneous_count"
                )
                or 0
            ),
            int(row.get("end_frame") or -1) - int(row.get("start_frame") or 0),
        ),
    )
    budget = _track_damage_budget(canonical)
    if budget <= 0.0 or roi_area > budget:
        raise DenseUiPanelProposalError("Dense panel exceeds existing damage budget")
    source = _source_path(root)
    preview_path = root / str(dict(meta.get("artifacts") or {}).get("video") or "")
    if not preview_path.is_file():
        raise DenseUiPanelProposalError("Rendered preview is missing")
    unique_vi = sorted(
        {
            str(track.get("text_vi") or "").strip()
            for track in epoch_tracks
            if str(track.get("text_vi") or "").strip()
        }
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "proposal_version": version,
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_approval_written": False,
        "automatic_policy_changes_applied": False,
        "case_id": root.name,
        "authority_refs": {
            "phase4_input": {"path": contract_path.name, "sha256": _sha256_file(contract_path)},
            "visual_remediation": remediation_ref,
            "output_qa": {"path": qa_path.relative_to(root).as_posix(), "sha256": _sha256_file(qa_path)},
            "rendered_preview": {"path": preview_path.name, "sha256": _sha256_file(preview_path)},
            "source_video": {"path": source.name, "sha256": _sha256_file(source)},
        },
        "trigger": {
            "qa_sample_count": int(sample.get("count") or 0),
            "residual_detection_count": len(detections),
            "residual_frame_span": [
                min(int(row.get("frame_index") or 0) for row in detections),
                max(int(row.get("frame_index") or 0) for row in detections),
            ],
            "failure_class": "DENSE_UI_RESIDUAL_CASCADE",
        },
        "decision": {
            "action": ACTION,
            "canonical_text_id": canonical.get("text_id"),
            "frame_span": epoch,
            "panel_roi": {key: round(value, 9) for key, value in roi.items()},
            "panel_area_fraction": round(roi_area, 9),
            "existing_max_frame_change_fraction": budget,
            "cover_strategy": "OPAQUE_SOURCE_AWARE_PHONE_UI_PLATE",
            "layout_strategy": "DEDUPLICATED_PRIORITY_GRID",
            "deduplication_key": "content_id_then_normalized_vi_text",
            "unique_vi_candidates": len(unique_vi),
            "max_rendered_lines": 12,
            "temporal_guard": "FIXED_PANEL_GEOMETRY_WITHIN_APPROVED_EPOCH",
            "rerender_after_approval": True,
            "output_qa_required": True,
        },
        "guards": [
            "do_not_change_damage_budget",
            "do_not_relax_mask_or_output_qa_thresholds",
            "do_not_apply_outside_approved_frame_span",
            "do_not_render_duplicate_content_lines",
            "fail_closed_if_panel_roi_or_authority_hash_changes",
        ],
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_mutate_translation_authority",
            "do_not_write_visual_approval",
            "do_not_render_from_this_proposal",
        ],
    }
    seed = _sha256_json(payload)[:12].upper()
    payload["operator_approval_token"] = (
        f"PHASE4_DENSE_UI_PANEL_PROPOSAL_APPROVED_{version}_{seed}"
    )
    payload["proposal_sha256"] = _sha256_json(payload)
    return payload


def _markdown(payload: Mapping[str, Any]) -> str:
    decision = dict(payload.get("decision") or {})
    trigger = dict(payload.get("trigger") or {})
    roi = dict(decision.get("panel_roi") or {})
    return "\n".join(
        [
            f"# Phase 4 Dense UI Panel Proposal {payload.get('proposal_version')}",
            "",
            f"- Status: `{payload.get('status')}`",
            f"- Token: `{payload.get('operator_approval_token')}`",
            f"- Proposal SHA-256: `{payload.get('proposal_sha256')}`",
            f"- Residual detections: `{trigger.get('residual_detection_count')}`",
            f"- QA samples: `{trigger.get('qa_sample_count')}`",
            f"- Frame span: `{decision.get('frame_span')}`",
            f"- Panel ROI: `x={roi.get('x')}, y={roi.get('y')}, w={roi.get('width')}, h={roi.get('height')}`",
            f"- Panel area: `{decision.get('panel_area_fraction')}` / budget `{decision.get('existing_max_frame_change_fraction')}`",
            f"- Unique VI candidates: `{decision.get('unique_vi_candidates')}`; render cap: `{decision.get('max_rendered_lines')}`",
            "",
            "Proposal only: no remediation or visual approval has been written.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_dense_ui_panel_proposal"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--proposal-version", default="V22_47")
    parser.add_argument("--output-stem")
    args = parser.parse_args()
    try:
        version = str(args.proposal_version or "").strip().lower()
        stem = str(args.output_stem or f"phase4_dense_ui_panel_proposal_{version}")
        if Path(stem).name != stem:
            raise DenseUiPanelProposalError("Invalid output stem")
        root = Path(args.artifact_root).resolve()
        payload = build_proposal(root, proposal_version=args.proposal_version)
        _write_json_atomic(root.parent / f"{stem}.json", payload)
        _write_text_atomic(root.parent / f"{stem}.md", _markdown(payload))
    except (OSError, ValueError, DenseUiPanelProposalError) as exc:
        print(f"[PHASE4-DENSE-UI-PANEL-PROPOSAL][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "operator_approval_token": payload["operator_approval_token"],
                "proposal_sha256": payload["proposal_sha256"],
                "frame_span": payload["decision"]["frame_span"],
                "panel_roi": payload["decision"]["panel_roi"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
