"""Read-only, hash-bound rights/music review pack for pending E2E cases."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class PipelineRightsReviewPackError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineRightsReviewPackError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise PipelineRightsReviewPackError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], field: str, label: str) -> str:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise PipelineRightsReviewPackError(f"{label} self-hash is invalid")
    return claimed


def _verified_item(package_root: Path, raw_ref: Mapping[str, Any], label: str) -> Path:
    relative = str(raw_ref.get("path") or "")
    path = (package_root / relative).resolve()
    if (
        not relative
        or not path.is_relative_to(package_root)
        or not path.is_file()
        or path.stat().st_size != int(raw_ref.get("size_bytes") or -1)
        or _sha256_file(path) != str(raw_ref.get("sha256") or "")
    ):
        raise PipelineRightsReviewPackError(f"Package item is stale: {label}")
    return path


def _case_review(root: Path, state_case: Mapping[str, Any]) -> dict[str, Any]:
    final_approval = _load(root / "phase5_final_approval.json")
    metadata_approval = _load(root / "phase5_metadata_approval.json")
    handoff = _load(root / "phase5_export_handoff.json")
    render_meta = _load(root / "phase4_adaptive_render_meta.json")
    phase1_meta = _load(root / "phase1_meta.json")
    final_approval_sha = _verify_self_hash(
        final_approval, "approval_sha256", "Final approval"
    )
    metadata_approval_sha = _verify_self_hash(
        metadata_approval, "approval_sha256", "Metadata approval"
    )
    if str(final_approval.get("status") or "") != "FINAL_APPROVED":
        raise PipelineRightsReviewPackError(f"Final approval missing for {root.name}")
    if str(metadata_approval.get("status") or "") != "METADATA_APPROVED":
        raise PipelineRightsReviewPackError(f"Metadata approval missing for {root.name}")
    if str(handoff.get("status") or "") != "READY_FOR_RIGHTS_REVIEW":
        raise PipelineRightsReviewPackError(f"Rights gate is not pending for {root.name}")

    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise PipelineRightsReviewPackError(f"Invalid package root for {root.name}")
    manifest = _load(package_root / "manifest.json")
    manifest_sha = _verify_self_hash(manifest, "manifest_sha256", "Package manifest")
    if manifest_sha != str(dict(handoff.get("package") or {}).get("manifest_sha256") or ""):
        raise PipelineRightsReviewPackError(f"Package handoff drifted for {root.name}")
    items = dict(manifest.get("items") or {})
    video_path = _verified_item(package_root, dict(items.get("video") or {}), "video")
    metadata_path = _verified_item(
        package_root, dict(items.get("metadata_approval") or {}), "metadata approval"
    )
    package_metadata = _load(metadata_path)
    if package_metadata != metadata_approval:
        raise PipelineRightsReviewPackError(f"Metadata package copy drifted for {root.name}")
    final_video_sha = _sha256_file(root / "phase4_adaptive_final.mp4")
    approved_final_ref = dict(dict(final_approval.get("refs") or {}).get("final_video") or {})
    if (
        final_video_sha != str(approved_final_ref.get("sha256") or "")
        or final_video_sha != _sha256_file(video_path)
        or final_video_sha != str(render_meta.get("output_video_sha256") or "")
    ):
        raise PipelineRightsReviewPackError(f"Final video authority drifted for {root.name}")

    source_path = Path(str(phase1_meta.get("video") or ""))
    source_sha = _sha256_file(source_path) if source_path.is_file() else None
    expected_source_sha = str(state_case.get("source_video_sha256") or "")
    if not source_sha or source_sha != expected_source_sha:
        raise PipelineRightsReviewPackError(f"Source video authority drifted for {root.name}")
    audio_mix = dict(render_meta.get("audio_mix") or {})
    background_ref = dict(dict(final_approval.get("refs") or {}).get("background_attachment") or {})
    background_sha = str(background_ref.get("sha256") or "") or None
    source = dict(final_approval.get("source_video") or {})
    external_id = str(source.get("external_id") or state_case.get("source_video_external_id") or "")
    return {
        "case_id": root.name,
        "source_video_external_id": external_id,
        "status": "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED",
        "evidence_valid": True,
        "source_video_sha256": source_sha,
        "final_video_sha256": final_video_sha,
        "final_approval_sha256": final_approval_sha,
        "metadata_approval_sha256": metadata_approval_sha,
        "package_manifest_sha256": manifest_sha,
        "target_platform": metadata_approval.get("target_platform"),
        "retained_audio": {
            "strategy": audio_mix.get("strategy"),
            "background_present": bool(audio_mix.get("background_present")),
            "background_gain": audio_mix.get("background_gain"),
            "background_attachment_sha256": background_sha,
        },
        "required_attestations": [
            "source_video_reuse_authorized",
            "retained_music_use_on_target_platform_authorized",
            "operator_accepts_responsibility_for_rights_claim",
        ],
        "approval_token": f"SOURCE_RIGHTS_AND_MUSIC_APPROVED_{external_id}_V23",
        "external_publish_triggered": False,
    }


def write_pipeline_rights_review_pack(
    run_root: str | Path, *, case_ids: list[str] | None = None
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    state = _load(run / "batch_regression_state.json")
    _verify_self_hash(state, "run_sha256", "Batch regression state")
    selected = set(case_ids or [])
    rows = [
        dict(row)
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping)
        and str(row.get("status") or "")
        == "WAITING_SOURCE_RIGHTS_AND_MUSIC_REVIEW"
        and (not selected or str(row.get("case_id") or "") in selected)
    ]
    if not rows:
        raise PipelineRightsReviewPackError("No pending rights-review cases found")
    cases = []
    for row in sorted(rows, key=lambda value: str(value.get("case_id") or "")):
        case_id = str(row.get("case_id") or "")
        root = run / case_id
        if not root.is_dir():
            raise PipelineRightsReviewPackError(f"Missing artifact root: {case_id}")
        cases.append(_case_review(root, row))
    pack: dict[str, Any] = {
        "schema_version": "pipeline_rights_music_review_pack_v1",
        "status": "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run.name,
        "case_count": len(cases),
        "all_evidence_valid": all(bool(row["evidence_valid"]) for row in cases),
        "cases": cases,
        "authority_boundary": {
            "operator_decision_recorded": False,
            "external_publish_authorized": False,
            "external_publish_triggered": False,
        },
    }
    pack["review_pack_sha256"] = _sha256_json(pack)
    json_path = run / "pipeline_rights_music_review_pack.json"
    temporary = json_path.with_suffix(json_path.suffix + ".tmp")
    temporary.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(json_path)
    lines = [
        "# Pipeline Rights And Music Review Pack",
        "",
        f"- Status: `{pack['status']}`",
        f"- Cases: `{pack['case_count']}`",
        f"- Evidence valid: `{pack['all_evidence_valid']}`",
        f"- Review pack SHA-256: `{pack['review_pack_sha256']}`",
        "- External publish authorized/triggered: `false/false`",
        "",
        "| Case | Audio strategy | Background | Gain | Approval token |",
        "|---|---|---|---:|---|",
    ]
    for case in cases:
        audio = dict(case["retained_audio"])
        lines.append(
            f"| `{case['source_video_external_id']}` | `{audio.get('strategy')}` | "
            f"`{audio.get('background_present')}` | {audio.get('background_gain')} | "
            f"`{case['approval_token']}` |"
        )
    lines.extend(
        [
            "",
            "This pack is read-only. It verifies evidence but does not attest rights, "
            "create a publish authorization, or call an external platform.",
        ]
    )
    markdown_path = run / "PIPELINE_RIGHTS_MUSIC_REVIEW_PACK.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pack

