"""
ML Module — Prediction Server (Inference API)
================================================
Lightweight FastAPI microservice that serves edge traversal time predictions.

Endpoints:
  POST /predict — Batch predict traversal times for a list of edges
  GET  /health  — Health check with model info

Protocol:
  Request:
    {
      "edges": [
        {
          "source": "node_123",
          "target": "node_456",
          "features": {
            "hour_of_day": 8,
            "day_of_week": 2,
            "road_type": 2,
            "road_length_m": 150.5,
            "speed_limit": 50,
            "historical_avg_time": 12.3
          }
        }
      ]
    }

  Response:
    {
      "predictions": [
        {
          "source": "node_123",
          "target": "node_456",
          "predicted_time_s": 14.7
        }
      ],
      "model_type": "random_forest",
      "model_version": "v1"
    }

Integration:
  - Called by backend/services/ml_integration.py via HTTP
  - Loads trained model from model_registry at startup
  - Uses same feature extraction logic as preprocess.py
  - Runs on port 8001 (configurable via config.json → server.ml_server_port)
"""

import os
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from model_registry import ModelRegistry
from preprocess import FEATURE_COLUMNS


# ─── Configuration ───────────────────────────────────────────────

CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "..", "config.json"))

def _load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        return {}

config = _load_config()
ml_config = config.get("ml", {})
server_config = config.get("server", {})

ML_PORT = server_config.get("ml_server_port", 8001)
MODEL_TYPE = ml_config.get("model_type", "random_forest")


# ─── Pydantic Models ────────────────────────────────────────────

class EdgeFeatures(BaseModel):
    """Features for a single edge prediction."""
    source: str
    target: str
    features: dict = Field(
        ...,
        description="Feature dict with keys matching FEATURE_COLUMNS",
        examples=[{
            "hour_of_day": 8,
            "day_of_week": 2,
            "road_type": 2,
            "road_length_m": 150.5,
            "speed_limit": 50,
            "historical_avg_time": 12.3,
        }],
    )


class PredictionRequest(BaseModel):
    """Batch prediction request."""
    edges: list[EdgeFeatures]


class EdgePrediction(BaseModel):
    """Predicted traversal time for a single edge."""
    source: str
    target: str
    predicted_time_s: float


class PredictionResponse(BaseModel):
    """Batch prediction response."""
    predictions: list[EdgePrediction]
    model_type: str = MODEL_TYPE
    model_version: str = "v1"


# ─── App Setup ───────────────────────────────────────────────────

app = FastAPI(
    title="GoliTransit ML Prediction Service",
    description="Serves edge traversal time predictions for the routing engine.",
    version="0.1.0",
)

# Load model at startup
registry = ModelRegistry()
model = None


@app.on_event("startup")
async def load_model():
    """Load the trained model from the registry at startup."""
    global model
    try:
        model = registry.load_model(MODEL_TYPE)
        print(f"[predict] Model loaded: {MODEL_TYPE}")
    except FileNotFoundError:
        print(f"[predict] WARNING: No trained model found for '{MODEL_TYPE}'. Using fallback.")
        model = None


# ─── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check with model status."""
    return {
        "status": "healthy" if model is not None else "no_model",
        "service": "GoliTransit ML Prediction",
        "model_type": MODEL_TYPE,
        "model_loaded": model is not None,
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """
    Predict edge traversal times.

    If no model is loaded, returns fallback predictions using
    a simple formula: road_length_m / (speed_limit_kmh * 1000 / 3600)

    TODO: When model is trained, replace fallback with:
      features_array = np.array([[e.features[col] for col in FEATURE_COLUMNS] for e in request.edges])
      predicted_times = model.predict(features_array)
    """
    predictions = []

    for edge in request.edges:
        if model is not None:
            # TODO: Use actual model prediction
            # feature_vector = [edge.features.get(col, 0) for col in FEATURE_COLUMNS]
            # predicted_time = model.predict([feature_vector])[0]
            predicted_time = _fallback_prediction(edge.features)
        else:
            # Fallback: simple physics-based estimate
            predicted_time = _fallback_prediction(edge.features)

        predictions.append(EdgePrediction(
            source=edge.source,
            target=edge.target,
            predicted_time_s=round(predicted_time, 2),
        ))

    return PredictionResponse(predictions=predictions)


# ─── Fallback Prediction ────────────────────────────────────────

def _fallback_prediction(features: dict) -> float:
    """
    Simple physics-based fallback when no trained model is available.

    Formula: time = distance / speed
    With time-of-day congestion factor applied.
    """
    length_m = features.get("road_length_m", 100.0)
    speed_kmh = features.get("speed_limit", 50.0)
    hour = features.get("hour_of_day", 12)

    # Convert speed to m/s
    speed_ms = speed_kmh * 1000 / 3600

    if speed_ms <= 0:
        speed_ms = 1.0  # Safety

    base_time = length_m / speed_ms

    # Apply congestion factor based on hour of day
    # Rush hours: 7-9 AM, 5-7 PM get 1.5x multiplier
    if 7 <= hour <= 9 or 17 <= hour <= 19:
        base_time *= 1.5
    elif 10 <= hour <= 16:
        base_time *= 1.1  # Mild daytime traffic
    # Night hours: no multiplier

    return base_time


# ─── Entry Point ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"[predict] Starting ML prediction server on port {ML_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=ML_PORT)
