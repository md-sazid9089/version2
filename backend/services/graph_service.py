"""
Graph Service — OSM Import & NetworkX Graph Management
========================================================
Responsible for loading and serving the in-memory road graph.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Optional

import networkx as nx
import numpy as np

from config import settings
from models.graph_models import GraphSnapshot, GraphNode, GraphEdge


_PROFILE_ENV = "ROUTING_PROFILE"
_PROFILE_FALSE_VALUES = {"0", "false", "off", "no"}


class _OsmnxProxy:
    """Lazy osmnx module proxy to keep startup memory low."""

    def __init__(self):
        self._module = None

    def _load(self):
        if self._module is None:
            import osmnx as loaded_osmnx

            self._module = loaded_osmnx
        return self._module

    def __getattr__(self, name):
        return getattr(self._load(), name)


ox = _OsmnxProxy()


def _profiling_enabled() -> bool:
    value = str(os.getenv(_PROFILE_ENV, "1")).strip().lower()
    return value not in _PROFILE_FALSE_VALUES


def _fmt_metric(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _profile_log(stage: str, **metrics):
    if not _profiling_enabled():
        return
    payload = " ".join(f"{k}={_fmt_metric(v)}" for k, v in metrics.items())
    print(f"[Profile][GraphService] {stage} {payload}".rstrip())


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _project_point_to_segment(
    p_lat: float,
    p_lng: float,
    a_lat: float,
    a_lng: float,
    b_lat: float,
    b_lng: float,
) -> tuple[float, float, float]:
    """
    Project point P onto line segment A→B.

    Returns:
        (fraction, proj_lat, proj_lng)
        fraction: 0.0 = at A, 1.0 = at B, clamped to [0, 1]
        proj_lat/proj_lng: the projected point coordinates
    """
    dx = b_lng - a_lng
    dy = b_lat - a_lat
    len_sq = dx * dx + dy * dy

    if len_sq < 1e-14:
        # A and B are the same point
        return 0.0, a_lat, a_lng

    # t = dot(AP, AB) / |AB|^2  → fraction along segment
    t = ((p_lng - a_lng) * dx + (p_lat - a_lat) * dy) / len_sq
    t = max(0.0, min(1.0, t))  # clamp to segment

    proj_lat = a_lat + t * dy
    proj_lng = a_lng + t * dx
    return t, proj_lat, proj_lng


def _first_highway_value(highway: object) -> str:
    if isinstance(highway, list) and highway:
        return str(highway[0])
    if isinstance(highway, str):
        return highway
    return "unknown"


def _parse_maxspeed_kmh(maxspeed: object) -> Optional[float]:
    if maxspeed is None:
        return None
    if isinstance(maxspeed, list) and maxspeed:
        maxspeed = maxspeed[0]
    text = str(maxspeed).strip().lower()
    if not text:
        return None

    number = "".join(ch for ch in text if (ch.isdigit() or ch == "."))
    if not number:
        return None

    try:
        value = float(number)
    except ValueError:
        return None

    if "mph" in text:
        return value * 1.60934
    return value


def _fallback_speed_for_road(road_type: str) -> float:
    major = {"motorway", "trunk", "primary"}
    secondary = {"secondary", "tertiary"}
    small = {
        "residential",
        "service",
        "unclassified",
        "road",
        "living_street",
        "path",
        "track",
        "footway",
        "cycleway",
    }

    if road_type in major:
        return 50.0
    if road_type in secondary:
        return 35.0
    if road_type in small:
        return 20.0
    return 30.0


def _is_main_road(road_type: str) -> bool:
    return road_type in {
        "motorway",
        "motorway_link",
        "trunk",
        "trunk_link",
        "primary",
        "primary_link",
        "secondary",
        "secondary_link",
        "tertiary",
        "tertiary_link",
    }


class GraphService:
    """Singleton service managing the in-memory road graph."""

    def __init__(self):
        self._graph: Optional[nx.MultiDiGraph] = None
        self._loaded = False
        self._graph_lock = threading.RLock()
        self._last_load_error: Optional[str] = None
        self._center_lat = float(settings.graph_center_lat)
        self._center_lng = float(settings.graph_center_lng)
        self._radius_m = float(settings.graph_radius_m)
        self._mode_subgraph_cache: dict[str, nx.MultiDiGraph] = {}
        self._out_edges_by_node: dict[object, tuple[tuple[object, object], ...]] = {}
        self._undirected_edges_by_node: dict[
            object, tuple[tuple[object, object], ...]
        ] = {}
        self._graph_version: int = 0
        self._node_ids: list = []
        self._node_coords: np.ndarray | None = None
        self._node_kdtree = None

    def ensure_loaded(
        self,
        location: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> Optional[nx.MultiDiGraph]:
        """Lazy-load graph once and return the shared instance."""
        if self._loaded and self._graph is not None:
            return self._graph

        with self._graph_lock:
            if self._loaded and self._graph is not None:
                return self._graph

            try:
                self.load_graph(location=location)
            except Exception as exc:
                self._loaded = False
                self._graph = None
                self._last_load_error = str(exc)
                if raise_on_error:
                    raise
                print(f"[GraphService] Lazy load failed: {exc}")
                return None

        return self._graph

    def get_last_load_error(self) -> Optional[str]:
        return self._last_load_error

    def load_graph(self, location: Optional[str] = None):
        """Download/load OSM graph and normalize edge attributes for routing."""
        with self._graph_lock:
            self._last_load_error = None

        load_started = time.perf_counter()
        fetch_ms = 0.0
        trim_ms = 0.0
        normalize_ms = 0.0
        mode_cache_ms = 0.0
        edge_index_ms = 0.0
        spatial_index_ms = 0.0

        location = location or settings.osm_location
        print(
            f"[GraphService] Loading graph for: {location} "
            f"(center={self._center_lat},{self._center_lng}, radius={self._radius_m}m)"
        )

        graph: Optional[nx.MultiDiGraph] = None

        try:
            fetch_started = time.perf_counter()
            if location != settings.osm_location:
                graph = ox.graph_from_place(
                    location,
                    network_type=settings.network_type,
                    simplify=settings.simplify_graph,
                )
            else:
                # Default runtime path: local neighborhood graph around AUST.
                graph = ox.graph_from_point(
                    center_point=(self._center_lat, self._center_lng),
                    dist=self._radius_m,
                    dist_type="bbox",
                    network_type=settings.network_type,
                    simplify=settings.simplify_graph,
                )

                # Enforce strict circular radius (not just bounding box).
                nodes_outside = []
                for node_id, node_data in graph.nodes(data=True):
                    y = float(node_data.get("y") or 0.0)
                    x = float(node_data.get("x") or 0.0)
                    if (
                        _haversine_m(self._center_lat, self._center_lng, y, x)
                        > self._radius_m
                    ):
                        nodes_outside.append(node_id)

                if nodes_outside:
                    graph.remove_nodes_from(nodes_outside)

            fetch_ms = (time.perf_counter() - fetch_started) * 1000.0

            # Keep only the largest connected component to avoid tiny disconnected scraps.
            trim_started = time.perf_counter()
            if graph.number_of_nodes() > 0:
                largest_cc = max(nx.weakly_connected_components(graph), key=len)
                graph = graph.subgraph(largest_cc).copy()
            trim_ms = (time.perf_counter() - trim_started) * 1000.0
        except Exception as e:
            raise RuntimeError(
                f"Failed to load OSM graph around AUST center ({self._center_lat}, {self._center_lng})"
            ) from e

        if graph is None:
            raise RuntimeError("Graph load failed: no graph returned")

        self._graph = graph
        normalize_started = time.perf_counter()
        self._normalize_edge_attributes()
        normalize_ms = (time.perf_counter() - normalize_started) * 1000.0

        mode_cache_started = time.perf_counter()
        self._rebuild_mode_subgraph_cache()
        mode_cache_ms = (time.perf_counter() - mode_cache_started) * 1000.0

        edge_index_started = time.perf_counter()
        self._rebuild_edge_indexes()
        edge_index_ms = (time.perf_counter() - edge_index_started) * 1000.0

        spatial_index_started = time.perf_counter()
        self._rebuild_spatial_index()
        spatial_index_ms = (time.perf_counter() - spatial_index_started) * 1000.0

        self._graph_version += 1
        self._loaded = True

        total_ms = (time.perf_counter() - load_started) * 1000.0
        print(
            f"[GraphService] Graph loaded — {self.node_count()} nodes, {self.edge_count()} edges"
        )
        _profile_log(
            "load_graph_complete",
            location=location,
            nodes=self.node_count(),
            edges=self.edge_count(),
            fetch_ms=fetch_ms,
            trim_ms=trim_ms,
            normalize_ms=normalize_ms,
            subgraph_cache_ms=mode_cache_ms,
            edge_index_ms=edge_index_ms,
            spatial_index_ms=spatial_index_ms,
            total_ms=total_ms,
        )

    def _rebuild_edge_indexes(self):
        self._out_edges_by_node = {}
        self._undirected_edges_by_node = {}

        if not self._graph:
            return

        out_edges: dict[object, list[tuple[object, object]]] = {}
        undirected_edges: dict[object, list[tuple[object, object]]] = {}

        for u, v, k in self._graph.edges(keys=True):
            out_edges.setdefault(u, []).append((v, k))
            undirected_edges.setdefault(u, []).append((v, k))
            undirected_edges.setdefault(v, []).append((u, k))

        self._out_edges_by_node = {
            node_id: tuple(edges) for node_id, edges in out_edges.items()
        }
        self._undirected_edges_by_node = {
            node_id: tuple(edges) for node_id, edges in undirected_edges.items()
        }

    def get_outgoing_edges(
        self,
        node_id,
        *,
        undirected: bool = False,
    ) -> tuple[tuple[object, object], ...]:
        if undirected:
            return self._undirected_edges_by_node.get(node_id, ())
        return self._out_edges_by_node.get(node_id, ())

    def _rebuild_spatial_index(self):
        self._node_ids = []
        self._node_coords = None
        self._node_kdtree = None

        if not self._graph or self._graph.number_of_nodes() == 0:
            return

        node_ids: list = []
        coords: list[list[float]] = []
        for node_id, node_data in self._graph.nodes(data=True):
            y = node_data.get("y")
            x = node_data.get("x")
            if y is None or x is None:
                continue
            node_ids.append(node_id)
            coords.append([float(y), float(x)])

        if not node_ids:
            return

        arr = np.asarray(coords, dtype=float)
        if arr.shape[0] == 0:
            return

        self._node_ids = node_ids
        self._node_coords = arr
        from sklearn.neighbors import KDTree

        self._node_kdtree = KDTree(arr, leaf_size=40)

    def _query_candidates_from_kdtree(self, lat: float, lng: float, k: int) -> list:
        if self._node_kdtree is None or not self._node_ids:
            return []

        k = max(1, int(k))
        k = min(k, len(self._node_ids))
        if k <= 0:
            return []

        _dist, idx = self._node_kdtree.query(np.asarray([[lat, lng]], dtype=float), k=k)
        indices = idx[0].tolist() if len(idx) > 0 else []
        candidates = []
        for i in indices:
            if 0 <= i < len(self._node_ids):
                candidates.append(self._node_ids[i])
        return candidates

    def _rebuild_mode_subgraph_cache(self):
        # Keep cached mode views lightweight by invalidating only.
        self._mode_subgraph_cache = {}

    def get_graph_version(self) -> int:
        return int(self._graph_version)

    def mark_graph_changed(
        self,
        *,
        mode_constraints_changed: bool = False,
    ):
        self._graph_version += 1
        if mode_constraints_changed:
            self._rebuild_mode_subgraph_cache()

    def _normalize_edge_attributes(self):
        if not self._graph:
            return

        for _, _, _, data in self._graph.edges(keys=True, data=True):
            length_m = float(data.get("length") or 0.0)
            road_type = _first_highway_value(data.get("highway"))
            service_tag = str(data.get("service", "")).lower()
            maxspeed_kmh = _parse_maxspeed_kmh(
                data.get("maxspeed")
            ) or _fallback_speed_for_road(road_type)
            base_travel_time_s = (
                length_m / (maxspeed_kmh / 3.6) if maxspeed_kmh > 0 else 1.0
            )

            data["length"] = length_m
            data["road_type"] = road_type
            data["speed_limit_kmh"] = maxspeed_kmh
            data["travel_time"] = base_travel_time_s
            data["base_travel_time"] = base_travel_time_s
            data["mode_travel_time_s"] = base_travel_time_s
            data["anomaly_multiplier"] = 1.0
            data["ml_predicted"] = False

            # ── Spec-mandated OSM tag constraints ────────────────
            # Start with config-based permissions, then override per OSM tags
            for mode, mode_cfg in settings.vehicle_types.items():
                allowed_road_types = set(mode_cfg.get("allowed_road_types", []))
                mode_speed = float(
                    mode_cfg.get("default_speed_kmh", maxspeed_kmh) or maxspeed_kmh
                )
                mode_allowed = road_type in allowed_road_types
                mode_time_s = (
                    length_m / (mode_speed / 3.6)
                    if mode_speed > 0
                    else base_travel_time_s
                )

                data[f"{mode}_allowed"] = mode_allowed
                data[f"{mode}_travel_time"] = mode_time_s

            # OSM tag overrides (hackathon design rules)
            # 1. highway=footway → car NOT allowed
            if road_type == "footway":
                data["car_allowed"] = False
                data["transit_allowed"] = False

            # 2. service=alley → only rickshaw + walk
            if service_tag == "alley" or road_type == "alley":
                data["car_allowed"] = False
                data["bike_allowed"] = False
                data["transit_allowed"] = False
                data["rickshaw_allowed"] = True
                data["walk_allowed"] = True

            # 3. highway=motorway → car only
            if road_type in ("motorway", "motorway_link"):
                data["rickshaw_allowed"] = False
                data["walk_allowed"] = False
                data["bike_allowed"] = False
                data["transit_allowed"] = False
                data["car_allowed"] = True

            # Keep bike permissions based on its own mode configuration.
            # Do not forcibly mirror rickshaw constraints, otherwise valid
            # bike corridors can disappear and trigger synthetic fallback routes.
            data["bike_allowed"] = bool(data.get("bike_allowed", False))

            # Bus (transit) should only run on main roads.
            if not _is_main_road(road_type):
                data["transit_allowed"] = False

            # Transport refinement timing model:
            # bike faster than rickshaw, slightly faster than car; bus slower than car.
            car_base = float(
                data.get("car_travel_time", base_travel_time_s) or base_travel_time_s
            )
            bike_time = max(car_base * 0.90, 0.01)
            rickshaw_time = max(bike_time * 1.35, 0.01)
            transit_time = max(car_base * 1.30, 0.01)

            data["car_travel_time"] = car_base
            data["bike_travel_time"] = bike_time
            data["rickshaw_travel_time"] = rickshaw_time
            data["transit_travel_time"] = transit_time

            # ── Build spec-compatible weights & constraints dicts ─
            data["base_weight"] = length_m
            data["weights"] = {}
            data["constraints"] = {}
            for mode in settings.vehicle_types:
                data[f"{mode}_base_travel_time"] = float(
                    data.get(f"{mode}_travel_time", base_travel_time_s)
                )
                data[f"{mode}_base_allowed"] = bool(data.get(f"{mode}_allowed", False))
                data["weights"][mode] = float(
                    data.get(f"{mode}_travel_time", base_travel_time_s)
                )
                data["constraints"][f"{mode}_allowed"] = bool(
                    data.get(f"{mode}_allowed", False)
                )

    def _annotate_graph_edges(self):
        """Backward-compatible alias used by existing tests and callers."""
        self._normalize_edge_attributes()

    def is_loaded(self) -> bool:
        return self._loaded and self._graph is not None

    def get_graph(self) -> Optional[nx.MultiDiGraph]:
        """Return the underlying NetworkX graph for direct access."""
        return self._graph

    def node_count(self) -> int:
        if not self._loaded or self._graph is None:
            return 0
        return self._graph.number_of_nodes()

    def edge_count(self) -> int:
        if not self._loaded or self._graph is None:
            return 0
        return self._graph.number_of_edges()

    def get_nearest_node(self, lat: float, lng: float, max_distance_m: float = 5000.0):
        """
        Find the nearest graph node using Haversine distance.

        Args:
            lat: User latitude
            lng: User longitude
            max_distance_m: Maximum snap distance in meters.
                            Returns None if closest node is farther.

        Returns:
            Node ID of the nearest node, or None if no node within threshold.
        """
        if not self._graph:
            return None

        # Fast path: KDTree candidate query, then exact Haversine ranking.
        if self._node_kdtree is not None and self._node_ids:
            candidates = self._query_candidates_from_kdtree(lat, lng, k=10)
            best_node = None
            best_dist_m = float("inf")
            for node_id in candidates:
                node_data = self._graph.nodes.get(node_id, {})
                y = node_data.get("y")
                x = node_data.get("x")
                if y is None or x is None:
                    continue
                dist_m = _haversine_m(lat, lng, float(y), float(x))
                if dist_m < best_dist_m:
                    best_dist_m = dist_m
                    best_node = node_id

            if best_node is not None:
                if best_dist_m > max_distance_m:
                    return None
                return best_node

        best_node = None
        best_dist_m = float("inf")

        for node_id, node_data in self._graph.nodes(data=True):
            y = node_data.get("y")
            x = node_data.get("x")
            if y is None or x is None:
                continue

            dist_m = _haversine_m(lat, lng, float(y), float(x))
            if dist_m < best_dist_m:
                best_dist_m = dist_m
                best_node = node_id

        # Threshold check: if the closest node is too far, return None
        if best_dist_m > max_distance_m:
            return None

        return best_node

    def get_nearest_node_in_graph(self, graph: nx.MultiDiGraph, lat: float, lng: float):
        """Find nearest node inside the provided graph."""
        if graph is None or graph.number_of_nodes() == 0:
            return None

        best_node = None
        best_dist_m = float("inf")

        for node_id, node_data in graph.nodes(data=True):
            y = node_data.get("y")
            x = node_data.get("x")
            if y is None or x is None:
                continue

            dist_m = _haversine_m(lat, lng, float(y), float(x))
            if dist_m < best_dist_m:
                best_dist_m = dist_m
                best_node = node_id

        return best_node

    def get_k_nearest_nodes_in_graph(
        self, graph: nx.MultiDiGraph, lat: float, lng: float, k: int = 8
    ):
        """Return k nearest nodes inside the provided graph, sorted by distance."""
        if graph is None or graph.number_of_nodes() == 0:
            return []

        # Use KDTree index when querying against the base graph.
        if graph is self._graph and self._node_kdtree is not None and self._node_ids:
            # Over-query to offset euclidean(lat,lng) approximation before exact Haversine ranking.
            requested = max(1, int(k))
            overquery = min(len(self._node_ids), max(requested * 4, requested))
            candidates = self._query_candidates_from_kdtree(lat, lng, k=overquery)

            ranked = []
            for node_id in candidates:
                node_data = self._graph.nodes.get(node_id, {})
                y = node_data.get("y")
                x = node_data.get("x")
                if y is None or x is None:
                    continue
                dist_m = _haversine_m(lat, lng, float(y), float(x))
                ranked.append((dist_m, node_id))

            ranked.sort(key=lambda t: t[0])
            return [node_id for _, node_id in ranked[:requested]]

        ranked = []
        for node_id, node_data in graph.nodes(data=True):
            y = node_data.get("y")
            x = node_data.get("x")
            if y is None or x is None:
                continue
            dist_m = _haversine_m(lat, lng, float(y), float(x))
            ranked.append((dist_m, node_id))

        ranked.sort(key=lambda t: t[0])
        return [node_id for _, node_id in ranked[: max(1, int(k))]]

    def get_nearest_node_with_distance(self, lat: float, lng: float):
        """
        Find the nearest graph node and return both the node ID and distance.

        Returns:
            (node_id, distance_m) tuple, or (None, inf) if graph not loaded.
        """
        if not self._graph:
            return None, float("inf")

        if self._node_kdtree is not None and self._node_ids:
            candidates = self._query_candidates_from_kdtree(lat, lng, k=10)
            best_node = None
            best_dist_m = float("inf")
            for node_id in candidates:
                node_data = self._graph.nodes.get(node_id, {})
                y = node_data.get("y")
                x = node_data.get("x")
                if y is None or x is None:
                    continue
                dist_m = _haversine_m(lat, lng, float(y), float(x))
                if dist_m < best_dist_m:
                    best_dist_m = dist_m
                    best_node = node_id
            if best_node is not None:
                return best_node, best_dist_m

        best_node = None
        best_dist_m = float("inf")

        for node_id, node_data in self._graph.nodes(data=True):
            y = node_data.get("y")
            x = node_data.get("x")
            if y is None or x is None:
                continue

            dist_m = _haversine_m(lat, lng, float(y), float(x))
            if dist_m < best_dist_m:
                best_dist_m = dist_m
                best_node = node_id

        return best_node, best_dist_m

    def snap_to_nearest_edge(self, lat: float, lng: float):
        """
        Find the nearest point on any graph edge (road segment).

        If the user is far from any intersection but close to a road segment,
        this finds the closest edge and creates a virtual projection point.

        Returns:
            dict with:
              - source: source node of nearest edge
              - target: target node of nearest edge
              - snap_node: the better endpoint to use (closest of source/target)
              - distance_m: distance from user to the snap point
              - fraction: 0.0-1.0 position along the edge

            Returns None if graph not loaded.
        """
        if not self._graph:
            return None

        best_edge = None
        best_dist = float("inf")
        best_fraction = 0.0

        for u, v, _, data in self._graph.edges(keys=True, data=True):
            u_data = self._graph.nodes.get(u, {})
            v_data = self._graph.nodes.get(v, {})

            u_lat = float(u_data.get("y", 0.0))
            u_lng = float(u_data.get("x", 0.0))
            v_lat = float(v_data.get("y", 0.0))
            v_lng = float(v_data.get("x", 0.0))

            # Project point onto the line segment u->v
            fraction, proj_lat, proj_lng = _project_point_to_segment(
                lat, lng, u_lat, u_lng, v_lat, v_lng
            )
            dist = _haversine_m(lat, lng, proj_lat, proj_lng)

            if dist < best_dist:
                best_dist = dist
                best_edge = (u, v)
                best_fraction = fraction

        if best_edge is None:
            return None

        u, v = best_edge
        # Return the closer endpoint as the snap node
        u_data = self._graph.nodes.get(u, {})
        v_data = self._graph.nodes.get(v, {})
        dist_u = _haversine_m(
            lat, lng, float(u_data.get("y", 0)), float(u_data.get("x", 0))
        )
        dist_v = _haversine_m(
            lat, lng, float(v_data.get("y", 0)), float(v_data.get("x", 0))
        )
        snap_node = u if dist_u <= dist_v else v

        return {
            "source": u,
            "target": v,
            "snap_node": snap_node,
            "distance_m": best_dist,
            "fraction": best_fraction,
        }

    def get_node_accessibility(self, node_id: str) -> list[str]:
        """
        Determine which transport modes can access a given node.

        A node is accessible to a mode if at least one outgoing edge
        allows that mode (has mode_allowed=True).

        Args:
            node_id: The node ID to check

        Returns:
            List of mode strings (car, bike, walk, transit, rickshaw) that can access this node
        """
        if not self._graph or node_id not in self._graph:
            return []

        accessible = set()

        # Check all outgoing edges from this node
        if node_id in self._graph:
            for v, edge_dict in self._graph[node_id].items():
                for key, data in edge_dict.items():
                    # Check each mode
                    for mode in settings.vehicle_types.keys():
                        mode_flag = f"{mode}_allowed"
                        if bool(data.get(mode_flag, False)):
                            accessible.add(mode)

        # Also check incoming edges
        for u in self._graph.pred.get(node_id, {}):
            edge_dict = self._graph[u].get(node_id, {})
            for key, data in edge_dict.items():
                for mode in settings.vehicle_types.keys():
                    mode_flag = f"{mode}_allowed"
                    if bool(data.get(mode_flag, False)):
                        accessible.add(mode)

        return sorted(list(accessible))

    def get_subgraph_for_mode(self, mode: str):
        if not self._graph:
            return None

        cached = self._mode_subgraph_cache.get(mode)
        if cached is not None:
            return cached

        mode_flag = f"{mode}_allowed"

        def _edge_filter(u, v, k):
            edge_data = self._graph.get_edge_data(u, v, key=k, default=None)
            if not edge_data:
                return False
            return bool(edge_data.get(mode_flag, False))

        mode_view = nx.subgraph_view(
            self._graph,
            filter_edge=_edge_filter,
        )
        self._mode_subgraph_cache[mode] = mode_view
        return mode_view

    def update_edge_weight(self, source: str, target: str, multiplier: float):
        if not self._graph:
            return

        changed = False
        if self._graph.has_edge(source, target):
            for key in self._graph[source][target]:
                edge_data = self._graph[source][target][key]
                base = float(
                    edge_data.get("base_travel_time")
                    or edge_data.get("travel_time")
                    or 0.0
                )
                edge_data["travel_time"] = base * multiplier
                edge_data["anomaly_multiplier"] = multiplier
                changed = True

        if changed:
            self.mark_graph_changed(mode_constraints_changed=False)

    def reset_edge_weight(self, source: str, target: str):
        if not self._graph:
            return

        changed = False
        if self._graph.has_edge(source, target):
            for key in self._graph[source][target]:
                edge_data = self._graph[source][target][key]
                edge_data["travel_time"] = float(
                    edge_data.get("base_travel_time")
                    or edge_data.get("travel_time")
                    or 0.0
                )
                edge_data["anomaly_multiplier"] = 1.0
                changed = True

        if changed:
            self.mark_graph_changed(mode_constraints_changed=False)

    def set_ml_predicted_weight(self, source: str, target: str, predicted_time: float):
        if not self._graph:
            return

        changed = False
        if self._graph.has_edge(source, target):
            for key in self._graph[source][target]:
                edge_data = self._graph[source][target][key]
                edge_data["travel_time"] = float(predicted_time)
                edge_data["ml_predicted"] = True
                changed = True

        if changed:
            self.mark_graph_changed(mode_constraints_changed=False)

    def get_snapshot(
        self,
        include_edges: bool = False,
        bbox: Optional[tuple] = None,
        mode_filter: Optional[str] = None,
        max_nodes: int = 800,
        max_edges: int = 1200,
    ) -> GraphSnapshot:
        """
        Get a snapshot of the graph, optionally filtered by transport mode.

        Args:
            include_edges: If True, include full edge list
            bbox: Optional bounding box tuple (south, west, north, east)
            mode_filter: Optional mode to filter nodes by accessibility

        Returns:
            GraphSnapshot with filtered nodes and edges
        """
        if not self._graph:
            return GraphSnapshot(
                node_count=0,
                edge_count=0,
                nodes=[],
                edges=[],
                anomaly_affected_edges=[],
            )

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        anomaly_affected_edges: list[str] = []
        anomaly_ids_by_edge: dict[str, list[str]] = {}

        if include_edges:
            try:
                from services.anomaly_service import anomaly_service

                for anomaly in anomaly_service._active.values():
                    for edge_id in anomaly.edge_ids:
                        anomaly_ids_by_edge.setdefault(edge_id, []).append(
                            anomaly.anomaly_id
                        )
            except Exception:
                anomaly_ids_by_edge = {}

        south, west, north, east = bbox or (None, None, None, None)
        max_nodes = max(1, int(max_nodes))
        max_edges = max(1, int(max_edges))

        def in_bbox(lat: float, lng: float) -> bool:
            if bbox is None:
                return True
            return south <= lat <= north and west <= lng <= east

        for node_id, data in self._graph.nodes(data=True):
            lat = float(data.get("y") or 0.0)
            lng = float(data.get("x") or 0.0)
            if in_bbox(lat, lng):
                # Compute accessible modes for this node
                accessible_modes = self.get_node_accessibility(node_id)

                # Filter by mode if specified
                if mode_filter is not None and mode_filter not in accessible_modes:
                    continue

                nodes.append(
                    GraphNode(
                        id=str(node_id),
                        lat=lat,
                        lng=lng,
                        accessible_modes=accessible_modes,
                    )
                )
                if len(nodes) >= max_nodes:
                    break

        if include_edges:
            for u, v, _, data in self._graph.edges(keys=True, data=True):
                u_data = self._graph.nodes.get(u, {})
                v_data = self._graph.nodes.get(v, {})
                u_lat, u_lng = float(u_data.get("y") or 0.0), float(
                    u_data.get("x") or 0.0
                )
                v_lat, v_lng = float(v_data.get("y") or 0.0), float(
                    v_data.get("x") or 0.0
                )

                if not (in_bbox(u_lat, u_lng) or in_bbox(v_lat, v_lng)):
                    continue

                edge_id = f"{u}->{v}"
                multiplier = float(data.get("anomaly_multiplier") or 1.0)
                if not math.isclose(multiplier, 1.0):
                    anomaly_affected_edges.append(edge_id)

                geometry_points: list[list[float]] = []
                edge_geom = data.get("geometry")
                if edge_geom is not None and hasattr(edge_geom, "coords"):
                    for x, y in list(edge_geom.coords):
                        geometry_points.append([float(y), float(x)])

                if len(geometry_points) < 2:
                    geometry_points = [[u_lat, u_lng], [v_lat, v_lng]]

                edges.append(
                    GraphEdge(
                        source=str(u),
                        target=str(v),
                        length_m=float(data.get("length") or 0.0),
                        travel_time_s=float(data.get("travel_time") or 0.0),
                        base_travel_time_s=float(data.get("base_travel_time") or 0.0),
                        road_type=str(data.get("road_type") or "unknown"),
                        speed_limit_kmh=(
                            float(data.get("speed_limit_kmh"))
                            if data.get("speed_limit_kmh") is not None
                            else None
                        ),
                        anomaly_multiplier=multiplier,
                        ml_predicted=bool(data.get("ml_predicted") or False),
                        geometry=geometry_points,
                        weights={
                            mode: float(data.get(f"{mode}_travel_time") or 0.0)
                            for mode in settings.vehicle_types.keys()
                        },
                        allowed_modes={
                            mode: bool(data.get(f"{mode}_allowed", False))
                            for mode in settings.vehicle_types.keys()
                        },
                        active_anomalies=anomaly_ids_by_edge.get(edge_id, []),
                    )
                )
                if len(edges) >= max_edges:
                    break

        bbox_list = list(bbox) if bbox is not None else None
        return GraphSnapshot(
            node_count=self.node_count(),
            edge_count=self.edge_count(),
            nodes=nodes,
            edges=edges,
            anomaly_affected_edges=anomaly_affected_edges,
            bbox=bbox_list,
        )


graph_service = GraphService()
