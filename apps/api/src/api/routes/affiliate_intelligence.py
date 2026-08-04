from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.affiliate_intelligence.services.affiliate_product_service import (
    AffiliateCatalogService,
    AffiliateIntelligenceError,
    AffiliateProductMatchingService,
)
from src.affiliate_intelligence.services.affiliate_product_image_service import (
    AffiliateProductImageError,
    AffiliateProductImageService,
)
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.core.settings import get_settings
from src.db.session import get_db_session
from src.models.content_intelligence import TopicCategory
from src.schemas.affiliate import (
    AffiliateProductBulkImportRequest,
    AffiliateProductBulkImportResponse,
    AffiliateProductCreateRequest,
    AffiliateProductListResponse,
    AffiliateProductImageUploadResponse,
    AffiliateProductMatchDecisionRequest,
    AffiliateProductMatchJobSummary,
    AffiliateProductMatchQueueItem,
    AffiliateProductMatchQueueKpis,
    AffiliateProductMatchQueueResponse,
    AffiliateProductMatchResponse,
    AffiliateProductMatchRunRequest,
    AffiliateProductMatchRunResponse,
    AffiliateProductResponse,
    AffiliateProductUpdateRequest,
)
from src.storage.local import LocalStorageBackend
from src.schemas.jobs import JobResponse


router = APIRouter(tags=["affiliate-intelligence"])
public_router = APIRouter(tags=["affiliate-public-assets"])


def require_affiliate_principal(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Affiliate catalog requires an authenticated operator session",
        )
    return principal


def get_catalog_service(db: Session = Depends(get_db_session)) -> AffiliateCatalogService:
    return AffiliateCatalogService(db)


def get_matching_service(db: Session = Depends(get_db_session)) -> AffiliateProductMatchingService:
    return AffiliateProductMatchingService(db)


def get_product_image_service(db: Session = Depends(get_db_session)) -> AffiliateProductImageService:
    return AffiliateProductImageService(db)


def _error(exc: AffiliateIntelligenceError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code == "affiliate_product_exists":
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail=str(exc))


