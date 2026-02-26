"""Dependency injection for FastAPI routes."""
from typing import Generator

from sqlalchemy.orm import Session

from bot.database import get_db


def get_db_session() -> Generator[Session, None, None]:
    """Yield DB session for route dependency injection.
    
    Usage in routes:
        @router.get("/example")
        async def example(db: Session = Depends(get_db_session)):
            ...
    """
    with get_db() as session:
        yield session
