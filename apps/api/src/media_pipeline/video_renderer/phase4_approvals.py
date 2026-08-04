"""Durable operator checkpoints and hash-verified Phase 4 audio handoff."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.audio_pipeline.demucs_runner import run_captured
from src.storage.local import to_windows_long_path


class Phase4ApprovalError(RuntimeError):
    pass


NO_DIALOGUE_AUDIO_POLICY_VERSION = "verified_silero_no_dialogue_source_audio_v1"
DIALOGUE_UNCERTAIN_REVIEW_POLICY_VERSION = "silero_asr_conflict_operator_review_v1"


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
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def residual_detection_sha256(detection: Mapping[str, Any]) -> str:
    normalized = {
        "frame_index": int(detection.get("frame_index") or 0),
        "text": str(detection.get("text") or "").strip(),
        "confidence": round(float(detection.get("confidence") or 0.0), 4),
        "geometry": {
            key: float(dict(detection.get("geometry") or {}).get(key) or 0.0)
            for key in ("x", "y", "width", "height")
        },
    }
    return _sha256_json(normalized)


RESIDUAL_FALSE_POSITIVE_CLUSTER_MAX_SECONDS = 0.5
RESIDUAL_FALSE_POSITIVE_MIN_GEOMETRY_OVERLAP = 0.80
RESIDUAL_FALSE_POSITIVE_MIN_AREA_SIMILARITY = 0.80


def _approval_rect(detection: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(detection.get("geometry") or {})
    x = float(geometry.get("x") or 0.0)
    y = float(geometry.get("y") or 0.0)
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    return x, y, x + width, y + height


def _approval_geometry_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    smaller = min(left_area, right_area)
    return intersection / smaller if smaller > 0.0 else 0.0


def _approval_area_similarity(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    larger = max(left_area, right_area)
    return min(left_area, right_area) / larger if larger > 0.0 else 0.0


def load_residual_cjk_false_positive_approval(
    *, root_dir: str | Path, contract: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Load and validate the operator residual-CJK approval authority.

    The approval is optional.  When present, every hash binding is checked so
    post-render QA cannot silently consume a decision from another source,
    Phase 3 handoff, detection, or evidence file.
    """

    root = Path(root_dir).resolve()
    path = root / "phase4_residual_cjk_false_positive_approval.json"
    if not path.is_file():
        return None
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("Residual false-positive approval is unreadable") from exc
    if not isinstance(approval, Mapping):
        raise Phase4ApprovalError("Residual false-positive approval must be an object")
    unsigned = dict(approval)
    claimed = str(unsigned.pop("approval_sha256", "") or "")
    schema_version = str(approval.get("schema_version") or "")
    if schema_version == "phase4_residual_cjk_false_positive_approval_v2":
        if (
            str(approval.get("status") or "")
            != "OCR_FALSE_POSITIVES_CONFIRMED"
            or len(claimed) != 64
            or claimed != _sha256_json(unsigned)
        ):
            raise Phase4ApprovalError(
                "Residual false-positive bundle self-hash is invalid"
            )
        binding = dict(approval.get("binding") or {})
        if str(approval.get("binding_sha256") or "") != _sha256_json(binding):
            raise Phase4ApprovalError(
                "Residual false-positive bundle binding is invalid"
            )
        source_sha256 = str(
            dict(dict(contract.get("refs") or {}).get("source_video_ref") or {}).get(
                "sha256"
            )
            or ""
        )
        input_path = root / "phase4_render_input.json"
        if (
            not input_path.is_file()
            or str(binding.get("source_video_sha256") or "") != source_sha256
            or str(binding.get("phase4_input_sha256") or "")
            != _sha256_file(input_path)
        ):
            raise Phase4ApprovalError(
                "Residual false-positive bundle authority is stale"
            )
        authority_refs = dict(approval.get("authority_refs") or {})
        for label, raw in authority_refs.items():
            ref = dict(raw or {})
            candidate = (root / str(ref.get("path") or "")).resolve()
            if (
                not candidate.is_relative_to(root.parent)
                or not candidate.is_file()
                or _sha256_file(candidate) != str(ref.get("sha256") or "")
            ):
                raise Phase4ApprovalError(
                    f"Residual false-positive {label} authority is stale"
                )
        entries = [
            dict(row)
            for row in list(approval.get("approvals") or [])
            if isinstance(row, Mapping)
        ]
        if not entries:
            raise Phase4ApprovalError("Residual false-positive bundle is empty")
        seen_clusters: set[str] = set()
        for entry in entries:
            entry_unsigned = dict(entry)
            entry_claimed = str(entry_unsigned.pop("entry_sha256", "") or "")
            cluster_id = str(entry.get("cluster_id") or "")
            detection = dict(entry.get("detection") or {})
            detection_sha256 = residual_detection_sha256(detection)
            evidence_ref = dict(entry.get("evidence_ref") or {})
            evidence_path = (root / str(evidence_ref.get("path") or "")).resolve()
            if (
                not cluster_id
                or cluster_id in seen_clusters
                or len(entry_claimed) != 64
                or entry_claimed != _sha256_json(entry_unsigned)
                or detection_sha256 != str(entry.get("detection_sha256") or "")
                or not evidence_path.is_relative_to(root)
                or not evidence_path.is_file()
                or _sha256_file(evidence_path) != str(evidence_ref.get("sha256") or "")
            ):
                raise Phase4ApprovalError(
                    "Residual false-positive bundle entry is invalid"
                )
            cluster_hashes = list(entry.get("cluster_detection_sha256s") or [])
            if detection_sha256 not in cluster_hashes:
                raise Phase4ApprovalError(
                    "Residual false-positive cluster binding is invalid"
                )
            seen_clusters.add(cluster_id)
        return dict(approval)
    if (
        str(approval.get("status") or "") != "OCR_FALSE_POSITIVE_CONFIRMED"
        or len(claimed) != 64
        or claimed != _sha256_json(unsigned)
    ):
        raise Phase4ApprovalError("Residual false-positive approval self-hash is invalid")
    binding = dict(approval.get("binding") or {})
    if str(approval.get("binding_sha256") or "") != _sha256_json(binding):
        raise Phase4ApprovalError("Residual false-positive binding is invalid")
    detection = dict(approval.get("detection") or {})
    detection_sha256 = residual_detection_sha256(detection)
    if detection_sha256 != str(approval.get("detection_sha256") or ""):
        raise Phase4ApprovalError("Residual false-positive detection hash is invalid")
    source_sha256 = str(
        dict(dict(contract.get("refs") or {}).get("source_video_ref") or {}).get(
            "sha256"
        )
        or ""
    )
    handoff_path = root / "phase3_render_handoff.json"
    if (
        not handoff_path.is_file()
        or str(binding.get("source_video_sha256") or "") != source_sha256
        or str(binding.get("phase3_render_handoff_sha256") or "")
        != _sha256_file(handoff_path)
    ):
        raise Phase4ApprovalError("Residual false-positive approval authority is stale")
    evidence_ref = dict(approval.get("evidence_ref") or {})
    evidence_path = (root / str(evidence_ref.get("path") or "")).resolve()
    if (
        not evidence_path.is_relative_to(root)
        or not evidence_path.is_file()
        or _sha256_file(evidence_path) != str(evidence_ref.get("sha256") or "")
        or str(binding.get("evidence_sha256") or "")
        != str(evidence_ref.get("sha256") or "")
    ):
        raise Phase4ApprovalError("Residual false-positive evidence is stale")
    if (
        str(binding.get("detection_sha256") or "") != detection_sha256
        or str(binding.get("approval_token") or "")
        != str(approval.get("approval_token") or "")
    ):
        raise Phase4ApprovalError("Residual false-positive detection binding is invalid")
    return dict(approval)


