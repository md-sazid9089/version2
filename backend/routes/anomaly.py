"""
Anomaly Endpoint — POST /anomaly & GET /anomaly
=================================================
Handles ingestion of real-time traffic anomalies (accidents, closures,
weather events) and retrieval of active anomalies.

Integration:
  - Validates input via models/anomaly_models.py
  - Delegates to services/anomaly_service.py for storage and graph weight updates
  - Anomaly service modifies edge weights in services/graph_service.py
    so that subsequent routing calls automatically avoid/de-prioritize
    affected edges
"""

from fastapi import APIRouter, HTTPException

from models.anomaly_models import AnomalyReport, AnomalyListResponse
from services.anomaly_service import anomaly_service
from services.graph_service import graph_service

router = APIRouter()


@router.post("", status_code=201)
async def report_anomaly(report: AnomalyReport):
    """
    Ingest a new traffic anomaly.

    Body:
      - location: { lat, lng } or edge_id
      - severity: numeric multiplier (e.g. 5)
      - type: "accident" | "closure" | "congestion" | "weather" | "construction"
      - description: optional human-readable description
      - duration_minutes: estimated duration (default: from config auto_expire)

    The anomaly service will:
      1. Store the anomaly in the active anomaly list
      2. Update the affected edges' weights in the graph using the
         severity multiplier from config.json
      3. If severity >= reroute_on_severity, flag for dynamic rerouting
    """
    try:
        needs_graph_resolution = bool(
            (report.target is not None and report.target.type == "bbox")
            or (
                report.location is not None
                and report.location.lat is not None
                and report.location.lng is not None
            )
            or (
                report.location is not None
                and str(report.location.edge_id or "") == "*"
            )
        )
        if needs_graph_resolution:
            graph_service.ensure_loaded(raise_on_error=False)

        anomaly_id = await anomaly_service.ingest(report)
        active = await anomaly_service.get_active()
        created = next((a for a in active if a.anomaly_id == anomaly_id), None)
        return {
            "anomaly_id": anomaly_id,
            "status": "accepted",
            "affected_edges": len(created.edge_ids) if created else 0,
            "edge_ids": created.edge_ids if created else [],
            "vehicle_types": created.vehicle_types if created else [],
            "severity": created.severity if created else report.severity,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=AnomalyListResponse)
async def list_anomalies():
    """
    Return all currently active anomalies.
    Expired anomalies are automatically pruned.
    """
    active = await anomaly_service.get_active()
    return AnomalyListResponse(anomalies=active, count=len(active))


@router.delete("")
async def clear_anomalies():
    cleared = await anomaly_service.clear_all()
    return {"status": "cleared", "count": cleared}
