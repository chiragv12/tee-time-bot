from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import BookingStatus, BookNowResult
from app.orm import BookingRecord

client = TestClient(app)

_PAYLOAD = {
    "course_id": "5e3d7968ce07ad0100ad93d0",
    "facility_id": 7743,
    "rate_id": 235361805,
    "gnc_facility_id": 141164,
    "teetime_iso": "2026-08-27T19:20:00.000Z",
    "local_date": "2026-08-27",
    "local_time": "15:20",
    "holes": 9,
    "transportation": "Walking",
    "price": 38,
}


def test_book_now_returns_200_on_success():
    with patch(
        "app.routers.bookings.book_now",
        AsyncMock(return_value=BookNowResult(success=True, order_id="order1", detail="Booked successfully")),
    ):
        response = client.post("/bookings/book-now", json=_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"success": True, "order_id": "order1", "detail": "Booked successfully"}


def test_book_now_returns_500_on_failure():
    with patch(
        "app.routers.bookings.book_now",
        AsyncMock(return_value=BookNowResult(success=False, order_id=None, detail="something went wrong")),
    ):
        response = client.post("/bookings/book-now", json=_PAYLOAD)

    assert response.status_code == 500
    assert response.json()["success"] is False


def test_book_now_rejects_missing_required_field():
    payload = dict(_PAYLOAD)
    del payload["rate_id"]

    response = client.post("/bookings/book-now", json=payload)

    assert response.status_code == 422


# --- scheduling endpoints ----------------------------------------------------------

_SCHEDULE_PAYLOAD = {
    "facility_id": 7743,
    "local_date": "2026-08-27",
    "earliest_time": "14:00",
    "latest_time": "16:00",
    "holes": 9,
    "transportation": "Walking",
}


def _record(**overrides) -> BookingRecord:
    defaults = dict(
        id="b1",
        facility_id=7743,
        local_date=date(2026, 8, 27),
        earliest_time="14:00",
        latest_time="16:00",
        holes=9,
        transportation="Walking",
        player_count=1,
        open_at=datetime(2026, 8, 20, 1, 0, tzinfo=UTC),
        status=BookingStatus.PENDING,
        detail=None,
        order_id=None,
        created_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
    )
    defaults.update(overrides)
    return BookingRecord(**defaults)


@pytest.fixture
def repo():
    with patch("app.routers.bookings.repository") as mock_repo:
        for name in ("create_booking", "get_booking", "list_bookings", "update_status"):
            setattr(mock_repo, name, AsyncMock())
        yield mock_repo


@pytest.fixture
def session():
    fake = MagicMock()
    app.dependency_overrides[get_session] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def jobs():
    with patch("app.routers.bookings.schedule_job") as schedule, patch(
        "app.routers.bookings.unschedule_job"
    ) as unschedule, patch("app.routers.bookings.site_today", return_value=date(2026, 8, 18)):
        yield MagicMock(schedule=schedule, unschedule=unschedule)


def test_schedule_creates_the_booking_and_registers_the_job(repo, session, jobs):
    record = _record()
    repo.create_booking.return_value = record

    response = client.post("/bookings/schedule", json=_SCHEDULE_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == "b1"
    assert response.json()["status"] == "pending"
    # 9pm EDT on Aug 19, eight days before the 27th
    assert repo.create_booking.call_args.args[2] == datetime(2026, 8, 20, 1, 0, tzinfo=UTC)
    jobs.schedule.assert_called_once_with(record)


def test_schedule_rejects_an_unsupported_facility(repo, session, jobs):
    response = client.post("/bookings/schedule", json={**_SCHEDULE_PAYLOAD, "facility_id": 1})

    assert response.status_code == 422
    repo.create_booking.assert_not_awaited()


def test_schedule_rejects_a_date_in_the_past(repo, session, jobs):
    response = client.post("/bookings/schedule", json={**_SCHEDULE_PAYLOAD, "local_date": "2026-08-01"})

    assert response.status_code == 422
    repo.create_booking.assert_not_awaited()


@pytest.mark.parametrize(
    "bad",
    [
        {"transportation": "Bike"},
        {"earliest_time": "3pm"},
        {"latest_time": "25:00"},
        {"earliest_time": "16:00", "latest_time": "14:00"},  # window backwards
        {"player_count": 5},
        {"local_date": "tomorrow"},
    ],
)
def test_schedule_rejects_malformed_fields(repo, session, jobs, bad):
    assert client.post("/bookings/schedule", json={**_SCHEDULE_PAYLOAD, **bad}).status_code == 422


def test_list_bookings_returns_everything(repo, session):
    repo.list_bookings.return_value = [_record(id="b1"), _record(id="b2")]

    response = client.get("/bookings")

    assert response.status_code == 200
    assert [b["id"] for b in response.json()] == ["b1", "b2"]


def test_get_booking_returns_the_record(repo, session):
    repo.get_booking.return_value = _record(status=BookingStatus.BOOKED, order_id="o1", detail="Booked")

    response = client.get("/bookings/b1")

    assert response.status_code == 200
    assert response.json()["status"] == "booked"
    assert response.json()["order_id"] == "o1"


def test_get_booking_404s_for_an_unknown_id(repo, session):
    repo.get_booking.return_value = None

    assert client.get("/bookings/nope").status_code == 404


def test_cancel_unschedules_the_job_and_marks_cancelled(repo, session, jobs):
    record = _record()
    repo.get_booking.return_value = record
    repo.update_status.return_value = _record(status=BookingStatus.CANCELLED)

    response = client.delete("/bookings/b1")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    jobs.unschedule.assert_called_once_with("b1")
    repo.update_status.assert_awaited_once_with(session, record, BookingStatus.CANCELLED)


def test_cancel_refuses_a_booking_that_already_started(repo, session, jobs):
    repo.get_booking.return_value = _record(status=BookingStatus.SEARCHING)

    response = client.delete("/bookings/b1")

    assert response.status_code == 409
    jobs.unschedule.assert_not_called()


def test_cancel_404s_for_an_unknown_id(repo, session, jobs):
    repo.get_booking.return_value = None

    assert client.delete("/bookings/nope").status_code == 404


# --- Swagger docs -------------------------------------------------------------------


def test_openapi_documents_example_payloads_for_the_post_endpoints():
    paths = client.get("/openapi.json").json()["paths"]

    for path, expected in (("/bookings/schedule", {"nine_holes_walking"}), ("/bookings/book-now", {"nine_holes_walking"})):
        examples = paths[path]["post"]["requestBody"]["content"]["application/json"]["examples"]
        assert expected <= set(examples)


def test_example_payloads_are_valid_requests():
    from app.models import BookNowRequest, ScheduleRequest
    from app.routers.bookings import BOOK_NOW_EXAMPLES, SCHEDULE_EXAMPLES

    for example in SCHEDULE_EXAMPLES.values():
        ScheduleRequest(**example["value"])
    for example in BOOK_NOW_EXAMPLES.values():
        BookNowRequest(**example["value"])
