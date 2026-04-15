"""
Routing Tests — Verify /route endpoint and routing engine
===========================================================
Tests cover:
  - Health check returns valid status
  - Single-modal route returns expected response shape
  - Multi-modal route includes mode switches
  - Invalid mode returns 400
  - Route response aggregates totals correctly

NOTE: These tests run against the stub implementation.
      Once NetworkX integration is complete, tests should be updated
      with real graph fixtures for meaningful pathfinding assertions.
"""

import pytest


# ─── Health Check ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check(client):
    """GET /health should return the canonical ok payload."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ─── Single-Modal Routing ───────────────────────────────────────


@pytest.mark.asyncio
async def test_single_modal_route(client, sample_route_request):
    """POST /route with a single mode should return a valid response."""
    response = await client.post("/route", json=sample_route_request)
    assert response.status_code == 200
    data = response.json()

    # Should have exactly one leg
    assert len(data["legs"]) == 1
    assert data["legs"][0]["mode"] == "car"

    # Should have totals
    assert "total_distance_m" in data
    assert "total_duration_s" in data
    assert "total_cost" in data

    # Should have no mode switches (single modal)
    assert len(data["mode_switches"]) == 0


@pytest.mark.asyncio
async def test_single_modal_route_bike(client):
    """POST /route with bike mode should return a valid response."""
    request = {
        "origin": {"lat": 37.7749, "lng": -122.4194},
        "destination": {"lat": 37.7799, "lng": -122.4144},
        "modes": ["bike"],
        "optimize": "distance",
    }
    response = await client.post("/route", json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["legs"][0]["mode"] == "bike"


# ─── Multi-Modal Routing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_multimodal_route(client, sample_multimodal_request):
    """POST /route with multiple modes should return legs + mode switches."""
    response = await client.post("/route", json=sample_multimodal_request)
    assert response.status_code == 200
    data = response.json()

    # Should have three legs (walk → transit → walk)
    assert len(data["legs"]) == 3
    assert data["legs"][0]["mode"] == "walk"
    assert data["legs"][1]["mode"] == "transit"
    assert data["legs"][2]["mode"] == "walk"

    # Should have two mode switches
    assert len(data["mode_switches"]) == 2
    assert data["mode_switches"][0]["from_mode"] == "walk"
    assert data["mode_switches"][0]["to_mode"] == "transit"


# ─── Error Cases ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_mode(client):
    """POST /route with unknown mode should return 400."""
    request = {
        "origin": {"lat": 37.7749, "lng": -122.4194},
        "destination": {"lat": 37.7849, "lng": -122.4094},
        "modes": ["helicopter"],
        "optimize": "time",
    }
    response = await client.post("/route", json=request)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_missing_origin(client):
    """POST /route with missing origin should return 422 (validation error)."""
    request = {
        "destination": {"lat": 37.7849, "lng": -122.4094},
        "modes": ["car"],
    }
    response = await client.post("/route", json=request)
    assert response.status_code == 422


# ─── Response Structure ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_response_has_geometry(client, sample_route_request):
    """Route legs should include geometry (polyline coordinates)."""
    response = await client.post("/route", json=sample_route_request)
    data = response.json()
    leg = data["legs"][0]
    assert "geometry" in leg
    assert len(leg["geometry"]) >= 2  # At least origin and destination


@pytest.mark.asyncio
async def test_route_response_has_instructions(client, sample_route_request):
    """Route legs should include navigation instructions."""
    response = await client.post("/route", json=sample_route_request)
    data = response.json()
    leg = data["legs"][0]
    assert "instructions" in leg
    assert len(leg["instructions"]) > 0
