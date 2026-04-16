"""
GoliTransit Backend — Application Entry Point
================================================
This is the main FastAPI application file. It:
  1. Initializes the FastAPI app with CORS middleware
  2. Creates database tables on startup
  3. Mounts all route modules (/health, /auth, /route, /anomaly, /graph)
  4. Triggers graph loading on startup via lifespan events

All business logic lives in the `services/` layer — routes are thin
wrappers that validate input, delegate to services, and return responses.
"""

import os
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base
from models import user_models, traffic_models  # noqa: F401
from routes import health, auth, route, anomaly, graph, traffic
from routes.v2 import router as v2_router
from services.ml_integration import ml_integration
from services.traffic_jam_service import traffic_jam_service
from services.graph_service import graph_service


# ─── Lifespan: load the road graph once at startup ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup:
      - Create database tables if they don't exist
      - Preload graph from cache (fast) or OSM (slow first time)
    On shutdown: clean up resources.
    """
    print("[startup] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[startup] Database tables created/verified")

    # ─── Preload graph on startup ────────────────────────
    preload_graph = os.getenv("PRELOAD_GRAPH", "1").lower() in {"1", "true", "yes"}
    use_cache = os.getenv("USE_GRAPH_CACHE", "1").lower() in {"1", "true", "yes"}
    
    if preload_graph:
        try:
            print(f"[startup] Preloading graph (cache={'enabled' if use_cache else 'disabled'})...")
            load_start = time.time()
            graph_service.ensure_loaded()
            load_time = time.time() - load_start
            
            if graph_service._graph:
                print(
                    f"[startup] ✓ Graph loaded in {load_time:.2f}s "
                    f"({graph_service._graph.number_of_nodes()} nodes, "
                    f"{graph_service._graph.number_of_edges()} edges)"
                )
            else:
                print(f"[startup] ⚠ Graph preload failed, will load on first request")
        except Exception as e:
            print(f"[startup] ⚠ Graph preload error: {e}")
    else:
        print("[startup] Graph preload disabled - will load on demand")

    yield
    print("[shutdown] Cleaning up resources...")
    await traffic_jam_service.stop_workers()
    await ml_integration.close()


# ─── App Initialization ──────────────────────────────────────────
app = FastAPI(
    title="GoliTransit API",
    description="Multi-modal hyper-local routing engine with real-time anomaly handling and ML-based congestion prediction.",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── CORS (allow frontend dev server) ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mount Routers ───────────────────────────────────────────────
# Each router is defined in its own file under routes/
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, tags=["Authentication"])
app.include_router(route.router, prefix="/route", tags=["Routing"])
app.include_router(traffic.router, prefix="/traffic", tags=["Traffic"])
app.include_router(anomaly.router, prefix="/anomaly", tags=["Anomaly"])
app.include_router(graph.router, prefix="/graph", tags=["Graph"])
app.include_router(v2_router, prefix="/v2", tags=["V2 — Multi-Modal Dijkstra"])
