"""
Routing Engine — Single-Modal & Multi-Modal Path Computation
==============================================================
Computes shortest paths over the in-memory OSM road graph.
"""

from __future__ import annotations

import math
import os
import time
from heapq import heappop, heappush
from collections import OrderedDict
from typing import Callable

import networkx as nx

from config import settings
from models.route_models import (
    RouteRequest,
    RouteResponse,
    RouteLeg,
    RouteTrafficEdge,
    ModeSwitch,
    LatLng,
    MultimodalSuggestion,
    SegmentSuggestion,
    VehicleOption,
)
from services.graph_service import graph_service
from services.ml_integration import ml_integration
from services.multimodal_dijkstra import multi_modal_dijkstra_with_coords
from services.anomaly_service import anomaly_service
from services.traffic_jam_service import traffic_jam_service


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
    print(f"[Profile][RoutingEngine] {stage} {payload}".rstrip())


class RoutingEngine:
    """Singleton routing engine service."""

    def __init__(self):
        self._algorithm = settings.routing_algorithm
        self._weight_attr = settings.weight_attribute
        self._max_alts = settings.max_alternatives
        self._max_transfers = settings.multimodal_max_transfers
        self._transfer_radius = settings.transfer_radius_meters
        self._shortest_tree_cache: OrderedDict[tuple, tuple[dict, float]] = (
            OrderedDict()
        )
        self._shortest_tree_cache_max = max(
            4,
            int(os.getenv("ROUTING_TREE_CACHE_MAX", "24")),
        )
        self._shortest_tree_cache_ttl_s = max(
            5.0,
            float(os.getenv("ROUTING_TREE_CACHE_TTL_S", "20")),
        )
        self._route_response_cache: OrderedDict[tuple, tuple[RouteResponse, float]] = (
            OrderedDict()
        )
        self._route_response_cache_max = max(
            8,
            int(os.getenv("ROUTING_RESPONSE_CACHE_MAX", "64")),
        )
        self._route_response_ttl_s = max(
            5.0,
            float(os.getenv("ROUTING_RESPONSE_CACHE_TTL_S", "20")),
        )
        self._ml_refresh_interval_s = max(
            0.0,
            float(os.getenv("ROUTING_ML_REFRESH_INTERVAL_S", "30")),
        )
        self._last_ml_refresh_monotonic = 0.0

    def _normalize_mode(self, mode: str) -> str:
        if mode == "bus":
            return "transit"
        return mode

    def _display_mode(self, mode: str) -> str:
        return self._normalize_mode(mode)

    def _current_graph_version(self) -> int:
        getter = getattr(graph_service, "get_graph_version", None)
        if callable(getter):
            try:
                return int(getter())
            except Exception:
                return 0
        return 0

    def _clone_response(self, response: RouteResponse) -> RouteResponse:
        if hasattr(response, "model_copy"):
            return response.model_copy(deep=True)
        return response.copy(deep=True)

    def _route_cache_key(
        self,
        request: RouteRequest,
    ) -> tuple:
        origin_lat = round(float(request.origin.lat), 4)
        origin_lng = round(float(request.origin.lng), 4)
        dest_lat = round(float(request.destination.lat), 4)
        dest_lng = round(float(request.destination.lng), 4)
        return (
            tuple(request.modes),
            str(request.optimize),
            bool(request.avoid_anomalies),
            int(request.max_alternatives or self._max_alts),
            bool(getattr(request, "include_multimodal", False)),
            origin_lat,
            origin_lng,
            dest_lat,
            dest_lng,
            self._current_graph_version(),
        )

    def _route_cache_get(self, key: tuple) -> RouteResponse | None:
        entry = self._route_response_cache.get(key)
        if entry is None:
            return None
        response, ts = entry
        if (time.monotonic() - ts) > self._route_response_ttl_s:
            self._route_response_cache.pop(key, None)
            return None
        self._route_response_cache.move_to_end(key)
        return self._clone_response(response)

    def _route_cache_set(self, key: tuple, response: RouteResponse):
        self._route_response_cache[key] = (
            self._clone_response(response),
            time.monotonic(),
        )
        self._route_response_cache.move_to_end(key)
        while len(self._route_response_cache) > self._route_response_cache_max:
            self._route_response_cache.popitem(last=False)

    def _tree_cache_key(
        self,
        graph: nx.MultiDiGraph,
        origin_node,
        mode: str,
        optimize: str,
        undirected: bool,
    ) -> tuple:
        return (
            self._current_graph_version(),
            id(graph),
            bool(undirected),
            mode,
            optimize,
            origin_node,
        )

    def _edge_cost_for_mode(self, edge_data: dict, mode: str, optimize: str):
        mode_allowed = bool(edge_data.get(f"{mode}_allowed", False))
        if mode == "walk":
            mode_allowed = bool(
                edge_data.get(
                    "walk_allowed",
                    edge_data.get(
                        "walking_allowed", edge_data.get("pedestrian_allowed", False)
                    ),
                )
            )
        if not mode_allowed:
            return None

        length = float(edge_data.get("length") or 0.0)
        travel_time = float(
            edge_data.get(f"{mode}_travel_time") or edge_data.get("travel_time") or 0.0
        )
        cost_per_km = float(
            settings.vehicle_types[mode].get("fuel_cost_per_km", 0.0) or 0.0
        )
        monetary_cost = (length / 1000.0) * cost_per_km

        if optimize == "distance":
            return max(length, 0.01)
        if optimize == "cost":
            return max(monetary_cost, 0.0001)
        return max(travel_time, 0.01)

    def _resolve_step_edge_data(
        self,
        graph: nx.MultiDiGraph,
        u,
        v,
        key,
        *,
        undirected: bool,
    ) -> tuple[dict | None, bool]:
        direct = graph.get_edge_data(u, v, key=key, default=None)
        if direct is not None:
            return direct, False

        if not undirected:
            return None, False

        reverse = graph.get_edge_data(v, u, key=key, default=None)
        if reverse is not None:
            return reverse, True

        return None, False

    def _iter_neighbor_edges(
        self,
        graph: nx.MultiDiGraph,
        node_id,
        *,
        undirected: bool,
    ):
        indexed_neighbors = graph_service.get_outgoing_edges(
            node_id,
            undirected=undirected,
        )
        if indexed_neighbors:
            return indexed_neighbors

        neighbors: list[tuple[object, object]] = []

        adjacency = getattr(graph, "adj", {})
        for neighbor_id, edge_dict in adjacency.get(node_id, {}).items():
            for edge_key in edge_dict.keys():
                neighbors.append((neighbor_id, edge_key))

        if undirected:
            predecessors = getattr(graph, "pred", {})
            for neighbor_id, edge_dict in predecessors.get(node_id, {}).items():
                for edge_key in edge_dict.keys():
                    neighbors.append((neighbor_id, edge_key))

        if not neighbors:
            return ()

        return tuple(dict.fromkeys(neighbors))

    def _reconstruct_path(self, previous: dict, destination) -> list:
        path = [destination]
        current = destination
        while current in previous:
            current = previous[current]
            path.append(current)
        path.reverse()
        return path

    def _dijkstra_path_to_targets(
        self,
        graph: nx.MultiDiGraph,
        origin_node,
        destination_candidates: list,
        mode: str,
        optimize: str,
        *,
        undirected: bool,
    ) -> tuple[object | None, list | None, float]:
        if origin_node is None:
            return None, None, float("inf")

        targets = set(destination_candidates)
        if not targets:
            return None, None, float("inf")

        if origin_node in targets:
            return origin_node, [origin_node], 0.0

        dist: dict = {origin_node: 0.0}
        previous: dict = {}
        queue: list[tuple[float, object]] = [(0.0, origin_node)]

        while queue:
            cost_so_far, node_id = heappop(queue)
            known = dist.get(node_id)
            if known is None or cost_so_far > known:
                continue

            if node_id in targets:
                return node_id, self._reconstruct_path(previous, node_id), cost_so_far

            for neighbor_id, edge_key in self._iter_neighbor_edges(
                graph,
                node_id,
                undirected=undirected,
            ):
                edge_data, _reversed = self._resolve_step_edge_data(
                    graph,
                    node_id,
                    neighbor_id,
                    edge_key,
                    undirected=undirected,
                )
                if edge_data is None:
                    continue

                step_weight = self._edge_cost_for_mode(edge_data, mode, optimize)
                if step_weight is None:
                    continue

                next_cost = cost_so_far + float(step_weight)
                best_known = dist.get(neighbor_id)
                if best_known is not None and next_cost >= best_known:
                    continue

                dist[neighbor_id] = next_cost
                previous[neighbor_id] = node_id
                heappush(queue, (next_cost, neighbor_id))

        return None, None, float("inf")

    def _find_best_path_lightweight(
        self,
        graph: nx.MultiDiGraph,
        origin_candidates: list,
        destination_candidates: list,
        mode: str,
        optimize: str,
        *,
        max_origins: int,
        undirected: bool,
    ) -> tuple[tuple[object, object] | None, list | None, float, int]:
        best_pair = None
        best_path = None
        best_cost = float("inf")
        dijkstra_runs = 0

        for origin_node in origin_candidates[: max(1, int(max_origins))]:
            dijkstra_runs += 1
            dest_node, candidate_path, candidate_cost = self._dijkstra_path_to_targets(
                graph,
                origin_node,
                destination_candidates,
                mode,
                optimize,
                undirected=undirected,
            )
            if not candidate_path:
                continue
            if candidate_cost < best_cost:
                best_cost = candidate_cost
                best_pair = (origin_node, dest_node)
                best_path = candidate_path
                # Latency-first behavior: accept the first valid origin path.
                break

        return best_pair, best_path, best_cost, dijkstra_runs

    async def compute(self, request: RouteRequest) -> RouteResponse:
        request_started = time.perf_counter()
        request_id = hex(time.perf_counter_ns() & 0xFFFFFFFF)[2:]
        _profile_log(
            "request_start",
            request_id=request_id,
            optimize=request.optimize,
            modes="|".join(request.modes),
            include_multimodal=bool(getattr(request, "include_multimodal", False)),
        )

        runtime_ready_started = time.perf_counter()
        full_graph = graph_service.ensure_loaded(raise_on_error=False)
        if full_graph is not None and full_graph.number_of_nodes() > 0:
            traffic_jam_service.ensure_initialized(full_graph)
        runtime_ready_ms = (time.perf_counter() - runtime_ready_started) * 1000.0

        anomaly_started = time.perf_counter()
        anomaly_service.sync_active_effects()
        anomaly_sync_ms = (time.perf_counter() - anomaly_started) * 1000.0

        request.modes = [self._normalize_mode(m) for m in request.modes]
        ml_refresh_ms = 0.0

        cache_lookup_started = time.perf_counter()
        cache_key = self._route_cache_key(request)
        cached_response = self._route_cache_get(cache_key)
        cache_lookup_ms = (time.perf_counter() - cache_lookup_started) * 1000.0
        if cached_response is not None:
            total_ms = (time.perf_counter() - request_started) * 1000.0
            _profile_log(
                "request_cache_hit",
                request_id=request_id,
                total_ms=total_ms,
                ml_refresh_ms=ml_refresh_ms,
                anomaly_sync_ms=anomaly_sync_ms,
                graph_hint_ms=0.0,
                runtime_ready_ms=runtime_ready_ms,
                cache_lookup_ms=cache_lookup_ms,
            )
            return cached_response

        ml_refresh_started = time.perf_counter()
        await self._refresh_ml_weights()
        ml_refresh_ms = (time.perf_counter() - ml_refresh_started) * 1000.0

        graph_hint_started = time.perf_counter()
        full_graph = graph_service.get_graph()
        origin_candidates_hint: list = []
        destination_candidates_hint: list = []

        if full_graph is not None and full_graph.number_of_nodes() > 0:
            origin_candidates_hint = graph_service.get_k_nearest_nodes_in_graph(
                full_graph,
                request.origin.lat,
                request.origin.lng,
                k=8,
            )
            destination_candidates_hint = graph_service.get_k_nearest_nodes_in_graph(
                full_graph,
                request.destination.lat,
                request.destination.lng,
                k=8,
            )

        graph_hint_ms = (time.perf_counter() - graph_hint_started) * 1000.0

        routing_started = time.perf_counter()
        if len(request.modes) == 1:
            legs, switches, anomalies_avoided = await self._single_modal(
                origin=request.origin,
                destination=request.destination,
                mode=request.modes[0],
                optimize=request.optimize,
                avoid_anomalies=request.avoid_anomalies,
                origin_candidates_hint=origin_candidates_hint,
                destination_candidates_hint=destination_candidates_hint,
            )
        else:
            legs, switches, anomalies_avoided = await self._multi_modal(
                origin=request.origin,
                destination=request.destination,
                modes=request.modes,
                optimize=request.optimize,
                avoid_anomalies=request.avoid_anomalies,
                origin_candidates_hint=origin_candidates_hint,
                destination_candidates_hint=destination_candidates_hint,
            )
        routing_ms = (time.perf_counter() - routing_started) * 1000.0

        aggregate_started = time.perf_counter()
        total_dist = sum(leg.distance_m for leg in legs)
        total_dur = sum(leg.duration_s for leg in legs) + sum(
            sw.penalty_time_s for sw in switches
        )
        total_cost = sum(leg.cost for leg in legs) + sum(
            sw.penalty_cost for sw in switches
        )
        aggregate_ms = (time.perf_counter() - aggregate_started) * 1000.0

        alternatives_started = time.perf_counter()
        num_alts = request.max_alternatives or self._max_alts
        alternatives = await self._compute_alternatives(request, num_alts)
        alternatives_ms = (time.perf_counter() - alternatives_started) * 1000.0

        suggestions_started = time.perf_counter()
        multimodal_suggestions: list[MultimodalSuggestion] = []
        if bool(getattr(request, "include_multimodal", False)):
            # Avoid duplicate state-space runs for multimodal requests by reusing the
            # already computed route legs.
            if len(request.modes) > 1:
                fastest_from_legs = self._build_multimodal_suggestion_from_legs(
                    legs,
                    strategy="fastest_time",
                )
                if fastest_from_legs is not None:
                    multimodal_suggestions.append(fastest_from_legs)

                distance_from_legs = self._build_multimodal_suggestions_from_route_legs(
                    legs
                )
                for suggestion in distance_from_legs:
                    if all(
                        existing.strategy != suggestion.strategy
                        for existing in multimodal_suggestions
                    ):
                        multimodal_suggestions.append(suggestion)
            else:
                multimodal_suggestions = self._compute_multimodal_suggestions(
                    request.origin,
                    request.destination,
                    fallback_legs=legs,
                )
        multimodal_suggestions_ms = (time.perf_counter() - suggestions_started) * 1000.0

        traffic_edge_collect_started = time.perf_counter()
        all_traffic_edges: list[dict] = []
        for leg in legs:
            all_traffic_edges.extend(
                [
                    {
                        "edge_id": e.edge_id,
                        "road_type": e.road_type,
                        "length_m": e.length_m,
                    }
                    for e in leg.traffic_edges
                ]
            )
        traffic_edge_collect_ms = (
            time.perf_counter() - traffic_edge_collect_started
        ) * 1000.0

        traffic_dispatch_started = time.perf_counter()
        traffic_job = traffic_jam_service.start_route_prediction(
            edge_contexts=all_traffic_edges,
            hour_of_day=request.traffic_hour_of_day,
        )
        traffic_dispatch_ms = (time.perf_counter() - traffic_dispatch_started) * 1000.0

        response_build_started = time.perf_counter()
        response = RouteResponse(
            legs=[
                RouteLeg(
                    mode=self._display_mode(leg.mode),
                    geometry=leg.geometry,
                    distance_m=leg.distance_m,
                    duration_s=leg.duration_s,
                    cost=leg.cost,
                    instructions=leg.instructions,
                )
                for leg in legs
            ],
            mode_switches=[
                ModeSwitch(
                    from_mode=self._display_mode(sw.from_mode),
                    to_mode=self._display_mode(sw.to_mode),
                    location=sw.location,
                    penalty_time_s=sw.penalty_time_s,
                    penalty_cost=sw.penalty_cost,
                )
                for sw in switches
            ],
            total_distance_m=total_dist,
            total_duration_s=total_dur,
            total_cost=total_cost,
            anomalies_avoided=anomalies_avoided,
            alternatives=alternatives,
            multimodal_suggestions=multimodal_suggestions,
            traffic_jam_prediction=traffic_job.get("data"),
            route_id=traffic_job.get("route_id"),
            traffic_status=str(traffic_job.get("status") or "loading"),
        )
        response_build_ms = (time.perf_counter() - response_build_started) * 1000.0

        cache_set_started = time.perf_counter()
        self._route_cache_set(cache_key, response)
        cache_set_ms = (time.perf_counter() - cache_set_started) * 1000.0

        total_ms = (time.perf_counter() - request_started) * 1000.0
        _profile_log(
            "request_complete",
            request_id=request_id,
            total_ms=total_ms,
            ml_refresh_ms=ml_refresh_ms,
            anomaly_sync_ms=anomaly_sync_ms,
            graph_hint_ms=graph_hint_ms,
            runtime_ready_ms=runtime_ready_ms,
            cache_lookup_ms=cache_lookup_ms,
            routing_ms=routing_ms,
            aggregate_ms=aggregate_ms,
            alternatives_ms=alternatives_ms,
            multimodal_suggestions_ms=multimodal_suggestions_ms,
            traffic_edge_collect_ms=traffic_edge_collect_ms,
            traffic_dispatch_ms=traffic_dispatch_ms,
            response_build_ms=response_build_ms,
            cache_set_ms=cache_set_ms,
            legs=len(legs),
            switches=len(switches),
            traffic_edges=len(all_traffic_edges),
            anomalies_avoided=anomalies_avoided,
        )
        return response

    async def _single_modal(
        self,
        origin: LatLng,
        destination: LatLng,
        mode: str,
        optimize: str,
        avoid_anomalies: bool,
        origin_candidates_hint: list | None = None,
        destination_candidates_hint: list | None = None,
    ) -> tuple[list[RouteLeg], list[ModeSwitch], int]:
        del avoid_anomalies  # Placeholder until anomaly filtering is added.

        single_started = time.perf_counter()
        edge_filter_ms = 0.0
        candidate_resolution_ms = 0.0
        routing_search_ms = 0.0
        geometry_build_ms = 0.0
        dijkstra_runs = 0
        used_undirected = False
        used_full_graph_fallback = False

        def _log_single(status: str, **extra):
            payload = {
                "mode": mode,
                "optimize": optimize,
                "status": status,
                "total_ms": (time.perf_counter() - single_started) * 1000.0,
                "edge_filter_ms": edge_filter_ms,
                "candidate_resolution_ms": candidate_resolution_ms,
                "routing_search_ms": routing_search_ms,
                "geometry_build_ms": geometry_build_ms,
                "dijkstra_runs": dijkstra_runs,
                "used_undirected": used_undirected,
                "used_full_graph_fallback": used_full_graph_fallback,
            }
            payload.update(extra)
            _profile_log("single_modal_complete", **payload)

        if mode not in settings.vehicle_types:
            raise ValueError(
                f"Unknown transport mode: '{mode}'. Available: {list(settings.vehicle_types.keys())}"
            )

        if not graph_service.is_loaded():
            # Graph not loaded yet - return synthetic route
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single("graph_not_loaded")
            return [leg], [], 0

        edge_filter_started = time.perf_counter()
        full_graph = graph_service.get_graph()
        graph = full_graph
        if graph is None or graph.number_of_nodes() == 0:
            leg = self._build_synthetic_leg(mode, origin, destination)
            edge_filter_ms = (time.perf_counter() - edge_filter_started) * 1000.0
            _log_single("empty_graph")
            return [leg], [], 0
        edge_filter_ms = (time.perf_counter() - edge_filter_started) * 1000.0

        candidate_started = time.perf_counter()
        if origin_candidates_hint:
            origin_candidates = [n for n in origin_candidates_hint if n in graph]
        else:
            origin_candidates = []

        if destination_candidates_hint:
            dest_candidates = [n for n in destination_candidates_hint if n in graph]
        else:
            dest_candidates = []

        if not origin_candidates:
            origin_candidates = graph_service.get_k_nearest_nodes_in_graph(
                graph, origin.lat, origin.lng, k=8
            )
        if not dest_candidates:
            dest_candidates = graph_service.get_k_nearest_nodes_in_graph(
                graph, destination.lat, destination.lng, k=8
            )
        candidate_resolution_ms = (time.perf_counter() - candidate_started) * 1000.0

        if not origin_candidates or not dest_candidates:
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single(
                "missing_candidates",
                origin_candidates=len(origin_candidates),
                destination_candidates=len(dest_candidates),
            )
            return [leg], [], 0

        def _find_best_path(max_origins: int, undirected: bool):
            nonlocal dijkstra_runs
            best_pair, best_path, _best_cost, runs = self._find_best_path_lightweight(
                graph,
                origin_candidates,
                dest_candidates,
                mode,
                optimize,
                max_origins=max_origins,
                undirected=undirected,
            )
            dijkstra_runs += runs
            return best_pair, best_path

        routing_started = time.perf_counter()
        best_pair, best_path = _find_best_path(max_origins=2, undirected=False)

        # For walking/bike/rickshaw/bus-like traversal, one-way directionality can
        # make reachable roads appear disconnected. Retry on undirected topology
        # before falling back to synthetic geometry.
        if best_path is None:
            used_undirected = True
            best_pair, best_path = _find_best_path(max_origins=3, undirected=True)

        routing_search_ms = (time.perf_counter() - routing_started) * 1000.0

        if best_path is None:
            # If the points are essentially colocated, return a zero-length leg.
            if (
                self._haversine_distance_m(
                    origin.lat, origin.lng, destination.lat, destination.lng
                )
                < 12.0
            ):
                leg = RouteLeg(
                    mode=mode,
                    geometry=[origin],
                    distance_m=0.0,
                    duration_s=0.0,
                    cost=0.0,
                    instructions=[
                        "Origin and destination are at the same location.",
                    ],
                )
                _log_single("colocated")
                return [leg], [], 0
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single("no_graph_path")
            return [leg], [], 0

        origin_node, dest_node = best_pair
        path = best_path
        if path is None:
            # No path found in graph - return synthetic direct route
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single("null_path")
            return [leg], [], 0

        if len(path) < 2:
            # Degenerate graph path - return synthetic direct route
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single("degenerate_path", path_nodes=len(path))
            return [leg], [], 0

        geometry_started = time.perf_counter()
        geometry: list[LatLng] = []
        traffic_edges: list[RouteTrafficEdge] = []
        total_distance_m = 0.0
        total_duration_s = 0.0
        weight_fn = self._build_weight_fn(mode, optimize)
        allow_reverse_edge = used_undirected

        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            edge_data = self._best_edge_data_for_step(
                graph,
                u,
                v,
                mode,
                optimize,
                weight_fn,
                allow_reverse_edge=allow_reverse_edge,
            )
            if not edge_data:
                continue
            total_distance_m += float(edge_data.get("length") or 0.0)
            total_duration_s += float(
                edge_data.get(f"{mode}_travel_time")
                or edge_data.get("travel_time")
                or 0.0
            )
            chosen_key = edge_data.get("_key")
            if chosen_key is None:
                chosen_key = 0
            traffic_edges.append(
                RouteTrafficEdge(
                    edge_id=str(edge_data.get("_edge_id") or f"{u}->{v}:{chosen_key}"),
                    road_type=self._road_type(edge_data),
                    length_m=float(edge_data.get("length") or 0.0),
                )
            )

            if bool(edge_data.get("_reverse", False)):
                edge_points = list(
                    reversed(self._edge_geometry_points(graph, v, u, edge_data))
                )
            else:
                edge_points = self._edge_geometry_points(graph, u, v, edge_data)
            if geometry and edge_points:
                if (
                    geometry[-1].lat == edge_points[0].lat
                    and geometry[-1].lng == edge_points[0].lng
                ):
                    geometry.extend(edge_points[1:])
                else:
                    geometry.extend(edge_points)
            else:
                geometry.extend(edge_points)

        geometry_build_ms = (time.perf_counter() - geometry_started) * 1000.0

        if len(geometry) < 2:
            # Degenerate geometry from graph edges - return synthetic direct route
            leg = self._build_synthetic_leg(mode, origin, destination)
            _log_single("degenerate_geometry", path_edges=max(0, len(path) - 1))
            return [leg], [], 0

        cost_per_km = float(
            settings.vehicle_types[mode].get("fuel_cost_per_km", 0.0) or 0.0
        )
        total_cost = (total_distance_m / 1000.0) * cost_per_km

        leg = RouteLeg(
            mode=mode,
            geometry=geometry,
            distance_m=total_distance_m,
            duration_s=total_duration_s,
            cost=total_cost,
            traffic_edges=traffic_edges,
            instructions=[
                f"Start at ({origin.lat:.5f}, {origin.lng:.5f})",
                f"Follow the shortest {mode} route on roads",
                f"Arrive at ({destination.lat:.5f}, {destination.lng:.5f})",
            ],
        )
        _log_single(
            "graph_route",
            path_nodes=len(path),
            path_edges=max(0, len(path) - 1),
            geometry_points=len(geometry),
            origin_node=origin_node,
            destination_node=dest_node,
        )
        return [leg], [], 0

    async def _multi_modal(
        self,
        origin: LatLng,
        destination: LatLng,
        modes: list[str],
        optimize: str,
        avoid_anomalies: bool,
        origin_candidates_hint: list | None = None,
        destination_candidates_hint: list | None = None,
    ) -> tuple[list[RouteLeg], list[ModeSwitch], int]:
        multi_started = time.perf_counter()
        node_resolution_ms = 0.0
        state_space_ms = 0.0
        fallback_reason = "state_space_no_path"

        graph = graph_service.get_graph()
        if graph is not None and graph.number_of_nodes() > 0:
            origin_node = None
            dest_node = None

            node_resolution_started = time.perf_counter()
            if origin_candidates_hint:
                for node_id in origin_candidates_hint:
                    if node_id in graph:
                        origin_node = node_id
                        break
            if destination_candidates_hint:
                for node_id in destination_candidates_hint:
                    if node_id in graph:
                        dest_node = node_id
                        break

            if origin_node is None:
                origin_node = graph_service.get_nearest_node(origin.lat, origin.lng)
            if dest_node is None:
                dest_node = graph_service.get_nearest_node(
                    destination.lat, destination.lng
                )
            node_resolution_ms = (
                time.perf_counter() - node_resolution_started
            ) * 1000.0

            allowed_modes = list(dict.fromkeys(modes))
            switch_penalty = float(
                settings.mode_switch_penalties.get("default_penalty_seconds", 5.0)
            )

            if origin_node is not None and dest_node is not None and allowed_modes:
                state_space_started = time.perf_counter()
                try:
                    result = multi_modal_dijkstra_with_coords(
                        graph=graph,
                        start=origin_node,
                        end=dest_node,
                        allowed_modes=allowed_modes,
                        switch_penalty=switch_penalty,
                    )
                    state_space_ms = (
                        time.perf_counter() - state_space_started
                    ) * 1000.0
                    stats = result.get("stats", {}) if result else {}
                    if result and result.get("path"):
                        _profile_log(
                            "multi_modal_state_space",
                            status=stats.get("status", "ok"),
                            algorithm_time_ms=stats.get(
                                "algorithm_time_ms", state_space_ms
                            ),
                            nodes_visited=stats.get("nodes_visited", -1),
                            edges_processed=stats.get("edges_processed", -1),
                            mode_checks=stats.get("mode_checks", -1),
                            switches_applied=stats.get("switches_applied", -1),
                        )
                        built = self._build_multimodal_from_state_path(
                            graph=graph,
                            origin=origin,
                            destination=destination,
                            path_steps=result["path"],
                        )
                        _profile_log(
                            "multi_modal_complete",
                            strategy="state_space",
                            total_ms=(time.perf_counter() - multi_started) * 1000.0,
                            node_resolution_ms=node_resolution_ms,
                            state_space_ms=state_space_ms,
                            legs=len(built[0]),
                            switches=len(built[1]),
                        )
                        return built
                    fallback_reason = str(stats.get("status", "state_space_empty_path"))
                except Exception as exc:
                    state_space_ms = (
                        time.perf_counter() - state_space_started
                    ) * 1000.0
                    fallback_reason = f"state_space_error:{type(exc).__name__}"
            else:
                fallback_reason = "missing_nodes_or_modes"
        else:
            fallback_reason = "graph_unavailable"

        sequential_started = time.perf_counter()
        result = await self._multi_modal_sequential(
            origin=origin,
            destination=destination,
            modes=modes,
            optimize=optimize,
            avoid_anomalies=avoid_anomalies,
            origin_candidates_hint=origin_candidates_hint,
            destination_candidates_hint=destination_candidates_hint,
        )
        sequential_ms = (time.perf_counter() - sequential_started) * 1000.0
        _profile_log(
            "multi_modal_complete",
            strategy="sequential_fallback",
            reason=fallback_reason,
            total_ms=(time.perf_counter() - multi_started) * 1000.0,
            node_resolution_ms=node_resolution_ms,
            state_space_ms=state_space_ms,
            sequential_ms=sequential_ms,
            legs=len(result[0]),
            switches=len(result[1]),
        )
        return result

    async def _multi_modal_sequential(
        self,
        origin: LatLng,
        destination: LatLng,
        modes: list[str],
        optimize: str,
        avoid_anomalies: bool,
        origin_candidates_hint: list | None = None,
        destination_candidates_hint: list | None = None,
    ) -> tuple[list[RouteLeg], list[ModeSwitch], int]:
        sequential_started = time.perf_counter()
        legs: list[RouteLeg] = []
        switches: list[ModeSwitch] = []
        total_anomalies_avoided = 0
        single_modal_ms = 0.0
        mode_switch_handling_ms = 0.0

        current_pos = origin
        for i, mode in enumerate(modes):
            leg_dest = (
                destination
                if i == len(modes) - 1
                else self._find_transfer_point(current_pos, destination, i, len(modes))
            )

            leg_started = time.perf_counter()
            leg_legs, _, avoided = await self._single_modal(
                origin=current_pos,
                destination=leg_dest,
                mode=mode,
                optimize=optimize,
                avoid_anomalies=avoid_anomalies,
                origin_candidates_hint=(origin_candidates_hint if i == 0 else None),
                destination_candidates_hint=(
                    destination_candidates_hint if i == len(modes) - 1 else None
                ),
            )
            single_modal_ms += (time.perf_counter() - leg_started) * 1000.0
            legs.extend(leg_legs)
            total_anomalies_avoided += avoided

            if i < len(modes) - 1:
                switch_started = time.perf_counter()
                next_mode = modes[i + 1]
                penalty_key = f"{mode}_to_{next_mode}"
                penalty = settings.mode_switch_penalties.get(penalty_key, {})
                switches.append(
                    ModeSwitch(
                        from_mode=mode,
                        to_mode=next_mode,
                        location=leg_dest,
                        penalty_time_s=float(penalty.get("time_seconds", 0.0) or 0.0),
                        penalty_cost=float(penalty.get("cost_units", 0.0) or 0.0),
                    )
                )
                mode_switch_handling_ms += (
                    time.perf_counter() - switch_started
                ) * 1000.0

            current_pos = leg_dest

        _profile_log(
            "multi_modal_sequential_complete",
            modes="|".join(modes),
            total_ms=(time.perf_counter() - sequential_started) * 1000.0,
            single_modal_ms=single_modal_ms,
            mode_switch_handling_ms=mode_switch_handling_ms,
            legs=len(legs),
            switches=len(switches),
        )
        return legs, switches, total_anomalies_avoided

    def _build_multimodal_from_state_path(
        self,
        graph: nx.MultiDiGraph,
        origin: LatLng,
        destination: LatLng,
        path_steps: list[dict],
    ) -> tuple[list[RouteLeg], list[ModeSwitch], int]:
        state_path_started = time.perf_counter()
        mode_switch_handling_ms = 0.0
        edge_processing_ms = 0.0
        legs: list[RouteLeg] = []
        switches: list[ModeSwitch] = []

        if not path_steps:
            _profile_log(
                "state_path_build_complete",
                status="empty_path",
                total_ms=(time.perf_counter() - state_path_started) * 1000.0,
                mode_switch_handling_ms=mode_switch_handling_ms,
                edge_processing_ms=edge_processing_ms,
                legs=len(legs),
                switches=len(switches),
            )
            return legs, switches, 0

        current_mode = None
        current_geometry: list[LatLng] = []
        current_distance_m = 0.0
        current_duration_s = 0.0
        current_traffic_edges: list[RouteTrafficEdge] = []

        def _finalize_leg(mode_name: str):
            nonlocal current_geometry, current_distance_m, current_duration_s, current_traffic_edges
            if not current_geometry:
                return
            cost_per_km = float(
                settings.vehicle_types.get(mode_name, {}).get("fuel_cost_per_km", 0.0)
                or 0.0
            )
            leg_cost = (current_distance_m / 1000.0) * cost_per_km
            start_pt = current_geometry[0]
            end_pt = current_geometry[-1]
            legs.append(
                RouteLeg(
                    mode=mode_name,
                    geometry=list(current_geometry),
                    distance_m=current_distance_m,
                    duration_s=current_duration_s,
                    cost=leg_cost,
                    traffic_edges=list(current_traffic_edges),
                    instructions=[
                        f"Start at ({start_pt.lat:.5f}, {start_pt.lng:.5f})",
                        f"Follow the shortest {mode_name} route on roads",
                        f"Arrive at ({end_pt.lat:.5f}, {end_pt.lng:.5f})",
                    ],
                )
            )
            current_geometry = []
            current_distance_m = 0.0
            current_duration_s = 0.0
            current_traffic_edges = []

        for step in path_steps:
            u = step.get("from")
            v = step.get("to")
            step_mode = self._normalize_mode(step.get("mode") or "walk")

            if current_mode is None:
                current_mode = step_mode
            elif step_mode != current_mode:
                switch_started = time.perf_counter()
                _finalize_leg(current_mode)
                switch_loc = LatLng(
                    lat=float(graph.nodes.get(u, {}).get("y") or 0.0),
                    lng=float(graph.nodes.get(u, {}).get("x") or 0.0),
                )
                penalty_key = f"{current_mode}_to_{step_mode}"
                penalty = settings.mode_switch_penalties.get(penalty_key, {})
                switches.append(
                    ModeSwitch(
                        from_mode=current_mode,
                        to_mode=step_mode,
                        location=switch_loc,
                        penalty_time_s=float(penalty.get("time_seconds", 0.0) or 0.0),
                        penalty_cost=float(penalty.get("cost_units", 0.0) or 0.0),
                    )
                )
                current_mode = step_mode
                mode_switch_handling_ms += (
                    time.perf_counter() - switch_started
                ) * 1000.0

            edge_started = time.perf_counter()
            edge_data = self._best_edge_for_mode(graph, u, v, step_mode)
            if not edge_data:
                edge_processing_ms += (time.perf_counter() - edge_started) * 1000.0
                continue

            current_distance_m += float(edge_data.get("length") or 0.0)
            current_duration_s += float(
                edge_data.get(f"{step_mode}_travel_time")
                or edge_data.get("travel_time")
                or 0.0
            )

            current_traffic_edges.append(
                RouteTrafficEdge(
                    edge_id=f"{u}->{v}:0",
                    road_type=self._road_type(edge_data),
                    length_m=float(edge_data.get("length") or 0.0),
                )
            )

            edge_points = self._edge_geometry_points(graph, u, v, edge_data)
            if current_geometry and edge_points:
                if (
                    current_geometry[-1].lat == edge_points[0].lat
                    and current_geometry[-1].lng == edge_points[0].lng
                ):
                    current_geometry.extend(edge_points[1:])
                else:
                    current_geometry.extend(edge_points)
            else:
                current_geometry.extend(edge_points)

            edge_processing_ms += (time.perf_counter() - edge_started) * 1000.0

        if current_mode is not None:
            _finalize_leg(current_mode)

        if legs:
            first_leg = legs[0]
            if first_leg.geometry:
                first_leg.instructions[0] = (
                    f"Start at ({origin.lat:.5f}, {origin.lng:.5f})"
                )

            last_leg = legs[-1]
            if last_leg.geometry:
                last_leg.instructions[-1] = (
                    f"Arrive at ({destination.lat:.5f}, {destination.lng:.5f})"
                )

        _profile_log(
            "state_path_build_complete",
            status="ok",
            total_ms=(time.perf_counter() - state_path_started) * 1000.0,
            mode_switch_handling_ms=mode_switch_handling_ms,
            edge_processing_ms=edge_processing_ms,
            path_steps=len(path_steps),
            legs=len(legs),
            switches=len(switches),
        )

        return legs, switches, 0

    def _build_weight_fn(self, mode: str, optimize: str) -> Callable:
        def weight(u, v, data):
            best = float("inf")
            for edge in data.values():
                mode_allowed = bool(edge.get(f"{mode}_allowed", False))
                if mode == "walk":
                    mode_allowed = bool(
                        edge.get(
                            "walk_allowed",
                            edge.get(
                                "walking_allowed", edge.get("pedestrian_allowed", False)
                            ),
                        )
                    )
                if not mode_allowed:
                    continue
                length = float(edge.get("length") or 0.0)
                travel_time = float(
                    edge.get(f"{mode}_travel_time") or edge.get("travel_time") or 0.0
                )
                cost_per_km = float(
                    settings.vehicle_types[mode].get("fuel_cost_per_km", 0.0) or 0.0
                )
                cost = (length / 1000.0) * cost_per_km

                if optimize == "distance":
                    value = max(length, 0.01)
                elif optimize == "cost":
                    value = max(cost, 0.0001)
                else:
                    value = max(travel_time, 0.01)

                if value < best:
                    best = value
            return best

        return weight

    def _best_edge_data(
        self, graph: nx.MultiDiGraph, u, v, weight_fn: Callable
    ) -> dict:
        data = graph.get_edge_data(u, v) or {}
        if not data:
            return {}

        best_key = None
        best_weight = float("inf")
        for key in data:
            fake_wrapper = {key: data[key]}
            w = weight_fn(u, v, fake_wrapper)
            if w < best_weight:
                best_weight = w
                best_key = key
        best_edge = (
            data[best_key] if best_key is not None else next(iter(data.values()))
        )
        if best_key is not None:
            best_edge = dict(best_edge)
            best_edge["_key"] = best_key
        return best_edge

    def _best_edge_data_for_step(
        self,
        graph: nx.MultiDiGraph,
        u,
        v,
        mode: str,
        optimize: str,
        weight_fn: Callable,
        *,
        allow_reverse_edge: bool,
    ) -> dict:
        if graph.has_edge(u, v):
            best_direct = self._best_edge_data(graph, u, v, weight_fn)
            if best_direct:
                chosen_key = best_direct.get("_key")
                if chosen_key is None:
                    chosen_key = 0
                best_direct["_edge_id"] = f"{u}->{v}:{chosen_key}"
            return best_direct

        if not allow_reverse_edge or not graph.has_edge(v, u):
            return {}

        best_reverse = self._best_edge_data(graph, v, u, weight_fn)
        if not best_reverse:
            return {}

        if self._edge_cost_for_mode(best_reverse, mode, optimize) is None:
            return {}

        best_reverse = dict(best_reverse)
        best_reverse["_reverse"] = True
        chosen_key = best_reverse.get("_key")
        if chosen_key is None:
            chosen_key = 0
        best_reverse["_edge_id"] = f"{v}->{u}:{chosen_key}"
        return best_reverse

    def _edge_geometry_points(
        self, graph: nx.MultiDiGraph, u, v, edge_data: dict
    ) -> list[LatLng]:
        geom = edge_data.get("geometry")
        points: list[LatLng] = []

        if geom is not None and hasattr(geom, "coords"):
            for x, y in list(geom.coords):
                points.append(LatLng(lat=float(y), lng=float(x)))
            if points:
                return points

        u_data = graph.nodes.get(u, {})
        v_data = graph.nodes.get(v, {})
        return [
            LatLng(
                lat=float(u_data.get("y") or 0.0), lng=float(u_data.get("x") or 0.0)
            ),
            LatLng(
                lat=float(v_data.get("y") or 0.0), lng=float(v_data.get("x") or 0.0)
            ),
        ]

    def _find_transfer_point(
        self, current: LatLng, destination: LatLng, leg_index: int, total_legs: int
    ) -> LatLng:
        fraction = (leg_index + 1) / total_legs
        return LatLng(
            lat=current.lat + (destination.lat - current.lat) * fraction,
            lng=current.lng + (destination.lng - current.lng) * fraction,
        )

    def _build_synthetic_leg(
        self, mode: str, origin: LatLng, destination: LatLng
    ) -> RouteLeg:
        """Fallback when graph data is unavailable: direct-line estimate preserving response contract."""
        distance_m = self._haversine_distance_m(
            origin.lat, origin.lng, destination.lat, destination.lng
        )
        speed_kmh = float(
            settings.vehicle_types[mode].get("default_speed_kmh", 30.0) or 30.0
        )
        speed_mps = max(speed_kmh / 3.6, 0.1)
        duration_s = distance_m / speed_mps
        cost_per_km = float(
            settings.vehicle_types[mode].get("fuel_cost_per_km", 0.0) or 0.0
        )
        cost = (distance_m / 1000.0) * cost_per_km

        return RouteLeg(
            mode=mode,
            geometry=[origin, destination],
            distance_m=distance_m,
            duration_s=duration_s,
            cost=cost,
            instructions=[
                f"Start at ({origin.lat:.5f}, {origin.lng:.5f})",
                f"Proceed directly toward destination using {mode}",
                f"Arrive at ({destination.lat:.5f}, {destination.lng:.5f})",
            ],
        )

    def _safe_shortest_path(
        self,
        graph: nx.MultiDiGraph,
        source,
        target,
        weight_fn: Callable,
    ):
        try:
            return nx.shortest_path(
                graph,
                source=source,
                target=target,
                weight=weight_fn,
                method="dijkstra",
            )
        except nx.NetworkXNoPath:
            return None

    def _haversine_distance_m(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        r = 6_371_000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    async def _compute_alternatives(
        self, request: RouteRequest, num_alternatives: int
    ) -> list[list[RouteLeg]]:
        del request, num_alternatives
        return []

    def _build_multimodal_suggestions_from_route_legs(
        self,
        route_legs: list[RouteLeg],
    ) -> list[MultimodalSuggestion]:
        graph = graph_service.get_graph()
        if not route_legs:
            return []

        segments: list[SegmentSuggestion] = []
        total_distance_m = 0.0
        total_duration_s = 0.0

        for leg in route_legs:
            traffic_edges = list(leg.traffic_edges or [])

            # If edge-level references are unavailable, keep the leg as one segment.
            if not traffic_edges or graph is None:
                mode_name = self._display_mode(str(leg.mode or "walk"))
                segments.append(
                    SegmentSuggestion(
                        segment_index=len(segments),
                        distance_m=float(leg.distance_m or 0.0),
                        road_type="mixed",
                        recommended_vehicle=mode_name,
                        geometry=list(leg.geometry or []),
                        vehicle_options=[
                            VehicleOption(
                                vehicle=mode_name,
                                travel_time_s=float(leg.duration_s or 0.0),
                                allowed=True,
                            )
                        ],
                    )
                )
                total_distance_m += float(leg.distance_m or 0.0)
                total_duration_s += float(leg.duration_s or 0.0)
                continue

            for t_edge in traffic_edges:
                edge_ref = self._parse_edge_id(t_edge.edge_id)
                if edge_ref is None:
                    continue

                u, v, edge_key = edge_ref
                edge_data_all = graph.get_edge_data(u, v) or {}
                if not edge_data_all:
                    continue

                selected = edge_data_all.get(edge_key)
                if selected is None:
                    selected = next(iter(edge_data_all.values()))
                edge_data = dict(selected)
                edge_data["_key"] = edge_key

                preferred_mode = self._select_preferred_mode_by_hierarchy(edge_data)
                distance_m = float(edge_data.get("length") or t_edge.length_m or 0.0)
                duration_s = float(
                    edge_data.get(f"{preferred_mode}_travel_time")
                    or edge_data.get("travel_time")
                    or 0.0
                )

                segments.append(
                    SegmentSuggestion(
                        segment_index=len(segments),
                        distance_m=distance_m,
                        road_type=self._road_type(edge_data),
                        recommended_vehicle=self._display_mode(preferred_mode),
                        geometry=self._edge_geometry_points(graph, u, v, edge_data),
                        vehicle_options=self._vehicle_options_for_edge(edge_data),
                    )
                )
                total_distance_m += distance_m
                total_duration_s += duration_s

        if not segments:
            return []

        return [
            MultimodalSuggestion(
                strategy="shortest_distance",
                total_distance_m=total_distance_m,
                total_duration_s=total_duration_s,
                segments=segments,
            )
        ]

    def _build_multimodal_suggestion_from_legs(
        self,
        route_legs: list[RouteLeg],
        strategy: str,
    ) -> MultimodalSuggestion | None:
        if not route_legs:
            return None

        segments: list[SegmentSuggestion] = []
        total_distance_m = 0.0
        total_duration_s = 0.0

        for idx, leg in enumerate(route_legs):
            if not leg.geometry:
                continue
            segments.append(
                SegmentSuggestion(
                    segment_index=idx,
                    distance_m=float(leg.distance_m or 0.0),
                    road_type=(
                        leg.traffic_edges[0].road_type if leg.traffic_edges else "mixed"
                    ),
                    recommended_vehicle=self._display_mode(str(leg.mode or "walk")),
                    geometry=list(leg.geometry or []),
                    vehicle_options=[
                        VehicleOption(
                            vehicle=self._display_mode(str(leg.mode or "walk")),
                            travel_time_s=float(leg.duration_s or 0.0),
                            allowed=True,
                        )
                    ],
                )
            )
            total_distance_m += float(leg.distance_m or 0.0)
            total_duration_s += float(leg.duration_s or 0.0)

        if not segments:
            return None

        return MultimodalSuggestion(
            strategy=strategy,
            total_distance_m=total_distance_m,
            total_duration_s=total_duration_s,
            segments=segments,
        )

    def _select_preferred_mode_by_hierarchy(self, edge_data: dict) -> str:
        # Required hierarchy:
        # Bus > Car > Bike > Rickshaw > Walk
        for mode in ("transit", "car", "bike", "rickshaw", "walk"):
            if bool(edge_data.get(f"{mode}_allowed", False)):
                return mode
        return "walk"

    def _parse_edge_id(self, edge_id: str):
        try:
            uv, key = str(edge_id).split(":", 1)
            u, v = uv.split("->", 1)
            return int(u), int(v), int(key)
        except Exception:
            return None

    def _compute_multimodal_suggestions(
        self,
        origin: LatLng,
        destination: LatLng,
        fallback_legs: list[RouteLeg] | None = None,
    ) -> list[MultimodalSuggestion]:
        graph = graph_service.get_graph()
        if graph is None or graph.number_of_nodes() == 0:
            return self._fallback_multimodal_suggestions_from_legs(fallback_legs)

        origin_node = graph_service.get_nearest_node(origin.lat, origin.lng)
        dest_node = graph_service.get_nearest_node(destination.lat, destination.lng)
        if origin_node is None or dest_node is None:
            return self._fallback_multimodal_suggestions_from_legs(fallback_legs)

        modes = list(settings.vehicle_types.keys())
        if not modes:
            return self._fallback_multimodal_suggestions_from_legs(fallback_legs)

        suggestions: list[MultimodalSuggestion] = []

        # 1) Distance-optimal route.
        try:
            dist_path = nx.shortest_path(
                graph,
                source=origin_node,
                target=dest_node,
                weight=lambda _u, _v, data: min(
                    max(float(edge.get("length") or 0.0), 0.01)
                    for edge in data.values()
                ),
                method="dijkstra",
            )
            dist_suggestion = self._build_suggestion_from_node_path(
                graph=graph,
                node_path=dist_path,
                strategy="shortest_distance",
            )
            suggestions.append(dist_suggestion)
        except Exception:
            pass

        # 2) Time-optimal route. Build from the same allowed-mode state-space search
        # so the map can show a distinct alternative route in multimodal mode.
        try:
            switch_penalty = float(
                settings.mode_switch_penalties.get("default_penalty_seconds", 5.0)
            )
            time_result = multi_modal_dijkstra_with_coords(
                graph=graph,
                start=origin_node,
                end=dest_node,
                allowed_modes=modes,
                switch_penalty=switch_penalty,
            )
            if time_result and time_result.get("path"):
                built_legs, _switches, _avoided = (
                    self._build_multimodal_from_state_path(
                        graph=graph,
                        origin=origin,
                        destination=destination,
                        path_steps=time_result["path"],
                    )
                )
                time_suggestion = self._build_multimodal_suggestion_from_legs(
                    built_legs,
                    strategy="fastest_time",
                )
                if time_suggestion is not None:
                    suggestions.append(time_suggestion)
        except Exception:
            pass

        if suggestions:
            return suggestions

        return self._fallback_multimodal_suggestions_from_legs(fallback_legs)

    def _fallback_multimodal_suggestions_from_legs(
        self,
        fallback_legs: list[RouteLeg] | None,
    ) -> list[MultimodalSuggestion]:
        if not fallback_legs:
            return []

        segments: list[SegmentSuggestion] = []
        total_distance_m = 0.0
        total_duration_s = 0.0

        for idx, leg in enumerate(fallback_legs):
            road_type = "mixed"
            if leg.traffic_edges:
                road_type = str(leg.traffic_edges[0].road_type or "mixed")

            segments.append(
                SegmentSuggestion(
                    segment_index=idx,
                    distance_m=float(leg.distance_m or 0.0),
                    road_type=road_type,
                    recommended_vehicle=self._display_mode(str(leg.mode or "walk")),
                    geometry=list(leg.geometry or []),
                    vehicle_options=[
                        VehicleOption(
                            vehicle=self._display_mode(str(leg.mode or "walk")),
                            travel_time_s=float(leg.duration_s or 0.0),
                            allowed=True,
                        )
                    ],
                )
            )
            total_distance_m += float(leg.distance_m or 0.0)
            total_duration_s += float(leg.duration_s or 0.0)

        if not segments:
            return []

        return [
            MultimodalSuggestion(
                strategy="fastest_time",
                total_distance_m=total_distance_m,
                total_duration_s=total_duration_s,
                segments=segments,
            )
        ]

    def _build_suggestion_from_node_path(
        self, graph: nx.MultiDiGraph, node_path: list, strategy: str
    ) -> MultimodalSuggestion:
        segments: list[SegmentSuggestion] = []
        total_distance_m = 0.0
        total_duration_s = 0.0

        for idx in range(len(node_path) - 1):
            u = node_path[idx]
            v = node_path[idx + 1]
            edge_data = self._best_edge_any(graph, u, v)
            if not edge_data:
                continue

            distance_m = float(edge_data.get("length") or 0.0)
            road_type = self._road_type(edge_data)
            edge_geometry = self._edge_geometry_points(graph, u, v, edge_data)
            options = self._vehicle_options_for_edge(edge_data)
            allowed_options = [o for o in options if o.allowed]
            if allowed_options:
                best = min(allowed_options, key=lambda o: o.travel_time_s)
                rec_mode = best.vehicle
                rec_time = best.travel_time_s
            else:
                rec_mode = "walk"
                rec_time = float(
                    edge_data.get("walk_travel_time")
                    or edge_data.get("travel_time")
                    or 0.0
                )

            segments.append(
                SegmentSuggestion(
                    segment_index=idx,
                    distance_m=distance_m,
                    road_type=road_type,
                    recommended_vehicle=self._display_mode(rec_mode),
                    geometry=edge_geometry,
                    vehicle_options=options,
                )
            )
            total_distance_m += distance_m
            total_duration_s += rec_time

        return MultimodalSuggestion(
            strategy=strategy,
            total_distance_m=total_distance_m,
            total_duration_s=total_duration_s,
            segments=segments,
        )

    def _best_edge_any(self, graph: nx.MultiDiGraph, u, v) -> dict:
        data = graph.get_edge_data(u, v) or {}
        if not data:
            return {}
        return min(
            data.values(),
            key=lambda e: max(float(e.get("length") or 0.0), 0.01),
        )

    def _best_edge_for_mode(self, graph: nx.MultiDiGraph, u, v, mode: str) -> dict:
        data = graph.get_edge_data(u, v) or {}
        if not data:
            return {}
        if mode == "walk":
            allowed = [
                e
                for e in data.values()
                if bool(
                    e.get(
                        "walk_allowed",
                        e.get("walking_allowed", e.get("pedestrian_allowed", False)),
                    )
                )
            ]
        else:
            allowed = [
                e for e in data.values() if bool(e.get(f"{mode}_allowed", False))
            ]
        if not allowed:
            return {}

        return min(
            allowed,
            key=lambda e: max(
                float(e.get(f"{mode}_travel_time") or e.get("travel_time") or 0.0),
                0.01,
            ),
        )

    def _road_type(self, edge_data: dict) -> str:
        road = edge_data.get("road_type") or edge_data.get("highway") or "unknown"
        if isinstance(road, (list, tuple)):
            return str(road[0]) if road else "unknown"
        return str(road)

    def _vehicle_options_for_edge(self, edge_data: dict) -> list[VehicleOption]:
        options: list[VehicleOption] = []
        for mode in settings.vehicle_types.keys():
            allowed = bool(edge_data.get(f"{mode}_allowed", False))
            t = float(
                edge_data.get(f"{mode}_travel_time")
                or edge_data.get("travel_time")
                or 0.0
            )
            options.append(
                VehicleOption(
                    vehicle=self._display_mode(mode),
                    travel_time_s=t,
                    allowed=allowed,
                )
            )
        options.sort(key=lambda o: o.travel_time_s)
        return options

    async def _refresh_ml_weights(self):
        now = time.monotonic()
        if self._ml_refresh_interval_s > 0.0:
            if (now - self._last_ml_refresh_monotonic) < self._ml_refresh_interval_s:
                return
            self._last_ml_refresh_monotonic = now

        started = time.perf_counter()
        try:
            await ml_integration.refresh_predictions()
            _profile_log(
                "ml_refresh_complete",
                runtime_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as e:
            print(f"[RoutingEngine] ML weight refresh failed (using defaults): {e}")
            _profile_log(
                "ml_refresh_failed",
                runtime_ms=(time.perf_counter() - started) * 1000.0,
                error=type(e).__name__,
            )


routing_engine = RoutingEngine()
