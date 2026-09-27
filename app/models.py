from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"  # HH:MM, 24-hour


class BookNowRequest(BaseModel):
    """Everything needed to book one specific, currently open slot.

    Don't write these by hand: every field except player_count/golfer_quantity comes straight
    from one entry of GET /tee-times (the slot's rate_id, gnc_facility_id, price, etc.).
    """

    course_id: str = Field(description="Mongo-style course id, returned per slot by GET /tee-times")
    facility_id: int = Field(description="Short numeric facility id, see GET /facilities")
    rate_id: int
    gnc_facility_id: int = Field(description="Also called rateSetId")
    teetime_iso: str = Field(description="Tee time in UTC, e.g. 2026-08-27T19:20:00.000Z")
    local_date: str = Field(description="Tee time date in site local (Eastern) time, YYYY-MM-DD")
    local_time: str = Field(description="Tee time in site local (Eastern) time, HH:MM")
    holes: int
    transportation: Literal["Walking", "Cart"]
    price: float = Field(description="Price in dollars")
    player_count: int = 1
    golfer_quantity: int = Field(default=1, description="Keep equal to player_count")


class BookNowResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"success": True, "order_id": "6a8a4d643e32a4083ac68fa8", "detail": "Booked successfully"}]}
    )

    success: bool
    order_id: str | None = None
    detail: str


class Facility(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"facility_id": 7743, "name": "Twin Lakes Golf Course - Lakes Course"}]}
    )

    facility_id: int
    name: str


class TeeTimeSlot(BaseModel):
    """A currently bookable slot, shaped to feed directly into BookNowRequest."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "course_id": "5e3d7968ce07ad0100ad93d0",
                    "facility_id": 7743,
                    "rate_id": 235361805,
                    "gnc_facility_id": 141164,
                    "teetime_iso": "2026-08-27T19:20:00.000Z",
                    "local_date": "2026-08-27",
                    "local_time": "15:20",
                    "holes": 9,
                    "transportation": "Walking",
                    "price": 38.0,
                    "max_players": 4,
                    "course_name": "Twin Lakes Golf Course - Lakes Course",
                }
            ]
        }
    )

    course_id: str
    facility_id: int
    rate_id: int
    gnc_facility_id: int
    teetime_iso: str
    local_date: str
    local_time: str
    holes: int
    transportation: str
    price: float
    max_players: int = Field(description="Most players that can be booked into this tee time right now")
    course_name: str


class BookingStatus(StrEnum):
    PENDING = "pending"  # scheduled, waiting for the window to open
    SEARCHING = "searching"  # window open, looking for the slot
    BOOKED = "booked"
    FAILED = "failed"  # slot found but the booking attempt itself failed
    TERMINATED = "terminated"  # slot never appeared within the search window
    CANCELLED = "cancelled"


class ScheduleRequest(BaseModel):
    """What you want booked. Slot ids aren't needed — they only exist once the slot is open.

    You give a time window; when the booking window opens, the earliest open slot inside it is booked."""

    facility_id: int = Field(description="Short numeric facility id, see GET /facilities")
    local_date: date = Field(description="Tee time date, YYYY-MM-DD. Must not be in the past")
    earliest_time: str = Field(
        pattern=TIME_PATTERN, description="Start of the acceptable tee time window (inclusive), site local time, HH:MM"
    )
    latest_time: str = Field(
        pattern=TIME_PATTERN,
        description="End of the window (inclusive). Same as earliest_time to ask for one exact time",
    )
    holes: int = Field(description="9 or 18")
    transportation: Literal["Walking", "Cart"]
    player_count: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def window_is_ordered(self):
        if self.earliest_time > self.latest_time:
            raise ValueError("earliest_time must not be after latest_time")
        return self


class ScheduledBooking(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "8f42fcd0-fd67-4c53-b814-ed60eb68b5b0",
                    "facility_id": 7743,
                    "local_date": "2026-10-03",
                    "earliest_time": "14:00",
                    "latest_time": "16:00",
                    "holes": 9,
                    "transportation": "Walking",
                    "player_count": 1,
                    "open_at": "2026-09-26T01:00:00Z",
                    "status": "pending",
                    "detail": None,
                    "order_id": None,
                    "created_at": "2026-09-24T13:04:32Z",
                }
            ]
        },
    )

    id: str
    facility_id: int
    local_date: date
    earliest_time: str
    latest_time: str
    holes: int
    transportation: str
    player_count: int
    open_at: datetime = Field(description="When the booking window opens (UTC)")
    status: BookingStatus
    detail: str | None = Field(description="Outcome message once finished (why it failed / terminated)")
    order_id: str | None = Field(description="TeeItUp order id, set once booked")
    created_at: datetime
