from typing import Annotated

from fastapi import APIRouter, Query

from app.config import settings
from app.models import TeeTimeSlot
from app.services.tee_time_search import search_slots
from app.services.teeitup_client import TeeItUpClient

router = APIRouter(prefix="/tee-times", tags=["tee-times"])


@router.get("", response_model=list[TeeTimeSlot], summary="List currently open tee times for a date")
async def list_tee_times(
    date: Annotated[str, Query(description="Tee time date, YYYY-MM-DD", examples=["2026-10-03"])],
    facility_ids: Annotated[
        str, Query(description="Comma-separated facility ids (see GET /facilities); defaults to all supported")
    ] = settings.supported_facility_ids,
) -> list[TeeTimeSlot]:
    """One entry per bookable option, so the same tee time appears once per holes/walking/cart rate.

    Each entry has everything `POST /bookings/book-now` needs."""
    client = TeeItUpClient()
    try:
        await client.login()
        return await search_slots(client, date, facility_ids)
    finally:
        await client.aclose()
