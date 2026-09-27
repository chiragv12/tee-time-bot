from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import TeeTimeSlot

client = TestClient(app, raise_server_exceptions=False)

_SLOT = TeeTimeSlot(
    course_id="5e3d7968ce07ad0100ad93d0",
    facility_id=7743,
    rate_id=235361805,
    gnc_facility_id=141164,
    teetime_iso="2026-08-27T19:20:00.000Z",
    local_date="2026-08-27",
    local_time="15:20",
    holes=9,
    transportation="Walking",
    price=38.0,
    max_players=4,
    course_name="Twin Lakes Golf Course - Lakes Course",
)


def _fake_client():
    fake = MagicMock()
    fake.login = AsyncMock()
    fake.aclose = AsyncMock()
    return fake


def test_list_tee_times_returns_slots_from_search():
    fake = _fake_client()
    search = AsyncMock(return_value=[_SLOT])

    with patch("app.routers.tee_times.TeeItUpClient", return_value=fake), patch(
        "app.routers.tee_times.search_slots", search
    ):
        response = client.get("/tee-times", params={"date": "2026-08-27", "facility_ids": "7743"})

    assert response.status_code == 200
    assert response.json() == [_SLOT.model_dump()]
    search.assert_awaited_once_with(fake, "2026-08-27", "7743")
    fake.login.assert_awaited_once()
    fake.aclose.assert_awaited_once()


def test_list_tee_times_defaults_to_supported_facilities():
    search = AsyncMock(return_value=[])

    with patch("app.routers.tee_times.TeeItUpClient", return_value=_fake_client()), patch(
        "app.routers.tee_times.search_slots", search
    ):
        client.get("/tee-times", params={"date": "2026-08-27"})

    assert search.call_args.args[2] == "7743,7756"


def test_list_tee_times_closes_client_even_on_error():
    fake = _fake_client()

    with patch("app.routers.tee_times.TeeItUpClient", return_value=fake), patch(
        "app.routers.tee_times.search_slots", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        response = client.get("/tee-times", params={"date": "2026-08-27"})

    assert response.status_code == 500
    fake.aclose.assert_awaited_once()
