import hashlib
import json
from pathlib import Path

import pytest

from scripts.rebind_phase4_audio_authority import (
    Phase4AudioRebindError,
    _load_active_for_audio_rebind,
    _materialize_phase2_visual_bridge,
    _sha256_json,
    contract_with_audio_authority,
    rebind,
    residual_bundle_with_rebound_input,
)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audio_rebind_changes_only_audio_authority_and_final_gate() -> None:
    contract = {
        "status": "READY_FOR_PHASE4",
        "final_render_gate": "BLOCKED_AUDIO_AUTHORITY",
        "render_tracks": [{"text_id": "sub_01"}],
        "authorities": {
            "timebase": {"status": "READY"},
            "audio": {"status": "VISUAL_PREVIEW_ONLY"},
            "color": {"codec": "h264"},
        },
    }
    audio = {
        "status": "READY",
        "strategy": "mix_vietnamese_narration_with_background_stem",
        "narration_ref": {"storage_key": "phase4_joined_narration.wav"},
        "background_ref": {"storage_key": "phase4_background.wav"},
    }

    rebound = contract_with_audio_authority(contract, audio)

    assert rebound["final_render_gate"] == "READY_FOR_FINAL_RENDER"
    assert rebound["authorities"]["audio"] == audio
    assert rebound["authorities"]["timebase"] == contract["authorities"]["timebase"]
    assert rebound["authorities"]["color"] == contract["authorities"]["color"]
    assert rebound["render_tracks"] == contract["render_tracks"]
    assert contract["final_render_gate"] == "BLOCKED_AUDIO_AUTHORITY"


def test_audio_rebind_updates_only_residual_bundle_input_binding() -> None:
    old_hash = "a" * 64
    new_hash = "b" * 64
    bundle = {
        "schema_version": "phase4_residual_cjk_false_positive_approval_v2",
        "status": "OCR_FALSE_POSITIVES_CONFIRMED",
        "authority_refs": {
            "phase4_input": {
                "path": "phase4_render_input.json",
                "sha256": old_hash,
            },
            "immutable_output_qa": {"path": "qa.json", "sha256": "c" * 64},
        },
        "binding": {
            "source_video_sha256": "d" * 64,
            "phase4_input_sha256": old_hash,
        },
        "binding_sha256": "stale",
        "approvals": [{"cluster_id": "outres_1"}],
        "approval_sha256": "stale",
    }

    rebound = residual_bundle_with_rebound_input(
        bundle,
        old_input_sha256=old_hash,
        new_input_sha256=new_hash,
    )

    assert rebound["binding"]["phase4_input_sha256"] == new_hash
    assert rebound["authority_refs"]["phase4_input"]["sha256"] == new_hash
    assert rebound["authority_refs"]["immutable_output_qa"] == bundle["authority_refs"]["immutable_output_qa"]
    assert bundle["binding"]["phase4_input_sha256"] == old_hash


