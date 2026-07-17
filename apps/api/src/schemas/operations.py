from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TranslationPromptResponse(BaseModel):
    prompt: str = ""
    source: str = Field(description="workspace_db | empty")
    updated: bool = False


class TranslationPromptUpdateRequest(BaseModel):
    prompt: str = Field(default="", description="Operator system prompt; empty clears DB override")


class TranslationAiResponse(BaseModel):
    enabled: bool = False
    provider: str = "auto"
    model: str = ""
    api_key_set: bool = False
    api_key_masked: str = ""
    base_url: str = ""
    timeout_seconds: float = 90.0
    fallback_provider: str = "none"
    fallback_model: str = ""
    source: str = Field(description="workspace_db | env")
    updated: bool = False


class TranslationAiUpdateRequest(BaseModel):
    enabled: bool = False
    provider: str = Field(default="auto", description="auto | gemini | openai_compatible | ollama | placeholder")
    model: str = ""
    api_key: str | None = Field(
        default=None,
        description="Omit/null to keep existing key; empty string clears when clear_api_key is true",
    )
    clear_api_key: bool = False
    base_url: str = ""
    timeout_seconds: float = 90.0
    fallback_provider: str = "none"
    fallback_model: str = ""


class TranslationAiTestRequest(BaseModel):
    """Optional unsaved draft; when omitted, tests the saved workspace config (or env)."""

    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    timeout_seconds: float | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None


class TranslationAiTestResponse(BaseModel):
    ok: bool
    provider: str = ""
    detail: str = ""


class TranslationAiModelsRequest(BaseModel):
    """Draft credentials used to list models without requiring Save first."""

    provider: str = "auto"
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    timeout_seconds: float | None = None


class TranslationAiModelsResponse(BaseModel):
    ok: bool
    provider: str = ""
    models: list[str] = Field(default_factory=list)
    detail: str = ""


class TtsAiVoiceOption(BaseModel):
    id: str
    label: str = ""


class TtsAiCatalog(BaseModel):
    source: str = "none"
    voices: list[TtsAiVoiceOption] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    default_voice_id: str = ""
    warning: str = ""
    sample_rate: int | None = None
    backends: list[str] = Field(default_factory=list)


class TtsAiLastInstall(BaseModel):
    at: str = ""
    ok: bool = False
    command: str = ""
    package: str = ""
    detail: str = ""
    already_satisfied: bool = False


class TtsAiLastProbe(BaseModel):
    at: str = ""
    ok: bool = False
    provider: str = ""
    detail: str = ""
    catalog: TtsAiCatalog | None = None


class TtsAiRuntime(BaseModel):
    last_install: TtsAiLastInstall | None = None
    last_probe: TtsAiLastProbe | None = None


class TtsAiResponse(BaseModel):
    enabled: bool = False
    provider: str = "auto"
    voice_id: str = ""
    speaking_rate: float = 1.0
    language_code: str = "vi"
    model_id: str = ""
    api_key_set: bool = False
    api_key_masked: str = ""
    base_url: str = ""
    timeout_seconds: float = 120.0
    fallback_provider: str = "none"
    fallback_voice_id: str = ""
    local_backend: str = "auto"
    device: str = "auto"
    cli_binary: str = ""
    options_json: dict = Field(default_factory=dict)
    runtime: TtsAiRuntime = Field(default_factory=TtsAiRuntime)
    live_import_ok: bool | None = None
    source: str = Field(description="workspace_db | env")
    updated: bool = False


class TtsAiUpdateRequest(BaseModel):
    enabled: bool = False
    provider: str = Field(
        default="auto",
        description=(
            "auto | edge | vieneu | google | azure | elevenlabs | openai | "
            "openai_compatible | http_custom | cli | placeholder"
        ),
    )
    voice_id: str = ""
    speaking_rate: float = 1.0
    language_code: str = "vi"
    model_id: str = ""
    api_key: str | None = Field(
        default=None,
        description="Omit/null to keep existing key; empty string clears when clear_api_key is true",
    )
    clear_api_key: bool = False
    base_url: str = ""
    timeout_seconds: float = 120.0
    fallback_provider: str = "none"
    fallback_voice_id: str = ""
    local_backend: str = "auto"
    device: str = "auto"
    cli_binary: str = ""
    options_json: dict = Field(default_factory=dict)


class TtsAiTestRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    voice_id: str | None = None
    speaking_rate: float | None = None
    language_code: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    timeout_seconds: float | None = None
    fallback_provider: str | None = None
    fallback_voice_id: str | None = None
    local_backend: str | None = None
    device: str | None = None
    cli_binary: str | None = None
    options_json: dict | None = None


class TtsAiTestResponse(BaseModel):
    ok: bool
    provider: str = ""
    detail: str = ""
    catalog: TtsAiCatalog | None = None
    runtime: TtsAiRuntime | None = None


class TtsAiInstallRequest(BaseModel):
    install_command: str | None = Field(
        default=None,
        description="Allowlisted form: pip install <package> | pip install git+https://...",
    )
    package: str | None = Field(default=None, description="PyPI package name, e.g. edge-tts")
    repo_url: str | None = Field(
        default=None,
        description="https://github.com/org/repo(.git) — installed via pip git+",
    )
    timeout_seconds: float = 300.0
    # Optional: which provider to probe after install (defaults to saved workspace provider)
    provider: str | None = None


class TtsAiInstallResponse(BaseModel):
    ok: bool
    detail: str = ""
    command: str = ""
    log_tail: str = ""
    already_satisfied: bool = False
    probe_ok: bool | None = None
    probe_detail: str = ""
    provider: str = ""
    catalog: TtsAiCatalog | None = None
    runtime: TtsAiRuntime | None = None


class TtsAiPreviewRequest(BaseModel):
    text: str = Field(
        default="Xin chào, đây là bản xem trước giọng đọc tiếng Việt.",
        description="Short Vietnamese sample for one-shot synthesize preview",
    )
    max_chars: int = 280
    enabled: bool | None = None
    provider: str | None = None
    voice_id: str | None = None
    speaking_rate: float | None = None
    language_code: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    timeout_seconds: float | None = None
    fallback_provider: str | None = None
    fallback_voice_id: str | None = None
    local_backend: str | None = None
    device: str | None = None
    cli_binary: str | None = None
    options_json: dict | None = None


class TtsAiPreviewResponse(BaseModel):
    ok: bool
    provider: str = ""
    detail: str = ""
    mime_type: str = "audio/wav"
    duration_seconds: float = 0.0
    audio_base64: str = ""
    warnings: list[str] = Field(default_factory=list)
    text: str = ""


class BacklogSummary(BaseModel):
    queued: int = 0
    retryable: int = 0
    running: int = 0


class FailureCategory(BaseModel):
    error_code: str
    count: int


class AssetReuseSummary(BaseModel):
    asset_type: str
    current_count: int = 0
    historical_count: int = 0


class FetchHealthReasonCount(BaseModel):
    reason: str
    count: int


class FetchHealthAccountSummary(BaseModel):
    douyin_account_connection_id: str | None = None
    runs_total: int = 0
    blocked_runs: int = 0
    parse_warning_runs: int = 0
    failed_runs: int = 0


class FetchHealthSummary(BaseModel):
    window_runs: int = 0
    blocked_runs: int = 0
    parse_warning_runs: int = 0
    failed_runs: int = 0
    blocked_ratio_percent: float = 0.0
    top_blocked_reasons: list[FetchHealthReasonCount] = Field(default_factory=list)
    by_account: list[FetchHealthAccountSummary] = Field(default_factory=list)


class OperationalMetricsResponse(BaseModel):
    generated_at: datetime
    job_counts_by_type_status: dict[str, dict[str, int]] = Field(default_factory=dict)
    job_failure_rate_percent_by_type: dict[str, float] = Field(default_factory=dict)
    queue_backlog: BacklogSummary = Field(default_factory=BacklogSummary)
    retryable_jobs: int = 0
    total_retry_attempts: int = 0
    step_duration_by_job_type: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    average_processing_seconds_per_source_video: float = 0.0
    common_failure_categories: list[FailureCategory] = Field(default_factory=list)
    asset_reuse_by_type: list[AssetReuseSummary] = Field(default_factory=list)
    render_counts_by_status: dict[str, int] = Field(default_factory=dict)
    publish_draft_counts_by_status: dict[str, int] = Field(default_factory=dict)
    open_risk_counts_by_severity: dict[str, int] = Field(default_factory=dict)
    douyin_fetch_health: FetchHealthSummary = Field(default_factory=FetchHealthSummary)

