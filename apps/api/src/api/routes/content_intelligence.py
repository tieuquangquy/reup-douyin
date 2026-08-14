from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.content_intelligence.services.content_classification_service import (
    DEFAULT_TAXONOMY_VERSION,
    ContentClassificationService,
    ContentIntelligenceError,
)
from src.content_intelligence.services.content_ai_classifier import (
    ContentAiClassifier,
    ContentAiClassifierError,
)
from src.content_intelligence.services.content_ai_settings_service import (
    ContentAiSettingsError,
    ContentAiSettingsService,
    merge_content_ai_list_models_draft,
)
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.db.session import get_db_session
from src.schemas.content_intelligence import (
    ContentClassificationDecisionRequest,
    ContentClassificationJobSummary,
    ContentClassificationQueueItem,
    ContentClassificationQueueKpis,
    ContentClassificationQueueResponse,
    ContentClassificationResponse,
    ContentClassificationRunRequest,
    ContentClassificationRunResponse,
    ContentAiConfigResponse,
    ContentAiConfigUpdateRequest,
    ContentAiModelsRequest,
    ContentAiModelsResponse,
    ContentAiPromptCreateRequest,
    ContentAiPromptProfile,
    ContentAiPromptUpdateRequest,
    ContentAiTestRequest,
    ContentAiTestResponse,
    TopicCategoryCreateRequest,
    TopicCategoryListResponse,
    TopicCategoryResponse,
    TopicCategoryUpdateRequest,
)
from src.schemas.jobs import JobResponse


router = APIRouter(tags=["content-intelligence"])
logger = logging.getLogger(__name__)


def require_content_principal(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Content classification requires an authenticated operator session",
        )
    return principal


def get_content_service(db: Session = Depends(get_db_session)) -> ContentClassificationService:
    return ContentClassificationService(db)


def get_content_ai_settings(db: Session = Depends(get_db_session)) -> ContentAiSettingsService:
    return ContentAiSettingsService(db)


def _error(exc: ContentIntelligenceError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code == "topic_code_exists":
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail=str(exc))


def _classification_response(
    service: ContentClassificationService,
    classification,
) -> ContentClassificationResponse:
    response = ContentClassificationResponse.model_validate(classification)
    return response.model_copy(update={"primary_topic_name": service.topic_name(classification.primary_topic_id)})


def _settings_error(exc: ContentAiSettingsError | ContentAiClassifierError) -> HTTPException:
    code = getattr(exc, "code", str(exc))
    status_code = status.HTTP_409_CONFLICT if code in {"prompt_name_exists"} else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("/content-intelligence/ai-config", response_model=ContentAiConfigResponse)
