# Reservation Intelligence

A restaurant reservation system with an agentic layer on top: table booking with
real concurrency safety, plus agent skills that assist staff with seating and
promotional decisions inside clearly defined autonomy boundaries.

## Status

Feature-complete for the minimum requirements: database schema, reservation
lifecycle, dynamic pricing, the booking API, all three agent skills, the
Reservation Operations Agent, and a dashboard tying it together.

## Requirements

- Python 3.12+
- No Docker, no external services. SQLite runs as a plain local file.
- A Google Gemini API key, only needed to actually run the agent skills.
  Everything else (booking, pricing, availability) works without one.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # then fill in GOOGLE_API_KEY
```

## Running the app

```bash
uvicorn app.main:app --reload
```

Then open `http://localhost:8000` for the dashboard. On startup, the app
creates the SQLite database (`reservation.db`) if it does not exist yet,
applies the schema, and seeds it with sample data (one restaurant, a few
tables, two users, a couple of menu items) so there is something real to work
against immediately.

## Running the tests

```bash
pytest
```

## Architecture

- `app/database.py`: SQLite connection handling, schema definition, and the
  `transaction()` context manager used everywhere a write needs to be atomic.
- `app/repositories/`: raw data access, one function per operation, no
  business logic. The only place SQL is allowed to live.
- `app/services/`: business rules and transaction boundaries, built on top of
  the repositories. Reservation release (on cancellation or expiry) and
  demand-driven pricing live here.
- `app/routers/`: the FastAPI route handlers, one module per resource, thin,
  they call into services and repositories, never SQL directly.
- `app/skills/`: agent skills. Each one gathers context through the existing
  repositories/services, then makes a single structured-output LLM call to
  reason over it. Skills 1 and 2 only ever suggest, they never mutate
  anything, the caller decides whether to act. Skill 3 is graduated instead
  of binary: a promotional discount within a menu item's pre-approved ceiling
  is created live immediately, above the ceiling it's created pending staff
  approval, that's the only skill that writes to the database itself.
- `app/reservation_agent.py`: the Reservation Operations Agent. Takes a
  plain-language description of a staff situation, binds all three skills to
  an LLM as tools, and lets the LLM decide which one applies. The agent only
  ever decides *which* skill to run, it never mutates anything itself.
- `app/main.py`: the FastAPI app, including a background task that sweeps for
  expired holds on a fixed interval, so a reservation's stored status stays
  accurate without depending on something else happening to read or contend
  for it, and serves the dashboard.
- `app/static/`: the dashboard, plain HTML/CSS/vanilla JS, no build step. The
  agent isn't a separate playground bolted onto the page, it surfaces in
  context: skill 1 appears inline when a booking attempt just failed, skill 2
  appears inline next to a table flagged below its minimum party size, skill
  3 has a direct "recommend a promo" action in the offers section, and a
  free-text panel demonstrates the Reservation Operations Agent's actual
  routing behavior directly.

## API overview

- `GET /restaurants`, `GET /restaurants/{id}/tables`,
  `GET /restaurants/{id}/availability`: browsing.
- `POST /reservations`, `GET /reservations/{id}`,
  `POST /reservations/{id}/confirm`, `POST /reservations/{id}/cancel`: booking
  lifecycle.
- `POST /agent/find-alternatives`: skill 1, suggests an alternative table or
  time after a failed booking attempt.
- `POST /agent/evaluate-min-party-override`: skill 2, evaluates whether to
  seat a party below a table's minimum size, given current demand.
- `POST /agent/recommend-offer`: skill 3, recommends a promotional offer when
  occupancy is low, creating it live or pending staff approval depending on
  whether it's within the menu item's pre-approved discount ceiling.
- `POST /agent/handle`: the Reservation Operations Agent entry point, describe
  a situation in plain language, it decides which skill (if any) applies.
- `GET /restaurants/{id}/menu-items`, `GET /restaurants/{id}/offers`,
  `POST /offers` (staff-created, always live immediately),
  `POST /offers/{id}/approve`, `POST /offers/{id}/reject`: offer management.

### Concurrency model, in short

Reservations are quantized into 15 minute slots. A reservation claims a set of
rows in `slot_claim`, one per slot, with a `UNIQUE(table_id, slot_index, date)`
constraint. Two overlapping bookings can never both succeed, the database
enforces it directly, rather than the application checking availability and
then writing in two separate steps. All of a reservation's slot claims are
inserted inside a single transaction, so a reservation can never end up
partially booked.
