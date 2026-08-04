"""Bind an approved late audio authority without changing visual operations."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.render_authority import resolve_audio_authority
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_json,
    apply_visual_remediation,
)


class Phase4AudioRebindError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4AudioRebindError(f"Cannot read valid {path.name}") from exc
    if not isinstance(value, dict):
        raise Phase4AudioRebindError(f"{path.name} must contain an object")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _load_active_for_audio_rebind(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Load a signed remediation while intentionally deferring input-hash validation.

    Final preflight can materialize the approved audio into Phase-4 input before
    this rebind runs.  The old visual authority is still trusted only when its
    pointer, artifact hash, self-hash and preview input hash all verify below.
    """
    pointer_path = root / ACTIVE_POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = _load(pointer_path)
    pointer_unsigned = dict(pointer)
    expected_pointer_hash = str(pointer_unsigned.pop("pointer_sha256", ""))
    if len(expected_pointer_hash) != 64 or _sha256_json(pointer_unsigned) != expected_pointer_hash:
        raise Phase4AudioRebindError("Visual remediation pointer self-hash is invalid")
    ref = dict(pointer.get("active_ref") or {})
    path = (root / str(ref.get("path") or "")).resolve()
    if (
        not path.is_relative_to(root)
        or not path.is_file()
        or _sha256_file(path) != str(ref.get("sha256") or "")
    ):
        raise Phase4AudioRebindError("Active visual remediation file hash drifted")
    payload = _load(path)
    unsigned = dict(payload)
    expected_materialization = str(unsigned.pop("materialization_sha256", ""))
    if (
        str(payload.get("status") or "") != "PHASE4_VISUAL_REMEDIATION_APPROVED"
        or len(expected_materialization) != 64
        or _sha256_json(unsigned) != expected_materialization
    ):
        raise Phase4AudioRebindError("Visual remediation authority is invalid")
    return payload, {
        "path": path.name,
        "sha256": _sha256_file(path),
        "materialization_sha256": expected_materialization,
    }


def contract_with_audio_authority(
    contract: Mapping[str, Any], audio_authority: Mapping[str, Any]
) -> dict[str, Any]:
    if str(audio_authority.get("status") or "") != "READY":
        raise Phase4AudioRebindError("Approved audio authority is not ready")
    updated = json.loads(json.dumps(dict(contract), ensure_ascii=False))
    authorities = dict(updated.get("authorities") or {})
    authorities["audio"] = dict(audio_authority)
    updated["authorities"] = authorities
    updated["final_render_gate"] = "READY_FOR_FINAL_RENDER"
    return updated


def residual_bundle_with_rebound_input(
    bundle: Mapping[str, Any],
    *,
    old_input_sha256: str,
    new_input_sha256: str,
) -> dict[str, Any]:
    """Rebind a v2 residual decision when only late audio authority changed."""

    value = json.loads(json.dumps(dict(bundle), ensure_ascii=False))
    binding = dict(value.get("binding") or {})
    refs = dict(value.get("authority_refs") or {})
    phase4_ref = dict(refs.get("phase4_input") or {})
    if (
        str(value.get("schema_version") or "")
        != "phase4_residual_cjk_false_positive_approval_v2"
        or str(binding.get("phase4_input_sha256") or "")
        != str(old_input_sha256)
        or str(phase4_ref.get("sha256") or "") != str(old_input_sha256)
        or not list(value.get("approvals") or [])
    ):
        raise Phase4AudioRebindError(
            "Residual false-positive bundle cannot be audio-rebound"
        )
    phase4_ref["sha256"] = str(new_input_sha256)
    refs["phase4_input"] = phase4_ref
    binding["phase4_input_sha256"] = str(new_input_sha256)
    value["authority_refs"] = refs
    value["binding"] = binding
    value["binding_sha256"] = _sha256_json(binding)
    value["audio_authority_rebind"] = {
        "status": "HASH_REBOUND_AFTER_AUDIO_ONLY_CONTRACT_CHANGE",
        "old_phase4_input_sha256": str(old_input_sha256),
        "new_phase4_input_sha256": str(new_input_sha256),
    }
    value.pop("approval_sha256", None)
    value["approval_sha256"] = _sha256_json(value)
    return value


