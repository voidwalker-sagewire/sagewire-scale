from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import schemas
from app.crud import events, readings, scales, sessions
from app.database import get_db
from app.services import stability


router = APIRouter(
    prefix="/readings",
    tags=["Readings"],
)


def resolve_scale(
    db: Session,
    scale_reference: str,
):
    """
    Resolve a scale using either:

    - its internal UUID, or
    - its human-readable scale_key.
    """

    scale = scales.get_scale(
        db=db,
        scale_id=scale_reference,
    )

    if scale is not None:
        return scale

    return scales.get_scale_by_key(
        db=db,
        scale_key=scale_reference,
    )


def resolve_session(
    db: Session,
    session_reference: str,
):
    """
    Resolve a weighing session using either:

    - its internal UUID, or
    - its optional session_key.
    """

    weighing_session = sessions.get_session(
        db=db,
        session_id=session_reference,
    )

    if weighing_session is not None:
        return weighing_session

    return sessions.get_session_by_key(
        db=db,
        session_key=session_reference,
    )


def resolve_optional_session(
    db: Session,
    session_reference: str | None,
    scale_id: str,
):
    """
    Resolve an optional session and verify that it belongs
    to the supplied scale.
    """

    if session_reference is None:
        return None

    weighing_session = resolve_session(
        db=db,
        session_reference=session_reference,
    )

    if weighing_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weighing session not found.",
        )

    if weighing_session.scale_id != scale_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The weighing session does not belong "
                "to the specified scale."
            ),
        )

    if weighing_session.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Readings cannot be added to a closed "
                "weighing session."
            ),
        )

    return weighing_session


