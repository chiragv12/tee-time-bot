from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.orm import Base

engine = create_async_engine(settings.database_url)
# expire_on_commit=False so records stay readable after their session closes.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    # ponytail: create_all on startup, add Alembic migrations before the schema changes in prod
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
