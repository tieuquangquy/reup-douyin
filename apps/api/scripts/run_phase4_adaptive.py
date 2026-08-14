"""Run the PTS-preserving adaptive Phase 4 renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.core.settings import get_settings
from src.media_pipeline.video_renderer.adaptive_video import (
    AdaptiveVideoRenderError,
    remux_adaptive_preview_as_final,
    render_adaptive_video,
)
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    AdaptiveOutputQaError,
    build_local_residual_ocr_provider,
    collect_adaptive_output_qa,
    collect_reused_visual_output_qa,
)
from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    load_residual_cjk_false_positive_approval,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    _resolve_phase1_source_path,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    VisualRemediationError,
    apply_visual_remediation,
)

logger = logging.getLogger(__name__)


class Phase4AdaptiveRunnerError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4AdaptiveRunnerError(f"Cannot read valid {path.name}") from exc


def _source_path(root: Path) -> Path:
    meta = _load_json(root / "phase1_meta.json")
    if not isinstance(meta, dict) or not str(meta.get("video") or "").strip():
        raise Phase4AdaptiveRunnerError("Phase 1 source video authority is missing")
    try:
        return _resolve_phase1_source_path(root, str(meta["video"]))
    except Phase4InputError as exc:
        raise Phase4AdaptiveRunnerError("Phase 1 source video is missing") from exc


def _approved_visual_preview_authority(
    root: Path,
    *,
    contract_path: Path,
    visual_remediation_ref: dict[str, Any] | None,
) -> tuple[Path, str, dict[str, Any]] | None:
    """Return a hash-bound PASS preview suitable for video stream reuse."""

    meta_path = root / "phase4_adaptive_render_meta.json"
    if not meta_path.is_file():
        return None
    meta = _load_json(meta_path)
    if not isinstance(meta, dict):
        return None
    contract_sha256 = _sha256_file(contract_path)
    exact_visual_authority = (
        str(meta.get("phase4_input_sha256") or "") == contract_sha256
        and dict(meta.get("visual_remediation_ref") or {})
        == dict(visual_remediation_ref or {})
    )
    audio_only_rebind_authority = _audio_only_rebind_preserves_preview(
        root,
        meta=meta,
        contract_sha256=contract_sha256,
        visual_remediation_ref=visual_remediation_ref,
    )
    if (
        str(meta.get("status") or "") != "VISUAL_PREVIEW_RENDERED"
        or str(meta.get("output_qa_status") or "") != "PASS"
        or not bool(meta.get("visual_preview"))
        or not (exact_visual_authority or audio_only_rebind_authority)
    ):
        return None
    artifacts = dict(meta.get("artifacts") or {})
    relative = str(artifacts.get("video") or "").strip()
    expected_hash = str(meta.get("output_video_sha256") or "").strip().lower()
    preview = (root / relative).resolve() if relative else root / "missing"
    if (
        not relative
        or not preview.is_relative_to(root)
        or not preview.is_file()
        or len(expected_hash) != 64
        or _sha256_file(preview) != expected_hash
    ):
        return None
    qa_relative = str(artifacts.get("output_qa") or "").strip()
    qa_path = (root / qa_relative).resolve() if qa_relative else root / "missing"
    if not qa_path.is_relative_to(root) or not qa_path.is_file():
        return None
    qa = _load_json(qa_path)
    residual = dict(qa.get("residual_cjk") or {}) if isinstance(qa, dict) else {}
    if (
        not isinstance(qa, dict)
        or str(qa.get("status") or "") != "PASS"
        or list(qa.get("failed_checks") or [])
        or not bool(residual.get("complete"))
        or list(residual.get("detections") or [])
    ):
        return None
    return preview, expected_hash, dict(qa)


def _audio_only_rebind_preserves_preview(
    root: Path,
    *,
    meta: dict[str, Any],
    contract_sha256: str,
    visual_remediation_ref: dict[str, Any] | None,
) -> bool:
    """Accept a PASS preview across a hash-bound late audio-only rebind.

    ``rebind_phase4_audio_authority`` deliberately changes the Phase-4 input
    hash after visual approval because the narration/background hashes become
    final authorities.  It also emits an empty-operation remediation artifact
    that binds the old visual contract, the new audio-bound contract and the
    exact encoded preview QA.  Treat that artifact as the visual identity
    bridge; otherwise final export needlessly renders every frame again.
    """

    ref = dict(visual_remediation_ref or {})
    relative = str(ref.get("path") or "").strip()
    expected_ref_sha = str(ref.get("sha256") or "").strip().lower()
    artifact = (root / relative).resolve() if relative else root / "missing"
    if (
        not relative
        or not artifact.is_relative_to(root)
        or not artifact.is_file()
        or len(expected_ref_sha) != 64
        or _sha256_file(artifact) != expected_ref_sha
    ):
        return False
    payload = _load_json(artifact)
    if not isinstance(payload, dict):
        return False
    authority_refs = dict(payload.get("authority_refs") or {})
    rebind = dict(authority_refs.get("audio_authority_rebind") or {})
    encoded_qa_ref = dict(authority_refs.get("encoded_output_qa") or {})
    qa_relative = str(encoded_qa_ref.get("path") or "").strip()
    qa_path = (root / qa_relative).resolve() if qa_relative else root / "missing"
    non_goals = {str(value) for value in list(payload.get("non_goals") or [])}
    return bool(
        str(payload.get("schema_version") or "")
        == "phase4_visual_remediation_v1"
        and str(payload.get("status") or "")
        == "PHASE4_VISUAL_REMEDIATION_APPROVED"
        and not list(payload.get("operations") or [])
        and "do_not_change_visual_operations" in non_goals
        and str(rebind.get("policy_version") or "")
        == "phase4_late_audio_authority_rebind_v1"
        and str(rebind.get("old_phase4_input_sha256") or "")
        == str(meta.get("phase4_input_sha256") or "")
        and str(rebind.get("new_phase4_input_sha256") or "")
        == contract_sha256
        and qa_path.is_relative_to(root)
        and qa_path.is_file()
        and _sha256_file(qa_path)
        == str(encoded_qa_ref.get("sha256") or "").lower()
    )


def run(
    root_dir: str | Path,
    *,
    visual_preview: bool,
    narration_path: str | Path | None = None,
    on_progress: Callable[[str, int | None], None] | None = None,
) -> int:
    root = Path(root_dir).resolve()
    contract_path = root / "phase4_render_input.json"
    contract = _load_json(contract_path)
    if not isinstance(contract, dict):
        raise Phase4AdaptiveRunnerError("phase4_render_input.json must be an object")
    contract, visual_remediation_ref = apply_visual_remediation(
        root,
        contract,
        contract_path=contract_path,
    )
    source = _source_path(root)
    expected_source_hash = str(
        dict(dict(contract.get("refs") or {}).get("source_video_ref") or {}).get(
            "sha256"
        )
        or ""
    )
    if not expected_source_hash or _sha256_file(source) != expected_source_hash:
        raise Phase4AdaptiveRunnerError("Source video hash does not match Phase 4 input")
    residual_false_positive_approval = (
        load_residual_cjk_false_positive_approval(
            root_dir=root,
            contract=contract,
        )
    )

    output_name = (
        "phase4_adaptive_visual_preview.mp4"
        if visual_preview
        else "phase4_adaptive_final.mp4"
    )
    output = root / output_name
    qa_path = root / "qa" / f"{Path(output_name).stem}_qa.json"
    last_percent = -10

    def progress(done: int, total: int) -> None:
        nonlocal last_percent
        percent = int((done * 100) / max(1, total))
        if percent >= last_percent + 10 or done == total:
            last_percent = percent
            logger.info(
                "phase4_adaptive_progress frames_done=%s frames_total=%s percent=%s",
                done,
                total,
                percent,
            )
        if on_progress is not None:
            # Frame rendering owns the expensive middle of this boundary.
            # Keep enough room for encode/remux and deterministic Output QA.
            mapped = 20 + int(max(0, min(100, percent)) * 0.55)
            on_progress(f"adaptive_frame_render|{done}|{max(1, total)}", mapped)

    resolved_narration = narration_path
    resolved_background = None
    if not visual_preview and resolved_narration is None:
        audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
        narration_ref = dict(audio.get("narration_ref") or {})
        storage_key = str(narration_ref.get("storage_key") or "").strip()
        candidate = (root / storage_key).resolve() if storage_key else None
        if candidate is None or not candidate.is_relative_to(root):
            raise Phase4AdaptiveRunnerError("Approved narration artifact path is invalid")
        resolved_narration = candidate
    if not visual_preview:
        audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
        background_ref = dict(audio.get("background_ref") or {})
        background_key = str(background_ref.get("storage_key") or "").strip()
        if background_key:
            candidate = (root / background_key).resolve()
            if not candidate.is_relative_to(root):
                raise Phase4AdaptiveRunnerError("Approved background artifact path is invalid")
            resolved_background = candidate
    settings = get_settings()
    preview_authority = (
        None
        if visual_preview
        else _approved_visual_preview_authority(
            root,
            contract_path=contract_path,
            visual_remediation_ref=visual_remediation_ref,
        )
    )
    if preview_authority is not None and resolved_narration is not None:
        if on_progress is not None:
            on_progress("adaptive_final_remux", 35)
        preview_path, preview_sha256, _preview_qa = preview_authority
        result = remux_adaptive_preview_as_final(
            preview_path,
            output,
            contract=contract,
            narration_path=resolved_narration,
            background_path=resolved_background,
            expected_preview_sha256=preview_sha256,
            qa_path=qa_path,
        )
    else:
        if on_progress is not None:
            on_progress("adaptive_frame_render", 20)
        result = render_adaptive_video(
            source,
            output,
            contract=contract,
            visual_preview=visual_preview,
            narration_path=resolved_narration,
            background_path=resolved_background,
            qa_path=qa_path,
            progress=progress,
            video_encoder_policy=str(settings.render_video_encoder or "auto"),
            hardware_smoke_probe=bool(settings.render_hardware_encoder_smoke_probe),
            hardware_fallback_enabled=bool(
                settings.render_hardware_encoder_fallback_enabled
            ),
        )
    if on_progress is not None:
        on_progress("adaptive_output_qa", 78)
    # Keep nested QA paths short on Windows.  Artifact roots already include
    # workspace/source/run identifiers; the previous descriptive directory
    # exceeded MAX_PATH when residual confirmation frames were added.
    output_qa_dir = root / "qa" / (
        "p4vp_qa" if visual_preview else "p4final_qa"
    )
    output_qa_path = root / "qa" / f"{Path(output_name).stem}_output_qa.json"
    meta = {
        "schema_version": "phase4_adaptive_render_meta_v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "VISUAL_PREVIEW_OUTPUT_QA_PENDING"
            if visual_preview
            else "FINAL_OUTPUT_QA_PENDING"
        ),
        "visual_preview": bool(visual_preview),
        "output_qa_status": "PENDING",
        "output_qa_failed_checks": [],
        "phase4_input_sha256": _sha256_file(contract_path),
        "visual_remediation_ref": visual_remediation_ref,
        "source_video_sha256": expected_source_hash,
        "output_video_sha256": _sha256_file(result.output_path),
        "frames": result.frame_count,
        "encoder": dict(getattr(result, "encoder_metadata", {}) or {}),
        "audio_mix": dict(getattr(result, "audio_mix_metadata", {}) or {}),
        "artifacts": {
            "video": result.output_path.relative_to(root).as_posix(),
            "qa": result.qa_path.relative_to(root).as_posix(),
            "output_qa": output_qa_path.relative_to(root).as_posix(),
        },
    }
    # Persist the encoded-video authority before local OCR.  If QA is
    # interrupted, rerun_phase4_output_qa can resume without rendering again.
    _write_json_atomic(root / "phase4_adaptive_render_meta.json", meta)
    try:
        if (
            not visual_preview
            and preview_authority is not None
            and bool(dict(getattr(result, "encoder_metadata", {}) or {}).get(
                "visual_authority_reused"
            ))
        ):
            preview_path, _preview_sha256, preview_qa = preview_authority
            output_qa = collect_reused_visual_output_qa(
                preview_path,
                result.output_path,
                preview_qa=preview_qa,
                contract=contract,
            )
        else:
            try:
                ocr_provider = build_local_residual_ocr_provider()
            except Exception as exc:  # Missing local OCR is fail-closed below.
                logger.warning(
                    "phase4_output_qa_local_ocr_unavailable error_type=%s",
                    type(exc).__name__,
                )
                ocr_provider = None
            output_qa = collect_adaptive_output_qa(
                source,
                result.output_path,
                contract=contract,
                artifact_dir=output_qa_dir,
                ocr_provider=ocr_provider,
                require_final_audio=not visual_preview,
                residual_false_positive_approval=residual_false_positive_approval,
            )
    except Exception as exc:
        # Preserve the resumable encoded-video checkpoint.  The QA exception
        # is diagnostic evidence, not proof that the already-rendered video is
        # invalid; rerun_phase4_output_qa can continue from this authority.
        meta["output_qa_error"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:1000],
        }
        _write_json_atomic(root / "phase4_adaptive_render_meta.json", meta)
        raise
    # The encoded-audio probe checks container duration, but it cannot tell
    # whether the narration stream itself was clipped at the video boundary.
    # Keep this renderer authority as a hard final gate.
    if not visual_preview and not bool(
        dict(getattr(result, "audio_mix_metadata", {}) or {}).get(
            "narration_complete"
        )
    ):
        output_qa["status"] = "FAIL"
        failed_checks = list(output_qa.get("failed_checks") or [])
        if "narration_complete" not in failed_checks:
            failed_checks.append("narration_complete")
        output_qa["failed_checks"] = failed_checks
        audio_qa = dict(output_qa.get("audio") or {})
        audio_failed = list(audio_qa.get("failed_checks") or [])
        if "narration_complete" not in audio_failed:
            audio_failed.append("narration_complete")
        audio_qa["status"] = "FAIL"
        audio_qa["failed_checks"] = audio_failed
        output_qa["audio"] = audio_qa
    _write_json_atomic(output_qa_path, output_qa)
    if on_progress is not None:
        on_progress("adaptive_output_qa_complete", 95)
    output_qa_passed = str(output_qa.get("status") or "") == "PASS"
    meta["status"] = (
        "VISUAL_PREVIEW_RENDERED"
        if visual_preview and output_qa_passed
        else "VISUAL_PREVIEW_QA_FAILED"
        if visual_preview
        else "FINAL_RENDERED"
        if output_qa_passed
        else "FINAL_OUTPUT_QA_FAILED"
    )
    meta["output_qa_status"] = output_qa.get("status")
    meta["output_qa_failed_checks"] = list(output_qa.get("failed_checks") or [])
    _write_json_atomic(root / "phase4_adaptive_render_meta.json", meta)
    if not output_qa_passed:
        failed = ",".join(str(value) for value in output_qa.get("failed_checks") or [])
        raise Phase4AdaptiveRunnerError(
            f"{'Visual preview' if visual_preview else 'Final'} output QA failed "
            f"({failed or 'unknown_check'})"
        )
    logger.info(
        "phase4_adaptive_completed status=%s frames=%s",
        meta["status"],
        result.frame_count,
    )
    if on_progress is not None:
        on_progress("adaptive_render_complete", 100)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.run_phase4_adaptive")
    parser.add_argument("phase4_output_dir")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--narration")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as exc:
        return int(exc.code)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(
            args.phase4_output_dir,
            visual_preview=not bool(args.final),
            narration_path=args.narration,
        )
    except (
        Phase4AdaptiveRunnerError,
        AdaptiveVideoRenderError,
        AdaptiveOutputQaError,
        Phase4ApprovalError,
        VisualRemediationError,
    ) as exc:
        print(f"[P4-ADAPTIVE][FAIL] {exc}", flush=True)
        return 1
    except Exception as exc:
        print(f"[P4-ADAPTIVE][FAIL] {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
