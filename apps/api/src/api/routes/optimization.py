from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.optimization.services.optimization_dashboard_service import OptimizationDashboardService
from src.optimization.services.optimization_signal_service import OptimizationSignalService
from src.optimization.services.outcome_score_service import OutcomeScoreError, OutcomeScoreService
from src.optimization.services.routing_hint_service import RoutingHintError, RoutingHintService
from src.schemas.optimization import (
    ManualTouchSummaryResponse,
    OptimizationDashboardResponse,
    OutcomeScoreResponse,
    OutcomeSummariesResponse,
    PresetFeedbackResponse,
    RoutingHintsResponse,
    SchedulingHintsResponse,
)

router = APIRouter(tags=["optimization"])


def get_db(db: Session = Depends(get_db_session)) -> Session:
    return db


@router.get("/optimization/dashboard-snapshot", response_model=OptimizationDashboardResponse)
def get_optimization_dashboard(db: Session = Depends(get_db)) -> OptimizationDashboardResponse:
    return OptimizationDashboardService(db).snapshot()


@router.get("/optimization/outcome-summaries", response_model=OutcomeSummariesResponse)
def get_outcome_summaries(db: Session = Depends(get_db)) -> OutcomeSummariesResponse:
    return OutcomeScoreService(db).outcome_summaries()


@router.get("/optimization/outcome-score/{target_id}", response_model=OutcomeScoreResponse)
def get_outcome_score(
    target_id: UUID,
    target_type: str = Query(default="PUBLISH_DRAFT", pattern="^(PUBLISH_DRAFT)$"),
    db: Session = Depends(get_db),
) -> OutcomeScoreResponse:
    try:
        return OutcomeScoreService(db).score_for_draft(target_id)
    except OutcomeScoreError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/optimization/routing-hints", response_model=RoutingHintsResponse)
def get_routing_hints(
    publish_draft_id: UUID,
    db: Session = Depends(get_db),
) -> RoutingHintsResponse:
    try:
        return RoutingHintService(db).routing_hints(publish_draft_id)
    except (RoutingHintError, OutcomeScoreError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/optimization/scheduling-hints", response_model=SchedulingHintsResponse)
def get_scheduling_hints(
    publish_draft_id: UUID,
    db: Session = Depends(get_db),
) -> SchedulingHintsResponse:
    try:
        return RoutingHintService(db).scheduling_hints(publish_draft_id)
    except (RoutingHintError, OutcomeScoreError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/optimization/manual-touch-summary", response_model=ManualTouchSummaryResponse)
def get_manual_touch_summary(db: Session = Depends(get_db)) -> ManualTouchSummaryResponse:
    return OptimizationSignalService(db).manual_touch_summary()


@router.get("/optimization/preset-feedback", response_model=PresetFeedbackResponse)
def get_preset_feedback(db: Session = Depends(get_db)) -> PresetFeedbackResponse:
    return OptimizationSignalService(db).preset_feedback()

