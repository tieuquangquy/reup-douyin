from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import JobStatus, JobType
from src.schemas.jobs import JobCreateRequest, JobListResponse, JobResponse
from src.services.job_service import JobNotFound, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db_session)) -> JobService:
    return JobService(db)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobCreateRequest,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    if request.job_type == JobType.DOWNLOAD_VIDEO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DOWNLOAD_VIDEO must be created through POST /downloads so source, account, idempotency, and retry policy are validated",
        )
    job = service.create_job(**request.model_dump())
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    job_type: JobType | None = None,
    source_video_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: JobService = Depends(get_job_service),
) -> JobListResponse:
    jobs, total = service.list_jobs(
        status=status_filter,
        job_type=job_type,
        source_video_id=source_video_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(
        jobs=[JobResponse.model_validate(job) for job in jobs],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        return JobResponse.model_validate(service.get_job(job_id))
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        return JobResponse.model_validate(service.retry_job(job_id))
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        return JobResponse.model_validate(service.cancel_job(job_id))
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{job_id}/resume", response_model=JobResponse)
def resume_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        return JobResponse.model_validate(service.resume_job(job_id))
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> None:
    try:
        service.delete_job(job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
