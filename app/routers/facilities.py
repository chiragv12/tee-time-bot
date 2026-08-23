from fastapi import APIRouter

from app.facilities import FACILITY_NAMES
from app.models import Facility

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=list[Facility])
async def list_facilities() -> list[Facility]:
    """List the supported facility IDs and names, for course-selection UI."""
    return [Facility(facility_id=facility_id, name=name) for facility_id, name in FACILITY_NAMES.items()]
