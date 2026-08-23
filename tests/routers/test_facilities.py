from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_facilities_returns_supported_courses():
    response = client.get("/facilities")

    assert response.status_code == 200
    body = response.json()
    assert {"facility_id": 7743, "name": "Twin Lakes Golf Course - Lakes Course"} in body
    assert {"facility_id": 7756, "name": "Twin Lakes Golf Course - Oaks Course"} in body
