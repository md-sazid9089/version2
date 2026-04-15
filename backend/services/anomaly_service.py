"""
Anomaly Service — Real-Time Anomaly Ingestion & Dynamic Rerouting
===================================================================
Handles the lifecycle of traffic anomalies:
  1. Ingest: Accept anomaly reports, validate, store in active list
  2. Apply: Modify affected edge weights in the graph using severity multipliers
  3. Expire: Automatically remove old anomalies and restore edge weights
  4. Query: Return list of currently active anomalies

Integration:
  - Called by routes/anomaly.py for ingestion and querying
  - Calls graph_service to modify/reset edge weights
  - Read by routing_engine to decide if rerouting is needed
  - Severity multipliers come from config.json → anomaly.weight_multipliers
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import settings
from models.anomaly_models import AnomalyReport, ActiveAnomaly, AnomalyEffects
from services.graph_service import graph_service


class AnomalyService:
    """
    Singleton service for anomaly lifecycle management.
    Anomalies are stored in-memory (suitable for hackathon/demo scope).
    """

    def __init__(self):
        # In-memory store of active anomalies keyed by anomaly_id
        self._active: dict[str, ActiveAnomaly] = {}
        # Config references
        self._default_expire = settings.anomaly_config.get("auto_expire_minutes", 60)
        self._reroute_threshold = settings.anomaly_config.get(
            "reroute_on_severity", "medium"
        )
        self._pedestrian_zone_rickshaw_allowed = bool(
            settings.anomaly_config.get("pedestrian_zone_rickshaw_allowed", True)
        )
        self._applied_edge_effects: dict[str, dict] = {}
        self._edge_resolve_cache: dict[str, tuple | None] = {}
        self._edge_resolve_cache_max = 4096

    # ─── Ingest ──────────────────────────────────────────────────

    async def ingest(self, report: AnomalyReport) -> str:
        """
        Process a new anomaly report:
          1. Validate severity level
          2. Resolve affected graph edges from location
          3. Apply weight multiplier to affected edges
          4. Store anomaly with expiry time
          5. Return anomaly_id

        Raises ValueError for invalid severity or location.
        """
        self.sync_active_effects()

        # Generate unique ID
        anomaly_id = f"anomaly_{uuid.uuid4().hex[:12]}"

        # Resolve affected edges from edge_ids / target / location.
        affected_edges = self._resolve_edges(report)
        if not affected_edges:
            raise ValueError("No valid edges resolved for anomaly report")

        severity_multiplier = self._resolve_severity_multiplier(report.severity)
        effects = self._resolve_effects(report, severity_multiplier)
        multiplier = float(severity_multiplier)
        vehicle_types = sorted(
            set(effects.weight_multiplier.keys()).union(set(effects.disable_modes))
        )

        # Calculate expiry
        now = datetime.now(timezone.utc)

        if report.ttl is not None:
            duration_seconds = max(int(report.ttl), 1)
            expires_at = now + timedelta(seconds=duration_seconds)
        else:
            duration = report.duration_minutes or self._default_expire
            expires_at = now + timedelta(minutes=duration)

        start_time = self._normalize_dt(report.start_time) or now
        end_time = self._normalize_dt(report.end_time) or expires_at
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time")

        # Store active anomaly
        active = ActiveAnomaly(
            anomaly_id=anomaly_id,
            location=report.location,
            edge_ids=affected_edges,
            vehicle_types=vehicle_types,
            target=report.target,
            effects=effects,
            severity=multiplier,
            type=report.type,
            description=report.description,
            weight_multiplier=multiplier,
            created_at=start_time,
            expires_at=end_time,
        )
        self._active[anomaly_id] = active

        # Apply (or defer) effects based on current time window.
        self.sync_active_effects()

        print(
            f"[AnomalyService] Ingested {anomaly_id}: "
            f"type={report.type}, severity={multiplier}, edges={len(affected_edges)}, "
            f"vehicles={vehicle_types}, start={start_time.isoformat()}, end={end_time.isoformat()}"
        )

        return anomaly_id

    # ─── Query ───────────────────────────────────────────────────

    async def get_active(self) -> list[ActiveAnomaly]:
        """
        Return all currently active anomalies.
        Automatically prunes expired anomalies before returning.
        """
        self.sync_active_effects()
        return list(self._active.values())

    def is_rerouting_needed(self) -> bool:
        """
        Check if any active anomaly has severity >= reroute threshold.
        Used by routing_engine to decide if rerouting logic should activate.
        """
        threshold_value = {
            "low": 1.0,
            "medium": 3.0,
            "high": 5.0,
            "critical": 8.0,
        }.get(str(self._reroute_threshold).lower(), 3.0)

        for anomaly in self._active.values():
            if float(anomaly.severity) >= threshold_value:
                return True
        return False

    def get_anomaly_edges(self) -> set[str]:
        """Return set of all edge IDs currently affected by anomalies."""
        self.sync_active_effects()
        edges = set()
        for anomaly in self._active.values():
            edges.update(anomaly.edge_ids)
        return edges

    def sync_active_effects(self):
        """Reconcile all active anomaly effects based on current time window."""
        now = datetime.now(timezone.utc)
        graph = graph_service.get_graph()
        if graph is None:
            return

        # Drop expired anomalies.
        expired_ids = [
            aid for aid, anomaly in self._active.items() if anomaly.expires_at <= now
        ]
        for aid in expired_ids:
            self._active.pop(aid, None)

        edge_mode_max_multiplier: dict[tuple[str, str], float] = {}
        edge_disabled_modes: dict[str, set[str]] = {}

        for anomaly in self._active.values():
            if anomaly.created_at > now or anomaly.expires_at <= now:
                continue

            effects = anomaly.effects or AnomalyEffects()
            for edge_id in anomaly.edge_ids:
                if effects.disable_modes:
                    edge_disabled_modes.setdefault(edge_id, set()).update(
                        effects.disable_modes
                    )

                for mode, mul in effects.weight_multiplier.items():
                    key = (edge_id, mode)
                    edge_mode_max_multiplier[key] = max(
                        edge_mode_max_multiplier.get(key, 1.0),
                        float(mul),
                    )

        desired_effects: dict[str, dict] = {}
        for (edge_id, mode), multiplier in edge_mode_max_multiplier.items():
            entry = desired_effects.setdefault(
                edge_id,
                {"multipliers": {}, "disabled_modes": set()},
            )
            entry["multipliers"][mode] = float(multiplier)

        for edge_id, disabled_modes in edge_disabled_modes.items():
            entry = desired_effects.setdefault(
                edge_id,
                {"multipliers": {}, "disabled_modes": set()},
            )
            entry["disabled_modes"].update(disabled_modes)

        all_edge_ids = set(self._applied_edge_effects.keys()).union(
            set(desired_effects.keys())
        )

        changed_pairs: set[tuple] = set()
        mode_constraints_changed = False

        for edge_id in all_edge_ids:
            current = self._applied_edge_effects.get(
                edge_id,
                {"multipliers": {}, "disabled_modes": set()},
            )
            target = desired_effects.get(
                edge_id,
                {"multipliers": {}, "disabled_modes": set()},
            )

            current_multipliers = current.get("multipliers", {})
            current_disabled = set(current.get("disabled_modes", set()))
            target_multipliers = target.get("multipliers", {})
            target_disabled = set(target.get("disabled_modes", set()))

            if (
                current_multipliers == target_multipliers
                and current_disabled == target_disabled
            ):
                continue

            resolved = self._resolve_graph_edge_nodes(edge_id)
            if not resolved:
                continue

            source, target_node = resolved
            changed_pairs.add((source, target_node))

            self._reset_edge_to_base(source, target_node)

            for mode, multiplier in target_multipliers.items():
                self._apply_edge_mode_current_weight(
                    source,
                    target_node,
                    mode,
                    multiplier,
                )

            if target_disabled:
                self._disable_edge_modes_on_pair(source, target_node, target_disabled)

            if current_disabled or target_disabled:
                mode_constraints_changed = True

        normalized_effects: dict[str, dict] = {}
        for edge_id, effect in desired_effects.items():
            normalized_effects[edge_id] = {
                "multipliers": dict(effect.get("multipliers", {})),
                "disabled_modes": set(effect.get("disabled_modes", set())),
            }
        self._applied_edge_effects = normalized_effects

        if changed_pairs:
            graph_service.mark_graph_changed(
                mode_constraints_changed=mode_constraints_changed,
            )

    async def clear_all(self) -> int:
        self.sync_active_effects()
        active_ids = list(self._active.keys())
        for aid in active_ids:
            self._active.pop(aid, None)
        self.sync_active_effects()
        return len(active_ids)

    # ─── Edge Resolution ─────────────────────────────────────────

    def _resolve_edges(self, report: AnomalyReport) -> list[str]:
        """
        Resolve the anomaly location to a list of affected graph edge IDs.
        Supports: direct edge_id, wildcard "*", or lat/lng nearest-node lookup.
        """
        edge_ids: list[str] = []

        if report.edge_ids:
            edge_ids = list(dict.fromkeys(report.edge_ids))
        elif report.target:
            if report.target.type == "edge" and report.target.edge_ids:
                edge_ids = list(dict.fromkeys(report.target.edge_ids))

            elif report.target.type == "bbox" and report.target.bbox:
                bbox = report.target.bbox
                if len(bbox) != 4:
                    raise ValueError("bbox must contain [south, west, north, east]")
                edge_ids = self._resolve_edges_from_bbox(tuple(float(x) for x in bbox))
        elif report.location and report.location.edge_id:
            if report.location.edge_id == "*":
                graph = graph_service.get_graph()
                if graph:
                    edge_ids = [f"{u}->{v}" for u, v, _ in graph.edges(keys=True)]
                else:
                    edge_ids = ["*"]
            else:
                edge_ids = [report.location.edge_id]
        elif (
            report.location
            and report.location.lat is not None
            and report.location.lng is not None
        ):
            nearest_node = graph_service.get_nearest_node(
                report.location.lat, report.location.lng
            )
            if nearest_node is None:
                # Fallback for out-of-bounds coordinates: snap to absolute nearest node.
                nearest_node, _ = graph_service.get_nearest_node_with_distance(
                    report.location.lat, report.location.lng
                )
            if nearest_node:
                graph = graph_service.get_graph()
                if graph:
                    for _, v, _ in graph.out_edges(nearest_node, keys=True):
                        edge_ids.append(f"{nearest_node}->{v}")
                    for u, _, _ in graph.in_edges(nearest_node, keys=True):
                        edge_ids.append(f"{u}->{nearest_node}")

        if (
            not edge_ids
            and report.location
            and report.location.lat is not None
            and report.location.lng is not None
        ):
            # Preserve location-scoped anomalies even if no graph edge could be resolved.
            edge_ids = [
                f"virtual:{float(report.location.lat):.6f},{float(report.location.lng):.6f}"
            ]

        edge_ids = list(dict.fromkeys(edge_ids))
        edge_ids = self._expand_bidirectional_edge_ids(edge_ids)

        # VIP movement only applies on main roads.
        if (report.type or "").strip().lower() in {"vip_movement", "vip"}:
            edge_ids = [eid for eid in edge_ids if self._is_main_road_edge(eid)]

        return edge_ids

    def _is_main_road_edge(self, edge_id: str) -> bool:
        graph = graph_service.get_graph()
        if graph is None:
            return False

        resolved = self._resolve_graph_edge_nodes(edge_id)
        if not resolved:
            return False

        source, target = resolved

        for key in graph[source][target]:
            edge_data = graph[source][target][key]
            road_type = str(
                edge_data.get("road_type") or edge_data.get("highway") or ""
            )
            if road_type in {
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
            }:
                return True
        return False

    def _resolve_edges_from_bbox(
        self, bbox: tuple[float, float, float, float]
    ) -> list[str]:
        graph = graph_service.get_graph()
        if graph is None:
            return []

        south, west, north, east = bbox
        edge_ids = []
        for u, v, _k, _data in graph.edges(keys=True, data=True):
            u_data = graph.nodes.get(u, {})
            v_data = graph.nodes.get(v, {})
            u_lat = float(u_data.get("y") or 0.0)
            u_lng = float(u_data.get("x") or 0.0)
            v_lat = float(v_data.get("y") or 0.0)
            v_lng = float(v_data.get("x") or 0.0)
            if (south <= u_lat <= north and west <= u_lng <= east) or (
                south <= v_lat <= north and west <= v_lng <= east
            ):
                edge_ids.append(f"{u}->{v}")

        return list(dict.fromkeys(edge_ids))

    def _resolve_effects(
        self,
        report: AnomalyReport,
        severity_value: float,
    ) -> AnomalyEffects:
        # If explicit effects are provided, trust them (normalized aliases).
        if report.effects is not None:
            return AnomalyEffects(
                weight_multiplier={
                    self._normalize_mode(k): float(v)
                    for k, v in report.effects.weight_multiplier.items()
                    if float(v) > 0
                },
                disable_modes=[
                    self._normalize_mode(m) for m in report.effects.disable_modes
                ],
            )

        anomaly_type = (report.type or "").strip().lower()
        severity = max(float(severity_value), 1.0)
        severity_factor = max(0.4, min(severity / 3.0, 2.0))

        def scale(base: float) -> float:
            # severity=3 keeps base multiplier; lower/higher scales impact.
            return max(1.0, 1.0 + (base - 1.0) * severity_factor)

        if anomaly_type in {"traffic_congestion", "traffic"}:
            return AnomalyEffects(
                weight_multiplier={
                    "car": scale(5.0),
                    "transit": scale(4.0),
                    "bike": scale(2.0),
                },
                disable_modes=[],
            )

        if anomaly_type in {"road_block", "closure", "road_closure", "road_blockade"}:
            return AnomalyEffects(
                weight_multiplier={
                    "walk": 1e6,
                    "rickshaw": 1e6,
                    "bike": 1e6,
                    "car": 1e6,
                    "transit": 1e6,
                },
                disable_modes=["car", "transit"],
            )

        if anomaly_type in {"waterlogging", "flood", "water"}:
            return AnomalyEffects(
                weight_multiplier={
                    "car": scale(6.0),
                    "bike": scale(4.0),
                    "rickshaw": scale(2.0),
                    "walk": scale(1.5),
                },
                disable_modes=[],
            )

        if anomaly_type in {"vip_movement", "vip"}:
            # Handled by mode disable + main-road filtering in _resolve_edges.
            return AnomalyEffects(
                weight_multiplier={}, disable_modes=["car", "transit"]
            )

        if anomaly_type in {"public_transport_delay", "bus_delay"}:
            return AnomalyEffects(
                weight_multiplier={"transit": scale(3.0)}, disable_modes=[]
            )

        if anomaly_type in {"partial_lane_block", "lane_block"}:
            return AnomalyEffects(
                weight_multiplier={
                    "car": scale(2.0),
                    "transit": scale(2.0),
                    "bike": scale(2.0),
                    "rickshaw": scale(2.0),
                },
                disable_modes=[],
            )

        if anomaly_type in {"pedestrian_only_zone", "pedestrian_zone"}:
            disable = ["car", "bike"]
            if not self._pedestrian_zone_rickshaw_allowed:
                disable.append("rickshaw")
            return AnomalyEffects(weight_multiplier={}, disable_modes=disable)

        # Fallback generic weighted anomaly.
        explicit_modes = self._resolve_vehicle_types(report.vehicle_types)
        return AnomalyEffects(
            weight_multiplier={m: float(severity_value) for m in explicit_modes},
            disable_modes=[],
        )

    def _resolve_severity_multiplier(self, severity: float | str) -> float:
        if isinstance(severity, (int, float)):
            value = float(severity)
            if value <= 0:
                raise ValueError("severity must be greater than 0")
            return value

        text = str(severity).strip().lower()
        if not text:
            raise ValueError("severity is required")

        multipliers = settings.anomaly_config.get("weight_multipliers", {})
        if text in multipliers:
            value = float(multipliers[text])
            if value <= 0:
                raise ValueError(
                    f"Configured multiplier for severity '{text}' must be greater than 0"
                )
            return value

        try:
            value = float(text)
        except ValueError:
            allowed = sorted(multipliers.keys())
            raise ValueError(
                f"Invalid severity '{severity}'. Use a numeric multiplier or one of {allowed}"
            )

        if value <= 0:
            raise ValueError("severity must be greater than 0")

        return value

    def _resolve_vehicle_types(self, vehicle_types: list[str]) -> list[str]:
        if not vehicle_types:
            return ["walk", "rickshaw", "bike", "car", "transit"]

        resolved = []
        for vt in vehicle_types:
            normalized = self._normalize_mode(vt)
            if normalized in {"walk", "rickshaw", "bike", "car", "transit"}:
                resolved.append(normalized)

        if not resolved:
            raise ValueError("vehicle_types contains no supported vehicles")

        return list(dict.fromkeys(resolved))

    # ─── Weight Application ──────────────────────────────────────

    def _apply_weight_multiplier(self, edge_id: str, vehicle: str, multiplier: float):
        """
        Apply the severity-based weight multiplier to an edge.
        Parses edge_id in 'source->target' format and calls graph_service.
        """
        resolved = self._resolve_graph_edge_nodes(edge_id)
        if resolved:
            source, target = resolved
            self._apply_edge_mode_current_weight(source, target, vehicle, multiplier)
        print(
            f"[AnomalyService] Applied {multiplier}x multiplier to edge {edge_id} vehicle={vehicle}"
        )

    def _apply_edge_mode_current_weight(
        self, source: str, target: str, vehicle: str, multiplier: float
    ):
        graph = graph_service.get_graph()
        if not graph or not graph.has_edge(source, target):
            return

        for key in graph[source][target]:
            edge_data = graph[source][target][key]
            base_key = f"{vehicle}_base_travel_time"
            time_key = f"{vehicle}_travel_time"
            base = float(edge_data.get(base_key, edge_data.get(time_key, 0.0)) or 0.0)
            edge_data[time_key] = base * float(multiplier)
            if "weights" in edge_data:
                edge_data["weights"][vehicle] = base * float(multiplier)

            if vehicle == "transit":
                edge_data["travel_time"] = max(
                    float(edge_data.get("travel_time", 0.0)),
                    float(edge_data[time_key]),
                )

    def _disable_edge_modes(self, edge_id: str, modes: set[str]):
        resolved = self._resolve_graph_edge_nodes(edge_id)
        if not resolved:
            return

        source, target = resolved
        self._disable_edge_modes_on_pair(source, target, modes)

    def _disable_edge_modes_on_pair(self, source: str, target: str, modes: set[str]):
        graph = graph_service.get_graph()
        if not graph or not graph.has_edge(source, target):
            return

        for key in graph[source][target]:
            edge_data = graph[source][target][key]
            for mode in modes:
                edge_data[f"{mode}_allowed"] = False
                if "constraints" in edge_data:
                    edge_data["constraints"][f"{mode}_allowed"] = False

    def _reset_edge_to_base(self, source: str, target: str):
        graph = graph_service.get_graph()
        if not graph or not graph.has_edge(source, target):
            return

        for key in graph[source][target]:
            edge_data = graph[source][target][key]
            for mode in settings.vehicle_types.keys():
                base_key = f"{mode}_base_travel_time"
                time_key = f"{mode}_travel_time"
                base = float(
                    edge_data.get(base_key, edge_data.get(time_key, 0.0)) or 0.0
                )
                edge_data[time_key] = base
                edge_data[f"{mode}_allowed"] = bool(
                    edge_data.get(
                        f"{mode}_base_allowed", edge_data.get(f"{mode}_allowed", True)
                    )
                )

                if "weights" in edge_data:
                    edge_data["weights"][mode] = base
                if "constraints" in edge_data:
                    edge_data["constraints"][f"{mode}_allowed"] = bool(
                        edge_data.get(f"{mode}_allowed", True)
                    )

    def _reset_all_edges_to_base(self, graph):
        for _u, _v, _k, edge_data in graph.edges(keys=True, data=True):
            for mode in settings.vehicle_types.keys():
                base_key = f"{mode}_base_travel_time"
                time_key = f"{mode}_travel_time"
                base = float(
                    edge_data.get(base_key, edge_data.get(time_key, 0.0)) or 0.0
                )
                edge_data[time_key] = base
                edge_data[f"{mode}_allowed"] = bool(
                    edge_data.get(
                        f"{mode}_base_allowed", edge_data.get(f"{mode}_allowed", True)
                    )
                )

                if "weights" in edge_data:
                    edge_data["weights"][mode] = base
                if "constraints" in edge_data:
                    edge_data["constraints"][f"{mode}_allowed"] = bool(
                        edge_data.get(f"{mode}_allowed", True)
                    )

    def _normalize_mode(self, mode: str) -> str:
        if mode == "bus":
            return "transit"
        return mode

    def _normalize_dt(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _resolve_graph_edge_nodes(self, edge_id: str):
        """Resolve an edge id like 'u->v' into graph-native node IDs (int/str/etc.)."""
        graph = graph_service.get_graph()
        if graph is None:
            return None

        cached = self._edge_resolve_cache.get(edge_id)
        if cached is not None:
            source, target = cached
            if graph.has_edge(source, target):
                return cached

        parts = edge_id.split("->")
        if len(parts) != 2:
            return None

        src_token = parts[0].strip()
        dst_token = parts[1].strip()

        source_candidates = self._candidate_node_ids(graph, src_token)
        target_candidates = self._candidate_node_ids(graph, dst_token)

        for source in source_candidates:
            for target in target_candidates:
                if graph.has_edge(source, target):
                    self._edge_resolve_cache[edge_id] = (source, target)
                    if len(self._edge_resolve_cache) > self._edge_resolve_cache_max:
                        self._edge_resolve_cache.pop(
                            next(iter(self._edge_resolve_cache))
                        )
                    return source, target

        self._edge_resolve_cache[edge_id] = None
        if len(self._edge_resolve_cache) > self._edge_resolve_cache_max:
            self._edge_resolve_cache.pop(next(iter(self._edge_resolve_cache)))
        return None

    def _candidate_node_ids(self, graph, token: str):
        candidates = [token]

        try:
            candidates.append(int(token))
        except (TypeError, ValueError):
            pass

        # Fallback match against existing node IDs string representation.
        for node_id in graph.nodes:
            if str(node_id) == token:
                candidates.append(node_id)
                break

        # Deduplicate while preserving order.
        return list(dict.fromkeys(candidates))

    def _expand_bidirectional_edge_ids(self, edge_ids: list[str]) -> list[str]:
        """Include reverse direction edge IDs when they exist in graph."""
        graph = graph_service.get_graph()
        if graph is None:
            return edge_ids

        expanded: list[str] = []
        for edge_id in edge_ids:
            expanded.append(edge_id)

            resolved = self._resolve_graph_edge_nodes(edge_id)
            if not resolved:
                continue

            source, target = resolved
            if graph.has_edge(target, source):
                expanded.append(f"{target}->{source}")

        return list(dict.fromkeys(expanded))

    # ─── Expiry/Window reconciliation is handled by sync_active_effects ─


# ─── Singleton Instance ──────────────────────────────────────────
anomaly_service = AnomalyService()
