from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud.readings import (
    kilograms_to_pounds,
    pounds_to_kilograms,
)


DEFAULT_DUPLICATE_WINDOW_SECONDS = 10
DEFAULT_DUPLICATE_TOLERANCE_LB = 0.5


def utc_now() -> datetime:
    """
    Return the current UTC time.
    """

    return datetime.now(timezone.utc)


def canonical_json(data: dict[str, Any]) -> str:
    """
    Convert a dictionary into stable JSON.

    Stable JSON always sorts keys and uses the same separators.
    This allows identical evidence to produce identical hashes.
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def create_sha256_hash(data: dict[str, Any]) -> str:
    """
    Create a SHA-256 hash from canonical JSON data.
    """

    payload = canonical_json(data).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def normalize_manual_weight(
    gross_weight: float,
    tare_weight: float,
    unit: str,
) -> tuple[float, float, float, float, float, float]:
    """
    Normalize gross, tare, and net weights into pounds and kilograms.

    Returns:
        (
            gross_weight_lb,
            tare_weight_lb,
            net_weight_lb,
            gross_weight_kg,
            tare_weight_kg,
            net_weight_kg,
        )
    """

    net_weight = gross_weight - tare_weight

    if unit == "lb":
        gross_weight_lb = gross_weight
        tare_weight_lb = tare_weight
        net_weight_lb = net_weight

        gross_weight_kg = pounds_to_kilograms(gross_weight_lb)
        tare_weight_kg = pounds_to_kilograms(tare_weight_lb)
        net_weight_kg = pounds_to_kilograms(net_weight_lb)

        return (
            gross_weight_lb,
            tare_weight_lb,
            net_weight_lb,
            gross_weight_kg,
            tare_weight_kg,
            net_weight_kg,
        )

    if unit == "kg":
        gross_weight_kg = gross_weight
        tare_weight_kg = tare_weight
        net_weight_kg = net_weight

        gross_weight_lb = kilograms_to_pounds(gross_weight_kg)
        tare_weight_lb = kilograms_to_pounds(tare_weight_kg)
        net_weight_lb = kilograms_to_pounds(net_weight_kg)

        return (
            gross_weight_lb,
            tare_weight_lb,
            net_weight_lb,
            gross_weight_kg,
            tare_weight_kg,
            net_weight_kg,
        )

    raise ValueError(
        f"Unsupported weight unit: {unit}"
    )


def get_event(
    db: Session,
    event_id: str,
) -> models.WeightEvent | None:
    """
    Look up one accepted weight event by its UUID.
    """

    return (
        db.query(models.WeightEvent)
        .filter(models.WeightEvent.id == event_id)
        .first()
    )


def find_duplicate_event(
    db: Session,
    scale_id: str,
    net_weight_lb: float,
    observed_at: datetime,
    session_id: str | None = None,
    channel_id: str | None = None,
    rfid_tag_id: str | None = None,
    duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS,
    duplicate_tolerance_lb: float = DEFAULT_DUPLICATE_TOLERANCE_LB,
) -> models.WeightEvent | None:
    """
    Search for a likely duplicate weight event.

    A likely duplicate must:

    - come from the same scale,
    - fall inside the duplicate time window,
    - have nearly the same net weight,
    - match the session context,
    - match the channel context,
    - and match the RFID context.

    None is treated as a real context value. This prevents an event
    without an RFID tag from being considered the same as an event
    associated with a specific tag.
    """

    window_start = observed_at - timedelta(
        seconds=duplicate_window_seconds
    )

    window_end = observed_at + timedelta(
        seconds=duplicate_window_seconds
    )

    minimum_weight = (
        net_weight_lb - duplicate_tolerance_lb
    )

    maximum_weight = (
        net_weight_lb + duplicate_tolerance_lb
    )

    query = (
        db.query(models.WeightEvent)
        .filter(
            models.WeightEvent.scale_id == scale_id,
            models.WeightEvent.observed_at >= window_start,
            models.WeightEvent.observed_at <= window_end,
            models.WeightEvent.net_weight_lb >= minimum_weight,
            models.WeightEvent.net_weight_lb <= maximum_weight,
            models.WeightEvent.is_duplicate.is_(False),
        )
    )

    if session_id is None:
        query = query.filter(
            models.WeightEvent.session_id.is_(None)
        )
    else:
        query = query.filter(
            models.WeightEvent.session_id == session_id
        )

    if channel_id is None:
        query = query.filter(
            models.WeightEvent.channel_id.is_(None)
        )
    else:
        query = query.filter(
            models.WeightEvent.channel_id == channel_id
        )

    if rfid_tag_id is None:
        query = query.filter(
            models.WeightEvent.rfid_tag_id.is_(None)
        )
    else:
        query = query.filter(
            models.WeightEvent.rfid_tag_id == rfid_tag_id
        )

    return (
        query
        .order_by(
            models.WeightEvent.observed_at.desc(),
            models.WeightEvent.accepted_at.desc(),
        )
        .first()
    )


def create_manual_event(
    db: Session,
    scale: models.Scale,
    request: schemas.ManualWeightEventRequest,
    session: models.WeighingSession | None = None,
    duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS,
    duplicate_tolerance_lb: float = DEFAULT_DUPLICATE_TOLERANCE_LB,
) -> tuple[models.WeightEvent, bool]:
    """
    Create an accepted manual weight event.

    If a matching event already exists inside the duplicate window,
    return the existing event instead of creating another one.

    Returns:
        (event, duplicate)
    """

    (
        gross_weight_lb,
        tare_weight_lb,
        net_weight_lb,
        gross_weight_kg,
        tare_weight_kg,
        net_weight_kg,
    ) = normalize_manual_weight(
        gross_weight=request.gross_weight,
        tare_weight=request.tare_weight,
        unit=request.unit,
    )

    observed_at = request.observed_at or utc_now()

    duplicate = find_duplicate_event(
        db=db,
        scale_id=scale.id,
        net_weight_lb=net_weight_lb,
        observed_at=observed_at,
        session_id=session.id if session is not None else None,
        channel_id=request.channel_id,
        rfid_tag_id=request.rfid_tag_id,
        duplicate_window_seconds=duplicate_window_seconds,
        duplicate_tolerance_lb=duplicate_tolerance_lb,
    )

    if duplicate is not None:
        return duplicate, True

    raw_evidence = {
        "source": "manual",
        "scale_id": scale.id,
        "session_id": (
            session.id if session is not None else None
        ),
        "channel_id": request.channel_id,
        "gross_weight": request.gross_weight,
        "tare_weight": request.tare_weight,
        "unit": request.unit,
        "rfid_tag_id": request.rfid_tag_id,
        "location_id": request.location_id,
        "observed_at": observed_at,
        "metadata": request.metadata_json,
    }

    normalized_evidence = {
        "scale_id": scale.id,
        "session_id": (
            session.id if session is not None else None
        ),
        "channel_id": request.channel_id,
        "gross_weight_lb": gross_weight_lb,
        "tare_weight_lb": tare_weight_lb,
        "net_weight_lb": net_weight_lb,
        "gross_weight_kg": gross_weight_kg,
        "tare_weight_kg": tare_weight_kg,
        "net_weight_kg": net_weight_kg,
        "rfid_tag_id": request.rfid_tag_id,
        "location_id": request.location_id,
        "observed_at": observed_at,
    }

    event = models.WeightEvent(
        scale_id=scale.id,
        session_id=(
            session.id if session is not None else None
        ),
        channel_id=request.channel_id,
        gross_weight_lb=gross_weight_lb,
        tare_weight_lb=tare_weight_lb,
        net_weight_lb=net_weight_lb,
        gross_weight_kg=gross_weight_kg,
        tare_weight_kg=tare_weight_kg,
        net_weight_kg=net_weight_kg,
        stable=True,
        stability_profile_id=scale.stability_profile_id,
        sample_count=1,
        variation_lb=0.0,
        rfid_tag_id=request.rfid_tag_id,
        location_id=request.location_id or scale.location_id,
        is_duplicate=False,
        duplicate_of=None,
        raw_evidence_hash=create_sha256_hash(
            raw_evidence
        ),
        normalized_evidence_hash=create_sha256_hash(
            normalized_evidence
        ),
        metadata_json=dict(request.metadata_json),
        observed_at=observed_at,
    )

    scale.last_seen_at = observed_at

    if scale.operational_state in {
        "REGISTERED",
        "OFFLINE",
    }:
        scale.operational_state = "ONLINE"

    db.add(event)
    db.add(scale)
    db.commit()
    db.refresh(event)
    db.refresh(scale)

    return event, False


def create_stable_event(
    db: Session,
    scale: models.Scale,
    readings: list[models.RawReading],
    gross_weight_lb: float,
    tare_weight_lb: float = 0.0,
    stability_profile: models.StabilityProfile | None = None,
    session: models.WeighingSession | None = None,
    channel_id: str | None = None,
    rfid_tag_id: str | None = None,
    location_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    observed_at: datetime | None = None,
    duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS,
    duplicate_tolerance_lb: float = DEFAULT_DUPLICATE_TOLERANCE_LB,
) -> tuple[models.WeightEvent, bool]:
    """
    Create a stable event from a group of raw readings.

    This function will be called by the stability engine after it has
    decided that the readings represent a usable stable measurement.

    Returns:
        (event, duplicate)
    """

    if not readings:
        raise ValueError(
            "At least one raw reading is required."
        )

    if tare_weight_lb < 0:
        raise ValueError(
            "tare_weight_lb cannot be less than zero."
        )

    if tare_weight_lb > gross_weight_lb:
        raise ValueError(
            "tare_weight_lb cannot exceed gross_weight_lb."
        )

    event_observed_at = (
        observed_at
        or readings[-1].observed_at
        or utc_now()
    )

    net_weight_lb = gross_weight_lb - tare_weight_lb

    gross_weight_kg = pounds_to_kilograms(
        gross_weight_lb
    )

    tare_weight_kg = pounds_to_kilograms(
        tare_weight_lb
    )

    net_weight_kg = pounds_to_kilograms(
        net_weight_lb
    )

    weights = [
        reading.weight_lb
        for reading in readings
    ]

    variation_lb = max(weights) - min(weights)

    duplicate = find_duplicate_event(
        db=db,
        scale_id=scale.id,
        net_weight_lb=net_weight_lb,
        observed_at=event_observed_at,
        session_id=(
            session.id if session is not None else None
        ),
        channel_id=channel_id,
        rfid_tag_id=rfid_tag_id,
        duplicate_window_seconds=duplicate_window_seconds,
        duplicate_tolerance_lb=duplicate_tolerance_lb,
    )

    if duplicate is not None:
        return duplicate, True

    reading_evidence = [
        {
            "id": reading.id,
            "raw_weight": reading.raw_weight,
            "raw_unit": reading.raw_unit,
            "weight_lb": reading.weight_lb,
            "weight_kg": reading.weight_kg,
            "device_stable": reading.device_stable,
            "observed_at": reading.observed_at,
            "received_at": reading.received_at,
        }
        for reading in readings
    ]

    raw_evidence = {
        "source": "stability_engine",
        "scale_id": scale.id,
        "session_id": (
            session.id if session is not None else None
        ),
        "channel_id": channel_id,
        "readings": reading_evidence,
    }

    normalized_evidence = {
        "scale_id": scale.id,
        "session_id": (
            session.id if session is not None else None
        ),
        "channel_id": channel_id,
        "gross_weight_lb": gross_weight_lb,
        "tare_weight_lb": tare_weight_lb,
        "net_weight_lb": net_weight_lb,
        "sample_count": len(readings),
        "variation_lb": variation_lb,
        "rfid_tag_id": rfid_tag_id,
        "location_id": location_id,
        "observed_at": event_observed_at,
    }

    event = models.WeightEvent(
        scale_id=scale.id,
        session_id=(
            session.id if session is not None else None
        ),
        channel_id=channel_id,
        gross_weight_lb=gross_weight_lb,
        tare_weight_lb=tare_weight_lb,
        net_weight_lb=net_weight_lb,
        gross_weight_kg=gross_weight_kg,
        tare_weight_kg=tare_weight_kg,
        net_weight_kg=net_weight_kg,
        stable=True,
        stability_profile_id=(
            stability_profile.id
            if stability_profile is not None
            else scale.stability_profile_id
        ),
        sample_count=len(readings),
        variation_lb=variation_lb,
        rfid_tag_id=rfid_tag_id,
        location_id=location_id or scale.location_id,
        is_duplicate=False,
        duplicate_of=None,
        raw_evidence_hash=create_sha256_hash(
            raw_evidence
        ),
        normalized_evidence_hash=create_sha256_hash(
            normalized_evidence
        ),
        metadata_json=dict(metadata or {}),
        observed_at=event_observed_at,
    )

    scale.last_seen_at = event_observed_at

    if scale.operational_state in {
        "REGISTERED",
        "OFFLINE",
    }:
        scale.operational_state = "ONLINE"

    db.add(event)
    db.add(scale)
    db.commit()
    db.refresh(event)
    db.refresh(scale)

    return event, False


def list_events(
    db: Session,
    scale_id: str | None = None,
    session_id: str | None = None,
    channel_id: str | None = None,
    rfid_tag_id: str | None = None,
    location_id: str | None = None,
    include_duplicates: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> list[models.WeightEvent]:
    """
    Return a page of accepted weight events.

    Results are ordered newest first.
    """

    query = db.query(models.WeightEvent)

    if scale_id is not None:
        query = query.filter(
            models.WeightEvent.scale_id == scale_id
        )

    if session_id is not None:
        query = query.filter(
            models.WeightEvent.session_id == session_id
        )

    if channel_id is not None:
        query = query.filter(
            models.WeightEvent.channel_id == channel_id
        )

    if rfid_tag_id is not None:
        query = query.filter(
            models.WeightEvent.rfid_tag_id == rfid_tag_id
        )

    if location_id is not None:
        query = query.filter(
            models.WeightEvent.location_id == location_id
        )

    if not include_duplicates:
        query = query.filter(
            models.WeightEvent.is_duplicate.is_(False)
        )

    return (
        query
        .order_by(
            models.WeightEvent.observed_at.desc(),
            models.WeightEvent.accepted_at.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_events(
    db: Session,
    scale_id: str | None = None,
    session_id: str | None = None,
    channel_id: str | None = None,
    rfid_tag_id: str | None = None,
    location_id: str | None = None,
    include_duplicates: bool = False,
) -> int:
    """
    Count weight events using the same filters as list_events.
    """

    query = db.query(
        func.count(models.WeightEvent.id)
    )

    if scale_id is not None:
        query = query.filter(
            models.WeightEvent.scale_id == scale_id
        )

    if session_id is not None:
        query = query.filter(
            models.WeightEvent.session_id == session_id
        )

    if channel_id is not None:
        query = query.filter(
            models.WeightEvent.channel_id == channel_id
        )

    if rfid_tag_id is not None:
        query = query.filter(
            models.WeightEvent.rfid_tag_id == rfid_tag_id
        )

    if location_id is not None:
        query = query.filter(
            models.WeightEvent.location_id == location_id
        )

    if not include_duplicates:
        query = query.filter(
            models.WeightEvent.is_duplicate.is_(False)
        )

    return int(query.scalar() or 0)
