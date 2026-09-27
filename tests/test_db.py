from unittest.mock import MagicMock, patch

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app import db


async def test_init_db_creates_the_bookings_table():
    engine = create_async_engine("sqlite+aiosqlite://")

    with patch.object(db, "engine", engine):
        await db.init_db()

    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    await engine.dispose()
    assert "bookings" in tables


async def test_get_session_yields_a_session_from_the_factory():
    session = MagicMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session

    with patch.object(db, "SessionLocal", factory):
        gen = db.get_session()
        assert await gen.__anext__() is session
        await gen.aclose()

    factory.return_value.__aexit__.assert_awaited_once()
