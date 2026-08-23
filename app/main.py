import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import bookings, facilities, tee_times

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Tee Time Bot")
app.include_router(bookings.router)
app.include_router(tee_times.router)
app.include_router(facilities.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
