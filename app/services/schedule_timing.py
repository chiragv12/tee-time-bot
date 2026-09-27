"""Pure time math for when a booking window opens and how long we keep searching for it."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta

from app.config import settings
from app.facilities import SITE_TIMEZONE

# Slots open at 9pm ET every day. The offset is 8 days, not 7, because the bookable day
# rolls over at 9pm: at 9pm Saturday, Sunday-of-next-week opens. Confirmed on the live site:
# Oct 5 tee times show "available to book from Sunday, September 27, 2026 at 9:00 PM".
BOOKING_OPEN_TIME = time(21, 0)
OPEN_DAYS_AHEAD = 8


def utc_now() -> datetime:
    return datetime.now(UTC)


def site_today() -> date:
    return utc_now().astimezone(SITE_TIMEZONE).date()


def compute_open_at(local_date: date) -> datetime:
    open_day = local_date - timedelta(days=OPEN_DAYS_AHEAD)
    return datetime.combine(open_day, BOOKING_OPEN_TIME, tzinfo=SITE_TIMEZONE).astimezone(UTC)


def compute_wake_at(open_at: datetime, now: datetime) -> datetime:
    """Wake shortly before the window opens, or right now if that moment has passed."""
    return max(open_at - timedelta(seconds=settings.wake_lead_seconds), now)


def compute_deadline(open_at: datetime, created_at: datetime) -> datetime:
    """Stop searching this long after the window opened — or after registering, if it was already open."""
    return max(open_at, created_at) + timedelta(minutes=settings.search_window_minutes)


async def sleep_until(target: datetime) -> None:
    while (remaining := (target - utc_now()).total_seconds()) > 0:
        await asyncio.sleep(remaining)