def apply_residual_cjk_false_positive_approval(
    detections: Sequence[Mapping[str, Any]],
    approval: Mapping[str, Any] | None,
    *,
    fps: float = 30.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exclude only the approved OCR event and its tight temporal track peers.

    The exact approved detection is hash-bound.  Encoded output can change OCR
    confidence by a small amount, so equivalent observations are accepted only
    when text and geometry remain stable within 0.5 seconds.  Unrelated CJK
    detections stay blocking.
    """

    rows = [dict(row) for row in detections]
    if approval is None:
        return rows, []
    if (
        str(approval.get("schema_version") or "")
        == "phase4_residual_cjk_false_positive_approval_v2"
    ):
        approved_entries = [
            dict(row)
            for row in list(approval.get("approvals") or [])
            if isinstance(row, Mapping)
        ]
    else:
        approved_entries = [dict(approval)]
    for entry in approved_entries:
        approved_detection = dict(entry.get("detection") or {})
        approved_sha256 = str(entry.get("detection_sha256") or "")
        if residual_detection_sha256(approved_detection) != approved_sha256:
            raise Phase4ApprovalError(
                "Residual false-positive detection hash is invalid"
            )
    frame_tolerance = max(
        1,
        int(
            round(
                max(1.0, float(fps))
                * RESIDUAL_FALSE_POSITIVE_CLUSTER_MAX_SECONDS
            )
        ),
    )
    blocking: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in rows:
        matched: tuple[dict[str, Any], bool, int, float, float] | None = None
        for entry in approved_entries:
            approved_detection = dict(entry.get("detection") or {})
            approved_sha256 = str(entry.get("detection_sha256") or "")
            approved_frame = int(approved_detection.get("frame_index") or 0)
            approved_text = str(approved_detection.get("text") or "").strip()
            approved_rect = _approval_rect(approved_detection)
            frame_index = int(row.get("frame_index") or 0)
            frame_delta = abs(frame_index - approved_frame)
            overlap = _approval_geometry_overlap(approved_rect, _approval_rect(row))
            area_similarity = _approval_area_similarity(
                approved_rect, _approval_rect(row)
            )
            approved_cluster_hashes = list(entry.get("cluster_detection_sha256s") or [])
            geometry_similarity_floor = (
                0.40
                if len(approved_cluster_hashes) > 1
                and len(approved_text) <= 1
                else RESIDUAL_FALSE_POSITIVE_MIN_AREA_SIMILARITY
            )
            geometry_overlap_floor = (
                0.20
                if len(approved_cluster_hashes) > 1
                and len(approved_text) <= 1
                else RESIDUAL_FALSE_POSITIVE_MIN_GEOMETRY_OVERLAP
            )
            exact_hash = residual_detection_sha256(row) == approved_sha256
            cluster_match = (
                str(row.get("text") or "").strip() == approved_text
                and frame_delta <= frame_tolerance
                and overlap >= geometry_overlap_floor
                and area_similarity >= geometry_similarity_floor
            )
            if exact_hash or cluster_match:
                matched = (entry, exact_hash, frame_delta, overlap, area_similarity)
                break
        if matched is None:
            blocking.append(row)
            continue
        entry, exact_hash, frame_delta, overlap, area_similarity = matched
        approved_frame = int(dict(entry.get("detection") or {}).get("frame_index") or 0)
        excluded.append(
            {
                **row,
                "classification": "OPERATOR_CONFIRMED_OCR_FALSE_POSITIVE",
                "approval_sha256": approval.get("approval_sha256"),
                "approval_token": approval.get("approval_token"),
                "approval_cluster_id": entry.get("cluster_id"),
                "approval_entry_sha256": entry.get("entry_sha256"),
                "approval_match": {
                    "type": "EXACT_HASH" if exact_hash else "TEMPORAL_GEOMETRY_CLUSTER",
                    "approved_frame_index": approved_frame,
                    "frame_delta": frame_delta,
                    "geometry_overlap": round(overlap, 6),
                    "geometry_area_similarity": round(area_similarity, 6),
                },
            }
        )
    return blocking, excluded


def record_residual_cjk_false_positive_approval(
    *,
    root_dir: str | Path,
    frame_index: int,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    """Bind an operator false-positive decision to immutable visual evidence."""

    root = Path(root_dir).resolve()
    token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    if (
        not root.is_dir()
        or not token.startswith("OCR_FALSE_POSITIVE_CONFIRMED_")
        or not operator
    ):
        raise Phase4ApprovalError(
            "Artifact root, false-positive token and operator are required"
        )
    meta_path = root / "phase4_preflight_meta.json"
    preview_path = root / "phase4_render_input_preview.json"
    handoff_path = root / "phase3_render_handoff.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("Residual preflight authority is missing") from exc
    residual = dict(meta.get("residual_cjk") or {})
    detections = [
        dict(row)
        for row in list(residual.get("detections") or [])
        if isinstance(row, Mapping)
        and int(dict(row).get("frame_index") or 0) == int(frame_index)
    ]
    if len(detections) != 1:
        raise Phase4ApprovalError(
            "Exactly one blocking residual detection is required at the frame"
        )
    if not handoff_path.is_file():
        raise Phase4ApprovalError("Phase 3 handoff authority is missing")
    handoff_sha256 = _sha256_file(handoff_path)
    if str(meta.get("phase3_render_handoff_sha256") or "") != handoff_sha256:
        raise Phase4ApprovalError("Residual preflight authority is stale")
    source_sha256 = str(
        dict(dict(preview.get("refs") or {}).get("source_video_ref") or {}).get(
            "sha256"
        )
        or ""
    )
    if len(source_sha256) != 64:
        raise Phase4ApprovalError("Source video authority is missing")
    evidence_source = (
        root
        / "qa"
        / "phase4_preflight_samples"
        / f"frame_{int(frame_index):06d}_before_mask_after.jpg"
    )
    if not evidence_source.is_file():
        raise Phase4ApprovalError("Residual visual evidence is missing")
    detection = detections[0]
    detection_sha256 = residual_detection_sha256(detection)
    evidence_sha256 = _sha256_file(evidence_source)
    immutable_dir = root / "residual_cjk_false_positive_approvals"
    immutable_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = immutable_dir / f"evidence_{evidence_sha256}.jpg"
    if not evidence_path.is_file():
        shutil.copy2(evidence_source, evidence_path)
    if _sha256_file(evidence_path) != evidence_sha256:
        raise Phase4ApprovalError("Immutable residual evidence hash mismatch")
    binding = {
        "source_video_sha256": source_sha256,
        "phase3_render_handoff_sha256": handoff_sha256,
        "detection_sha256": detection_sha256,
        "evidence_sha256": evidence_sha256,
        "approval_token": token,
    }
    binding_sha256 = _sha256_json(binding)
    immutable_path = immutable_dir / f"approval_{binding_sha256}.json"
    if immutable_path.is_file():
        try:
            approval = json.loads(immutable_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Phase4ApprovalError(
                "Existing residual false-positive approval is invalid"
            ) from exc
    else:
        approval = {
            "schema_version": "phase4_residual_cjk_false_positive_approval_v1",
            "status": "OCR_FALSE_POSITIVE_CONFIRMED",
            "approved_at": _now(),
            "operator_id": operator,
            "approval_token": token,
            "detection": detection,
            "detection_sha256": detection_sha256,
            "evidence_ref": {
                "path": evidence_path.relative_to(root).as_posix(),
                "sha256": evidence_sha256,
            },
            "binding": binding,
            "binding_sha256": binding_sha256,
        }
        approval["approval_sha256"] = _sha256_json(approval)
        _write_json_atomic(immutable_path, approval)
    if str(approval.get("status") or "") != "OCR_FALSE_POSITIVE_CONFIRMED":
        raise Phase4ApprovalError("Residual false-positive approval status is invalid")
    _write_json_atomic(
        root / "phase4_residual_cjk_false_positive_approval.json",
        approval,
    )
    return approval


def _unique_asset_refs(values: list[Any]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in values:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        key = (str(item.get("storage_key") or ""), str(item.get("sha256") or ""))
        unique[key] = item
    return list(unique.values())


def prepare_approved_audio_handoff(
    *,
    root_dir: str | Path,
    manifest: Mapping[str, Any],
    narration_path: str | Path,
    background_path: str | Path | None = None,
    operator_id: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    source = to_windows_long_path(Path(narration_path).resolve())
    operator = str(operator_id or "").strip()
    if str(manifest.get("manifest_version") or "") != "RENDER_PREP_MANIFEST_V2":
        raise Phase4ApprovalError("Audio approval requires RENDER_PREP_MANIFEST_V2")
    if not source.is_file() or source.stat().st_size <= 0:
        raise Phase4ApprovalError("Joined narration file is missing or empty")
    if not operator:
        raise Phase4ApprovalError("Audio approval requires an operator id")
    outputs = dict(manifest.get("current_outputs") or {})
    joined = _unique_asset_refs(list(outputs.get("joined_narration") or []))
    if len(joined) != 1:
        raise Phase4ApprovalError("Audio approval requires exactly one joined narration")
    expected = str(joined[0].get("sha256") or "").lower()
    actual = _sha256_file(source)
    if len(expected) != 64 or actual != expected:
        raise Phase4ApprovalError("Joined narration hash does not match manifest authority")

    target = root / "phase4_joined_narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target.resolve():
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    if _sha256_file(target) != expected:
        raise Phase4ApprovalError("Copied Phase 4 narration failed hash verification")

    approved = json.loads(json.dumps(dict(manifest), ensure_ascii=False, default=str))
    approved_outputs = dict(approved.get("current_outputs") or {})
    approved_item = dict(joined[0])
    approved_item["source_storage_key"] = approved_item.get("storage_key")
    approved_item["storage_key"] = target.name
    approved_outputs["joined_narration"] = [approved_item]
    raw_backgrounds = _unique_asset_refs(list(outputs.get("background_audio") or []))
    approved_background_ref: dict[str, Any] | None = None
    if raw_backgrounds:
        if len(raw_backgrounds) != 1 or background_path is None:
            raise Phase4ApprovalError(
                "Manifest background stem requires one hash-verified background path"
            )
        background_source = to_windows_long_path(Path(background_path).resolve())
        expected_background = str(raw_backgrounds[0].get("sha256") or "").lower()
        if (
            not background_source.is_file()
            or len(expected_background) != 64
            or _sha256_file(background_source) != expected_background
        ):
            raise Phase4ApprovalError("Background stem hash does not match manifest")
        background_target = root / "phase4_background.wav"
        if background_source != background_target.resolve():
            temporary = background_target.with_suffix(background_target.suffix + ".tmp")
            shutil.copyfile(background_source, temporary)
            temporary.replace(background_target)
        approved_background = dict(raw_backgrounds[0])
        approved_background["source_storage_key"] = approved_background.get("storage_key")
        approved_background["storage_key"] = background_target.name
        approved_outputs["background_audio"] = [approved_background]
        approved_background_ref = {
            "path": background_target.name,
            "sha256": expected_background,
            "mime_type": approved_background.get("mime_type") or "audio/wav",
        }
    approved["current_outputs"] = approved_outputs
    approved_at = _now()
    approval = {
        "schema_version": "phase4_audio_approval_v1",
        "status": "AUDIO_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
        "narration_ref": {
            "path": target.name,
            "sha256": expected,
            "mime_type": approved_item.get("mime_type") or "audio/wav",
        },
        "background_ref": approved_background_ref,
    }
    approved["audio_review"] = {
        "status": "AUDIO_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator,
        "narration_sha256": expected,
    }
    _write_json_atomic(root / "render_prep_manifest.json", approved)
    _write_json_atomic(root / "phase4_audio_approval.json", approval)
    return approval


def attach_background_and_approve(
    *,
    root_dir: str | Path,
    manifest: Mapping[str, Any],
    narration_path: str | Path,
    background_path: str | Path,
    operator_id: str,
    provider: str = "demucs_htdemucs",
    model: str = "htdemucs",
) -> dict[str, Any]:
    """Add a newly generated no-vocals stem to an approved narration handoff."""

    root = Path(root_dir).resolve()
    background = to_windows_long_path(Path(background_path).resolve())
    if not background.is_file() or background.stat().st_size <= 44:
        raise Phase4ApprovalError("Background stem is missing or empty")
    background_sha256 = _sha256_file(background)
    enriched = json.loads(json.dumps(dict(manifest), ensure_ascii=False, default=str))
    outputs = dict(enriched.get("current_outputs") or {})
    outputs["background_audio"] = [
        {
            "storage_key": background.name,
            "sha256": background_sha256,
            "mime_type": "audio/wav",
            "size_bytes": background.stat().st_size,
            "role": "demucs_no_vocals",
            "metadata": {
                "provider": str(provider),
                "model": str(model),
                "source": "phase4_background_recovery",
            },
        }
    ]
    enriched["current_outputs"] = outputs
    render_contract = dict(enriched.get("render_contract") or {})
    render_contract["audio_strategy"] = "mix_vietnamese_narration_with_background_stem"
    enriched["render_contract"] = render_contract
    approval = prepare_approved_audio_handoff(
        root_dir=root,
        manifest=enriched,
        narration_path=narration_path,
        background_path=background,
        operator_id=operator_id,
    )
    attachment = {
        "schema_version": "phase4_background_attachment_v1",
        "status": "BACKGROUND_APPROVED",
        "approved_at": approval["approved_at"],
        "operator_id": approval["operator_id"],
        "provider": str(provider),
        "model": str(model),
        "background_ref": dict(approval.get("background_ref") or {}),
        "narration_ref": dict(approval.get("narration_ref") or {}),
    }
    _write_json_atomic(root / "phase4_background_attachment.json", attachment)
    return approval


def stage_audio_handoff(
    *,
    root_dir: str | Path,
    manifest: Mapping[str, Any],
    narration_path: str | Path,
    background_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    source = to_windows_long_path(Path(narration_path).resolve())
    if str(manifest.get("manifest_version") or "") != "RENDER_PREP_MANIFEST_V2":
        raise Phase4ApprovalError("Audio staging requires RENDER_PREP_MANIFEST_V2")
    outputs = dict(manifest.get("current_outputs") or {})
    joined = _unique_asset_refs(list(outputs.get("joined_narration") or []))
    if len(joined) != 1 or not source.is_file():
        raise Phase4ApprovalError("Audio staging requires one joined narration file")
    expected = str(joined[0].get("sha256") or "").lower()
    if len(expected) != 64 or _sha256_file(source) != expected:
        raise Phase4ApprovalError("Staged narration hash does not match manifest")
    target = root / "phase4_joined_narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target.resolve():
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    staged = json.loads(json.dumps(dict(manifest), ensure_ascii=False, default=str))
    staged_outputs = dict(staged.get("current_outputs") or {})
    staged_item = dict(joined[0])
    staged_item["source_storage_key"] = staged_item.get("storage_key")
    staged_item["storage_key"] = target.name
    staged_outputs["joined_narration"] = [staged_item]
    backgrounds = _unique_asset_refs(list(outputs.get("background_audio") or []))
    if backgrounds:
        if len(backgrounds) != 1 or background_path is None:
            raise Phase4ApprovalError("Background authority exists but staging path is missing")
        background_source = to_windows_long_path(Path(background_path).resolve())
        expected_background = str(backgrounds[0].get("sha256") or "").lower()
        if (
            not background_source.is_file()
            or len(expected_background) != 64
            or _sha256_file(background_source) != expected_background
        ):
            raise Phase4ApprovalError("Staged background hash does not match manifest")
        background_target = root / "phase4_background.wav"
        if background_source != background_target.resolve():
            temporary = background_target.with_suffix(background_target.suffix + ".tmp")
            shutil.copyfile(background_source, temporary)
            temporary.replace(background_target)
        staged_background = dict(backgrounds[0])
        staged_background["source_storage_key"] = staged_background.get("storage_key")
        staged_background["storage_key"] = background_target.name
        staged_outputs["background_audio"] = [staged_background]
    staged["current_outputs"] = staged_outputs
    staged["audio_review"] = {
        "status": "PENDING_AUDIO_REVIEW",
        "approved_at": None,
        "operator_id": None,
    }
    result = {
        "schema_version": "phase4_audio_staging_v1",
        "status": "PENDING_AUDIO_REVIEW",
        "created_at": _now(),
        "narration_ref": {"path": target.name, "sha256": expected},
        "background_staged": bool(backgrounds),
    }
    _write_json_atomic(root / "render_prep_manifest.json", staged)
    _write_json_atomic(root / "phase4_audio_staging.json", result)
    return result


def stage_verified_no_dialogue_audio_handoff(
    *,
    root_dir: str | Path,
    source_video_path: str | Path,
    analysis_metadata: Mapping[str, Any],
    source_video_id: str,
    required_approval_token: str,
    expected_source_sha256: str | None = None,
    ffmpeg_binary: str = "ffmpeg",
    run: Any = run_captured,
) -> dict[str, Any]:
    """Stage original audio only when measured VAD proves there is no dialogue.

    This is the no-dubbing counterpart to joined Vietnamese narration.  It is
    intentionally not approved here: the extracted audio and its VAD evidence
    are hash-bound for a separate operator listening checkpoint.
    """

    root = Path(root_dir).resolve()
    source = to_windows_long_path(Path(source_video_path).resolve())
    token = str(required_approval_token or "").strip()
    source_id = str(source_video_id or "").strip()
    if not source.is_file() or source.stat().st_size <= 0:
        raise Phase4ApprovalError("No-dialogue audio staging requires source media")
    if not token or not source_id:
        raise Phase4ApprovalError("No-dialogue audio staging requires identity and token")

    metadata = dict(analysis_metadata)
    vad = dict(metadata.get("vad") or {})
    vad_metadata = dict(vad.get("metadata") or {})
    flags = {str(value) for value in list(vad.get("difficulty_flags") or [])}
    speech_seconds = float(vad_metadata.get("speech_seconds") or 0.0)
    measured_no_dialogue = (
        str(metadata.get("dialogue_phase") or "") == "no_dialogue"
        and str(vad.get("provider") or "") == "silero_vad"
        and "silero_vad_executed" in flags
        and "no_speech_detected" in flags
        and speech_seconds == 0.0
        and int(vad_metadata.get("speech_segment_count") or 0) == 0
    )
    if not measured_no_dialogue:
        raise Phase4ApprovalError(
            "Source passthrough requires measured Silero no-dialogue authority"
        )

    audio_input = dict(metadata.get("audio_input") or {})
    duration = float(audio_input.get("source_video_duration_seconds") or 0.0)
    if duration <= 0:
        raise Phase4ApprovalError("No-dialogue authority requires source duration")
    source_sha256 = _sha256_file(source)
    expected = str(expected_source_sha256 or "").lower()
    if expected and (len(expected) != 64 or source_sha256 != expected):
        raise Phase4ApprovalError("No-dialogue source hash does not match Phase 4 authority")

    target = root / "phase4_no_dialogue_source_audio.wav"
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        f"{duration:.6f}",
        str(target),
    ]
    completed: subprocess.CompletedProcess[str] = run(command)
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size <= 44:
        detail = (completed.stderr or completed.stdout or "ffmpeg audio extract failed").strip()
        raise Phase4ApprovalError(detail[-500:])

    audio_sha256 = _sha256_file(target)
    authority = {
        "analysis_version": metadata.get("analysis_version"),
        "source_video_id": source_id,
        "dialogue_phase": "no_dialogue",
        "vad_provider": "silero_vad",
        "silero_vad_executed": True,
        "speech_seconds": speech_seconds,
        "speech_segment_count": 0,
        "source_video_sha256": source_sha256,
    }
    authority["authority_sha256"] = _sha256_json(authority)
    audio_item = {
        "storage_key": target.name,
        "sha256": audio_sha256,
        "mime_type": "audio/wav",
        "size_bytes": target.stat().st_size,
        "duration_seconds": duration,
        "audio_format": {
            "codec": "pcm_s16le",
            "sample_rate_hz": 48000,
            "channels": 2,
        },
        "role": "verified_no_dialogue_source_audio",
    }
    manifest = {
        "manifest_version": "RENDER_PREP_MANIFEST_V2",
        "source_video": {
            "source_video_id": source_id,
            "duration_seconds": duration,
            "sha256": source_sha256,
        },
        "current_outputs": {
            "joined_narration": [audio_item],
            "background_audio": [],
        },
        "render_contract": {
            "audio_strategy": "preserve_verified_no_dialogue_source_audio"
        },
        "audio_review": {
            "status": "PENDING_AUDIO_REVIEW",
            "approved_at": None,
            "operator_id": None,
        },
        "no_dialogue_authority": authority,
    }
    review = {
        "schema_version": "phase4_no_dialogue_audio_review_v1",
        "status": "PENDING_AUDIO_REVIEW",
        "created_at": _now(),
        "required_approval_token": token,
        "operator_approval_written": False,
        "source_video_id": source_id,
        "source_video_ref": {"sha256": source_sha256},
        "audio_ref": {
            "path": target.name,
            "sha256": audio_sha256,
            "mime_type": "audio/wav",
            "duration_seconds": duration,
        },
        "no_dialogue_authority": authority,
    }
    review["artifact_sha256"] = _sha256_json(review)
    staging = {
        "schema_version": "phase4_audio_staging_v1",
        "status": "PENDING_AUDIO_REVIEW",
        "created_at": review["created_at"],
        "narration_ref": {"path": target.name, "sha256": audio_sha256},
        "background_staged": False,
        "audio_role": "verified_no_dialogue_source_audio",
    }
    _write_json_atomic(root / "render_prep_manifest.json", manifest)
    _write_json_atomic(root / "phase4_audio_staging.json", staging)
    _write_json_atomic(root / "phase4_no_dialogue_audio_review.json", review)
    return review


def stage_uncertain_dialogue_audio_review(
    *,
    root_dir: str | Path,
    analysis_metadata: Mapping[str, Any],
    vocals_path: str | Path,
    background_path: str | Path,
    source_video_id: str,
    source_video_sha256: str,
    required_dialogue_present_token: str,
    required_no_dialogue_token: str,
) -> dict[str, Any]:
    """Stage a fail-closed listening checkpoint for VAD/ASR disagreement."""

    root = Path(root_dir).resolve()
    source_id = str(source_video_id or "").strip()
    source_hash = str(source_video_sha256 or "").strip().lower()
    dialogue_token = str(required_dialogue_present_token or "").strip()
    no_dialogue_token = str(required_no_dialogue_token or "").strip()
    if (
        not source_id
        or len(source_hash) != 64
        or not dialogue_token
        or not no_dialogue_token
        or dialogue_token == no_dialogue_token
    ):
        raise Phase4ApprovalError("Dialogue uncertainty review identity is incomplete")

    visual_approval_path = root / "phase4_visual_approval.json"
    try:
        visual_approval = json.loads(
            visual_approval_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError(
            "Dialogue uncertainty review requires visual approval"
        ) from exc
    if str(visual_approval.get("status") or "") != "VISUAL_APPROVED":
        raise Phase4ApprovalError("Visual approval is not current")
    video_ref = dict(visual_approval.get("video_ref") or {})
    preview = (root / str(video_ref.get("path") or "")).resolve()
    if (
        not preview.is_relative_to(root)
        or not preview.is_file()
        or _sha256_file(preview) != str(video_ref.get("sha256") or "").lower()
    ):
        raise Phase4ApprovalError("Visual preview no longer matches its approval")

    metadata = json.loads(
        json.dumps(dict(analysis_metadata), ensure_ascii=False, default=str)
    )
    audio_input = dict(metadata.get("audio_input") or {})
    vad = dict(metadata.get("vad") or {})
    vad_metadata = dict(vad.get("metadata") or {})
    separation = dict(metadata.get("separation") or {})
    separation_flags = {
        str(value) for value in list(separation.get("difficulty_flags") or [])
    }
    vad_flags = {str(value) for value in list(vad.get("difficulty_flags") or [])}
    if (
        str(metadata.get("dialogue_phase") or "") != "dialogue_uncertain"
        or str(audio_input.get("source_video_id") or "") != source_id
        or str(vad.get("provider") or "") != "silero_vad"
        or not bool(vad.get("has_speech"))
        or "silero_vad_executed" not in vad_flags
        or "asr_empty_despite_vad_speech" not in separation_flags
        or "needs_operator_review" not in separation_flags
    ):
        raise Phase4ApprovalError(
            "Dialogue uncertainty review requires measured VAD/ASR conflict authority"
        )

    contract_path = root / "phase4_render_input.json"
    if contract_path.is_file():
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Phase4ApprovalError("Phase 4 render input is invalid") from exc
        expected_source_hash = str(
            dict(dict(contract.get("refs") or {}).get("source_video_ref") or {}).get(
                "sha256"
            )
            or ""
        ).lower()
        if expected_source_hash and expected_source_hash != source_hash:
            raise Phase4ApprovalError(
                "Audio analysis source does not match Phase 4 source authority"
            )

    staged: dict[str, dict[str, Any]] = {}
    for role, raw_source, filename in (
        ("isolated_vocals", vocals_path, "phase4_dialogue_uncertain_vocals.wav"),
        (
            "background_reference",
            background_path,
            "phase4_dialogue_uncertain_background.wav",
        ),
    ):
        source = to_windows_long_path(Path(raw_source).resolve())
        if not source.is_file() or source.stat().st_size <= 44:
            raise Phase4ApprovalError(f"{role} audio is missing or empty")
        target = root / filename
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        staged[role] = {
            "path": target.name,
            "sha256": _sha256_file(target),
            "size_bytes": target.stat().st_size,
            "mime_type": "audio/wav",
        }

    review = {
        "schema_version": "phase4_dialogue_detection_review_v1",
        "policy_version": DIALOGUE_UNCERTAIN_REVIEW_POLICY_VERSION,
        "status": "PENDING_DIALOGUE_OPERATOR_REVIEW",
        "created_at": _now(),
        "operator_approval_written": False,
        "source_video_id": source_id,
        "source_video_ref": {"sha256": source_hash},
        "visual_approval_ref": {
            "path": visual_approval_path.name,
            "sha256": _sha256_file(visual_approval_path),
        },
        "original_audio_preview_ref": {
            "path": preview.relative_to(root).as_posix(),
            "sha256": _sha256_file(preview),
        },
        "analysis_authority": {
            "analysis_version": metadata.get("analysis_version"),
            "dialogue_phase": "dialogue_uncertain",
            "analysis_sha256": _sha256_json(metadata),
            "vad_provider": "silero_vad",
            "speech_seconds": float(vad_metadata.get("speech_seconds") or 0.0),
            "audio_seconds": float(vad_metadata.get("audio_seconds") or 0.0),
            "speech_segment_count": int(
                vad_metadata.get("speech_segment_count") or 0
            ),
            "stt_provider": metadata.get("stt_provider"),
            "conflict_reason": "asr_empty_despite_vad_speech",
        },
        "audition_assets": staged,
        "required_decision_tokens": {
            "dialogue_present": dialogue_token,
            "no_dialogue": no_dialogue_token,
        },
    }
    review["artifact_sha256"] = _sha256_json(review)
    _write_json_atomic(root / "phase4_dialogue_detection_review.json", review)
    return review


def approve_uncertain_dialogue_audio_review(
    *,
    root_dir: str | Path,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    """Record one of the two hash-bound VAD/ASR conflict decisions."""

    root = Path(root_dir).resolve()
    review_path = root / "phase4_dialogue_detection_review.json"
    token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("Dialogue detection review is missing") from exc
    candidate = dict(review)
    expected_review_hash = str(candidate.pop("artifact_sha256", ""))
    if (
        len(expected_review_hash) != 64
        or _sha256_json(candidate) != expected_review_hash
        or str(review.get("status") or "")
        != "PENDING_DIALOGUE_OPERATOR_REVIEW"
        or bool(review.get("operator_approval_written"))
    ):
        raise Phase4ApprovalError("Dialogue detection review authority is invalid")
    if not token or not operator:
        raise Phase4ApprovalError("Dialogue detection approval identity is incomplete")
    decision_tokens = dict(review.get("required_decision_tokens") or {})
    if token == str(decision_tokens.get("dialogue_present") or ""):
        decision = "DIALOGUE_PRESENT_CONFIRMED"
    elif token == str(decision_tokens.get("no_dialogue") or ""):
        decision = "NO_DIALOGUE_CONFIRMED"
    else:
        raise Phase4ApprovalError("Dialogue detection approval token does not match")

    for raw in dict(review.get("audition_assets") or {}).values():
        if not isinstance(raw, Mapping):
            raise Phase4ApprovalError("Dialogue audition asset reference is invalid")
        path = (root / str(raw.get("path") or "")).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or _sha256_file(path) != str(raw.get("sha256") or "").lower()
        ):
            raise Phase4ApprovalError("Dialogue audition asset hash changed")

    approval = {
        "schema_version": "phase4_dialogue_detection_approval_v1",
        "status": decision,
        "approved_at": _now(),
        "operator_id": operator,
        "approval_token": token,
        "operator_approval_written": True,
        "review_ref": {
            "path": review_path.name,
            "sha256": _sha256_file(review_path),
            "artifact_sha256": expected_review_hash,
        },
        "source_video_id": review.get("source_video_id"),
        "source_video_ref": review.get("source_video_ref"),
        "analysis_authority": review.get("analysis_authority"),
    }
    approval["approval_sha256"] = _sha256_json(approval)
    _write_json_atomic(root / "phase4_dialogue_detection_approval.json", approval)
    return approval


def approve_verified_no_dialogue_audio_handoff(
    *,
    root_dir: str | Path,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    """Approve exactly the hash-bound no-dialogue audio staged for review."""

    root = Path(root_dir).resolve()
    review_path = root / "phase4_no_dialogue_audio_review.json"
    manifest_path = root / "render_prep_manifest.json"
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("No-dialogue audio review is missing or invalid") from exc
    token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    if not operator or token != str(review.get("required_approval_token") or ""):
        raise Phase4ApprovalError("No-dialogue audio approval token is invalid")
    if str(review.get("status") or "") != "PENDING_AUDIO_REVIEW":
        raise Phase4ApprovalError("No-dialogue audio review is not pending")
    expected_artifact_hash = str(review.get("artifact_sha256") or "")
    review_without_hash = {
        key: value for key, value in review.items() if key != "artifact_sha256"
    }
    if _sha256_json(review_without_hash) != expected_artifact_hash:
        raise Phase4ApprovalError("No-dialogue audio review hash is stale")
    if dict(review.get("no_dialogue_authority") or {}) != dict(
        manifest.get("no_dialogue_authority") or {}
    ):
        raise Phase4ApprovalError("No-dialogue authority differs from staged manifest")

    audio_ref = dict(review.get("audio_ref") or {})
    audio_raw = str(audio_ref.get("path") or "")
    audio_path = (root / audio_raw).resolve()
    if (
        not audio_raw
        or not audio_path.is_relative_to(root)
        or not audio_path.is_file()
        or _sha256_file(audio_path) != str(audio_ref.get("sha256") or "")
    ):
        raise Phase4ApprovalError("No-dialogue audio artifact failed hash verification")
    joined = list(dict(manifest.get("current_outputs") or {}).get("joined_narration") or [])
    if (
        len(joined) != 1
        or not isinstance(joined[0], Mapping)
        or str(joined[0].get("role") or "")
        != "verified_no_dialogue_source_audio"
    ):
        raise Phase4ApprovalError("Staged manifest is not a no-dialogue audio handoff")

    approval = prepare_approved_audio_handoff(
        root_dir=root,
        manifest=manifest,
        narration_path=audio_path,
        operator_id=operator,
    )
    review["status"] = "AUDIO_APPROVED"
    review["approved_at"] = approval["approved_at"]
    review["operator_approval_written"] = True
    review["operator_id"] = operator
    review["operator_decision"] = token
    review["approved_audio_ref"] = dict(approval.get("narration_ref") or {})
    review["artifact_sha256"] = _sha256_json(
        {key: value for key, value in review.items() if key != "artifact_sha256"}
    )
    _write_json_atomic(review_path, review)

    approval["audio_role"] = "verified_no_dialogue_source_audio"
    approval["no_dialogue_review_ref"] = {
        "path": review_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(review_path),
        "artifact_sha256": review["artifact_sha256"],
    }
    _write_json_atomic(root / "phase4_audio_approval.json", approval)
    return approval


def stage_background_mix_review(
    *,
    root_dir: str | Path,
    manifest: Mapping[str, Any],
    narration_path: str | Path,
    background_path: str | Path,
    provider: str = "demucs_htdemucs",
    model: str = "htdemucs",
    ffmpeg_binary: str = "ffmpeg",
    background_gain: float = 1.0,
    target_lufs: float = -14.0,
    required_approval_token: str = "AUDIO_MIX_APPROVED",
    run: Any = run_captured,
) -> dict[str, Any]:
    """Stage and preview a new background authority without approving the mix."""

    root = Path(root_dir).resolve()
    narration = to_windows_long_path(Path(narration_path).resolve())
    background = to_windows_long_path(Path(background_path).resolve())
    if not narration.is_file() or not background.is_file():
        raise Phase4ApprovalError("Background mix review requires narration and background files")
    approved_review = dict(manifest.get("audio_review") or {})
    if str(approved_review.get("status") or "") != "AUDIO_APPROVED":
        raise Phase4ApprovalError("Background mix review requires approved narration")

    safe_gain = max(0.0, min(1.0, float(background_gain)))
    background_sha256 = _sha256_file(background)
    enriched = json.loads(json.dumps(dict(manifest), ensure_ascii=False, default=str))
    outputs = dict(enriched.get("current_outputs") or {})
    outputs["background_audio"] = [
        {
            "storage_key": str(background),
            "sha256": background_sha256,
            "mime_type": "audio/wav",
            "size_bytes": background.stat().st_size,
            "role": "demucs_no_vocals",
            "metadata": {"provider": str(provider), "model": str(model)},
        }
    ]
    enriched["current_outputs"] = outputs
    render_contract = dict(enriched.get("render_contract") or {})
    render_contract["audio_strategy"] = "mix_vietnamese_narration_with_background_stem"
    render_contract["background_gain"] = round(safe_gain, 6)
    enriched["render_contract"] = render_contract
    stage_audio_handoff(
        root_dir=root,
        manifest=enriched,
        narration_path=narration,
        background_path=background,
    )

    staged_manifest_path = root / "render_prep_manifest.json"
    staged_manifest = json.loads(staged_manifest_path.read_text(encoding="utf-8"))
    staged_manifest["audio_review"] = {
        "status": "PENDING_AUDIO_MIX_REVIEW",
        "approved_at": None,
        "operator_id": None,
        "prior_narration_approval": {
            "approved_at": approved_review.get("approved_at"),
            "operator_id": approved_review.get("operator_id"),
            "narration_sha256": approved_review.get("narration_sha256"),
        },
    }
    _write_json_atomic(staged_manifest_path, staged_manifest)

    target_narration = root / "phase4_joined_narration.wav"
    target_background = root / "phase4_background.wav"
    preview = root / "phase4_audio_mix_preview.wav"
    duration = float(
        dict(staged_manifest.get("source_video") or {}).get("duration_seconds") or 0.0
    )
    if duration <= 0:
        raise Phase4ApprovalError("Background mix review requires source duration authority")
    loudnorm = f"loudnorm=I={float(target_lufs):g}:TP=-1.5:LRA=11"
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(target_narration),
        "-i",
        str(target_background),
        "-filter_complex",
        "[0:a]volume=1.0[narration];"
        f"[1:a]volume={safe_gain:.4f}[background];"
        "[narration][background]"
        "amix=inputs=2:duration=longest:dropout_transition=0,"
        f"{loudnorm}[audio_out]",
        "-map",
        "[audio_out]",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        f"{duration:.6f}",
        str(preview),
    ]
    completed: subprocess.CompletedProcess[str] = run(command)
    if completed.returncode != 0 or not preview.is_file() or preview.stat().st_size <= 44:
        detail = (completed.stderr or completed.stdout or "ffmpeg audio mix failed").strip()
        raise Phase4ApprovalError(detail[-500:])

    prior_approval_ref: dict[str, Any] | None = None
    approval_path = root / "phase4_audio_approval.json"
    if approval_path.is_file():
        approval_sha256 = _sha256_file(approval_path)
        stale_dir = root / "qa" / "stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived = stale_dir / (
            f"phase4_audio_approval_before_background_{timestamp}_{approval_sha256[:12]}.json"
        )
        try:
            approval_path.replace(archived)
        except FileNotFoundError:
            # Another retry may have archived the same authority between the
            # existence check and replace. The staged mix remains valid; leave
            # the prior reference unset rather than failing the durable job.
            pass
        else:
            prior_approval_ref = {
                "path": archived.relative_to(root).as_posix(),
                "sha256": approval_sha256,
            }

    staged = json.loads((root / "phase4_audio_staging.json").read_text(encoding="utf-8"))
    staged["status"] = "PENDING_AUDIO_MIX_REVIEW"
    staged["background_staged"] = True
    staged["mix_preview_ref"] = {
        "path": preview.name,
        "sha256": _sha256_file(preview),
    }
    _write_json_atomic(root / "phase4_audio_staging.json", staged)

    review: dict[str, Any] = {
        "schema_version": "phase4_background_mix_review_v1",
        "status": "PENDING_AUDIO_MIX_REVIEW",
        "created_at": _now(),
        "operator_approval_written": False,
        "required_approval_token": str(required_approval_token or "").strip(),
        "narration_ref": {
            "path": target_narration.name,
            "sha256": _sha256_file(target_narration),
        },
        "background_ref": {
            "path": target_background.name,
            "sha256": _sha256_file(target_background),
            "provider": str(provider),
            "model": str(model),
        },
        "mix_preview_ref": {
            "path": preview.name,
            "sha256": _sha256_file(preview),
        },
        "mix_recipe": {
            "background_gain": round(safe_gain, 6),
            "target_lufs": float(target_lufs),
            "true_peak_db": -1.5,
            "duration_seconds": duration,
        },
        "prior_narration_approval_ref": prior_approval_ref,
    }
    review["artifact_sha256"] = _sha256_json(review)
    _write_json_atomic(root / "phase4_background_mix_review.json", review)
    return review


def approve_background_mix_review(
    *,
    root_dir: str | Path,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    """Approve exactly the staged narration/background/mix-preview authority."""

    root = Path(root_dir).resolve()
    review_path = root / "phase4_background_mix_review.json"
    manifest_path = root / "render_prep_manifest.json"
    existing_approval_path = root / "phase4_background_mix_approval.json"
    if existing_approval_path.is_file():
        try:
            existing_approval = json.loads(
                existing_approval_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            existing_approval = {}
        if str(existing_approval.get("status") or "") == "AUDIO_MIX_APPROVED":
            return dict(existing_approval)
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("Background mix review is missing or invalid") from exc
    token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    candidate = dict(review)
    expected_review_hash = str(candidate.pop("artifact_sha256", ""))
    if (
        len(expected_review_hash) != 64
        or _sha256_json(candidate) != expected_review_hash
        or str(review.get("status") or "") != "PENDING_AUDIO_MIX_REVIEW"
        or bool(review.get("operator_approval_written"))
        or token != str(review.get("required_approval_token") or "")
        or not operator
    ):
        raise Phase4ApprovalError("Background mix approval authority is invalid")

    verified_refs: dict[str, dict[str, Any]] = {}
    for key in ("narration_ref", "background_ref", "mix_preview_ref"):
        raw = dict(review.get(key) or {})
        path = (root / str(raw.get("path") or "")).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or _sha256_file(path) != str(raw.get("sha256") or "").lower()
        ):
            raise Phase4ApprovalError(f"Background mix {key} hash changed")
        verified_refs[key] = raw
    if str(dict(manifest.get("audio_review") or {}).get("status") or "") != (
        "PENDING_AUDIO_MIX_REVIEW"
    ):
        raise Phase4ApprovalError("Background mix manifest is not pending review")

    audio_approval = prepare_approved_audio_handoff(
        root_dir=root,
        manifest=manifest,
        narration_path=root / str(verified_refs["narration_ref"]["path"]),
        background_path=root / str(verified_refs["background_ref"]["path"]),
        operator_id=operator,
    )
    mix_approval = {
        "schema_version": "phase4_background_mix_approval_v1",
        "status": "AUDIO_MIX_APPROVED",
        "approved_at": audio_approval["approved_at"],
        "operator_id": operator,
        "approval_token": token,
        "operator_approval_written": True,
        "review_ref": {
            "path": review_path.name,
            "sha256": _sha256_file(review_path),
            "artifact_sha256": expected_review_hash,
        },
        "narration_ref": verified_refs["narration_ref"],
        "background_ref": verified_refs["background_ref"],
        "mix_preview_ref": verified_refs["mix_preview_ref"],
        "mix_recipe": review.get("mix_recipe"),
        "audio_approval_ref": {
            "path": "phase4_audio_approval.json",
            "status": audio_approval["status"],
        },
    }
    mix_approval["approval_sha256"] = _sha256_json(mix_approval)
    _write_json_atomic(root / "phase4_background_mix_approval.json", mix_approval)
    return mix_approval


def record_visual_approval(
    *,
    root_dir: str | Path,
    video_path: str | Path,
    output_qa_path: str | Path,
    operator_id: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    video = Path(video_path).resolve()
    qa_path = Path(output_qa_path).resolve()
    operator = str(operator_id or "").strip()
    if (
        not video.is_relative_to(root)
        or not qa_path.is_relative_to(root)
        or not video.is_file()
        or not qa_path.is_file()
        or not operator
    ):
        raise Phase4ApprovalError("Visual approval inputs are incomplete")
    try:
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ApprovalError("Visual output QA is invalid") from exc
    if not isinstance(qa, Mapping) or str(qa.get("status") or "") != "PASS":
        raise Phase4ApprovalError("Visual approval requires PASS encoded-output QA")
    approval = {
        "schema_version": "phase4_visual_approval_v1",
        "status": "VISUAL_APPROVED",
        "approved_at": _now(),
        "operator_id": operator,
        "video_ref": {
            "path": video.relative_to(root).as_posix(),
            "sha256": _sha256_file(video),
        },
        "output_qa_ref": {
            "path": qa_path.relative_to(root).as_posix(),
            "sha256": _sha256_file(qa_path),
        },
    }
    _write_json_atomic(root / "phase4_visual_approval.json", approval)
    return approval