@router.post(
    "",
    response_model=schemas.ReadingIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a raw scale reading",
)
def ingest_reading(
    request: schemas.RawReadingCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Store one raw scale reading and immediately evaluate it
    with the SageWire stability engine.

    The request's scale_id may contain either:

    - a scale UUID, or
    - a scale_key.

    The optional session_id may contain either:

    - a session UUID, or
    - a session_key.
    """

    scale = resolve_scale(
        db=db,
        scale_reference=request.scale_id,
    )

    if scale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scale not found.",
        )

    if scale.operational_state == "DISABLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This scale is disabled.",
        )

    weighing_session = resolve_optional_session(
        db=db,
        session_reference=request.session_id,
        scale_id=scale.id,
    )

    normalized_request = request.model_copy(
        update={
            "scale_id": scale.id,
            "session_id": (
                weighing_session.id
                if weighing_session is not None
                else None
            ),
        }
    )

    try:
        raw_reading = readings.create_reading(
            db=db,
            scale=scale,
            request=normalized_request,
            session=weighing_session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    decision = stability.evaluate_latest_reading(
        db=db,
        scale=scale,
        newest_reading=raw_reading,
        session=weighing_session,
    )

    return {
        "reading": raw_reading,
        "stable": decision.stable,
        "stability_reason": decision.reason,
        "sample_count": decision.sample_count,
        "variation_lb": decision.variation_lb,
        "candidate_weight_lb": (
            decision.candidate_weight_lb
        ),
        "event": decision.event,
        "duplicate": decision.duplicate,
    }


@router.post(
    "/manual-event",
    response_model=schemas.WeightEventCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual weight event",
)
def create_manual_weight_event(
    request: schemas.ManualWeightEventRequest,
    db: Session = Depends(get_db),
):
    """
    Create an accepted weight event without waiting for a raw-reading
    stability window.

    This is intended for:

    - manual entries,
    - imported weights,
    - testing,
    - and indicators that already provide a stable final weight.
    """

    scale = resolve_scale(
        db=db,
        scale_reference=request.scale_id,
    )

    if scale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scale not found.",
        )

    if scale.operational_state == "DISABLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This scale is disabled.",
        )

    weighing_session = resolve_optional_session(
        db=db,
        session_reference=request.session_id,
        scale_id=scale.id,
    )

    normalized_request = request.model_copy(
        update={
            "scale_id": scale.id,
            "session_id": (
                weighing_session.id
                if weighing_session is not None
                else None
            ),
        }
    )

    try:
        event, duplicate = events.create_manual_event(
            db=db,
            scale=scale,
            request=normalized_request,
            session=weighing_session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return {
        "event": event,
        "duplicate": duplicate,
    }


@router.get(
    "/events",
    response_model=schemas.WeightEventListResponse,
    summary="List accepted weight events",
)
def list_weight_events(
    scale_reference: str | None = Query(
        default=None,
        description="Optional scale UUID or scale_key.",
    ),
    session_reference: str | None = Query(
        default=None,
        description="Optional session UUID or session_key.",
    ),
    channel_id: str | None = Query(
        default=None,
        description="Optional scale channel identifier.",
    ),
    rfid_tag_id: str | None = Query(
        default=None,
        description="Optional RFID tag identifier.",
    ),
    location_id: str | None = Query(
        default=None,
        description="Optional location identifier.",
    ),
    include_duplicates: bool = Query(
        default=False,
        description="Include events marked as duplicates.",
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
):
    """
    Return accepted weight events.

    These are the usable measurements produced either by:

    - the stability engine, or
    - manual event creation.
    """

    scale_id: str | None = None
    session_id: str | None = None

    if scale_reference is not None:
        scale = resolve_scale(
            db=db,
            scale_reference=scale_reference,
        )

        if scale is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scale not found.",
            )

        scale_id = scale.id

    if session_reference is not None:
        weighing_session = resolve_session(
            db=db,
            session_reference=session_reference,
        )

        if weighing_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Weighing session not found.",
            )

        session_id = weighing_session.id

        if (
            scale_id is not None
            and weighing_session.scale_id != scale_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The weighing session does not belong "
                    "to the specified scale."
                ),
            )

    event_items = events.list_events(
        db=db,
        scale_id=scale_id,
        session_id=session_id,
        channel_id=channel_id,
        rfid_tag_id=rfid_tag_id,
        location_id=location_id,
        include_duplicates=include_duplicates,
        skip=skip,
        limit=limit,
    )

    total = events.count_events(
        db=db,
        scale_id=scale_id,
        session_id=session_id,
        channel_id=channel_id,
        rfid_tag_id=rfid_tag_id,
        location_id=location_id,
        include_duplicates=include_duplicates,
    )

    return {
        "items": event_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/events/{event_id}",
    response_model=schemas.WeightEventResponse,
    summary="Get an accepted weight event",
)
def get_weight_event(
    event_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve one accepted weight event by UUID.
    """

    event = events.get_event(
        db=db,
        event_id=event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight event not found.",
        )

    return event


@router.get(
    "",
    response_model=schemas.RawReadingListResponse,
    summary="List raw scale readings",
)
def list_raw_readings(
    scale_reference: str | None = Query(
        default=None,
        description="Optional scale UUID or scale_key.",
    ),
    session_reference: str | None = Query(
        default=None,
        description="Optional session UUID or session_key.",
    ),
    channel_id: str | None = Query(
        default=None,
        description="Optional scale channel identifier.",
    ),
    validation_status: str | None = Query(
        default=None,
        description=(
            "Optional validation status such as "
            "VALID, REJECTED, or INVALID."
        ),
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
):
    """
    Return raw readings exactly as preserved by the service,
    along with their normalized values and validation status.
    """

    scale_id: str | None = None
    session_id: str | None = None

    if scale_reference is not None:
        scale = resolve_scale(
            db=db,
            scale_reference=scale_reference,
        )

        if scale is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scale not found.",
            )

        scale_id = scale.id

    if session_reference is not None:
        weighing_session = resolve_session(
            db=db,
            session_reference=session_reference,
        )

        if weighing_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Weighing session not found.",
            )

        session_id = weighing_session.id

        if (
            scale_id is not None
            and weighing_session.scale_id != scale_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The weighing session does not belong "
                    "to the specified scale."
                ),
            )

    reading_items = readings.list_readings(
        db=db,
        scale_id=scale_id,
        session_id=session_id,
        channel_id=channel_id,
        validation_status=validation_status,
        skip=skip,
        limit=limit,
    )

    total = readings.count_readings(
        db=db,
        scale_id=scale_id,
        session_id=session_id,
        channel_id=channel_id,
        validation_status=validation_status,
    )

    return {
        "items": reading_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{reading_id}",
    response_model=schemas.RawReadingResponse,
    summary="Get a raw scale reading",
)
def get_raw_reading(
    reading_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve one raw reading by UUID.
    """

    raw_reading = readings.get_reading(
        db=db,
        reading_id=reading_id,
    )

    if raw_reading is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw reading not found.",
        )

    return raw_reading
