from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.auth import get_current_workspace
from src.db.session import get_db_session
from src.schemas.pipeline_dashboard import PipelineDashboardResponse
from src.services.pipeline_dashboard_service import PipelineDashboardService

router = APIRouter(prefix="/ops", tags=["operations"])


def get_pipeline_dashboard_service(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> PipelineDashboardService:
    return PipelineDashboardService(db, workspace_id=workspace_id)


@router.get("/pipeline-dashboard", response_model=PipelineDashboardResponse)
def get_pipeline_dashboard(
    service: PipelineDashboardService = Depends(get_pipeline_dashboard_service),
) -> PipelineDashboardResponse:
    return service.snapshot()
