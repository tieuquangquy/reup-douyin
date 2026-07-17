from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.session import get_db_session
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.models.media import MediaAsset
from src.schemas.downloads import (
    DownloadCreateRequest,
    DownloadCreateResponse,
    MediaAssetResponse,
    SourceVideoAssetsResponse,
)
from src.services.download_service import DownloadRequest, DownloadService
from src.storage.local import LocalStorageBackend

router = APIRouter(tags=["downloads"])


def get_download_service(db: Session = Depends(get_db_session)) -> DownloadService:
    return DownloadService(db)


@router.post("/downloads", response_model=DownloadCreateResponse, status_code=status.HTTP_201_CREATED)
def create_download(
    request: DownloadCreateRequest,
    service: DownloadService = Depends(get_download_service),
) -> DownloadCreateResponse:
    try:
        result = service.create_download_job(
            DownloadRequest(
                source_video_id=request.source_video_id,
                candidate_id=request.candidate_id,
                force_refresh=request.force_refresh,
            )
        )
    except DownloadError as exc:
        raise _download_http_error(exc) from exc
    return DownloadCreateResponse(
        job_id=UUID(result.job_id),
        status=result.status,
        source_video_id=UUID(result.source_video_id),
        asset_count=result.asset_count,
        manifest=result.manifest,
    )


@router.get("/source-videos/{source_video_id}/assets", response_model=SourceVideoAssetsResponse)
def list_source_video_assets(
    source_video_id: UUID,
    service: DownloadService = Depends(get_download_service),
) -> SourceVideoAssetsResponse:
    try:
        assets = service.get_assets(source_video_id)
        manifest = service.get_manifest(source_video_id)
    except DownloadError as exc:
        raise _download_http_error(exc) from exc
    return SourceVideoAssetsResponse(
        source_video_id=source_video_id,
        assets=[MediaAssetResponse.model_validate(asset) for asset in assets],
        manifest=manifest,
    )


@router.get("/source-videos/{source_video_id}/asset-manifest")
def get_source_video_asset_manifest(
    source_video_id: UUID,
    service: DownloadService = Depends(get_download_service),
) -> dict:
    try:
        return service.get_manifest(source_video_id)
    except DownloadError as exc:
        raise _download_http_error(exc) from exc


@router.get("/media-assets/{asset_id}/content")
def get_media_asset_content(asset_id: UUID, db: Session = Depends(get_db_session)) -> FileResponse:
    asset = db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id))
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    if asset.storage_provider != "local":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only local media assets are streamable in phase 1")
    storage = LocalStorageBackend(get_settings().local_storage_root)
    path = storage.resolve(asset.storage_key).absolute_path
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset file not found")
    return FileResponse(path, media_type=asset.mime_type or "application/octet-stream", filename=path.name)


@router.post("/source-videos/{source_video_id}/assets/refresh", response_model=DownloadCreateResponse)
def refresh_source_video_assets(
    source_video_id: UUID,
    service: DownloadService = Depends(get_download_service),
) -> DownloadCreateResponse:
    try:
        result = service.create_download_job(DownloadRequest(source_video_id=source_video_id, force_refresh=True))
    except DownloadError as exc:
        raise _download_http_error(exc) from exc
    return DownloadCreateResponse(
        job_id=UUID(result.job_id),
        status=result.status,
        source_video_id=UUID(result.source_video_id),
        asset_count=result.asset_count,
        manifest=result.manifest,
    )


def _download_http_error(exc: DownloadError) -> HTTPException:
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        DownloadErrorCode.DOWNLOAD_FAILED,
        DownloadErrorCode.WRITE_FAILED,
        DownloadErrorCode.STORAGE_RESOLUTION_FAILED,
    }:
        http_status = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
