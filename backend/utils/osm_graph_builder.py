"""
OSM Graph Builder - Multi-Modal Road Network Extraction
========================================================

Downloads and processes OpenStreetMap data into a NetworkX graph
with custom vehicle attributes and travel time calculations.

Features:
  - Downloads road networks from OSM via OSMnx
  - Adds vehicle-specific attributes (car, rickshaw, walking, transit)
  - Calculates per-mode travel times based on speeds
  - Implements graph caching for offline use
  - Handles coordinate normalization and edge cases
  - Provides fallback synthetic graph for offline development

Vehicle Rules (Dhaka context):
  - Major roads (motorway, trunk, primary): car=True, rickshaw=False, walk=True
  - Secondary roads: car=True, rickshaw=True, walk=True
  - Small roads/alleys (residential, service, path): car=False, rickshaw=True, walk=True

Usage:
  from utils.osm_graph_builder import build_graph, print_graph_stats
  
  graph = build_graph("Dhaka, Bangladesh")
  print_graph_stats(graph)
"""

import os
import json
import pickle
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import logging
import threading
from datetime import datetime

import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)

# ─── Road Type Classifications ───────────────────────────────────

MAJOR_ROADS = {
    "motorway", "trunk", "primary", "secondary", 
    "secondary_link", "primary_link", "trunk_link"
}

SECONDARY_ROADS = {
    "tertiary", "tertiary_link", "unclassified"
}

SMALL_ROADS_ALLEYS = {
    "residential", "service", "path", "footway",
    "cycleway", "pedestrian", "living_street", "alley"
}

# ─── Default Speeds (km/h) ───────────────────────────────────────

DEFAULT_SPEEDS = {
    "car": 40,           # km/h
    "bike": 15,          # km/h
    "rickshaw": 15,      # km/h (slower, local traffic)
    "walk": 5,           # km/h
    "transit": 30,       # km/h (bus/public transport)
}

# ─── Vehicle Allowed Rules ──────────────────────────────────────

VEHICLE_RULES = {
    "major_roads": {
        "car": True,
        "bike": False,
        "rickshaw": False,  # Major roads prohibit rickshaws in many cities
        "walk": True,
        "transit": True,
    },
    "secondary_roads": {
        "car": True,
        "bike": True,
        "rickshaw": True,
        "walk": True,
        "transit": True,
    },
    "small_roads_alleys": {
        "car": False,
        "bike": True,
        "rickshaw": True,
        "walk": True,
        "transit": False,
    },
}


def _classify_road_type(highway_tag: Any) -> str:
    """
    Classify a road type as major, secondary, or small/alley.
    
    Args:
        highway_tag: OSM 'highway' tag value (can be string or list)
    
    Returns:
        "major", "secondary", or "small_alley"
    """
    if isinstance(highway_tag, list):
        highway_tag = highway_tag[0] if highway_tag else "residential"
    
    highway_str = str(highway_tag).lower()
    
    if highway_str in MAJOR_ROADS:
        return "major"
    elif highway_str in SECONDARY_ROADS:
        return "secondary"
    else:
        return "small_alley"


def _get_vehicle_permissions(road_classification: str) -> Dict[str, bool]:
    """Get vehicle permissions for a road classification."""
    return VEHICLE_RULES.get(
        f"{road_classification}_roads" if road_classification != "small_alley" else "small_roads_alleys",
        VEHICLE_RULES["secondary_roads"]  # Default fallback
    )


def _extract_speed_kmh(edge_data: Dict[str, Any], highway_type: str) -> float:
    """
    Extract or estimate speed in km/h from edge data.
    
    Args:
        edge_data: OSM edge attributes
        highway_type: Highway tag value
    
    Returns:
        Speed in km/h
    """
    # Try OSMnx-added speed_kph first
    speed_kph = edge_data.get("speed_kph")
    if isinstance(speed_kph, (int, float)) and speed_kph > 0:
        return float(speed_kph)
    
    # Try maxspeed tag
    maxspeed = edge_data.get("maxspeed")
    if isinstance(maxspeed, list):
        maxspeed = maxspeed[0] if maxspeed else None
    
    if isinstance(maxspeed, str):
        # Extract digits from speed string (e.g., "50 km/h")
        digits = "".join(ch for ch in maxspeed if ch.isdigit() or ch == ".")
        if digits:
            try:
                return float(digits)
            except ValueError:
                pass
    
    if isinstance(maxspeed, (int, float)) and maxspeed > 0:
        return float(maxspeed)
    
    # Default speeds by road type
    road_classification = _classify_road_type(highway_type)
    if road_classification == "major":
        return 50.0
    elif road_classification == "secondary":
        return 40.0
    else:
        return 20.0


