"""
ML Module — Model Registry (Save / Load / Version)
=====================================================
Manages trained model artifacts:
  - Save trained models to disk (pickle/joblib for sklearn, h5 for TensorFlow)
  - Load models for inference
  - Track model versions and metadata

Integration:
  - Called by train.py after training to persist models
  - Called by predict.py at startup to load the model for inference
  - Model path configured in config.json → ml.model_path

Supported formats:
  - .pkl / .joblib → scikit-learn models (pickle/joblib)
  - .h5 → TensorFlow/Keras models

Storage structure:
  ml/models/
    edge_time_predictor.pkl        ← current model
    edge_time_predictor_v1.pkl     ← versioned backup
    model_metadata.json            ← training metadata
"""

import os
import json
from datetime import datetime, timezone

# TODO: Uncomment for actual implementation
# import joblib


# ─── Configuration ───────────────────────────────────────────────

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
METADATA_FILE = os.path.join(MODELS_DIR, "model_metadata.json")


class ModelRegistry:
    """
    Manages model persistence and versioning.
    """

    def __init__(self, models_dir: str = None):
        self._models_dir = models_dir or MODELS_DIR
        os.makedirs(self._models_dir, exist_ok=True)

    # ─── Save ────────────────────────────────────────────────────

    def save_model(self, model, model_type: str, version: str = None):
        """
        Save a trained model to disk with metadata.

        Args:
            model: Trained model object (sklearn estimator or Keras model)
            model_type: Type identifier (e.g., "random_forest")
            version: Optional version string (auto-generated if not provided)

        TODO: Implement with joblib:
          model_path = self._get_model_path(model_type)
          joblib.dump(model, model_path)
          self._save_metadata(model_type, version, model_path)
        """
        if model is None:
            print("[ModelRegistry] No model to save (stub mode)")
            return

        version = version or f"v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        model_path = self._get_model_path(model_type)

        # STUB: In production
        # joblib.dump(model, model_path)
        # # Also save versioned copy
        # versioned_path = model_path.replace(".pkl", f"_{version}.pkl")
        # joblib.dump(model, versioned_path)

        # Save metadata
        self._save_metadata(model_type, version, model_path)

        print(f"[ModelRegistry] Saved model: {model_type} ({version}) → {model_path}")

    # ─── Load ────────────────────────────────────────────────────

    def load_model(self, model_type: str):
        """
        Load a trained model from disk.

        Args:
            model_type: Type identifier to determine file path

        Returns:
            Trained model object

        Raises:
            FileNotFoundError if no saved model exists

        TODO: Implement with joblib:
          model_path = self._get_model_path(model_type)
          if not os.path.exists(model_path):
              raise FileNotFoundError(f"No saved model at {model_path}")
          return joblib.load(model_path)
        """
        model_path = self._get_model_path(model_type)

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"No trained model found at {model_path}. "
                f"Run 'python train.py' first to train and save a model."
            )

        # STUB: In production
        # return joblib.load(model_path)
        print(f"[ModelRegistry] Loading model from {model_path}")
        return None

    # ─── Metadata ────────────────────────────────────────────────

    def get_metadata(self) -> dict:
        """Return current model metadata (version, training date, etc.)."""
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
        return {}

    def _save_metadata(self, model_type: str, version: str, model_path: str):
        """Save model metadata to JSON."""
        metadata = {
            "model_type": model_type,
            "version": version,
            "model_path": model_path,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "format": "pkl" if model_type != "neural_net" else "h5",
        }

        with open(METADATA_FILE, "w") as f:
            json.dump(metadata, f, indent=2)

    # ─── Helpers ─────────────────────────────────────────────────

    def _get_model_path(self, model_type: str) -> str:
        """Get the file path for a model type."""
        if model_type == "neural_net":
            return os.path.join(self._models_dir, "edge_time_predictor.h5")
        return os.path.join(self._models_dir, "edge_time_predictor.pkl")

    def list_versions(self) -> list[str]:
        """List all saved model versions."""
        versions = []
        for f in os.listdir(self._models_dir):
            if f.startswith("edge_time_predictor") and (f.endswith(".pkl") or f.endswith(".h5")):
                versions.append(f)
        return sorted(versions)
