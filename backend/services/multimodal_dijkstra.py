"""
Multi-Modal Dijkstra Engine — (node, mode) State-Space Routing
================================================================
Implements the spec's core algorithm: a Dijkstra variant where the
state space is (current_node, current_mode) instead of just (node).

This allows:
  - Traversing different transport modes on the same graph
  - Applying mode-switch penalties during traversal (not just between legs)
  - Respecting per-mode edge constraints (car_allowed, rickshaw_allowed, etc.)
  - O(V log V) optimized via heapq

Design Rules:
  ✔ Never route through restricted edges
  ✔ Always apply mode switch penalty
  ✔ Use OSM as base truth layer
  ✔ Modify only weights dynamically (not structure)
  ✔ Ensure O(V log V) optimized Dijkstra
  ✔ Return actual road geometry (not straight lines)
  ✔ Guard against negative / zero weights

FIXES APPLIED (audit):
  - Replaced O(n) path-copy-per-push with predecessor map (O(1) per push)
  - Added negative weight guard (clamps to 0.01)
  - Added road geometry extraction from OSM edge 'geometry' attribute
  - geometry now follows real road curves, not straight node-to-node lines
"""

import heapq
import math
import os
import time
from typing import Optional


# Default mode switch penalty (seconds) if not specified
DEFAULT_SWITCH_PENALTY = 5

# Minimum edge cost to prevent zero/negative weight issues
MIN_EDGE_COST = 0.01

_PROFILE_ENV = "ROUTING_PROFILE"
_PROFILE_FALSE_VALUES = {"0", "false", "off", "no"}


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
    print(f"[Profile][MultiModalDijkstra] {stage} {payload}".rstrip())


_TRANSIT_HIGHWAY_VALUES = {"bus_stop"}
_TRANSIT_PUBLIC_TRANSPORT_VALUES = {
    "platform",
    "stop_position",
    "station",
    "stop_area",
    "bus_station",
}
_TRANSIT_RAILWAY_VALUES = {"station", "halt", "tram_stop", "subway_entrance"}
_TRANSIT_AMENITY_VALUES = {"bus_station", "ferry_terminal", "taxi"}
_SWITCH_NODE_CACHE: dict[tuple[int, int, int], set] = {}


def _to_text(value: object) -> str:
    return str(value or "").strip().lower()


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _edge_allows_mode(edge_data: dict, constraints: dict, mode: str) -> bool:
    keys = [f"{mode}_allowed"]
    if mode == "walk":
        keys.extend(["walking_allowed", "pedestrian_allowed"])

    for key in keys:
        if key in constraints:
            return bool(constraints.get(key))
        if key in edge_data:
            return bool(edge_data.get(key))

    # Constraint metadata absent -> treat as disallowed for safety.
    return False


def _edge_cost_for_mode(edge_data: dict, mode: str) -> float:
    weights = edge_data.get("weights", {})
    edge_cost = weights.get(mode)
    if edge_cost is None:
        edge_cost = float(
            edge_data.get(f"{mode}_travel_time")
            or edge_data.get("travel_time")
            or edge_data.get("length", 1)
        )
    return max(float(edge_cost), MIN_EDGE_COST)


def _build_valid_switch_nodes(graph) -> set:
    """Precompute nodes where mode switches are permitted."""
    cache_key = (id(graph), graph.number_of_nodes(), graph.number_of_edges())
    cached = _SWITCH_NODE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    valid = set()
    for node_id, node_data in graph.nodes(data=True):
        if bool(node_data.get("is_switch_node", False)):
            valid.add(node_id)
            continue
        if bool(node_data.get("is_transit_stop", False)):
            valid.add(node_id)
            continue

        highway = _to_text(node_data.get("highway"))
        public_transport = _to_text(node_data.get("public_transport"))
        railway = _to_text(node_data.get("railway"))
        amenity = _to_text(node_data.get("amenity"))

        is_transit_node = (
            highway in _TRANSIT_HIGHWAY_VALUES
            or public_transport in _TRANSIT_PUBLIC_TRANSPORT_VALUES
            or railway in _TRANSIT_RAILWAY_VALUES
            or amenity in _TRANSIT_AMENITY_VALUES
        )
        street_count_raw = node_data.get("street_count")
        if street_count_raw is not None:
            is_junction = _safe_int(street_count_raw, default=0) >= 3
        else:
            is_junction = _safe_int(graph.degree(node_id), default=0) >= 3

        if is_transit_node or is_junction:
            valid.add(node_id)

    _SWITCH_NODE_CACHE[cache_key] = valid
    if len(_SWITCH_NODE_CACHE) > 8:
        _SWITCH_NODE_CACHE.pop(next(iter(_SWITCH_NODE_CACHE)))

    return valid


