from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


ScaleState = Literal[
    "REGISTERED",
    "ONLINE",
    "OFFLINE",
    "ERROR",
    "MAINTENANCE",
]

SessionState = Literal[
    "OPEN",
    "CLOSED",
]

ValidationState = Literal[
    "VALID",
    "INVALID",
    "REJECTED",
]

WeightUnit = Literal[
    "lb",
    "lbs",
    "pound",
    "pounds",
    "kg",
    "kilogram",
    "kilograms",
]


class APIModel(BaseModel):
    """
    Shared parent for SageWire API schemas.

    Allows Pydantic to read directly from SQLAlchemy model objects.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )


class MessageResponse(APIModel):
    """
    Generic API message.
    """

    message: str


class HealthResponse(APIModel):
    """
    Response returned by /health.
    """

    service: str = "sagewire-scale"
    status: str = "healthy"
    version: str = "0.1.0"


class VersionResponse(APIModel):
    """
    Response returned by /version.
    """

    service: str = "sagewire-scale"
    version: str = "0.1.0"


class InfoResponse(APIModel):
    """
    Response returned by /info.
    """

    service: str
    purpose: str
    version: str
    database: str
    status: str


class MetricsResponse(APIModel):
    """
    Basic operational counters returned by /metrics.
    """

    service: str = "sagewire-scale"
    version: str = "0.1.0"
    scales: int = 0
    online_scales: int = 0
    open_sessions: int = 0
    raw_readings: int = 0
    weight_events: int = 0


# ============================================================
# Stability Profiles
# ============================================================


class StabilityProfileBase(APIModel):
    """
    Shared stability-profile fields.
    """

    name: str = Field(
        min_length=1,
        max_length=100,
        examples=["default"],
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    minimum_samples: int = Field(
        default=3,
        ge=2,
        le=100,
    )

    window_seconds: float = Field(
        default=1.0,
        gt=0,
        le=60,
    )

    maximum_variation_lb: float = Field(
        default=2.0,
        ge=0,
        le=1000,
    )

    is_active: bool = True


class StabilityProfileCreate(StabilityProfileBase):
    """
    Request body used to create a stability profile.
    """

    pass


class StabilityProfileUpdate(APIModel):
    """
    Request body used to update selected stability-profile fields.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    minimum_samples: int | None = Field(
        default=None,
        ge=2,
        le=100,
    )

    window_seconds: float | None = Field(
        default=None,
        gt=0,
        le=60,
    )

    maximum_variation_lb: float | None = Field(
        default=None,
        ge=0,
        le=1000,
    )

    is_active: bool | None = None


class StabilityProfileResponse(StabilityProfileBase):
    """
    Stability profile returned by the API.
    """

    id: str
    created_at: datetime
    updated_at: datetime


# ============================================================
# Scales
# ============================================================


