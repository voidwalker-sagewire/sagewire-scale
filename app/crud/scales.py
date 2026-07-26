from sqlalchemy.orm import Session

from app import models, schemas


def get_scale_by_key(
    db: Session,
    scale_key: str,
):
    """
    Look up a scale using its unique scale_key.
    """

    return (
        db.query(models.Scale)
        .filter(models.Scale.scale_key == scale_key)
        .first()
    )


def get_scale(
    db: Session,
    scale_id: str,
):
    """
    Look up a scale by its UUID.
    """

    return (
        db.query(models.Scale)
        .filter(models.Scale.id == scale_id)
        .first()
    )


def list_scales(
    db: Session,
    skip: int = 0,
    limit: int = 100,
):
    """
    Return a page of registered scales.
    """

    return (
        db.query(models.Scale)
        .offset(skip)
        .limit(limit)
        .all()
    )


def register_scale(
    db: Session,
    request: schemas.ScaleRegisterRequest,
):
    """
    Register a scale.

    If the scale already exists,
    return it without creating a duplicate.
    """

    existing = get_scale_by_key(
        db,
        request.scale_key,
    )

    if existing:
        return existing, False

    scale = models.Scale(
        scale_key=request.scale_key,
        name=request.name,
        description=request.description,
        manufacturer=request.manufacturer,
        model=request.model,
        serial_number=request.serial_number,
        adapter_type=request.adapter_type,
        connection_type=request.connection_type,
        capacity_lb=request.capacity_lb,
        minimum_weight_lb=request.minimum_weight_lb,
        resolution_lb=request.resolution_lb,
        location_id=request.location_id,
        stability_profile_id=request.stability_profile_id,
        metadata_json=request.metadata_json,
    )

    db.add(scale)
    db.commit()
    db.refresh(scale)

    return scale, True
