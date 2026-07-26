from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas


def utc_now() -> datetime:
    """
    Return the current UTC time.
    """

    return datetime.now(timezone.utc)


def create_heartbeat(
    db: Session,
    scale: models.Scale,
    request: schemas.HeartbeatRequest,
) -> models.Heartbeat:
    """
    Store a heartbeat and update the scale's current health state.
    """

    observed_at = request.observed_at or utc_now()

    heartbeat = models.Heartbeat(
        scale_id=scale.id,
        status=request.status,
        firmware_version=request.firmware_version,
        adapter_version=request.adapter_version,
        message=request.message,
        metadata_json=request.metadata_json,
        observed_at=observed_at,
    )

    scale.operational_state = request.status
    scale.last_seen_at = observed_at

    db.add(heartbeat)
    db.add(scale)
    db.commit()
    db.refresh(heartbeat)
    db.refresh(scale)

    return heartbeat


def get_heartbeat(
    db: Session,
    heartbeat_id: str,
) -> models.Heartbeat | None:
    """
    Look up one heartbeat by its UUID.
    """

    return (
        db.query(models.Heartbeat)
        .filter(models.Heartbeat.id == heartbeat_id)
        .first()
    )


def get_latest_heartbeat(
    db: Session,
    scale_id: str,
) -> models.Heartbeat | None:
    """
    Return the newest heartbeat recorded for a scale.
    """

    return (
        db.query(models.Heartbeat)
        .filter(models.Heartbeat.scale_id == scale_id)
        .order_by(
            models.Heartbeat.observed_at.desc(),
            models.Heartbeat.received_at.desc(),
        )
        .first()
    )


def list_heartbeats(
    db: Session,
    scale_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Heartbeat]:
    """
    Return a page of stored heartbeats.

    Results are ordered newest first.
    """

    query = db.query(models.Heartbeat)

    if scale_id is not None:
        query = query.filter(
            models.Heartbeat.scale_id == scale_id
        )

    if status is not None:
        query = query.filter(
            models.Heartbeat.status == status
        )

    return (
        query
        .order_by(
            models.Heartbeat.observed_at.desc(),
            models.Heartbeat.received_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_heartbeats(
    db: Session,
    scale_id: str | None = None,
    status: str | None = None,
) -> int:
    """
    Count heartbeats using the same filters as list_heartbeats.
    """

    query = db.query(func.count(models.Heartbeat.id))

    if scale_id is not None:
        query = query.filter(
            models.Heartbeat.scale_id == scale_id
        )

    if status is not None:
        query = query.filter(
            models.Heartbeat.status == status
        )

    return int(query.scalar() or 0)
