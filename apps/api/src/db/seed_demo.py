from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.bootstrap import ensure_default_workspace
from src.db.session import get_session_factory
from src.enums import (
    CandidateStatus,
    CrawlSessionStatus,
    ExternalPublicationStatus,
    JobStatus,
    JobStepStatus,
    JobType,
    MediaAssetStatus,
    MediaAssetType,
    OperatorFeedbackQualityLabel,
    OperatorFeedbackRootCause,
    OperatorFeedbackTargetType,
    PlatformAccountStatus,
    PublishAccountAssignmentStatus,
    PublishAttemptStatus,
    PublishConfidenceLabel,
    PublishDraftStatus,
    PublishReconciliationStatus,
    PublishRoutingRuleStatus,
    PublishTargetPlatform,
    RenderOutputStatus,
    RiskFlagStatus,
    RiskFlagType,
    RiskSeverity,
    RiskTargetType,
    SourcePlatformEnum,
    SourceProfileStatus,
    SourceVideoStatus,
    TranscriptSegmentStatus,
)
from src.models.artifacts import SubtitleSegment, TranscriptSegment, TranslationSegment
from src.models.analytics import OperatorFeedback
from src.models.ingestion import CrawlSession, SourceProfile, SourceVideo, VideoMetricSnapshot
from src.models.jobs import Job, JobStep
from src.models.media import MediaAsset, RenderOutput
from src.models.publish import PlatformAccount, PublishAttempt, PublishDraft, PublishRoutingRule
from src.models.review import RiskFlag, VideoCandidate
from src.storage.local import LocalStorageBackend


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "alpha_demo_fixture.json"


def seed_demo_data(db: Session) -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    workspace = ensure_default_workspace(db)
    profile = _upsert_profile(db, workspace.id, fixture["source_profile"])
    crawl_session = _ensure_crawl_session(db, workspace.id, profile.id)
    platform_accounts = _seed_platform_accounts(db, workspace.id)
    _seed_routing_rule(db, workspace.id, platform_accounts["primary"].id)
    storage = LocalStorageBackend(get_settings().local_storage_root)
    created_videos: list[SourceVideo] = []

    for index, video_data in enumerate(fixture["source_videos"]):
        video = _upsert_video(db, workspace.id, profile.id, crawl_session.id, video_data, index)
        created_videos.append(video)
        _upsert_metric_snapshot(db, workspace.id, video.id, crawl_session.id, video_data["metrics"])
        if candidate_data := video_data.get("candidate"):
            _upsert_candidate(db, workspace.id, video.id, candidate_data)
        if video_data["path"] in {"rendered_final", "publish_ready", "warning_path"}:
            _seed_media_and_render(db, storage, workspace.id, video, approved=video.status == SourceVideoStatus.PUBLISH_READY)
            _seed_segments(db, workspace.id, video.id)
        if risk_flags := video_data.get("risk_flags"):
            _seed_risk_flags(db, workspace.id, video.id, risk_flags)
        if publish_data := video_data.get("publish_draft"):
            render = _latest_render(db, video.id)
            if render:
                _upsert_publish_draft(db, workspace.id, video.id, render.id, publish_data, platform_accounts["primary"].id)

    _seed_jobs(db, workspace.id, created_videos[-1].id, fixture["job_cases"])
    db.commit()
    return {"workspace_slug": workspace.slug, "source_profile_external_id": profile.source_profile_external_id, "video_count": len(created_videos)}


def _upsert_profile(db: Session, workspace_id, payload: dict) -> SourceProfile:
    profile = db.scalar(select(SourceProfile).where(SourceProfile.source_platform == SourcePlatformEnum.DOUYIN, SourceProfile.source_profile_external_id == payload["source_profile_external_id"]))
    if profile is None:
        profile = SourceProfile(workspace_id=workspace_id, source_platform=SourcePlatformEnum.DOUYIN, source_profile_external_id=payload["source_profile_external_id"], profile_url=payload["profile_url"], status=SourceProfileStatus.ACTIVE)
        db.add(profile)
    profile.display_name = payload["display_name"]
    profile.handle = payload["handle"]
    profile.metadata_json = {"fixture": "alpha_demo"}
    db.flush()
    return profile