def _verify_audio_refs(root: Path, authority: Mapping[str, Any]) -> None:
    for label in ("narration_ref", "background_ref"):
        raw = authority.get(label)
        if raw is None:
            continue
        ref = dict(raw)
        candidate = (root / str(ref.get("storage_key") or "")).resolve()
        expected = str(ref.get("sha256") or "").lower()
        if (
            not candidate.is_relative_to(root)
            or not candidate.is_file()
            or len(expected) != 64
            or _sha256_file(candidate) != expected
        ):
            raise Phase4AudioRebindError(f"{label} hash authority is invalid")


def rebind(
    case_root: str | Path,
    *,
    operator_id: str = "operator-auto-audio-authority-rebind",
) -> dict[str, Any]:
    root = Path(case_root).resolve()
    contract_path = root / "phase4_render_input.json"
    manifest_path = root / "render_prep_manifest.json"
    approval_path = root / "phase4_audio_approval.json"
    mix_approval_path = root / "phase4_background_mix_approval.json"
    visual_approval_path = root / "phase4_visual_approval.json"
    output_qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    preview_path = root / "phase4_adaptive_visual_preview.mp4"

    contract = _load(contract_path)
    active = _load_active_for_audio_rebind(root)
    if active is None:
        raise Phase4AudioRebindError("Active visual remediation is required")
    remediation, remediation_ref = active
    manifest = _load(manifest_path)
    approval = _load(approval_path)
    visual_approval = _load(visual_approval_path)
    output_qa = _load(output_qa_path)
    preview_meta = _load(root / "phase4_adaptive_render_meta.json")
    remediation_input_ref = dict(
        dict(remediation.get("authority_refs") or {}).get("phase4_input") or {}
    )
    old_input_sha256 = str(remediation_input_ref.get("sha256") or "")
    if (
        str(approval.get("status") or "") != "AUDIO_APPROVED"
        or str(visual_approval.get("status") or "") != "VISUAL_APPROVED"
        or str(output_qa.get("status") or "") != "PASS"
        or not preview_path.is_file()
        or _sha256_file(preview_path)
        != str(dict(visual_approval.get("video_ref") or {}).get("sha256") or "")
        or len(old_input_sha256) != 64
        or old_input_sha256 != str(preview_meta.get("phase4_input_sha256") or "")
    ):
        raise Phase4AudioRebindError("Visual or narration approval authority is incomplete")

    audio_authority = resolve_audio_authority(
        manifest, allow_source_passthrough=False
    )
    _verify_audio_refs(root, audio_authority)
    if audio_authority.get("background_ref") is not None:
        mix_approval = _load(mix_approval_path)
        if str(mix_approval.get("status") or "") != "AUDIO_MIX_APPROVED":
            raise Phase4AudioRebindError("Background mix approval is required")

    updated_contract = contract_with_audio_authority(contract, audio_authority)
    current_input_sha256 = _sha256_file(contract_path)
    existing_audit_path = root / "phase4_audio_authority_rebind.json"
    if old_input_sha256 == current_input_sha256 and existing_audit_path.is_file():
        existing_audit = _load(existing_audit_path)
        if (
            str(existing_audit.get("status") or "") == "READY_FOR_FINAL_RENDER"
            and str(existing_audit.get("new_phase4_input_sha256") or "")
            == current_input_sha256
        ):
            return existing_audit
    contract_temp = contract_path.with_suffix(".json.rebind.tmp")
    contract_temp.write_text(
        json.dumps(updated_contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    new_input_sha256 = _sha256_file(contract_temp)
    if new_input_sha256 == old_input_sha256:
        contract_temp.unlink(missing_ok=True)
        raise Phase4AudioRebindError("Audio authority rebind produced no contract change")

    manifest_sha256 = _sha256_file(manifest_path)
    approval_sha256 = _sha256_file(approval_path)
    rebind_key = _sha256_json(
        {
            "parent_visual_remediation": remediation_ref,
            "old_phase4_input_sha256": old_input_sha256,
            "new_phase4_input_sha256": new_input_sha256,
            "manifest_sha256": manifest_sha256,
            "audio_approval_sha256": approval_sha256,
            "audio_authority": audio_authority,
        }
    )
    rebound = json.loads(json.dumps(remediation, ensure_ascii=False))
    authority_refs = dict(rebound.get("authority_refs") or {})
    authority_refs["phase4_input"] = {
        "path": contract_path.name,
        "sha256": new_input_sha256,
    }
    authority_refs["audio_authority_rebind"] = {
        "policy_version": "phase4_late_audio_authority_rebind_v1",
        "rebind_key": rebind_key,
        "old_phase4_input_sha256": old_input_sha256,
        "new_phase4_input_sha256": new_input_sha256,
        "manifest_ref": {
            "path": manifest_path.name,
            "sha256": manifest_sha256,
        },
        "audio_approval_ref": {
            "path": approval_path.name,
            "sha256": approval_sha256,
        },
    }
    rebound["authority_refs"] = authority_refs
    rebound["operator_id"] = str(operator_id).strip()
    rebound.pop("materialization_sha256", None)
    rebound["materialization_sha256"] = _sha256_json(rebound)
    artifact_name = f"phase4_visual_remediation_{rebind_key[:12]}_audio_rebind.json"
    artifact_path = root / artifact_name
    _write(artifact_path, rebound)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": artifact_name,
            "sha256": _sha256_file(artifact_path),
            "materialization_sha256": rebound["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)

    if new_input_sha256 == current_input_sha256:
        contract_temp.unlink(missing_ok=True)
    else:
        contract_temp.replace(contract_path)
    _write(root / ACTIVE_POINTER_NAME, pointer)
    apply_visual_remediation(root, updated_contract, contract_path=contract_path)

    stale_residual_ref: dict[str, Any] | None = None
    residual_path = root / "phase4_residual_cjk_false_positive_approval.json"
    operator_exclusions = list(
        dict(output_qa.get("residual_cjk") or {}).get(
            "operator_false_positive_exclusions"
        )
        or []
    )
    residual_rebind_ref: dict[str, Any] | None = None
    if residual_path.is_file() and not operator_exclusions:
        residual_sha256 = _sha256_file(residual_path)
        stale_dir = root / "qa" / "stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        archived = stale_dir / (
            f"phase4_residual_false_positive_before_audio_rebind_"
            f"{residual_sha256[:12]}.json"
        )
        if not archived.is_file():
            residual_path.replace(archived)
        else:
            residual_path.unlink()
        stale_residual_ref = {
            "path": archived.relative_to(root).as_posix(),
            "sha256": residual_sha256,
            "reason": "latest_visual_output_qa_used_zero_operator_exclusions",
        }
    elif residual_path.is_file() and operator_exclusions:
        residual_sha256 = _sha256_file(residual_path)
        stale_dir = root / "qa" / "stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        archived = stale_dir / (
            f"phase4_residual_false_positive_before_audio_rebind_"
            f"{residual_sha256[:12]}.json"
        )
        if not archived.is_file():
            _write(archived, _load(residual_path))
        rebound_residual = residual_bundle_with_rebound_input(
            _load(residual_path),
            old_input_sha256=old_input_sha256,
            new_input_sha256=new_input_sha256,
        )
        _write(residual_path, rebound_residual)
        residual_rebind_ref = {
            "path": residual_path.name,
            "sha256": _sha256_file(residual_path),
            "previous_ref": {
                "path": archived.relative_to(root).as_posix(),
                "sha256": residual_sha256,
            },
            "reason": "audio_only_phase4_input_hash_change",
        }

    audit: dict[str, Any] = {
        "schema_version": "phase4_audio_authority_rebind_v1",
        "status": "READY_FOR_FINAL_RENDER",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": str(operator_id).strip(),
        "old_phase4_input_sha256": old_input_sha256,
        "new_phase4_input_sha256": new_input_sha256,
        "visual_remediation_ref": pointer["active_ref"],
        "visual_approval_ref": {
            "path": visual_approval_path.name,
            "sha256": _sha256_file(visual_approval_path),
        },
        "audio_authority": audio_authority,
        "stale_residual_false_positive_ref": stale_residual_ref,
        "residual_false_positive_rebind_ref": residual_rebind_ref,
        "invariants": {
            "render_tracks_unchanged": updated_contract.get("render_tracks")
            == contract.get("render_tracks"),
            "visual_remediation_operations_unchanged": rebound.get("operations")
            == remediation.get("operations"),
            "master_timeline_untouched": True,
        },
    }
    audit["artifact_sha256"] = _sha256_json(audit)
    _write(root / "phase4_audio_authority_rebind.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.rebind_phase4_audio_authority"
    )
    parser.add_argument("case_root")
    parser.add_argument(
        "--operator", default="operator-auto-audio-authority-rebind"
    )
    args = parser.parse_args()
    try:
        result = rebind(args.case_root, operator_id=args.operator)
    except (OSError, ValueError, Phase4AudioRebindError) as exc:
        print(f"[P4-AUDIO-REBIND][FAIL] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
