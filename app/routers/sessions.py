from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import schemas
from app.crud import scales, sessions
from app.database import get_db


router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
)


def resolve_scale(
    db: Session,
    scale_reference: str,
):
    """
    Resolve a scale using either its internal UUID
    or its human-readable scale_key.
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


@router.post(
    "",
    response_model=schemas.SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a weighing session",
)
def create_session(
    request: schemas.SessionCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Open a new weighing session.

    The scale_id field may contain either:

    - the scale UUID, or
    - the scale_key.

    When a session_key is supplied, repeated requests using the
    same session_key return the existing session rather than
    creating a duplicate.
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

    existing_open_session = (
        sessions.get_open_session_for_scale(
            db=db,
            scale_id=scale.id,
        )
    )

    if existing_open_session is not None:
        if (
            request.session_key is not None
            and existing_open_session.session_key
            == request.session_key
        ):
            return existing_open_session

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This scale already has an open weighing session."
            ),
        )

    normalized_request = request.model_copy(
        update={
            "scale_id": scale.id,
        }
    )

    weighing_session, _created = sessions.create_session(
        db=db,
        request=normalized_request,
    )

    return weighing_session


@router.get(
    "",
    response_model=schemas.SessionListResponse,
    summary="List weighing sessions",
)
def list_sessions(
    scale_reference: str | None = Query(
        default=None,
        description=(
            "Optional scale UUID or human-readable scale_key."
        ),
    ),
    session_status: str | None = Query(
        default=None,
        alias="status",
        description="Optional session status: OPEN or CLOSED.",
    ),
    location_id: str | None = Query(
        default=None,
        description="Optional location identifier.",
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
    Return a paginated list of weighing sessions.
    """

    scale_id: str | None = None

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

    session_items = sessions.list_sessions(
        db=db,
        scale_id=scale_id,
        status=session_status,
        location_id=location_id,
        skip=skip,
        limit=limit,
    )

    total = sessions.count_sessions(
        db=db,
        scale_id=scale_id,
        status=session_status,
        location_id=location_id,
    )

    return {
        "items": session_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{session_reference}",
    response_model=schemas.SessionResponse,
    summary="Get a weighing session",
)
def get_session(
    session_reference: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve one weighing session using either its UUID
    or session_key.
    """

    weighing_session = resolve_session(
        db=db,
        session_reference=session_reference,
    )

    if weighing_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weighing session not found.",
        )

    return weighing_session


@router.post(
    "/{session_reference}/close",
    response_model=schemas.SessionResponse,
    summary="Close a weighing session",
)
def close_session(
    session_reference: str,
    request: schemas.SessionCloseRequest,
    db: Session = Depends(get_db),
):
    """
    Close an open weighing session.

    Repeating the same close request is safe. An already-closed
    session is returned unchanged.
    """

    weighing_session = resolve_session(
        db=db,
        session_reference=session_reference,
    )

    if weighing_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weighing session not found.",
        )

    weighing_session, _closed_now = sessions.close_session(
        db=db,
        session=weighing_session,
        request=request,
    )

    return weighing_session


@router.get(
    "/scale/{scale_reference}/open",
    response_model=schemas.SessionResponse,
    summary="Get the open session for a scale",
)
def get_open_session_for_scale(
    scale_reference: str,
    db: Session = Depends(get_db),
):
    """
    Return the currently open weighing session for a scale.
    """

    scale = resolve_scale(
        db=db,
        scale_reference=scale_reference,
    )

    if scale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scale not found.",
        )

    weighing_session = (
        sessions.get_open_session_for_scale(
            db=db,
            scale_id=scale.id,
        )
    )

    if weighing_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This scale does not currently have "
                "an open weighing session."
            ),
        )

    return weighing_session
