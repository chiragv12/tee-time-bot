from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.db import get_session
from app.facilities import FACILITY_NAMES
from app.models import BookingStatus, BookNowRequest, BookNowResult, ScheduledBooking, ScheduleRequest
from app.orm import BookingRecord
from app.services.booking_engine import book_now
from app.services.schedule_timing import compute_open_at, site_today
from app.services.scheduler import schedule_job, unschedule_job

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Example payloads shown (and runnable) in Swagger UI at /docs. The schedule dates are computed
# so "Try it out" is never rejected as being in the past.
_EXAMPLE_DATE = (site_today() + timedelta(days=10)).isoformat()

SCHEDULE_EXAMPLES = {
    "nine_holes_walking": {
        "summary": "9 holes, walking, anytime 2-4pm",
        "value": {
            "facility_id": 7743,
            "local_date": _EXAMPLE_DATE,
            "earliest_time": "14:00",
            "latest_time": "16:00",
            "holes": 9,
            "transportation": "Walking",
            "player_count": 1,
        },
    },
    "eighteen_holes_cart_foursome": {
        "summary": "18 holes, cart, foursome, Oaks course, 7:30-9am",
        "value": {
            "facility_id": 7756,
            "local_date": _EXAMPLE_DATE,
            "earliest_time": "07:30",
            "latest_time": "09:00",
            "holes": 18,
            "transportation": "Cart",
            "player_count": 4,
        },
    },
}

# Real values from a GET /tee-times response. These are for a past date, so booking them will
# fail at the lock/bookable step — copy a fresh slot from GET /tee-times for a real attempt.
BOOK_NOW_EXAMPLES = {
    "nine_holes_walking": {
        "summary": "9 holes, walking (Lakes course)",
        "value": {
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
            "player_count": 1,
            "golfer_quantity": 1,
        },
    },
    "eighteen_holes_cart": {
        "summary": "18 holes, cart",
        "value": {
            "course_id": "5e3d7968ce07ad0100ad93d0",
            "facility_id": 7743,
            "rate_id": 235364359,
            "gnc_facility_id": 149764,
            "teetime_iso": "2026-08-27T19:20:00.000Z",
            "local_date": "2026-08-27",
            "local_time": "15:20",
            "holes": 18,
            "transportation": "Cart",
            "price": 76.0,
            "player_count": 1,
            "golfer_quantity": 1,
        },
    },
}


def validate_schedule_request(request: ScheduleRequest) -> None:
    if request.facility_id not in FACILITY_NAMES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unsupported facility {request.facility_id}")
    if request.local_date < site_today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "local_date is in the past")


async def get_booking_or_404(session: AsyncSession, booking_id: str) -> BookingRecord:
    booking = await repository.get_booking(session, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Booking {booking_id} not found")
    return booking


@router.post(
    "/book-now",
    response_model=BookNowResult,
    summary="Book a currently open slot right now",
    responses={500: {"model": BookNowResult, "description": "The booking attempt failed; `detail` says why"}},
)
async def book_now_endpoint(
    request: Annotated[BookNowRequest, Body(openapi_examples=BOOK_NOW_EXAMPLES)], response: Response
) -> BookNowResult:
    """Runs the full booking sequence immediately against TeeItUp. **This makes a real reservation.**

    Take the slot's fields from `GET /tee-times`. To book something that isn't open yet, use
    `POST /bookings/schedule` instead."""
    result = await book_now(request)
    if not result.success:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return result


@router.post(
    "/schedule",
    response_model=ScheduledBooking,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a booking for when its window opens",
    responses={422: {"description": "Unsupported facility, date in the past, or malformed field"}},
)
async def schedule_booking(
    request: Annotated[ScheduleRequest, Body(openapi_examples=SCHEDULE_EXAMPLES)],
    session: AsyncSession = Depends(get_session),
):
    """Describe the slot you want as a time window; the server books the earliest match the moment one appears.

    It wakes 30s before the booking window opens (9pm ET, 8 days before the tee time), searches
    every second, and books the earliest open slot inside your `earliest_time`-`latest_time` range
    (inclusive) as soon as one shows up. If it hasn't appeared 10 minutes after
    the window opens, the booking is marked `terminated`. If the window is already open, it starts
    immediately. **A match makes a real reservation.** Track it with `GET /bookings/{id}`."""
    validate_schedule_request(request)
    booking = await repository.create_booking(session, request, compute_open_at(request.local_date))
    schedule_job(booking)
    return booking


@router.get("", response_model=list[ScheduledBooking], summary="List scheduled bookings, newest first")
async def list_bookings(session: AsyncSession = Depends(get_session)):
    return await repository.list_bookings(session)


@router.get(
    "/{booking_id}",
    response_model=ScheduledBooking,
    summary="Get one scheduled booking and its status",
    responses={404: {"description": "No booking with that id"}},
)
async def get_booking(booking_id: str, session: AsyncSession = Depends(get_session)):
    return await get_booking_or_404(session, booking_id)


@router.delete(
    "/{booking_id}",
    response_model=ScheduledBooking,
    summary="Cancel a scheduled booking",
    responses={
        404: {"description": "No booking with that id"},
        409: {"description": "Already searching, booked, or finished, so it can no longer be cancelled"},
    },
)
async def cancel_booking(booking_id: str, session: AsyncSession = Depends(get_session)):
    """Cancel a booking that hasn't started searching yet (status `pending`)."""
    booking = await get_booking_or_404(session, booking_id)
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel a booking that is {booking.status}")
    unschedule_job(booking_id)
    return await repository.update_status(session, booking, BookingStatus.CANCELLED)
