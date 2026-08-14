from dataclasses import dataclass

from src.enums import JobType


@dataclass(frozen=True)
class StepTemplate:
    key: str
    name: str
    order: int


STEP_TEMPLATES: dict[JobType, tuple[StepTemplate, ...]] = {
    JobType.VALIDATE_DOUYIN_ACCOUNT: (
        StepTemplate("validate_account", "Validate Douyin account", 0),
        StepTemplate("finalize", "Finalize health summary", 1),
    ),
    JobType.REVALIDATE_STALE_DOUYIN_ACCOUNTS: (
        StepTemplate("find_due_accounts", "Find due Douyin accounts", 0),
        StepTemplate("validate_accounts", "Validate due Douyin accounts", 1),
        StepTemplate("finalize", "Finalize health sweep", 2),
    ),
    JobType.CRAWL_PROFILE: (
        StepTemplate("validate_input", "Validate input", 0),
        StepTemplate("resolve_profile", "Resolve profile", 1),
        StepTemplate("fetch_profile_payload", "Fetch profile payload", 2),
        StepTemplate("normalize_payload", "Normalize payload", 3),
        StepTemplate("upsert_profile", "Upsert profile", 4),
        StepTemplate("upsert_videos", "Upsert videos", 5),
        StepTemplate("create_metric_snapshots", "Create metric snapshots", 6),
        StepTemplate("finalize_session", "Finalize session", 7),
    ),
    JobType.SCORE_CANDIDATES: (
        StepTemplate("load_candidates", "Load candidates placeholder", 0),
        StepTemplate("score_candidates", "Score candidates placeholder", 1),
        StepTemplate("persist_scores", "Persist scores placeholder", 2),
        StepTemplate("finalize", "Finalize", 3),
    ),
    JobType.DOWNLOAD_VIDEO: (
        # The transfer is one resumable, ffprobe-gated boundary. Its internal
        # subphases are emitted as heartbeat metadata; no zero-work placeholder
        # rows should make the UI appear frozen at 71%.
        StepTemplate("register_assets", "Download, validate and register assets", 0),
        StepTemplate("finalize_manifest", "Finalize manifest", 1),
    ),
    JobType.ANALYZE_AUDIO: (
        StepTemplate("validate_input", "Validate input", 0),
        StepTemplate("resolve_assets", "Resolve audio assets", 1),
        StepTemplate("extract_audio_if_needed", "Extract audio if needed", 2),
        StepTemplate("separate_sources", "Separate sources", 3),
        StepTemplate("transcribe", "Transcribe speech", 4),
        StepTemplate("build_transcript_segments", "Build transcript segments", 5),
        StepTemplate("build_translation_draft", "Build translation draft", 6),
        StepTemplate("persist_outputs", "Persist outputs", 7),
        StepTemplate("finalize", "Finalize", 8),
    ),
    JobType.ANALYZE_OCR: (
        StepTemplate("sample_frames", "Prepare Phase 1 v58 geometry", 0),
        StepTemplate("detect_text", "Run local Phase 2 OCR", 1),
        StepTemplate("group_objects", "Build hash-bound OCR review", 2),
        StepTemplate("remove_hardsub", "Prepare localization authority", 3),
        StepTemplate("persist_outputs", "Persist quality localization artifacts", 4),
        StepTemplate("finalize", "Finalize OCR checkpoint", 5),
    ),
    JobType.BUILD_TRANSLATION_DRAFT: (
        StepTemplate("load_transcript", "Load approved transcript beats", 0),
        StepTemplate("translate_segments", "Translate contextual candidate blocks", 1),
        StepTemplate("prepare_review", "Prepare Checkpoint #1 review", 2),
        StepTemplate("finalize", "Finalize", 3),
    ),
    JobType.SYNTHESIZE_TTS: (
        StepTemplate("validate_input", "Validate approved Vietnamese timeline", 0),
        StepTemplate("resolve_translation_segments", "Repair dialogue boundaries", 1),
        StepTemplate("synthesize_segment_clips", "Probe voice and synthesize candidates", 2),
        StepTemplate("evaluate_timing_fit", "Apply selective timeline correction", 3),
        StepTemplate("assemble_narration_track", "Assemble full-duration narration", 4),
        StepTemplate("build_subtitle_segments", "Bind subtitles to final TTS timing", 5),
        StepTemplate("export_subtitle_assets", "Export subtitles and temporal QA", 6),
        StepTemplate("build_render_prep_manifest", "Preserve background and prepare render", 7),
        StepTemplate("persist_outputs", "Persist Temporal V3 outputs", 8),
        StepTemplate("finalize", "Finalize TTS Temporal V3", 9),
    ),
    JobType.RENDER_PREVIEW: (
        StepTemplate("prepare_timeline", "Apply translation review", 0),
        StepTemplate("render_preview", "Build adaptive visual preview", 1),
        StepTemplate("persist_output", "Persist preview and Output QA", 2),
        StepTemplate("finalize", "Finalize visual checkpoint", 3),
    ),
    JobType.RENDER_FINAL: (
        StepTemplate("validate_input", "Validate input", 0),
        StepTemplate("resolve_render_prep", "Resolve render-prep manifest", 1),
        StepTemplate("probe_source_video", "Probe source video", 2),
        StepTemplate("prepare_audio", "Prepare audio replacement", 3),
        StepTemplate("prepare_subtitle_burn", "Prepare subtitle burn", 4),
        StepTemplate("export_video", "Export video", 5),
        StepTemplate("validate_output", "Validate output", 6),
        StepTemplate("persist_render_output", "Persist render output", 7),
        StepTemplate("finalize", "Finalize", 8),
    ),
    JobType.PUBLISH_CONTENT: (
        StepTemplate("validate_draft", "Validate publish draft", 0),
        StepTemplate("resolve_render_output", "Resolve approved render output", 1),
        StepTemplate("resolve_platform_account", "Resolve platform account", 2),
        StepTemplate("evaluate_gate", "Evaluate publish gate", 3),
        StepTemplate("initialize_attempt", "Initialize publish attempt", 4),
        StepTemplate("upload_media", "Upload media", 5),
        StepTemplate("finalize_publish", "Finalize platform publish", 6),
        StepTemplate("sync_status", "Sync status", 7),
        StepTemplate("persist_result", "Persist publish result", 8),
    ),
    JobType.REFRESH_PUBLISH_STATUS: (
        StepTemplate("validate_target", "Validate publish attempt target", 0),
        StepTemplate("query_platform_status", "Query platform publish status", 1),
        StepTemplate("normalize_external_status", "Normalize external status", 2),
        StepTemplate("apply_reconciliation_rules", "Apply reconciliation rules", 3),
        StepTemplate("persist_updates", "Persist status updates", 4),
        StepTemplate("finalize", "Finalize", 5),
    ),
    JobType.RECONCILE_PUBLISH_ATTEMPT: (
        StepTemplate("validate_target", "Validate publish draft or attempt target", 0),
        StepTemplate("resolve_uncertain_attempts", "Resolve uncertain attempts", 1),
        StepTemplate("query_platform_status", "Query platform status", 2),
        StepTemplate("apply_reconciliation_rules", "Apply reconciliation rules", 3),
        StepTemplate("persist_updates", "Persist reconciliation result", 4),
        StepTemplate("finalize", "Finalize", 5),
    ),
    JobType.COLLECT_PUBLICATION_METRICS: (
        StepTemplate("validate_publication", "Validate platform publication", 0),
        StepTemplate("validate_account", "Validate account and metrics cooldown", 1),
        StepTemplate("collect_and_persist_snapshot", "Collect and persist metric snapshot", 2),
        StepTemplate("finalize", "Finalize metric collection", 3),
    ),
    JobType.CLASSIFY_CONTENT: (
        StepTemplate("validate_publication", "Validate publication and taxonomy", 0),
        StepTemplate("collect_evidence", "Collect caption, transcript, and OCR evidence", 1),
        StepTemplate("classify_and_persist", "Classify and persist topic result", 2),
        StepTemplate("finalize", "Finalize content classification", 3),
    ),
    JobType.MATCH_AFFILIATE_PRODUCTS: (
        StepTemplate("validate_classification", "Validate approved topic classification", 0),
        StepTemplate("load_catalog", "Load active affiliate catalog", 1),
        StepTemplate("match_and_persist", "Match products and persist review suggestions", 2),
        StepTemplate("finalize", "Finalize product matching", 3),
    ),
    JobType.CALCULATE_GROWTH_SCORE: (
        StepTemplate("validate_publication", "Validate platform publication", 0),
        StepTemplate("load_metric_evidence", "Load stable metric evidence", 1),
        StepTemplate("calculate_and_persist", "Calculate and persist Growth Score", 2),
        StepTemplate("finalize", "Finalize Growth Score", 3),
    ),
    JobType.POST_AFFILIATE_COMMENT: (
        StepTemplate("validate_approval", "Validate operator approval and opportunity gates", 0),
        StepTemplate("resolve_page_credential", "Resolve Facebook Page credential", 1),
        StepTemplate("post_comment", "Post affiliate comment to Facebook Reel", 2),
        StepTemplate("persist_result", "Persist external comment result", 3),
        StepTemplate("finalize", "Finalize affiliate comment placement", 4),
    ),
    JobType.VERIFY_AFFILIATE_COMMENT: (
        StepTemplate("validate_target", "Validate posted comment target", 0),
        StepTemplate("verify_comment_and_link", "Verify Facebook comment and affiliate link", 1),
        StepTemplate("persist_result", "Persist verification result", 2),
        StepTemplate("finalize", "Finalize comment verification", 3),
    ),
}


def get_step_templates(job_type: JobType) -> tuple[StepTemplate, ...]:
    return STEP_TEMPLATES[job_type]
