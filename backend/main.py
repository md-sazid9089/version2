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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base
from models import user_models, traffic_models  # noqa: F401
from routes import health, auth, route, anomaly, graph, traffic
from routes.v2 import router as v2_router
from services.ml_integration import ml_integration
from services.traffic_jam_service import traffic_jam_service


# ─── Lifespan: load the road graph once at startup ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup:
      - Create database tables if they don't exist
      - Skip graph/model preloading to keep boot memory low
    On shutdown: clean up resources.
    """
    print("[startup] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[startup] Database tables created/verified")

    print("[startup] Lazy runtime enabled - graph and traffic model load on demand")

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