def _calculate_travel_times(length_m: float, speeds: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate travel times for each vehicle type.
    
    Args:
        length_m: Edge length in meters
        speeds: Speed dict {mode: speed_kmh}
    
    Returns:
        {mode: travel_time_seconds}
    """
    travel_times = {}
    for mode, speed_kmh in speeds.items():
        speed_mps = max(speed_kmh / 3.6, 0.1)  # km/h to m/s, min 0.1 m/s
        travel_time_s = (length_m / speed_mps) if length_m > 0 else 0.0
        travel_times[mode] = travel_time_s
    
    return travel_times


def _normalize_edge_attributes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Add/normalize vehicle attributes to all edges.
    
    Args:
        graph: NetworkX MultiDiGraph from OSMnx
    
    Returns:
        Modified graph with enriched attributes
    """
    for u, v, k, data in graph.edges(keys=True, data=True):
        # Normalize length
        if "length" not in data or data["length"] is None:
            data["length"] = 0.0
        data["length"] = float(data["length"])
        
        # Normalize highway tag
        highway_tag = data.get("highway", "residential")
        data["highway"] = str(highway_tag)
        
        # Classify road
        road_classification = _classify_road_type(highway_tag)
        data["road_classification"] = road_classification
        
        # Extract base speed
        base_speed = _extract_speed_kmh(data, highway_tag)
        data["speed_limit_kmh"] = base_speed
        
        # Add vehicle permissions
        vehicle_perms = _get_vehicle_permissions(road_classification)
        for vehicle, allowed in vehicle_perms.items():
            data[f"{vehicle}_allowed"] = allowed
        
        # Calculate per-mode speeds (respecting permissions)
        mode_speeds = {}
        for mode, default_speed in DEFAULT_SPEEDS.items():
            if data.get(f"{mode}_allowed", False):
                # Use vehicle's default speed, capped by road speed limit
                mode_speeds[mode] = min(default_speed, base_speed)
            else:
                # Vehicle not allowed - use infinity to exclude from routing
                mode_speeds[mode] = float("inf")
        
        # Calculate travel times per mode
        travel_times = _calculate_travel_times(data["length"], mode_speeds)
        data["travel_time_per_mode"] = travel_times
        
        # Set a finite default travel_time based on fastest allowed mode.
        allowed_times = [
            float(travel_times[m])
            for m in DEFAULT_SPEEDS.keys()
            if data.get(f"{m}_allowed", False) and travel_times.get(m) is not None and travel_times[m] != float("inf")
        ]
        data["travel_time"] = min(allowed_times) if allowed_times else float(data["length"]) / max(base_speed / 3.6, 0.1)
        
        # Store original base for anomaly tracking
        data["base_travel_time"] = data["travel_time"]
        data["anomaly_multiplier"] = 1.0
        data["ml_predicted"] = False
    
    return graph


def _save_graph_cache(graph: nx.MultiDiGraph, cache_path: str) -> None:
    """
    Save graph to cache file (GraphML format).
    
    Args:
        graph: NetworkX graph to cache
        cache_path: File path for cache
    """
    try:
        # Create parent directories if needed
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Save as GraphML
        nx.write_graphml(graph, cache_path)
        logger.info(f"Graph cached to: {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to cache graph: {e}")


def _load_graph_cache(cache_path: str) -> Optional[nx.MultiDiGraph]:
    """
    Load graph from cache if exists.
    
    Args:
        cache_path: Path to cached graph file
    
    Returns:
        Graph if found, None otherwise
    """
    if Path(cache_path).exists():
        try:
            graph = nx.read_graphml(cache_path)
            logger.info(f"Loaded graph from cache: {cache_path}")
            return graph
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    
    return None


def save_graph_cache_pkl(
    graph: nx.MultiDiGraph,
    location: str = "Dhaka, Bangladesh",
    output_dir: str = "./data/osm_cache"
) -> str:
    """
    Save graph to pickle file with metadata.
    
    Pickle format is much faster than GraphML for large graphs and
    preserves all complex Python object attributes.
    
    Args:
        graph: NetworkX MultiDiGraph to serialize
        location: Location name (used for filename)
        output_dir: Directory to save pickle file
    
    Returns:
        Path to saved pickle file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generate filename from location
    safe_name = location.replace(", ", "_").lower().replace(" ", "_")
    cache_file = output_path / f"{safe_name}_graph.pkl"
    
    metadata_file = output_path / f"{safe_name}_graph_meta.json"
    
    try:
        logger.info(f"Saving graph to pickle: {cache_file}")
        
        # Save the graph as pickle
        with open(cache_file, 'wb') as f:
            pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Create metadata file
        metadata = {
            "location": location,
            "timestamp": datetime.now().isoformat(),
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "pickle_file": cache_file.name,
            "file_size_bytes": cache_file.stat().st_size,
            "file_size_mb": round(cache_file.stat().st_size / (1024 * 1024), 2),
        }
        
        # Calculate simple hash of graph structure for verification
        edge_count_str = f"{graph.number_of_nodes()}_{graph.number_of_edges()}"
        metadata["structure_hash"] = hashlib.md5(edge_count_str.encode()).hexdigest()[:12]
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(
            f"Graph saved: {cache_file.name} "
            f"({metadata['file_size_mb']} MB, "
            f"{graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges)"
        )
        
        return str(cache_file)
        
    except Exception as e:
        logger.error(f"Failed to save graph cache: {e}")
        raise


def load_graph_cache_pkl(cache_file: str) -> Optional[nx.MultiDiGraph]:
    """
    Load graph from pickle file.
    
    Args:
        cache_file: Path to pickle file
    
    Returns:
        NetworkX graph if found and valid, None otherwise
    """
    cache_path = Path(cache_file)
    
    if not cache_path.exists():
        logger.debug(f"Cache file not found: {cache_file}")
        return None
    
    try:
        logger.info(f"Loading graph from pickle: {cache_file}")
        load_start = time.time()
        
        with open(cache_path, 'rb') as f:
            graph = pickle.load(f)
        
        load_time = time.time() - load_start
        logger.info(
            f"Graph loaded in {load_time:.2f}s: "
            f"{graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges"
        )
        
        return graph
        
    except Exception as e:
        logger.error(f"Failed to load graph cache: {e}")
        return None


def _create_synthetic_dhaka_graph() -> nx.MultiDiGraph:
    """
    Create a synthetic graph for Dhaka if OSM download fails.
    
    Uses realistic coordinates and road structure for testing.
    
    Returns:
        NetworkX graph of synthetic Dhaka street network
    """
    logger.info("Creating synthetic Dhaka graph for offline use")
    
    G = nx.MultiDiGraph()
    
    # Central Dhaka coordinates (Motijheel/Gulshan area)
    # Base: 23.8103, 90.4125
    nodes_data = {
        "n1": {"x": 90.4100, "y": 23.8090, "name": "Node 1"},
        "n2": {"x": 90.4140, "y": 23.8090, "name": "Node 2 - Major"},
        "n3": {"x": 90.4180, "y": 23.8090, "name": "Node 3"},
        "n4": {"x": 90.4100, "y": 23.8110, "name": "Node 4"},
        "n5": {"x": 90.4140, "y": 23.8110, "name": "Node 5 - Central"},
        "n6": {"x": 90.4180, "y": 23.8110, "name": "Node 6"},
        "n7": {"x": 90.4100, "y": 23.8130, "name": "Node 7"},
        "n8": {"x": 90.4140, "y": 23.8130, "name": "Node 8 - Major"},
        "n9": {"x": 90.4180, "y": 23.8130, "name": "Node 9"},
    }
    
    for node_id, attrs in nodes_data.items():
        G.add_node(node_id, **attrs)
    
    # Define edges with realistic Dhaka road types
    edges_data = [
        # Bottom row - residential with some secondary
        ("n1", "n2", {"highway": "secondary", "length": 450, "maxspeed": "60"}),
        ("n2", "n3", {"highway": "residential", "length": 450, "maxspeed": "40"}),
        # Middle row - mix including motorway access
        ("n4", "n5", {"highway": "primary", "length": 450, "maxspeed": "80"}),
        ("n5", "n6", {"highway": "secondary", "length": 450, "maxspeed": "60"}),
        # Top row - major roads
        ("n7", "n8", {"highway": "trunk", "length": 400, "maxspeed": "100"}),
        ("n8", "n9", {"highway": "primary", "length": 400, "maxspeed": "80"}),
        # Vertical connectors
        ("n1", "n4", {"highway": "residential", "length": 550, "maxspeed": "40"}),
        ("n4", "n7", {"highway": "tertiary", "length": 550, "maxspeed": "50"}),
        ("n2", "n5", {"highway": "secondary", "length": 550, "maxspeed": "60"}),
        ("n5", "n8", {"highway": "secondary", "length": 550, "maxspeed": "60"}),
        ("n3", "n6", {"highway": "residential", "length": 550, "maxspeed": "40"}),
        ("n6", "n9", {"highway": "tertiary", "length": 550, "maxspeed": "50"}),
        # Alleys and shortcuts
        ("n1", "n5", {"highway": "path", "length": 700, "maxspeed": "20"}),
        ("n2", "n4", {"highway": "service", "length": 700, "maxspeed": "30"}),
        ("n5", "n9", {"highway": "alley", "length": 700, "maxspeed": "15"}),
        ("n8", "n6", {"highway": "residential", "length": 700, "maxspeed": "40"}),
    ]
    
    # Add edges bidirectionally
    for source, target, edge_attrs in edges_data:
        G.add_edge(source, target, key=0, **edge_attrs)
        G.add_edge(target, source, key=0, **edge_attrs)  # Bidirectional
    
    # Normalize attributes
    G = _normalize_edge_attributes(G)
    
    return G


def build_graph(
    location: str = "Dhaka, Bangladesh",
    cache_dir: str = "./data/osm_cache",
    force_download: bool = False,
) -> nx.MultiDiGraph:
    """
    Build a road network graph from OpenStreetMap or synthetic data.
    
    For Dhaka and other cities in Bangladesh, uses high-quality synthetic graph
    due to OSM API download time constraints. For other locations, attempts
    real OSM download with fallback to synthetic.
    
    Args:
        location: OSM location string (e.g., "Dhaka, Bangladesh")
        cache_dir: Directory for caching graphs
        force_download: Skip cache and re-download from OSM
    
    Returns:
        NetworkX MultiDiGraph with enriched vehicle attributes
    """
    # For Dhaka/Bangladesh, prefer a bounded real OSM download centered on Dhaka.
    # This gives road-following geometry while keeping query size manageable.
    if "dhaka" in location.lower() or "bangladesh" in location.lower():
        try:
            logger.info(f"Downloading bounded OSM graph for {location} (Dhaka center)")
            graph = ox.graph_from_point(
                center_point=(23.8103, 90.4125),
                dist=12000,
                network_type="drive",
                simplify=True,
            )
            for _, data in graph.nodes(data=True):
                if "y" in data:
                    data["y"] = float(data["y"])
                if "x" in data:
                    data["x"] = float(data["x"])

            logger.info(
                f"Dhaka OSM graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
            )
            graph = _normalize_edge_attributes(graph)
            return graph
        except Exception as e:
            logger.warning(f"Dhaka OSM download failed ({e}), using synthetic graph")
            graph = _create_synthetic_dhaka_graph()
            graph = _normalize_edge_attributes(graph)
            return graph
    
    # For other locations, try OSM cache/download
    cache_file = Path(cache_dir) / f"{location.replace(', ', '_').lower()}.graphml"
    
    # Try to load from cache
    if not force_download:
        cached_graph = _load_graph_cache(str(cache_file))
        if cached_graph is not None:
            return cached_graph
    
    # Try to download from OSM
    try:
        logger.info(f"Downloading graph for: {location}")
        
        # Download with error handling for coordinate normalization
        graph = ox.graph_from_place(
            location,
            network_type="drive",
            simplify=True,
            retain_all=False,
            custom_filter=None,
        )
        
        # Normalize node coordinates (handle potential float issues)
        for node, data in graph.nodes(data=True):
            if "y" in data:
                data["y"] = float(data["y"])
            if "x" in data:
                data["x"] = float(data["x"])
        
        logger.info(f"OSM graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        
    except Exception as e:
        logger.warning(f"OSM download failed ({e}), using synthetic graph")
        graph = _create_synthetic_dhaka_graph()
    
    # Normalize/enrich attributes
    graph = _normalize_edge_attributes(graph)
    
    # Skip caching for graphs with complex dict attributes
    # (GraphML serialization issue)
    # _save_graph_cache(graph, str(cache_file))
    
    return graph


def print_graph_stats(graph: nx.MultiDiGraph) -> None:
    """
    Print basic statistics about the graph.
    
    Args:
        graph: NetworkX graph
    """
    print("\n" + "=" * 60)
    print("GRAPH STATISTICS")
    print("=" * 60)
    print(f"Nodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")
    
    # Vehicle availability stats
    car_edges = sum(1 for _, _, d in graph.edges(data=True) if d.get("car_allowed", False))
    rickshaw_edges = sum(1 for _, _, d in graph.edges(data=True) if d.get("rickshaw_allowed", False))
    walk_edges = sum(1 for _, _, d in graph.edges(data=True) if d.get("walk_allowed", False))
    transit_edges = sum(1 for _, _, d in graph.edges(data=True) if d.get("transit_allowed", False))
    
    print(f"\nVehicle Coverage:")
    print(f"  Car: {car_edges}/{graph.number_of_edges()} edges ({car_edges*100/graph.number_of_edges():.1f}%)")
    print(f"  Rickshaw: {rickshaw_edges}/{graph.number_of_edges()} edges ({rickshaw_edges*100/graph.number_of_edges():.1f}%)")
    print(f"  Walk: {walk_edges}/{graph.number_of_edges()} edges ({walk_edges*100/graph.number_of_edges():.1f}%)")
    print(f"  Transit: {transit_edges}/{graph.number_of_edges()} edges ({transit_edges*100/graph.number_of_edges():.1f}%)")
    
    # Distance stats
    total_length = sum(d.get("length", 0) for _, _, d in graph.edges(data=True))
    print(f"\nTotal Network Length: {total_length/1000:.2f} km")
    
    # Road type distribution
    road_types = {}
    for _, _, d in graph.edges(data=True):
        hw = d.get("highway", "unknown")
        road_types[hw] = road_types.get(hw, 0) + 1
    
    print("\nRoad Type Distribution:")
    for hw, count in sorted(road_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {hw}: {count} edges")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Test the graph builder
    print("Building road network graph for Dhaka, Bangladesh...")
    
    graph = build_graph("Dhaka, Bangladesh", force_download=False)
    print_graph_stats(graph)
    
    # Print sample edges
    print("Sample edges with vehicle attributes:")
    print("-" * 60)
    for i, (u, v, k, data) in enumerate(graph.edges(keys=True, data=True)):
        if i >= 3:
            break
        print(f"\n{u} → {v}")
        print(f"  Length: {data.get('length', 0):.1f}m")
        print(f"  Road Type: {data.get('highway', 'unknown')}")
        print(f"  Car allowed: {data.get('car_allowed', False)}")
        print(f"  Rickshaw allowed: {data.get('rickshaw_allowed', False)}")
        print(f"  Walk allowed: {data.get('walk_allowed', False)}")
        travel_times = data.get("travel_time_per_mode", {})
        print(f"  Travel times: {' | '.join(f'{m}: {t:.1f}s' for m, t in travel_times.items())}")
