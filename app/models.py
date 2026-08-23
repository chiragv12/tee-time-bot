from pydantic import BaseModel


class BookNowRequest(BaseModel):
    """Everything needed to book a specific, already-known slot.

    These values (course_id, rate_id, gnc_facility_id) come from a prior search —
    there's no slot discovery here yet, this is for testing the booking sequence itself.
    """

    course_id: str  # Mongo-style facility id, e.g. "5e3d7968ce07ad0100ad93d0"
    facility_id: int  # short numeric id, e.g. 7743
    rate_id: int
    gnc_facility_id: int  # aka rateSetId
    teetime_iso: str  # e.g. "2026-08-27T19:20:00.000Z"
    local_date: str  # "2026-08-27"
    local_time: str  # "15:20"
    holes: int
    transportation: str  # "Walking" | "Cart"
    price: float
    player_count: int = 1
    golfer_quantity: int = 1


class BookNowResult(BaseModel):
    success: bool
    order_id: str | None = None
    detail: str
