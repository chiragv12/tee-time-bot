# tee-time-bot

Automates booking tee times on TeeItUp-powered golf booking sites (e.g. `fairfax-county-mco.book.teeitup.golf`) the instant a booking window opens (typically 7 days ahead, at a fixed time).

See `/Users/chirag/.claude/plans/there-is-this-webiste-polymorphic-blanket.md` for the full project plan, and `docs/teeitup-api.md` for the reverse-engineered TeeItUp/Kenna API this is built against.

## Project structure

```
app/
  main.py              FastAPI app entrypoint — mounts routers, exposes /health
  config.py            Settings loaded from .env (pydantic-settings)
  models.py            Request/response models (BookNowRequest, ScheduleRequest, ScheduledBooking, TeeTimeSlot, ...)
  facilities.py         Static facility ID -> course name mapping (MVP scope: two Twin Lakes courses) + site timezone
  db.py / orm.py        Async SQLAlchemy engine/session and the `bookings` table (SQLite locally, Postgres when hosted)
  repository.py         Small DB functions over the bookings table
  routers/
    bookings.py          POST /bookings/book-now, POST /bookings/schedule, GET /bookings, GET/DELETE /bookings/{id}
    tee_times.py          GET /tee-times — currently open/bookable slots
    facilities.py         GET /facilities — supported course IDs/names for UI
  services/
    teeitup_client.py   Thin httpx wrapper around every TeeItUp/Kenna API endpoint
    booking_engine.py   Orchestrates the full booking sequence (login -> lock -> cart -> order -> commit -> poll)
    tee_time_search.py  Search + reduce results to bookable slots, match a slot to criteria (shared by /tee-times and the scheduler)
    schedule_timing.py  When a window opens (9pm ET), when to wake, when to give up
    scheduler.py        APScheduler wake-ups: wait for the window, poll for the slot, hand it to book_now()
docs/
  teeitup-api.md         Reverse-engineered API reference (endpoints, auth, booking flow)
tests/
  services/               Unit tests for the services (HTTP layer / TeeItUpClient / repository mocked)
  routers/                Unit tests for each router (service layer mocked, via FastAPI TestClient)
curls.md                  Raw captured requests from a real booking flow — gitignored, contains real credentials, never commit
.env.example              Template for local secrets
pytest.ini                pytest config (asyncio_mode = auto)
Pipfile / Pipfile.lock    Dependencies (managed with pipenv, not pip/requirements.txt)
```

## Running locally

Everything runs on your machine with two commands: no Docker, no database to install, no compose file. The API is a plain `uvicorn` process, and scheduled bookings live in a SQLite file the app creates itself.

### Prerequisites

