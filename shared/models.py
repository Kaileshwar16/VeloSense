from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCENARIOS = (
    "NORMAL",
    "IDLING",
    "SPEEDING",
    "HARSH_BRAKE",
    "HARSH_ACCELERATION",
    "ENGINE_FAULT",
    "LOW_ENERGY",
    "OFFLINE",
    "DUPLICATE_EVENT",
    "OUT_OF_ORDER_EVENT",
    "MALFORMED_EVENT",
    "NETWORK_RECOVERY_BURST",
)


class Vehicle(BaseModel):
    vehicle_id: str = Field(pattern=r"^V\d{6}$")
    vin: str = Field(pattern=r"^SYN\d{14}$")
    fleet_id: str = Field(pattern=r"^F\d{3}$")
    oem: str
    model: str
    fuel_type: Literal["EV", "ICE"]
    manufacture_year: int
    home_region: str
    odometer_km: float


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: UUID
    vehicle_id: str = Field(pattern=r"^V\d{6}$")
    vin: str = Field(pattern=r"^SYN\d{14}$")
    fleet_id: str = Field(pattern=r"^F\d{3}$")
    timestamp: datetime
    seq: int = Field(ge=0)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=220)
    heading_deg: float = Field(ge=0, lt=360)
    engine_on: bool
    fuel_pct: float | None = Field(ge=0, le=100)
    soc_pct: float | None = Field(ge=0, le=100)
    odometer_km: float = Field(ge=0)
    engine_temp_c: float = Field(ge=-40, le=160)
    dtc: list[str] = Field(max_length=16)
    event_type: Literal[
        "NORMAL",
        "IDLING",
        "SPEEDING",
        "HARSH_BRAKE",
        "HARSH_ACCELERATION",
        "ENGINE_FAULT",
        "LOW_ENERGY",
        "OFFLINE",
        "DUPLICATE_EVENT",
        "OUT_OF_ORDER_EVENT",
        "MALFORMED_EVENT",
        "NETWORK_RECOVERY_BURST",
    ]
    source_oem: str = Field(min_length=1, max_length=50)
    schema_version: Literal[1]

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("dtc")
    @classmethod
    def valid_dtc(cls, values: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(r"[PBCU][0-9A-F]{4}", code) for code in values):
            raise ValueError("invalid diagnostic code")
        return values

    @model_validator(mode="after")
    def energy(self):
        if (self.fuel_pct is None) == (self.soc_pct is None):
            raise ValueError("exactly one of fuel_pct and soc_pct must be present")
        return self
