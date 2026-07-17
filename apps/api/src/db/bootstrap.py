from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.foundation import Workspace


DEFAULT_WORKSPACE_SLUG = "local"
DEFAULT_WORKSPACE_NAME = "Local Workspace"


def ensure_default_workspace(db: Session) -> Workspace:
    """Create the Phase 1 local workspace if it does not already exist."""

    workspace = db.scalar(
        select(Workspace).where(Workspace.slug == DEFAULT_WORKSPACE_SLUG)
    )
    if workspace is not None:
        return workspace

    workspace = Workspace(
        name=DEFAULT_WORKSPACE_NAME,
        slug=DEFAULT_WORKSPACE_SLUG,
        description="Default workspace for local Phase 1 operation.",
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace

