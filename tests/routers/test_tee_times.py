from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.tee_times import _price_and_transportation

client = TestClient(app, raise_server_exceptions=False)

_SEARCH_RESPONSE = [
    {
        "courseId": "5e3d7968ce07ad0100ad93d0",
        "totalAvailableTeetimes": 2,
        "teetimes": [
            {
                "courseId": "5e3d7968ce07ad0100ad93d0",
                "teetime": "2026-08-27T19:20:00.000Z",
                "maxPlayers": 4,
                "rates": [
                    {
                        "_id": 235361805,
                        "holes": 9,
                        "golfnow": {"GolfFacilityId": 7743, "GolfCourseId": 141164},
                        "greenFeeWalking": 3800,
                    },
                    {
                        "_id": 235364302,
                        "holes": 9,
                        "golfnow": {"GolfFacilityId": 7743, "GolfCourseId": 149742},
                        "greenFeeCart": 5400,
                    },
                ],
            },
            {
                "courseId": "unknown-course-id",
                "teetime": "2026-08-27T20:10:00.000Z",
                "maxPlayers": 1,
                "rates": [
                    {
                        "_id": 999999,
                        "holes": 18,
                        "golfnow": {"GolfFacilityId": 9999, "GolfCourseId": 111111},
                        "greenFeeWalking": 4600,
                    }
                ],
            },
        ],
    }
]


def _fake_client():
    fake = MagicMock()
    fake.login = AsyncMock()
    fake.search_tee_times = AsyncMock(return_value=_SEARCH_RESPONSE)
    fake.aclose = AsyncMock()
    return fake


def test_list_tee_times_flattens_rates_and_resolves_known_names():
    with patch("app.routers.tee_times.TeeItUpClient", return_value=_fake_client()):
        response = client.get("/tee-times", params={"date": "2026-08-27"})

    assert response.status_code == 200
    slots = response.json()
    assert len(slots) == 3

    walking = slots[0]
    assert walking["course_id"] == "5e3d7968ce07ad0100ad93d0"
    assert walking["facility_id"] == 7743
    assert walking["rate_id"] == 235361805
    assert walking["gnc_facility_id"] == 141164
    assert walking["transportation"] == "Walking"
    assert walking["price"] == 38.0
    # UTC teetime converts to America/New_York local date/time
    assert walking["local_date"] == "2026-08-27"
    assert walking["local_time"] == "15:20"
    assert walking["course_name"] == "Twin Lakes Golf Course - Lakes Course"

    cart = slots[1]
    assert cart["transportation"] == "Cart"
    assert cart["price"] == 54.0


def test_list_tee_times_falls_back_to_generic_name_for_unknown_facility():
    with patch("app.routers.tee_times.TeeItUpClient", return_value=_fake_client()):
        response = client.get("/tee-times", params={"date": "2026-08-27"})

    unknown_slot = response.json()[2]
    assert unknown_slot["facility_id"] == 9999
    assert unknown_slot["course_name"] == "Facility 9999"


def test_list_tee_times_closes_client_even_on_error():
    fake = _fake_client()
    fake.search_tee_times = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("app.routers.tee_times.TeeItUpClient", return_value=fake):
        response = client.get("/tee-times", params={"date": "2026-08-27"})

    assert response.status_code == 500
    fake.aclose.assert_awaited_once()


def test_price_and_transportation_rejects_unrecognized_rate_shape():
    with pytest.raises(ValueError, match="Unrecognized rate pricing shape"):
        _price_and_transportation({"holes": 9})
