"""Direct HTTP client for the TeeItUp/Kenna booking API.

Endpoint shapes reverse-engineered from a real booking flow — see docs/teeitup-api.md.
"""

import httpx

from app.config import settings


class TeeItUpClient:
    def __init__(self) -> None:
        self._session_token: str | None = None
        self.customer: dict | None = None
        self._http = httpx.AsyncClient(
            base_url=settings.teeitup_api_base,
            headers={"x-be-alias": settings.teeitup_site_alias},
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _auth_headers(self) -> dict[str, str]:
        if not self._session_token:
            raise RuntimeError("Not authenticated — call login() first")
        return {"session": self._session_token}

    async def login(self) -> None:
        response = await self._http.post(
            "/profile/authenticate",
            json={
                "username": settings.teeitup_username,
                "credentials": settings.teeitup_password,
                "type": "basic",
            },
        )
        response.raise_for_status()
        body = response.json()
        self._session_token = body["sessionToken"]
        self.customer = body["customer"]

    async def search_tee_times(self, date: str, facility_ids: str) -> list[dict]:
        response = await self._http.get(
            "/v2/tee-times",
            params={"date": date, "facilityIds": facility_ids, "returnPromotedRates": "true"},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def get_rate_invoice(self, rate_id: int, gnc_facility_id: int, player_count: int) -> dict:
        response = await self._http.get(
            f"/tee-times/rate/{rate_id}/invoice",
            params={"gncFacilityId": gnc_facility_id, "playerCount": player_count},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def lock_tee_time(self, course_id: str, local_date: str, local_time: str) -> dict:
        response = await self._http.get(
            f"/course/{course_id}/tee-time/locks",
            params={"localDate": local_date, "localTime": local_time},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def unlock_tee_time(self, course_id: str, teetime_iso: str) -> None:
        response = await self._http.request(
            "DELETE",
            f"/course/{course_id}/tee-time/lock",
            json={"teetime": teetime_iso},
            headers=self._auth_headers(),
        )
        response.raise_for_status()

    async def create_cart(self) -> dict:
        response = await self._http.post("/shopping-cart", headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    async def add_to_cart(self, cart_id: str, item: dict) -> dict:
        response = await self._http.post(
            f"/shopping-cart/{cart_id}/cart-item",
            json={"item": item},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def is_bookable(self, cart_id: str, cart_item_id: str) -> dict:
        response = await self._http.post(
            f"/shopping-cart/{cart_id}/cart-item/{cart_item_id}/is-bookable",
            json={"reservationCountsByTime": {}},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def create_order(self, cart_id: str) -> dict:
        response = await self._http.post(
            "/orders",
            json={"language": "en", "cartId": cart_id},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def order_teetime(
        self, teetime_iso: str, rate_id: int, cart_id: str, cart_item_id: str, golfer_quantity: int
    ) -> dict:
        response = await self._http.post(
            "/order-teetime",
            json={
                "teetime": teetime_iso,
                "rateId": rate_id,
                "cartId": cart_id,
                "cartItemId": cart_item_id,
                "golferQuantity": golfer_quantity,
            },
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def update_profile(self, profile: dict) -> dict:
        response = await self._http.put("/v2/profile", json=profile, headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    async def get_reservation_token(self) -> str:
        response = await self._http.get("/tr/token", headers=self._auth_headers())
        response.raise_for_status()
        return response.json()

    async def add_reservation(self, form_data: dict) -> httpx.Response:
        # Different host, form-encoded, no session header — see docs/teeitup-api.md step 9.
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post("https://tr.gnsvc.com/AddReservation", data=form_data)
            response.raise_for_status()
            return response

    async def poll_order_status(self, order_id: str, cart_id: str, cart_item_id: str) -> dict:
        response = await self._http.patch(
            f"/order-teetime/status/{order_id}",
            params={"cartId": cart_id, "cartItemId": cart_item_id},
            json={},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def clear_cart(self, cart_id: str) -> None:
        response = await self._http.delete(f"/shopping-cart/{cart_id}", headers=self._auth_headers())
        response.raise_for_status()
