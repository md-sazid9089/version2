"""
Test Configuration — Shared Fixtures for GoliTransit Backend Tests
====================================================================
Provides:
  - FastAPI TestClient via httpx async client
  - Mock graph service with sample data
  - Test anomaly fixtures
  - Configuration overrides for test mode

Usage:
  All test modules import fixtures from here automatically (pytest convention).
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ─── Override config BEFORE importing the app ────────────────────
# This ensures tests don't try to load a real OSM graph
import os
# Construct the path to config.json in the project root
conf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))
os.environ["CONFIG_PATH"] = conf_path

from main import app


# ─── Async Test Client ──────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """
    Async HTTP client for testing FastAPI endpoints.
    Uses httpx ASGITransport to call the app directly (no network).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ─── Sample Data Fixtures ───────────────────────────────────────

@pytest.fixture
def sample_route_request():
    """A basic single-modal route request."""
    return {
        "origin": {"lat": 37.7749, "lng": -122.4194},
        "destination": {"lat": 37.7849, "lng": -122.4094},
        "modes": ["car"],
        "optimize": "time",
        "avoid_anomalies": True,
    }


@pytest.fixture
def sample_multimodal_request():
    """A multi-modal route request: walk → transit → walk."""
    return {
        "origin": {"lat": 37.7749, "lng": -122.4194},
        "destination": {"lat": 37.8049, "lng": -122.3894},
        "modes": ["walk", "transit", "walk"],
        "optimize": "time",
        "avoid_anomalies": True,
    }


@pytest.fixture
def sample_anomaly_report():
    """A sample anomaly report for testing ingestion."""
    return {
        "location": {"lat": 37.7800, "lng": -122.4100, "edge_id": None},
        "severity": "high",
        "type": "accident",
        "description": "Multi-vehicle collision on Market St",
        "duration_minutes": 45,
    }


@pytest.fixture
def sample_critical_anomaly():
    """A critical anomaly (road closure) for testing rerouting."""
    return {
        "location": {"edge_id": "market_st_seg_3"},
        "severity": "critical",
        "type": "closure",
        "description": "Full road closure for construction",
        "duration_minutes": 120,
    }
