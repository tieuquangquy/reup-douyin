from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API service."""

    app_env: str = "local"
    database_url: str
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    local_storage_root: str = "./data/storage"
    # Content-addressed controlled-pilot recipe used by Reup Queue auto runs.
    # Empty means the repository's docs/pipeline-recipes current pointer.
    pipeline_recipe_lock_path: str = ""
    log_level: str = "INFO"
    douyin_enable_live_fetch: bool = False
    douyin_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
    douyin_session_cookie: str | None = None
    douyin_proxy_url: str | None = None
    douyin_fetch_timeout_seconds: float = 15.0
    douyin_fetch_max_videos: int = 50
    douyin_yt_dlp_enabled: bool = True
    douyin_yt_dlp_binary: str = "yt-dlp"
    douyin_yt_dlp_format: str = "bestvideo*+bestaudio/best"
    douyin_yt_dlp_timeout_seconds: int = 180
    douyin_yt_dlp_prefer_browser_cookies: bool = True
    douyin_download_cookie_store_dir: str | None = None
    douyin_playwright_download_enabled: bool = True
    douyin_playwright_download_timeout_ms: int = 90_000
    douyin_playwright_download_staging_dir: str | None = None
    # When cookie-store yt-dlp fails, auto-open Playwright for download fallback.
    # Headless=True keeps Chromium in background (no operator window).
    douyin_playwright_download_auto_open: bool = True
    douyin_playwright_download_headless: bool = True
    # Strict HQ/no-logo: do not persist watermarked play streams unless explicitly allowed.
    douyin_download_allow_watermarked_fallback: bool = False
    douyin_download_api_base_url: str = "http://127.0.0.1:8000"
    # DOWNLOAD_VIDEO retry policy (error-class aware).
    douyin_download_transient_max_attempts: int = 8
    douyin_download_auth_max_attempts: int = 2
    douyin_download_retry_backoff_base_seconds: int = 5
    douyin_download_retry_backoff_max_seconds: int = 120
    douyin_persistent_browser_profile_enabled: bool = True
    douyin_persistent_browser_profiles_root_dir: str = "./data/browser-profiles/douyin"
    douyin_prefer_browser_profile_for_validation: bool = True
    douyin_prefer_browser_profile_for_fetch: bool = True
    douyin_allow_legacy_http_fallback_for_intake: bool = False
    douyin_persistent_browser_context_enabled: bool = True
    douyin_reuse_live_browser_for_validation: bool = True
    douyin_reuse_live_browser_for_fetch: bool = True
    douyin_browser_context_idle_timeout_seconds: int = 1800
    douyin_browser_context_max_lifetime_seconds: int = 14400
    douyin_browser_connect_stabilization_seconds: int = 8
    douyin_intake_preflight_cache_ttl_seconds: int = 30
    douyin_browser_profile_fetch_scroll_passes: int = 4
    douyin_browser_profile_fetch_settle_seconds: int = 2
    douyin_enable_legacy_manual_import: bool = False
    douyin_enable_legacy_http_fallback: bool = False
    douyin_enable_legacy_debug_surfaces: bool = False
    api_auth_required: bool = True
    jwt_secret_key: str = "local-dev-insecure-change-me"
    jwt_issuer: str | None = None
    # Legacy single audience (falls back as web audience when jwt_web_audience unset).
    jwt_audience: str | None = None
    jwt_web_audience: str | None = None
    jwt_api_audience: str | None = None
    jwt_ops_audience: str | None = None
    # Phase B session hardening
    auth_access_token_ttl_minutes: int = 30
    auth_api_ui_access_token_ttl_minutes: int = 15
    auth_ops_access_token_ttl_minutes: int = 30
    auth_refresh_token_ttl_days: int = 14
    auth_registration_enabled: bool = True
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: float = 300.0
    auth_invite_ttl_days: int = 7
    douyin_secret_encryption_key_ref: str | None = None
    # Hard cap for batch START_PROCESSING / START_AUTO (Playwright download path). Soft ceiling ~100.
    reup_queue_start_processing_batch_limit: int = 30
    # Max DOWNLOAD_VIDEO jobs RUNNING per workspace at once (Start-auto queue storm guard).
    download_video_max_concurrent_running: int = 1
    # Requeue RUNNING jobs older than N seconds (hung register_assets / ~71% guard). None = auto.
    download_video_stale_running_seconds: int | None = None
    # Lock age without a heartbeat before a RUNNING job is treated as dead, per job type.
    # Dead workers are caught immediately by orphan release; these are the backstop only.
    analyze_audio_stale_running_seconds: int = 2_700
    build_translation_draft_stale_running_seconds: int = 1_800
    synthesize_tts_stale_running_seconds: int = 2_700
    analyze_ocr_stale_running_seconds: int = 5_400
    render_preview_stale_running_seconds: int = 3_600
    render_final_stale_running_seconds: int = 5_400
    job_stale_running_seconds_default: int = 1_800
    job_heartbeat_seconds: int = 30
    # Kill only the isolated Phase-1 subprocess when it emits no frame progress.
    # The durable scan checkpoint lets the normal retry resume without restarting DBNet at frame 0.
    phase1_no_progress_timeout_seconds: int = 300
    # Post-processing can legitimately spend much longer than one scan frame on
    # 2K/4K sources with thousands of DBNet hits.  It emits stage heartbeats, but
    # keep a separate ceiling so the scan watchdog does not kill healthy track
    # reconciliation while still bounding a genuinely wedged subprocess.
    phase1_postprocess_no_progress_timeout_seconds: int = 1_200
    # Even out perceived volume across the batch (EBU R128 single-pass loudnorm at render).
    render_loudness_normalization_enabled: bool = True
    render_loudness_target_lufs: float = -14.0
    # Preserve the source background stem at unity before the final loudness
    # pass; a lower pre-mix gain made approved music practically inaudible.
    render_background_mix_gain: float = 1.0
    # auto probes a real hardware encode, then falls back to libx264 when unavailable.
    # Explicit values: libx264 | h264_nvenc | h264_qsv | h264_videotoolbox.
    render_video_encoder: str = "auto"
    render_hardware_encoder_smoke_probe: bool = True
    render_hardware_encoder_fallback_enabled: bool = True
    # Reclaim regenerable intermediates (stems, extracted audio, TTS clips, OCR frames) from
    # clips that finished with a deliverable. Off by default: deleting media is unforgiving.
    artifact_retention_enabled: bool = False
    artifact_retention_min_age_hours: int = 24
    # The cleaned (hardsub-removed) video is the biggest win, but some flows re-render from it.
    artifact_retention_include_cleaned_video: bool = False
    artifact_retention_sweep_interval_seconds: int = 900
    # Free space required on the storage volume before a heavy media job starts. ffmpeg does
    # not fail cleanly on a full disk — it writes a truncated file that looks successful.
    # Set to 0 to disable the guard.
    min_free_disk_gb: int = 10
    # How many clips the auto lane keeps moving at once. Starting everything at once
    # finishes nothing; a bounded lane delivers finished videos in a steady stream.
    reup_max_items_in_flight: int = 5
    # Shared budget for stages that load a model or encoder onto the GPU. Per-type slots
    # alone would still let OCR + TTS + render collide on one card.
    gpu_max_concurrent_running: int = 1
    # Running-job caps per workspace for the stages that saturate one machine.
    analyze_audio_max_concurrent_running: int = 1
    synthesize_tts_max_concurrent_running: int = 2
    analyze_ocr_max_concurrent_running: int = 1
    render_final_max_concurrent_running: int = 1
    metrics_collection_max_concurrent_running: int = 2
    classification_max_concurrent_running: int = 2
    affiliate_matching_max_concurrent_running: int = 2
    # Auto-retry for pipeline stages after download (transient provider/IO failures).
    pipeline_transient_max_attempts: int = 3
    pipeline_retry_backoff_base_seconds: int = 15
    pipeline_retry_backoff_max_seconds: int = 300
    # Publication metrics collector: cheap network reads, bounded for provider quotas.
    metrics_collection_stale_running_seconds: int = 300
    classification_stale_running_seconds: int = 1_800
    affiliate_matching_stale_running_seconds: int = 1_800
    metrics_collection_retry_backoff_base_seconds: int = 60
    metrics_collection_retry_backoff_max_seconds: int = 3600
    metrics_collection_rate_limit_cooldown_seconds: int = 900
    # Schedules are opt-in per publication; the worker sweep can therefore be on by default.
    metrics_scheduler_enabled: bool = True
    metrics_scheduler_sweep_interval_seconds: int = 60
    metrics_scheduler_dispatch_limit: int = 20
    # Meta OAuth onboarding for Facebook Pages. Disabled until all required
    # values are configured; Page tokens are encrypted server-side only.
    facebook_app_id: str | None = None
    facebook_app_secret: str | None = None
    facebook_oauth_redirect_uri: str = "http://localhost:3000/publishing/accounts"
    facebook_graph_api_version: str = "v20.0"
    facebook_oauth_scopes: str = "pages_show_list,pages_read_engagement,read_insights,pages_manage_posts"
    facebook_oauth_session_ttl_minutes: int = 10
    facebook_oauth_request_timeout_seconds: float = 20.0
    platform_credential_encryption_key_ref: str | None = None
    # Local-first bootstrap: generated by the API on the first UI-managed
    # platform integration save when no external key reference is configured.
    # Production keeps fail-closed behavior and must use a managed key/KMS ref.
    platform_credential_local_key_path: str = "./data/secrets/platform-credentials.key"
    # Conservative Page-level admission control. These are product safety limits,
    # not claims about Meta's unpublished platform limits.
    facebook_publish_guardrails_enabled: bool = True
    facebook_publish_require_verified_capability: bool = True
    facebook_publish_capability_max_age_days: int = 30
    facebook_publish_max_concurrent_per_account: int = 1
    facebook_publish_min_interval_minutes: int = 60
    facebook_publish_max_attempts_per_24h: int = 6
    facebook_publish_max_failures_per_24h: int = 2
    facebook_publish_warmup_days: int = 7
    facebook_publish_warmup_min_interval_minutes: int = 360
    facebook_publish_warmup_max_attempts_per_24h: int = 2
    facebook_publish_observe_min_age_hours: int = 48
    facebook_publish_observe_min_successes: int = 2
    facebook_publish_observe_min_interval_minutes: int = 180
    facebook_publish_observe_max_attempts_per_24h: int = 3
    facebook_publish_standard_min_successes: int = 5
    facebook_publish_rate_limit_cooldown_minutes: int = 360
    # Conservative Page-level admission control. These are product safety limits,
    # not claims about Meta's unpublished platform limits.
    facebook_publish_guardrails_enabled: bool = True
    facebook_publish_require_verified_capability: bool = True
    facebook_publish_capability_max_age_days: int = 30
    facebook_publish_max_concurrent_per_account: int = 1
    facebook_publish_min_interval_minutes: int = 60
    facebook_publish_max_attempts_per_24h: int = 6
    facebook_publish_max_failures_per_24h: int = 2
    facebook_publish_warmup_days: int = 7
    facebook_publish_warmup_min_interval_minutes: int = 360
    facebook_publish_warmup_max_attempts_per_24h: int = 2
    facebook_publish_rate_limit_cooldown_minutes: int = 360

    # Audio analysis / localization (free stack). See docs/localization-reup-pipeline-design.md.
    # STT: funasr (default) or caption. FunASR requires optional `funasr` package + model download.
    audio_stt_provider: str = "funasr"
    # Hard cap for FunASR AutoModel load+generate (includes first ModelScope download).
    # On timeout, ANALYZE_AUDIO falls back to segmented caption STT.
    audio_funasr_timeout_seconds: float = 900.0
    # Translation: auto | gemini | qwen | placeholder
    audio_translation_provider: str = "auto"
    gemini_api_key: str | None = None
    # AI Studio examples: gemini-2.5-pro | gemini-2.5-flash | gemini-2.0-flash
    gemini_translation_model: str = "gemini-2.5-flash"
    # Conservative free-tier pacing (~4.6 RPM). Set to 0 only for a paid key
    # after measuring the provider quota; concurrency alone does not enforce RPM.
    gemini_translation_min_request_interval_seconds: float = 13.0
    # Off by default so ANALYZE_AUDIO does not hang on dead localhost:11434.
    # Enable after `ollama pull qwen2.5:14b` (or set GEMINI_API_KEY for free cloud).
    ollama_translation_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_translation_model: str = "qwen2.5:14b"
    # Bounded parallelism for BUILD_TRANSLATION_DRAFT (one LLM call per beat).
    # The service forces Gemini to one call at a time for free-tier RPM safety;
    # paid/local providers may raise this setting after a measured load test.
    audio_translation_max_concurrency: int = 1
    # TTS: workspace Ops active profile is authority for Generate TTS; these are env fallbacks.
    # Providers: auto | edge | vieneu | google | azure | elevenlabs | openai |
    # openai_compatible | http_custom | cli | placeholder
    audio_tts_provider: str = "auto"
    audio_tts_voice_id: str = "vi-VN-HoaiMyNeural"
    audio_tts_speaking_rate: float = 1.0
    audio_tts_api_key: str | None = None
    audio_tts_base_url: str = ""
    audio_tts_model_id: str = ""
    audio_tts_fallback_provider: str = "none"
    audio_tts_fallback_voice_id: str = ""
    audio_tts_local_backend: str = "auto"
    audio_tts_device: str = "auto"
    audio_tts_cli_binary: str = ""
    audio_tts_timeout_seconds: float = 120.0
    # When true, Ops TTS can run reviewed pip and managed-source engine recipes.
    audio_tts_allow_install: bool = True
    # Managed source checkouts, isolated venvs and model weights for one-click engine installs.
    audio_tts_engine_root: str = "./data/tts-engines"
    # Operator-owned dialogue translation system prompt (optional).
    # File path wins over inline when both are set. Relative paths resolve from process cwd.
    audio_translation_user_prompt: str | None = None
    audio_translation_user_prompt_file: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def effective_web_audience(self) -> str:
        return (self.jwt_web_audience or self.jwt_audience or "reup-douyin-web").strip()

    @property
    def effective_api_audience(self) -> str:
        return (self.jwt_api_audience or "reup-douyin-api").strip()

    @property
    def effective_ops_audience(self) -> str:
        return (self.jwt_ops_audience or "reup-douyin-ops").strip()

    @property
    def accepted_jwt_audiences(self) -> frozenset[str]:
        return frozenset(
            {
                self.effective_web_audience,
                self.effective_api_audience,
                self.effective_ops_audience,
            }
        )

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env in {"production", "prod"}:
            if not self.api_auth_required:
                raise ValueError("API_AUTH_REQUIRED must be true in production")
            if self.jwt_secret_key == "local-dev-insecure-change-me" or len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be a production-grade secret of at least 32 characters")
            if not self.douyin_secret_encryption_key_ref:
                raise ValueError("DOUYIN_SECRET_ENCRYPTION_KEY_REF is required in production")
            if self.facebook_app_id or self.facebook_app_secret:
                if not self.facebook_app_id or not self.facebook_app_secret:
                    raise ValueError("FACEBOOK_APP_ID and FACEBOOK_APP_SECRET must be configured together")
                if not self.platform_credential_encryption_key_ref:
                    raise ValueError("PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF is required for Facebook OAuth")
                if not self.facebook_oauth_redirect_uri.startswith("https://"):
                    raise ValueError("FACEBOOK_OAUTH_REDIRECT_URI must use HTTPS in production")
            if any(origin in {"*", "http://localhost:3000", "http://127.0.0.1:3000"} for origin in self.cors_origins):
                raise ValueError("CORS_ALLOWED_ORIGINS must not include wildcard or localhost origins in production")
            if self.douyin_enable_legacy_debug_surfaces:
                raise ValueError("DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES must be false in production")
            if self.douyin_enable_legacy_http_fallback or self.douyin_allow_legacy_http_fallback_for_intake:
                raise ValueError("Legacy Douyin HTTP fallback must be disabled in production")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
