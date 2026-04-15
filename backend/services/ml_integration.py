"""
ML Integration Service — Predicted Edge Weight Client
=======================================================
Bridges the backend routing engine with the isolated ML prediction module.

Responsibilities:
  1. Request edge traversal time predictions from the ML service (HTTP)
  2. Apply predicted weights to graph edges via graph_service
  3. Handle ML service failures gracefully (fallback to base weights)

Integration:
  - Called by routing_engine before each route computation
  - Sends edge features to the ML service at ml_prediction_url (config.json)
  - Receives predicted travel times and applies them via graph_service
  - If ML service is unavailable, falls back to default weights (config: fallback_to_default)

Communication protocol:
  POST {ml_prediction_url}
  Body: { "edges": [{ "source": "...", "target": "...", "features": {...} }] }
  Response: { "predictions": [{ "source": "...", "target": "...", "predicted_time_s": 42.5 }] }
"""

from typing import Optional

import httpx

from config import settings
from services.graph_service import graph_service


class MLIntegration:
    """
    Singleton HTTP client for the ML prediction service.
    """

    def __init__(self):
        self._prediction_url = settings.ml_prediction_url
        self._fallback = settings.ml_fallback_to_default
        self._client: Optional[httpx.AsyncClient] = None

    # ─── Client Lifecycle ────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def close(self):
        """Close the HTTP client (called on app shutdown)."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ─── Prediction API ──────────────────────────────────────────

    async def refresh_predictions(self):
        """
        Fetch fresh ML predictions for all graph edges and apply them.

        TODO: Implement:
          1. Collect edge features from graph_service (road_type, length, time-of-day, etc.)
          2. Batch-send features to ML service
          3. Apply returned predictions via graph_service.set_ml_predicted_weight()

        STUB: Logs the attempt and returns without action.
        """
        if not graph_service.is_loaded():
            return

        print("[MLIntegration] Refreshing ML predictions...")

        # TODO: Collect edges and their features
        # edges_to_predict = self._collect_edge_features()
        # if not edges_to_predict:
        #     return
        #
        # try:
        #     client = self._get_client()
        #     response = await client.post(
        #         self._prediction_url,
        #         json={"edges": edges_to_predict},
        #     )
        #     response.raise_for_status()
        #     predictions = response.json().get("predictions", [])
        #     self._apply_predictions(predictions)
        # except httpx.HTTPError as e:
        #     if self._fallback:
        #         print(f"[MLIntegration] ML service unavailable, using base weights: {e}")
        #     else:
        #         raise

        print("[MLIntegration] Prediction refresh complete (stub mode)")

    async def predict_single_edge(
        self,
        source: str,
        target: str,
        features: dict,
    ) -> Optional[float]:
        """
        Get ML prediction for a single edge.
        Returns predicted traversal time in seconds, or None on failure.

        Useful for on-demand prediction during incremental route updates.
        """
        try:
            client = self._get_client()
            response = await client.post(
                self._prediction_url,
                json={"edges": [{"source": source, "target": target, "features": features}]},
            )
            response.raise_for_status()
            predictions = response.json().get("predictions", [])
            if predictions:
                return predictions[0].get("predicted_time_s")
        except httpx.HTTPError as e:
            print(f"[MLIntegration] Single-edge prediction failed: {e}")
            if not self._fallback:
                raise
        return None

    # ─── Feature Collection ──────────────────────────────────────

    def _collect_edge_features(self) -> list[dict]:
        """
        Collect features for all graph edges to send to the ML service.

        TODO: Implement:
          - Iterate over graph edges
          - Extract: hour_of_day, day_of_week, road_type, road_length_m,
                     speed_limit, historical_avg_time
          - Return list of edge feature dicts
        """
        # STUB
        return []

    # ─── Prediction Application ──────────────────────────────────

    def _apply_predictions(self, predictions: list[dict]):
        """
        Apply ML predictions to graph edges.

        Each prediction dict has: { source, target, predicted_time_s }
        """
        applied = 0
        for pred in predictions:
            source = pred.get("source")
            target = pred.get("target")
            predicted_time = pred.get("predicted_time_s")
            if source and target and predicted_time is not None:
                graph_service.set_ml_predicted_weight(source, target, predicted_time)
                applied += 1
        print(f"[MLIntegration] Applied {applied} ML predictions to graph edges")


# ─── Singleton Instance ──────────────────────────────────────────
ml_integration = MLIntegration()
