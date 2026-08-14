from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.jobs import JobResponse


class TopicCategoryCreateRequest(BaseModel):
    taxonomy_version: str = Field(default="CONTENT_TAXONOMY_V1", min_length=1, max_length=80)
    code: str = Field(min_length=2, max_length=100, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: UUID | None = None
    keywords: list[str] = Field(default_factory=list, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.strip().split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                result.append(cleaned)
                seen.add(key)
        return result


class TopicCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: UUID | None = None
    keywords: list[str] | None = Field(default=None, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str] | None) -> list[str] | None:
        return TopicCategoryCreateRequest.normalize_keywords(values) if values is not None else None


class TopicCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    taxonomy_version: str
    code: str
    name: str
    description: str | None
    parent_id: UUID | None
    keywords_json: list | None
    sort_order: int
    is_active: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class TopicCategoryListResponse(BaseModel):
    topics: list[TopicCategoryResponse]
    taxonomy_version: str


class ClassificationEvidenceResponse(BaseModel):
    source: Literal["PUBLICATION_TITLE", "PUBLICATION_CAPTION", "DRAFT_TITLE", "DRAFT_CAPTION", "SOURCE_CAPTION", "TRANSCRIPT", "OCR"]
    source_id: str | None = None
    text: str
    language_code: str | None = None
    confidence: float | None = None
    matched_keywords: list[str] = Field(default_factory=list)


class ContentClassificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    source_video_id: UUID | None
    taxonomy_version: str
    classifier_version: str
    input_fingerprint_sha256: str
    decision_status: Literal["NEEDS_REVIEW", "APPROVED", "OVERRIDDEN"]
    primary_topic_id: UUID | None
    primary_topic_code: str | None
    primary_topic_name: str | None = None
    confidence: float
    secondary_topics_json: list | None
    evidence_json: list | None
    rationale: str | None
    created_by_job_id: UUID | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    override_reason: str | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class ContentClassificationRunRequest(BaseModel):
    taxonomy_version: str = Field(default="CONTENT_TAXONOMY_V1", min_length=1, max_length=80)
    classifier_version: str = Field(default="HYBRID_CONTENT_V1", min_length=1, max_length=80)
    external_network_authorized: bool = False
    operator_confirmation: str | None = None

    @model_validator(mode="after")
    def validate_ai_authorization(self) -> "ContentClassificationRunRequest":
        if self.external_network_authorized and self.operator_confirmation != "CONTENT_CLASSIFICATION_AI_APPROVED":
            raise ValueError("AI classification requires explicit operator confirmation")
        return self


class ContentClassificationRunResponse(BaseModel):
    reused: bool
    classification: ContentClassificationResponse | None = None
    job: JobResponse | None = None


class ContentClassificationDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "OVERRIDDEN"]
    primary_topic_id: UUID | None = None
    secondary_topic_ids: list[UUID] = Field(default_factory=list, max_length=5)
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_override(self) -> "ContentClassificationDecisionRequest":
        if self.decision == "OVERRIDDEN":
            if self.primary_topic_id is None:
                raise ValueError("primary_topic_id is required when overriding a classification")
            if not (self.reason or "").strip():
                raise ValueError("reason is required when overriding a classification")
        return self


class ContentClassificationJobSummary(BaseModel):
    id: UUID
    status: str
    progress_percent: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ContentClassificationQueueItem(BaseModel):
    platform_publication_id: UUID
    platform_account_id: UUID
    page_display_name: str
    external_reel_id: str | None = None
    external_permalink: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    classification: ContentClassificationResponse | None = None
    latest_job: ContentClassificationJobSummary | None = None


class ContentClassificationQueueKpis(BaseModel):
    total_publications: int
    unclassified_count: int
    needs_review_count: int
    approved_count: int
    overridden_count: int
    low_confidence_count: int


class ContentClassificationQueueResponse(BaseModel):
    items: list[ContentClassificationQueueItem]
    total: int
    limit: int
    offset: int
    kpis: ContentClassificationQueueKpis


class ContentAiPromptProfile(BaseModel):
    id: str
    name: str
    version: str
    prompt: str
    is_active: bool = False


class ContentAiConfigResponse(BaseModel):
    enabled: bool = False
    provider: str = "auto"
    model: str = ""
    api_key_set: bool = False
    api_key_masked: str = ""
    base_url: str = ""
    timeout_seconds: float = 90.0
    fallback_mode: str = "local_keyword"
    mode: Literal["HYBRID", "AI_ONLY", "LOCAL_ONLY"] = "HYBRID"
    local_confidence_threshold: float = 0.75
    temperature: float = 0.1
    max_output_tokens: int = 900
    source: str = "default"
    active_prompt_id: str
    active_prompt_name: str
    active_prompt_version: str
    prompts: list[ContentAiPromptProfile] = Field(default_factory=list)


class ContentAiConfigUpdateRequest(BaseModel):
    enabled: bool = False
    provider: Literal["auto", "gemini", "openai_compatible", "ollama", "placeholder"] = "auto"
    model: str = Field(default="", max_length=240)
    api_key: str | None = Field(default=None, max_length=2000)
    clear_api_key: bool = False
    base_url: str = Field(default="", max_length=1000)
    timeout_seconds: float = Field(default=90.0, ge=5, le=300)
    fallback_mode: Literal["none", "local_keyword"] = "local_keyword"
    mode: Literal["HYBRID", "AI_ONLY", "LOCAL_ONLY"] = "HYBRID"
    local_confidence_threshold: float = Field(default=0.75, ge=0.5, le=0.99)
    temperature: float = Field(default=0.1, ge=0, le=1)
    max_output_tokens: int = Field(default=900, ge=200, le=4000)


class ContentAiPromptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ContentAiPromptUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    prompt: str | None = Field(default=None, min_length=80, max_length=30000)


class ContentAiTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    detail: str


class ContentAiTestRequest(BaseModel):
    external_network_authorized: bool = False
    operator_confirmation: str | None = None

    @model_validator(mode="after")
    def validate_ai_authorization(self) -> "ContentAiTestRequest":
        if not self.external_network_authorized or self.operator_confirmation != "CONTENT_CLASSIFICATION_AI_APPROVED":
            raise ValueError("AI provider test requires explicit operator confirmation")
        return self


class ContentAiModelsRequest(BaseModel):
    """Draft connection fields used to list models without requiring Save first."""

    provider: Literal["auto", "gemini", "openai_compatible", "ollama", "placeholder"] | None = None
    api_key: str | None = Field(default=None, max_length=2000)
    clear_api_key: bool = False
    base_url: str | None = Field(default=None, max_length=1000)
    timeout_seconds: float | None = Field(default=None, ge=5, le=300)


class ContentAiModelsResponse(BaseModel):
    ok: bool
    provider: str = ""
    models: list[str] = Field(default_factory=list)
    detail: str = ""
