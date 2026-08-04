"""Hash-bound local final approval and export package for the Phase 4 pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from src.enums import PublishTargetPlatform
from src.risk.scanners.rule_based import scan_publish_draft
from src.services.publish_draft_helpers import validate_publish_draft_payload
from src.services.publish_targets import get_target_config
from src.storage.local import to_windows_long_path


class LocalFinalHandoffError(RuntimeError):
    pass


CoverGenerator = Callable[[Path, Path], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with to_windows_long_path(path.resolve()).open("rb") as handle:
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
    try:
        value = json.loads(
            to_windows_long_path(path.resolve()).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalFinalHandoffError(f"Cannot read valid {path.name}") from exc
    if not isinstance(value, dict):
        raise LocalFinalHandoffError(f"{path.name} must contain a JSON object")
    return value


def _write_json_atomic(path: Path, payload: Any) -> None:
    resolved = path.resolve()
    temporary = resolved.with_suffix(resolved.suffix + ".tmp")
    to_windows_long_path(resolved.parent).mkdir(parents=True, exist_ok=True)
    temporary_fs = to_windows_long_path(temporary)
    target_fs = to_windows_long_path(resolved)
    temporary_fs.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_fs.replace(target_fs)


def _write_text_atomic(path: Path, value: str) -> None:
    resolved = path.resolve()
    temporary = resolved.with_suffix(resolved.suffix + ".tmp")
    to_windows_long_path(resolved.parent).mkdir(parents=True, exist_ok=True)
    temporary_fs = to_windows_long_path(temporary)
    target_fs = to_windows_long_path(resolved)
    temporary_fs.write_text(value, encoding="utf-8")
    temporary_fs.replace(target_fs)


def _copy_atomic(source: Path, target: Path) -> None:
    resolved_source = source.resolve()
    resolved_target = target.resolve()
    temporary = resolved_target.with_suffix(resolved_target.suffix + ".tmp")
    to_windows_long_path(resolved_target.parent).mkdir(parents=True, exist_ok=True)
    source_fs = to_windows_long_path(resolved_source)
    temporary_fs = to_windows_long_path(temporary)
    target_fs = to_windows_long_path(resolved_target)
    shutil.copyfile(source_fs, temporary_fs)
    temporary_fs.replace(target_fs)


def _create_zip_atomic(source: Path, target: Path) -> None:
    resolved_source = source.resolve()
    resolved_target = target.resolve()
    temporary = resolved_target.with_suffix(resolved_target.suffix + ".tmp")
    source_fs = to_windows_long_path(resolved_source)
    target_fs = to_windows_long_path(resolved_target)
    temporary_fs = to_windows_long_path(temporary)
    to_windows_long_path(resolved_target.parent).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(temporary_fs, mode="w", allowZip64=True) as archive:
        for item in sorted(source_fs.rglob("*"), key=lambda value: value.as_posix()):
            if not item.is_file() or item.name.endswith(".tmp"):
                continue
            relative = item.relative_to(source_fs)
            archive_name = (Path(resolved_source.name) / relative).as_posix()
            compress_type = (
                zipfile.ZIP_STORED
                if item.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png"}
                else zipfile.ZIP_DEFLATED
            )
            archive.write(item, archive_name, compress_type=compress_type)
    temporary_fs.replace(target_fs)


def _default_cover_generator(video: Path, output: Path) -> None:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "1.0",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        raise LocalFinalHandoffError("Could not generate export cover from final video")


def _artifact_ref(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise LocalFinalHandoffError("Final approval artifact is outside the artifact root")
    resolved_fs = to_windows_long_path(resolved)
    if not resolved_fs.is_file() or resolved_fs.stat().st_size <= 0:
        raise LocalFinalHandoffError(f"Required artifact is missing: {path.name}")
    return {
        "path": resolved.relative_to(root).as_posix(),
        "sha256": _sha256_file(resolved),
        "size_bytes": resolved_fs.stat().st_size,
    }


def _verify_package_integrity(
    *,
    package_root: Path,
    manifest: dict[str, Any],
    handoff: dict[str, Any],
) -> None:
    claimed_manifest_sha256 = str(manifest.get("manifest_sha256") or "")
    unsigned_manifest = dict(manifest)
    unsigned_manifest.pop("manifest_sha256", None)
    if (
        len(claimed_manifest_sha256) != 64
        or _sha256_json(unsigned_manifest) != claimed_manifest_sha256
    ):
        raise LocalFinalHandoffError("Export package manifest hash is invalid")
    handoff_manifest_sha256 = str(
        dict(handoff.get("package") or {}).get("manifest_sha256") or ""
    )
    if handoff_manifest_sha256 != claimed_manifest_sha256:
        raise LocalFinalHandoffError("Export handoff does not match package manifest")
    items = manifest.get("items")
    if not isinstance(items, dict) or not items:
        raise LocalFinalHandoffError("Export package manifest has no items")
    for name, raw_item in items.items():
        if not isinstance(raw_item, dict):
            raise LocalFinalHandoffError(f"Invalid package item: {name}")
        relative = str(raw_item.get("path") or "")
        item_path = (package_root / relative).resolve()
        if not item_path.is_relative_to(package_root) or not item_path.is_file():
            raise LocalFinalHandoffError(f"Package item is missing: {name}")
        if item_path.stat().st_size != int(raw_item.get("size_bytes") or -1):
            raise LocalFinalHandoffError(f"Package item size changed: {name}")
        if _sha256_file(item_path) != str(raw_item.get("sha256") or ""):
            raise LocalFinalHandoffError(f"Package item hash changed: {name}")


def record_local_final_approval(
    *,
    root_dir: str | Path,
    source_video_id: str,
    source_video_external_id: str,
    operator_id: str,
) -> dict[str, Any]:
    """Record only FINAL_APPROVED; export/package creation remains a later step."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise LocalFinalHandoffError("Artifact root and operator id are required")

    final_video = root / "phase4_adaptive_final.mp4"
    render_meta_path = root / "phase4_adaptive_render_meta.json"
    output_qa_path = root / "qa" / "phase4_adaptive_final_output_qa.json"
    render_recipe_path = root / "phase4_render_recipe.json"
    visual_approval_path = root / "phase4_visual_approval.json"
    audio_approval_path = root / "phase4_audio_approval.json"
    phase3_closeout_path = root / "phase3_closeout.json"

    render_meta = _load_object(render_meta_path)
    output_qa = _load_object(output_qa_path)
    visual_approval = _load_object(visual_approval_path)
    audio_approval = _load_object(audio_approval_path)
    phase3_closeout = _load_object(phase3_closeout_path)
    if str(render_meta.get("status") or "") != "FINAL_RENDERED":
        raise LocalFinalHandoffError("Final render is not FINAL_RENDERED")
    if str(render_meta.get("output_qa_status") or "") != "PASS":
        raise LocalFinalHandoffError("Final render metadata does not record passing QA")
    if str(output_qa.get("status") or "") != "PASS" or list(
        output_qa.get("failed_checks") or []
    ):
        raise LocalFinalHandoffError("Encoded-output QA did not pass")
    if str(visual_approval.get("status") or "") != "VISUAL_APPROVED":
        raise LocalFinalHandoffError("Visual approval is missing")
    if str(audio_approval.get("status") or "") != "AUDIO_APPROVED":
        raise LocalFinalHandoffError("Audio approval is missing")
    if str(phase3_closeout.get("status") or "") != "PHASE3_CLOSED":
        raise LocalFinalHandoffError("Phase 3 closeout is missing")

    final_ref = _artifact_ref(root, final_video)
    if final_ref["sha256"] != str(render_meta.get("output_video_sha256") or ""):
        raise LocalFinalHandoffError("Final video hash does not match render metadata")
    refs = {
        "final_video": final_ref,
        "output_qa": _artifact_ref(root, output_qa_path),
        "render_meta": _artifact_ref(root, render_meta_path),
        "render_recipe": _artifact_ref(root, render_recipe_path),
        "visual_approval": _artifact_ref(root, visual_approval_path),
        "audio_approval": _artifact_ref(root, audio_approval_path),
        "phase3_closeout": _artifact_ref(root, phase3_closeout_path),
    }
    background_attachment = root / "phase4_background_attachment.json"
    if background_attachment.is_file():
        refs["background_attachment"] = _artifact_ref(root, background_attachment)

    versioned_path = root / "final_approvals" / f"final_{final_ref['sha256']}.json"
    if versioned_path.is_file():
        approval = _load_object(versioned_path)
        unsigned = dict(approval)
        claimed_sha256 = str(unsigned.pop("approval_sha256", ""))
        existing_final = dict(dict(approval.get("refs") or {}).get("final_video") or {})
        if (
            str(approval.get("status") or "") != "FINAL_APPROVED"
            or existing_final.get("sha256") != final_ref["sha256"]
            or len(claimed_sha256) != 64
            or _sha256_json(unsigned) != claimed_sha256
        ):
            raise LocalFinalHandoffError("Existing versioned final approval is invalid")
    else:
        approval = {
            "schema_version": "phase5_final_approval_v1",
            "status": "FINAL_APPROVED",
            "approved_at": _now(),
            "operator_id": operator,
            "source_video": {
                "id": str(source_video_id),
                "external_id": str(source_video_external_id),
            },
            "refs": refs,
            "external_publish_triggered": False,
        }
        approval["approval_sha256"] = _sha256_json(approval)
        _write_json_atomic(versioned_path, approval)
    _write_json_atomic(root / "phase5_final_approval.json", approval)
    return approval


