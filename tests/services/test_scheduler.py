from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.jobstores.base import JobLookupError

from app.config import settings
from app.models import BookingStatus, BookNowResult
from app.services import scheduler as sched

_OPEN_AT = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)
_DEADLINE = _OPEN_AT + timedelta(minutes=settings.search_window_minutes)


def _booking(**overrides):
    defaults = dict(
        id="b1",
        facility_id=7743,
        local_date=date(2026, 8, 27),
        earliest_time="14:00",
        latest_time="16:00",
        holes=9,
        transportation="Walking",
        player_count=1,
        open_at=_OPEN_AT,
        created_at=_OPEN_AT - timedelta(days=3),
        status=BookingStatus.PENDING,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def repo():
    with patch.object(sched, "repository") as mock_repo:
        for name in ("get_booking", "list_by_status", "update_status"):
            setattr(mock_repo, name, AsyncMock())
        yield mock_repo


@pytest.fixture
def session():
    fake = MagicMock()
    with patch.object(sched, "SessionLocal") as factory:
        factory.return_value.__aenter__.return_value = fake
        yield fake


@pytest.fixture
def fake_scheduler():
    with patch.object(sched, "scheduler") as mock_scheduler:
        yield mock_scheduler


# --- try_find_slot ---------------------------------------------------------------


async def test_try_find_slot_returns_the_matching_slot():
    slot = MagicMock()
    with patch.object(sched, "search_slots", AsyncMock(return_value=["all"])) as search, patch.object(
        sched, "find_earliest_slot", return_value=slot
    ) as match:
        result = await sched.try_find_slot(MagicMock(), _booking())

    assert result is slot
    assert search.call_args.args[1:] == ("2026-08-27", "7743")
    match.assert_called_once_with(["all"], 7743, "14:00", "16:00", 9, "Walking", 1)


async def test_try_find_slot_treats_a_failed_search_as_not_found_yet():
    with patch.object(sched, "search_slots", AsyncMock(side_effect=RuntimeError("timeout"))):
        assert await sched.try_find_slot(MagicMock(), _booking()) is None


# --- poll_for_slot ---------------------------------------------------------------


@pytest.fixture
def polling():
    client = MagicMock(login=AsyncMock(), aclose=AsyncMock())
    with patch.object(sched, "TeeItUpClient", return_value=client), patch.object(
        sched, "sleep_until", AsyncMock()
    ) as sleep_until, patch.object(sched.asyncio, "sleep", AsyncMock()) as nap, patch.object(
        sched, "utc_now", return_value=_OPEN_AT + timedelta(seconds=1)
    ) as now:
        yield SimpleNamespace(client=client, sleep_until=sleep_until, nap=nap, now=now)


async def test_poll_for_slot_logs_in_waits_for_open_then_returns_the_slot(polling):
    slot = MagicMock()
    with patch.object(sched, "try_find_slot", AsyncMock(return_value=slot)):
        assert await sched.poll_for_slot(_booking()) is slot

    polling.client.login.assert_awaited_once()
    polling.sleep_until.assert_awaited_once_with(_OPEN_AT)
    polling.nap.assert_not_awaited()
    polling.client.aclose.assert_awaited_once()


async def test_poll_for_slot_retries_until_the_slot_appears(polling):
    slot = MagicMock()
    with patch.object(sched, "try_find_slot", AsyncMock(side_effect=[None, None, slot])) as find:
        assert await sched.poll_for_slot(_booking()) is slot

    assert find.await_count == 3
    assert polling.nap.await_count == 2
    polling.nap.assert_awaited_with(sched.POLL_INTERVAL_SECONDS)


async def test_poll_for_slot_gives_up_after_the_deadline(polling):
    polling.now.return_value = _DEADLINE + timedelta(seconds=1)
    with patch.object(sched, "try_find_slot", AsyncMock(return_value=None)) as find:
        assert await sched.poll_for_slot(_booking()) is None

    find.assert_awaited_once()  # always one attempt, even if we start past the deadline
    polling.nap.assert_not_awaited()
    polling.client.aclose.assert_awaited_once()


async def test_poll_for_slot_closes_the_client_when_login_fails(polling):
    polling.client.login.side_effect = RuntimeError("bad credentials")

    with pytest.raises(RuntimeError):
        await sched.poll_for_slot(_booking())

    polling.client.aclose.assert_awaited_once()


# --- claim_booking / finish_booking ----------------------------------------------


async def test_claim_booking_moves_pending_to_searching(repo, session):
    booking = _booking()
    repo.get_booking.return_value = booking
    repo.update_status.return_value = booking

    assert await sched.claim_booking("b1") is booking
    repo.update_status.assert_awaited_once_with(session, booking, BookingStatus.SEARCHING)


@pytest.mark.parametrize("found", [None, _booking(status=BookingStatus.CANCELLED)])
async def test_claim_booking_skips_missing_or_non_pending(repo, session, found):
    repo.get_booking.return_value = found

    assert await sched.claim_booking("b1") is None
    repo.update_status.assert_not_awaited()


async def test_finish_booking_updates_status_detail_and_order(repo, session):
    booking = _booking()
    repo.get_booking.return_value = booking

    await sched.finish_booking("b1", BookingStatus.BOOKED, "done", "order1")

    repo.update_status.assert_awaited_once_with(session, booking, BookingStatus.BOOKED, "done", "order1")


async def test_finish_booking_ignores_a_booking_that_no_longer_exists(repo, session):
    repo.get_booking.return_value = None

    await sched.finish_booking("b1", BookingStatus.FAILED)

    repo.update_status.assert_not_awaited()


# --- run_scheduled_booking -------------------------------------------------------


@pytest.fixture
def run():
    with patch.object(sched, "claim_booking", AsyncMock(return_value=_booking())) as claim, patch.object(
        sched, "poll_for_slot", AsyncMock(return_value=MagicMock())
    ) as poll, patch.object(sched, "slot_to_book_request", return_value="request") as to_request, patch.object(
        sched, "book_now", AsyncMock(return_value=BookNowResult(success=True, order_id="o1", detail="Booked"))
    ) as book, patch.object(sched, "finish_booking", AsyncMock()) as finish:
        yield SimpleNamespace(claim=claim, poll=poll, to_request=to_request, book=book, finish=finish)


async def test_run_books_the_found_slot_and_records_success(run):
    await sched.run_scheduled_booking("b1")

    run.book.assert_awaited_once_with("request")
    run.finish.assert_awaited_once_with("b1", BookingStatus.BOOKED, "Booked", "o1")


async def test_run_records_failure_when_the_booking_attempt_fails(run):
    run.book.return_value = BookNowResult(success=False, detail="Slot is no longer bookable")

    await sched.run_scheduled_booking("b1")

    run.finish.assert_awaited_once_with("b1", BookingStatus.FAILED, "Slot is no longer bookable", None)


async def test_run_terminates_when_the_slot_never_appears(run):
    run.poll.return_value = None

    await sched.run_scheduled_booking("b1")

    run.book.assert_not_awaited()
    assert run.finish.call_args.args[:2] == ("b1", BookingStatus.TERMINATED)


async def test_run_does_nothing_when_the_booking_was_cancelled(run):
    run.claim.return_value = None

    await sched.run_scheduled_booking("b1")

    run.poll.assert_not_awaited()
    run.finish.assert_not_awaited()


async def test_run_marks_failed_instead_of_leaving_it_searching_on_a_crash(run):
    run.poll.side_effect = RuntimeError("boom")

    await sched.run_scheduled_booking("b1")

    run.finish.assert_awaited_once_with("b1", BookingStatus.FAILED, "RuntimeError: boom")


# --- schedule_job / unschedule_job -----------------------------------------------


def test_schedule_job_registers_a_one_off_job_at_the_wake_time(fake_scheduler):
    booking = _booking()
    wake = _OPEN_AT - timedelta(seconds=30)

    with patch.object(sched, "compute_wake_at", return_value=wake):
        sched.schedule_job(booking)

    fake_scheduler.add_job.assert_called_once_with(
        sched.run_scheduled_booking,
        "date",
        run_date=wake,
        args=["b1"],
        id="b1",
        replace_existing=True,
        misfire_grace_time=None,
    )


def test_unschedule_job_removes_the_job(fake_scheduler):
    sched.unschedule_job("b1")

    fake_scheduler.remove_job.assert_called_once_with("b1")


def test_unschedule_job_ignores_a_job_that_already_fired(fake_scheduler):
    fake_scheduler.remove_job.side_effect = JobLookupError("b1")

    sched.unschedule_job("b1")


# --- rehydrate_jobs --------------------------------------------------------------


async def test_rehydrate_fails_bookings_that_were_mid_search_instead_of_rerunning_them(repo, session):
    searching = _booking(status=BookingStatus.SEARCHING)
    repo.list_by_status.side_effect = lambda _session, status: [searching] if status == BookingStatus.SEARCHING else []

    await sched.rehydrate_jobs()

    args = repo.update_status.call_args.args
    assert args[:3] == (session, searching, BookingStatus.FAILED)
    assert "restart" in args[3]


async def test_rehydrate_terminates_pending_bookings_whose_window_has_passed(repo, session, fake_scheduler):
    stale = _booking()
    repo.list_by_status.side_effect = lambda _session, status: [stale] if status == BookingStatus.PENDING else []

    with patch.object(sched, "utc_now", return_value=_DEADLINE + timedelta(seconds=1)):
        await sched.rehydrate_jobs()

    assert repo.update_status.call_args.args[:3] == (session, stale, BookingStatus.TERMINATED)
    fake_scheduler.add_job.assert_not_called()


async def test_rehydrate_reschedules_pending_bookings_still_inside_their_window(repo, session):
    live = _booking()
    repo.list_by_status.side_effect = lambda _session, status: [live] if status == BookingStatus.PENDING else []

    with patch.object(sched, "utc_now", return_value=_OPEN_AT - timedelta(days=1)), patch.object(
        sched, "schedule_job"
    ) as schedule:
        await sched.rehydrate_jobs()

    schedule.assert_called_once_with(live)
    repo.update_status.assert_not_awaited()
