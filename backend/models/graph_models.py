"""
Graph Models — Pydantic Schemas for /graph
============================================
Defines the shapes for graph snapshot responses.

Used by:
  - routes/graph.py for response serialization
  - services/graph_service.py as the contract for get_snapshot()
"""

from typing import Optional

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A node in the road graph (intersection or endpoint)."""

    id: str = Field(..., description="Unique node identifier (OSM node ID)")
    lat: float
    lng: float
    accessible_modes: list[str] = Field(
        default_factory=list,
        description="List of transport modes that can access this node (car, bike, walk, transit, rickshaw)"
    )


class GraphEdge(BaseModel):
    """An edge in the road graph (road segment)."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    length_m: float = Field(0.0, description="Physical length in meters")
    travel_time_s: float = Field(0.0, description="Current estimated traversal time")
    base_travel_time_s: float = Field(
        0.0, description="Base traversal time without anomalies"
    )
    road_type: str = Field("unknown", description="OSM highway tag value")
    speed_limit_kmh: Optional[float] = None
    anomaly_multiplier: float = Field(
        1.0, description="Current anomaly weight multiplier (1.0 = normal)"
    )
    ml_predicted: bool = Field(
        False, description="Whether travel_time uses ML prediction"
    )
    geometry: list[list[float]] = Field(
        default_factory=list,
        description="Edge polyline as [lat, lng] points",
    )
    weights: dict[str, float] = Field(default_factory=dict)
    allowed_modes: dict[str, bool] = Field(default_factory=dict)
    active_anomalies: list[str] = Field(default_factory=list)


class GraphSnapshot(BaseModel):
    """Full or partial snapshot of the road graph."""

    node_count: int
    edge_count: int
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    anomaly_affected_edges: list[str] = Field(
        default_factory=list,
        description="Edge IDs currently affected by anomalies",
    )
    bbox: Optional[list[float]] = Field(
        None,
        description="Bounding box of the snapshot [south, west, north, east]",
    )
