# backend/services/__init__.py
"""
Services Package
==================
Core business logic layer. Routes delegate all computation here.

Modules:
  - graph_service.py     → OSM import, NetworkX graph management, snapshots
  - routing_engine.py    → Single-modal & multi-modal path computation
  - anomaly_service.py   → Anomaly storage, graph weight modification, expiry
  - ml_integration.py    → HTTP client for ML prediction service

Dependency graph:
  routing_engine → graph_service (reads graph)
  routing_engine → ml_integration (gets predicted edge weights)
  routing_engine → anomaly_service (checks rerouting flags)
  anomaly_service → graph_service (modifies edge weights)
  ml_integration → external ML service (HTTP)
"""
