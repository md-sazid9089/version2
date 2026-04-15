"""
Graph Snapshot Endpoint — GET /graph/snapshot
===============================================
Exports the current state of the road graph for debugging, visualization,
and testing. Returns node/edge counts and optionally the full adjacency data.

Integration:
  - Reads directly from services/graph_service.py
  - Useful for the frontend MapView to overlay the graph on Leaflet
  - Useful for debugging anomaly weight modifications
"""

from fastapi import APIRouter, Query

from models.graph_models import GraphSnapshot
from services.graph_service import graph_service

router = APIRouter()


@router.get("/snapshot", response_model=GraphSnapshot)
async def get_graph_snapshot(
    include_edges: bool = Query(
        False, description="Include full edge list (can be large)"
    ),
    bbox: str = Query(None, description="Bounding box filter: 'south,west,north,east'"),
    mode: str = Query(
        None,
        description="Filter nodes by transport mode accessibility (car, bike, walk, transit, rickshaw)",
    ),
    max_nodes: int = Query(
        800, ge=1, le=5000, description="Maximum nodes to include in response"
    ),
    max_edges: int = Query(
        1200,
        ge=1,
        le=10000,
        description="Maximum edges to include when include_edges=true",
    ),
):
    """
    Return a snapshot of the current road graph.

    Query params:
      - include_edges: if true, return the full edge list (warning: large payload)
      - bbox: optional geographic bounding box to filter nodes/edges
      - mode: optional transport mode to filter nodes that are accessible by this mode

    Returns:
      - node_count, edge_count
      - nodes: list of { id, lat, lng, accessible_modes } (always included)
      - edges: list of { source, target, weight, road_type } (if include_edges=true)
      - anomaly_affected_edges: edges with modified weights due to active anomalies
    """
    bbox_tuple = None
    graph_service.ensure_loaded(raise_on_error=False)

    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox_tuple = tuple(parts)
        except ValueError:
            pass  # ignore malformed bbox, return full graph

    snapshot = graph_service.get_snapshot(
        include_edges=include_edges,
        bbox=bbox_tuple,
        mode_filter=mode,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    return snapshot
