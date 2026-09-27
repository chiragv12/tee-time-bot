from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookingStatus, ScheduleRequest
from app.orm import BookingRecord


async def create_booking(session: AsyncSession, request: ScheduleRequest, open_at: datetime) -> BookingRecord:
    record = BookingRecord(**request.model_dump(), open_at=open_at)
    session.add(record)
    await session.commit()
    return record


async def get_booking(session: AsyncSession, booking_id: str) -> BookingRecord | None:
    return await session.get(BookingRecord, booking_id)


async def list_bookings(session: AsyncSession) -> list[BookingRecord]:
    result = await session.scalars(select(BookingRecord).order_by(BookingRecord.created_at.desc()))
    return list(result)


async def list_by_status(session: AsyncSession, status: BookingStatus) -> list[BookingRecord]:
    result = await session.scalars(select(BookingRecord).where(BookingRecord.status == status))
    return list(result)


async def update_status(
    session: AsyncSession,
    record: BookingRecord,
    status: BookingStatus,
    detail: str | None = None,
    order_id: str | None = None,
) -> BookingRecord:
    record.status = status
    record.detail = detail
    record.order_id = order_id
    await session.commit()
    return record
