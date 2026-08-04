from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.auth import get_current_workspace
from src.db.session import get_db_session
from src.schemas.ops_home import OpsHomeSummaryResponse
from src.services.ops_home_summary_service import OpsHomeSummaryService


router = APIRouter(tags=["ops-home"])


@router.get("/ops/home-summary", response_model=OpsHomeSummaryResponse)
def get_ops_home_summary(
    workspace_id: UUID = Depends(get_current_workspace),
    db: Session = Depends(get_db_session),
) -> OpsHomeSummaryResponse:
    return OpsHomeSummaryService(db, workspace_id=workspace_id).get_summary()

