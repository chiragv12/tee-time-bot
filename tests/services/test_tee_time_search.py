from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import TeeTimeSlot
from app.services.tee_time_search import (
    build_slot,
    find_earliest_slot,
    flatten_search_response,
    local_date_time,
    price_and_transportation,
    search_slots,
    slot_to_book_request,
)

_WALKING_RATE = {
    "_id": 235361805,
    "holes": 9,
    "golfnow": {"GolfFacilityId": 7743, "GolfCourseId": 141164},
    "greenFeeWalking": 3800,
}
_CART_RATE = {
    "_id": 235364302,
    "holes": 9,
    "golfnow": {"GolfFacilityId": 7743, "GolfCourseId": 149742},
    "greenFeeCart": 5400,
}
_UNKNOWN_FACILITY_RATE = {
    "_id": 999999,
    "holes": 18,
    "golfnow": {"GolfFacilityId": 9999, "GolfCourseId": 111111},
    "greenFeeWalking": 4600,
}
_TEETIME = {
    "courseId": "5e3d7968ce07ad0100ad93d0",
    "teetime": "2026-08-27T19:20:00.000Z",
    "maxPlayers": 4,
    "rates": [_WALKING_RATE, _CART_RATE],
}
_SEARCH_RESPONSE = [
    {
        "teetimes": [
            _TEETIME,
            {
                "courseId": "other-course",
                "teetime": "2026-08-27T20:10:00.000Z",
                "maxPlayers": 1,
                "rates": [_UNKNOWN_FACILITY_RATE],
            },
        ]
    }
]


def _slot(**overrides) -> TeeTimeSlot:
    defaults = dict(
        course_id="c1",
        facility_id=7743,
        rate_id=1,
        gnc_facility_id=2,
        teetime_iso="2026-08-27T19:20:00.000Z",
        local_date="2026-08-27",
        local_time="15:20",
        holes=9,
        transportation="Walking",
        price=38.0,
        max_players=4,
        course_name="Twin Lakes Golf Course - Lakes Course",
    )
    defaults.update(overrides)
    return TeeTimeSlot(**defaults)


def test_local_date_time_converts_utc_to_eastern():
    assert local_date_time("2026-08-27T19:20:00.000Z") == ("2026-08-27", "15:20")


def test_local_date_time_can_roll_back_to_previous_local_day():
    assert local_date_time("2026-08-28T01:30:00.000Z") == ("2026-08-27", "21:30")


def test_price_and_transportation_walking_converts_cents_to_dollars():
    assert price_and_transportation(_WALKING_RATE) == (38.0, "Walking")


def test_price_and_transportation_cart():
    assert price_and_transportation(_CART_RATE) == (54.0, "Cart")


def test_price_and_transportation_rejects_unrecognized_rate_shape():
    with pytest.raises(ValueError, match="Unrecognized rate pricing shape"):
        price_and_transportation({"holes": 9})


def test_build_slot_maps_all_fields_and_known_course_name():
    slot = build_slot(_TEETIME, _WALKING_RATE)

    assert slot.course_id == "5e3d7968ce07ad0100ad93d0"
    assert slot.facility_id == 7743
    assert slot.rate_id == 235361805
    assert slot.gnc_facility_id == 141164
    assert slot.local_time == "15:20"
    assert slot.max_players == 4
    assert slot.course_name == "Twin Lakes Golf Course - Lakes Course"


def test_build_slot_falls_back_to_generic_name_for_unknown_facility():
    slot = build_slot(_TEETIME, _UNKNOWN_FACILITY_RATE)

    assert slot.course_name == "Facility 9999"


def test_flatten_search_response_returns_one_slot_per_rate():
    slots = flatten_search_response(_SEARCH_RESPONSE)

    assert [s.rate_id for s in slots] == [235361805, 235364302, 999999]


async def test_search_slots_flattens_the_client_response():
    client = MagicMock()
    client.search_tee_times = AsyncMock(return_value=_SEARCH_RESPONSE)

    slots = await search_slots(client, "2026-08-27", "7743")

    assert len(slots) == 3
    client.search_tee_times.assert_awaited_once_with("2026-08-27", "7743")


def _find(slots, earliest="15:00", latest="16:00", facility_id=7743, holes=9, transportation="Walking", players=1):
    return find_earliest_slot(slots, facility_id, earliest, latest, holes, transportation, players)


def test_find_earliest_slot_picks_the_earliest_inside_the_window_regardless_of_input_order():
    earliest = _slot(rate_id=1, local_time="15:10")

    slots = [_slot(rate_id=2, local_time="15:40"), earliest, _slot(rate_id=3, local_time="15:20")]

    assert _find(slots) is earliest


def test_find_earliest_slot_includes_both_ends_of_the_window():
    at_start = _slot(local_time="15:00")
    at_end = _slot(local_time="16:00")

    assert _find([at_end, at_start]) is at_start
    assert _find([at_end]) is at_end


def test_find_earliest_slot_ignores_times_outside_the_window():
    slots = [_slot(local_time="14:50"), _slot(local_time="16:10")]

    assert _find(slots) is None


def test_find_earliest_slot_still_works_for_a_single_exact_time():
    exact = _slot(local_time="15:20")

    assert _find([_slot(local_time="15:30"), exact], earliest="15:20", latest="15:20") is exact


def test_find_earliest_slot_matches_holes_and_transportation():
    match = _slot(rate_id=7, local_time="15:30")
    slots = [_slot(holes=18, local_time="15:00"), _slot(transportation="Cart", local_time="15:05"), match]

    assert _find(slots) is match


def test_find_earliest_slot_requires_enough_room_for_the_party():
    assert _find([_slot(local_time="15:30", max_players=1)], players=2) is None


def test_find_earliest_slot_requires_matching_facility():
    assert _find([_slot(local_time="15:30", facility_id=7756)]) is None


def test_find_earliest_slot_returns_none_when_nothing_matches():
    assert _find([]) is None


def test_slot_to_book_request_copies_booking_fields_and_party_size():
    request = slot_to_book_request(_slot(), player_count=2)

    assert request.course_id == "c1"
    assert request.rate_id == 1
    assert request.gnc_facility_id == 2
    assert request.price == 38.0
    assert request.player_count == 2
    assert request.golfer_quantity == 2