def multi_modal_dijkstra(
    graph,
    start,
    end,
    allowed_modes: list[str],
    switch_penalty: float = DEFAULT_SWITCH_PENALTY,
) -> Optional[dict]:
    """
    Compute the optimal multi-modal route using (node, mode) state space.

    Uses a predecessor map instead of copying paths per heap entry,
    giving true O((V+E) log V) performance on large OSM graphs.

    Args:
        graph: NetworkX MultiDiGraph with edges containing 'weights' and 'constraints' dicts
        start: Source node ID
        end:   Destination node ID
        allowed_modes: List of transport modes to consider (e.g. ["car", "rickshaw", "walk"])
        switch_penalty: Cost penalty for switching between modes (seconds)

    Returns:
        dict with:
          - cost: total traversal cost
          - path: list of step dicts {from, to, mode}
          - node_path: ordered list of node IDs
          - stats: algorithm counters/timing for profiling
        Returns None if no path exists.
    """
    started_at = time.perf_counter()
    states_popped = 0
    states_settled = 0
    neighbor_pairs_scanned = 0
    parallel_edges_seen = 0
    mode_checks = 0
    edges_processed = 0
    constraint_rejections = 0
    switch_checks = 0
    switches_applied = 0
    switch_rejections = 0
    expansion_time_s = 0.0
    switch_handling_time_s = 0.0
    unique_nodes_visited = set()

    def _stats(status: str) -> dict:
        total_ms = (time.perf_counter() - started_at) * 1000.0
        return {
            "status": status,
            "algorithm_time_ms": total_ms,
            "states_popped": states_popped,
            "states_settled": states_settled,
            "nodes_visited": len(unique_nodes_visited),
            "neighbor_pairs_scanned": neighbor_pairs_scanned,
            "parallel_edges_seen": parallel_edges_seen,
            "mode_checks": mode_checks,
            "edges_processed": edges_processed,
            "constraint_rejections": constraint_rejections,
            "switch_checks": switch_checks,
            "switches_applied": switches_applied,
            "switch_rejections": switch_rejections,
            "expansion_time_ms": expansion_time_s * 1000.0,
            "switch_handling_time_ms": switch_handling_time_s * 1000.0,
        }

    if start == end:
        stats = _stats("start_equals_end")
        _profile_log(
            "complete",
            status=stats["status"],
            algorithm_time_ms=stats["algorithm_time_ms"],
            nodes_visited=stats["nodes_visited"],
            edges_processed=stats["edges_processed"],
        )
        return {"cost": 0, "path": [], "node_path": [start], "stats": stats}

    if not graph.has_node(start) or not graph.has_node(end):
        stats = _stats("invalid_endpoints")
        _profile_log(
            "complete",
            status=stats["status"],
            algorithm_time_ms=stats["algorithm_time_ms"],
            nodes_visited=stats["nodes_visited"],
            edges_processed=stats["edges_processed"],
        )
        return None

    valid_switch_nodes = _build_valid_switch_nodes(graph)

    # Priority queue: (cost, counter, node, mode)
    # counter breaks ties for heapq stability
    pq = []
    counter = 0

    # Predecessor map: (node, mode) -> (prev_node, prev_mode, edge_mode_used)
    predecessors = {}

    # Best cost seen: (node, mode) -> cost
    best_cost = {}

    # Seed: start with no mode (None) — first edge pick is free
    heapq.heappush(pq, (0.0, counter, start, None))
    counter += 1
    best_cost[(start, None)] = 0.0

    edge_allows_mode = _edge_allows_mode
    edge_cost_for_mode = _edge_cost_for_mode
    push_heap = heapq.heappush

    while pq:
        cost, _, node, mode = heapq.heappop(pq)
        states_popped += 1
        unique_nodes_visited.add(node)

        # Reached destination — reconstruct path from predecessors
        if node == end:
            result = _reconstruct_path(predecessors, start, end, mode, cost)
            stats = _stats("ok")
            result["stats"] = stats
            _profile_log(
                "complete",
                status=stats["status"],
                algorithm_time_ms=stats["algorithm_time_ms"],
                nodes_visited=stats["nodes_visited"],
                states_popped=stats["states_popped"],
                edges_processed=stats["edges_processed"],
                constraint_rejections=stats["constraint_rejections"],
                switches_applied=stats["switches_applied"],
            )
            return result

        state = (node, mode)

        # Skip if we've already settled this state with a cheaper cost
        if cost > best_cost.get(state, float("inf")):
            continue

        states_settled += 1
        expansion_started = time.perf_counter()

        # Explore all neighbors via outgoing edges
        for neighbor, edge_data_dict in graph[node].items():
            neighbor_pairs_scanned += 1
            if not edge_data_dict:
                continue

            edge_count = len(edge_data_dict)
            parallel_edges_seen += edge_count

            can_switch_here = (mode is None) or (node in valid_switch_nodes)
            candidate_modes = allowed_modes if can_switch_here else [mode]

            if edge_count == 1:
                edge_data = next(iter(edge_data_dict.values()))
                constraints = edge_data.get("constraints", {})

                for next_mode in candidate_modes:
                    mode_checks += 1

                    if not edge_allows_mode(edge_data, constraints, next_mode):
                        constraint_rejections += 1
                        continue

                    edges_processed += 1
                    best_mode_edge_cost = edge_cost_for_mode(edge_data, next_mode)

                    # ✔ Mode switch penalty
                    extra_penalty = 0.0
                    if mode is not None:
                        switch_checks += 1
                        if mode != next_mode:
                            if node not in valid_switch_nodes:
                                switch_rejections += 1
                                continue

                            switch_started = time.perf_counter()
                            extra_penalty = switch_penalty
                            switches_applied += 1
                            switch_handling_time_s += (
                                time.perf_counter() - switch_started
                            )

                    new_cost = cost + best_mode_edge_cost + extra_penalty

                    neighbor_state = (neighbor, next_mode)
                    if new_cost < best_cost.get(neighbor_state, float("inf")):
                        best_cost[neighbor_state] = new_cost
                        predecessors[neighbor_state] = (node, mode, next_mode)
                        push_heap(pq, (new_cost, counter, neighbor, next_mode))
                        counter += 1

                continue

            for next_mode in candidate_modes:
                mode_checks += 1
                best_mode_edge_cost = None
                for edge_data in edge_data_dict.values():
                    constraints = edge_data.get("constraints", {})
                    if not edge_allows_mode(edge_data, constraints, next_mode):
                        constraint_rejections += 1
                        continue

                    edge_cost = edge_cost_for_mode(edge_data, next_mode)
                    if best_mode_edge_cost is None or edge_cost < best_mode_edge_cost:
                        best_mode_edge_cost = edge_cost

                if best_mode_edge_cost is None:
                    continue

                edges_processed += 1

                # ✔ Mode switch penalty
                extra_penalty = 0.0
                if mode is not None:
                    switch_checks += 1
                    if mode != next_mode:
                        if node not in valid_switch_nodes:
                            switch_rejections += 1
                            continue

                        switch_started = time.perf_counter()
                        extra_penalty = switch_penalty
                        switches_applied += 1
                        switch_handling_time_s += time.perf_counter() - switch_started

                new_cost = cost + best_mode_edge_cost + extra_penalty

                neighbor_state = (neighbor, next_mode)
                if new_cost < best_cost.get(neighbor_state, float("inf")):
                    best_cost[neighbor_state] = new_cost
                    predecessors[neighbor_state] = (node, mode, next_mode)
                    push_heap(pq, (new_cost, counter, neighbor, next_mode))
                    counter += 1

        expansion_time_s += time.perf_counter() - expansion_started

    # No path found
    stats = _stats("no_path")
    _profile_log(
        "complete",
        status=stats["status"],
        algorithm_time_ms=stats["algorithm_time_ms"],
        nodes_visited=stats["nodes_visited"],
        states_popped=stats["states_popped"],
        edges_processed=stats["edges_processed"],
        constraint_rejections=stats["constraint_rejections"],
        switches_applied=stats["switches_applied"],
    )
    return None


