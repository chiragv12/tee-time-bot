from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.teeitup_client import TeeItUpClient


def _mock_response(json_body=None, raise_error: bool = False):
    response = MagicMock()
    response.json.return_value = json_body
    if raise_error:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    else:
        response.raise_for_status.return_value = None
    return response


@pytest.fixture
async def client():
    c = TeeItUpClient()
    yield c
    await c.aclose()


@pytest.fixture
async def authed_client(client):
    client._session_token = "session-token-123"
    client.customer = {"username": "chirag@example.com"}
    return client


async def test_auth_headers_requires_login(client):
    with pytest.raises(RuntimeError, match="login"):
        client._auth_headers()


async def test_login_sets_session_token_and_customer(client):
    body = {"sessionToken": "abc", "customer": {"username": "chirag@example.com"}}
    with patch.object(client._http, "post", AsyncMock(return_value=_mock_response(body))) as mock_post:
        await client.login()

    assert client._session_token == "abc"
    assert client.customer == {"username": "chirag@example.com"}
    mock_post.assert_awaited_once()
    assert mock_post.call_args.args[0] == "/profile/authenticate"
    assert mock_post.call_args.kwargs["json"]["type"] == "basic"


async def test_login_propagates_http_errors(client):
    with patch.object(client._http, "post", AsyncMock(return_value=_mock_response(raise_error=True))):
        with pytest.raises(httpx.HTTPStatusError):
            await client.login()


async def test_search_tee_times_sends_expected_params(authed_client):
    body = [{"teetimes": []}]
    with patch.object(authed_client._http, "get", AsyncMock(return_value=_mock_response(body))) as mock_get:
        result = await authed_client.search_tee_times("2026-08-27", "7743,7756")

    assert result == body
    assert mock_get.call_args.args[0] == "/v2/tee-times"
    assert mock_get.call_args.kwargs["params"] == {
        "date": "2026-08-27",
        "facilityIds": "7743,7756",
        "returnPromotedRates": "true",
    }
    assert mock_get.call_args.kwargs["headers"] == {"session": "session-token-123"}


async def test_get_rate_invoice_sends_expected_params(authed_client):
    with patch.object(authed_client._http, "get", AsyncMock(return_value=_mock_response({}))) as mock_get:
        await authed_client.get_rate_invoice(235361805, 141164, 1)

    assert mock_get.call_args.args[0] == "/tee-times/rate/235361805/invoice"
    assert mock_get.call_args.kwargs["params"] == {"gncFacilityId": 141164, "playerCount": 1}


async def test_lock_tee_time_sends_expected_params(authed_client):
    with patch.object(authed_client._http, "get", AsyncMock(return_value=_mock_response([]))) as mock_get:
        await authed_client.lock_tee_time("course123", "2026-08-27", "15:20")

    assert mock_get.call_args.args[0] == "/course/course123/tee-time/locks"
    assert mock_get.call_args.kwargs["params"] == {"localDate": "2026-08-27", "localTime": "15:20"}


async def test_unlock_tee_time_uses_delete_request_with_body(authed_client):
    with patch.object(authed_client._http, "request", AsyncMock(return_value=_mock_response())) as mock_request:
        await authed_client.unlock_tee_time("course123", "2026-08-27T19:20:00.000Z")

    mock_request.assert_awaited_once()
    assert mock_request.call_args.args[0] == "DELETE"
    assert mock_request.call_args.args[1] == "/course/course123/tee-time/lock"
    assert mock_request.call_args.kwargs["json"] == {"teetime": "2026-08-27T19:20:00.000Z"}


async def test_create_cart_posts_with_no_body(authed_client):
    body = {"id": "cart1", "items": []}
    with patch.object(authed_client._http, "post", AsyncMock(return_value=_mock_response(body))) as mock_post:
        result = await authed_client.create_cart()

    assert result == body
    assert mock_post.call_args.args[0] == "/shopping-cart"
    assert "json" not in mock_post.call_args.kwargs