def _image_error(exc: AffiliateProductImageError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _public_image_path(asset_id: UUID) -> str:
    return f"/api/public/affiliate-product-images/{asset_id}"


def _public_image_url(request: Request, asset_id: UUID, *, configured_origin: str | None = None) -> str:
    path = _public_image_path(asset_id)
    if configured_origin:
        return f"{configured_origin.rstrip('/')}{path}"
    origin = str(request.headers.get("origin") or "").strip().rstrip("/")
    if origin.startswith(("http://", "https://")):
        return f"{origin}{path}"
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").strip()
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").strip() or request.url.scheme
    host = forwarded_host or str(request.headers.get("host") or request.url.netloc)
    return f"{forwarded_proto}://{host}{path}"


def _product_response(service: AffiliateCatalogService, product) -> AffiliateProductResponse:
    topic_ids, topic_codes, topic_names = service.topic_details(product)
    return AffiliateProductResponse(
        id=product.id,
        workspace_id=product.workspace_id,
        catalog_version=product.catalog_version,
        platform=product.platform,
        external_product_id=product.external_product_id,
        merchant_name=product.merchant_name,
        name=product.name,
        description=product.description,
        image_url=product.image_url,
        product_url=product.product_url,
        affiliate_url=product.affiliate_url,
        currency_code=product.currency_code,
        price_amount=product.price_amount,
        commission_rate_percent=product.commission_rate_percent,
        commission_amount=product.commission_amount,
        availability_status=product.availability_status,
        keywords=list(product.keywords_json or []),
        supported_platforms=list(product.supported_platforms_json or []),
        topic_ids=topic_ids,
        topic_codes=topic_codes,
        topic_names=topic_names,
        fingerprint_sha256=product.fingerprint_sha256,
        is_active=product.is_active,
        metadata_json=product.metadata_json,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.post(
    "/affiliate-product-images",
    response_model=AffiliateProductImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_affiliate_product_image(
    request: Request,
    file: UploadFile = File(...),
    service: AffiliateProductImageService = Depends(get_product_image_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductImageUploadResponse:
    try:
        content = await file.read()
        asset = service.upload(
            principal.workspace_id,
            content=content,
            original_filename=file.filename,
            declared_content_type=file.content_type,
            uploaded_by=principal.subject,
        )
    except AffiliateProductImageError as exc:
        raise _image_error(exc) from exc
    finally:
        await file.close()
    return AffiliateProductImageUploadResponse(
        id=asset.id,
        image_url=_public_image_url(
            request,
            asset.id,
            configured_origin=service.configured_public_origin(principal.workspace_id),
        ),
        public_path=_public_image_path(asset.id),
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        checksum_sha256=asset.checksum_sha256,
        created_at=asset.created_at,
    )


@public_router.get("/public/affiliate-product-images/{asset_id}")
def serve_affiliate_product_image(
    asset_id: UUID,
    service: AffiliateProductImageService = Depends(get_product_image_service),
) -> FileResponse:
    asset = service.get_public(asset_id)
    if asset is None or asset.storage_provider != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image asset was not found")
    storage = LocalStorageBackend(get_settings().local_storage_root)
    path = storage.resolve(asset.storage_key).absolute_path
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image asset was not found")
    return FileResponse(
        path,
        media_type=asset.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def _match_response(product_match) -> AffiliateProductMatchResponse:
    return AffiliateProductMatchResponse(
        id=product_match.id,
        workspace_id=product_match.workspace_id,
        platform_publication_id=product_match.platform_publication_id,
        content_classification_id=product_match.content_classification_id,
        matcher_version=product_match.matcher_version,
        catalog_version=product_match.catalog_version,
        catalog_fingerprint_sha256=product_match.catalog_fingerprint_sha256,
        decision_status=product_match.decision_status,
        suggestions=list(product_match.suggestions_json or []),
        selected_product_id=product_match.selected_product_id,
        selected_fit_score=product_match.selected_fit_score,
        created_by_job_id=product_match.created_by_job_id,
        reviewed_by=product_match.reviewed_by,
        reviewed_at=product_match.reviewed_at,
        decision_reason=product_match.decision_reason,
        is_current=product_match.is_current,
        metadata_json=product_match.metadata_json,
        created_at=product_match.created_at,
        updated_at=product_match.updated_at,
    )


@router.get("/affiliate-products", response_model=AffiliateProductListResponse)
def list_affiliate_products(
    q: str | None = Query(default=None, max_length=240),
    platform: str | None = None,
    availability_status: str | None = None,
    active_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AffiliateCatalogService = Depends(get_catalog_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductListResponse:
    products, total, active_count, out_of_stock_count = service.list_products(
        principal.workspace_id,
        query=q,
        platform=platform,
        availability_status=availability_status,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return AffiliateProductListResponse(
        products=[_product_response(service, product) for product in products],
        total=total,
        limit=limit,
        offset=offset,
        active_count=active_count,
        out_of_stock_count=out_of_stock_count,
    )


@router.post("/affiliate-products", response_model=AffiliateProductResponse, status_code=status.HTTP_201_CREATED)
def create_affiliate_product(
    request: AffiliateProductCreateRequest,
    service: AffiliateCatalogService = Depends(get_catalog_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductResponse:
    try:
        return _product_response(service, service.create(principal.workspace_id, request))
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc


@router.patch("/affiliate-products/{product_id}", response_model=AffiliateProductResponse)
def update_affiliate_product(
    product_id: UUID,
    request: AffiliateProductUpdateRequest,
    service: AffiliateCatalogService = Depends(get_catalog_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductResponse:
    try:
        return _product_response(service, service.update(principal.workspace_id, product_id, request))
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc


@router.post("/affiliate-products/bulk-import", response_model=AffiliateProductBulkImportResponse)
def bulk_import_affiliate_products(
    request: AffiliateProductBulkImportRequest,
    service: AffiliateCatalogService = Depends(get_catalog_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductBulkImportResponse:
    try:
        products, created, updated_count, skipped = service.bulk_import(principal.workspace_id, request.products)
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc
    return AffiliateProductBulkImportResponse(
        created_count=created,
        updated_count=updated_count,
        skipped_count=skipped,
        products=[_product_response(service, product) for product in products],
    )


@router.get(
    "/platform-publications/{publication_id}/affiliate-product-match",
    response_model=AffiliateProductMatchResponse | None,
)
def get_publication_affiliate_product_match(
    publication_id: UUID,
    service: AffiliateProductMatchingService = Depends(get_matching_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductMatchResponse | None:
    try:
        product_match = service.get_current(publication_id, principal.workspace_id)
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc
    return _match_response(product_match) if product_match else None


@router.post(
    "/platform-publications/{publication_id}/affiliate-product-match-jobs",
    response_model=AffiliateProductMatchRunResponse,
)
def enqueue_affiliate_product_match(
    publication_id: UUID,
    request: AffiliateProductMatchRunRequest,
    service: AffiliateProductMatchingService = Depends(get_matching_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductMatchRunResponse:
    try:
        product_match, job, reused = service.enqueue(publication_id, principal.workspace_id, request)
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc
    return AffiliateProductMatchRunResponse(
        reused=reused,
        product_match=_match_response(product_match) if product_match else None,
        job=JobResponse.model_validate(job) if job else None,
    )


@router.post("/affiliate-product-matches/{match_id}/decision", response_model=AffiliateProductMatchResponse)
def decide_affiliate_product_match(
    match_id: UUID,
    request: AffiliateProductMatchDecisionRequest,
    service: AffiliateProductMatchingService = Depends(get_matching_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductMatchResponse:
    try:
        product_match = service.decide(match_id, principal.workspace_id, principal.subject, request)
    except AffiliateIntelligenceError as exc:
        raise _error(exc) from exc
    return _match_response(product_match)


@router.get("/affiliate-product-matches/review-queue", response_model=AffiliateProductMatchQueueResponse)
def get_affiliate_product_match_review_queue(
    decision_status: Literal["UNMATCHED", "NEEDS_REVIEW", "APPROVED", "REJECTED", "OVERRIDDEN"] | None = None,
    q: str | None = Query(default=None, max_length=240),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: AffiliateProductMatchingService = Depends(get_matching_service),
    principal: AuthenticatedPrincipal = Depends(require_affiliate_principal),
) -> AffiliateProductMatchQueueResponse:
    rows, total, kpis, latest_jobs = service.review_queue(
        principal.workspace_id,
        decision_status=decision_status,
        query=q,
        limit=limit,
        offset=offset,
    )
    items: list[AffiliateProductMatchQueueItem] = []
    for publication, account, classification, product_match in rows:
        metadata = publication.metadata_json or {}
        topic = service.db.get(TopicCategory, classification.primary_topic_id) if classification.primary_topic_id else None
        job = latest_jobs.get(publication.id)
        items.append(
            AffiliateProductMatchQueueItem(
                platform_publication_id=publication.id,
                platform_account_id=publication.platform_account_id,
                page_display_name=account.display_name,
                external_reel_id=publication.external_reel_id,
                external_permalink=publication.external_permalink,
                caption=metadata.get("external_caption") if isinstance(metadata.get("external_caption"), str) else None,
                thumbnail_url=metadata.get("thumbnail_url") if isinstance(metadata.get("thumbnail_url"), str) else None,
                published_at=publication.published_at,
                classification_id=classification.id,
                classification_status=classification.decision_status,
                primary_topic_code=classification.primary_topic_code,
                primary_topic_name=topic.name if topic else None,
                product_match=_match_response(product_match) if product_match else None,
                latest_job=AffiliateProductMatchJobSummary.model_validate(job, from_attributes=True) if job else None,
            )
        )
    return AffiliateProductMatchQueueResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        kpis=AffiliateProductMatchQueueKpis(**kpis),
    )