def test_phase2_residual_bridge_materializes_empty_phase4_authority(tmp_path: Path) -> None:
    preview = tmp_path / "phase4_adaptive_visual_preview.mp4"
    preview.write_bytes(b"preview-pass")
    qa_path = tmp_path / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    _write_json(qa_path, {"status": "PASS", "failed_checks": []})
    visual_approval = {
        "status": "VISUAL_APPROVED",
        "video_ref": {"sha256": _file_sha(preview)},
        "output_qa_ref": {"sha256": _file_sha(qa_path)},
    }
    _write_json(tmp_path / "phase4_visual_approval.json", visual_approval)
    phase2 = tmp_path / "phase2_residual_remediation_a.json"
    _write_json(phase2, {"status": "APPROVED"})
    phase2_ref = {
        "path": phase2.name,
        "sha256": _file_sha(phase2),
        "remediation_sha256": "b" * 64,
    }
    pointer = {
        "schema_version": "phase2_residual_remediation_active_v1",
        "status": "ACTIVE",
        "remediation_ref": phase2_ref,
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write_json(tmp_path / "phase2_residual_remediation_active.json", pointer)
    preview_meta = {
        "status": "VISUAL_PREVIEW_RENDERED",
        "output_qa_status": "PASS",
        "phase4_input_sha256": "a" * 64,
        "visual_remediation_ref": None,
    }
    contract = {"refs": {"residual_remediation_ref": phase2_ref}}

    _materialize_phase2_visual_bridge(
        tmp_path,
        contract=contract,
        preview_meta=preview_meta,
        visual_approval=visual_approval,
        output_qa={"status": "PASS"},
    )

    active = _load_active_for_audio_rebind(tmp_path)
    assert active is not None
    payload, _ = active
    assert payload["operations"] == []
    assert payload["authority_refs"]["phase2_residual_remediation"] == phase2_ref
    assert payload["authority_refs"]["phase4_input"]["sha256"] == "a" * 64


def test_phase2_residual_bridge_rejects_contract_pointer_drift(tmp_path: Path) -> None:
    preview = tmp_path / "phase4_adaptive_visual_preview.mp4"
    preview.write_bytes(b"preview-pass")
    qa_path = tmp_path / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    _write_json(qa_path, {"status": "PASS"})
    visual_approval = {
        "status": "VISUAL_APPROVED",
        "video_ref": {"sha256": _file_sha(preview)},
        "output_qa_ref": {"sha256": _file_sha(qa_path)},
    }
    _write_json(tmp_path / "phase4_visual_approval.json", visual_approval)
    phase2 = tmp_path / "phase2_residual_remediation_a.json"
    _write_json(phase2, {"status": "APPROVED"})
    phase2_ref = {"path": phase2.name, "sha256": _file_sha(phase2)}
    pointer = {"status": "ACTIVE", "remediation_ref": phase2_ref}
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write_json(tmp_path / "phase2_residual_remediation_active.json", pointer)

    with pytest.raises(Phase4AudioRebindError, match="authority is invalid"):
        _materialize_phase2_visual_bridge(
            tmp_path,
            contract={"refs": {"residual_remediation_ref": {"path": "drift"}}},
            preview_meta={
                "status": "VISUAL_PREVIEW_RENDERED",
                "output_qa_status": "PASS",
                "phase4_input_sha256": "a" * 64,
                "visual_remediation_ref": None,
            },
            visual_approval=visual_approval,
            output_qa={"status": "PASS"},
        )


def _completed_rebind_fixture(tmp_path: Path) -> dict:
    old_hash = "a" * 64
    narration = tmp_path / "phase4_joined_narration.wav"
    narration.write_bytes(b"approved-narration")
    manifest = {
        "manifest_version": "RENDER_PREP_MANIFEST_V2",
        "audio_review": {"status": "AUDIO_APPROVED"},
        "current_outputs": {
            "joined_narration": [
                {
                    "storage_key": narration.name,
                    "sha256": _file_sha(narration),
                    "mime_type": "audio/wav",
                    "duration_seconds": 1.0,
                    "audio_format": {"codec": "pcm_s16le"},
                    "role": None,
                }
            ]
        },
    }
    manifest_path = tmp_path / "render_prep_manifest.json"
    _write_json(manifest_path, manifest)
    audio_approval_path = tmp_path / "phase4_audio_approval.json"
    _write_json(
        audio_approval_path,
        {
            "status": "AUDIO_APPROVED",
            "narration_ref": {
                "path": narration.name,
                "sha256": _file_sha(narration),
            },
            "background_ref": None,
        },
    )

    audio_authority = {
        "status": "READY",
        "strategy": "replace_with_vietnamese_narration",
        "narration_ref": {
            "storage_key": narration.name,
            "sha256": _file_sha(narration),
            "mime_type": "audio/wav",
            "duration_seconds": 1.0,
            "audio_format": {"codec": "pcm_s16le"},
            "role": None,
        },
        "background_ref": None,
        "background_gain": None,
        "warnings": [],
    }
    contract = {
        "status": "READY_FOR_PHASE4",
        "authorities": {"audio": audio_authority},
        "final_render_gate": "READY_FOR_FINAL_RENDER",
        "render_tracks": [],
    }
    contract_path = tmp_path / "phase4_render_input.json"
    _write_json(contract_path, contract)
    current_hash = _file_sha(contract_path)

    preview = tmp_path / "phase4_adaptive_visual_preview.mp4"
    preview.write_bytes(b"approved-preview")
    qa_path = tmp_path / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    _write_json(qa_path, {"status": "PASS", "failed_checks": []})
    visual_approval_path = tmp_path / "phase4_visual_approval.json"
    _write_json(
        visual_approval_path,
        {
            "status": "VISUAL_APPROVED",
            "video_ref": {"sha256": _file_sha(preview)},
            "output_qa_ref": {"sha256": _file_sha(qa_path)},
        },
    )
    _write_json(
        tmp_path / "phase4_adaptive_render_meta.json",
        {
            "status": "VISUAL_PREVIEW_RENDERED",
            "output_qa_status": "PASS",
            "phase4_input_sha256": old_hash,
        },
    )

    remediation = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "authority_refs": {
            "phase4_input": {
                "path": contract_path.name,
                "sha256": current_hash,
            },
            "audio_authority_rebind": {
                "policy_version": "phase4_late_audio_authority_rebind_v1",
                "old_phase4_input_sha256": old_hash,
                "new_phase4_input_sha256": current_hash,
                "manifest_ref": {
                    "path": manifest_path.name,
                    "sha256": _file_sha(manifest_path),
                },
                "audio_approval_ref": {
                    "path": audio_approval_path.name,
                    "sha256": _file_sha(audio_approval_path),
                },
            },
        },
        "operations": [],
    }
    remediation["materialization_sha256"] = _sha256_json(remediation)
    remediation_path = tmp_path / "phase4_visual_remediation_audio_rebind.json"
    _write_json(remediation_path, remediation)
    remediation_ref = {
        "path": remediation_path.name,
        "sha256": _file_sha(remediation_path),
        "materialization_sha256": remediation["materialization_sha256"],
    }
    pointer = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": remediation_ref,
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write_json(tmp_path / "phase4_visual_remediation_active.json", pointer)

    audit = {
        "schema_version": "phase4_audio_authority_rebind_v1",
        "status": "READY_FOR_FINAL_RENDER",
        "old_phase4_input_sha256": old_hash,
        "new_phase4_input_sha256": current_hash,
        "visual_remediation_ref": remediation_ref,
        "visual_approval_ref": {
            "path": visual_approval_path.name,
            "sha256": _file_sha(visual_approval_path),
        },
        "audio_authority": audio_authority,
    }
    audit["artifact_sha256"] = _sha256_json(audit)
    _write_json(tmp_path / "phase4_audio_authority_rebind.json", audit)
    return audit


