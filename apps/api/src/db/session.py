from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import get_settings


def _engine_connect_args(database_url: str) -> dict:
    if database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        return {"connect_timeout": 5}
    return {}


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    resolved_url = database_url or settings.database_url
    return create_engine(resolved_url, pool_pre_ping=True, connect_args=_engine_connect_args(resolved_url))


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_db_session() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
