"""
ML Module — Data Preprocessing & Feature Engineering
======================================================
Transforms raw OSM road data and historical traffic data into features
suitable for training the edge traversal time prediction model.

Features extracted per edge:
  - hour_of_day (0-23)        — time-based congestion pattern
  - day_of_week (0-6)         — weekday vs weekend pattern
  - road_type (encoded)       — OSM highway tag (motorway, residential, etc.)
  - road_length_m             — physical edge length in meters
  - speed_limit               — posted speed limit (or default for road type)
  - historical_avg_time       — rolling average traversal time

Input data sources:
  - OSM road network (via OSMnx export or graph_service snapshot)
  - Historical speed/time data (CSV from traffic APIs or simulation)

Output:
  - Processed feature DataFrame saved to data/processed_features.csv
  - Feature metadata saved to data/feature_metadata.json

Integration:
  - Output feeds into train.py for model training
  - Feature extraction logic is also used in predict.py for live inference
"""

import os
import json

# TODO: Uncomment for actual implementation
# import pandas as pd
# import numpy as np


# ─── Configuration ───────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_traffic_data.csv")
PROCESSED_PATH = os.path.join(DATA_DIR, "processed_features.csv")
METADATA_PATH = os.path.join(DATA_DIR, "feature_metadata.json")

# Feature column definitions (must match config.json → ml.features)
FEATURE_COLUMNS = [
    "hour_of_day",
    "day_of_week",
    "road_type",
    "road_length_m",
    "speed_limit",
    "historical_avg_time",
]

# Road type encoding (OSM highway tag → integer)
ROAD_TYPE_ENCODING = {
    "motorway": 0,
    "trunk": 1,
    "primary": 2,
    "secondary": 3,
    "tertiary": 4,
    "residential": 5,
    "cycleway": 6,
    "footway": 7,
    "path": 8,
    "pedestrian": 9,
    "steps": 10,
    "unknown": 11,
}


# ─── Preprocessing Pipeline ─────────────────────────────────────

def load_raw_data():
    """
    Load raw traffic data from CSV.

    Expected CSV columns:
      edge_source, edge_target, timestamp, traversal_time_s,
      road_type, road_length_m, speed_limit_kmh

    TODO: Implement with pandas:
      df = pd.read_csv(RAW_DATA_PATH, parse_dates=["timestamp"])
      return df
    """
    print(f"[preprocess] Loading raw data from {RAW_DATA_PATH}")
    # STUB: Return empty dataset
    # return pd.DataFrame(columns=[
    #     "edge_source", "edge_target", "timestamp", "traversal_time_s",
    #     "road_type", "road_length_m", "speed_limit_kmh",
    # ])
    return None


def extract_time_features(df):
    """
    Extract temporal features from timestamp column.

    TODO: Implement:
      df["hour_of_day"] = df["timestamp"].dt.hour
      df["day_of_week"] = df["timestamp"].dt.dayofweek
      return df
    """
    print("[preprocess] Extracting time features...")
    # STUB
    return df


def encode_road_types(df):
    """
    Encode categorical road_type strings to integers.

    TODO: Implement:
      df["road_type"] = df["road_type"].map(ROAD_TYPE_ENCODING).fillna(ROAD_TYPE_ENCODING["unknown"])
      return df
    """
    print("[preprocess] Encoding road types...")
    # STUB
    return df


def compute_historical_averages(df):
    """
    Compute rolling historical average traversal time per edge per hour.

    TODO: Implement:
      df["historical_avg_time"] = (
          df.groupby(["edge_source", "edge_target", "hour_of_day"])["traversal_time_s"]
          .transform("mean")
      )
      return df
    """
    print("[preprocess] Computing historical averages...")
    # STUB
    return df


def select_features(df):
    """
    Select and order final feature columns + target variable.

    Returns: (features_df, target_series)
    """
    print("[preprocess] Selecting features...")
    # TODO: Implement
    # features = df[FEATURE_COLUMNS]
    # target = df["traversal_time_s"]
    # return features, target
    return None, None


def save_processed(features, target):
    """
    Save processed features to CSV and metadata to JSON.

    TODO: Implement:
      os.makedirs(DATA_DIR, exist_ok=True)
      full_df = features.copy()
      full_df["target_traversal_time_s"] = target
      full_df.to_csv(PROCESSED_PATH, index=False)
      metadata = {
          "feature_columns": FEATURE_COLUMNS,
          "target_column": "target_traversal_time_s",
          "num_samples": len(full_df),
          "road_type_encoding": ROAD_TYPE_ENCODING,
      }
      with open(METADATA_PATH, "w") as f:
          json.dump(metadata, f, indent=2)
    """
    print(f"[preprocess] Saving processed data to {PROCESSED_PATH}")
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    # Save metadata stub
    metadata = {
        "feature_columns": FEATURE_COLUMNS,
        "target_column": "target_traversal_time_s",
        "num_samples": 0,
        "road_type_encoding": ROAD_TYPE_ENCODING,
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print("[preprocess] Metadata saved")


# ─── Main Pipeline ───────────────────────────────────────────────

def run_pipeline():
    """
    Execute the full preprocessing pipeline:
      1. Load raw data
      2. Extract time features
      3. Encode categoricals
      4. Compute historical averages
      5. Select features
      6. Save processed output
    """
    print("=" * 60)
    print("[preprocess] Starting preprocessing pipeline")
    print("=" * 60)

    df = load_raw_data()
    df = extract_time_features(df)
    df = encode_road_types(df)
    df = compute_historical_averages(df)
    features, target = select_features(df)
    save_processed(features, target)

    print("[preprocess] Pipeline complete!")


if __name__ == "__main__":
    run_pipeline()
