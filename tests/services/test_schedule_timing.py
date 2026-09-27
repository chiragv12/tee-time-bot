from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.config import settings
from app.services import schedule_timing
from app.services.schedule_timing import (
    compute_deadline,
    compute_open_at,
    compute_wake_at,
    site_today,
    sleep_until,
    utc_now,
)

_T0 = datetime(2026, 8, 19, 22, 0, tzinfo=UTC)


def test_utc_now_is_timezone_aware_utc():
    assert utc_now().tzinfo is UTC


def test_site_today_uses_eastern_date_not_utc_date():
    # 02:00 UTC on the 28th is still 10pm on the 27th in Eastern time
    with patch.object(schedule_timing, "utc_now", return_value=datetime(2026, 8, 28, 2, 0, tzinfo=UTC)):
        assert site_today() == date(2026, 8, 27)


def test_compute_open_at_is_9pm_eastern_eight_days_before_in_summer():
    # 9pm EDT (UTC-4) on Aug 19
    assert compute_open_at(date(2026, 8, 27)) == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def test_compute_open_at_follows_daylight_saving_in_winter():
    # 9pm EST (UTC-5) on Jan 2
    assert compute_open_at(date(2027, 1, 10)) == datetime(2027, 1, 3, 2, 0, tzinfo=UTC)


def test_compute_wake_at_is_lead_seconds_before_open():
    open_at = _T0 + timedelta(days=2)

    assert compute_wake_at(open_at, _T0) == open_at - timedelta(seconds=settings.wake_lead_seconds)


def test_compute_wake_at_is_now_when_wake_time_already_passed():
    assert compute_wake_at(_T0, _T0 + timedelta(hours=1)) == _T0 + timedelta(hours=1)


def test_compute_deadline_counts_from_open_when_registered_before_it():
    assert compute_deadline(_T0, _T0 - timedelta(days=3)) == _T0 + timedelta(minutes=settings.search_window_minutes)


def test_compute_deadline_counts_from_registration_when_window_already_open():
    created = _T0 + timedelta(days=1)

    assert compute_deadline(_T0, created) == created + timedelta(minutes=settings.search_window_minutes)


async def test_sleep_until_returns_immediately_for_a_past_time():
    await sleep_until(utc_now() - timedelta(seconds=5))


async def test_sleep_until_waits_for_a_future_time():
    target = utc_now() + timedelta(milliseconds=50)

    await sleep_until(target)

    assert utc_now() >= target