class ScaleBase(APIModel):
    """
    Shared scale fields.
    """

    scale_key: str = Field(
        min_length=1,
        max_length=150,
        examples=["dcc-chute-scale-01"],
    )

    name: str = Field(
        min_length=1,
        max_length=200,
        examples=["DCC Pearson Chute Scale"],
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
        examples=["SellEton"],
    )

    model: str | None = Field(
        default=None,
        max_length=150,
    )

    serial_number: str | None = Field(
        default=None,
        max_length=150,
    )

    adapter_type: str = Field(
        default="manual",
        min_length=1,
        max_length=100,
        examples=["rs232"],
    )

    connection_type: str | None = Field(
        default=None,
        max_length=100,
        examples=["serial"],
    )

    capacity_lb: float | None = Field(
        default=None,
        gt=0,
    )

    minimum_weight_lb: float | None = Field(
        default=None,
        ge=0,
    )

    resolution_lb: float | None = Field(
        default=None,
        gt=0,
    )

    location_id: str | None = Field(
        default=None,
        max_length=150,
    )

    stability_profile_id: str | None = None

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
    )

    @field_validator("scale_key")
    @classmethod
    def normalize_scale_key(cls, value: str) -> str:
        """
        Normalize the scale key so accidental spaces do not create
        separate registrations.
        """

        normalized = value.strip().lower()

        if not normalized:
            raise ValueError("scale_key cannot be empty")

        return normalized

    @field_validator(
        "name",
        "manufacturer",
        "model",
        "serial_number",
        "adapter_type",
        "connection_type",
        "location_id",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        """
        Remove accidental leading and trailing spaces.
        """

        if isinstance(value, str):
            value = value.strip()

            if value == "":
                return None

        return value

    @model_validator(mode="after")
    def validate_scale_limits(self) -> "ScaleBase":
        """
        Make sure scale limits make physical sense.
        """

        if (
            self.capacity_lb is not None
            and self.minimum_weight_lb is not None
            and self.minimum_weight_lb > self.capacity_lb
        ):
            raise ValueError(
                "minimum_weight_lb cannot be greater than capacity_lb"
            )

        if (
            self.capacity_lb is not None
            and self.resolution_lb is not None
            and self.resolution_lb > self.capacity_lb
        ):
            raise ValueError(
                "resolution_lb cannot be greater than capacity_lb"
            )

        return self


class ScaleRegisterRequest(ScaleBase):
    """
    Request body used by POST /scales/register.
    """

    pass


class ScaleUpdateRequest(APIModel):
    """
    Request body used to update an existing scale.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
    )

    manufacturer: str | None = Field(
        default=None,
        max_length=150,
    )

    model: str | None = Field(
        default=None,
        max_length=150,
    )

    serial_number: str | None = Field(
        default=None,
        max_length=150,
    )

    adapter_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    connection_type: str | None = Field(
        default=None,
        max_length=100,
    )

    operational_state: ScaleState | None = None

    capacity_lb: float | None = Field(
        default=None,
        gt=0,
    )

    minimum_weight_lb: float | None = Field(
        default=None,
        ge=0,
    )

    resolution_lb: float | None = Field(
        default=None,
        gt=0,
    )

    location_id: str | None = Field(
        default=None,
        max_length=150,
    )

    stability_profile_id: str | None = None

    metadata_json: dict[str, Any] | None = Field(
        default=None,
        alias="metadata",
    )


class ScaleResponse(ScaleBase):
    """
    Registered scale returned by the API.
    """

    id: str
    operational_state: ScaleState
    last_seen_at: datetime | None
    registered_at: datetime
    updated_at: datetime


class ScaleRegistrationResponse(APIModel):
    """
    Response returned by POST /scales/register.

    created=True means HTTP 201.
    created=False means the scale already existed and HTTP 200 is returned.
    """

    created: bool
    scale: ScaleResponse


# ============================================================
# Heartbeats
# ============================================================


class HeartbeatRequest(APIModel):
    """
    Health signal sent by a scale bridge or adapter.
    """

    status: ScaleState = "ONLINE"

    firmware_version: str | None = Field(
        default=None,
        max_length=100,
    )

    adapter_version: str | None = Field(
        default=None,
        max_length=100,
    )

    message: str | None = Field(
        default=None,
        max_length=2000,
    )

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
    )

    observed_at: datetime | None = None


class HeartbeatResponse(APIModel):
    """
    Stored heartbeat returned by the API.
    """

    id: str
    scale_id: str
    status: ScaleState
    firmware_version: str | None
    adapter_version: str | None
    message: str | None
    metadata_json: dict[str, Any] = Field(alias="metadata")
    observed_at: datetime
    received_at: datetime


# ============================================================
# Sessions
# ============================================================


class SessionCreateRequest(APIModel):
    """
    Request body used to open a weighing session.
    """

    scale_id: str

    session_key: str | None = Field(
        default=None,
        max_length=150,
        examples=["dcc-chute-2026-07-26-am"],
    )

    name: str | None = Field(
        default=None,
        max_length=200,
        examples=["Morning Chute Session"],
    )

    location_id: str | None = Field(
        default=None,
        max_length=150,
    )

    opened_by: str | None = Field(
        default=None,
        max_length=150,
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
    )

    opened_at: datetime | None = None

    @field_validator("session_key", mode="before")
    @classmethod
    def normalize_session_key(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower()

            if value == "":
                return None

        return value


class SessionCloseRequest(APIModel):
    """
    Request body used to close a weighing session.
    """

    closed_by: str | None = Field(
        default=None,
        max_length=150,
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    closed_at: datetime | None = None


class SessionResponse(APIModel):
    """
    Weighing session returned by the API.
    """

    id: str
    scale_id: str
    session_key: str | None
    name: str | None
    status: SessionState
    location_id: str | None
    opened_by: str | None
    closed_by: str | None
    notes: str | None
    metadata_json: dict[str, Any] = Field(alias="metadata")
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# Raw Readings
# ============================================================


class RawReadingCreateRequest(APIModel):
    """
    Canonical weight reading received from an adapter.

    The adapter may send pounds or kilograms.
    The service will normalize both.
    """

    scale_id: str

    session_id: str | None = None

    channel_id: str | None = Field(
        default=None,
        max_length=100,
    )

    raw_weight: float

    raw_unit: WeightUnit

    device_stable: bool | None = None

    source_packet: str | None = Field(
        default=None,
        max_length=20000,
    )

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
    )

    observed_at: datetime | None = None

    tare_weight: float = Field(
        default=0.0,
        ge=0,
        description=(
            "Tare value expressed in the same unit as raw_weight."
        ),
    )

    rfid_tag_id: str | None = Field(
        default=None,
        max_length=200,
    )

    location_id: str | None = Field(
        default=None,
        max_length=150,
    )

    @field_validator("raw_unit")
    @classmethod
    def normalize_weight_unit(cls, value: str) -> str:
        """
        Convert all accepted unit spellings to lb or kg.
        """

        normalized = value.strip().lower()

        pound_units = {
            "lb",
            "lbs",
            "pound",
            "pounds",
        }

        kilogram_units = {
            "kg",
            "kilogram",
            "kilograms",
        }

        if normalized in pound_units:
            return "lb"

        if normalized in kilogram_units:
            return "kg"

        raise ValueError(
            "raw_unit must represent pounds or kilograms"
        )

    @model_validator(mode="after")
    def validate_tare(self) -> "RawReadingCreateRequest":
        """
        Tare cannot be larger than gross raw weight when the raw weight
        is positive.
        """

        if self.raw_weight >= 0 and self.tare_weight > self.raw_weight:
            raise ValueError(
                "tare_weight cannot be greater than raw_weight"
            )

        return self


class RawReadingResponse(APIModel):
    """
    Preserved raw reading returned by the API.
    """

    id: str
    scale_id: str
    session_id: str | None
    channel_id: str | None

    raw_weight: float
    raw_unit: str

    weight_lb: float
    weight_kg: float

    device_stable: bool | None

    validation_status: ValidationState
    validation_message: str | None

    source_packet: str | None

    metadata_json: dict[str, Any] = Field(alias="metadata")

    observed_at: datetime
    received_at: datetime


class ReadingIngestResponse(APIModel):
    """
    Response returned after a raw reading is ingested.

    A reading may or may not create an accepted weight event.
    """

    reading: RawReadingResponse

    stable_event_created: bool = False

    weight_event: WeightEventResponse | None = None


# ============================================================
# Weight Events
# ============================================================


class WeightEventResponse(APIModel):
    """
    Accepted stable weight event returned by the API.
    """

    id: str
    scale_id: str
    session_id: str | None
    channel_id: str | None

    gross_weight_lb: float
    tare_weight_lb: float
    net_weight_lb: float

    gross_weight_kg: float
    tare_weight_kg: float
    net_weight_kg: float

    stable: bool

    stability_profile_id: str | None

    sample_count: int | None
    variation_lb: float | None

    rfid_tag_id: str | None
    location_id: str | None

    is_duplicate: bool
    duplicate_of: str | None

    raw_evidence_hash: str | None
    normalized_evidence_hash: str | None

    metadata_json: dict[str, Any] = Field(alias="metadata")

    observed_at: datetime
    accepted_at: datetime


class ManualWeightEventRequest(APIModel):
    """
    Optional request body for manually creating an accepted weight event.

    This is useful for manual-entry adapters, testing, migration,
    and hardware that already performs its own stability calculation.
    """

    scale_id: str

    session_id: str | None = None

    channel_id: str | None = Field(
        default=None,
        max_length=100,
    )

    gross_weight: float

    tare_weight: float = Field(
        default=0.0,
        ge=0,
    )

    unit: WeightUnit

    rfid_tag_id: str | None = Field(
        default=None,
        max_length=200,
    )

    location_id: str | None = Field(
        default=None,
        max_length=150,
    )

    observed_at: datetime | None = None

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        alias="metadata",
    )

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        normalized = value.strip().lower()

        if normalized in {
            "lb",
            "lbs",
            "pound",
            "pounds",
        }:
            return "lb"

        if normalized in {
            "kg",
            "kilogram",
            "kilograms",
        }:
            return "kg"

        raise ValueError(
            "unit must represent pounds or kilograms"
        )

    @model_validator(mode="after")
    def validate_manual_weight(self) -> "ManualWeightEventRequest":
        if self.gross_weight >= 0 and self.tare_weight > self.gross_weight:
            raise ValueError(
                "tare_weight cannot be greater than gross_weight"
            )

        return self


class WeightEventCreateResponse(APIModel):
    """
    Response returned when the service creates or detects a weight event.

    duplicate=True means HTTP 200.
    duplicate=False means HTTP 201.
    """

    duplicate: bool
    event: WeightEventResponse


# ============================================================
# List and Pagination Responses
# ============================================================


class ScaleListResponse(APIModel):
    """
    Paginated list of scales.
    """

    items: list[ScaleResponse]
    total: int
    limit: int
    offset: int


class HeartbeatListResponse(APIModel):
    """
    Paginated list of heartbeats.
    """

    items: list[HeartbeatResponse]
    total: int
    limit: int
    offset: int


class SessionListResponse(APIModel):
    """
    Paginated list of weighing sessions.
    """

    items: list[SessionResponse]
    total: int
    limit: int
    offset: int


class RawReadingListResponse(APIModel):
    """
    Paginated list of raw readings.
    """

    items: list[RawReadingResponse]
    total: int
    limit: int
    offset: int


class WeightEventListResponse(APIModel):
    """
    Paginated list of accepted weight events.
    """

    items: list[WeightEventResponse]
    total: int
    limit: int
    offset: int
