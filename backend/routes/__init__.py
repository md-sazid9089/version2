# backend/routes/__init__.py
"""
Routes Package
===============
Each module in this package defines a FastAPI APIRouter for a specific
endpoint group. Routers are mounted in main.py.

Modules:
  - health.py  → GET /health
  - route.py   → POST /route
  - traffic.py → GET /traffic/{route_id}
  - anomaly.py → POST /anomaly, GET /anomaly
  - graph.py   → GET /graph/snapshot
  - v2.py      → POST /v2/route, POST /v2/route/coords,
                  POST /v2/anomaly, GET /v2/graph/snapshot
"""
