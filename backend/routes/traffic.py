"""
Traffic Endpoint — GET /traffic/{route_id}
===========================================
Returns background traffic prediction status for a previously computed route.
"""

from fastapi import APIRouter, HTTPException

from models.route_models import RouteTrafficStatusResponse
from services.traffic_jam_service import traffic_jam_service

router = APIRouter()


@router.get("/{route_id}", response_model=RouteTrafficStatusResponse)
async def get_route_traffic(route_id: str):
    """Fetch asynchronous traffic status for a route_id returned by POST /route."""
    payload = traffic_jam_service.get_route_prediction(route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Unknown route_id")
    return payload
