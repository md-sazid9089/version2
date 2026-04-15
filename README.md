# GoliTransit

Multi-modal hyper-local routing engine that computes road-accurate routes around AUST, adapts to anomalies in real time, and uses a dedicated ML microservice for asynchronous route traffic risk prediction.

## Judge Quick Read (2-3 Minutes)

### Quick Navigation

- Live URLs: [Section 16](#16-live-deployments-and-public-domains)
- Judge demo steps: [Section 17](#17-suggested-judge-demo-flow)
- ML-first feature showcase: [Section 14](#14-dedicated-feature-showcase-judge-focused-ml-first)
- API contracts and payloads: [Section 6](#6-api-documentation)
- Setup and run instructions: [Section 7](#7-setup-instructions-very-important), [Section 8](#8-execution-steps)

### Evidence Map (Where to Read What)

- Architecture and system design: [Section 3](#3-system-overview), [Section 4](#4-architecture-design)
- API behavior and payload examples: [Section 6](#6-api-documentation)
- Setup and execution: [Section 7](#7-setup-instructions-very-important), [Section 8](#8-execution-steps)
- Design decisions and assumptions: [Section 9](#9-design-decisions), [Section 10](#10-assumptions)
- Performance and scalability: [Section 11](#11-performance--scalability)
- Full feature inventory for showcase: [Section 14](#14-dedicated-feature-showcase-judge-focused-ml-first)
- CI/CD and deployment implementation: [Section 15](#15-cicd-and-deployment-implementation)

### Important Scope Note for Judges

- Authentication endpoints exist in code, but the primary judged flow is routing, anomaly adaptation, and ML-based traffic prediction.

## 1. Project Title

### GoliTransit - AI-Powered Multi-Modal Urban Routing

GoliTransit is a full-stack intelligent routing system built for urban mobility scenarios where cars, rickshaws, bikes, walking, and transit need to coexist inside one routing workflow.

---

## 2. Problem Statement

Dhaka-like city mobility is not a single-mode problem. Users frequently switch between walking, rickshaw, bike, car, and transit depending on road type, congestion, and local constraints.

Traditional route systems fail in three important ways for this context:

- They treat all roads as equally accessible for all vehicles.
- They do not react quickly to dynamic incidents (closures, flooding, congestion, VIP movement).
- They do not expose judge-friendly transparency on how route decisions are made.

GoliTransit addresses this by combining:

- OSM road graph constraints by transport mode,
- Dynamic anomaly-driven edge weight updates,
- Multi-modal state-space shortest path search,
- Frontend map visualization with route comparison and mode-color interpretation.

Real-world relevance:

- Emergency rerouting during accidents/waterlogging,
- Better first/last-mile decisions,
- Explainable mobility planning for mixed-transport cities.

---

## 3. System Overview

### Backend Architecture (FastAPI)

The backend is a service-layered FastAPI application.

Core modules:

- `routes/`: thin HTTP controllers
- `services/`: routing, graph, anomaly, traffic, ML integration logic
- `models/`: Pydantic and SQLAlchemy schemas
- `database.py`: SQLAlchemy session/engine

Startup pipeline in `backend/main.py`:

1. Create DB tables.
2. Load and normalize OSM graph around AUST center.
3. Initialize traffic dummy dataset + model.
4. Start async traffic workers.

### Frontend Architecture (React + Vite + Leaflet)

Frontend is a React SPA with two main pages:

- `HomePage` (landing)
- `MapPage` (interactive route planning + anomaly injection)

Key components:

- `MapView`: route rendering, overlap handling, node overlays, anomaly overlays
- `RoutePanel`: route compute controls + metrics
- `RouteSelectionPanel`: fastest vs shortest multimodal selector
- `ModeSelector`, `AnomalyModal`, `AnomalyAlert`

### Database Layer

SQLAlchemy models currently include:

- `road_traffic_observations` (hourly per-edge dummy traffic labels)

Default runtime DB is MySQL (from `config.json` and Docker Compose).

### Graph / Routing Engine

Graph source and processing:

- OSMnx graph extraction (`network_type: all`) around configured center/radius
- NetworkX MultiDiGraph in memory
- Mode constraints per edge (`car_allowed`, `bike_allowed`, etc.)
- Mode-specific travel time weights (`{mode}_travel_time`)
- Current working graph size: **2,741 nodes** and **6,169 edges**

Routing paths:

- Single-modal shortest path
- Multi-modal state-space Dijkstra (`(node, mode)` states)
- Sequential fallback if state-space fails

### ML / Anomaly / Real-Time Components

- **Anomaly Service**: applies dynamic weight multipliers and mode disabling on affected edges.
- **Traffic Jam Service**: async queue-based route-level risk prediction with retry and worker pool.
- **ML Integration (Core Differentiator)**: backend route responses return fast while a decoupled ML pipeline computes per-edge traversal risk and route-level congestion probability.
- **Fallback Safety**: if ML is unavailable, routing stays functional with deterministic fallback estimates so the UX remains stable.

### High-Level Architecture Flow

```text
User Action (Frontend)
  -> FastAPI Route API
  -> RoutingEngine
  -> GraphService + MultiModalDijkstra
  -> (Optional) Anomaly effects + Traffic prediction job
  -> Response + route_id
  -> Frontend map render + async traffic polling
```

### ML Integration Flow (Traffic Prediction)

- `/route` returns route geometry and `route_id` quickly.
- `TrafficJamService` enqueues ML prediction work without blocking route computation.
- Worker threads call ML `/predict` with batched edge features.
- Predictions are aggregated into route risk metrics and confidence.
- Frontend polls `/traffic/{route_id}` to render final ML-enhanced traffic status.
- If the ML service is down, fallback logic keeps routing and anomaly adaptation available.

---

## 4. Architecture Design

### 4.1 Multi-Layer Graph Model

GoliTransit uses one OSM truth graph with layered semantics:

- **Base Layer**: geometry, length, road type
- **Constraint Layer**: per-mode allowed/disallowed flags
- **Weight Layer**: base and dynamic travel-time weights
- **Runtime Layer**: anomaly multipliers, ML-predicted updates

Why this design:

- Preserves road topology integrity,
- Allows safe dynamic behavior without mutating graph structure,
- Keeps routing explainable (weights + constraints are observable).

### 4.2 State Management Strategy (Frontend)

React local state with explicit routing/anomaly state slices in `MapPage`:

- origin/destination,
- route mode (single vs multimodal),
- selected comparison route,
- anomalies,
- async traffic status per route.

Why this design:

- Minimal overhead for hackathon scope,
- Predictable and easy to demo,
- No external state framework required.

### 4.3 Concurrency Handling

Traffic prediction pipeline is decoupled from route computation:

- route request returns quickly with `route_id`,
- prediction jobs are queued,
- worker pool processes jobs concurrently,
- retry with backoff for transient failures,
- frontend polls `/traffic/{route_id}`.

Why this design:

- Keeps `/route` latency stable,
- Prevents blocking request threads,
- Scales with worker count.

### 4.4 Real-Time Processing Pipeline

```text
Anomaly POST
  -> AnomalyService validates + resolves edge targets
  -> Graph edge weights updated (and optional mode disabling)
  -> graph version incremented
  -> next route requests automatically adapt
```

### 4.5 Caching Strategy

Implemented caches:

- Route response cache with TTL in `RoutingEngine`
- Single-source shortest-tree LRU cache in `RoutingEngine`
- Mode-subgraph cache in `GraphService`
- KDTree spatial index for nearest-node lookup
- Edge prediction cache + route prediction lifecycle cache in `TrafficJamService`

Why this design:

- Reduces repeated graph traversals,
- Accelerates hot-path route requests,
- Supports interactive frontend usage.

---

## 5. Features

This section is intentionally concise to avoid repeating details already documented in the dedicated showcase.

- Full feature showcase (single source of truth): [Section 14](#14-dedicated-feature-showcase-judge-focused-ml-first)
- Routing and anomalies: [Section 14.1](#141-routing-intelligence), [Section 14.2](#142-real-time-incident-and-dynamic-reweighting)
- ML prediction and training functionality: [Section 14.3](#143-async-traffic-and-ml-augmented-pipeline), [Section 14.7](#147-ml-functionality-judges-can-see-live), [Section 14.8](#148-ml-training-already-active-in-runtime)
- API endpoint surface: [Section 14.5](#145-api-surface-implemented-in-code)

---

## 6. API Documentation

### 6.1 Backend Service (default `http://localhost:8000`)

#### GET /health

Description: Service health check.

Request body:

```json
null
```

Response:

```json
{
  "status": "ok"
}
```

---

#### POST /route

Description: Compute single-modal or multi-modal optimal route.

Request:

```json
{
  "origin": { "lat": 23.7639, "lng": 90.4066 },
  "destination": { "lat": 23.7725, "lng": 90.415 },
  "modes": ["walk", "transit", "car"],
  "optimize": "time",
  "avoid_anomalies": true,
  "include_multimodal": true,
  "traffic_hour_of_day": 9,
  "max_alternatives": 3
}
```

Response:

```json
{
  "legs": [
    {
      "mode": "walk",
      "geometry": [{ "lat": 23.7639, "lng": 90.4066 }],
      "distance_m": 210.5,
      "duration_s": 155.2,
      "cost": 0,
      "instructions": ["Start...", "Arrive..."]
    }
  ],
  "mode_switches": [
    {
      "from_mode": "walk",
      "to_mode": "transit",
      "location": { "lat": 23.765, "lng": 90.408 },
      "penalty_time_s": 60,
      "penalty_cost": 0.2
    }
  ],
  "total_distance_m": 3200.4,
  "total_duration_s": 820.6,
  "total_cost": 1.4,
  "anomalies_avoided": 2,
  "alternatives": [],
  "multimodal_suggestions": [],
  "traffic_jam_prediction": null,
  "route_id": "route_ab12cd34ef56",
  "traffic_status": "loading"
}
```

---

#### GET /traffic/{route_id}

Description: Get asynchronous traffic prediction status for an existing route.

Request body:

```json
null
```

Response:

```json
{
  "route_id": "route_ab12cd34ef56",
  "status": "ready",
  "job_status": "completed",
  "retry_count": 0,
  "max_retries": 3,
  "updated_at": 1712833000.42,
  "data": {
    "hour_of_day": 9,
    "route_jam_chance_pct": 34.8,
    "edges_analyzed": 41,
    "heavy_edges": 4,
    "moderate_edges": 12,
    "low_edges": 25,
    "confidence": 0.92
  }
}
```

---

#### POST /anomaly

Description: Inject anomaly and apply dynamic graph effects.

Request:

```json
{
  "type": "waterlogging",
  "severity": "high",
  "edge_ids": ["123->456"],
  "vehicle_types": ["car", "bike"],
  "description": "Road submerged after rain",
  "duration_minutes": 45
}
```

Response:

```json
{
  "anomaly_id": "anomaly_9f31e7b1d4a2",
  "status": "accepted",
  "affected_edges": 1,
  "edge_ids": ["123->456"],
  "vehicle_types": ["bike", "car"],
  "severity": 3
}
```

---

#### GET /anomaly

Description: List active anomalies.

Request body:

```json
null
```

Response:

```json
{
  "anomalies": [
    {
      "anomaly_id": "anomaly_9f31e7b1d4a2",
      "edge_ids": ["123->456"],
      "severity": 3,
      "type": "waterlogging",
      "description": "Road submerged after rain",
      "weight_multiplier": 3,
      "created_at": "2026-04-11T10:10:00Z",
      "expires_at": "2026-04-11T10:55:00Z"
    }
  ],
  "count": 1
}
```

---

#### DELETE /anomaly

Description: Clear all active anomalies and reset effects.

Request body:

```json
null
```

Response:

```json
{
  "status": "cleared",
  "count": 3
}
```

---

#### GET /graph/snapshot

Description: Return graph snapshot for visualization/debugging.

Query params:

- `include_edges` (bool)
- `bbox` = `south,west,north,east` (optional)
- `mode` = `car|bike|walk|transit|rickshaw` (optional)

Response:

```json
{
  "node_count": 2741,
  "edge_count": 6169,
  "nodes": [
    {
      "id": "123456",
      "lat": 23.7631,
      "lng": 90.4058,
      "accessible_modes": ["car", "walk", "rickshaw"]
    }
  ],
  "edges": [],
  "anomaly_affected_edges": []
}
```

---

### 6.2 V2 Routing & Validation API (`/v2`)

#### POST /v2/route

Description: Multi-modal state-space Dijkstra by source/destination node IDs.

Request:

```json
{
  "source": 123456,
  "destination": 789012,
  "allowed_modes": ["car", "rickshaw", "walk"],
  "mode_switch_penalty": 5
}
```

Response:

```json
{
  "computation_time_ms": 312.8,
  "node_path": [123456, 223344, 789012],
  "coordinate_path": [{ "node_id": 123456, "lat": 23.7639, "lng": 90.4066 }],
  "path": [{ "from": 123456, "to": 223344, "mode": "walk" }],
  "geometry": [
    [23.7639, 90.4066],
    [23.7645, 90.4074]
  ],
  "total_cost": 189.4,
  "num_steps": 2,
  "modes_used": ["walk", "car"],
  "justification": "Multi-modal optimal route computed..."
}
```

---

#### POST /v2/route/coords

Description: Multi-modal state-space Dijkstra by lat/lng with nearest-node or edge snap.

Request:

```json
{
  "source_lat": 23.7639,
  "source_lng": 90.4066,
  "dest_lat": 23.7725,
  "dest_lng": 90.415,
  "allowed_modes": ["walk", "transit", "car"],
  "mode_switch_penalty": 5
}
```

Response:

```json
{
  "computation_time_ms": 341.2,
  "source_node": 123456,
  "destination_node": 789012,
  "source_snap_distance_m": 8.7,
  "dest_snap_distance_m": 11.3,
  "node_path": [123456, 223344, 789012],
  "coordinate_path": [],
  "path": [],
  "geometry": [],
  "total_cost": 205.9,
  "num_steps": 2,
  "modes_used": ["walk", "transit"],
  "justification": "Multi-modal optimal route computed..."
}
```

---

#### POST /v2/anomaly

Description: Directly modify v2 graph edge weights by severity.

Request:

```json
{
  "affected_edges": [
    [123456, 223344],
    [223344, 789012]
  ],
  "severity": 4
}
```

Response:

```json
{
  "status": "updated",
  "edges_affected": 2,
  "cars_blocked": 2,
  "severity": 4,
  "multiplier_applied": 3
}
```

---

#### GET /v2/graph/snapshot

Description: Debug graph sample for v2 engine.

Query params:

- `limit` (default 100)
- `include_weights` (default false)

Response:

```json
{
  "total_nodes": 2741,
  "total_edges": 6169,
  "nodes_sample": [123456],
  "edges_sample": [
    {
      "from": 123456,
      "to": 223344
    }
  ]
}
```

---

#### GET /v2/graph/validate

Description: Validate graph constraints and integrity for audit/judging.

Response:

```json
{
  "valid": true,
  "issues": [],
  "stats": {
    "total_nodes": 2741,
    "total_edges": 6169,
    "negative_weight_edges": 0,
    "connected_components": 1
  },
  "design_rules": {
    "edges_from_osm": true,
    "no_negative_weights": true,
    "graph_connected": true,
    "road_geometry_available": true
  }
}
```

---

### 6.3 ML Microservice (Core Integration Highlight, default `http://localhost:8001`)

#### GET /health

Description: ML service and model-load status.

Response:

```json
{
  "status": "healthy",
  "service": "GoliTransit ML Prediction",
  "model_type": "random_forest",
  "model_loaded": true
}
```

---

#### POST /predict

Description: Batch edge traversal time prediction endpoint used by backend integration.

Request:

```json
{
  "edges": [
    {
      "source": "123",
      "target": "456",
      "features": {
        "hour_of_day": 8,
        "day_of_week": 2,
        "road_type": 3,
        "road_length_m": 120.0,
        "speed_limit": 40,
        "historical_avg_time": 11.8
      }
    }
  ]
}
```

Response:

```json
{
  "predictions": [
    {
      "source": "123",
      "target": "456",
      "predicted_time_s": 14.7
    }
  ],
  "model_type": "random_forest",
  "model_version": "v1"
}
```

---

## 7. Setup Instructions (Very Important)

### 7.1 Prerequisites

- Python 3.11 (recommended)
- Node.js 20.x (recommended)
- MySQL 8.x
- Docker + Docker Compose (recommended for judges)

---

### 7.2 Quick Judge Setup (Docker Recommended)

1. Clone repository:

```bash
git clone https://github.com/md-sazid9089/Aust_hackathon_26.git
cd Aust_hackathon_26
```

2. Start full stack:

```bash
docker compose up --build
```

3. Access services:

- Frontend: `http://localhost:5174`
- Backend API: `http://localhost:8000`
- Backend Docs: `http://localhost:8000/docs`
- ML API: `http://localhost:8001`

4. Production-style compose (optional):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

### 7.3 Local Development Setup (Without Docker)

#### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

Important:

- Ensure MySQL is running and reachable.
- Update root `config.json` database section for your local DB host/user/password.
- From `backend/`, run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### ML Service

```bash
cd ml
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
python predict.py
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server defaults to Vite and proxies `/api` to backend.

---

### 7.4 Environment Variables

#### Backend / Infrastructure

- `CONFIG_PATH` (path to root config JSON)
- `PORT` (backend port)
- `DATABASE_URL` (optional full SQLAlchemy DSN override)
- `ML_PREDICTION_URL` (ML endpoint)
- `REDIS_URL` (Redis connection)
- `TESTING` (`1|true` to skip heavy startup operations in tests)

#### Frontend

- `VITE_PROXY_TARGET`
- `VITE_API_BASE_URL`
- `VITE_HMR_CLIENT_PORT`
- `VITE_DEV_SERVER_PORT`
- `DOCKER`

#### Docker Compose DB Variables

- `MYSQL_ROOT_PASSWORD`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

Note: Do not commit real credentials. Use secure environment-specific values.

---

## 8. Execution Steps

### Step 1: Start Backend

Docker:

```bash
docker compose up backend mysql redis ml
```

Local:

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 2: Start Frontend

Docker:

```bash
docker compose up frontend
```

Local:

```bash
cd frontend
npm run dev
```

### Step 3: Test APIs

Health check:

```bash
curl http://localhost:8000/health
```

Route compute:

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{
    "origin": {"lat": 23.7639, "lng": 90.4066},
    "destination": {"lat": 23.7725, "lng": 90.4150},
    "modes": ["car"],
    "optimize": "time",
    "avoid_anomalies": true
  }'
```

### Step 4: Run Full System

```bash
docker compose up --build
```

Then open frontend and execute route scenarios from UI.

---

## 9. Design Decisions

### Why Dijkstra / State-Space Dijkstra

- Deterministic shortest path behavior with weighted graph semantics.
- State-space extension enables multi-modal switching during traversal (not only pre-defined segmented legs).
- Fits dynamic edge weight updates from anomalies.

### Why OSM-Centric Graph

- Real road geometry and topology.
- Tag-level transport restrictions (`footway`, `motorway`, `service=alley`) can be encoded as hard constraints.

### Why Async Traffic Pipeline

- Traffic prediction is non-critical-path relative to route geometry.
- Returning `route_id` quickly improves UX and API responsiveness.

### Why Multiple Caches

- Shortest tree cache for repeated origins.
- Route response cache for repeated requests.
- Mode subgraph cache and KDTree for geospatial efficiency.
- Prediction cache to avoid repeated per-edge inference.

### Tradeoffs

- In-memory anomaly state is fast but not durable across restarts.
- Current ML integration has functional fallback and stubs in training pipeline.
- Locality-focused graph radius improves latency but limits geographic coverage.

---

## 10. Assumptions

- Graph is built around configured AUST center with a finite radius (2 km by default).
- OSM tags are available and sufficiently accurate for transport constraints.
- Input coordinates are near graph coverage; far points may require nearest-edge snap.
- `modes` list in route request is ordered and intentional.
- Anomaly reports supply valid edge references, location, or bbox target definitions.
- MySQL is available for traffic observation persistence.
- ML service may be unavailable; routing still works via fallback strategy.
- Judge flow is currently focused on routing, anomaly adaptation, and ML traffic prediction (no authentication dependency).

---

## 11. Performance & Scalability

### Algorithmic Complexity

- Single-modal shortest path (Dijkstra): `O((V + E) log V)`
- Multi-modal state-space Dijkstra:
  - states: `|V| * |M|`
  - transitions: `|E| * |M|`
  - overall approx: `O((|V||M| + |E||M|) log(|V||M|))`

### Real-Time Update Strategy

- Anomalies adjust edge weights in-place and increment graph version.
- New route calls consume updated weights immediately.

### Concurrency

- FastAPI async request handling.
- Route traffic prediction queue with multiple workers and retry backoff.
- Production compose backend configured with multiple Uvicorn workers.

### Latency Optimization Techniques

- KDTree nearest-node lookup.
- Mode-subgraph caching.
- Shortest-path tree LRU cache.
- Route response TTL cache.
- Edge-level prediction cache.

### p95/Runtime Targets

- Practical target for judge demos on local AUST graph: p95 route response under 1s.
- Profiling logs in service output commonly show ~300-350 ms algorithm time for multimodal state-space runs on the current graph size.

### Scalability Roadmap

- Current scope is single-instance in-memory graph.
- Horizontal scale requires shared anomaly/prediction state and graph sharding/partitioning strategy.

---

## 12. Project Structure

```text
Aust_hackathon_26/
|- backend/
|  |- main.py
|  |- config.py
|  |- database.py
|  |- routes/
|  |  |- health.py
|  |  |- auth.py
|  |  |- route.py
|  |  |- traffic.py
|  |  |- anomaly.py
|  |  |- graph.py
|  |  '- v2.py
|  |- services/
|  |  |- graph_service.py
|  |  |- routing_engine.py
|  |  |- multimodal_dijkstra.py
|  |  |- anomaly_service.py
|  |  |- traffic_jam_service.py
|  |  |- ml_integration.py
|  |  '- auth_service.py
|  |- models/
|  |  |- route_models.py
|  |  |- anomaly_models.py
|  |  |- graph_models.py
|  |  |- auth_schemas.py
|  |  |- user_models.py
|  |  '- traffic_models.py
|  |- utils/
|  |  '- osm_graph_builder.py
|  |- tests/
|  '- Dockerfile
|- frontend/
|  |- src/
|  |  |- App.jsx
|  |  |- pages/
|  |  |  |- HomePage.jsx
|  |  |  '- MapPage.jsx
|  |  |- components/
|  |  |  |- MapView.jsx
|  |  |  |- RoutePanel.jsx
|  |  |  |- RouteSelectionPanel.jsx
|  |  |  |- ModeSelector.jsx
|  |  |  |- AnomalyModal.jsx
|  |  |  '- AnomalyAlert.jsx
|  |  '- services/
|  |     |- api.js
|  |     '- routeService.js
|  |- package.json
|  |- vite.config.js
|  '- Dockerfile
|- ml/
|  |- predict.py
|  |- preprocess.py
|  |- train.py
|  |- model_registry.py
|  |- requirements.txt
|  '- Dockerfile
|- config.json
|- docker-compose.yml
|- docker-compose.prod.yml
|- render.yaml
|- setup-local.sh
'- test-render-readiness.sh
```

---

## 13. Future Improvements

- Replace ML stubs with fully trained and deployed traffic model pipeline.
- Persist anomaly and async job state in Redis/MySQL for restart durability.
- Add WebSocket push for real-time route traffic status instead of polling.
- Add distributed/partitioned graph processing for city-scale expansion.
- Introduce historical anomaly analytics and incident replay.
- Add role-based admin moderation for anomaly ingestion.
- Implement mobile client and offline route snapshot support.

---

## 14. Dedicated Feature Showcase (Judge-Focused, ML-First)

### 14.1 Routing Intelligence

- OSM-based graph extraction around AUST and normalization into an in-memory NetworkX MultiDiGraph.
- Single-modal and multi-modal routing from the same graph source.
- State-space Dijkstra (`(node, mode)`) for true in-path mode switching.
- Sequential multimodal fallback strategy when state-space pathing cannot be resolved.
- Config-driven mode-switch penalties and mode constraints.
- Geometry-preserving route rendering (road-following coordinates, no synthetic straight-line jumps when graph path exists).
- Coordinate-to-graph snapping support (nearest-node and nearest-edge fallback in v2 coordinate routing).

### 14.2 Real-Time Incident and Dynamic Reweighting

- Live anomaly ingestion with severity (`low`, `medium`, `high`, `critical`).
- Edge targeting by direct edge IDs or by map-selected bounding box (frontend-assisted targeting).
- Severity-driven edge weight multiplication and optional mode blocking behavior for high-severity incidents.
- Active anomaly lifecycle management (list, clear, expiry reconciliation).
- Graph version tracking so new route computations adapt immediately after anomaly updates.

### 14.3 Async Traffic and ML-Augmented Pipeline

- Route response returns immediately with `route_id`.
- Non-blocking traffic prediction pipeline with internal queue, worker pool, and retry with backoff.
- Route traffic lifecycle endpoint (`loading`, `ready`, `failed`) for frontend polling.
- Edge-level prediction cache and route-level lifecycle cache with TTL-based eviction.
- ML prediction microservice endpoint integration (`/predict`) and graceful fallback behavior when ML is unavailable.
- Service-level dataset generation/training utilities for traffic model bootstrapping.

### 14.4 Frontend Demo UX Capabilities

- Health-aware landing page with engine status indicator.
- Full-screen interactive map planner.
- Origin/destination selection via map click and draggable markers.
- Single-mode route flow and multimodal compare flow.
- Fastest vs shortest comparison selector with overlap-aware rendering.
- Segment-level vehicle coloring plus persistent vehicle color legend.
- Anomaly injection UI for edge mode and bbox mode.
- Live anomaly overlay rendering and anomaly panel controls.
- Progressive traffic status UX (`loading -> ready/failed`) tied to backend polling.
- Graph overlay visualization support (nodes/edges snapshot rendering paths).

### 14.5 API Surface Implemented in Code

- Core: `GET /health`, `POST /route`, `GET /traffic/{route_id}`
- Anomalies: `POST /anomaly`, `GET /anomaly`, `DELETE /anomaly`
- Graph: `GET /graph/snapshot`
- V2 engine: `POST /v2/route`, `POST /v2/route/coords`, `POST /v2/anomaly`, `GET /v2/graph/snapshot`, `GET /v2/graph/validate`
- Auth module exists in code (`/auth/register`, `/auth/login`) but is not part of the current hackathon judge flow.

### 14.6 Data, Caching, and Reliability Primitives

- MySQL persistence for road traffic observation records.
- Redis integration for runtime caching support.
- Route caching, shortest-tree caching, mode subgraph caching, and KDTree nearest-node acceleration.
- Automated startup initialization pipeline (DB table ensure, graph load, traffic service bootstrap, worker start).
- Test suite coverage across routing, anomaly, graph, and multimodal logic (`backend/tests`).

### 14.7 ML Functionality Judges Can See Live

- Frontend sends local-time context (`traffic_hour_of_day = new Date().getHours()`) in route requests.
- Backend responds quickly with route geometry and `traffic_status: loading`.
- `TrafficJamService` workers process route edges in background and update status to `ready`.
- Response includes:
  - `route_jam_chance_pct`
  - `edges_analyzed`
  - `heavy_edges`, `moderate_edges`, `low_edges`
  - `confidence`
- If prediction fails or ML endpoint is unavailable, route computation still succeeds (graceful degradation).

### 14.8 ML Training Already Active in Runtime

- Startup bootstraps ML traffic model from graph data via `TrafficJamService.initialize_from_graph(...)`.
- Dataset generation covers every edge across all 24 hours and persists to DB/CSV.
- Training uses `RandomForestClassifier` over engineered features:
  - hour of day
  - deterministic edge hash
  - encoded road type
  - road-length bucket
- Model is used to classify edge jam levels and aggregate route-level jam probability.
- Caching + retry logic improves stability and responsiveness under repeated queries.

### 14.9 Edge-Time ML Microservice Path (Extensible Architecture)

- Separate ML FastAPI microservice exposes `/health` and `/predict`.
- Model registry supports save/load/version metadata for trained artifacts.
- Current predictor includes fallback inference logic when no trained artifact is present.
- `ml/preprocess.py` and `ml/train.py` define the training pipeline contract for production-grade model evolution.
- This separation keeps routing API reliable while allowing independent ML iteration.

### 14.10 Suggested Judge Script for Maximum Impact

1. Compute a multimodal route and show segment-level vehicle colors.
2. Inject a high-severity anomaly and recompute to show adaptation.
3. Observe `/traffic/{route_id}` lifecycle from `loading` to `ready`.
4. Highlight returned ML fields (`route_jam_chance_pct`, heavy/moderate/low distribution, confidence).
5. Mention resilience behavior: route remains available even if ML prediction path degrades.

---

## 15. CI/CD and Deployment Implementation

### 15.1 Continuous Integration (`.github/workflows/ci.yml`)

- Triggered on push to `dev` and on pull requests.
- Backend test job:
  - Python 3.11 setup
  - dependency install from `backend/requirements.txt`
  - `pytest` execution with `TESTING=1` and in-memory SQLite override for fast deterministic CI
- Frontend build job:
  - Node 20 setup
  - `npm ci` and production build validation
- Docker validation job:
  - `docker compose config` structural validation

### 15.2 Continuous Delivery (`.github/workflows/cd.yml`)

- Triggered on push to `dev`, PRs targeting `dev`, and manual dispatch.
- Container publication pipeline (non-PR):
  - builds backend, ML, and frontend images
  - pushes to GHCR with both `latest` and commit-SHA tags
- Frontend Vercel production deployment (non-PR):
  - pulls Vercel production env metadata
  - builds frontend
  - executes `vercel deploy --prod`
- Frontend Vercel preview deployment (PR):
  - builds preview artifact
  - deploys preview and publishes preview URL into workflow summary

### 15.3 Azure Deployment Workflow (`.github/workflows/dev_maploactor.yml`)

- Separate Azure-focused pipeline configured for the `maploactor` Azure Web App.
- Triggered on push to `dev` and manual dispatch.
- Uploads build artifact and deploys via `azure/webapps-deploy`.

### 15.4 Render Deployment Path

- `render.yaml` defines backend service, health checks, auto-deploy, persistent disk for OSM cache, and environment wiring.
- `backend/render-build.sh` performs dependency installation and import verification.
- `backend/render-start.sh` validates config and starts Uvicorn with Render-ready settings.

### 15.5 Containerized Runtime Strategy

- `docker-compose.yml` orchestrates local/dev stack: backend, frontend, ML, MySQL, Redis.
- `docker-compose.prod.yml` applies production overrides (worker count, resource limits, production frontend image target).
- Multi-stage Dockerfiles implemented for backend, frontend, and ML services.

---

## 16. Live Deployments and Public Domains

- Frontend (Vercel): https://aust-hackathon-26.vercel.app/
- Backend (Azure App Service): https://maploactor-eve5e0d5f5h0aqh8.southeastasia-01.azurewebsites.net/
- Backend (Render): https://aust-hackathon-26.onrender.com/
- Public live domain: https://www.smartcommutebd.live/
- Backend is currently not working in deployment due to free tier limit
Notes:

- The same codebase supports multiple backend hosting targets (Azure and Render) and a Vercel-hosted frontend.
- For hackathon demos, backend target can be switched by frontend environment configuration without changing application logic.

---

## 17. Suggested Judge Demo Flow

1. Open frontend map.
2. Set origin and destination.
3. Compute single-mode and multimodal routes.
4. Inject anomaly on selected edge or bbox.
5. Recompute and compare route adaptation.
6. Observe asynchronous traffic status transitions (`loading -> ready`).

---

## 18. Credits / Team

### TEAM NULL

- Md Tayeb Ibne Sayed
- MD Sazid
- Shajedul Kabir Rafi
