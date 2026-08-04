from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.affiliate_intelligence.services.affiliate_comment_service import AffiliateCommentError, AffiliateCommentService
from src.affiliate_intelligence.services.affiliate_comment_verification_service import (
    AffiliateCommentVerificationError,
    AffiliateCommentVerificationService,
)
from src.affiliate_intelligence.services.affiliate_comment_template_service import AffiliateCommentTemplateError, AffiliateCommentTemplateService
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.db.session import get_db_session
from src.schemas.affiliate_comment import (
    AffiliateCommentApproveResponse,
    AffiliateCommentHistoryResponse,
    AffiliateCommentPlacementResponse,
    AffiliateCommentPreviewRequest,
    AffiliateCommentPreviewResponse,
    AffiliateCommentVerificationJobResponse,
    AffiliateCommentVerificationRequest,
)
from src.schemas.affiliate_comment_template import (
    AffiliateCommentTemplateCreateRequest,
    AffiliateCommentTemplateListResponse,
    AffiliateCommentTemplateResponse,
    AffiliateCommentTemplateUpdateRequest,
)
from src.schemas.jobs import JobResponse


router = APIRouter(tags=["affiliate-comments"])


def require_comment_principal(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Affiliate comments require an authenticated operator session")
    return principal


def get_comment_service(db: Session = Depends(get_db_session)) -> AffiliateCommentService:
    return AffiliateCommentService(db)


def get_comment_template_service(db: Session = Depends(get_db_session)) -> AffiliateCommentTemplateService:
    return AffiliateCommentTemplateService(db)


def get_comment_verification_service(db: Session = Depends(get_db_session)) -> AffiliateCommentVerificationService:
    return AffiliateCommentVerificationService(db)


def _error(exc: AffiliateCommentError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        "affiliate_comment_already_exists",
        "affiliate_comment_preview_changed",
        "affiliate_comment_preview_locked",
        "affiliate_comment_previous_changed",
        "affiliate_comment_cooldown",
        "affiliate_comment_daily_limit",
        "affiliate_comment_duplicate",
    }:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


def _template_error(exc: AffiliateCommentTemplateError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code.endswith("_exists") or exc.code in {"affiliate_comment_template_active", "affiliate_comment_template_in_use"}:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


def _template_response(template) -> AffiliateCommentTemplateResponse:
    return AffiliateCommentTemplateResponse(
        id=template.id,
        workspace_id=template.workspace_id,
        platform=template.platform,
        name=template.name,
        message_template=template.message_template,
        default_cta=template.default_cta,
        default_disclosure=template.default_disclosure,
        attach_product_image=template.attach_product_image,
        version=template.version,
        is_active=template.is_active,
        metadata_json=template.metadata_json,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/affiliate-comment-templates", response_model=AffiliateCommentTemplateListResponse)
def list_affiliate_comment_templates(
    service: AffiliateCommentTemplateService = Depends(get_comment_template_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentTemplateListResponse:
    templates = service.list(principal.workspace_id)
    active = next((template for template in templates if template.is_active), None)
    return AffiliateCommentTemplateListResponse(
        templates=[_template_response(template) for template in templates],
        active_template_id=active.id if active else None,
    )


@router.post("/affiliate-comment-templates", response_model=AffiliateCommentTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_affiliate_comment_template(
    request: AffiliateCommentTemplateCreateRequest,
    service: AffiliateCommentTemplateService = Depends(get_comment_template_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentTemplateResponse:
    try:
        return _template_response(service.create(principal.workspace_id, request, principal.subject))
    except AffiliateCommentTemplateError as exc:
        raise _template_error(exc) from exc


@router.patch("/affiliate-comment-templates/{template_id}", response_model=AffiliateCommentTemplateResponse)
def revise_affiliate_comment_template(
    template_id: UUID,
    request: AffiliateCommentTemplateUpdateRequest,
    service: AffiliateCommentTemplateService = Depends(get_comment_template_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentTemplateResponse:
    try:
        return _template_response(service.revise(principal.workspace_id, template_id, request, principal.subject))
    except AffiliateCommentTemplateError as exc:
        raise _template_error(exc) from exc


@router.post("/affiliate-comment-templates/{template_id}/activate", response_model=AffiliateCommentTemplateResponse)
def activate_affiliate_comment_template(
    template_id: UUID,
    service: AffiliateCommentTemplateService = Depends(get_comment_template_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentTemplateResponse:
    try:
        return _template_response(service.activate(principal.workspace_id, template_id))
    except AffiliateCommentTemplateError as exc:
        raise _template_error(exc) from exc


@router.delete("/affiliate-comment-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_affiliate_comment_template(
    template_id: UUID,
    service: AffiliateCommentTemplateService = Depends(get_comment_template_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> None:
    try:
        service.delete(principal.workspace_id, template_id)
    except AffiliateCommentTemplateError as exc:
        raise _template_error(exc) from exc


def _response(placement) -> AffiliateCommentPlacementResponse:
    return AffiliateCommentPlacementResponse(
        id=placement.id,
        workspace_id=placement.workspace_id,
        platform_publication_id=placement.platform_publication_id,
        platform_account_id=placement.platform_account_id,
        affiliate_product_match_id=placement.affiliate_product_match_id,
        selected_product_id=placement.selected_product_id,
        growth_assessment_id=placement.growth_assessment_id,
        post_job_id=placement.post_job_id,
        status=placement.status,
        idempotency_key=placement.idempotency_key,
        message_sha256=placement.message_sha256,
        comment_message=placement.comment_message,
        cta_text=placement.cta_text,
        disclosure_text=placement.disclosure_text,
        affiliate_url=placement.affiliate_url,
        attachment_image_url=placement.attachment_image_url,
        template_id=placement.template_id,
        template_version=placement.template_version,
        attach_product_image=placement.attach_product_image,
        external_reel_id=placement.external_reel_id,
        external_comment_id=placement.external_comment_id,
        external_comment_permalink=placement.external_comment_permalink,
        created_by=placement.created_by,
        approved_by=placement.approved_by,
        approved_at=placement.approved_at,
        posted_at=placement.posted_at,
        error_code=placement.error_code,
        error_message=placement.error_message,
        response_summary_json=placement.response_summary_json,
        gate_snapshot_json=placement.gate_snapshot_json,
        is_current=placement.is_current,
        metadata_json=placement.metadata_json,
        created_at=placement.created_at,
        updated_at=placement.updated_at,
    )


@router.get(
    "/platform-publications/{publication_id}/affiliate-comment-placement",
    response_model=AffiliateCommentPlacementResponse | None,
)
def get_affiliate_comment_placement(
    publication_id: UUID,
    service: AffiliateCommentService = Depends(get_comment_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentPlacementResponse | None:
    try:
        placement = service.get_current(publication_id, principal.workspace_id)
    except AffiliateCommentError as exc:
        raise _error(exc) from exc
    return _response(placement) if placement else None


@router.get(
    "/platform-publications/{publication_id}/affiliate-comment-placements",
    response_model=AffiliateCommentHistoryResponse,
)
def list_affiliate_comment_placements(
    publication_id: UUID,
    service: AffiliateCommentService = Depends(get_comment_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentHistoryResponse:
    try:
        placements, policy = service.list_history(publication_id, principal.workspace_id)
    except AffiliateCommentError as exc:
        raise _error(exc) from exc
    return AffiliateCommentHistoryResponse(
        placements=[_response(placement) for placement in placements],
        **policy,
    )


@router.post(
    "/platform-publications/{publication_id}/affiliate-comment-placement/preview",
    response_model=AffiliateCommentPreviewResponse,
)
def create_affiliate_comment_preview(
    publication_id: UUID,
    request: AffiliateCommentPreviewRequest,
    service: AffiliateCommentService = Depends(get_comment_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentPreviewResponse:
    try:
        placement, reused = service.preview(publication_id, principal.workspace_id, principal.subject, request)
    except AffiliateCommentError as exc:
        raise _error(exc) from exc
    return AffiliateCommentPreviewResponse(reused=reused, placement=_response(placement))


@router.post(
    "/affiliate-comment-placements/{placement_id}/approve",
    response_model=AffiliateCommentApproveResponse,
)
def approve_affiliate_comment_placement(
    placement_id: UUID,
    service: AffiliateCommentService = Depends(get_comment_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentApproveResponse:
    try:
        placement, job, _ = service.approve_and_enqueue(placement_id, principal.workspace_id, principal.subject)
    except AffiliateCommentError as exc:
        raise _error(exc) from exc
    return AffiliateCommentApproveResponse(
        placement=_response(placement),
        job=JobResponse.model_validate(job) if job else None,
    )


@router.post(
    "/affiliate-comment-placements/{placement_id}/verification-jobs",
    response_model=AffiliateCommentVerificationJobResponse,
)
def verify_affiliate_comment_placement(
    placement_id: UUID,
    request: AffiliateCommentVerificationRequest,
    service: AffiliateCommentVerificationService = Depends(get_comment_verification_service),
    principal: AuthenticatedPrincipal = Depends(require_comment_principal),
) -> AffiliateCommentVerificationJobResponse:
    if not request.authorize_network:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Explicit network authorization is required to check Facebook and the affiliate URL",
        )
    try:
        placement, job, reused = service.enqueue(placement_id, principal.workspace_id)
    except AffiliateCommentVerificationError as exc:
        if exc.code.endswith("_not_found"):
            code = status.HTTP_404_NOT_FOUND
        elif exc.code == "affiliate_comment_verification_setup_incomplete":
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return AffiliateCommentVerificationJobResponse(
        placement=_response(placement),
        job=JobResponse.model_validate(job),
        reused=reused,
    )
