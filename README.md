# tee-time-bot

Automates booking tee times on TeeItUp-powered golf booking sites (e.g. `fairfax-county-mco.book.teeitup.golf`) the instant a booking window opens (typically 7 days ahead, at a fixed time).

See `/Users/chirag/.claude/plans/there-is-this-webiste-polymorphic-blanket.md` for the full project plan, and `docs/teeitup-api.md` for the reverse-engineered TeeItUp/Kenna API this is built against.

## Project structure

```
app/
  main.py              FastAPI app entrypoint — mounts routers, exposes /health
  config.py            Settings loaded from .env (pydantic-settings)
  models.py            Request/response models (BookNowRequest, BookNowResult, TeeTimeSlot, Facility)
  facilities.py         Static facility ID -> course name mapping (MVP scope: two Twin Lakes courses)
  routers/
    bookings.py          POST /bookings/book-now
    tee_times.py          GET /tee-times — currently open/bookable slots
    facilities.py         GET /facilities — supported course IDs/names for UI
  services/
    teeitup_client.py   Thin httpx wrapper around every TeeItUp/Kenna API endpoint
    booking_engine.py   Orchestrates the full booking sequence (login -> lock -> cart -> order -> commit -> poll)
docs/
  teeitup-api.md         Reverse-engineered API reference (endpoints, auth, booking flow)
tests/
  services/               Unit tests for teeitup_client.py and booking_engine.py (HTTP layer mocked)
  routers/                Unit tests for each router (service layer mocked, via FastAPI TestClient)
curls.md                  Raw captured requests from a real booking flow — gitignored, contains real credentials, never commit
.env.example              Template for local secrets
pytest.ini                pytest config (asyncio_mode = auto)
Pipfile / Pipfile.lock    Dependencies (managed with pipenv, not pip/requirements.txt)
```

## Prerequisites

- Python 3.12
- [pipenv](https://pipenv.pypa.io/) (`brew install pipenv` or `pip install pipenv`)

## Setup

```bash
pipenv install
cp .env.example .env
```

Fill in `.env` with your real TeeItUp login:

```
TEEITUP_USERNAME=you@example.com
TEEITUP_PASSWORD=your-password
TEEITUP_SITE_ALIAS=fairfax-county-mco
```

`.env` is gitignored — never commit it.

## Running the server locally

```bash
pipenv run uvicorn app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive docs (Swagger UI) at `http://127.0.0.1:8000/docs` — useful for triggering `POST /bookings/book-now` manually before any frontend exists.

Quick health check:

```bash
curl http://127.0.0.1:8000/health
```

## Running tests

```bash
pipenv run pytest
```

Every router and service function is unit tested with everything outside it mocked (the HTTP layer for `teeitup_client.py`, the `TeeItUpClient` for `booking_engine.py` and the routers) — no network calls, no real TeeItUp credentials needed. Runs with coverage by default (`pytest.ini`); currently 100%.

## Status

Direct-API booking engine verified end-to-end against a real live booking (Twin Lakes Golf Course, Aug 27 2026). `GET /tee-times` and `GET /facilities` are built and unit tested. Next step: the scheduling module (`POST /bookings/schedule`, `GET /bookings`, `GET /bookings/{id}`) so a future booking window can be watched and fired automatically instead of only booking already-open slots.
