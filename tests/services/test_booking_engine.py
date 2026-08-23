from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import BookNowRequest
from app.services.booking_engine import INVENTORY_CHANNEL_ID, book_now


def _sample_request(**overrides) -> BookNowRequest:
    defaults = dict(
        course_id="5e3d7968ce07ad0100ad93d0",
        facility_id=7743,
        rate_id=235361805,
        gnc_facility_id=141164,
        teetime_iso="2026-08-27T19:20:00.000Z",
        local_date="2026-08-27",
        local_time="15:20",
        holes=9,
        transportation="Walking",
        price=38,
    )
    defaults.update(overrides)
    return BookNowRequest(**defaults)


def _make_fake_client(**overrides) -> MagicMock:
    client = MagicMock()
    client.login = AsyncMock()
    client.customer = {
        "username": "chirag@example.com",
        "name": {"given": "Chirag", "family": "Venkatesan", "formatted": "Chirag Venkatesan"},
        "phoneNumbers": [{"value": "16099033585"}],
    }
    client.get_rate_invoice = AsyncMock(return_value={})
    client.lock_tee_time = AsyncMock(return_value=[])
    client.unlock_tee_time = AsyncMock()
    client.create_cart = AsyncMock(return_value={"id": "cart1"})
    client.add_to_cart = AsyncMock(return_value={"items": [{"id": "item1"}]})
    client.is_bookable = AsyncMock(return_value={"bookable": True})
    client.create_order = AsyncMock(return_value={"id": "order-doc-1"})
    client.order_teetime = AsyncMock(
        return_value={
            "id": "order1",
            "teetimes": [{"players": [{"invoice": {"referenceId": "ref1"}}]}],
        }
    )
    client.update_profile = AsyncMock(return_value={})
    client.get_reservation_token = AsyncMock(return_value="reservation-token-1")

    add_reservation_response = MagicMock()
    add_reservation_response.json.return_value = {"Success": True, "Message": ""}
    add_reservation_response.status_code = 200
    add_reservation_response.url = "https://tr.gnsvc.com/AddReservation"
    client.add_reservation = AsyncMock(return_value=add_reservation_response)

    client.poll_order_status = AsyncMock(return_value={})
    client.clear_cart = AsyncMock()
    client.aclose = AsyncMock()

    for key, value in overrides.items():
        setattr(client, key, value)
    return client


@pytest.fixture
def client_cls():
    with patch("app.services.booking_engine.TeeItUpClient") as cls:
        yield cls


async def test_book_now_success(client_cls):
    client = _make_fake_client()
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is True
    assert result.order_id == "order1"
    client.aclose.assert_awaited_once()


async def test_book_now_uses_server_issued_reference_id_not_a_generated_one(client_cls):
    client = _make_fake_client()
    client_cls.return_value = client

    await book_now(_sample_request())

    sent_form = client.add_reservation.call_args.args[0]
    assert sent_form["TeeTime.ReferenceID"] == "ref1"
    assert sent_form["TeeTime.InventoryChannelID"] == INVENTORY_CHANNEL_ID
    assert sent_form["Token"] == "reservation-token-1"


async def test_book_now_no_phone_number_short_circuits_before_locking(client_cls):
    client = _make_fake_client()
    client.customer = {"username": "x", "name": {}, "phoneNumbers": []}
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is False
    assert "phone number" in result.detail
    client.lock_tee_time.assert_not_awaited()


async def test_book_now_not_bookable_reports_failure_and_cleans_up(client_cls):
    client = _make_fake_client(is_bookable=AsyncMock(return_value={"bookable": False}))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is False
    assert "lost the race" in result.detail
    client.unlock_tee_time.assert_awaited_once()
    client.clear_cart.assert_awaited_once_with("cart1")
    client.create_order.assert_not_awaited()


async def test_book_now_add_reservation_failure_is_reported_as_failure(client_cls):
    response = MagicMock()
    response.json.return_value = {"Success": False, "Message": "Unable to find stored override reference"}
    client = _make_fake_client(add_reservation=AsyncMock(return_value=response))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is False
    assert "Unable to find stored override reference" in result.detail
    client.poll_order_status.assert_not_awaited()


async def test_book_now_poll_status_failure_after_real_success_is_non_fatal(client_cls):
    client = _make_fake_client(poll_order_status=AsyncMock(side_effect=Exception("400 Bad Request")))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is True
    assert result.order_id == "order1"


async def test_book_now_exception_mid_flow_is_caught_and_cleans_up(client_cls):
    client = _make_fake_client(create_order=AsyncMock(side_effect=RuntimeError("boom")))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is False
    assert "boom" in result.detail
    client.unlock_tee_time.assert_awaited_once()
    client.clear_cart.assert_awaited_once_with("cart1")


async def test_book_now_cleanup_failure_does_not_mask_a_successful_result(client_cls):
    client = _make_fake_client(unlock_tee_time=AsyncMock(side_effect=Exception("cleanup failed")))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is True


async def test_book_now_clear_cart_failure_does_not_mask_a_successful_result(client_cls):
    client = _make_fake_client(clear_cart=AsyncMock(side_effect=Exception("clear cart failed")))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is True


async def test_book_now_never_locked_skips_unlock_in_cleanup(client_cls):
    client = _make_fake_client(get_rate_invoice=AsyncMock(side_effect=RuntimeError("network error")))
    client_cls.return_value = client

    result = await book_now(_sample_request())

    assert result.success is False
    client.unlock_tee_time.assert_not_awaited()
    client.clear_cart.assert_not_awaited()
