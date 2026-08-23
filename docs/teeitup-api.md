# TeeItUp API reference (reverse-engineered)

Captured 2026-08-22 from `fairfax-county-mco.book.teeitup.golf`, booking Twin Lakes Golf Course - Lakes Course.
Source: manual DevTools capture during a real login + booking flow (see local, gitignored `curls.md` for raw requests — never commit that file, it contains real credentials/session tokens).

The site frontend (`*.book.teeitup.golf`) is a Next.js app behind Cloudflare. The actual booking backend lives on a **different host**, `phx-api-be-east-1b.kenna.io` ("Kenna" — the platform TeeItUp is built on), which had **no CAPTCHA, no CSRF token, and no Cloudflare challenge** on any call observed. This is good news for the direct-HTTP fast path.

`x-be-alias: fairfax-county-mco` on every API call identifies which course network/site you're operating against — this is presumably how the same API backs every `*.book.teeitup.golf` site (relevant for the "other TeeItUp sites" future-items goal).

## Auth

```
POST https://phx-api-be-east-1b.kenna.io/profile/authenticate
Content-Type: application/json

{"username": "<email>", "credentials": "<password>", "type": "basic"}
```

Returns:
```json
{
  "sessionToken": "Fe26.2**...",
  "customer": { "id": "...", "name": {...}, "facilityCustomers": {...} }
}
```

`sessionToken` is a Hapi `iron`-sealed token. It's sent on every subsequent API call as a **custom header**, not a cookie:
```
session: Fe26.2**...
```
(The frontend Next.js pages separately store the same value in a `phxprofile` cookie, but that's only relevant for server-rendered page navigation, not the API calls we care about.)

**Open question (Phase 0 follow-up)**: exact token lifetime unknown — need to observe over a few days whether it survives long enough to avoid re-login before a scheduled booking.

## Search

```
GET https://phx-api-be-east-1b.kenna.io/v2/tee-times?date=YYYY-MM-DD&facilityIds=7743,7756&returnPromotedRates=true
session: <sessionToken>
```

`facilityIds` maps to the `course=` query param on the frontend URL — multiple courses can be searched in one call.

## Booking flow (in the order the UI triggers them)

1. **Get rate/pricing** (fired per visible slot, essentially a price lookup):
   ```
   GET /tee-times/rate/{rateId}/invoice?gncFacilityId={rateSetId}&playerCount={n}
   ```

2. **Lock the slot** — this is the real point of contention in an open-time race; whoever locks first wins:
   ```
   GET /course/{courseId}/tee-time/locks?localDate=YYYY-MM-DD&localTime=HH:MM
   ```
   (`courseId` here is a different, longer Mongo-style ID than `facilityIds`/`gncFacilityId` — need a mapping table per course.)

3. **Create a cart** (empty body, `Content-Length: 0`):
   ```
   POST /shopping-cart
   ```
   Returns a new `cartId`.

4. **Add to cart**:
   ```
   POST /shopping-cart/{cartId}/cart-item
   {"item": {"facilityId": 7743, "type": "TeeTime", "extra": {"teetime": "...", "players": 1, "rate": {...}, ...}}}
   ```
   Response is the **full cart object**, not just the new item — the top-level `id` is the *cart* id (same as `cartId`), and the item's own id is nested:
   ```json
   {"id": "<cartId>", "items": [{"id": "<cartItemId>", "facilityId": 7743, "extra": {...}}]}
   ```
   `cartItemId` = `response["items"][-1]["id"]`.

5. **Validate bookability**:
   ```
   POST /shopping-cart/{cartId}/cart-item/{cartItemId}/is-bookable
   {"reservationCountsByTime": {}}
   ```

6. **Create order from cart**:
   ```
   POST /orders
   {"language": "en", "cartId": "..."}
   ```

7. **Commit the reservation**:
   ```
   POST /order-teetime
   {"teetime": "...", "rateId": ..., "cartId": "...", "cartItemId": "...", "golferQuantity": 1}
   ```
   Response includes `teetimes[0].players[0].invoice.referenceId` — a server-issued reference for this specific invoice. **This must be sent as `TeeTime.ReferenceID` in step 9's `AddReservation` call.** A client-generated UUID there produces `{"Success":false,"Message":"Unable to find stored override reference"}` — confirmed via real testing.

   Also fire `PUT /v2/profile` after this step (mirrors "Complete Purchase" in the real flow, `curls.md:588-611`) — associates the customer profile with the facility being booked. Payload: `{"emailAddress", "profileDetails": {"firstName", "lastName", "phoneNumber", "facilities": [{"gnFacilityId", "marketing": {...}, "transactional": {...}}]}}`.

8. **Get a one-time payment/reservation token**:
   ```
   GET /tr/token
   ```
   Response is just the token as a bare JSON string, e.g. `"498da587-a3a6-4057-85eb-ee42f73f182a"` — confirmed via real capture. `TeeTime.InventoryChannelID` (step 9) is *not* part of this response; it was a hardcoded `20972` in our capture, origin/scope still unconfirmed.

9. **Legacy reservation commit** (different host, form-encoded, no `session` header — uses the one-time `Token` from step 8 instead):
   ```
   POST https://tr.gnsvc.com/AddReservation
   Content-Type: application/x-www-form-urlencoded

   TeeTime.InventoryChannelID=...&TeeTime.FacilityID=...&TeeTime.TeeTimeRateID=...&TeeTime.PlayerCount=...
   &TeeTime.Amount=-1&Reservation.CustomerEmail=...&Payment.Name=...&PaymentReturnURL=.../payment-authorization&Token=...
   ```
   `TeeTime.Amount=-1` and empty `Payment.Address.*` fields in our capture — consistent with "no card charged at booking time."

10. **Poll/confirm status**:
    ```
    PATCH /order-teetime/status/{orderId}?cartId=...&cartItemId=...
    {}
    ```
    Confirmed via real testing: this returned `400` even after a fully successful booking (reservation confirmed in the account, `AddReservation` returned `Success: true`). Treat this as best-effort/non-critical — success is determined by step 9's `Success` field, not this call.

11. **Cleanup** (release lock, clear cart — fired after success):
    ```
    DELETE /course/{courseId}/tee-time/lock
    {"teetime": "..."}

    DELETE /shopping-cart/{cartId}
    ```

## Noise to ignore
Requests to `browser-intake-datadoghq.com` (Datadog RUM), `events.launchdarkly.com` (feature flags), and Google Analytics (`_ga*`) are analytics/telemetry only — not part of the booking flow, safe to ignore when building the client.

## Implications for the booking engine
- The API is clean enough that the **fast path (direct `httpx` calls) is very viable** as primary — no CAPTCHA/CSRF observed. This reduces reliance on the Playwright fallback for the happy path, though we should still keep Playwright as the fallback for when TeeItUp changes something or blocks unusual traffic patterns.
- The **lock endpoint (step 2) is the real race** — the booking engine should fire the lock call immediately when the window opens, before doing anything else, then proceed through the rest of checkout once the lock succeeds.
- Still need to confirm: session token lifetime, and whether hitting these endpoints outside business/open hours behaves differently (e.g. does `/tee-times/rate/.../invoice` or the lock endpoint 403/404 before a slot opens, or just return empty — this determines whether we can "pre-warm" a request).