def _ensure_crawl_session(db: Session, workspace_id, profile_id) -> CrawlSession:
    session = db.scalar(select(CrawlSession).where(CrawlSession.source_profile_id == profile_id, CrawlSession.normalized_profile_identifier == "alpha-demo-seed"))
    if session is None:
        session = CrawlSession(workspace_id=workspace_id, source_platform=SourcePlatformEnum.DOUYIN, source_profile_id=profile_id, normalized_profile_identifier="alpha-demo-seed", submitted_profile_url="https://www.douyin.com/user/demo-douyin-food")
        db.add(session)
    session.status = CrawlSessionStatus.COMPLETED
    session.started_at = datetime.now(UTC) - timedelta(minutes=10)
    session.finished_at = datetime.now(UTC) - timedelta(minutes=9)
    session.result_summary_json = {"seed": "alpha_demo", "videos": 5}
    db.flush()
    return session


def _upsert_video(db: Session, workspace_id, profile_id, crawl_session_id, payload: dict, index: int) -> SourceVideo:
    video = db.scalar(select(SourceVideo).where(SourceVideo.source_platform == SourcePlatformEnum.DOUYIN, SourceVideo.source_video_external_id == payload["external_id"]))
    if video is None:
        video = SourceVideo(workspace_id=workspace_id, source_profile_id=profile_id, first_crawl_session_id=crawl_session_id, source_platform=SourcePlatformEnum.DOUYIN, source_video_external_id=payload["external_id"], source_url=f"https://www.douyin.com/video/{payload['external_id']}")
        db.add(video)
    video.caption = payload["caption"]
    video.duration_seconds = payload["duration_seconds"]
    video.status = SourceVideoStatus(payload["status"])
    video.posted_at = datetime.now(UTC) - timedelta(days=index + 1)
    video.metadata_json = {"fixture_path": payload["path"], **payload.get("metadata_json", {})}
    db.flush()
    return video


def _upsert_metric_snapshot(db: Session, workspace_id, video_id, crawl_session_id, metrics: dict) -> None:
    snapshot = db.scalar(select(VideoMetricSnapshot).where(VideoMetricSnapshot.source_video_id == video_id, VideoMetricSnapshot.crawl_session_id == crawl_session_id))
    if snapshot is None:
        snapshot = VideoMetricSnapshot(workspace_id=workspace_id, source_video_id=video_id, crawl_session_id=crawl_session_id)
        db.add(snapshot)
    for key, value in metrics.items():
        setattr(snapshot, key, value)


def _upsert_candidate(db: Session, workspace_id, video_id, payload: dict) -> None:
    candidate = db.scalar(select(VideoCandidate).where(VideoCandidate.source_video_id == video_id))
    if candidate is None:
        candidate = VideoCandidate(workspace_id=workspace_id, source_video_id=video_id)
        db.add(candidate)
    candidate.status = CandidateStatus(payload["status"])
    candidate.score = payload["score"]
    candidate.score_label = payload["score_label"]
    candidate.score_version = "REUP_SCORE_V1"
    candidate.score_breakdown_json = {"engagement_quality": {"normalized_subscore": 86, "weight": 0.25, "weighted_contribution": 21.5}}
    candidate.inclusion_reasons_json = ["strong engagement", "operator demo fixture"]
    candidate.warnings_json = []
    candidate.priority = int(payload["score"])


def _seed_media_and_render(db: Session, storage: LocalStorageBackend, workspace_id, video: SourceVideo, *, approved: bool) -> None:
    raw_asset = _upsert_asset(db, storage, workspace_id, video.id, MediaAssetType.SOURCE_VIDEO_RAW, f"demo/{video.source_video_external_id}/raw/source.mp4", b"demo source video", "video/mp4", "raw")
    final_asset = _upsert_asset(db, storage, workspace_id, video.id, MediaAssetType.FINAL_RENDER_VIDEO, f"demo/{video.source_video_external_id}/renders/final.mp4", b"demo final render", "video/mp4", "render_outputs")
    render = _latest_render(db, video.id)
    if render is None:
        render = RenderOutput(workspace_id=workspace_id, source_video_id=video.id, version=1)
        db.add(render)
    render.media_asset_id = final_asset.id
    render.status = RenderOutputStatus.APPROVED if approved else RenderOutputStatus.READY_FOR_REVIEW
    render.render_type = "final"
    render.output_format = "mp4"
    render.width = 1080
    render.height = 1920
    render.fps = 30
    render.duration_seconds = video.duration_seconds
    render.video_codec = "h264"
    render.audio_codec = "aac"
    render.subtitle_burned = True
    render.audio_strategy = "replace_with_vietnamese_narration"
    render.render_version = "RENDER_PIPELINE_V1_DEMO"
    render.warning_summary_json = {"warnings": []}
    render.metadata_json = {"manifest": {"output": {"asset_id": str(final_asset.id)}, "source": {"asset_id": str(raw_asset.id)}}}