def _reconstruct_path(
    predecessors: dict,
    start,
    end,
    end_mode,
    total_cost: float,
) -> dict:
    """Reconstruct the path from predecessor map — O(path_length)."""
    path = []
    node_path = []
    current_state = (end, end_mode)

    while current_state in predecessors:
        prev_node, prev_mode, edge_mode = predecessors[current_state]
        current_node = current_state[0]
        path.append(
            {
                "from": prev_node,
                "to": current_node,
                "mode": edge_mode,
            }
        )
        node_path.append(current_node)
        current_state = (prev_node, prev_mode)

    # Add start node
    node_path.append(start)
    path.reverse()
    node_path.reverse()

    return {
        "cost": total_cost,
        "path": path,
        "node_path": node_path,
    }


def _extract_edge_road_geometry(graph, from_node, to_node) -> list[list[float]]:
    """
    Extract the ACTUAL road geometry from an OSM edge.

    OSMnx stores Shapely LineString geometry objects on edges that represent
    the real road shape (curves, bends). If no geometry attribute exists,
    fall back to straight node-to-node line.

    This is THE fix for the straight-line bug.
    """
    edge_data_dict = graph.get_edge_data(from_node, to_node)
    if not edge_data_dict:
        # Fallback: straight line
        fd = graph.nodes.get(from_node, {})
        td = graph.nodes.get(to_node, {})
        return [
            [float(fd.get("y", 0.0)), float(fd.get("x", 0.0))],
            [float(td.get("y", 0.0)), float(td.get("x", 0.0))],
        ]

    edge_data = next(iter(edge_data_dict.values()))
    geom = edge_data.get("geometry")

    # If the edge has an OSM geometry (Shapely LineString), use its coordinates
    if geom is not None and hasattr(geom, "coords"):
        points = []
        for x, y in list(geom.coords):
            points.append([float(y), float(x)])  # lat, lng
        if len(points) >= 2:
            return points

    # Fallback: straight node-to-node
    fd = graph.nodes.get(from_node, {})
    td = graph.nodes.get(to_node, {})
    return [
        [float(fd.get("y", 0.0)), float(fd.get("x", 0.0))],
        [float(td.get("y", 0.0)), float(td.get("x", 0.0))],
    ]