def _rewrite_signed_audit(tmp_path: Path, audit: dict) -> None:
    audit.pop("artifact_sha256", None)
    audit["artifact_sha256"] = _sha256_json(audit)
    _write_json(tmp_path / "phase4_audio_authority_rebind.json", audit)


def test_rebind_is_idempotent_after_successful_audio_authority_rebind(
    tmp_path: Path,
) -> None:
    audit = _completed_rebind_fixture(tmp_path)
    protected_paths = [
        tmp_path / "phase4_render_input.json",
        tmp_path / "phase4_visual_remediation_active.json",
        tmp_path / "phase4_audio_authority_rebind.json",
    ]
    before = {path.name: path.read_bytes() for path in protected_paths}

    result = rebind(tmp_path)

    assert result == audit
    assert {path.name: path.read_bytes() for path in protected_paths} == before


def test_rebind_accepts_semantically_identical_retry_materialization(
    tmp_path: Path,
) -> None:
    audit = _completed_rebind_fixture(tmp_path)
    manifest_path = tmp_path / "render_prep_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["audio_review"]["approved_at"] = "later-retry"
    _write_json(manifest_path, manifest)
    approval_path = tmp_path / "phase4_audio_approval.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["approved_at"] = "later-retry"
    _write_json(approval_path, approval)

    assert rebind(tmp_path) == audit


def test_completed_rebind_rejects_invalid_audit_self_hash(tmp_path: Path) -> None:
    _completed_rebind_fixture(tmp_path)
    audit_path = tmp_path / "phase4_audio_authority_rebind.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["artifact_sha256"] = "f" * 64
    _write_json(audit_path, audit)

    with pytest.raises(Phase4AudioRebindError, match="audit is invalid"):
        rebind(tmp_path)


def test_completed_rebind_rejects_active_pointer_drift(tmp_path: Path) -> None:
    audit = _completed_rebind_fixture(tmp_path)
    audit["visual_remediation_ref"] = {
        **audit["visual_remediation_ref"],
        "sha256": "f" * 64,
    }
    _rewrite_signed_audit(tmp_path, audit)

    with pytest.raises(Phase4AudioRebindError, match="audit is invalid"):
        rebind(tmp_path)


def test_completed_rebind_rejects_audio_authority_drift(tmp_path: Path) -> None:
    audit = _completed_rebind_fixture(tmp_path)
    audit["audio_authority"] = {
        **audit["audio_authority"],
        "strategy": "tampered",
    }
    _rewrite_signed_audit(tmp_path, audit)

    with pytest.raises(Phase4AudioRebindError, match="audit is invalid"):
        rebind(tmp_path)