def _upsert_asset(db: Session, storage: LocalStorageBackend, workspace_id, video_id, asset_type: MediaAssetType, key: str, content: bytes, mime_type: str, group: str) -> MediaAsset:
    write = storage.write_bytes(key, content)
    asset = db.scalar(select(MediaAsset).where(MediaAsset.source_video_id == video_id, MediaAsset.asset_type == asset_type, MediaAsset.version == 1))
    if asset is None:
        asset = MediaAsset(workspace_id=workspace_id, source_video_id=video_id, asset_type=asset_type, version=1)
        db.add(asset)
    asset.status = MediaAssetStatus.AVAILABLE
    asset.storage_provider = write.storage_provider
    asset.storage_key = write.storage_key
    asset.logical_key = write.storage_key
    asset.relative_path = write.relative_path
    asset.manifest_group = group
    asset.is_current = True
    asset.mime_type = mime_type
    asset.size_bytes = write.size_bytes
    asset.checksum_sha256 = write.checksum_sha256
    asset.metadata_json = {"fixture": "alpha_demo"}
    db.flush()
    return asset


def _seed_segments(db: Session, workspace_id, video_id) -> None:
    transcript = db.scalar(select(TranscriptSegment).where(TranscriptSegment.source_video_id == video_id, TranscriptSegment.segment_index == 0, TranscriptSegment.version == 1))
    if transcript is None:
        transcript = TranscriptSegment(workspace_id=workspace_id, source_video_id=video_id, segment_index=0, version=1, start_ms=0, end_ms=3200, text="这是一个演示片段", language_code="zh", status=TranscriptSegmentStatus.DRAFT)
        db.add(transcript)
        db.flush()
    translation = db.scalar(select(TranslationSegment).where(TranslationSegment.transcript_segment_id == transcript.id, TranslationSegment.language_code == "vi", TranslationSegment.version == 1))
    if translation is None:
        translation = TranslationSegment(workspace_id=workspace_id, source_video_id=video_id, transcript_segment_id=transcript.id, segment_index=0, language_code="vi", version=1, text="Day la mot doan demo da Viet hoa.", status=TranscriptSegmentStatus.DRAFT, duration_budget_ms=3200)
        db.add(translation)
        db.flush()
    subtitle = db.scalar(select(SubtitleSegment).where(SubtitleSegment.source_video_id == video_id, SubtitleSegment.segment_index == 0, SubtitleSegment.version == 1))
    if subtitle is None:
        db.add(SubtitleSegment(workspace_id=workspace_id, source_video_id=video_id, translation_segment_id=translation.id, segment_index=0, version=1, start_ms=0, end_ms=3200, text=translation.text, status=TranscriptSegmentStatus.DRAFT, track_kind="vietnamese_hard_burn"))


def _seed_risk_flags(db: Session, workspace_id, video_id, flags: list[dict]) -> None:
    for payload in flags:
        existing = db.scalar(select(RiskFlag).where(RiskFlag.source_video_id == video_id, RiskFlag.flag_type == RiskFlagType(payload["flag_type"]), RiskFlag.title == payload["title"]))
        if existing is None:
            db.add(RiskFlag(workspace_id=workspace_id, source_video_id=video_id, target_type=RiskTargetType.SOURCE_VIDEO, target_id=video_id, flag_type=RiskFlagType(payload["flag_type"]), severity=RiskSeverity(payload["severity"]), status=RiskFlagStatus.OPEN, title=payload["title"], description="Demo warning for alpha risk flow.", evidence_summary="Seeded fixture signal", scan_source="alpha_demo_seed", detected_at=datetime.now(UTC)))


