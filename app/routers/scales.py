from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import schemas
from app.crud import heartbeats, scales
from app.database import get_db


router = APIRouter(
    prefix="/scales",
    tags=["Scales"],
)


def resolve_scale(
    db: Session,
    scale_reference: str,
):
    """
    Resolve a scale using either:

    - its internal UUID, or
    - its human-readable scale_key.

    This lets callers use whichever identifier they already have.
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


@router.post(
    "",
    response_model=schemas.ScaleRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a scale",
)
def register_scale(
    request: schemas.ScaleRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a scale with SageWire Scale Service.

    Registration is idempotent when the same scale_key is submitted
    more than once. An existing scale will be returned rather than
    duplicated.
    """

    scale, created = scales.register_scale(
        db=db,
        request=request,
    )

    return {
        "scale": scale,
        "created": created,
    }


@router.get(
    "",
    response_model=schemas.ScaleListResponse,
    summary="List scales",
)
def list_scales(
    operational_state: str | None = Query(
        default=None,
        description=(
            "Optional operational-state filter, such as "
            "REGISTERED, ONLINE, OFFLINE, or DISABLED."
        ),
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
    Return a paginated list of registered scales.
    """

    scale_items = scales.list_scales(
        db=db,
        operational_state=operational_state,
        location_id=location_id,
        skip=skip,
        limit=limit,
    )

    total = scales.count_scales(
        db=db,
        operational_state=operational_state,
        location_id=location_id,
    )

    return {
        "items": scale_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{scale_reference}",
    response_model=schemas.ScaleResponse,
    summary="Get a scale",
)
def get_scale(
    scale_reference: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve one scale using either its UUID or scale_key.
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

    return scale


@router.post(
    "/{scale_reference}/heartbeats",
    response_model=schemas.HeartbeatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a scale heartbeat",
)
def create_heartbeat(
    scale_reference: str,
    request: schemas.HeartbeatRequest,
    db: Session = Depends(get_db),
):
    """
    Store a heartbeat and update the scale's current operational state
    and last-seen timestamp.
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

    heartbeat = heartbeats.create_heartbeat(
        db=db,
        scale=scale,
        request=request,
    )

    return heartbeat


@router.get(
    "/{scale_reference}/heartbeats",
    response_model=schemas.HeartbeatListResponse,
    summary="List scale heartbeats",
)
def list_scale_heartbeats(
    scale_reference: str,
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
    Return heartbeat history for one scale.
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

    heartbeat_items = heartbeats.list_heartbeats(
        db=db,
        scale_id=scale.id,
        skip=skip,
        limit=limit,
    )

    total = heartbeats.count_heartbeats(
        db=db,
        scale_id=scale.id,
    )

    return {
        "items": heartbeat_items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/{scale_reference}/heartbeats/latest",
    response_model=schemas.HeartbeatResponse,
    summary="Get latest scale heartbeat",
)
def get_latest_scale_heartbeat(
    scale_reference: str,
    db: Session = Depends(get_db),
):
    """
    Return the most recent heartbeat received from one scale.
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

    heartbeat = heartbeats.get_latest_heartbeat(
        db=db,
        scale_id=scale.id,
    )

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No heartbeat has been recorded for this scale.",
        )

    return heartbeat
