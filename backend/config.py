"""
GoliTransit Backend — Configuration Loader
============================================
Reads config.json from the project root and exposes typed settings
to the rest of the backend.

Integration:
  - Used by main.py for CORS origins and server config
  - Used by graph_service.py for OSM download parameters
  - Used by routing_engine.py for vehicle types and penalties
  - Used by anomaly_service.py for severity thresholds
  - Used by ml_integration.py for the prediction server URL
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any


# ─── Path to the global config file ──────────────────────────────
# Try multiple locations:
#   1. CONFIG_PATH environment variable (explicit override)
#   2. ./config.json (backend directory - for Render deployment)
#   3. ../config.json (project root - for local dev)
def _find_config_path():
    # Check environment variable first
    if "CONFIG_PATH" in os.environ:
        return os.environ["CONFIG_PATH"]
    
    # Check backend directory (Render deployment)
    backend_config = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(backend_config):
        return backend_config
    
    # Check parent directory (local development)
    root_config = os.path.join(os.path.dirname(__file__), "..", "config.json")
    if os.path.exists(root_config):
        return root_config
    
    # Default fallback
    return root_config

CONFIG_PATH = _find_config_path()


def _load_config() -> dict:
    """Load and parse the JSON config file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"\n[ERROR] Config file not found at: {CONFIG_PATH}")
        print(f"[ERROR] Tried locations:")
        print(f"         - {os.path.join(os.path.dirname(__file__), 'config.json')}")
        print(f"         - {os.path.join(os.path.dirname(__file__), '..', 'config.json')}")
        print(f"[ERROR] Please ensure config.json is in the project root or backend directory")
        raise
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] Invalid JSON in {CONFIG_PATH}: {e}")
        raise


_raw: dict = _load_config()


@dataclass
class Settings:
    """
    Typed settings object built from config.json.
    Access nested values via attributes for autocomplete and safety.
    """
    # Server
    backend_host: str = _raw.get("server", {}).get("backend_host", "0.0.0.0")
    backend_port: int = _raw.get("server", {}).get("backend_port", 8000)
    cors_origins: list[str] = field(default_factory=lambda: _raw.get("server", {}).get("cors_origins", ["*"]))

    # Database
    db_driver: str = _raw.get("database", {}).get("driver", "mysql+pymysql")
    db_user: str = _raw.get("database", {}).get("user", "golitransit")
    db_password: str = _raw.get("database", {}).get("password", "golitransit")
    db_host: str = _raw.get("database", {}).get("host", "localhost")
    db_port: int = _raw.get("database", {}).get("port", 3306)
    db_name: str = _raw.get("database", {}).get("database", "golitransit")

    # JWT
    jwt_secret_key: str = _raw.get("jwt", {}).get("secret_key", "your-secret-key-change-in-production")
    jwt_algorithm: str = _raw.get("jwt", {}).get("algorithm", "HS256")
    jwt_access_token_expire_minutes: int = _raw.get("jwt", {}).get("access_token_expire_minutes", 30)

    # Graph
    osm_location: str = _raw.get("graph", {}).get("default_location", "San Francisco, California, USA")
    network_type: str = _raw.get("graph", {}).get("network_type", "all")
    simplify_graph: bool = _raw.get("graph", {}).get("simplify", True)
    graph_center_lat: float = _raw.get("graph", {}).get("center_lat", 23.7639)
    graph_center_lng: float = _raw.get("graph", {}).get("center_lng", 90.4066)
    graph_radius_m: float = _raw.get("graph", {}).get("radius_m", 2000)

    # Vehicle types (dict of dicts)
    vehicle_types: dict[str, Any] = field(default_factory=lambda: _raw.get("vehicle_types", {}))

    # Mode-switch penalties
    mode_switch_penalties: dict[str, Any] = field(default_factory=lambda: _raw.get("mode_switch_penalties", {}))

    # Anomaly
    anomaly_config: dict[str, Any] = field(default_factory=lambda: _raw.get("anomaly", {}))

    # ML
    ml_prediction_url: str = _raw.get("ml", {}).get("prediction_server_url", "http://localhost:8001/predict")
    ml_fallback_to_default: bool = _raw.get("ml", {}).get("fallback_to_default", True)

    # Routing
    routing_algorithm: str = _raw.get("routing", {}).get("algorithm", "dijkstra")
    weight_attribute: str = _raw.get("routing", {}).get("weight_attribute", "travel_time")
    max_alternatives: int = _raw.get("routing", {}).get("max_alternatives", 3)
    multimodal_max_transfers: int = _raw.get("routing", {}).get("multimodal_max_transfers", 3)
    transfer_radius_meters: float = _raw.get("routing", {}).get("transfer_radius_meters", 500)

    # Demo scenarios
    demo_scenarios: dict[str, Any] = field(default_factory=lambda: _raw.get("demo_scenarios", {}))


# Singleton settings instance — import this everywhere
settings = Settings()
