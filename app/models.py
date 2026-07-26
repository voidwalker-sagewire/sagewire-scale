from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """
    Return the current UTC time.

    All SageWire timestamps are stored in UTC.
    """

    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """
    Create a new UUID string for database records.
    """

    return str(uuid4())


class StabilityProfile(Base):
    """
    Rules used to decide when a group of raw readings is stable.
    """

    __tablename__ = "stability_profiles"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    minimum_samples: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    window_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    maximum_variation_lb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=2.0,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    scales: Mapped[list["Scale"]] = relationship(
        back_populates="stability_profile",
    )


class Scale(Base):
    """
    A registered physical or virtual scale.

    Examples:
    - SellEton chute scale
    - Bluetooth calf scale
    - Grain platform scale
    - Manual-entry scale
    """

    __tablename__ = "scales"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    scale_key: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    manufacturer: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    model: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    serial_number: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    adapter_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="manual",
    )

    connection_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    operational_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="REGISTERED",
    )

    capacity_lb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    minimum_weight_lb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    resolution_lb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    location_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    stability_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("stability_profiles.id"),
        nullable=True,
        index=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    stability_profile: Mapped["StabilityProfile | None"] = relationship(
        back_populates="scales",
    )

    heartbeats: Mapped[list["Heartbeat"]] = relationship(
        back_populates="scale",
        cascade="all, delete-orphan",
    )

    raw_readings: Mapped[list["RawReading"]] = relationship(
        back_populates="scale",
        cascade="all, delete-orphan",
    )

    weight_events: Mapped[list["WeightEvent"]] = relationship(
        back_populates="scale",
        cascade="all, delete-orphan",
    )

    sessions: Mapped[list["WeighingSession"]] = relationship(
        back_populates="scale",
        cascade="all, delete-orphan",
    )


class Heartbeat(Base):
    """
    A health signal sent by a scale bridge or adapter.
    """

    __tablename__ = "heartbeats"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    scale_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scales.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ONLINE",
    )

    firmware_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    adapter_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    scale: Mapped["Scale"] = relationship(
        back_populates="heartbeats",
    )


class WeighingSession(Base):
    """
    A bounded period of weighing activity.

    Examples:
    - Morning chute session
    - Calf-weighing trip
    - Grain bag filling run
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    scale_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scales.id"),
        nullable=False,
        index=True,
    )

    session_key: Mapped[str | None] = mapped_column(
        String(150),
        unique=True,
        nullable=True,
        index=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="OPEN",
        index=True,
    )

    location_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    opened_by: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    closed_by: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    scale: Mapped["Scale"] = relationship(
        back_populates="sessions",
    )

    raw_readings: Mapped[list["RawReading"]] = relationship(
        back_populates="session",
    )

    weight_events: Mapped[list["WeightEvent"]] = relationship(
        back_populates="session",
    )


class RawReading(Base):
    """
    One unaltered weight observation received from a device or adapter.

    Raw readings are evidence.

    They are preserved even when they are unstable, duplicated, rejected,
    or never become an accepted WeightEvent.
    """

    __tablename__ = "raw_readings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    scale_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scales.id"),
        nullable=False,
        index=True,
    )

    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=True,
        index=True,
    )

    channel_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    raw_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    raw_unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    weight_lb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    weight_kg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    device_stable: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    validation_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="VALID",
        index=True,
    )

    validation_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_packet: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    scale: Mapped["Scale"] = relationship(
        back_populates="raw_readings",
    )

    session: Mapped["WeighingSession | None"] = relationship(
        back_populates="raw_readings",
    )


class WeightEvent(Base):
    """
    A usable weight accepted by the SageWire Scale Service.

    A WeightEvent is created only after validation and stability processing.
    """

    __tablename__ = "weight_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_uuid,
    )

    scale_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scales.id"),
        nullable=False,
        index=True,
    )

    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=True,
        index=True,
    )

    channel_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    gross_weight_lb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    tare_weight_lb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    net_weight_lb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    gross_weight_kg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    tare_weight_kg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    net_weight_kg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    stable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    stability_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("stability_profiles.id"),
        nullable=True,
        index=True,
    )

    sample_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    variation_lb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    rfid_tag_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    location_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    is_duplicate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    duplicate_of: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("weight_events.id"),
        nullable=True,
        index=True,
    )

    raw_evidence_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    normalized_evidence_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    scale: Mapped["Scale"] = relationship(
        back_populates="weight_events",
    )

    session: Mapped["WeighingSession | None"] = relationship(
        back_populates="weight_events",
    )

    stability_profile: Mapped["StabilityProfile | None"] = relationship()

    original_event: Mapped["WeightEvent | None"] = relationship(
        remote_side=[id],
    )


Index(
    "ix_raw_readings_scale_observed",
    RawReading.scale_id,
    RawReading.observed_at,
)

Index(
    "ix_weight_events_scale_observed",
    WeightEvent.scale_id,
    WeightEvent.observed_at,
)

Index(
    "ix_weight_events_duplicate_search",
    WeightEvent.scale_id,
    WeightEvent.net_weight_lb,
    WeightEvent.observed_at,
  )