def get_content_ai_config(
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        return ContentAiConfigResponse.model_validate(service.get_public(principal.workspace_id))
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.put("/content-intelligence/ai-config", response_model=ContentAiConfigResponse)
def update_content_ai_config(
    request: ContentAiConfigUpdateRequest,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        payload = request.model_dump()
        return ContentAiConfigResponse.model_validate(service.save_config(principal.workspace_id, payload))
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.post("/content-intelligence/ai-config/test", response_model=ContentAiTestResponse)
def test_content_ai_config(
    request: ContentAiTestRequest,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiTestResponse:
    del request
    try:
        config, _prompt = service.get_runtime(principal.workspace_id)
        result = ContentAiClassifier().probe(config)
        return ContentAiTestResponse(
            ok=True,
            provider=result.provider,
            model=result.model,
            detail="Provider returned valid structured JSON",
        )
    except (ContentAiSettingsError, ContentAiClassifierError) as exc:
        raise _settings_error(exc) from exc


@router.post("/content-intelligence/ai-config/models", response_model=ContentAiModelsResponse)
def list_content_ai_models(
    request: ContentAiModelsRequest,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiModelsResponse:
    try:
        saved, _prompt = service.get_runtime(principal.workspace_id)
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc
    config = merge_content_ai_list_models_draft(saved, request.model_dump())
    ok, models, detail = ContentAiClassifier().list_models(config)
    provider = ContentAiClassifier._resolve_provider(config)
    logger.info(
        "content_ai_list_models",
        extra={
            "workspace_id": str(principal.workspace_id),
            "provider": provider,
            "ok": ok,
            "model_count": len(models),
        },
    )
    return ContentAiModelsResponse(ok=ok, provider=provider, models=models, detail=detail)


@router.get("/content-intelligence/prompts", response_model=list[ContentAiPromptProfile])
def list_content_ai_prompts(
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> list[ContentAiPromptProfile]:
    try:
        payload = service.get_public(principal.workspace_id)
        return [ContentAiPromptProfile.model_validate(item) for item in payload["prompts"]]
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.post(
    "/content-intelligence/prompts",
    response_model=ContentAiConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_content_ai_prompt(
    request: ContentAiPromptCreateRequest,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        return ContentAiConfigResponse.model_validate(
            service.create_prompt(principal.workspace_id, name=request.name)
        )
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.patch("/content-intelligence/prompts/{prompt_id}", response_model=ContentAiConfigResponse)
def update_content_ai_prompt(
    prompt_id: str,
    request: ContentAiPromptUpdateRequest,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        return ContentAiConfigResponse.model_validate(
            service.update_prompt(principal.workspace_id, prompt_id, request.model_dump(exclude_unset=True))
        )
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.post("/content-intelligence/prompts/{prompt_id}/activate", response_model=ContentAiConfigResponse)
def activate_content_ai_prompt(
    prompt_id: str,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        return ContentAiConfigResponse.model_validate(service.activate_prompt(principal.workspace_id, prompt_id))
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc


@router.delete("/content-intelligence/prompts/{prompt_id}", response_model=ContentAiConfigResponse)
def delete_content_ai_prompt(
    prompt_id: str,
    service: ContentAiSettingsService = Depends(get_content_ai_settings),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentAiConfigResponse:
    try:
        payload = service.delete_prompt(principal.workspace_id, prompt_id)
    except ContentAiSettingsError as exc:
        raise _settings_error(exc) from exc
    logger.info(
        "content_ai_prompt_deleted",
        extra={"workspace_id": str(principal.workspace_id), "prompt_id": prompt_id},
    )
    return ContentAiConfigResponse.model_validate(payload)


@router.get("/content-topics", response_model=TopicCategoryListResponse)
def list_content_topics(
    taxonomy_version: str = Query(default=DEFAULT_TAXONOMY_VERSION, min_length=1, max_length=80),
    include_inactive: bool = False,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> TopicCategoryListResponse:
    topics = service.list_topics(
        principal.workspace_id,
        taxonomy_version=taxonomy_version,
        include_inactive=include_inactive,
    )
    return TopicCategoryListResponse(
        topics=[TopicCategoryResponse.model_validate(topic) for topic in topics],
        taxonomy_version=taxonomy_version,
    )


@router.post("/content-topics", response_model=TopicCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_content_topic(
    request: TopicCategoryCreateRequest,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> TopicCategoryResponse:
    try:
        return TopicCategoryResponse.model_validate(service.create_topic(principal.workspace_id, request))
    except ContentIntelligenceError as exc:
        raise _error(exc) from exc


@router.patch("/content-topics/{topic_id}", response_model=TopicCategoryResponse)
def update_content_topic(
    topic_id: UUID,
    request: TopicCategoryUpdateRequest,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> TopicCategoryResponse:
    try:
        return TopicCategoryResponse.model_validate(service.update_topic(principal.workspace_id, topic_id, request))
    except ContentIntelligenceError as exc:
        raise _error(exc) from exc


@router.get(
    "/platform-publications/{publication_id}/content-classification",
    response_model=ContentClassificationResponse | None,
)
def get_publication_content_classification(
    publication_id: UUID,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentClassificationResponse | None:
    try:
        classification = service.get_current(publication_id, principal.workspace_id)
    except ContentIntelligenceError as exc:
        raise _error(exc) from exc
    return _classification_response(service, classification) if classification else None


@router.post(
    "/platform-publications/{publication_id}/content-classification-jobs",
    response_model=ContentClassificationRunResponse,
)
def enqueue_publication_content_classification(
    publication_id: UUID,
    request: ContentClassificationRunRequest,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentClassificationRunResponse:
    try:
        classification, job, reused = service.enqueue(publication_id, principal.workspace_id, request)
    except ContentIntelligenceError as exc:
        raise _error(exc) from exc
    return ContentClassificationRunResponse(
        reused=reused,
        classification=_classification_response(service, classification) if classification else None,
        job=JobResponse.model_validate(job) if job else None,
    )


@router.get("/content-classifications/review-queue", response_model=ContentClassificationQueueResponse)
def get_content_classification_review_queue(
    platform_account_id: UUID | None = None,
    decision_status: Literal["UNCLASSIFIED", "NEEDS_REVIEW", "APPROVED", "OVERRIDDEN"] | None = None,
    low_confidence_only: bool = False,
    confidence_threshold: float = Query(default=0.6, ge=0, le=1),
    q: str | None = Query(default=None, max_length=240),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentClassificationQueueResponse:
    rows, total, kpis, latest_jobs = service.review_queue(
        principal.workspace_id,
        platform_account_id=platform_account_id,
        decision_status=decision_status,
        low_confidence_only=low_confidence_only,
        confidence_threshold=confidence_threshold,
        query=q,
        limit=limit,
        offset=offset,
    )
    items: list[ContentClassificationQueueItem] = []
    for publication, account, classification in rows:
        metadata = publication.metadata_json or {}
        job = latest_jobs.get(publication.id)
        items.append(
            ContentClassificationQueueItem(
                platform_publication_id=publication.id,
                platform_account_id=publication.platform_account_id,
                page_display_name=account.display_name,
                external_reel_id=publication.external_reel_id,
                external_permalink=publication.external_permalink,
                caption=metadata.get("external_caption") if isinstance(metadata.get("external_caption"), str) else None,
                thumbnail_url=metadata.get("thumbnail_url") if isinstance(metadata.get("thumbnail_url"), str) else None,
                published_at=publication.published_at,
                classification=_classification_response(service, classification) if classification else None,
                latest_job=ContentClassificationJobSummary.model_validate(job, from_attributes=True) if job else None,
            )
        )
    return ContentClassificationQueueResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        kpis=ContentClassificationQueueKpis(**kpis),
    )


@router.post(
    "/content-classifications/{classification_id}/decision",
    response_model=ContentClassificationResponse,
)
def decide_content_classification(
    classification_id: UUID,
    request: ContentClassificationDecisionRequest,
    service: ContentClassificationService = Depends(get_content_service),
    principal: AuthenticatedPrincipal = Depends(require_content_principal),
) -> ContentClassificationResponse:
    try:
        classification = service.decide(
            classification_id,
            principal.workspace_id,
            principal.subject,
            request,
        )
    except ContentIntelligenceError as exc:
        raise _error(exc) from exc
    return _classification_response(service, classification)
