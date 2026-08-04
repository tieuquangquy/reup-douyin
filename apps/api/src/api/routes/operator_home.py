from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.auth import get_current_workspace
from src.db.session import get_db_session
from src.schemas.operator_home import OperatorHomeSummaryResponse
from src.services.douyin_extension_setup_service import DouyinExtensionSetupService
from src.services.operator_home_summary_service import OperatorHomeSummaryService


router = APIRouter(tags=["operator-home"])


def get_operator_home_summary_service(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> OperatorHomeSummaryService:
    return OperatorHomeSummaryService(db, workspace_id=workspace_id)


@router.get("/operator/home-summary", response_model=OperatorHomeSummaryResponse)
def get_operator_home_summary(
    service: OperatorHomeSummaryService = Depends(get_operator_home_summary_service),
) -> OperatorHomeSummaryResponse:
    extension = DouyinExtensionSetupService().status()
    return service.snapshot(extension=extension)
