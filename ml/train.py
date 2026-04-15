"""
ML Module — Model Training Pipeline
======================================
Trains a edge traversal time prediction model from processed features.

Supported model types (configurable via config.json → ml.model_type):
  - "random_forest"  → scikit-learn RandomForestRegressor (default)
  - "gradient_boost"  → scikit-learn GradientBoostingRegressor
  - "neural_net"      → TensorFlow/Keras sequential model (stub)

Training pipeline:
  1. Load processed features from data/processed_features.csv
  2. Train/test split (80/20)
  3. Train selected model type
  4. Evaluate on test set (MAE, RMSE, R²)
  5. Save trained model via model_registry

Integration:
  - Reads features from preprocess.py output (data/processed_features.csv)
  - Saves model via model_registry.py
  - Trained model is loaded by predict.py for inference
  - Can be triggered via CLI or scheduled (config: retrain_interval_hours)
"""

import os
import json

# TODO: Uncomment for actual implementation
# import pandas as pd
# import numpy as np
# from sklearn.model_selection import train_test_split
# from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
# from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from model_registry import ModelRegistry


# ─── Configuration ───────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROCESSED_PATH = os.path.join(DATA_DIR, "processed_features.csv")
METADATA_PATH = os.path.join(DATA_DIR, "feature_metadata.json")

# Load config for model type
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "..", "config.json"))

def _load_ml_config() -> dict:
    """Load ML configuration from project config.json."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f).get("ml", {})
    except FileNotFoundError:
        return {}

ml_config = _load_ml_config()
registry = ModelRegistry()


# ─── Model Factories ────────────────────────────────────────────

def _build_random_forest():
    """
    Build a RandomForestRegressor with sensible defaults for
    edge traversal time prediction.

    TODO: Implement:
      return RandomForestRegressor(
          n_estimators=100,
          max_depth=15,
          min_samples_split=5,
          random_state=42,
          n_jobs=-1,
      )
    """
    print("[train] Building RandomForest model")
    # STUB
    return None


def _build_gradient_boost():
    """
    Build a GradientBoostingRegressor.

    TODO: Implement:
      return GradientBoostingRegressor(
          n_estimators=200,
          max_depth=8,
          learning_rate=0.1,
          random_state=42,
      )
    """
    print("[train] Building GradientBoosting model")
    # STUB
    return None


def _build_neural_net():
    """
    Build a Keras sequential model for edge time prediction.

    TODO: Implement with TensorFlow:
      from tensorflow import keras
      model = keras.Sequential([
          keras.layers.Dense(64, activation='relu', input_shape=(num_features,)),
          keras.layers.Dropout(0.2),
          keras.layers.Dense(32, activation='relu'),
          keras.layers.Dense(1),  # regression output
      ])
      model.compile(optimizer='adam', loss='mse', metrics=['mae'])
      return model
    """
    print("[train] Building Neural Network model (TensorFlow)")
    # STUB
    return None


MODEL_BUILDERS = {
    "random_forest": _build_random_forest,
    "gradient_boost": _build_gradient_boost,
    "neural_net": _build_neural_net,
}


# ─── Training Pipeline ──────────────────────────────────────────

def load_processed_data():
    """
    Load processed features and target from CSV.

    TODO: Implement:
      df = pd.read_csv(PROCESSED_PATH)
      with open(METADATA_PATH) as f:
          meta = json.load(f)
      X = df[meta["feature_columns"]]
      y = df[meta["target_column"]]
      return X, y
    """
    print(f"[train] Loading processed data from {PROCESSED_PATH}")
    # STUB
    return None, None


def train_model(X, y, model_type: str = None):
    """
    Train the selected model on the given features and target.

    TODO: Implement:
      1. X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
      2. model = MODEL_BUILDERS[model_type]()
      3. model.fit(X_train, y_train)
      4. y_pred = model.predict(X_test)
      5. Return model, metrics
    """
    model_type = model_type or ml_config.get("model_type", "random_forest")
    print(f"[train] Training model: {model_type}")

    builder = MODEL_BUILDERS.get(model_type)
    if builder is None:
        raise ValueError(f"Unknown model type: {model_type}. Available: {list(MODEL_BUILDERS.keys())}")

    model = builder()

    # STUB: Return placeholder metrics
    metrics = {
        "model_type": model_type,
        "mae": 0.0,
        "rmse": 0.0,
        "r2": 0.0,
        "train_samples": 0,
        "test_samples": 0,
    }

    return model, metrics


def evaluate_and_save(model, metrics: dict, model_type: str = None):
    """
    Print evaluation metrics and save the trained model via registry.

    TODO: Implement:
      print(f"MAE:  {metrics['mae']:.2f}s")
      print(f"RMSE: {metrics['rmse']:.2f}s")
      print(f"R²:   {metrics['r2']:.4f}")
      registry.save_model(model, model_type or "random_forest")
    """
    print("[train] Evaluation metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    model_type = model_type or ml_config.get("model_type", "random_forest")
    registry.save_model(model, model_type)
    print("[train] Model saved to registry")


# ─── Main Pipeline ───────────────────────────────────────────────

def run_training():
    """
    Execute the full training pipeline:
      1. Load processed features
      2. Train the configured model type
      3. Evaluate and save
    """
    print("=" * 60)
    print("[train] Starting training pipeline")
    print("=" * 60)

    X, y = load_processed_data()
    model_type = ml_config.get("model_type", "random_forest")
    model, metrics = train_model(X, y, model_type)
    evaluate_and_save(model, metrics, model_type)

    print("[train] Training complete!")


if __name__ == "__main__":
    run_training()
