from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.config import settings
from app.facilities import FACILITY_NAMES
from app.models import TeeTimeSlot
from app.services.teeitup_client import TeeItUpClient

router = APIRouter(prefix="/tee-times", tags=["tee-times"])

# MVP scope is fairfax-county-mco only, which is Eastern-time courses.
SITE_TIMEZONE = ZoneInfo("America/New_York")


def _local_date_time(teetime_iso: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(teetime_iso.replace("Z", "+00:00")).astimezone(SITE_TIMEZONE)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _price_and_transportation(rate: dict) -> tuple[float, str]:
    if "greenFeeWalking" in rate:
        return rate["greenFeeWalking"] / 100, "Walking"
    if "greenFeeCart" in rate:
        return rate["greenFeeCart"] / 100, "Cart"
    raise ValueError(f"Unrecognized rate pricing shape: {rate}")


@router.get("", response_model=list[TeeTimeSlot])
async def list_tee_times(date: str, facility_ids: str = settings.supported_facility_ids) -> list[TeeTimeSlot]:
    """List currently bookable slots (across all rates/holes/transportation options) for a date."""
    client = TeeItUpClient()
    try:
        await client.login()
        days = await client.search_tee_times(date, facility_ids)
        slots = []
        for day in days:
            for teetime in day["teetimes"]:
                local_date, local_time = _local_date_time(teetime["teetime"])
                for rate in teetime["rates"]:
                    price, transportation = _price_and_transportation(rate)
                    facility_id = rate["golfnow"]["GolfFacilityId"]
                    slots.append(
                        TeeTimeSlot(
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
                    )
        return slots
    finally:
        await client.aclose()
