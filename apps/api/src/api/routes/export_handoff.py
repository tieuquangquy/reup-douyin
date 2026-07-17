from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.schemas.export_handoff import (
    BatchItemResultResponse,
    BatchOperationResponse,
    ExportPackageCreateRequest,
    ExportPackageListResponse,
    ExportPackageResponse,
    PublishHandoffCreateRequest,
    PublishHandoffListResponse,
    PublishHandoffResponse,
)
from src.models.export_handoff import ExportPackage, PublishHandoff
from src.services.export_handoff_service import BatchOperationResult, ExportHandoffError, ExportHandoffService

router = APIRouter(tags=["export-handoff"])


def get_export_handoff_service(db: Session = Depends(get_db_session)) -> ExportHandoffService:
    return ExportHandoffService(db)


def _batch_response(result: BatchOperationResult) -> BatchOperationResponse:
    return BatchOperationResponse(
        requested_count=result.requested_count,
        succeeded_count=result.succeeded_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        export_package_id=result.export_package_id,
        publish_handoff_id=result.publish_handoff_id,
        results=[BatchItemResultResponse(**item.__dict__) for item in result.results],
    )


def _export_package_response(package: ExportPackage) -> ExportPackageResponse:
    return ExportPackageResponse.model_validate(
        {
            "id": package.id,
            "workspace_id": package.workspace_id,
            "status": package.status,
            "label": package.label,
            "operator_note": package.operator_note,
            "item_count": package.item_count,
            "manifest_json": package.manifest_json,
            "diagnostics_json": package.diagnostics_json,
            "ready_at": package.ready_at,
            "failed_at": package.failed_at,
            "cancelled_at": package.cancelled_at,
            "items": package.items,
            "publish_handoff_ids": [handoff.id for handoff in package.publish_handoffs],
            "created_at": package.created_at,
            "updated_at": package.updated_at,
        }
    )


def _publish_handoff_response(handoff: PublishHandoff) -> PublishHandoffResponse:
    return PublishHandoffResponse.model_validate(handoff)


@router.post("/export-packages", response_model=ExportPackageResponse, status_code=status.HTTP_201_CREATED)
def create_export_package(
    request: ExportPackageCreateRequest,
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> ExportPackageResponse:
    try:
        package, _result = service.create_export_package(
            item_ids=request.item_ids,
            label=request.label,
            operator_note=request.operator_note,
        )
    except ExportHandoffError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": exc.code, "message": exc.message}) from exc
    return _export_package_response(package)


@router.get("/export-packages", response_model=ExportPackageListResponse)
def list_export_packages(
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> ExportPackageListResponse:
    packages, total = service.list_export_packages(limit=limit, offset=offset)
    return ExportPackageListResponse(items=[_export_package_response(package) for package in packages], total_count=total, limit=limit, offset=offset)


@router.get("/export-packages/{package_id}", response_model=ExportPackageResponse)
def get_export_package(
    package_id: UUID,
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> ExportPackageResponse:
    try:
        package = service.get_export_package(package_id)
    except ExportHandoffError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message}) from exc
    return _export_package_response(package)


@router.post("/publish-handoffs", response_model=PublishHandoffResponse, status_code=status.HTTP_201_CREATED)
def create_publish_handoff(
    request: PublishHandoffCreateRequest,
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> PublishHandoffResponse:
    try:
        handoff = service.create_publish_handoff(
            export_package_id=request.export_package_id,
            target_platform=request.target_platform,
            operator_note=request.operator_note,
        )
    except ExportHandoffError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": exc.code, "message": exc.message}) from exc
    return _publish_handoff_response(handoff)


@router.get("/publish-handoffs", response_model=PublishHandoffListResponse)
def list_publish_handoffs(
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> PublishHandoffListResponse:
    handoffs, total = service.list_publish_handoffs(limit=limit, offset=offset)
    return PublishHandoffListResponse(items=[_publish_handoff_response(handoff) for handoff in handoffs], total_count=total, limit=limit, offset=offset)


@router.get("/publish-handoffs/{handoff_id}", response_model=PublishHandoffResponse)
def get_publish_handoff(
    handoff_id: UUID,
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> PublishHandoffResponse:
    try:
        handoff = service.get_publish_handoff(handoff_id)
    except ExportHandoffError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message}) from exc
    return _publish_handoff_response(handoff)
