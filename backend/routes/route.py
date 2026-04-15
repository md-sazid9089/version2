"""
Routing Endpoint — POST /route
================================
Accepts an origin, destination, and transport mode(s), then returns
the optimal route(s) computed by the routing engine.

Integration:
  - Validates input using models/route_models.py (Pydantic)
  - Delegates computation to services/routing_engine.py
  - Routing engine internally calls services/ml_integration.py for
    ML-predicted edge weights when available
  - Routing engine reads the graph from services/graph_service.py
"""

from fastapi import APIRouter, HTTPException

from models.route_models import RouteRequest, RouteResponse
from services.routing_engine import routing_engine

router = APIRouter()


@router.post("", response_model=RouteResponse)
async def compute_route(request: RouteRequest):
    """
    Compute a single-modal or multi-modal route.

    Body:
      - origin: { lat, lng }
      - destination: { lat, lng }
      - modes: list of transport modes (e.g. ["car"], ["walk", "transit", "walk"])
      - optimize: "time" | "distance" | "cost"
      - avoid_anomalies: bool (default true)

    Returns:
      - legs: list of route legs with geometry, distance, duration
      - total_distance_m, total_duration_s, total_cost
      - alternatives: optional additional routes
    """
    try:
        result = await routing_engine.compute(request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")
