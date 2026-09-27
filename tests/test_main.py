from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_initialises_the_db_and_runs_the_scheduler():
    with patch("app.main.init_db", AsyncMock()) as init_db, patch("app.main.rehydrate_jobs", AsyncMock()) as rehydrate, patch(
        "app.main.scheduler"
    ) as scheduler:
        with TestClient(app):
            init_db.assert_awaited_once()
            scheduler.start.assert_called_once()
            rehydrate.assert_awaited_once()
            scheduler.shutdown.assert_not_called()

    scheduler.shutdown.assert_called_once_with(wait=False)
