from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas


POUNDS_PER_KILOGRAM = 2.2046226218


def utc_now() -> datetime:
    """
    Return the current UTC time.
    """

    return datetime.now(timezone.utc)


def pounds_to_kilograms(weight_lb: float) -> float:
    """
    Convert pounds to kilograms.
    """

    return weight_lb / POUNDS_PER_KILOGRAM


def kilograms_to_pounds(weight_kg: float) -> float:
    """
    Convert kilograms to pounds.
    """

    return weight_kg * POUNDS_PER_KILOGRAM


def normalize_weight(
    raw_weight: float,
    raw_unit: str,
) -> tuple[float, float]:
    """
    Convert a raw reading into canonical pounds and kilograms.

    Returns:
        (weight_lb, weight_kg)
    """

    if raw_unit == "lb":
        weight_lb = raw_weight
        weight_kg = pounds_to_kilograms(raw_weight)

        return weight_lb, weight_kg

    if raw_unit == "kg":
        weight_kg = raw_weight
        weight_lb = kilograms_to_pounds(raw_weight)

        return weight_lb, weight_kg

    raise ValueError(
        f"Unsupported weight unit: {raw_unit}"
    )


def validate_reading(
    scale: models.Scale,
    weight_lb: float,
) -> tuple[str, str | None]:
    """
    Validate a normalized weight against the scale's registered limits.

    The reading is still preserved even when invalid.

    Returns:
        (validation_status, validation_message)
    """

    if weight_lb < 0:
        return (
            "INVALID",
            "Weight cannot be less than zero.",
        )

    if (
        scale.capacity_lb is not None
        and weight_lb > scale.capacity_lb
    ):
        return (
            "INVALID",
            (
                f"Weight exceeds registered scale capacity "
                f"of {scale.capacity_lb} lb."
            ),
        )

    if (
        scale.minimum_weight_lb is not None
        and weight_lb < scale.minimum_weight_lb
    ):
        return (
            "REJECTED",
            (
                f"Weight is below the registered minimum "
                f"of {scale.minimum_weight_lb} lb."
            ),
        )

    return "VALID", None


def get_reading(
    db: Session,
    reading_id: str,
) -> models.RawReading | None:
    """
    Look up one raw reading by its UUID.
    """

    return (
        db.query(models.RawReading)
        .filter(models.RawReading.id == reading_id)
        .first()
    )


def create_reading(
    db: Session,
    scale: models.Scale,
    request: schemas.RawReadingCreateRequest,
    session: models.WeighingSession | None = None,
) -> models.RawReading:
    """
    Normalize, validate, and preserve one raw scale reading.

    This function does not create a WeightEvent yet.
    The stability engine will perform that work later.
    """

    weight_lb, weight_kg = normalize_weight(
        raw_weight=request.raw_weight,
        raw_unit=request.raw_unit,
    )

    validation_status, validation_message = validate_reading(
        scale=scale,
        weight_lb=weight_lb,
    )

    observed_at = request.observed_at or utc_now()

    metadata = dict(request.metadata_json)

    metadata["tare_weight"] = request.tare_weight
    metadata["tare_unit"] = request.raw_unit

    if request.rfid_tag_id is not None:
        metadata["rfid_tag_id"] = request.rfid_tag_id

    if request.location_id is not None:
        metadata["location_id"] = request.location_id

    reading = models.RawReading(
        scale_id=scale.id,
        session_id=session.id if session is not None else None,
        channel_id=request.channel_id,
        raw_weight=request.raw_weight,
        raw_unit=request.raw_unit,
        weight_lb=weight_lb,
        weight_kg=weight_kg,
        device_stable=request.device_stable,
        validation_status=validation_status,
        validation_message=validation_message,
        source_packet=request.source_packet,
        metadata_json=metadata,
        observed_at=observed_at,
    )

    scale.last_seen_at = observed_at

    if scale.operational_state in {
        "REGISTERED",
        "OFFLINE",
    }:
        scale.operational_state = "ONLINE"

    db.add(reading)
    db.add(scale)
    db.commit()
    db.refresh(reading)
    db.refresh(scale)

    return reading


def list_readings(
    db: Session,
    scale_id: str | None = None,
    session_id: str | None = None,
    channel_id: str | None = None,
    validation_status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[models.RawReading]:
    """
    Return a page of raw readings.

    Results are ordered newest first.
    """

    query = db.query(models.RawReading)

    if scale_id is not None:
        query = query.filter(
            models.RawReading.scale_id == scale_id
        )

    if session_id is not None:
        query = query.filter(
            models.RawReading.session_id == session_id
        )

    if channel_id is not None:
        query = query.filter(
            models.RawReading.channel_id == channel_id
        )

    if validation_status is not None:
        query = query.filter(
            models.RawReading.validation_status
            == validation_status
        )

    return (
        query
        .order_by(
            models.RawReading.observed_at.desc(),
            models.RawReading.received_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_readings(
    db: Session,
    scale_id: str | None = None,
    session_id: str | None = None,
    channel_id: str | None = None,
    validation_status: str | None = None,
) -> int:
    """
    Count raw readings using the same filters as list_readings.
    """

    query = db.query(
        func.count(models.RawReading.id)
    )

    if scale_id is not None:
        query = query.filter(
            models.RawReading.scale_id == scale_id
        )

    if session_id is not None:
        query = query.filter(
            models.RawReading.session_id == session_id
        )

    if channel_id is not None:
        query = query.filter(
            models.RawReading.channel_id == channel_id
        )

    if validation_status is not None:
        query = query.filter(
            models.RawReading.validation_status
            == validation_status
        )

    return int(query.scalar() or 0)


def get_recent_valid_readings(
    db: Session,
    scale_id: str,
    channel_id: str | None = None,
    session_id: str | None = None,
    limit: int = 100,
) -> list[models.RawReading]:
    """
    Return recent valid readings for stability analysis.

    Results are returned oldest to newest so the stability engine
    can process them in chronological order.
    """

    query = (
        db.query(models.RawReading)
        .filter(
            models.RawReading.scale_id == scale_id,
            models.RawReading.validation_status == "VALID",
        )
    )

    if channel_id is None:
        query = query.filter(
            models.RawReading.channel_id.is_(None)
        )
    else:
        query = query.filter(
            models.RawReading.channel_id == channel_id
        )

    if session_id is None:
        query = query.filter(
            models.RawReading.session_id.is_(None)
        )
    else:
        query = query.filter(
            models.RawReading.session_id == session_id
        )

    readings = (
        query
        .order_by(
            models.RawReading.observed_at.desc(),
            models.RawReading.received_at.desc(),
        )
        .limit(limit)
        .all()
    )

    readings.reverse()

    return readings
