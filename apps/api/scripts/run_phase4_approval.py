"""Persist Phase 4 visual/audio operator approvals as hash-bound artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    approve_background_mix_review,
    approve_uncertain_dialogue_audio_review,
    approve_verified_no_dialogue_audio_handoff,
    attach_background_and_approve,
    prepare_approved_audio_handoff,
    record_residual_cjk_false_positive_approval,
    record_visual_approval,
    stage_audio_handoff,
    stage_background_mix_review,
    stage_uncertain_dialogue_audio_review,
    stage_verified_no_dialogue_audio_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.run_phase4_approval")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    visual = subparsers.add_parser("visual")
    visual.add_argument("artifact_root")
    visual.add_argument("--operator", default="local_operator")
    residual_false_positive = subparsers.add_parser(
        "approve-residual-false-positive"
    )
    residual_false_positive.add_argument("artifact_root")
    residual_false_positive.add_argument("approval_token")
    residual_false_positive.add_argument("--frame-index", type=int, required=True)
    residual_false_positive.add_argument("--operator", required=True)
    audio = subparsers.add_parser("audio")
    audio.add_argument("artifact_root")
    audio.add_argument("manifest_json")
    audio.add_argument("narration_wav")
    audio.add_argument("--background")
    audio.add_argument("--operator", default="local_operator")
    database = subparsers.add_parser("audio-from-db")
    database.add_argument("artifact_root")
    database.add_argument("source_video_id")
    database.add_argument("--operator", default="local_operator")
    staging = subparsers.add_parser("stage-audio-from-db")
    staging.add_argument("artifact_root")
    staging.add_argument("source_video_id")
    background = subparsers.add_parser("attach-background")
    background.add_argument("artifact_root")
    background.add_argument("background_wav")
    background.add_argument("--operator", default="local_operator")
    background.add_argument("--provider", default="demucs_htdemucs")
    background.add_argument("--model", default="htdemucs")
    mix_review = subparsers.add_parser("stage-background-from-db")
    mix_review.add_argument("artifact_root")
    mix_review.add_argument("source_video_id")
    mix_review.add_argument("--approval-token", default="AUDIO_MIX_APPROVED")
    mix_review.add_argument(
        "--background-gain",
        type=float,
        help="Override background stem gain (1.0 preserves the recovered stem level).",
    )
    mix_approval = subparsers.add_parser("approve-background-mix")
    mix_approval.add_argument("artifact_root")
    mix_approval.add_argument("approval_token")
    mix_approval.add_argument("--operator", required=True)
    no_dialogue = subparsers.add_parser("stage-no-dialogue-from-db")
    no_dialogue.add_argument("artifact_root")
    no_dialogue.add_argument("source_video_id")
    no_dialogue.add_argument(
        "--approval-token", default="AUDIO_APPROVED"
    )
    no_dialogue_approval = subparsers.add_parser("approve-no-dialogue")
    no_dialogue_approval.add_argument("artifact_root")
    no_dialogue_approval.add_argument("approval_token")
    no_dialogue_approval.add_argument("--operator", required=True)
    dialogue_uncertain = subparsers.add_parser(
        "stage-dialogue-uncertain-from-db"
    )
    dialogue_uncertain.add_argument("artifact_root")
    dialogue_uncertain.add_argument("source_video_id")
    dialogue_uncertain.add_argument("--dialogue-present-token", required=True)
    dialogue_uncertain.add_argument("--no-dialogue-token", required=True)
    dialogue_uncertain_approval = subparsers.add_parser(
        "approve-dialogue-uncertain"
    )
    dialogue_uncertain_approval.add_argument("artifact_root")
    dialogue_uncertain_approval.add_argument("approval_token")
    dialogue_uncertain_approval.add_argument("--operator", required=True)
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        root = Path(args.artifact_root).resolve()
        if args.mode == "visual":
            result = record_visual_approval(
                root_dir=root,
                video_path=root / "phase4_adaptive_visual_preview.mp4",
                output_qa_path=(
                    root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
                ),
                operator_id=args.operator,
            )
        elif args.mode == "approve-residual-false-positive":
            result = record_residual_cjk_false_positive_approval(
                root_dir=root,
                frame_index=int(args.frame_index),
                approval_token=str(args.approval_token),
                operator_id=str(args.operator),
            )
        elif args.mode == "approve-dialogue-uncertain":
            result = approve_uncertain_dialogue_audio_review(
                root_dir=root,
                approval_token=str(args.approval_token),
                operator_id=str(args.operator),
            )
        elif args.mode == "stage-dialogue-uncertain-from-db":
            from sqlalchemy import select

            from src.core.settings import get_settings
            from src.db.session import get_session_factory
            from src.enums import MediaAssetStatus, MediaAssetType
            from src.models.media import MediaAsset
            from src.storage.local import LocalStorageBackend, to_windows_long_path

            source_video_id = UUID(str(args.source_video_id))
            with get_session_factory()() as db:
                assets = list(
                    db.scalars(
                        select(MediaAsset).where(
                            MediaAsset.source_video_id == source_video_id,
                            MediaAsset.asset_type.in_(
                                [
                                    MediaAssetType.SOURCE_VIDEO_RAW,
                                    MediaAssetType.AUDIO_ANALYSIS_METADATA,
                                ]
                            ),
                            MediaAsset.status == MediaAssetStatus.AVAILABLE,
                            MediaAsset.is_current.is_(True),
                        )
                    ).all()
                )
                by_type = {asset.asset_type: asset for asset in assets}
                source_asset = by_type.get(MediaAssetType.SOURCE_VIDEO_RAW)
                analysis_asset = by_type.get(MediaAssetType.AUDIO_ANALYSIS_METADATA)
                if source_asset is None or analysis_asset is None:
                    raise Phase4ApprovalError(
                        "Current source and audio-analysis assets are required"
                    )
                storage = LocalStorageBackend(get_settings().local_storage_root)
                source_metadata = storage.metadata(source_asset.storage_key)
                if (
                    not source_metadata.exists
                    or source_metadata.checksum_sha256
                    != str(source_asset.checksum_sha256 or "").lower()
                ):
                    raise Phase4ApprovalError(
                        "Current source file does not match DB authority"
                    )
                analysis_path = to_windows_long_path(
                    storage.resolve(analysis_asset.storage_key).absolute_path
                )
                analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
                separation_metadata = dict(
                    dict(analysis.get("separation") or {}).get("metadata") or {}
                )
                vocals_key = str(
                    separation_metadata.get("vocal_storage_key") or ""
                )
                background_key = str(
                    separation_metadata.get("background_storage_key") or ""
                )
                if not vocals_key or not background_key:
                    raise Phase4ApprovalError(
                        "Dialogue uncertainty review stems are missing"
                    )
                result = stage_uncertain_dialogue_audio_review(
                    root_dir=root,
                    analysis_metadata=analysis,
                    vocals_path=to_windows_long_path(
                        storage.resolve(vocals_key).absolute_path
                    ),
                    background_path=to_windows_long_path(
                        storage.resolve(background_key).absolute_path
                    ),
                    source_video_id=str(source_video_id),
                    source_video_sha256=str(source_asset.checksum_sha256 or ""),
                    required_dialogue_present_token=str(
                        args.dialogue_present_token
                    ),
                    required_no_dialogue_token=str(args.no_dialogue_token),
                )
        elif args.mode == "attach-background":
            manifest = json.loads(
                (root / "render_prep_manifest.json").read_text(encoding="utf-8")
            )
            result = attach_background_and_approve(
                root_dir=root,
                manifest=manifest,
                narration_path=root / "phase4_joined_narration.wav",
                background_path=args.background_wav,
                operator_id=args.operator,
                provider=args.provider,
                model=args.model,
            )
        elif args.mode == "approve-background-mix":
            result = approve_background_mix_review(
                root_dir=root,
                approval_token=str(args.approval_token),
                operator_id=str(args.operator),
            )
        elif args.mode == "stage-background-from-db":
            from sqlalchemy import select

            from src.core.settings import get_settings
            from src.db.session import get_session_factory
            from src.enums import MediaAssetStatus, MediaAssetType
            from src.models.media import MediaAsset
            from src.render_pipeline.audio_loudness import (
                background_mix_gain,
                loudness_target_lufs,
            )
            from src.storage.local import LocalStorageBackend

            source_video_id = UUID(str(args.source_video_id))
            with get_session_factory()() as db:
                background_asset = db.scalar(
                    select(MediaAsset).where(
                        MediaAsset.source_video_id == source_video_id,
                        MediaAsset.asset_type == MediaAssetType.AUDIO_BACKGROUND_STEM,
                        MediaAsset.status == MediaAssetStatus.AVAILABLE,
                        MediaAsset.is_current.is_(True),
                    )
                )
                if background_asset is None:
                    raise Phase4ApprovalError("Current background stem asset is missing")
                storage = LocalStorageBackend(get_settings().local_storage_root)
                background_path = storage.resolve(
                    background_asset.storage_key
                ).absolute_path
                manifest = json.loads(
                    (root / "render_prep_manifest.json").read_text(encoding="utf-8")
                )
                result = stage_background_mix_review(
                    root_dir=root,
                    manifest=manifest,
                    narration_path=root / "phase4_joined_narration.wav",
                    background_path=background_path,
                    provider=str(
                        dict(background_asset.metadata_json or {}).get("provider")
                        or "demucs_htdemucs"
                    ),
                    model=str(
                        dict(background_asset.metadata_json or {}).get("model")
                        or "htdemucs"
                    ),
                    background_gain=(
                        background_mix_gain()
                        if args.background_gain is None
                        else float(args.background_gain)
                    ),
                    target_lufs=loudness_target_lufs(),
                    required_approval_token=str(args.approval_token),
                )
        elif args.mode == "approve-no-dialogue":
            result = approve_verified_no_dialogue_audio_handoff(
                root_dir=root,
                approval_token=str(args.approval_token),
                operator_id=str(args.operator),
            )
        elif args.mode == "stage-no-dialogue-from-db":
            from sqlalchemy import select

            from src.core.settings import get_settings
            from src.db.session import get_session_factory
            from src.enums import MediaAssetStatus, MediaAssetType
            from src.models.media import MediaAsset
            from src.storage.local import LocalStorageBackend

            source_video_id = UUID(str(args.source_video_id))
            with get_session_factory()() as db:
                assets = list(
                    db.scalars(
                        select(MediaAsset).where(
                            MediaAsset.source_video_id == source_video_id,
                            MediaAsset.asset_type.in_(
                                [
                                    MediaAssetType.SOURCE_VIDEO_RAW,
                                    MediaAssetType.AUDIO_ANALYSIS_METADATA,
                                ]
                            ),
                            MediaAsset.status == MediaAssetStatus.AVAILABLE,
                            MediaAsset.is_current.is_(True),
                        )
                    ).all()
                )
                by_type = {asset.asset_type: asset for asset in assets}
                source_asset = by_type.get(MediaAssetType.SOURCE_VIDEO_RAW)
                analysis_asset = by_type.get(MediaAssetType.AUDIO_ANALYSIS_METADATA)
                if source_asset is None or analysis_asset is None:
                    raise Phase4ApprovalError(
                        "Current source and audio-analysis assets are required"
                    )
                storage = LocalStorageBackend(get_settings().local_storage_root)
                source_path = storage.resolve(source_asset.storage_key).absolute_path
                analysis_path = storage.resolve(analysis_asset.storage_key).absolute_path
                analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
                contract = json.loads(
                    (root / "phase4_render_input.json").read_text(encoding="utf-8")
                )
                expected_source_hash = str(
                    dict(dict(contract.get("refs") or {}).get("source_video_ref") or {}).get(
                        "sha256"
                    )
                    or ""
                )
                result = stage_verified_no_dialogue_audio_handoff(
                    root_dir=root,
                    source_video_path=source_path,
                    analysis_metadata=analysis,
                    source_video_id=str(source_video_id),
                    required_approval_token=str(args.approval_token),
                    expected_source_sha256=expected_source_hash,
                )
        elif args.mode == "audio":
            manifest = json.loads(
                Path(args.manifest_json).read_text(encoding="utf-8")
            )
            result = prepare_approved_audio_handoff(
                root_dir=root,
                manifest=manifest,
                narration_path=args.narration_wav,
                background_path=args.background,
                operator_id=args.operator,
            )
        else:
            from sqlalchemy import select

            from src.core.settings import get_settings
            from src.db.session import get_session_factory
            from src.enums import MediaAssetStatus, MediaAssetType
            from src.models.media import MediaAsset
            from src.storage.local import LocalStorageBackend
            from src.tts_pipeline.services.tts_service import TtsPipelineService

            source_video_id = UUID(str(args.source_video_id))
            with get_session_factory()() as db:
                manifest = TtsPipelineService(db).get_render_prep_manifest(
                    source_video_id
                )
                narration_asset = db.scalar(
                    select(MediaAsset).where(
                        MediaAsset.source_video_id == source_video_id,
                        MediaAsset.asset_type == MediaAssetType.TTS_AUDIO_JOINED,
                        MediaAsset.status == MediaAssetStatus.AVAILABLE,
                        MediaAsset.is_current.is_(True),
                    )
                )
                if narration_asset is None:
                    raise Phase4ApprovalError("Current joined narration asset is missing")
                resolved = LocalStorageBackend(
                    get_settings().local_storage_root
                ).resolve(narration_asset.storage_key)
                background_values = list(
                    dict(manifest.get("current_outputs") or {}).get("background_audio")
                    or []
                )
                background_resolved = (
                    LocalStorageBackend(get_settings().local_storage_root).resolve(
                        str(background_values[0].get("storage_key") or "")
                    ).absolute_path
                    if background_values and isinstance(background_values[0], dict)
                    else None
                )
                if args.mode == "stage-audio-from-db":
                    result = stage_audio_handoff(
                        root_dir=root,
                        manifest=manifest,
                        narration_path=resolved.absolute_path,
                        background_path=background_resolved,
                    )
                else:
                    result = prepare_approved_audio_handoff(
                        root_dir=root,
                        manifest=manifest,
                        narration_path=resolved.absolute_path,
                        background_path=background_resolved,
                        operator_id=args.operator,
                    )
        print(f"[P4-APPROVAL][OK] {result['status']}", flush=True)
        return 0
    except (OSError, json.JSONDecodeError, Phase4ApprovalError) as exc:
        print(f"[P4-APPROVAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
