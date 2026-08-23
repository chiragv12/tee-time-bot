import logging

from app.config import settings
from app.models import BookNowRequest, BookNowResult
from app.services.teeitup_client import TeeItUpClient

logger = logging.getLogger(__name__)

# Hardcoded from the one real capture (curls.md) — /tr/token doesn't return this,
# scope (per-facility vs per-site) unconfirmed. Revisit if a second course differs.
INVENTORY_CHANNEL_ID = 20972


async def book_now(request: BookNowRequest) -> BookNowResult:
    """Runs the full lock -> cart -> order -> commit sequence for one known slot.

    Sequence and endpoint shapes: docs/teeitup-api.md. The lock step is fired first
    since it's the actual point of contention in an open-time race. On any failure
    after the lock is acquired, we best-effort release the lock/cart so a retry
    (ours or anyone else's) isn't blocked by a slot we're not actually holding onto.
    """
    client = TeeItUpClient()
    locked = False
    cart_id: str | None = None
    try:
        await client.login()
        customer = client.customer
        if not customer.get("phoneNumbers"):
            return BookNowResult(success=False, detail="TeeItUp account has no phone number on file")

        # Mirrors clicking "Choose Rate" in the real flow (curls.md:88) — likely registers a
        # price/rate override server-side that add_reservation later expects to find; skipping
        # this previously produced "Unable to find stored override reference" from AddReservation.
        invoice = await client.get_rate_invoice(request.rate_id, request.gnc_facility_id, request.player_count)
        logger.debug("rate_invoice response: %s", invoice)

        lock = await client.lock_tee_time(request.course_id, request.local_date, request.local_time)
        locked = True
        logger.info("locked slot for %s %s", request.local_date, request.local_time)
        logger.debug("lock response: %s", lock)

        cart = await client.create_cart()
        cart_id = cart["id"]
        logger.info("created cart %s", cart_id)

        item = {
            "facilityId": request.facility_id,
            "type": "TeeTime",
            "extra": {
                "teetime": request.teetime_iso,
                "players": request.player_count,
                "groupSize": request.player_count,
                "isPnasSelected": False,
                "price": request.price,
                "rate": {
                    "holes": request.holes,
                    "price": request.price,
                    "rateId": request.rate_id,
                    "rateSetId": request.gnc_facility_id,
                    "name": f"{request.holes} Holes",
                    "transactionFees": 0,
                    "transportation": request.transportation,
                    "isSimulator": False,
                },
                "productLineups": [],
                "slots": [],
            },
        }
        cart = await client.add_to_cart(cart_id, item)
        cart_item_id = cart["items"][-1]["id"]
        logger.info("added cart item %s", cart_item_id)

        # NOTE: exact "not bookable" shape is unverified (we only captured a bookable
        # response). Checking both common key names defensively; if neither is present
        # we assume bookable rather than block on speculation.
        bookable = await client.is_bookable(cart_id, cart_item_id)
        logger.debug("is_bookable response: %s", bookable)
        if bookable.get("bookable", bookable.get("isBookable", True)) is False:
            return BookNowResult(success=False, detail="Slot is no longer bookable (lost the race)")

        order_created = await client.create_order(cart_id)
        logger.debug("create_order response: %s", order_created)
        order = await client.order_teetime(
            request.teetime_iso, request.rate_id, cart_id, cart_item_id, request.golfer_quantity
        )
        order_id = order["id"]
        # The server issues its own reference for this teetime's invoice — AddReservation's
        # "Unable to find stored override reference" happened because we sent a fresh random
        # UUID instead of this one. Must match exactly what order_teetime stored server-side.
        reference_id = order["teetimes"][0]["players"][0]["invoice"]["referenceId"]
        logger.info("created order %s", order_id)
        logger.debug("order_teetime response: %s", order)

        # Mirrors clicking "Complete Purchase" in the real flow (curls.md:588-611) — associates
        # the profile with this facility. Previously skipped; suspected root cause of
        # AddReservation's "Unable to find stored override reference" failure.
        profile_response = await client.update_profile(
            {
                "emailAddress": customer["username"],
                "profileDetails": {
                    "firstName": customer["name"]["given"],
                    "lastName": customer["name"]["family"],
                    "phoneNumber": customer["phoneNumbers"][0]["value"],
                    "facilities": [
                        {
                            "gnFacilityId": request.facility_id,
                            "marketing": {"emailOptIn": False, "smsOptIn": False},
                            "transactional": {"smsOptIn": False},
                        }
                    ],
                },
            }
        )
        logger.debug("update_profile response: %s", profile_response)

        # /tr/token returns just the token as a bare JSON string (confirmed via real capture).
        # TeeTime.InventoryChannelID isn't part of that response — it was a hardcoded 20972
        # in our one real capture (curls.md), scope (per-facility vs per-site) unconfirmed.
        reservation_token = await client.get_reservation_token()
        add_reservation_response = await client.add_reservation(
            {
                "TeeTime.InventoryChannelID": INVENTORY_CHANNEL_ID,
                "TeeTime.FacilityID": request.facility_id,
                "TeeTime.TeeTimeRateID": request.rate_id,
                "TeeTime.PlayerCount": request.player_count,
                "TeeTime.GroupSize": request.player_count,
                "TeeTime.Amount": -1,
                "TeeTime.ReferenceID": reference_id,
                "Reservation.CustomerEmail": customer["username"],
                "SelectedCourses": request.facility_id,
                "ENGINE": "5.0",
                "ALIAS": settings.teeitup_site_alias,
                "Reservation.TrackingCode": "TL:",
                "tl.holes": request.holes,
                "EmailCampaignId": "",
                "PaymentReturnURL": f"https://{settings.teeitup_site_alias}.book.teeitup.golf/payment-authorization",
                "Payment.Name": customer["name"]["formatted"],
                "bookerFirstName": customer["name"]["given"],
                "bookerLastName": customer["name"]["family"],
                "Payments_1_CreditCard_NameOnCard": customer["name"]["formatted"].upper(),
                "BookerEmail": customer["username"],
                "Payment.Address.Line1": "",
                "Payment.Address.PostalCode": "",
                "Payment.Address.Country": "",
                "tl.customerMobile": customer["phoneNumbers"][0]["value"],
                "Payment.PhoneNumber": customer["phoneNumbers"][0]["value"],
                "Token": reservation_token,
            }
        )
        add_reservation_body = add_reservation_response.json()
        logger.debug(
            "add_reservation response: status=%s url=%s body=%s",
            add_reservation_response.status_code,
            add_reservation_response.url,
            add_reservation_body,
        )
        if not add_reservation_body.get("Success"):
            return BookNowResult(
                success=False,
                detail=f"AddReservation did not succeed: {add_reservation_body.get('Message')}",
            )

        # The reservation is already committed at this point — this final status sync is
        # best-effort polish, not part of whether the booking happened. A failure here
        # shouldn't be reported as a failed booking.
        try:
            await client.poll_order_status(order_id, cart_id, cart_item_id)
        except Exception:
            logger.warning("poll_order_status failed after a successful reservation", exc_info=True)

        return BookNowResult(success=True, order_id=order_id, detail="Booked successfully")
    except Exception as exc:
        logger.exception("book_now failed")
        return BookNowResult(success=False, detail=f"{type(exc).__name__}: {exc}")
    finally:
        await _cleanup(client, request, locked, cart_id)
        await client.aclose()


async def _cleanup(client: TeeItUpClient, request: BookNowRequest, locked: bool, cart_id: str | None) -> None:
    """Best-effort release of the lock/cart so a failed attempt doesn't block retries."""
    if locked:
        try:
            await client.unlock_tee_time(request.course_id, request.teetime_iso)
        except Exception:
            logger.exception("Failed to release tee-time lock during cleanup")
    if cart_id:
        try:
            await client.clear_cart(cart_id)
        except Exception:
            logger.exception("Failed to clear cart during cleanup")