async def test_add_to_cart_wraps_item_in_item_key(authed_client):
    with patch.object(authed_client._http, "post", AsyncMock(return_value=_mock_response({}))) as mock_post:
        await authed_client.add_to_cart("cart1", {"facilityId": 7743})

    assert mock_post.call_args.args[0] == "/shopping-cart/cart1/cart-item"
    assert mock_post.call_args.kwargs["json"] == {"item": {"facilityId": 7743}}


async def test_is_bookable_hits_expected_url(authed_client):
    body = {"bookable": True}
    with patch.object(authed_client._http, "post", AsyncMock(return_value=_mock_response(body))) as mock_post:
        result = await authed_client.is_bookable("cart1", "item1")

    assert result == body
    assert mock_post.call_args.args[0] == "/shopping-cart/cart1/cart-item/item1/is-bookable"


async def test_create_order_sends_cart_id(authed_client):
    with patch.object(authed_client._http, "post", AsyncMock(return_value=_mock_response({}))) as mock_post:
        await authed_client.create_order("cart1")

    assert mock_post.call_args.args[0] == "/orders"
    assert mock_post.call_args.kwargs["json"] == {"language": "en", "cartId": "cart1"}


async def test_order_teetime_sends_expected_payload(authed_client):
    with patch.object(authed_client._http, "post", AsyncMock(return_value=_mock_response({}))) as mock_post:
        await authed_client.order_teetime("2026-08-27T19:20:00.000Z", 235361805, "cart1", "item1", 1)

    assert mock_post.call_args.args[0] == "/order-teetime"
    assert mock_post.call_args.kwargs["json"] == {
        "teetime": "2026-08-27T19:20:00.000Z",
        "rateId": 235361805,
        "cartId": "cart1",
        "cartItemId": "item1",
        "golferQuantity": 1,
    }


async def test_update_profile_puts_expected_payload(authed_client):
    payload = {"emailAddress": "chirag@example.com"}
    with patch.object(authed_client._http, "put", AsyncMock(return_value=_mock_response({}))) as mock_put:
        await authed_client.update_profile(payload)

    assert mock_put.call_args.args[0] == "/v2/profile"
    assert mock_put.call_args.kwargs["json"] == payload


async def test_get_reservation_token_returns_bare_string(authed_client):
    with patch.object(authed_client._http, "get", AsyncMock(return_value=_mock_response("token-abc"))):
        result = await authed_client.get_reservation_token()

    assert result == "token-abc"


async def test_add_reservation_posts_to_legacy_host_without_session_header(client):
    fake_response = _mock_response()
    inner_client = MagicMock()
    inner_client.post = AsyncMock(return_value=fake_response)
    inner_client.__aenter__ = AsyncMock(return_value=inner_client)
    inner_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.teeitup_client.httpx.AsyncClient", return_value=inner_client):
        result = await client.add_reservation({"TeeTime.FacilityID": 7743})

    inner_client.post.assert_awaited_once_with("https://tr.gnsvc.com/AddReservation", data={"TeeTime.FacilityID": 7743})
    assert result is fake_response


async def test_poll_order_status_sends_cart_and_item_id(authed_client):
    with patch.object(authed_client._http, "patch", AsyncMock(return_value=_mock_response({}))) as mock_patch:
        await authed_client.poll_order_status("order1", "cart1", "item1")

    assert mock_patch.call_args.args[0] == "/order-teetime/status/order1"
    assert mock_patch.call_args.kwargs["params"] == {"cartId": "cart1", "cartItemId": "item1"}


async def test_clear_cart_deletes_expected_url(authed_client):
    with patch.object(authed_client._http, "delete", AsyncMock(return_value=_mock_response())) as mock_delete:
        await authed_client.clear_cart("cart1")

    assert mock_delete.call_args.args[0] == "/shopping-cart/cart1"
