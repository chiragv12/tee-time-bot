import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import init_db
from app.routers import bookings, facilities, tee_times
from app.services.scheduler import rehydrate_jobs, scheduler

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.start()
    await rehydrate_jobs()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Tee Time Bot", lifespan=lifespan)
app.include_router(bookings.router)
app.include_router(tee_times.router)
app.include_router(facilities.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