def _seed_platform_accounts(db: Session, workspace_id) -> dict[str, PlatformAccount]:
    primary = db.scalar(select(PlatformAccount).where(PlatformAccount.workspace_id == workspace_id, PlatformAccount.external_account_id == "fb-page-demo-food-main"))
    if primary is None:
        primary = PlatformAccount(
            workspace_id=workspace_id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            display_name="FB Page Demo Food Main",
            external_account_id="fb-page-demo-food-main",
            token_reference="env:FACEBOOK_PAGE_ACCESS_TOKEN",
        )
        db.add(primary)
    primary.status = PlatformAccountStatus.ACTIVE
    primary.priority = 10
    primary.is_on_hold = False
    primary.allowed_niches_json = ["food", "kitchen", "affiliate"]
    primary.routing_notes = "Primary demo Page for food short videos."

    backup = db.scalar(select(PlatformAccount).where(PlatformAccount.workspace_id == workspace_id, PlatformAccount.external_account_id == "fb-page-demo-backup-held"))
    if backup is None:
        backup = PlatformAccount(
            workspace_id=workspace_id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            display_name="FB Page Demo Backup Held",
            external_account_id="fb-page-demo-backup-held",
            token_reference="env:FACEBOOK_PAGE_ACCESS_TOKEN",
        )
        db.add(backup)
    backup.status = PlatformAccountStatus.ACTIVE
    backup.priority = 80
    backup.is_on_hold = True
    backup.hold_reason = "Seeded hold state to demonstrate account health routing."
    backup.allowed_niches_json = ["food"]
    backup.routing_notes = "Held demo Page; routing should explain why it is blocked."
    db.flush()
    return {"primary": primary, "backup": backup}


def _seed_routing_rule(db: Session, workspace_id, primary_account_id) -> None:
    rule = db.scalar(select(PublishRoutingRule).where(PublishRoutingRule.workspace_id == workspace_id, PublishRoutingRule.rule_name == "demo-food-to-main-page"))
    if rule is None:
        rule = PublishRoutingRule(workspace_id=workspace_id, rule_name="demo-food-to-main-page")
        db.add(rule)
    rule.platform = PublishTargetPlatform.FACEBOOK_REELS
    rule.status = PublishRoutingRuleStatus.ACTIVE
    rule.priority = 10
    rule.match_json = {"niches": ["food", "kitchen"], "source_profile": "demo-douyin-food"}
    rule.action_json = {"recommend_account_ids": [str(primary_account_id)]}
    rule.fallback_behavior = "manual_review"
    rule.notes = "Seeded deterministic routing rule for the publish control plane."


def _upsert_publish_draft(db: Session, workspace_id, video_id, render_id, payload: dict, primary_account_id) -> None:
    target_platform = PublishTargetPlatform(payload["target_platform"])
    draft = db.scalar(select(PublishDraft).where(PublishDraft.source_video_id == video_id, PublishDraft.target_platform == target_platform.value, PublishDraft.version == 1))
    if draft is None:
        draft = PublishDraft(workspace_id=workspace_id, source_video_id=video_id, render_output_id=render_id, target_platform=target_platform.value, version=1)
        db.add(draft)
    draft.status = PublishDraftStatus(payload["status"])
    draft.caption = "Video da Viet hoa, san sang dang thu nghiem."
    draft.cta_text = "Theo doi de xem them video moi."
    draft.hashtags_json = [{"tag": "vietsub", "source": "alpha_demo"}, {"tag": "shortvideo", "source": "alpha_demo"}]
    draft.language_code = "vi"
    draft.generation_source = "alpha_demo_seed"
    draft.assigned_platform_account_id = primary_account_id
    draft.assignment_status = PublishAccountAssignmentStatus.ASSIGNED
    draft.assigned_at = datetime.now(UTC) - timedelta(minutes=15)
    draft.assigned_reason = "Seeded routing recommendation accepted for demo."
    draft.assignment_metadata_json = {"source": "alpha_demo_seed", "routing_confidence": "high"}
    db.flush()
    if draft.status == PublishDraftStatus.PUBLISHED:
        _seed_successful_publish_attempt(db, workspace_id, draft, primary_account_id)


