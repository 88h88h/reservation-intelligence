"""FastAPI entrypoint: schema init, sample data, and the background
expiry sweep that keeps a reservation's stored status accurate without
relying on someone happening to read or contend for it.
"""

import asyncio
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import init_db, seed_if_empty
from app.routers import reservations, restaurants
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

app.include_router(reservations.router)
app.include_router(restaurants.router)


@app.exception_handler(sqlite3.IntegrityError)
def integrity_error_handler(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "the requested slots are no longer available"})


@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
