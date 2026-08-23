from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import BookNowResult

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
