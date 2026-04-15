"""
Anomaly Tests — Verify /anomaly endpoint and anomaly service
===============================================================
Tests cover:
  - Anomaly ingestion returns 201 with anomaly_id
  - GET /anomaly returns active anomaly list
  - Invalid severity returns 400
  - Anomaly response includes expected fields
  - Graph snapshot endpoint returns valid data

NOTE: These tests run against the stub implementation.
      Once graph integration is complete, tests should verify that
      edge weights are actually modified by anomaly ingestion.
"""

import pytest


# ─── Anomaly Ingestion ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_anomaly(client, sample_anomaly_report):
    """POST /anomaly should return 201 with an anomaly_id."""
    response = await client.post("/anomaly", json=sample_anomaly_report)
    assert response.status_code == 201
    data = response.json()
    assert "anomaly_id" in data
    assert data["anomaly_id"].startswith("anomaly_")
    assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_ingest_critical_anomaly(client, sample_critical_anomaly):
    """Critical anomaly ingestion should succeed."""
    response = await client.post("/anomaly", json=sample_critical_anomaly)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"


# ─── Anomaly List ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_anomalies(client, sample_anomaly_report):
    """GET /anomaly should return active anomalies after ingestion."""
    # Ingest an anomaly first
    await client.post("/anomaly", json=sample_anomaly_report)

    # Query active anomalies
    response = await client.get("/anomaly")
    assert response.status_code == 200
    data = response.json()
    assert "anomalies" in data
    assert "count" in data
    assert data["count"] >= 1  # At least the one we just ingested


@pytest.mark.asyncio
async def test_list_anomalies_empty(client):
    """GET /anomaly on a fresh service should return empty or previously ingested."""
    response = await client.get("/anomaly")
    assert response.status_code == 200
    data = response.json()
    assert "anomalies" in data
    assert isinstance(data["anomalies"], list)


# ─── Anomaly Validation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_severity(client):
    """POST /anomaly with invalid severity should return 400."""
    report = {
        "location": {"lat": 37.78, "lng": -122.41},
        "severity": "extreme",  # Not in valid list
        "type": "accident",
    }
    response = await client.post("/anomaly", json=report)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_anomaly_missing_type(client):
    """POST /anomaly with missing type should return 422."""
    report = {
        "location": {"lat": 37.78, "lng": -122.41},
        "severity": "high",
        # Missing "type" field
    }
    response = await client.post("/anomaly", json=report)
    assert response.status_code == 422


# ─── Graph Snapshot ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_graph_snapshot(client):
    """GET /graph/snapshot should return graph statistics."""
    response = await client.get("/graph/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert "node_count" in data
    assert "edge_count" in data
    assert "nodes" in data
    assert "edges" in data


@pytest.mark.asyncio
async def test_graph_snapshot_with_edges(client):
    """GET /graph/snapshot?include_edges=true should include edge data."""
    response = await client.get("/graph/snapshot?include_edges=true")
    assert response.status_code == 200
    data = response.json()
    assert "edges" in data
    # In stub mode edges will be empty, but the field should exist
    assert isinstance(data["edges"], list)


@pytest.mark.asyncio
async def test_graph_snapshot_with_bbox(client):
    """GET /graph/snapshot with bbox should still return valid data."""
    response = await client.get("/graph/snapshot?bbox=37.7,-122.5,37.8,-122.4")
    assert response.status_code == 200
    data = response.json()
    assert "node_count" in data