- Python 3.12
- [pipenv](https://pipenv.pypa.io/) (`brew install pipenv` or `pip install pipenv`)

### First-time setup

```bash
pipenv install --dev      # app + test dependencies
cp .env.example .env      # then fill in your TeeItUp login
```

### Configuration

Settings come from `.env` (gitignored, never commit it) or real environment variables. Restart the server after changing it; `--reload` only watches Python files.

| Variable | Default | What it does |
|---|---|---|
| `TEEITUP_USERNAME` | *required* | TeeItUp login email |
| `TEEITUP_PASSWORD` | *required* | TeeItUp login password |
| `TEEITUP_SITE_ALIAS` | `fairfax-county-mco` | Which TeeItUp site to book on |
| `SUPPORTED_FACILITY_IDS` | `7743,7756` | Facilities `GET /tee-times` searches by default |
| `DATABASE_URL` | `sqlite+aiosqlite:///./tee_time_bot.db` | Where scheduled bookings are stored (see below) |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs every raw TeeItUp response and HTTP frame, which is very noisy while polling |
| `WAKE_LEAD_SECONDS` | `30` | How long before the window opens the scheduler wakes up |
| `SEARCH_WINDOW_MINUTES` | `10` | How long after the window opens to keep searching before giving up (`terminated`) |

The database path is relative to the directory you start the server from, so **start it from the repo root** or you'll get a second, empty `tee_time_bot.db` somewhere else. For Neon Postgres later, set `DATABASE_URL=postgresql+asyncpg://user:password@host/dbname` and `pipenv install asyncpg`.

### Start the server

While developing, with auto-reload:

```bash
pipenv run uvicorn app.main:app --reload
```

The API is at `http://127.0.0.1:8000`, interactive docs (Swagger UI) at `http://127.0.0.1:8000/docs`, and a health check at `/health`.

**To leave it running unattended (e.g. overnight so a real 9pm window fires):**

```bash
caffeinate -i pipenv run uvicorn app.main:app 2>&1 | tee -a server.log
```

- **No `--reload`.** A reload restarts the process, and anything mid-search at that moment is marked `failed` rather than re-run.
- **Exactly one process.** Never pass `--workers`; each worker would run its own scheduler and every booking would fire more than once.
- **`caffeinate -i`** keeps the Mac awake. A sleeping laptop misses the wake-up and the window with it.
- Keep `LOG_LEVEL=INFO`.

### Try it in Swagger UI

Open `http://127.0.0.1:8000/docs`, expand an endpoint, and press **Try it out**:

1. `GET /facilities` lists the supported courses and their ids.
2. `GET /tee-times` with a `date` shows what's open right now. This is read-only but does call TeeItUp live.
3. `POST /bookings/schedule` schedules a booking; pick one of the example payloads from the dropdown.
4. `GET /bookings/{id}` shows its status; `GET /bookings` lists all of them.
5. `DELETE /bookings/{id}` cancels one that's still `pending`.

`POST /bookings/book-now` and a `schedule` that finds its slot both **make real reservations** on your TeeItUp account.

### Example payloads

Example payloads live in Swagger UI itself, generated from the code so they can't drift from the API (a test checks that every example validates):

- Each `POST` endpoint has a dropdown of named request examples (e.g. "9 holes, walking, just me", "18 holes, cart, foursome"). The schedule examples use a date 10 days out so **Execute** is never rejected as being in the past.
- Every response, and every error status, shows an example and a description.
- `http://127.0.0.1:8000/openapi.json` is the raw machine-readable spec.

For `book-now`, don't write the body by hand: take an entry from `GET /tee-times`, which already has every field it needs.

### What to expect in the logs

For a scheduled booking you'll see this sequence (`LOG_LEVEL=INFO`):

```
INFO app.services.scheduler: booking 8f42fcd0-...: will wake at 2026-10-04 01:59:30+00:00 (window opens 2026-10-04 02:00:00+00:00)
INFO app.services.scheduler: booking 8f42fcd0-...: logged in, waiting for the window to open at 2026-10-04 02:00:00+00:00
INFO app.services.scheduler: booking 8f42fcd0-...: window open, searching until 2026-10-04 02:10:00+00:00
INFO app.services.scheduler: booking 8f42fcd0-...: found 2026-10-12 15:20 (rate 235361805), booking it
INFO app.services.scheduler: booking 8f42fcd0-...: booked - Booked successfully
```

If the slot never appears, the last two lines become `slot never appeared, terminating`. A `WARNING ... slot search failed` line is one failed poll; the next poll retries it.

### Checking results, and resetting

```bash
curl -s http://127.0.0.1:8000/bookings                                   # everything, newest first
sqlite3 tee_time_bot.db "select id, status, detail from bookings;"       # straight from the DB
```

To wipe all scheduled bookings: stop the server and `rm tee_time_bot.db` (it's recreated on the next start).

### Troubleshooting

- **`Address already in use`**: something is on port 8000. Use `--port 8001`, or stop the other process.
- **Nothing happened at 9pm**: check `GET /bookings`. `pending` means the wake-up never fired (laptop asleep, or the server was down; a restart re-arms pending bookings unless their search window already passed, in which case they become `terminated`).
- **`book-now` returns 500**: the body's `detail` says which step failed; the server log has the full traceback.
- **Booking is `failed` with "Interrupted by a server restart"**: the server died or reloaded mid-search. A reservation may have gone through, so check TeeItUp before scheduling again.

## Scheduling a booking

`POST /bookings/schedule` takes what you want (facility, date, a time window, holes, walking/cart, players), not slot IDs, since those only exist once the slot is open:

```json
{"facility_id": 7743, "local_date": "2026-10-03", "earliest_time": "14:00", "latest_time": "16:00", "holes": 9, "transportation": "Walking", "player_count": 1}
```

`earliest_time` and `latest_time` are site local (Eastern) time, both inclusive; use the same value for one exact time. The server records it, then wakes 30s before the booking window opens (9pm ET, 8 days ahead), logs in, searches every second, and books the **earliest open slot inside your time window** the moment one appears (via `book_now()`). If nothing in your window has shown up 10 minutes after the booking window opens, it stops and marks the booking `terminated`. If the window is already open when you schedule, it starts immediately.

Statuses: `pending` → `searching` → `booked` / `failed` (found a slot, the booking attempt failed) / `terminated` (never appeared) / `cancelled`. `GET /bookings/{id}` shows where one is, `DELETE /bookings/{id}` cancels a `pending` one. Bookings live in the database, so they survive restarts; after a restart, pending ones are re-armed and any that were mid-search are marked `failed` (not retried — a reservation may already have gone through, so check TeeItUp).

## Running tests

```bash
pipenv run pytest
```

Every router and service function is unit tested with everything outside it mocked (the HTTP layer for `teeitup_client.py`, the `TeeItUpClient` for `booking_engine.py` and the routers) — no network calls, no real TeeItUp credentials needed. Runs with coverage by default (`pytest.ini`); currently 100%.

## Status

Direct-API booking engine verified end-to-end against a real live booking (Twin Lakes Golf Course, Aug 27 2026). `GET /tee-times`, `GET /facilities` and the scheduling module (`/bookings/schedule`, `GET /bookings`, `GET|DELETE /bookings/{id}`) are built and unit tested. The scheduler has been smoke-tested locally (persistence, restart re-arming, cancel) but has not yet fired against the live TeeItUp site at a real window open. Next: that live dry run, then deploying to Render + Neon.
