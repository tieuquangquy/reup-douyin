from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adapters.errors import SourceAdapterErrorCode
from src.db.session import get_db_session
from src.enums import CrawlSessionStatus, SourcePlatformEnum
from src.models.ingestion import CrawlSession, SourceProfile, SourceVideo
from src.schemas.source_ingest import (
    CrawlSessionListResponse,
    CrawlSessionResponse,
    IngestSummaryResponse,
    SourceProfileIngestRequest,
    SourceProfileListResponse,
    SourceProfileResponse,
    SourceVideoListResponse,
    SourceVideoResponse,
)
from src.services.source_ingest_service import SourceIngestError, SourceIngestService

router = APIRouter(tags=["source-ingest"])


def get_source_ingest_service(db: Session = Depends(get_db_session)) -> SourceIngestService:
    return SourceIngestService(db)


@router.post("/source-profiles/ingest", response_model=IngestSummaryResponse)
def ingest_source_profile(
    request: SourceProfileIngestRequest,
    service: SourceIngestService = Depends(get_source_ingest_service),
) -> IngestSummaryResponse:
    try:
        summary = service.ingest_profile(
            workspace_id=request.workspace_id,
            profile_url=request.profile_url,
            source_platform=request.source_platform,
            crawl_mode=request.crawl_mode,
            adapter_payload_json=request.adapter_payload_json,
        )
    except SourceIngestError as exc:
        http_status = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if exc.code
            in {
                SourceAdapterErrorCode.INVALID_URL,
                SourceAdapterErrorCode.UNSUPPORTED_PROFILE,
                SourceAdapterErrorCode.NORMALIZATION_FAILED,
            }
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message}) from exc
    return IngestSummaryResponse(**summary.__dict__)


@router.get("/crawl-sessions", response_model=CrawlSessionListResponse)
def list_crawl_sessions(
    status_filter: CrawlSessionStatus | None = Query(default=None, alias="status"),
    source_platform: SourcePlatformEnum | None = None,
    source_profile_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> CrawlSessionListResponse:
    stmt = select(CrawlSession)
    if status_filter is not None:
        stmt = stmt.where(CrawlSession.status == status_filter)
    if source_platform is not None:
        stmt = stmt.where(CrawlSession.source_platform == source_platform)
    if source_profile_id is not None:
        stmt = stmt.where(CrawlSession.source_profile_id == source_profile_id)
    stmt = stmt.order_by(CrawlSession.created_at.desc()).limit(limit).offset(offset)
    return CrawlSessionListResponse(
        crawl_sessions=[CrawlSessionResponse.model_validate(item) for item in db.scalars(stmt)]
    )


@router.get("/crawl-sessions/{crawl_session_id}", response_model=CrawlSessionResponse)
def get_crawl_session(
    crawl_session_id: UUID,
    db: Session = Depends(get_db_session),
) -> CrawlSessionResponse:
    crawl_session = db.get(CrawlSession, crawl_session_id)
    if crawl_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl session not found")
    return CrawlSessionResponse.model_validate(crawl_session)


@router.get("/source-profiles", response_model=SourceProfileListResponse)
def list_source_profiles(
    source_platform: SourcePlatformEnum | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> SourceProfileListResponse:
    stmt = select(SourceProfile)
    if source_platform is not None:
        stmt = stmt.where(SourceProfile.source_platform == source_platform)
    stmt = stmt.order_by(SourceProfile.updated_at.desc()).limit(limit).offset(offset)
    return SourceProfileListResponse(
        source_profiles=[SourceProfileResponse.model_validate(item) for item in db.scalars(stmt)]
    )


@router.get("/source-profiles/{profile_id}/videos", response_model=SourceVideoListResponse)
def list_source_profile_videos(
    profile_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> SourceVideoListResponse:
    stmt = (
        select(SourceVideo)
        .where(SourceVideo.source_profile_id == profile_id)
        .order_by(SourceVideo.posted_at.desc().nullslast(), SourceVideo.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return SourceVideoListResponse(videos=[SourceVideoResponse.model_validate(item) for item in db.scalars(stmt)])

