# Reservation Intelligence

A restaurant reservation system with an agentic layer on top: table booking with
real concurrency safety, plus agent skills that assist staff with seating and
promotional decisions inside clearly defined autonomy boundaries.

## Status

Work in progress, built incrementally. What exists so far: the database schema,
the reservation lifecycle, dynamic pricing, the booking API, and the first
agent skill (finding alternatives after a failed booking). Still to come: the
remaining agent skills and the dashboard.

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

On startup, the app creates the SQLite database (`reservation.db`) if it does
not exist yet, applies the schema, and seeds it with sample data (one
restaurant, a few tables, two users, a couple of menu items) so there is
something real to work against immediately.

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
  reason over it. Suggestion only, no skill books, cancels, or otherwise
  mutates anything itself, the caller decides whether to act on it.
- `app/main.py`: the FastAPI app, including a background task that sweeps for
  expired holds on a fixed interval, so a reservation's stored status stays
  accurate without depending on something else happening to read or contend
  for it.

## API overview

- `GET /restaurants`, `GET /restaurants/{id}/tables`,
  `GET /restaurants/{id}/availability`: browsing.
- `POST /reservations`, `GET /reservations/{id}`,
  `POST /reservations/{id}/confirm`, `POST /reservations/{id}/cancel`: booking
  lifecycle.
- `POST /agent/find-alternatives`: agent skill 1, suggests an alternative
  table or time after a failed booking attempt.

### Concurrency model, in short

Reservations are quantized into 15 minute slots. A reservation claims a set of
rows in `slot_claim`, one per slot, with a `UNIQUE(table_id, slot_index, date)`
constraint. Two overlapping bookings can never both succeed, the database
enforces it directly, rather than the application checking availability and
then writing in two separate steps. All of a reservation's slot claims are
inserted inside a single transaction, so a reservation can never end up
partially booked.
