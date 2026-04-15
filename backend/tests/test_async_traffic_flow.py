"""
Async Traffic Flow Tests
========================
Validate that route responses are not blocked by traffic prediction and
that traffic status can be polled until ready.
"""

import asyncio
import time

import networkx as nx
import pytest

from services.graph_service import graph_service
from services.routing_engine import routing_engine
from services.traffic_jam_service import traffic_jam_service


def _build_min_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=90.50010, y=23.70010)
    graph.add_node(2, x=90.50030, y=23.70030)

    edge_data = {
        "length": 120.0,
        "travel_time": 12.0,
        "base_travel_time": 12.0,
        "road_type": "residential",
        "car_allowed": True,
        "bike_allowed": True,
        "walk_allowed": True,
        "rickshaw_allowed": True,
        "transit_allowed": True,
        "car_travel_time": 12.0,
        "bike_travel_time": 10.0,
        "walk_travel_time": 40.0,
        "rickshaw_travel_time": 16.0,
        "transit_travel_time": 18.0,
        "weights": {
            "car": 12.0,
            "bike": 10.0,
            "walk": 40.0,
            "rickshaw": 16.0,
            "transit": 18.0,
        },
        "constraints": {
            "car_allowed": True,
            "bike_allowed": True,
            "walk_allowed": True,
            "rickshaw_allowed": True,
            "transit_allowed": True,
        },
    }

    graph.add_edge(1, 2, key=0, **edge_data)
    graph.add_edge(2, 1, key=0, **edge_data)
    return graph


@pytest.mark.asyncio
async def test_route_returns_immediately_while_traffic_loads(client, monkeypatch):
    graph = _build_min_graph()

    monkeypatch.setattr(graph_service, "is_loaded", lambda: True)
    monkeypatch.setattr(graph_service, "get_graph", lambda: graph)
    monkeypatch.setattr(graph_service, "get_subgraph_for_mode", lambda mode: graph)
    monkeypatch.setattr(
        graph_service,
        "get_k_nearest_nodes_in_graph",
        lambda _g, lat, lng, k=8: [1] if lat < 23.70020 else [2],
    )

    routing_engine._route_response_cache.clear()
    routing_engine._shortest_tree_cache.clear()
    await traffic_jam_service.stop_workers()
    await traffic_jam_service.start_workers(worker_count=2)
    traffic_jam_service._route_predictions.clear()
    traffic_jam_service._route_prediction_tasks.clear()

    def slow_predict(_edge_contexts: list[dict], hour_of_day=None):
        del hour_of_day
        time.sleep(0.35)
        return {
            "hour_of_day": 8,
            "route_jam_chance_pct": 37.5,
            "edges_analyzed": 2,
            "heavy_edges": 0,
            "moderate_edges": 1,
            "low_edges": 1,
            "confidence": 0.91,
        }

    monkeypatch.setattr(traffic_jam_service, "predict_route_jam", slow_predict)

    request = {
        "origin": {"lat": 23.70010, "lng": 90.50010},
        "destination": {"lat": 23.70030, "lng": 90.50030},
        "modes": ["car"],
        "optimize": "time",
        "avoid_anomalies": True,
    }

    started = time.perf_counter()
    response = await client.post("/route", json=request)
    elapsed_s = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed_s < 0.2

    body = response.json()
    assert body.get("traffic_status") == "loading"
    route_id = body.get("route_id")
    assert route_id

    first_poll = await client.get(f"/traffic/{route_id}")
    assert first_poll.status_code == 200
    assert first_poll.json().get("status") in {"loading", "ready"}
    assert first_poll.json().get("job_status") in {"pending", "running", "completed"}

    final_payload = None
    for _ in range(40):
        poll = await client.get(f"/traffic/{route_id}")
        assert poll.status_code == 200
        payload = poll.json()
        if payload.get("status") == "ready":
            final_payload = payload
            break
        await asyncio.sleep(0.05)

    assert final_payload is not None
    assert final_payload.get("status") == "ready"
    assert final_payload.get("job_status") == "completed"
    assert int(final_payload.get("retry_count") or 0) >= 0
    assert final_payload.get("data") is not None


@pytest.mark.asyncio
async def test_traffic_endpoint_unknown_route_returns_404(client):
    response = await client.get("/traffic/unknown-route-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_traffic_job_retries_then_completes(client, monkeypatch):
    attempts = {"count": 0}
    original_retry_limit = traffic_jam_service._max_job_retries

    await traffic_jam_service.stop_workers()
    traffic_jam_service._max_job_retries = 3
    await traffic_jam_service.start_workers(worker_count=2)
    traffic_jam_service._route_predictions.clear()

    def flaky_predict(_edge_contexts: list[dict], hour_of_day=None):
        del hour_of_day
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient traffic model failure")
        return {
            "hour_of_day": 9,
            "route_jam_chance_pct": 28.0,
            "edges_analyzed": 1,
            "heavy_edges": 0,
            "moderate_edges": 1,
            "low_edges": 0,
            "confidence": 0.85,
        }

    monkeypatch.setattr(traffic_jam_service, "predict_route_jam", flaky_predict)

    queued = traffic_jam_service.start_route_prediction(
        edge_contexts=[{"edge_id": "e1", "road_type": "residential", "length_m": 80.0}],
        hour_of_day=9,
    )
    route_id = queued.get("route_id")
    assert route_id

    final_payload = None
    for _ in range(80):
        poll = await client.get(f"/traffic/{route_id}")
        assert poll.status_code == 200
        payload = poll.json()
        if payload.get("status") == "ready":
            final_payload = payload
            break
        await asyncio.sleep(0.05)

    traffic_jam_service._max_job_retries = original_retry_limit

    assert final_payload is not None
    assert final_payload.get("status") == "ready"
    assert final_payload.get("job_status") == "completed"
    assert int(final_payload.get("retry_count") or 0) >= 2
    assert attempts["count"] >= 3


@pytest.mark.asyncio
async def test_traffic_job_marks_failed_after_retry_exhaustion(client, monkeypatch):
    original_retry_limit = traffic_jam_service._max_job_retries

    await traffic_jam_service.stop_workers()
    traffic_jam_service._max_job_retries = 1
    await traffic_jam_service.start_workers(worker_count=2)
    traffic_jam_service._route_predictions.clear()

    def always_fail(_edge_contexts: list[dict], hour_of_day=None):
        del hour_of_day
        raise RuntimeError("persistent traffic model failure")

    monkeypatch.setattr(traffic_jam_service, "predict_route_jam", always_fail)

    queued = traffic_jam_service.start_route_prediction(
        edge_contexts=[
            {"edge_id": "e_fail", "road_type": "residential", "length_m": 90.0}
        ],
        hour_of_day=10,
    )
    route_id = queued.get("route_id")
    assert route_id

    final_payload = None
    for _ in range(80):
        poll = await client.get(f"/traffic/{route_id}")
        assert poll.status_code == 200
        payload = poll.json()
        if payload.get("status") == "failed":
            final_payload = payload
            break
        await asyncio.sleep(0.05)

    traffic_jam_service._max_job_retries = original_retry_limit

    assert final_payload is not None
    assert final_payload.get("status") == "failed"
    assert final_payload.get("job_status") == "failed"
    assert int(final_payload.get("retry_count") or 0) >= 2
    assert "failure" in str(final_payload.get("error") or "").lower()
