"""Rerun encoded Phase-4 QA without repeating deterministic frame rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.run_phase4_adaptive import _source_path
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    AdaptiveOutputQaError,
    build_local_residual_ocr_provider,
    collect_adaptive_output_qa,
    classify_source_scene_protected_cjk,
    summarize_temporal_flicker_for_verdict,
)
from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    load_residual_cjk_false_positive_approval,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    VisualRemediationError,
    apply_visual_remediation,
)


class Phase4OutputQaRerunError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4OutputQaRerunError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, Mapping):
        raise Phase4OutputQaRerunError(f"{path.name} must contain an object")
    return dict(payload)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def is_valid_audio_only_rebind(
    audit: Mapping[str, Any],
    *,
    rendered_input_sha256: str,
    current_input_sha256: str,
    current_remediation_ref: Mapping[str, Any],
) -> bool:
    invariants = dict(audit.get("invariants") or {})
    return (
        str(audit.get("status") or "") == "READY_FOR_FINAL_RENDER"
        and str(audit.get("old_phase4_input_sha256") or "")
        == str(rendered_input_sha256)
        and str(audit.get("new_phase4_input_sha256") or "")
        == str(current_input_sha256)
        and dict(audit.get("visual_remediation_ref") or {})
        == dict(current_remediation_ref)
        and bool(invariants.get("render_tracks_unchanged"))
        and bool(invariants.get("visual_remediation_operations_unchanged"))
        and bool(invariants.get("master_timeline_untouched"))
    )


def rerun_output_qa(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    contract_path = root / "phase4_render_input.json"
    meta_path = root / "phase4_adaptive_render_meta.json"
    raw_contract = _load_object(contract_path)
    meta = _load_object(meta_path)
    visual_preview = bool(meta.get("visual_preview"))
    current_input_sha256 = _sha256_file(contract_path)
    rendered_input_sha256 = str(meta.get("phase4_input_sha256") or "")
    contract, visual_remediation_ref = apply_visual_remediation(
        root,
        raw_contract,
        contract_path=contract_path,
    )
    rendered_visual_ref = meta.get("visual_remediation_ref")
    audio_rebind_path = root / "phase4_audio_authority_rebind.json"
    audio_only_rebind = (
        visual_preview
        and audio_rebind_path.is_file()
        and is_valid_audio_only_rebind(
            _load_object(audio_rebind_path),
            rendered_input_sha256=rendered_input_sha256,
            current_input_sha256=current_input_sha256,
            current_remediation_ref=visual_remediation_ref,
        )
    )
    if current_input_sha256 != rendered_input_sha256 and not audio_only_rebind:
        raise Phase4OutputQaRerunError("Phase 4 input changed after render")
    if visual_remediation_ref != rendered_visual_ref and not audio_only_rebind:
        raise Phase4OutputQaRerunError(
            "Visual remediation authority changed after render"
        )
    source = _source_path(root)
    if _sha256_file(source) != str(meta.get("source_video_sha256") or ""):
        raise Phase4OutputQaRerunError("Source video changed after render")
    video_raw = str(dict(meta.get("artifacts") or {}).get("video") or "")
    output = (root / video_raw).resolve()
    if (
        not video_raw
        or not output.is_relative_to(root)
        or not output.is_file()
        or _sha256_file(output) != str(meta.get("output_video_sha256") or "")
    ):
        raise Phase4OutputQaRerunError("Rendered video authority is stale")
    output_stem = output.stem
    qa_dir = root / "qa" / (
        "p4vp_qa" if visual_preview else "p4final_qa"
    )
    qa_path = root / "qa" / f"{output_stem}_output_qa.json"
    prior_qa_hash = _sha256_file(qa_path) if qa_path.is_file() else None
    provider = build_local_residual_ocr_provider()
    residual_false_positive_approval = (
        load_residual_cjk_false_positive_approval(
            root_dir=root,
            contract=contract,
        )
    )
    output_qa = collect_adaptive_output_qa(
        source,
        output,
        contract=contract,
        artifact_dir=qa_dir,
        ocr_provider=provider,
        require_final_audio=not visual_preview,
        residual_false_positive_approval=residual_false_positive_approval,
    )
    _write_json_atomic(qa_path, output_qa)
    passed = str(output_qa.get("status") or "") == "PASS"
    meta["status"] = (
        "VISUAL_PREVIEW_RENDERED"
        if visual_preview and passed
        else "VISUAL_PREVIEW_QA_FAILED"
        if visual_preview
        else "FINAL_RENDERED"
        if passed
        else "FINAL_OUTPUT_QA_FAILED"
    )
    meta["output_qa_status"] = output_qa.get("status")
    meta["output_qa_failed_checks"] = list(output_qa.get("failed_checks") or [])
    meta["qa_rerun"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": "output_qa_policy_update_without_render_change",
        "prior_qa_sha256": prior_qa_hash,
        "current_qa_sha256": _sha256_file(qa_path),
    }
    _write_json_atomic(meta_path, meta)
    return meta


def recalculate_output_qa_verdict(root_dir: str | Path) -> dict[str, Any]:
    """Re-evaluate a complete encoded QA artifact without repeating OCR."""

    root = Path(root_dir).resolve()
    contract_path = root / "phase4_render_input.json"
    meta_path = root / "phase4_adaptive_render_meta.json"
    raw_contract = _load_object(contract_path)
    meta = _load_object(meta_path)
    contract, remediation_ref = apply_visual_remediation(
        root, raw_contract, contract_path=contract_path
    )
    if remediation_ref != meta.get("visual_remediation_ref"):
        raise Phase4OutputQaRerunError("Visual remediation authority changed after render")
    video_raw = str(dict(meta.get("artifacts") or {}).get("video") or "")
    output = (root / video_raw).resolve()
    if (
        not output.is_relative_to(root)
        or not output.is_file()
        or _sha256_file(output) != str(meta.get("output_video_sha256") or "")
    ):
        raise Phase4OutputQaRerunError("Rendered video authority is stale")
    qa_path = root / "qa" / f"{output.stem}_output_qa.json"
    qa = _load_object(qa_path)
    residual = dict(qa.get("residual_cjk") or {})
    if not bool(residual.get("complete")) or residual.get("error"):
        raise Phase4OutputQaRerunError("Encoded residual OCR evidence is incomplete")
    reclassified_blocking, reclassified_source = classify_source_scene_protected_cjk(
        list(residual.get("detections") or []),
        contract=contract,
    )
    residual["detections"] = reclassified_blocking
    if reclassified_source:
        existing_source = list(residual.get("source_scene_protected_exclusions") or [])
        keys = {
            (int(row.get("frame_index") or 0), str(row.get("text") or ""))
            for row in existing_source
            if isinstance(row, Mapping)
        }
        existing_source.extend(
            row
            for row in reclassified_source
            if (int(row.get("frame_index") or 0), str(row.get("text") or ""))
            not in keys
        )
        residual["source_scene_protected_exclusions"] = existing_source
    qa["residual_cjk"] = residual
    temporal = dict(qa.get("temporal_flicker") or {})
    summary = summarize_temporal_flicker_for_verdict(
        list(temporal.get("frames") or []),
        contract=contract,
    )
    temporal.update(
        {
            "max_extra_flicker": summary["max_extra_flicker"],
            "limit": summary["limit"],
            "boundary_excluded_count": summary["boundary_excluded_count"],
            "frames": summary["frames"],
        }
    )
    qa["temporal_flicker"] = temporal
    checks = dict(qa.get("checks") or {})
    checks["temporal_flicker"] = float(summary["max_extra_flicker"]) <= float(
        summary["limit"]
    )
    checks["residual_cjk"] = not bool(residual.get("detections"))
    qa["checks"] = checks
    failed = [name for name, passed in checks.items() if not bool(passed)]
    qa["failed_checks"] = failed
    qa["status"] = "FAIL" if failed else "PASS"
    thresholds = dict(qa.get("thresholds") or {})
    thresholds["max_extra_flicker"] = float(summary["limit"])
    qa["thresholds"] = thresholds
    _write_json_atomic(qa_path, qa)
    visual_preview = bool(meta.get("visual_preview"))
    meta["status"] = (
        "VISUAL_PREVIEW_RENDERED"
        if visual_preview and not failed
        else "VISUAL_PREVIEW_QA_FAILED"
        if visual_preview
        else "FINAL_RENDERED"
        if not failed
        else "FINAL_OUTPUT_QA_FAILED"
    )
    meta["output_qa_status"] = qa["status"]
    meta["output_qa_failed_checks"] = failed
    meta["qa_verdict_recalculation"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": "caption_boundary_aware_flicker_policy",
        "qa_sha256": _sha256_file(qa_path),
    }
    _write_json_atomic(meta_path, meta)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.rerun_phase4_output_qa")
    parser.add_argument("artifact_root")
    parser.add_argument("--verdict-only", action="store_true")
    args = parser.parse_args()
    try:
        meta = (
            recalculate_output_qa_verdict(args.artifact_root)
            if args.verdict_only
            else rerun_output_qa(args.artifact_root)
        )
        print(
            json.dumps(
                {
                    "status": meta["status"],
                    "output_qa_status": meta["output_qa_status"],
                    "failed_checks": meta["output_qa_failed_checks"],
                    "output_video_sha256": meta["output_video_sha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        AdaptiveOutputQaError,
        Phase4ApprovalError,
        Phase4OutputQaRerunError,
        VisualRemediationError,
    ) as exc:
        print(f"[PHASE4-OUTPUT-QA-RERUN][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
