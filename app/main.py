"""FastAPI entrypoint: schema init, sample data, and the background
expiry sweep that keeps a reservation's stored status accurate without
relying on someone happening to read or contend for it.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db, seed_if_empty
from app.services.reservation_service import release_expired_reservations

SWEEP_INTERVAL_SECONDS = 30


async def _expiry_sweep_loop() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        release_expired_reservations()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_if_empty()
    sweep_task = asyncio.create_task(_expiry_sweep_loop())
    yield
    sweep_task.cancel()


app = FastAPI(title="Reservation Intelligence", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
