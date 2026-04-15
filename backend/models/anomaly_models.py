"""
Anomaly Models — Pydantic Schemas for /anomaly
================================================
Defines the request and response shapes for anomaly ingestion and queries.

Used by:
  - routes/anomaly.py for input validation
  - services/anomaly_service.py as the contract for ingest() and get_active()
"""

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


class AnomalyLocation(BaseModel):
    """Location can be specified as lat/lng or as a graph edge ID."""

    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    edge_id: Optional[str] = Field(
        None, description="Direct edge identifier in the graph"
    )


class AnomalyTarget(BaseModel):
    type: Literal["edge", "bbox"] = "edge"
    edge_ids: list[str] = Field(default_factory=list)
    bbox: Optional[list[float]] = Field(
        None,
        description="[south, west, north, east]",
        min_length=4,
        max_length=4,
    )


class AnomalyEffects(BaseModel):
    weight_multiplier: dict[str, float] = Field(default_factory=dict)
    disable_modes: list[str] = Field(default_factory=list)


class AnomalyReport(BaseModel):
    """
    Incoming anomaly report from external data sources or manual input.

    Severity levels map to weight multipliers defined in config.json:
      - low:      1.2x (minor slowdown)
      - medium:   1.8x (noticeable delay)
      - high:     3.0x (major delay)
      - critical: effectively blocked (max weight)
    """

    location: Optional[AnomalyLocation] = None
    edge_ids: list[str] = Field(default_factory=list)
    vehicle_types: list[str] = Field(default_factory=list)
    target: Optional[AnomalyTarget] = None
    effects: Optional[AnomalyEffects] = None
    severity: float | str = Field(
        ...,
        description="Severity label (low/medium/high/critical) or numeric weight multiplier (> 0)",
        examples=["high", 5],
    )
    type: str = Field(
        ...,
        description="Anomaly type: 'accident', 'closure', 'congestion', 'weather', 'construction'",
        examples=["accident"],
    )
    description: Optional[str] = Field(None, description="Human-readable description")
    duration_minutes: Optional[int] = Field(
        None,
        description="Estimated duration in minutes (defaults to config auto_expire_minutes)",
    )
    ttl: Optional[int] = Field(
        None,
        description="TTL in seconds (optional). If provided, overrides duration_minutes.",
    )
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class ActiveAnomaly(BaseModel):
    """An anomaly currently affecting the graph."""

    anomaly_id: str
    location: Optional[AnomalyLocation] = None
    edge_ids: list[str] = Field(default_factory=list)
    vehicle_types: list[str] = Field(default_factory=list)
    target: Optional[AnomalyTarget] = None
    effects: Optional[AnomalyEffects] = None
    severity: float
    type: str
    description: Optional[str] = None
    affected_edges: list[str] = Field(default_factory=list)
    weight_multiplier: float = 1.0
    created_at: datetime
    expires_at: datetime


class AnomalyListResponse(BaseModel):
    """Response for GET /anomaly — list of active anomalies."""

    anomalies: list[ActiveAnomaly]
    count: int
