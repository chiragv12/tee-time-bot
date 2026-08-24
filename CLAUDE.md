# tee-time-bot

Automates booking tee times on TeeItUp-powered golf booking sites (e.g. `fairfax-county-mco.book.teeitup.golf`) the instant a booking window opens. MVP scope is two Twin Lakes Golf Course facilities on that one site; see `README.md` for project structure and setup, `docs/teeitup-api.md` for the reverse-engineered TeeItUp/Kenna API this is built against, and `/Users/chirag/.claude/plans/there-is-this-webiste-polymorphic-blanket.md` for the full project plan and current phase.

## Stack

- Python 3.12, FastAPI, httpx (async).
- **pipenv and `Pipfile` for dependency management — never `pip`/`requirements.txt`.**
- pytest + pytest-asyncio + pytest-cov for tests (`pipenv run pytest`, coverage on by default via `pytest.ini`).

## Conventions

- **Keep functions small and reusable.** Prefer several small, single-purpose functions over one large one — especially in `services/`, where the booking sequence should stay composed of individually-testable steps rather than one long procedure.
- **Every new function/endpoint needs a unit test**, with everything outside the unit under test mocked (the HTTP layer for `teeitup_client.py` methods; `TeeItUpClient` itself for `booking_engine.py` and the routers). No test should make a real network call or need real credentials. Keep coverage at 100%; if you touch a function that regresses it, add the missing case rather than leaving it.
- **Never fire a request against the real TeeItUp API (including via `book-now`) without asking first.** This is a real booking site with real side effects (reservations, emails/SMS) — always confirm before running a curl or hitting a live endpoint, even for something that looks read-only, unless the user explicitly says to proceed.
- When a real API response confirms or corrects something in `docs/teeitup-api.md` (a field name, a response shape, a missing step), update that doc in the same change — it's meant to stay a reliable reference, not go stale.
- `curls.md` and `.env` are gitignored and contain real credentials/session tokens — never commit them, never print full session tokens/passwords in responses.
