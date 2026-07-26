from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.crud import events, readings


DEFAULT_MINIMUM_SAMPLES = 3
DEFAULT_WINDOW_SECONDS = 1.0
DEFAULT_MAXIMUM_VARIATION_LB = 2.0
MAX_READINGS_TO_EXAMINE = 100


@dataclass
class StabilityDecision:
    """
    Result produced when the stability engine examines recent readings.
    """

    stable: bool
    reason: str

    sample_count: int = 0
    variation_lb: float | None = None
    candidate_weight_lb: float | None = None

    event: models.WeightEvent | None = None
    duplicate: bool = False


def ensure_utc(value: datetime) -> datetime:
    """
    Return a timezone-aware UTC datetime.

    SQLite may sometimes return timestamps without timezone information,
    even when DateTime(timezone=True) is used.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_stability_settings(
    scale: models.Scale,
) -> tuple[
    int,
    float,
    float,
    models.StabilityProfile | None,
]:
    """
    Determine which stability rules apply to a scale.

    A scale may use a database StabilityProfile. If no active profile
    is assigned, the service uses safe default rules.

    Returns:
        (
            minimum_samples,
            window_seconds,
            maximum_variation_lb,
            stability_profile,
        )
    """

    profile = scale.stability_profile

    if profile is not None and profile.is_active:
        return (
            profile.minimum_samples,
            profile.window_seconds,
            profile.maximum_variation_lb,
            profile,
        )

    return (
        DEFAULT_MINIMUM_SAMPLES,
        DEFAULT_WINDOW_SECONDS,
        DEFAULT_MAXIMUM_VARIATION_LB,
        None,
    )


def get_reading_tare_lb(
    reading: models.RawReading,
) -> float:
    """
    Retrieve the tare value preserved in a raw reading's metadata
    and normalize it to pounds.

    Missing tare information means zero tare.
    """

    metadata = reading.metadata_json or {}

    raw_tare = metadata.get("tare_weight", 0.0)
    tare_unit = metadata.get(
        "tare_unit",
        reading.raw_unit,
    )

    try:
        tare_value = float(raw_tare)
    except (TypeError, ValueError):
        return 0.0

    if tare_value < 0:
        return 0.0

    if tare_unit == "kg":
        return readings.kilograms_to_pounds(
            tare_value
        )

    return tare_value


def get_context_value(
    reading: models.RawReading,
    key: str,
) -> Any:
    """
    Retrieve an optional context value from reading metadata.
    """

    metadata = reading.metadata_json or {}

    return metadata.get(key)


def select_window_readings(
    recent_readings: list[models.RawReading],
    newest_reading: models.RawReading,
    window_seconds: float,
) -> list[models.RawReading]:
    """
    Select readings that occurred inside the active stability window.

    The newest reading anchors the end of the window.
    """

    newest_time = ensure_utc(
        newest_reading.observed_at
    )

    window_start = newest_time - timedelta(
        seconds=window_seconds
    )

    selected: list[models.RawReading] = []

    for reading in recent_readings:
        reading_time = ensure_utc(
            reading.observed_at
        )

        if window_start <= reading_time <= newest_time:
            selected.append(reading)

    return selected


def examine_readings(
    scale: models.Scale,
    candidate_readings: list[models.RawReading],
    minimum_samples: int,
    maximum_variation_lb: float,
) -> StabilityDecision:
    """
    Decide whether a set of readings is stable.

    Stability requires:

    - enough valid samples,
    - the latest hardware stable flag must not be False,
    - all samples must fit inside the allowed weight variation.
    """

    sample_count = len(candidate_readings)

    if sample_count < minimum_samples:
        return StabilityDecision(
            stable=False,
            reason=(
                f"Waiting for more samples: "
                f"{sample_count}/{minimum_samples}."
            ),
            sample_count=sample_count,
        )

    newest_reading = candidate_readings[-1]

    if newest_reading.device_stable is False:
        return StabilityDecision(
            stable=False,
            reason=(
                "The device reports that the weight "
                "is still moving."
            ),
            sample_count=sample_count,
        )

    sample_weights = [
        reading.weight_lb
        for reading in candidate_readings
    ]

    minimum_weight = min(sample_weights)
    maximum_weight = max(sample_weights)

    variation_lb = (
        maximum_weight - minimum_weight
    )

    candidate_weight_lb = float(
        median(sample_weights)
    )

    if variation_lb > maximum_variation_lb:
        return StabilityDecision(
            stable=False,
            reason=(
                f"Weight variation is {variation_lb:.3f} lb; "
                f"maximum allowed is "
                f"{maximum_variation_lb:.3f} lb."
            ),
            sample_count=sample_count,
            variation_lb=variation_lb,
            candidate_weight_lb=candidate_weight_lb,
        )

    if (
        scale.minimum_weight_lb is not None
        and candidate_weight_lb
        < scale.minimum_weight_lb
    ):
        return StabilityDecision(
            stable=False,
            reason=(
                f"Candidate weight is below the scale's "
                f"minimum usable weight of "
                f"{scale.minimum_weight_lb} lb."
            ),
            sample_count=sample_count,
            variation_lb=variation_lb,
            candidate_weight_lb=candidate_weight_lb,
        )

    if (
        scale.capacity_lb is not None
        and candidate_weight_lb
        > scale.capacity_lb
    ):
        return StabilityDecision(
            stable=False,
            reason=(
                f"Candidate weight exceeds the scale's "
                f"capacity of {scale.capacity_lb} lb."
            ),
            sample_count=sample_count,
            variation_lb=variation_lb,
            candidate_weight_lb=candidate_weight_lb,
        )

    return StabilityDecision(
        stable=True,
        reason="The reading window is stable.",
        sample_count=sample_count,
        variation_lb=variation_lb,
        candidate_weight_lb=candidate_weight_lb,
    )


def evaluate_latest_reading(
    db: Session,
    scale: models.Scale,
    newest_reading: models.RawReading,
    session: models.WeighingSession | None = None,
) -> StabilityDecision:
    """
    Examine the newest raw reading and its recent neighbors.

    If the readings are stable, create or locate the corresponding
    accepted WeightEvent.
    """

    if newest_reading.validation_status != "VALID":
        return StabilityDecision(
            stable=False,
            reason=(
                "The newest reading is not valid and "
                "cannot become a weight event."
            ),
            sample_count=0,
        )

    (
        minimum_samples,
        window_seconds,
        maximum_variation_lb,
        stability_profile,
    ) = get_stability_settings(scale)

    recent_readings = readings.get_recent_valid_readings(
        db=db,
        scale_id=scale.id,
        channel_id=newest_reading.channel_id,
        session_id=newest_reading.session_id,
        limit=MAX_READINGS_TO_EXAMINE,
    )

    window_readings = select_window_readings(
        recent_readings=recent_readings,
        newest_reading=newest_reading,
        window_seconds=window_seconds,
    )

    decision = examine_readings(
        scale=scale,
        candidate_readings=window_readings,
        minimum_samples=minimum_samples,
        maximum_variation_lb=maximum_variation_lb,
    )

    if not decision.stable:
        return decision

    if decision.candidate_weight_lb is None:
        return StabilityDecision(
            stable=False,
            reason=(
                "A stable candidate weight could not "
                "be calculated."
            ),
            sample_count=decision.sample_count,
            variation_lb=decision.variation_lb,
        )

    tare_weight_lb = get_reading_tare_lb(
        newest_reading
    )

    if tare_weight_lb > decision.candidate_weight_lb:
        return StabilityDecision(
            stable=False,
            reason=(
                "The tare weight is greater than the "
                "stable gross weight."
            ),
            sample_count=decision.sample_count,
            variation_lb=decision.variation_lb,
            candidate_weight_lb=(
                decision.candidate_weight_lb
            ),
        )

    rfid_tag_id = get_context_value(
        newest_reading,
        "rfid_tag_id",
    )

    location_id = get_context_value(
        newest_reading,
        "location_id",
    )

    stability_metadata = {
        "engine": "sagewire-window-stability",
        "minimum_samples": minimum_samples,
        "window_seconds": window_seconds,
        "maximum_variation_lb": (
            maximum_variation_lb
        ),
        "reading_ids": [
            reading.id
            for reading in window_readings
        ],
    }

    event, duplicate = events.create_stable_event(
        db=db,
        scale=scale,
        readings=window_readings,
        gross_weight_lb=(
            decision.candidate_weight_lb
        ),
        tare_weight_lb=tare_weight_lb,
        stability_profile=stability_profile,
        session=session,
        channel_id=newest_reading.channel_id,
        rfid_tag_id=rfid_tag_id,
        location_id=location_id,
        metadata=stability_metadata,
        observed_at=newest_reading.observed_at,
    )

    decision.event = event
    decision.duplicate = duplicate

    if duplicate:
        decision.reason = (
            "The readings are stable, but the matching "
            "weight event already exists."
        )
    else:
        decision.reason = (
            "The readings are stable and a new "
            "weight event was created."
        )

    return decision