def multi_modal_dijkstra_with_coords(
    graph,
    start,
    end,
    allowed_modes: list[str],
    switch_penalty: float = DEFAULT_SWITCH_PENALTY,
) -> Optional[dict]:
    """
    Same as multi_modal_dijkstra but enriches the path with:
      - lat/lng coordinates on each step
      - Full road geometry following actual OSM road shapes (not straight lines)
      - node_path: ordered list of node IDs

    Returns:
        dict with:
          - cost: total traversal cost
          - path: list of step dicts with coordinates
          - node_path: ordered list of node IDs
          - geometry: list of [lat, lng] points following real roads
    """
    result = multi_modal_dijkstra(graph, start, end, allowed_modes, switch_penalty)
    if result is None:
        return None

    geometry = []
    enriched_path = []

    for step in result["path"]:
        from_node = step["from"]
        to_node = step["to"]

        from_data = graph.nodes.get(from_node, {})
        to_data = graph.nodes.get(to_node, {})

        from_lat = float(from_data.get("y", 0.0))
        from_lng = float(from_data.get("x", 0.0))
        to_lat = float(to_data.get("y", 0.0))
        to_lng = float(to_data.get("x", 0.0))

        enriched_step = {
            **step,
            "from_lat": from_lat,
            "from_lng": from_lng,
            "to_lat": to_lat,
            "to_lng": to_lng,
        }
        enriched_path.append(enriched_step)

        # ✔ Use REAL road geometry, not straight lines
        edge_points = _extract_edge_road_geometry(graph, from_node, to_node)

        if geometry and edge_points:
            # Avoid duplicating the junction point
            last = geometry[-1]
            first_new = edge_points[0]
            if (
                abs(last[0] - first_new[0]) < 1e-8
                and abs(last[1] - first_new[1]) < 1e-8
            ):
                geometry.extend(edge_points[1:])
            else:
                geometry.extend(edge_points)
        else:
            geometry.extend(edge_points)

    return {
        "cost": result["cost"],
        "path": enriched_path,
        "node_path": result.get("node_path", []),
        "geometry": geometry,
        "stats": result.get("stats", {}),
    }
