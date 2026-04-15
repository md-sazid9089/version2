"""
Route Models — Pydantic Schemas for /route
============================================
Defines the request and response shapes for route computation.

Used by:
  - routes/route.py for input validation and response serialization
  - services/routing_engine.py as the contract for compute()
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class LatLng(BaseModel):
    """Geographic coordinate."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")


class RouteRequest(BaseModel):
    """
    Input for a route computation.

    For single-modal: modes = ["car"]
    For multi-modal: modes = ["walk", "transit", "walk"]
    The order of modes defines the sequence of legs.
    """

    origin: LatLng
    destination: LatLng
    modes: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of transport modes for each leg",
        examples=[["car"], ["walk", "transit", "walk"]],
    )
    optimize: str = Field(
        "time",
        description="Optimization criterion: 'time', 'distance', or 'cost'",
    )
    avoid_anomalies: bool = Field(
        True,
        description="Whether to avoid edges affected by active anomalies",
    )
    max_alternatives: Optional[int] = Field(
        None,
        description="Number of alternative routes to return (overrides config default)",
    )
    include_multimodal: bool = Field(
        False,
        description="When true, include multimodal segment suggestions in response",
    )
    traffic_hour_of_day: Optional[int] = Field(
        None,
        ge=0,
        le=23,
        description="Hour in user's local device time to evaluate traffic jam risk (0-23). If omitted, backend current hour is used.",
    )


class RouteLeg(BaseModel):
    """A single leg of a route (one transport mode)."""

    mode: str = Field(..., description="Transport mode for this leg")
    geometry: list[LatLng] = Field(
        default_factory=list,
        description="Ordered list of coordinates forming the leg polyline",
    )
    distance_m: float = Field(0.0, description="Leg distance in meters")
    duration_s: float = Field(0.0, description="Leg duration in seconds")
    cost: float = Field(0.0, description="Estimated cost for this leg")
    instructions: list[str] = Field(
        default_factory=list,
        description="Turn-by-turn navigation instructions",
    )
    traffic_edges: list["RouteTrafficEdge"] = Field(
        default_factory=list,
        description="Road-edge references used for traffic jam prediction",
    )


class RouteTrafficEdge(BaseModel):
    """Edge metadata used by traffic-jam prediction."""

    edge_id: str
    road_type: str = "unknown"
    length_m: float = 0.0


class ModeSwitch(BaseModel):
    """Represents a mode transfer point between two legs."""

    from_mode: str
    to_mode: str
    location: LatLng
    penalty_time_s: float = 0.0
    penalty_cost: float = 0.0


class VehicleOption(BaseModel):
    """Travel-time option for one vehicle on one segment."""

    vehicle: str
    travel_time_s: float = 0.0
    allowed: bool = True


class SegmentSuggestion(BaseModel):
    """Segment-level multimodal recommendation."""

    segment_index: int
    distance_m: float = 0.0
    road_type: str = "unknown"
    recommended_vehicle: str
    geometry: list[LatLng] = Field(default_factory=list)
    vehicle_options: list[VehicleOption] = Field(default_factory=list)


class MultimodalSuggestion(BaseModel):
    """Route-wide recommendation strategy (distance-first or time-first)."""

    strategy: str
    total_distance_m: float = 0.0
    total_duration_s: float = 0.0
    segments: list[SegmentSuggestion] = Field(default_factory=list)


class TrafficJamPrediction(BaseModel):
    """Route-level chance of hitting traffic jam for the selected hour."""

    hour_of_day: int = Field(..., ge=0, le=23)
    route_jam_chance_pct: float = Field(..., ge=0.0, le=100.0)
    edges_analyzed: int = 0
    heavy_edges: int = 0
    moderate_edges: int = 0
    low_edges: int = 0
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class RouteResponse(BaseModel):
    """Full response for a route computation."""

    legs: list[RouteLeg]
    mode_switches: list[ModeSwitch] = Field(default_factory=list)
    total_distance_m: float = 0.0
    total_duration_s: float = 0.0
    total_cost: float = 0.0
    anomalies_avoided: int = Field(
        0, description="Number of anomaly-affected edges bypassed"
    )
    alternatives: list[list[RouteLeg]] = Field(
        default_factory=list,
        description="Alternative route options",
    )
    multimodal_suggestions: list[MultimodalSuggestion] = Field(
        default_factory=list,
        description="Segment-wise vehicle suggestions for shortest-distance and fastest-time strategies",
    )
    traffic_jam_prediction: Optional[TrafficJamPrediction] = Field(
        default=None,
        description="Predicted chance (percentage) of facing traffic jam on the selected route at current hour",
    )
    route_id: Optional[str] = Field(
        default=None,
        description="Opaque ID used to fetch asynchronous traffic prediction status.",
    )
    traffic_status: Literal["loading", "ready", "failed", "unavailable"] = Field(
        default="unavailable",
        description="Traffic prediction lifecycle state for this route.",
    )


class RouteTrafficStatusResponse(BaseModel):
    route_id: str
    status: Literal["loading", "ready", "failed"]
    job_status: Literal["pending", "running", "completed", "failed"]
    retry_count: int = 0
    max_retries: int = 0
    updated_at: float = 0.0
    data: Optional[TrafficJamPrediction] = None
    error: Optional[str] = None
