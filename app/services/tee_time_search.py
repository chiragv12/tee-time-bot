"""Search TeeItUp for open slots and reduce the raw response to bookable TeeTimeSlots.

Shared by GET /tee-times and the scheduler, so both discover slots the same way.
"""

from datetime import datetime

from app.facilities import FACILITY_NAMES, SITE_TIMEZONE
from app.models import BookNowRequest, TeeTimeSlot
from app.services.teeitup_client import TeeItUpClient


def local_date_time(teetime_iso: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(teetime_iso.replace("Z", "+00:00")).astimezone(SITE_TIMEZONE)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def price_and_transportation(rate: dict) -> tuple[float, str]:
    if "greenFeeWalking" in rate:
        return rate["greenFeeWalking"] / 100, "Walking"
    if "greenFeeCart" in rate:
        return rate["greenFeeCart"] / 100, "Cart"
    raise ValueError(f"Unrecognized rate pricing shape: {rate}")


def build_slot(teetime: dict, rate: dict) -> TeeTimeSlot:
    local_date, local_time = local_date_time(teetime["teetime"])
    price, transportation = price_and_transportation(rate)
    facility_id = rate["golfnow"]["GolfFacilityId"]
    return TeeTimeSlot(
        course_id=teetime["courseId"],
        facility_id=facility_id,
        rate_id=rate["_id"],
        gnc_facility_id=rate["golfnow"]["GolfCourseId"],
        teetime_iso=teetime["teetime"],
        local_date=local_date,
        local_time=local_time,
        holes=rate["holes"],
        transportation=transportation,
        price=price,
        max_players=teetime["maxPlayers"],
        course_name=FACILITY_NAMES.get(facility_id, f"Facility {facility_id}"),
    )


def flatten_search_response(days: list[dict]) -> list[TeeTimeSlot]:
    return [
        build_slot(teetime, rate)
        for day in days
        for teetime in day["teetimes"]
        for rate in teetime["rates"]
    ]


async def search_slots(client: TeeItUpClient, date: str, facility_ids: str) -> list[TeeTimeSlot]:
    """Search with an already-logged-in client, so callers polling repeatedly log in once."""
    return flatten_search_response(await client.search_tee_times(date, facility_ids))


def find_earliest_slot(
    slots: list[TeeTimeSlot],
    facility_id: int,
    earliest_time: str,
    latest_time: str,
    holes: int,
    transportation: str,
    player_count: int,
) -> TeeTimeSlot | None:
    """The earliest slot inside the (inclusive) time window that fits the request, or None.

    HH:MM strings compare correctly as text, so no time parsing is needed."""
    candidates = [
        slot
        for slot in slots
        if slot.facility_id == facility_id
        and earliest_time <= slot.local_time <= latest_time
        and slot.holes == holes
        and slot.transportation == transportation
        and slot.max_players >= player_count
    ]
    return min(candidates, key=lambda slot: slot.local_time, default=None)


def slot_to_book_request(slot: TeeTimeSlot, player_count: int) -> BookNowRequest:
    return BookNowRequest(
        **slot.model_dump(exclude={"max_players", "course_name"}),
        player_count=player_count,
        golfer_quantity=player_count,
    )
