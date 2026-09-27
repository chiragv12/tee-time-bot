"""Wake when a booking window opens, find the target slot, and hand it to book_now().

The bookings table is the source of truth for what's scheduled; APScheduler only holds the
in-memory wake-up timers, which are rebuilt from pending rows on startup.
"""

import asyncio
import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import repository
from app.config import settings
from app.db import SessionLocal
from app.models import BookingStatus, TeeTimeSlot
from app.orm import BookingRecord
from app.services.booking_engine import book_now
from app.services.schedule_timing import compute_deadline, compute_wake_at, sleep_until, utc_now
from app.services.tee_time_search import find_earliest_slot, search_slots, slot_to_book_request
from app.services.teeitup_client import TeeItUpClient

logger = logging.getLogger(__name__)

# How often to search once the window is open. 1s is fast enough to win slots that vanish in
# seconds; if TeeItUp starts throttling (we saw a hang once after many rapid calls), raise it.
POLL_INTERVAL_SECONDS = 1.0

scheduler = AsyncIOScheduler()


async def try_find_slot(client: TeeItUpClient, booking: BookingRecord) -> TeeTimeSlot | None:
    """One search attempt. A failed search is just 'not found yet' — the next poll retries."""
    try:
        slots = await search_slots(client, booking.local_date.isoformat(), str(booking.facility_id))
    except Exception:
        logger.warning("slot search failed for booking %s", booking.id, exc_info=True)
        return None
    return find_earliest_slot(
        slots,
        booking.facility_id,
        booking.earliest_time,
        booking.latest_time,
        booking.holes,
        booking.transportation,
        booking.player_count,
    )


async def poll_for_slot(booking: BookingRecord) -> TeeTimeSlot | None:
    """Log in early, wait for the window to open, then search every poll interval until the deadline."""
    deadline = compute_deadline(booking.open_at, booking.created_at)
    client = TeeItUpClient()
    try:
        await client.login()
        logger.info("booking %s: logged in, waiting for the window to open at %s", booking.id, booking.open_at)
        await sleep_until(booking.open_at)
        logger.info("booking %s: window open, searching until %s", booking.id, deadline)
        while True:
            slot = await try_find_slot(client, booking)
            if slot is not None or utc_now() >= deadline:
                return slot
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await client.aclose()


async def claim_booking(booking_id: str) -> BookingRecord | None:
    """Move pending -> searching; returns None if it was cancelled (or removed) in the meantime."""
    async with SessionLocal() as session:
        booking = await repository.get_booking(session, booking_id)
        # ponytail: check-then-set isn't atomic; a cancel landing between the two can lose. Use a
        # conditional UPDATE if cancels ever race real jobs.
        if booking is None or booking.status != BookingStatus.PENDING:
            return None
        return await repository.update_status(session, booking, BookingStatus.SEARCHING)


async def finish_booking(
    booking_id: str, status: BookingStatus, detail: str | None = None, order_id: str | None = None
) -> None:
    async with SessionLocal() as session:
        booking = await repository.get_booking(session, booking_id)
        if booking is not None:
            await repository.update_status(session, booking, status, detail, order_id)


async def run_scheduled_booking(booking_id: str) -> None:
    try:
        booking = await claim_booking(booking_id)
        if booking is None:
            logger.info("booking %s: not pending any more, skipping", booking_id)
            return
        slot = await poll_for_slot(booking)
        if slot is None:
            logger.info("booking %s: slot never appeared, terminating", booking_id)
            await finish_booking(
                booking_id,
                BookingStatus.TERMINATED,
                f"Slot never appeared within {settings.search_window_minutes} minutes of the window opening",
            )
            return
        logger.info("booking %s: found %s %s (rate %s), booking it", booking_id, slot.local_date, slot.local_time, slot.rate_id)
        result = await book_now(slot_to_book_request(slot, booking.player_count))
        status = BookingStatus.BOOKED if result.success else BookingStatus.FAILED
        logger.info("booking %s: %s - %s", booking_id, status, result.detail)
        await finish_booking(booking_id, status, result.detail, result.order_id)
    except Exception as exc:
        logger.exception("scheduled booking %s crashed", booking_id)
        await finish_booking(booking_id, BookingStatus.FAILED, f"{type(exc).__name__}: {exc}")


def schedule_job(booking: BookingRecord) -> None:
    run_date = compute_wake_at(booking.open_at, utc_now())
    logger.info("booking %s: will wake at %s (window opens %s)", booking.id, run_date, booking.open_at)
    scheduler.add_job(
        run_scheduled_booking,
        "date",
        run_date=run_date,
        args=[booking.id],
        id=booking.id,
        replace_existing=True,
        misfire_grace_time=None,  # a late wake still runs; the search deadline handles staleness
    )


def unschedule_job(booking_id: str) -> None:
    try:
        scheduler.remove_job(booking_id)
    except JobLookupError:
        pass  # already fired or never registered


async def rehydrate_jobs() -> None:
    """Rebuild timers after a restart.

    Anything mid-search when we died is failed rather than re-run: book_now may have already
    committed a reservation, and retrying could double-book.
    """
    async with SessionLocal() as session:
        for booking in await repository.list_by_status(session, BookingStatus.SEARCHING):
            await repository.update_status(
                session, booking, BookingStatus.FAILED, "Interrupted by a server restart; check TeeItUp before retrying"
            )
        for booking in await repository.list_by_status(session, BookingStatus.PENDING):
            if utc_now() >= compute_deadline(booking.open_at, booking.created_at):
                await repository.update_status(
                    session, booking, BookingStatus.TERMINATED, "Search window passed while the server was down"
                )
            else:
                schedule_job(booking)
