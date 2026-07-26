from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas


def utc_now() -> datetime:
    """
    Return the current UTC time.
    """

    return datetime.now(timezone.utc)


def get_session(
    db: Session,
    session_id: str,
) -> models.WeighingSession | None:
    """
    Look up one weighing session by its UUID.
    """

    return (
        db.query(models.WeighingSession)
        .filter(models.WeighingSession.id == session_id)
        .first()
    )


def get_session_by_key(
    db: Session,
    session_key: str,
) -> models.WeighingSession | None:
    """
    Look up a weighing session using its optional unique session key.
    """

    return (
        db.query(models.WeighingSession)
        .filter(models.WeighingSession.session_key == session_key)
        .first()
    )


def get_open_session_for_scale(
    db: Session,
    scale_id: str,
) -> models.WeighingSession | None:
    """
    Return the newest open session for a scale.

    The database does not currently forbid multiple open sessions,
    but the service can use this helper to enforce that rule.
    """

    return (
        db.query(models.WeighingSession)
        .filter(
            models.WeighingSession.scale_id == scale_id,
            models.WeighingSession.status == "OPEN",
        )
        .order_by(
            models.WeighingSession.opened_at.desc(),
            models.WeighingSession.created_at.desc(),
        )
        .first()
    )


def create_session(
    db: Session,
    request: schemas.SessionCreateRequest,
) -> tuple[models.WeighingSession, bool]:
    """
    Open a weighing session.

    If a matching session_key already exists, return the existing
    session instead of creating a duplicate.

    Returns:
        (session, created)
    """

    if request.session_key is not None:
        existing = get_session_by_key(
            db,
            request.session_key,
        )

        if existing is not None:
            return existing, False

    session = models.WeighingSession(
        scale_id=request.scale_id,
        session_key=request.session_key,
        name=request.name,
        status="OPEN",
        location_id=request.location_id,
        opened_by=request.opened_by,
        notes=request.notes,
        metadata_json=request.metadata_json,
        opened_at=request.opened_at or utc_now(),
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session, True


def close_session(
    db: Session,
    session: models.WeighingSession,
    request: schemas.SessionCloseRequest,
) -> tuple[models.WeighingSession, bool]:
    """
    Close an open weighing session.

    If the session is already closed, return it unchanged.

    Returns:
        (session, closed_now)
    """

    if session.status == "CLOSED":
        return session, False

    session.status = "CLOSED"
    session.closed_by = request.closed_by
    session.closed_at = request.closed_at or utc_now()

    if request.notes is not None:
        session.notes = request.notes

    db.add(session)
    db.commit()
    db.refresh(session)

    return session, True


def list_sessions(
    db: Session,
    scale_id: str | None = None,
    status: str | None = None,
    location_id: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[models.WeighingSession]:
    """
    Return a page of weighing sessions.

    Results are ordered newest first.
    """

    query = db.query(models.WeighingSession)

    if scale_id is not None:
        query = query.filter(
            models.WeighingSession.scale_id == scale_id
        )

    if status is not None:
        query = query.filter(
            models.WeighingSession.status == status
        )

    if location_id is not None:
        query = query.filter(
            models.WeighingSession.location_id == location_id
        )

    return (
        query
        .order_by(
            models.WeighingSession.opened_at.desc(),
            models.WeighingSession.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_sessions(
    db: Session,
    scale_id: str | None = None,
    status: str | None = None,
    location_id: str | None = None,
) -> int:
    """
    Count weighing sessions using the same filters as list_sessions.
    """

    query = db.query(
        func.count(models.WeighingSession.id)
    )

    if scale_id is not None:
        query = query.filter(
            models.WeighingSession.scale_id == scale_id
        )

    if status is not None:
        query = query.filter(
            models.WeighingSession.status == status
        )

    if location_id is not None:
        query = query.filter(
            models.WeighingSession.location_id == location_id
        )

    return int(query.scalar() or 0)
