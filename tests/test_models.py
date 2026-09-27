import pytest
from pydantic import ValidationError

from app.models import ScheduleRequest

_VALID = dict(
    facility_id=7743, local_date="2026-10-03", earliest_time="14:00", latest_time="16:00", holes=9, transportation="Walking"
)


def test_schedule_request_accepts_a_time_window():
    request = ScheduleRequest(**_VALID)

    assert (request.earliest_time, request.latest_time) == ("14:00", "16:00")
    assert request.player_count == 1


def test_schedule_request_accepts_an_exact_time_as_a_one_point_window():
    ScheduleRequest(**{**_VALID, "earliest_time": "15:20", "latest_time": "15:20"})


def test_schedule_request_rejects_a_backwards_window():
    with pytest.raises(ValidationError, match="earliest_time must not be after latest_time"):
        ScheduleRequest(**{**_VALID, "earliest_time": "16:00", "latest_time": "14:00"})


@pytest.mark.parametrize("bad_time", ["3pm", "1500", "24:00", "12:60", "9:00", ""])
def test_schedule_request_rejects_malformed_times(bad_time):
    with pytest.raises(ValidationError):
        ScheduleRequest(**{**_VALID, "earliest_time": bad_time})
