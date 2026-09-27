from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import repository
from app.models import BookingStatus, ScheduleRequest
from app.orm import Base

_OPEN_AT = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def _request(**overrides) -> ScheduleRequest:
    defaults = dict(
        facility_id=7743,
        local_date=date(2026, 8, 27),
        earliest_time="14:00",
        latest_time="16:00",
        holes=9,
        transportation="Walking",
    )
    defaults.update(overrides)
    return ScheduleRequest(**defaults)


# In-memory SQLite: the repository is a thin layer over SQL, so a real (throwaway) DB is the honest test.
@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def test_create_booking_persists_request_fields_with_pending_defaults(session):
    record = await repository.create_booking(session, _request(player_count=2), _OPEN_AT)

    assert record.id
    assert record.facility_id == 7743
    assert record.local_date == date(2026, 8, 27)
    assert record.earliest_time == "14:00"
    assert record.latest_time == "16:00"
    assert record.player_count == 2
    assert record.status == BookingStatus.PENDING
    assert record.detail is None
    assert record.order_id is None
    assert record.created_at.tzinfo is not None


async def test_get_booking_round_trips_open_at_as_aware_utc(session):
    record = await repository.create_booking(session, _request(), _OPEN_AT)
    session.expunge_all()

    loaded = await repository.get_booking(session, record.id)

    assert loaded.open_at == _OPEN_AT
    assert loaded.open_at.tzinfo is not None


async def test_get_booking_returns_none_for_unknown_id(session):
    assert await repository.get_booking(session, "nope") is None


async def test_list_bookings_returns_newest_first(session):
    older = await repository.create_booking(session, _request(earliest_time="08:00", latest_time="09:00"), _OPEN_AT)
    older.created_at = datetime.now(UTC) - timedelta(hours=1)
    newer = await repository.create_booking(session, _request(earliest_time="09:00", latest_time="10:00"), _OPEN_AT)

    assert [b.id for b in await repository.list_bookings(session)] == [newer.id, older.id]


async def test_list_by_status_filters(session):
    pending = await repository.create_booking(session, _request(), _OPEN_AT)
    other = await repository.create_booking(session, _request(), _OPEN_AT)
    await repository.update_status(session, other, BookingStatus.BOOKED)

    assert [b.id for b in await repository.list_by_status(session, BookingStatus.PENDING)] == [pending.id]


async def test_update_status_sets_status_detail_and_order_id(session):
    record = await repository.create_booking(session, _request(), _OPEN_AT)

    await repository.update_status(session, record, BookingStatus.BOOKED, "Booked successfully", "order1")
    session.expunge_all()
    loaded = await repository.get_booking(session, record.id)

    assert loaded.status == BookingStatus.BOOKED
    assert loaded.detail == "Booked successfully"
    assert loaded.order_id == "order1"