def _seed_successful_publish_attempt(db: Session, workspace_id, draft: PublishDraft, primary_account_id) -> None:
    now = datetime.now(UTC)
    attempt = db.scalar(select(PublishAttempt).where(PublishAttempt.publish_draft_id == draft.id, PublishAttempt.attempt_number == 1))
    if attempt is None:
        attempt = PublishAttempt(workspace_id=workspace_id, publish_draft_id=draft.id, platform_account_id=primary_account_id, attempt_number=1)
        db.add(attempt)
    attempt.platform = PublishTargetPlatform.FACEBOOK_REELS
    attempt.status = PublishAttemptStatus.SUCCEEDED
    attempt.started_at = now - timedelta(hours=2, minutes=2)
    attempt.finished_at = now - timedelta(hours=2)
    attempt.external_publish_id = "fb-reel-demo-1001"
    attempt.external_media_id = "fb-media-demo-1001"
    attempt.external_reel_id = "fb-reel-demo-1001"
    attempt.external_permalink = "https://facebook.com/reel/fb-reel-demo-1001"
    attempt.external_status = ExternalPublicationStatus.PUBLISHED
    attempt.reconciliation_status = PublishReconciliationStatus.NOT_REQUIRED
    attempt.reconciliation_required = False
    attempt.last_status_checked_at = now - timedelta(hours=1, minutes=45)
    attempt.request_summary_json = {"mode": "seeded_demo", "caption_length": len(draft.caption or "")}
    attempt.response_summary_json = {"external_publish_id": attempt.external_publish_id, "permalink": attempt.external_permalink}
    attempt.warning_summary_json = {"warnings": []}
    db.flush()

    draft.latest_publish_attempt_id = attempt.id
    draft.canonical_publish_attempt_id = attempt.id
    draft.current_publication_status = ExternalPublicationStatus.PUBLISHED
    draft.current_external_publish_id = attempt.external_publish_id
    draft.current_external_permalink = attempt.external_permalink
    draft.published_at = attempt.finished_at
    draft.last_publish_synced_at = attempt.last_status_checked_at
    draft.publication_summary_json = {
        "canonical_attempt_id": str(attempt.id),
        "external_publish_id": attempt.external_publish_id,
        "external_permalink": attempt.external_permalink,
        "external_status": attempt.external_status.value,
        "summary_source": "alpha_demo_seed",
    }

    feedback = db.scalar(select(OperatorFeedback).where(OperatorFeedback.publish_attempt_id == attempt.id))
    if feedback is None:
        feedback = OperatorFeedback(
            workspace_id=workspace_id,
            target_type=OperatorFeedbackTargetType.PUBLISH_ATTEMPT,
            target_id=attempt.id,
            publish_attempt_id=attempt.id,
            publish_draft_id=draft.id,
            source_video_id=draft.source_video_id,
            render_output_id=draft.render_output_id,
        )
        db.add(feedback)
    feedback.quality_label = OperatorFeedbackQualityLabel.GOOD
    feedback.publish_confidence = PublishConfidenceLabel.SCALABLE
    feedback.root_cause = OperatorFeedbackRootCause.OTHER
    feedback.note = "Seeded successful publication for analytics and optimization demo."
    feedback.created_by = "alpha_demo_seed"
    feedback.feedback_at = now - timedelta(hours=1, minutes=30)


def _seed_jobs(db: Session, workspace_id, video_id, job_cases: list[dict]) -> None:
    for payload in job_cases:
        key = f"alpha-demo-{payload['job_type'].lower()}-{payload['status'].lower()}"
        job = db.scalar(select(Job).where(Job.workspace_id == workspace_id, Job.idempotency_key == key))
        if job is None:
            job = Job(workspace_id=workspace_id, job_type=JobType(payload["job_type"]), idempotency_key=key, source_video_id=video_id)
            db.add(job)
            db.flush()
            db.add(JobStep(workspace_id=workspace_id, job_id=job.id, step_key="demo_step", step_name="Demo step", step_order=0, sequence_index=0))
        job.status = JobStatus(payload["status"])
        job.error_code = payload.get("error_code")
        job.error_message = "Seeded alpha failure path" if job.error_code else None
        for step in job.steps:
            step.status = JobStepStatus.FAILED if job.status == JobStatus.FAILED else JobStepStatus.COMPLETED


def _latest_render(db: Session, video_id) -> RenderOutput | None:
    return db.scalar(select(RenderOutput).where(RenderOutput.source_video_id == video_id).order_by(RenderOutput.created_at.desc()).limit(1))


def main() -> None:
    with get_session_factory()() as db:
        result = seed_demo_data(db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