def create_local_final_handoff(
    *,
    root_dir: str | Path,
    source_video_id: str,
    source_video_external_id: str,
    operator_id: str,
    cover_generator: CoverGenerator | None = None,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise LocalFinalHandoffError("Artifact root and operator id are required")

    final_video = root / "phase4_adaptive_final.mp4"
    render_meta_path = root / "phase4_adaptive_render_meta.json"
    output_qa_path = root / "qa" / "phase4_adaptive_final_output_qa.json"
    render_recipe_path = root / "phase4_render_recipe.json"
    visual_approval_path = root / "phase4_visual_approval.json"
    audio_approval_path = root / "phase4_audio_approval.json"
    phase3_closeout_path = root / "phase3_closeout.json"

    render_meta = _load_object(render_meta_path)
    output_qa = _load_object(output_qa_path)
    visual_approval = _load_object(visual_approval_path)
    audio_approval = _load_object(audio_approval_path)
    phase3_closeout = _load_object(phase3_closeout_path)
    if str(render_meta.get("status") or "") != "FINAL_RENDERED":
        raise LocalFinalHandoffError("Final render is not FINAL_RENDERED")
    if str(render_meta.get("output_qa_status") or "") != "PASS":
        raise LocalFinalHandoffError("Final render metadata does not record passing QA")
    if str(output_qa.get("status") or "") != "PASS" or list(
        output_qa.get("failed_checks") or []
    ):
        raise LocalFinalHandoffError("Encoded-output QA did not pass")
    if str(visual_approval.get("status") or "") != "VISUAL_APPROVED":
        raise LocalFinalHandoffError("Visual approval is missing")
    if str(audio_approval.get("status") or "") != "AUDIO_APPROVED":
        raise LocalFinalHandoffError("Audio approval is missing")
    if str(phase3_closeout.get("status") or "") != "PHASE3_CLOSED":
        raise LocalFinalHandoffError("Phase 3 closeout is missing")

    final_ref = _artifact_ref(root, final_video)
    if final_ref["sha256"] != str(render_meta.get("output_video_sha256") or ""):
        raise LocalFinalHandoffError("Final video hash does not match render metadata")

    approval_refs = {
        "final_video": final_ref,
        "output_qa": _artifact_ref(root, output_qa_path),
        "render_meta": _artifact_ref(root, render_meta_path),
        "render_recipe": _artifact_ref(root, render_recipe_path),
        "visual_approval": _artifact_ref(root, visual_approval_path),
        "audio_approval": _artifact_ref(root, audio_approval_path),
        "phase3_closeout": _artifact_ref(root, phase3_closeout_path),
    }
    background_attachment = root / "phase4_background_attachment.json"
    if background_attachment.is_file():
        approval_refs["background_attachment"] = _artifact_ref(
            root, background_attachment
        )
    versioned_approval_path = (
        root / "final_approvals" / f"final_{final_ref['sha256']}.json"
    )
    if versioned_approval_path.is_file():
        final_approval = _load_object(versioned_approval_path)
        existing_final = dict(dict(final_approval.get("refs") or {}).get("final_video") or {})
        if (
            str(final_approval.get("status") or "") != "FINAL_APPROVED"
            or existing_final.get("sha256") != final_ref["sha256"]
        ):
            raise LocalFinalHandoffError("Existing versioned final approval is invalid")
    else:
        final_approval = {
            "schema_version": "phase5_final_approval_v1",
            "status": "FINAL_APPROVED",
            "approved_at": _now(),
            "operator_id": operator,
            "source_video": {
                "id": str(source_video_id),
                "external_id": str(source_video_external_id),
            },
            "refs": approval_refs,
            "external_publish_triggered": False,
        }
        final_approval["approval_sha256"] = _sha256_json(final_approval)
        _write_json_atomic(versioned_approval_path, final_approval)
    final_approval_path = root / "phase5_final_approval.json"
    _write_json_atomic(final_approval_path, final_approval)

    package_key = f"{source_video_external_id}_{final_ref['sha256'][:12]}"
    package_root = root / "export_packages" / package_key
    package_video = package_root / "final_video.mp4"
    package_cover = package_root / "cover.jpg"
    _copy_atomic(final_video, package_video)
    (cover_generator or _default_cover_generator)(package_video, package_cover)
    if not package_cover.is_file() or package_cover.stat().st_size <= 0:
        raise LocalFinalHandoffError("Export cover is missing after generation")

    publish_draft = {
        "schema_version": "local_publish_draft_v1",
        "status": "DRAFT_REVIEW_REQUIRED",
        "target_platform": None,
        "title": "",
        "caption": "",
        "hashtags": [],
        "cta": "",
        "schedule_at": None,
        "required_operator_fields": ["target_platform", "title", "caption"],
        "external_publish_triggered": False,
    }
    publish_draft_path = package_root / "publish_draft.json"
    _write_json_atomic(publish_draft_path, publish_draft)
    _copy_atomic(final_approval_path, package_root / "final_approval.json")

    package_manifest = {
        "schema_version": "local_export_package_v1",
        "status": "READY_FOR_OPERATOR_HANDOFF",
        "created_at": _now(),
        "package_id": package_key,
        "source_video": final_approval["source_video"],
        "final_approval_sha256": final_approval["approval_sha256"],
        "items": {
            "video": _artifact_ref(package_root, package_video),
            "cover": _artifact_ref(package_root, package_cover),
            "publish_draft": _artifact_ref(package_root, publish_draft_path),
            "final_approval": _artifact_ref(
                package_root, package_root / "final_approval.json"
            ),
        },
        "diagnostics": {
            "warnings": ["PUBLISH_METADATA_REVIEW_REQUIRED"],
            "external_publish_triggered": False,
        },
    }
    package_manifest["manifest_sha256"] = _sha256_json(package_manifest)
    package_manifest_path = package_root / "manifest.json"
    _write_json_atomic(package_manifest_path, package_manifest)

    handoff = {
        "schema_version": "local_export_handoff_v1",
        "status": "READY_FOR_OPERATOR",
        "created_at": _now(),
        "operator_id": operator,
        "package": {
            "path": package_root.relative_to(root).as_posix(),
            "manifest_sha256": package_manifest["manifest_sha256"],
        },
        "publish_metadata_status": publish_draft["status"],
        "external_publish_triggered": False,
    }
    _write_json_atomic(root / "phase5_export_handoff.json", handoff)
    return {
        "final_approval": final_approval,
        "package_manifest": package_manifest,
        "handoff": handoff,
        "package_root": package_root,
    }


def update_local_publish_metadata(
    *,
    root_dir: str | Path,
    target_platform: str,
    title: str,
    caption: str,
    cta_text: str,
    hashtags: list[str],
    generation_source: str = "operator_assisted_local_v1",
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    if str(handoff.get("status") or "") != "READY_FOR_OPERATOR":
        raise LocalFinalHandoffError("Local export handoff is not ready")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")
    manifest_path = package_root / "manifest.json"
    manifest = _load_object(manifest_path)
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )
    platform = PublishTargetPlatform(str(target_platform))
    config = get_target_config(platform)
    clean_title = str(title or "").strip()
    clean_caption = str(caption or "").strip()
    clean_cta = str(cta_text or "").strip()
    clean_tags = list(
        dict.fromkeys(
            str(tag or "").strip().lstrip("#")
            for tag in hashtags
            if str(tag or "").strip().lstrip("#")
        )
    )
    if not clean_title:
        raise LocalFinalHandoffError("Publish title is required")
    if len(clean_tags) > config.hashtag_limit:
        raise LocalFinalHandoffError(
            f"Hashtags exceed {platform} limit ({config.hashtag_limit})"
        )
    hashtag_rows = [
        {"tag": tag, "source": generation_source} for tag in clean_tags
    ]
    draft_for_validation = SimpleNamespace(
        target_platform=platform,
        caption=clean_caption,
        cta_text=clean_cta,
        hashtags_json=hashtag_rows,
    )
    validation_errors = validate_publish_draft_payload(draft_for_validation)
    if validation_errors:
        raise LocalFinalHandoffError(
            "Publish metadata validation failed: " + "; ".join(validation_errors)
        )
    findings = scan_publish_draft(draft_for_validation)
    risk_findings = [
        {
            "risk_type": str(finding.risk_type),
            "severity": str(finding.severity),
            "title": finding.title,
            "evidence_summary": finding.evidence_summary,
        }
        for finding in findings
    ]
    publish_draft = {
        "schema_version": "local_publish_draft_v1",
        "status": "METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED",
        "target_platform": str(platform),
        "title": clean_title,
        "caption": clean_caption,
        "cta_text": clean_cta,
        "hashtags": hashtag_rows,
        "language_code": "vi",
        "schedule_at": None,
        "generation_source": generation_source,
        "validation": {
            "caption_max_length": config.caption_max_length,
            "hashtag_limit": config.hashtag_limit,
            "post_text_length": len(clean_caption + " " + clean_cta),
            "errors": [],
        },
        "risk_findings": risk_findings,
        "operator_review": {
            "status": "PENDING_OPERATOR_REVIEW",
            "approved_at": None,
            "operator_id": None,
        },
        "external_publish_triggered": False,
    }
    draft_path = package_root / "publish_draft.json"
    _write_json_atomic(draft_path, publish_draft)

    items = dict(manifest.get("items") or {})
    items["publish_draft"] = _artifact_ref(package_root, draft_path)
    manifest["items"] = items
    diagnostics = dict(manifest.get("diagnostics") or {})
    diagnostics["warnings"] = [
        "OPERATOR_METADATA_APPROVAL_REQUIRED",
        "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED",
    ]
    diagnostics["metadata_validation_errors"] = []
    diagnostics["risk_findings"] = risk_findings
    diagnostics["external_publish_triggered"] = False
    manifest["diagnostics"] = diagnostics
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _sha256_json(manifest)
    _write_json_atomic(manifest_path, manifest)

    handoff["package"]["manifest_sha256"] = manifest["manifest_sha256"]
    handoff["publish_metadata_status"] = publish_draft["status"]
    handoff["external_publish_triggered"] = False
    _write_json_atomic(handoff_path, handoff)
    return {
        "publish_draft": publish_draft,
        "package_manifest": manifest,
        "handoff": handoff,
        "package_root": package_root,
    }


def approve_local_publish_metadata(
    *,
    root_dir: str | Path,
    operator_id: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise LocalFinalHandoffError("Artifact root and operator id are required")

    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    handoff_status = str(handoff.get("status") or "")
    if handoff_status not in {"READY_FOR_OPERATOR", "READY_FOR_RIGHTS_REVIEW"}:
        raise LocalFinalHandoffError("Local export handoff cannot approve metadata")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")

    manifest_path = package_root / "manifest.json"
    manifest = _load_object(manifest_path)
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )
    draft_path = package_root / "publish_draft.json"
    publish_draft = _load_object(draft_path)

    if handoff_status == "READY_FOR_RIGHTS_REVIEW":
        approval_path = package_root / "metadata_approval.json"
        approval = _load_object(approval_path)
        draft_ref = _artifact_ref(package_root, draft_path)
        approved_ref = dict(approval.get("publish_draft_ref") or {})
        if (
            str(publish_draft.get("status") or "") != "METADATA_APPROVED"
            or str(approval.get("status") or "") != "METADATA_APPROVED"
            or approved_ref.get("sha256") != draft_ref["sha256"]
        ):
            raise LocalFinalHandoffError("Existing metadata approval is invalid")
        return {
            "metadata_approval": approval,
            "publish_draft": publish_draft,
            "package_manifest": manifest,
            "handoff": handoff,
            "package_root": package_root,
        }

    if (
        str(publish_draft.get("status") or "")
        != "METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED"
    ):
        raise LocalFinalHandoffError("Publish metadata draft is not ready for approval")
    if list(dict(publish_draft.get("validation") or {}).get("errors") or []):
        raise LocalFinalHandoffError("Publish metadata has validation errors")
    if list(publish_draft.get("risk_findings") or []):
        raise LocalFinalHandoffError(
            "Publish metadata risk findings require a separate operator decision"
        )
    if bool(publish_draft.get("external_publish_triggered")):
        raise LocalFinalHandoffError("Publish metadata already triggered external work")

    manifest_draft_ref = dict(dict(manifest.get("items") or {}).get("publish_draft") or {})
    candidate_ref = _artifact_ref(package_root, draft_path)
    if manifest_draft_ref.get("sha256") != candidate_ref["sha256"]:
        raise LocalFinalHandoffError("Publish draft does not match package manifest")
    draft_history = package_root / "publish_drafts"
    _copy_atomic(
        draft_path,
        draft_history / f"draft_{candidate_ref['sha256']}.json",
    )

    approved_at = _now()
    approved_draft = dict(publish_draft)
    approved_draft["status"] = "METADATA_APPROVED"
    approved_draft["operator_review"] = {
        "status": "METADATA_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
    }
    approved_draft["approval_checkpoint"] = {
        "supersedes_publish_draft_sha256": candidate_ref["sha256"],
        "external_publish_triggered": False,
    }
    approved_draft["external_publish_triggered"] = False
    _write_json_atomic(draft_path, approved_draft)
    approved_draft_ref = _artifact_ref(package_root, draft_path)
    _copy_atomic(
        draft_path,
        draft_history / f"draft_{approved_draft_ref['sha256']}.json",
    )

    approval = {
        "schema_version": "local_publish_metadata_approval_v1",
        "status": "METADATA_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
        "source_video": dict(manifest.get("source_video") or {}),
        "target_platform": approved_draft.get("target_platform"),
        "publish_draft_ref": approved_draft_ref,
        "final_approval_sha256": manifest.get("final_approval_sha256"),
        "next_gate": "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED",
        "external_publish_triggered": False,
    }
    approval["approval_sha256"] = _sha256_json(approval)
    versioned_approval_path = (
        root
        / "metadata_approvals"
        / f"metadata_{approved_draft_ref['sha256']}.json"
    )
    if versioned_approval_path.is_file():
        existing = _load_object(versioned_approval_path)
        if existing != approval:
            raise LocalFinalHandoffError(
                "Versioned metadata approval conflicts with current approval"
            )
    else:
        _write_json_atomic(versioned_approval_path, approval)
    _write_json_atomic(root / "phase5_metadata_approval.json", approval)
    package_approval_path = package_root / "metadata_approval.json"
    _write_json_atomic(package_approval_path, approval)

    items = dict(manifest.get("items") or {})
    items["publish_draft"] = approved_draft_ref
    items["metadata_approval"] = _artifact_ref(
        package_root, package_approval_path
    )
    manifest["items"] = items
    manifest["status"] = "READY_FOR_RIGHTS_REVIEW"
    diagnostics = dict(manifest.get("diagnostics") or {})
    diagnostics["warnings"] = ["SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED"]
    diagnostics["metadata_approval_sha256"] = approval["approval_sha256"]
    diagnostics["external_publish_triggered"] = False
    manifest["diagnostics"] = diagnostics
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _sha256_json(manifest)
    _write_json_atomic(manifest_path, manifest)

    handoff["status"] = "READY_FOR_RIGHTS_REVIEW"
    handoff["package"]["manifest_sha256"] = manifest["manifest_sha256"]
    handoff["publish_metadata_status"] = "METADATA_APPROVED"
    handoff["metadata_approval"] = {
        "path": versioned_approval_path.relative_to(root).as_posix(),
        "sha256": approval["approval_sha256"],
    }
    handoff["next_gate"] = "SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED"
    handoff["external_publish_triggered"] = False
    _write_json_atomic(handoff_path, handoff)
    return {
        "metadata_approval": approval,
        "publish_draft": approved_draft,
        "package_manifest": manifest,
        "handoff": handoff,
        "package_root": package_root,
    }


def approve_local_source_rights_and_music(
    *,
    root_dir: str | Path,
    operator_id: str,
    verification_method: str = "EXPLICIT_OPERATOR_ATTESTATION",
    attestation_overrides: dict[str, Any] | None = None,
    evidence_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record operator rights attestation without authorizing a publish call."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise LocalFinalHandoffError("Artifact root and operator id are required")

    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    handoff_status = str(handoff.get("status") or "")
    allowed_statuses = {
        "READY_FOR_RIGHTS_REVIEW",
        "READY_FOR_MANUAL_PUBLISH_HANDOFF",
    }
    if handoff_status not in allowed_statuses:
        raise LocalFinalHandoffError("Local export handoff cannot approve rights")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")

    manifest_path = package_root / "manifest.json"
    manifest = _load_object(manifest_path)
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )

    if handoff_status == "READY_FOR_MANUAL_PUBLISH_HANDOFF":
        approval = _load_object(package_root / "rights_music_approval.json")
        if (
            str(approval.get("status") or "")
            != "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
            or str(handoff.get("source_rights_and_music_status") or "")
            != "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
            or bool(approval.get("external_publish_triggered"))
        ):
            raise LocalFinalHandoffError("Existing rights and music approval is invalid")
        return {
            "rights_music_approval": approval,
            "package_manifest": manifest,
            "handoff": handoff,
            "package_root": package_root,
        }

    publish_draft = _load_object(package_root / "publish_draft.json")
    if str(publish_draft.get("status") or "") != "METADATA_APPROVED":
        raise LocalFinalHandoffError("Metadata must be approved before rights review")
    items = dict(manifest.get("items") or {})
    video_ref = dict(items.get("video") or {})
    metadata_item_ref = dict(items.get("metadata_approval") or {})
    if not video_ref or not metadata_item_ref:
        raise LocalFinalHandoffError("Rights approval inputs are missing from package")
    metadata_approval = _load_object(package_root / "metadata_approval.json")
    metadata_approval_sha256 = str(
        metadata_approval.get("approval_sha256") or ""
    )
    unsigned_metadata_approval = dict(metadata_approval)
    unsigned_metadata_approval.pop("approval_sha256", None)
    if (
        str(metadata_approval.get("status") or "") != "METADATA_APPROVED"
        or len(metadata_approval_sha256) != 64
        or _sha256_json(unsigned_metadata_approval) != metadata_approval_sha256
    ):
        raise LocalFinalHandoffError("Metadata approval authority is invalid")
    if metadata_item_ref.get("sha256") != _sha256_file(
        package_root / "metadata_approval.json"
    ):
        raise LocalFinalHandoffError("Metadata approval does not match package")

    final_approval = _load_object(package_root / "final_approval.json")
    final_refs = dict(final_approval.get("refs") or {})
    background_attachment_ref = dict(final_refs.get("background_attachment") or {})
    target_platform = str(metadata_approval.get("target_platform") or "")
    if target_platform != "FACEBOOK_REELS":
        raise LocalFinalHandoffError(
            "Local rights approval pilot only supports FACEBOOK_REELS"
        )

    binding = {
        "final_video_sha256": video_ref.get("sha256"),
        "metadata_approval_sha256": metadata_approval_sha256,
        "target_platform": target_platform,
    }
    binding_sha256 = _sha256_json(binding)
    approved_at = _now()
    attestations = {
        "source_video_reuse_authorized": True,
        "retained_music_use_on_target_platform_authorized": True,
        "operator_accepts_responsibility_for_rights_claim": True,
    }
    attestations.update(dict(attestation_overrides or {}))
    evidence = {
        "source": "explicit_operator_attestation",
        "supporting_document_refs": [],
        "legal_review_performed": False,
    }
    evidence.update(dict(evidence_overrides or {}))
    approval = {
        "schema_version": "local_source_rights_music_approval_v1",
        "status": "SOURCE_RIGHTS_AND_MUSIC_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
        "verification_method": str(verification_method),
        "attestations": attestations,
        "scope": {
            "source_video": dict(manifest.get("source_video") or {}),
            "target_platform": target_platform,
            "final_video_ref": video_ref,
            "background_attachment_ref": background_attachment_ref or None,
            "metadata_approval_sha256": metadata_approval_sha256,
            "final_approval_sha256": manifest.get("final_approval_sha256"),
            "binding_sha256": binding_sha256,
        },
        "evidence": evidence,
        "next_gate": "EXTERNAL_PUBLISH_AUTHORIZATION_REQUIRED",
        "external_publish_triggered": False,
    }
    approval["approval_sha256"] = _sha256_json(approval)
    versioned_approval_path = (
        root / "rights_music_approvals" / f"rights_{binding_sha256}.json"
    )
    if versioned_approval_path.is_file():
        existing = _load_object(versioned_approval_path)
        if existing != approval:
            raise LocalFinalHandoffError(
                "Versioned rights approval conflicts with current approval"
            )
    else:
        _write_json_atomic(versioned_approval_path, approval)
    _write_json_atomic(root / "phase5_rights_music_approval.json", approval)
    package_approval_path = package_root / "rights_music_approval.json"
    _write_json_atomic(package_approval_path, approval)

    items["rights_music_approval"] = _artifact_ref(
        package_root, package_approval_path
    )
    manifest["items"] = items
    manifest["status"] = "READY_FOR_MANUAL_PUBLISH_HANDOFF"
    diagnostics = dict(manifest.get("diagnostics") or {})
    diagnostics["warnings"] = [
        "EXTERNAL_PUBLISH_AUTHORIZATION_REQUIRED",
        "DB_RENDER_OUTPUT_HANDOFF_NOT_PERSISTED",
    ]
    diagnostics["rights_music_approval_sha256"] = approval["approval_sha256"]
    diagnostics["rights_verification_method"] = approval["verification_method"]
    diagnostics["legal_review_performed"] = False
    diagnostics["external_publish_triggered"] = False
    manifest["diagnostics"] = diagnostics
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _sha256_json(manifest)
    _write_json_atomic(manifest_path, manifest)

    handoff["status"] = "READY_FOR_MANUAL_PUBLISH_HANDOFF"
    handoff["package"]["manifest_sha256"] = manifest["manifest_sha256"]
    handoff["source_rights_and_music_status"] = (
        "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
    )
    handoff["rights_music_approval"] = {
        "path": versioned_approval_path.relative_to(root).as_posix(),
        "sha256": approval["approval_sha256"],
    }
    handoff["next_gate"] = "EXTERNAL_PUBLISH_AUTHORIZATION_REQUIRED"
    handoff["publish_authorization_status"] = "NOT_GRANTED"
    handoff["external_publish_triggered"] = False
    _write_json_atomic(handoff_path, handoff)
    return {
        "rights_music_approval": approval,
        "package_manifest": manifest,
        "handoff": handoff,
        "package_root": package_root,
    }


def approve_public_regression_source_rights(
    *,
    root_dir: str | Path,
    operator_id: str,
    public_source_manifest_path: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    """Verify public-license evidence for a local-regression-only export.

    This does not expand the manifest's ``LOCAL_REGRESSION_ONLY`` boundary and
    does not authorize or trigger an external publish call.
    """

    root = Path(root_dir).resolve()
    workspace = Path(workspace_root).resolve()
    manifest_path = Path(public_source_manifest_path).resolve()
    manifest = _load_object(manifest_path)
    unsigned_manifest = dict(manifest)
    manifest_sha256 = str(unsigned_manifest.pop("manifest_sha256", "") or "")
    if len(manifest_sha256) != 64 or _sha256_json(unsigned_manifest) != manifest_sha256:
        raise LocalFinalHandoffError("Public source manifest self-hash is invalid")
    manifest_scope = dict(manifest.get("scope") or {})
    if (
        str(manifest_scope.get("allowed_use") or "") != "LOCAL_REGRESSION_ONLY"
        or bool(manifest_scope.get("external_reup_or_publish_authorized"))
    ):
        raise LocalFinalHandoffError("Public source manifest scope is invalid")

    final_approval = _load_object(root / "phase5_final_approval.json")
    external_id = str(dict(final_approval.get("source_video") or {}).get("external_id") or "")
    matches = [
        dict(row)
        for row in list(manifest.get("sources") or [])
        if Path(str(dict(row).get("filename") or "")).stem == external_id
    ]
    if len(matches) != 1:
        raise LocalFinalHandoffError("Public source license entry was not found")
    entry = matches[0]
    license_name = str(entry.get("license") or "")
    if license_name not in {"CC0-1.0", "CC-BY-SA-3.0", "CC-BY-SA-4.0"}:
        raise LocalFinalHandoffError("Public source license is unsupported")
    source_path = (workspace / str(entry.get("source_path") or "")).resolve()
    if (
        not source_path.is_relative_to(workspace)
        or not source_path.is_file()
        or source_path.stat().st_size != int(entry.get("size_bytes") or -1)
        or _sha256_file(source_path) != str(entry.get("sha256") or "")
    ):
        raise LocalFinalHandoffError("Public source license evidence drifted")
    no_text_review = _load_object(root / "phase1_no_text_review.json")
    approved_source = dict(no_text_review.get("source_video") or {})
    if str(approved_source.get("sha256") or "") != str(entry.get("sha256") or ""):
        raise LocalFinalHandoffError("Public license belongs to another source")

    handoff = _load_object(root / "phase5_export_handoff.json")
    package_root = (
        root / str(dict(handoff.get("package") or {}).get("path") or "")
    ).resolve()
    publish_draft = _load_object(package_root / "publish_draft.json")
    publication_text = " ".join(
        str(publish_draft.get(field) or "")
        for field in ("title", "caption", "cta_text")
    )
    if bool(entry.get("attribution_required")) and not all(
        value and value in publication_text
        for value in (
            str(entry.get("source_page_url") or ""),
            license_name,
            str(entry.get("license_url") or ""),
        )
    ):
        raise LocalFinalHandoffError("Required CC attribution is missing from metadata")

    evidence_ref = {
        "path": manifest_path.relative_to(workspace).as_posix(),
        "sha256": _sha256_file(manifest_path),
        "manifest_sha256": manifest_sha256,
        "source_page_url": entry.get("source_page_url"),
        "license": license_name,
        "license_url": entry.get("license_url"),
        "source_video_sha256": entry.get("sha256"),
    }
    return approve_local_source_rights_and_music(
        root_dir=root,
        operator_id=operator_id,
        verification_method="PUBLIC_LICENSE_MANIFEST_LOCAL_REGRESSION_ONLY",
        attestation_overrides={
            "operator_accepts_responsibility_for_rights_claim": False,
            "local_regression_only": True,
            "external_publish_authorized": False,
        },
        evidence_overrides={
            "source": "hash_bound_public_license_manifest",
            "supporting_document_refs": [evidence_ref],
            "legal_review_performed": False,
            "local_regression_only": True,
        },
    )


def finalize_local_manual_export(
    *,
    root_dir: str | Path,
    operator_id: str,
) -> dict[str, Any]:
    """Create a hash-verified manual-upload package without external publishing."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise LocalFinalHandoffError("Artifact root and operator id are required")
    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    handoff_status = str(handoff.get("status") or "")
    allowed_statuses = {
        "READY_FOR_MANUAL_PUBLISH_HANDOFF",
        "MANUAL_EXPORT_PACKAGING",
        "MANUAL_EXPORT_READY",
    }
    if handoff_status not in allowed_statuses:
        raise LocalFinalHandoffError("Local export handoff cannot be finalized manually")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")
    manifest_path = package_root / "manifest.json"
    manifest = _load_object(manifest_path)
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )

    if handoff_status == "MANUAL_EXPORT_READY":
        manual_handoff = _load_object(root / "phase5_manual_export_handoff.json")
        archive_ref = dict(manual_handoff.get("archive") or {})
        archive_path = (root / str(archive_ref.get("path") or "")).resolve()
        archive_fs = to_windows_long_path(archive_path)
        if (
            not archive_path.is_relative_to(root)
            or not archive_fs.is_file()
            or archive_fs.stat().st_size != int(archive_ref.get("size_bytes") or -1)
            or _sha256_file(archive_path) != str(archive_ref.get("sha256") or "")
            or str(manual_handoff.get("status") or "") != "MANUAL_EXPORT_READY"
            or bool(manual_handoff.get("external_publish_triggered"))
        ):
            raise LocalFinalHandoffError("Existing manual export handoff is invalid")
        return {
            "manual_export_decision": _load_object(
                package_root / "manual_export_decision.json"
            ),
            "manual_export_handoff": manual_handoff,
            "package_manifest": manifest,
            "handoff": handoff,
            "package_root": package_root,
            "archive_path": archive_path,
        }

    if handoff_status == "READY_FOR_MANUAL_PUBLISH_HANDOFF":
        if (
            str(handoff.get("source_rights_and_music_status") or "")
            != "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
            or str(handoff.get("publish_authorization_status") or "")
            != "NOT_GRANTED"
            or bool(handoff.get("external_publish_triggered"))
        ):
            raise LocalFinalHandoffError("Manual export prerequisites are incomplete")
        items = dict(manifest.get("items") or {})
        rights_approval = _load_object(package_root / "rights_music_approval.json")
        rights_approval_sha256 = str(rights_approval.get("approval_sha256") or "")
        unsigned_rights = dict(rights_approval)
        unsigned_rights.pop("approval_sha256", None)
        if (
            str(rights_approval.get("status") or "")
            != "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
            or len(rights_approval_sha256) != 64
            or _sha256_json(unsigned_rights) != rights_approval_sha256
        ):
            raise LocalFinalHandoffError("Rights and music approval is invalid")
        metadata_approval = _load_object(package_root / "metadata_approval.json")
        publish_draft = _load_object(package_root / "publish_draft.json")
        if str(publish_draft.get("status") or "") != "METADATA_APPROVED":
            raise LocalFinalHandoffError("Approved publish metadata is missing")

        input_manifest_sha256 = str(manifest.get("manifest_sha256") or "")
        binding = {
            "package_id": manifest.get("package_id"),
            "input_manifest_sha256": input_manifest_sha256,
            "final_video_sha256": dict(items.get("video") or {}).get("sha256"),
            "metadata_approval_sha256": metadata_approval.get("approval_sha256"),
            "rights_music_approval_sha256": rights_approval_sha256,
            "decision": "MANUAL_EXPORT_ONLY",
        }
        binding_sha256 = _sha256_json(binding)
        decision = {
            "schema_version": "local_manual_export_decision_v1",
            "status": "MANUAL_EXPORT_ONLY",
            "decided_at": _now(),
            "operator_id": operator,
            "scope": binding,
            "binding_sha256": binding_sha256,
            "external_publish_authorized": False,
            "external_publish_triggered": False,
        }
        decision["decision_sha256"] = _sha256_json(decision)
        versioned_decision_path = (
            root
            / "manual_export_decisions"
            / f"manual_{binding_sha256}.json"
        )
        if versioned_decision_path.is_file():
            existing = _load_object(versioned_decision_path)
            if existing != decision:
                raise LocalFinalHandoffError(
                    "Versioned manual export decision conflicts with current decision"
                )
        else:
            _write_json_atomic(versioned_decision_path, decision)
        _write_json_atomic(root / "phase5_manual_export_decision.json", decision)
        package_decision_path = package_root / "manual_export_decision.json"
        _write_json_atomic(package_decision_path, decision)

        hashtag_text = " ".join(
            f"#{str(row.get('tag') or '').lstrip('#')}"
            for row in list(publish_draft.get("hashtags") or [])
            if isinstance(row, dict) and str(row.get("tag") or "").strip()
        )
        checklist = "\n".join(
            [
                "# Manual Facebook Reels Upload Checklist",
                "",
                f"Package: `{manifest.get('package_id')}`",
                "",
                "This package does not authorize or trigger an external publish call.",
                "",
                "1. Confirm the destination Facebook Page/account.",
                "2. Upload `final_video.mp4` and select `cover.jpg` if supported.",
                "3. Copy the reviewed metadata below; recheck the preview before posting.",
                "4. Choose publish-now or schedule inside Facebook.",
                "5. Record the resulting post URL and timestamp in the operator log.",
                "",
                "## Reviewed metadata",
                "",
                f"Title: {publish_draft.get('title') or ''}",
                "",
                f"Caption: {publish_draft.get('caption') or ''}",
                "",
                f"CTA: {publish_draft.get('cta_text') or ''}",
                "",
                f"Hashtags: {hashtag_text}",
                "",
            ]
        )
        checklist_path = package_root / "MANUAL_UPLOAD_CHECKLIST.md"
        _write_text_atomic(checklist_path, checklist)

        items["manual_export_decision"] = _artifact_ref(
            package_root, package_decision_path
        )
        items["manual_upload_checklist"] = _artifact_ref(
            package_root, checklist_path
        )
        manifest["items"] = items
        manifest["status"] = "READY_FOR_MANUAL_EXPORT"
        diagnostics = dict(manifest.get("diagnostics") or {})
        diagnostics["warnings"] = [
            "MANUAL_UPLOAD_REQUIRED",
            "EXTERNAL_PUBLISH_NOT_AUTHORIZED",
            "DB_RENDER_OUTPUT_HANDOFF_NOT_PERSISTED",
        ]
        diagnostics["manual_export_decision_sha256"] = decision[
            "decision_sha256"
        ]
        diagnostics["external_publish_triggered"] = False
        manifest["diagnostics"] = diagnostics
        manifest.pop("manifest_sha256", None)
        manifest["manifest_sha256"] = _sha256_json(manifest)
        _write_json_atomic(manifest_path, manifest)

        handoff["status"] = "MANUAL_EXPORT_PACKAGING"
        handoff["package"]["manifest_sha256"] = manifest["manifest_sha256"]
        handoff["publish_authorization_status"] = "MANUAL_EXPORT_ONLY"
        handoff["manual_export_decision"] = {
            "path": versioned_decision_path.relative_to(root).as_posix(),
            "sha256": decision["decision_sha256"],
        }
        handoff["next_gate"] = "OPERATOR_MANUAL_UPLOAD"
        handoff["external_publish_triggered"] = False
        _write_json_atomic(handoff_path, handoff)
    else:
        decision = _load_object(package_root / "manual_export_decision.json")

    package_id = str(manifest.get("package_id") or package_root.name)
    archive_path = (
        root
        / "manual_exports"
        / f"{package_id}_{manifest['manifest_sha256'][:12]}.zip"
    )
    _create_zip_atomic(package_root, archive_path)
    archive_ref = {
        "path": archive_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(archive_path),
        "size_bytes": to_windows_long_path(archive_path).stat().st_size,
    }
    manual_handoff = {
        "schema_version": "local_manual_export_handoff_v1",
        "status": "MANUAL_EXPORT_READY",
        "created_at": _now(),
        "operator_id": operator,
        "package": {
            "path": package_root.relative_to(root).as_posix(),
            "manifest_sha256": manifest["manifest_sha256"],
        },
        "archive": archive_ref,
        "manual_export_decision_sha256": decision["decision_sha256"],
        "next_action": "OPERATOR_MANUAL_UPLOAD",
        "external_publish_authorized": False,
        "external_publish_triggered": False,
    }
    manual_handoff["handoff_sha256"] = _sha256_json(manual_handoff)
    _write_json_atomic(root / "phase5_manual_export_handoff.json", manual_handoff)

    handoff["status"] = "MANUAL_EXPORT_READY"
    handoff["manual_export"] = archive_ref
    handoff["manual_export_handoff_sha256"] = manual_handoff["handoff_sha256"]
    handoff["publish_authorization_status"] = "MANUAL_EXPORT_ONLY"
    handoff["next_gate"] = "OPERATOR_MANUAL_UPLOAD"
    handoff["external_publish_triggered"] = False
    _write_json_atomic(handoff_path, handoff)
    return {
        "manual_export_decision": decision,
        "manual_export_handoff": manual_handoff,
        "package_manifest": manifest,
        "handoff": handoff,
        "package_root": package_root,
        "archive_path": archive_path,
    }


def record_local_manual_upload_evidence(
    *,
    root_dir: str | Path,
    operator_id: str,
    permalink: str,
    published_at: str,
    timezone_name: str,
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Record external verification or an explicit operator-only attestation."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    clean_permalink = str(permalink or "").strip()
    clean_timezone = str(timezone_name or "").strip()
    parsed = urlparse(clean_permalink)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        not root.is_dir()
        or not operator
        or parsed.scheme != "https"
        or parsed.hostname not in {"facebook.com", "www.facebook.com"}
        or len(path_parts) != 2
        or path_parts[0] != "reel"
        or not path_parts[1].isdigit()
    ):
        raise LocalFinalHandoffError("A valid Facebook Reel permalink is required")
    try:
        published_datetime = datetime.fromisoformat(str(published_at))
    except ValueError as exc:
        raise LocalFinalHandoffError("Published time must be valid ISO-8601") from exc
    if published_datetime.tzinfo is None or not clean_timezone:
        raise LocalFinalHandoffError(
            "Published time must include an offset and timezone name"
        )

    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    handoff_status = str(handoff.get("status") or "")
    if handoff_status not in {
        "MANUAL_EXPORT_READY",
        "MANUAL_UPLOAD_DEFERRED",
        "MANUAL_UPLOAD_COMPLETED",
    }:
        raise LocalFinalHandoffError("Manual export is not ready for upload evidence")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")
    manifest = _load_object(package_root / "manifest.json")
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )
    manual_handoff = _load_object(root / "phase5_manual_export_handoff.json")
    publish_draft = _load_object(package_root / "publish_draft.json")
    normalized_permalink = f"https://www.facebook.com/reel/{path_parts[1]}"
    reported_at = published_datetime.isoformat()
    verification_payload = dict(verification or {})
    permalink_reachable = bool(verification_payload.get("permalink_reachable"))
    content_match = bool(verification_payload.get("content_match"))
    public_visibility = bool(
        verification_payload.get("public_visibility_observed")
    )
    verification_method = str(verification_payload.get("method") or "").strip()
    operator_attested_without_check = bool(
        verification_method == "OPERATOR_ATTESTATION_NO_EXTERNAL_CHECK"
        and verification_payload.get("operator_attested") is True
        and verification_payload.get("external_verification_skipped") is True
        and str(verification_payload.get("skip_reason") or "").strip()
    )
    evidence_status = (
        "MANUAL_UPLOAD_EVIDENCE_VERIFIED"
        if permalink_reachable and content_match and public_visibility
        else "MANUAL_UPLOAD_EVIDENCE_OPERATOR_ATTESTED"
        if operator_attested_without_check
        else "MANUAL_UPLOAD_EVIDENCE_MISMATCH"
    )
    binding = {
        "package_manifest_sha256": manifest.get("manifest_sha256"),
        "archive_sha256": dict(manual_handoff.get("archive") or {}).get("sha256"),
        "permalink": normalized_permalink,
        "reported_published_at": reported_at,
        "reported_timezone": clean_timezone,
    }
    binding_sha256 = _sha256_json(binding)
    evidence_path = (
        root / "manual_upload_evidence" / f"evidence_{binding_sha256}.json"
    )
    if evidence_path.is_file():
        evidence = _load_object(evidence_path)
        if str(evidence.get("status") or "") != evidence_status:
            raise LocalFinalHandoffError(
                "Existing manual upload evidence conflicts with verification"
            )
    else:
        evidence = {
            "schema_version": "local_manual_upload_evidence_v1",
            "status": evidence_status,
            "recorded_at": _now(),
            "operator_id": operator,
            "operator_report": {
                "permalink": normalized_permalink,
                "published_at": reported_at,
                "timezone": clean_timezone,
            },
            "expected_content": {
                "target_platform": publish_draft.get("target_platform"),
                "title": publish_draft.get("title"),
                "caption": publish_draft.get("caption"),
                "final_video_sha256": dict(
                    dict(manifest.get("items") or {}).get("video") or {}
                ).get("sha256"),
            },
            "verification": verification_payload,
            "binding": binding,
            "binding_sha256": binding_sha256,
            "system_external_publish_triggered": False,
        }
        evidence["evidence_sha256"] = _sha256_json(evidence)
        _write_json_atomic(evidence_path, evidence)
    _write_json_atomic(root / "phase5_manual_upload_evidence.json", evidence)

    handoff["operator_reported_manual_upload"] = True
    handoff["manual_upload_evidence_status"] = evidence_status
    handoff["manual_upload_evidence"] = {
        "path": evidence_path.relative_to(root).as_posix(),
        "sha256": evidence["evidence_sha256"],
    }
    handoff["external_publish_triggered"] = False
    if evidence_status == "MANUAL_UPLOAD_EVIDENCE_MISMATCH":
        handoff["next_gate"] = "CORRECT_MANUAL_UPLOAD_EVIDENCE_REQUIRED"
        _write_json_atomic(handoff_path, handoff)
        return {
            "status": evidence_status,
            "evidence": evidence,
            "handoff": handoff,
            "completion": None,
        }

    completion_binding = {
        "evidence_sha256": evidence["evidence_sha256"],
        "package_manifest_sha256": manifest.get("manifest_sha256"),
        "archive_sha256": dict(manual_handoff.get("archive") or {}).get("sha256"),
    }
    completion_binding_sha256 = _sha256_json(completion_binding)
    completion_path = (
        root
        / "manual_upload_completions"
        / f"completion_{completion_binding_sha256}.json"
    )
    if completion_path.is_file():
        completion = _load_object(completion_path)
    else:
        completion = {
            "schema_version": "local_manual_upload_completion_v1",
            "status": "MANUAL_UPLOAD_COMPLETED",
            "completed_at": _now(),
            "operator_id": operator,
            "permalink": normalized_permalink,
            "published_at": reported_at,
            "timezone": clean_timezone,
            "evidence_status": evidence_status,
            "binding": completion_binding,
            "binding_sha256": completion_binding_sha256,
            "system_external_publish_triggered": False,
        }
        completion["completion_sha256"] = _sha256_json(completion)
        _write_json_atomic(completion_path, completion)
    _write_json_atomic(root / "phase5_manual_upload_completion.json", completion)
    handoff["status"] = "MANUAL_UPLOAD_COMPLETED"
    handoff["manual_upload_completion"] = {
        "path": completion_path.relative_to(root).as_posix(),
        "sha256": completion["completion_sha256"],
    }
    handoff["next_gate"] = "PILOT_CLOSED"
    _write_json_atomic(handoff_path, handoff)
    return {
        "status": "MANUAL_UPLOAD_COMPLETED",
        "evidence": evidence,
        "handoff": handoff,
        "completion": completion,
    }


def defer_local_manual_upload(
    *,
    root_dir: str | Path,
    operator_id: str,
    reason: str = "operator_will_publish_later",
) -> dict[str, Any]:
    """Defer manual publication while preserving the export and evidence audit."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    clean_reason = str(reason or "").strip()
    if not root.is_dir() or not operator or not clean_reason:
        raise LocalFinalHandoffError(
            "Artifact root, operator id and deferral reason are required"
        )
    handoff_path = root / "phase5_export_handoff.json"
    handoff = _load_object(handoff_path)
    handoff_status = str(handoff.get("status") or "")
    if handoff_status not in {"MANUAL_EXPORT_READY", "MANUAL_UPLOAD_DEFERRED"}:
        raise LocalFinalHandoffError("Manual upload cannot be deferred in current state")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise LocalFinalHandoffError("Export package path is invalid")
    manifest = _load_object(package_root / "manifest.json")
    _verify_package_integrity(
        package_root=package_root,
        manifest=manifest,
        handoff=handoff,
    )
    manual_handoff = _load_object(root / "phase5_manual_export_handoff.json")
    archive_ref = dict(manual_handoff.get("archive") or {})
    archive_path = (root / str(archive_ref.get("path") or "")).resolve()
    if (
        not archive_path.is_relative_to(root)
        or not archive_path.is_file()
        or _sha256_file(archive_path) != str(archive_ref.get("sha256") or "")
    ):
        raise LocalFinalHandoffError("Manual export archive is invalid")

    binding = {
        "package_manifest_sha256": manifest.get("manifest_sha256"),
        "archive_sha256": archive_ref.get("sha256"),
        "manual_upload_evidence_sha256": dict(
            handoff.get("manual_upload_evidence") or {}
        ).get("sha256"),
        "reason": clean_reason,
    }
    binding_sha256 = _sha256_json(binding)
    deferral_path = (
        root
        / "manual_upload_deferrals"
        / f"deferral_{binding_sha256}.json"
    )
    if deferral_path.is_file():
        deferral = _load_object(deferral_path)
    else:
        deferral = {
            "schema_version": "local_manual_upload_deferral_v1",
            "status": "MANUAL_UPLOAD_DEFERRED",
            "deferred_at": _now(),
            "operator_id": operator,
            "reason": clean_reason,
            "binding": binding,
            "binding_sha256": binding_sha256,
            "resume_gate": "OPERATOR_MANUAL_UPLOAD",
            "archive_preserved": True,
            "evidence_audit_preserved": bool(
                handoff.get("manual_upload_evidence")
            ),
            "system_external_publish_triggered": False,
        }
        deferral["deferral_sha256"] = _sha256_json(deferral)
        _write_json_atomic(deferral_path, deferral)
    if str(deferral.get("status") or "") != "MANUAL_UPLOAD_DEFERRED":
        raise LocalFinalHandoffError("Existing manual upload deferral is invalid")
    _write_json_atomic(root / "phase5_manual_upload_deferral.json", deferral)

    handoff["status"] = "MANUAL_UPLOAD_DEFERRED"
    handoff["manual_upload_deferral"] = {
        "path": deferral_path.relative_to(root).as_posix(),
        "sha256": deferral["deferral_sha256"],
    }
    handoff["next_gate"] = "BATCH_REGRESSION_READY"
    handoff["manual_upload_resume_gate"] = "OPERATOR_MANUAL_UPLOAD"
    handoff["external_publish_triggered"] = False
    _write_json_atomic(handoff_path, handoff)
    return {
        "deferral": deferral,
        "handoff": handoff,
        "package_manifest": manifest,
        "archive_path": archive_path,
    }
