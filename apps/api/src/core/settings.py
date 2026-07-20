from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API service."""

    app_env: str = "local"
    database_url: str
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    local_storage_root: str = "./data/storage"
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
    # Hard cap for batch START_PROCESSING (Playwright download path). Soft ceiling ~100.
    reup_queue_start_processing_batch_limit: int = 30

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
    # Off by default so ANALYZE_AUDIO does not hang on dead localhost:11434.
    # Enable after `ollama pull qwen2.5:14b` (or set GEMINI_API_KEY for free cloud).
    ollama_translation_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_translation_model: str = "qwen2.5:14b"
    # Bounded parallelism for BUILD_TRANSLATION_DRAFT (one LLM call per beat).
    # Lower if Gemini returns 429; raise carefully (5–8) for faster drafts.
    audio_translation_max_concurrency: int = 4
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
    # When true, Ops TTS can run allowlisted `pip install` into the API Python env.
    audio_tts_allow_install: bool = True
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
