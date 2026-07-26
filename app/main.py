from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from app import models
from app.database import Base, engine
from app.routers import readings, scales, sessions


SERVICE_NAME = "SageWire Scale Service"
SERVICE_SLUG = "sagewire-scale"
SERVICE_VERSION = "0.1.0"
SERVICE_DESCRIPTION = (
    "Standalone SageWire service for scale registration, "
    "heartbeats, weighing sessions, raw readings, stability "
    "evaluation, and accepted weight events."
)


def utc_now() -> datetime:
    """
    Return the current UTC time.
    """

    return datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize service resources when FastAPI starts.

    For version 0.1.0, SQLAlchemy creates any database tables
    that do not already exist.
    """

    Base.metadata.create_all(bind=engine)

    app.state.started_at = utc_now()

    yield


app = FastAPI(
    title=SERVICE_NAME,
    description=SERVICE_DESCRIPTION,
    version=SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.include_router(scales.router)
app.include_router(sessions.router)
app.include_router(readings.router)


@app.get(
    "/",
    summary="Service root",
)
def root() -> dict[str, Any]:
    """
    Return a basic description of the running service.
    """

    return {
        "service": SERVICE_NAME,
        "service_slug": SERVICE_SLUG,
        "version": SERVICE_VERSION,
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    summary="Health check",
)
def health() -> dict[str, Any]:
    """
    Return the current health of the API process.
    """

    started_at = getattr(
        app.state,
        "started_at",
        None,
    )

    return {
        "service": SERVICE_NAME,
        "status": "ok",
        "version": SERVICE_VERSION,
        "started_at": started_at,
        "checked_at": utc_now(),
    }


@app.get(
    "/version",
    summary="Service version",
)
def version() -> dict[str, str]:
    """
    Return the current service version.
    """

    return {
        "service": SERVICE_NAME,
        "service_slug": SERVICE_SLUG,
        "version": SERVICE_VERSION,
    }


@app.get(
    "/info",
    summary="Service information",
)
def info() -> dict[str, Any]:
    """
    Describe the service and its principal capabilities.
    """

    return {
        "service": SERVICE_NAME,
        "service_slug": SERVICE_SLUG,
        "version": SERVICE_VERSION,
        "description": SERVICE_DESCRIPTION,
        "database": {
            "engine": "SQLAlchemy",
            "default_backend": "SQLite",
        },
        "capabilities": [
            "scale registration",
            "scale heartbeat history",
            "operational-state tracking",
            "weighing sessions",
            "raw-reading preservation",
            "pound and kilogram normalization",
            "reading validation",
            "window-based stability evaluation",
            "accepted weight events",
            "duplicate-event detection",
            "RFID association",
            "evidence hashing",
        ],
        "routes": {
            "documentation": "/docs",
            "openapi": "/openapi.json",
            "scales": "/scales",
            "sessions": "/sessions",
            "readings": "/readings",
            "weight_events": "/readings/events",
        },
    }
