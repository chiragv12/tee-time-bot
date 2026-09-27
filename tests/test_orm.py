from datetime import UTC, datetime, timedelta, timezone

from app.orm import UTCDateTime

_EASTERN_EDT = timezone(timedelta(hours=-4))
_type = UTCDateTime()


def test_bind_none_passes_through():
    assert _type.process_bind_param(None, None) is None


def test_bind_converts_aware_values_to_utc():
    value = datetime(2026, 8, 19, 21, 0, tzinfo=_EASTERN_EDT)

    assert _type.process_bind_param(value, None) == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def test_result_none_passes_through():
    assert _type.process_result_value(None, None) is None


def test_result_attaches_utc_to_naive_values_like_sqlite_returns():
    assert _type.process_result_value(datetime(2026, 8, 20, 1, 0), None) == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def test_result_converts_aware_values_like_postgres_returns():
    value = datetime(2026, 8, 19, 21, 0, tzinfo=_EASTERN_EDT)

    assert _type.process_result_value(value, None) == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)
