from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import RiskFlagStatus, RiskTargetType
from src.risk.services.risk_service import RiskService, RiskServiceError
from src.schemas.risk import (
    OperatorRiskDecisionResponse,
    RiskDecisionRequest,
    RiskFlagActionRequest,
    RiskFlagListResponse,
    RiskFlagResponse,
    RiskScanRequest,
    RiskScanResponse,
    RiskSummaryResponse,
)

router = APIRouter(tags=["risk"])


def get_risk_service(db: Session = Depends(get_db_session)) -> RiskService:
    return RiskService(db)


@router.post("/risk-scans", response_model=RiskScanResponse)
def run_risk_scan(request: RiskScanRequest, service: RiskService = Depends(get_risk_service)) -> RiskScanResponse:
    try:
        scan_run_id, flags, gate = service.run_scan(request.target_type, request.target_id)
        latest_decision = service.latest_decision(request.target_type, request.target_id)
        return RiskScanResponse(
            scan_run_id=scan_run_id,
            target_type=request.target_type,
            target_id=request.target_id,
            flags=[RiskFlagResponse.model_validate(flag) for flag in flags],
            gate=gate.__dict__,
            latest_decision=OperatorRiskDecisionResponse.model_validate(latest_decision) if latest_decision else None,
        )
    except RiskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/risk-flags", response_model=RiskFlagListResponse)
def list_risk_flags(
    target_type: RiskTargetType | None = Query(default=None),
    target_id: UUID | None = None,
    status_filter: RiskFlagStatus | None = Query(default=None, alias="status"),
    service: RiskService = Depends(get_risk_service),
) -> RiskFlagListResponse:
    flags = service.list_flags(target_type=target_type, target_id=target_id, status=status_filter)
    return RiskFlagListResponse(flags=[RiskFlagResponse.model_validate(flag) for flag in flags])


@router.get("/risk-flags/{risk_flag_id}", response_model=RiskFlagResponse)
def get_risk_flag(risk_flag_id: UUID, service: RiskService = Depends(get_risk_service)) -> RiskFlagResponse:
    try:
        return RiskFlagResponse.model_validate(service.get_flag(risk_flag_id))
    except RiskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/risk-flags/{risk_flag_id}/acknowledge", response_model=RiskFlagResponse)
def acknowledge_risk_flag(risk_flag_id: UUID, request: RiskFlagActionRequest, service: RiskService = Depends(get_risk_service)) -> RiskFlagResponse:
    return RiskFlagResponse.model_validate(service.update_flag_status(risk_flag_id, RiskFlagStatus.ACKNOWLEDGED, request.note))


@router.post("/risk-flags/{risk_flag_id}/resolve", response_model=RiskFlagResponse)
def resolve_risk_flag(risk_flag_id: UUID, request: RiskFlagActionRequest, service: RiskService = Depends(get_risk_service)) -> RiskFlagResponse:
    return RiskFlagResponse.model_validate(service.update_flag_status(risk_flag_id, RiskFlagStatus.RESOLVED, request.note))


@router.post("/risk-flags/{risk_flag_id}/waive", response_model=RiskFlagResponse)
def waive_risk_flag(risk_flag_id: UUID, request: RiskFlagActionRequest, service: RiskService = Depends(get_risk_service)) -> RiskFlagResponse:
    return RiskFlagResponse.model_validate(service.update_flag_status(risk_flag_id, RiskFlagStatus.WAIVED, request.note))


@router.post("/risk-decisions", response_model=RiskSummaryResponse)
def create_risk_decision(request: RiskDecisionRequest, service: RiskService = Depends(get_risk_service)) -> RiskSummaryResponse:
    try:
        decision = service.create_decision(
            target_type=request.target_type,
            target_id=request.target_id,
            decision_type=request.decision_type,
            note=request.note,
            decided_by=request.decided_by,
        )
        flags = service.list_flags(target_type=request.target_type, target_id=request.target_id)
        gate = service.gate_summary(request.target_type, request.target_id)
        return RiskSummaryResponse(
            target_type=request.target_type,
            target_id=request.target_id,
            flags=[RiskFlagResponse.model_validate(flag) for flag in flags],
            gate=gate.__dict__,
            latest_decision=OperatorRiskDecisionResponse.model_validate(decision),
        )
    except RiskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/targets/{target_type}/{target_id}/risk-summary", response_model=RiskSummaryResponse)
def get_target_risk_summary(target_type: RiskTargetType, target_id: UUID, service: RiskService = Depends(get_risk_service)) -> RiskSummaryResponse:
    try:
        flags = service.list_flags(target_type=target_type, target_id=target_id)
        gate = service.gate_summary(target_type, target_id)
        latest_decision = service.latest_decision(target_type, target_id)
        return RiskSummaryResponse(
            target_type=target_type,
            target_id=target_id,
            flags=[RiskFlagResponse.model_validate(flag) for flag in flags],
            gate=gate.__dict__,
            latest_decision=OperatorRiskDecisionResponse.model_validate(latest_decision) if latest_decision else None,
        )
    except RiskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
