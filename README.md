# tee-time-bot

Automates booking tee times on TeeItUp-powered golf booking sites (e.g. `fairfax-county-mco.book.teeitup.golf`) the instant a booking window opens (typically 7 days ahead, at a fixed time).

See `/Users/chirag/.claude/plans/there-is-this-webiste-polymorphic-blanket.md` for the full project plan, and `docs/teeitup-api.md` for the reverse-engineered TeeItUp/Kenna API this is built against.

## Project structure

```
app/
  main.py              FastAPI app entrypoint — mounts routers, exposes /health
  config.py            Settings loaded from .env (pydantic-settings)
  models.py            Request/response models (BookNowRequest, BookNowResult, ...)
  routers/
    bookings.py         API routes under /bookings
  services/
    teeitup_client.py   Thin httpx wrapper around every TeeItUp/Kenna API endpoint
    booking_engine.py   Orchestrates the full booking sequence (login -> lock -> cart -> order -> commit -> poll)
docs/
  teeitup-api.md         Reverse-engineered API reference (endpoints, auth, booking flow)
tests/                    (empty for now)
curls.md                  Raw captured requests from a real booking flow — gitignored, contains real credentials, never commit
.env.example              Template for local secrets
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

## Status

Direct-API booking engine verified end-to-end against a real live booking (Twin Lakes Golf Course, Aug 27 2026). Next steps: the search-response parsing needed to feed `rate_id`/`gnc_facility_id`/`price` into a scheduled booking automatically (currently supplied manually to `/bookings/book-now`), and the scheduling module itself.
