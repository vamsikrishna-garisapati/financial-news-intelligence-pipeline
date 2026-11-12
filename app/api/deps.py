"""FastAPI dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.collection import CollectionService


def get_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_collection_service(db: Session) -> CollectionService:
    return CollectionService(db)
