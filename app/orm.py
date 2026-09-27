from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.models import BookingStatus


class UTCDateTime(TypeDecorator):
    """Always hands back tz-aware UTC — SQLite drops tzinfo, Postgres returns the session tz."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class BookingRecord(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    facility_id: Mapped[int]
    local_date: Mapped[date]
    earliest_time: Mapped[str]
    latest_time: Mapped[str]
    holes: Mapped[int]
    transportation: Mapped[str]
    player_count: Mapped[int]
    open_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(default=BookingStatus.PENDING)
    detail: Mapped[str | None]
    order_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
