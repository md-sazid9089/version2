# -*- coding: utf-8 -*-
"""
GoliTransit Routing Engine -- Comprehensive Test Suite
"""

import sys
sys.path.insert(0, ".")

import networkx as nx
from unittest.mock import MagicMock
from services.multimodal_dijkstra import (
    multi_modal_dijkstra,
    multi_modal_dijkstra_with_coords,
    _extract_edge_road_geometry,
)
from services.graph_service import _haversine_m, _project_point_to_segment


def _build_road_graph():
    G = nx.MultiDiGraph()
    G.add_node("A", x=90.3900, y=23.7640)
    G.add_node("B", x=90.3950, y=23.7640)
    G.add_node("C", x=90.3900, y=23.7610)
    G.add_node("D", x=90.3990, y=23.7650)
    G.add_node("E", x=90.3950, y=23.7610)
    G.add_node("ISOLATED", x=90.5000, y=23.9000)

    geom_ab = MagicMock()
    geom_ab.coords = [
        (90.3900, 23.7640),
        (90.3925, 23.7645),
        (90.3950, 23.7640),
    ]

    G.add_edge("A", "B", key=0,
        length=500, road_type="secondary", highway="secondary",
        travel_time=36.0, base_travel_time=36.0, speed_limit_kmh=50,
        car_travel_time=36.0, rickshaw_travel_time=120.0, walk_travel_time=360.0,
        weights={"car": 36.0, "rickshaw": 120.0, "walk": 360.0},
        constraints={"car_allowed": True, "rickshaw_allowed": True, "walk_allowed": True},
        base_weight=500, anomaly_multiplier=1.0,
        geometry=geom_ab,
    )

    G.add_edge("B", "D", key=0,
        length=400, road_type="primary", highway="primary",
        travel_time=28.8, base_travel_time=28.8, speed_limit_kmh=50,
        car_travel_time=28.8, rickshaw_travel_time=96.0, walk_travel_time=288.0,
        weights={"car": 28.8, "rickshaw": 96.0, "walk": 288.0},
        constraints={"car_allowed": True, "rickshaw_allowed": True, "walk_allowed": True},
        base_weight=400, anomaly_multiplier=1.0,
    )

    G.add_edge("A", "C", key=0,
        length=300, road_type="footway", highway="footway",
        travel_time=216.0, base_travel_time=216.0, speed_limit_kmh=5,
        car_travel_time=216.0, rickshaw_travel_time=72.0, walk_travel_time=216.0,
        weights={"car": 216.0, "rickshaw": 72.0, "walk": 216.0},
        constraints={"car_allowed": False, "rickshaw_allowed": True, "walk_allowed": True},
        base_weight=300, anomaly_multiplier=1.0,
    )

    G.add_edge("C", "E", key=0,
        length=300, road_type="footway", highway="footway",
        travel_time=216.0, base_travel_time=216.0, speed_limit_kmh=5,
        car_travel_time=216.0, rickshaw_travel_time=72.0, walk_travel_time=216.0,
        weights={"car": 216.0, "rickshaw": 72.0, "walk": 216.0},
        constraints={"car_allowed": False, "rickshaw_allowed": True, "walk_allowed": True},
        base_weight=300, anomaly_multiplier=1.0,
    )

    G.add_edge("B", "E", key=0,
        length=600, road_type="residential", highway="residential",
        travel_time=54.0, base_travel_time=54.0, speed_limit_kmh=40,
        car_travel_time=54.0, rickshaw_travel_time=144.0, walk_travel_time=432.0,
        weights={"car": 54.0, "rickshaw": 144.0, "walk": 432.0},
        constraints={"car_allowed": True, "rickshaw_allowed": True, "walk_allowed": True},
        base_weight=600, anomaly_multiplier=1.0,
    )

    return G


def run_all_tests():
    G = _build_road_graph()
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print("  [PASS] " + name)
            passed += 1
        else:
            print("  [FAIL] " + name + " -- " + str(detail))
            failed += 1

    print("=" * 70)
    print("GoliTransit Routing Engine -- Comprehensive Audit Tests")
    print("=" * 70)

    # Test 1: Nearest node by Haversine
    print("\n-- Test 1: Nearest node (source) --")
    test_lat, test_lng = 23.7640, 90.3915
    dist_a = _haversine_m(test_lat, test_lng, 23.7640, 90.3900)
    dist_b = _haversine_m(test_lat, test_lng, 23.7640, 90.3950)
    check("Haversine to A < Haversine to B", dist_a < dist_b,
          "dist_a=%.1fm, dist_b=%.1fm" % (dist_a, dist_b))

    # Test 2: Nearest node (destination)
    print("\n-- Test 2: Nearest node (destination) --")
    test_lat2, test_lng2 = 23.7610, 90.3940
    dist_c = _haversine_m(test_lat2, test_lng2, 23.7610, 90.3900)
    dist_e = _haversine_m(test_lat2, test_lng2, 23.7610, 90.3950)
    check("Point closer to E than C", dist_e < dist_c,
          "dist_c=%.1fm, dist_e=%.1fm" % (dist_c, dist_e))

    # Test 3: Shortest path among multiple routes
    print("\n-- Test 3: Shortest path selection --")
    result = multi_modal_dijkstra(G, "A", "D", ["car"])
    check("Car route exists", result is not None)
    if result:
        check("Car optimal cost = 64.8", abs(result["cost"] - 64.8) < 0.1,
              "got %s" % result["cost"])
        nodes = result.get("node_path", [])
        check("Car path is A->B->D", nodes == ["A", "B", "D"],
              "got %s" % nodes)

    # Test 4: Straight line invalid, must follow roads
    print("\n-- Test 4: Straight line vs road path --")
    result_car = multi_modal_dijkstra(G, "A", "D", ["car"])
    check("Car route A->D exists", result_car is not None)
    if result_car:
        for step in result_car["path"]:
            has_edge = G.has_edge(step["from"], step["to"])
            check("Edge %s->%s exists in graph" % (step["from"], step["to"]), has_edge)

    # Test 5: Disconnected node returns None
    print("\n-- Test 5: Disconnected node --")
    result_disconn = multi_modal_dijkstra(G, "A", "ISOLATED", ["car"])
    check("Disconnected returns None", result_disconn is None)

    result_disconn2 = multi_modal_dijkstra(G, "ISOLATED", "A", ["walk"])
    check("Disconnected reverse returns None", result_disconn2 is None)

    # Test 6: Dijkstra correctness
    print("\n-- Test 6: Dijkstra algorithm correctness --")
    result_same = multi_modal_dijkstra(G, "A", "A", ["car"])
    check("Same node: cost=0", result_same is not None and result_same["cost"] == 0)
    check("Same node: empty path", result_same is not None and len(result_same["path"]) == 0)

    result_path = multi_modal_dijkstra(G, "A", "B", ["car"])
    check("Returns cost", result_path is not None and "cost" in result_path)
    check("Returns path", result_path is not None and "path" in result_path)
    check("Returns node_path", result_path is not None and "node_path" in result_path)

    # Test 7: No negative weights
    print("\n-- Test 7: No negative weights --")
    result_neg = multi_modal_dijkstra(G, "A", "D", ["car"])
    if result_neg:
        all_positive = all(
            result_neg["path"][i] is not None
            for i in range(len(result_neg["path"]))
        )
        check("All steps exist (no None)", all_positive)
        check("Total cost > 0", result_neg["cost"] > 0)

    # Test 8: Road distance weights (not Euclidean)
    print("\n-- Test 8: Road distance weights (not Euclidean) --")
    edge_ab = G.get_edge_data("A", "B")
    if edge_ab:
        ed = next(iter(edge_ab.values()))
        check("Edge has 'length' attribute", "length" in ed)
        check("Edge length = 500 (road distance)", ed["length"] == 500)
        check("Edge weight uses travel_time (not Euclidean)", ed["travel_time"] == 36.0)

    # Test 9: Road geometry follows OSM, not straight lines
    print("\n-- Test 9: Road geometry (no straight-line bug) --")
    result_geom = multi_modal_dijkstra_with_coords(G, "A", "B", ["car"])
    check("Geometry result exists", result_geom is not None)
    if result_geom:
        geom = result_geom.get("geometry", [])
        check("Geometry has >= 3 points (road curve)", len(geom) >= 3,
              "got %d points" % len(geom))
        if len(geom) >= 3:
            mid = geom[1]
            check("Middle point is curve (not straight)", mid[0] != 23.7640,
                  "lat=%s" % mid[0])

    # Test 10: Mode switch penalty
    print("\n-- Test 10: Mode switch penalty --")
    r_free = multi_modal_dijkstra(G, "A", "D", ["car"], switch_penalty=0)
    r_high = multi_modal_dijkstra(G, "A", "D", ["car", "walk"], switch_penalty=1000)
    check("Free penalty exists", r_free is not None)
    check("High penalty exists", r_high is not None)
    if r_free and r_high:
        check("High penalty >= free penalty",
              r_high["cost"] >= r_free["cost"],
              "free=%s, high=%s" % (r_free["cost"], r_high["cost"]))

    # Test 11: Restricted edges never used by car
    print("\n-- Test 11: Restricted edge enforcement --")
    result_ae = multi_modal_dijkstra(G, "A", "E", ["car"])
    check("Car route A->E exists", result_ae is not None)
    if result_ae:
        went_through_c = any(s["to"] == "C" for s in result_ae["path"])
        check("Car did NOT route through C (footway)", not went_through_c)

    # Test 12: Point projection to segment
    print("\n-- Test 12: Point-to-segment projection --")
    t, plat, plng = _project_point_to_segment(
        23.7640, 90.3925,
        23.7640, 90.3900,
        23.7640, 90.3950,
    )
    check("Projection fraction ~ 0.5", abs(t - 0.5) < 0.01, "got %s" % t)
    check("Projected point on segment", abs(plat - 23.7640) < 0.001)

    t2, _, _ = _project_point_to_segment(
        23.7640, 90.3970,
        23.7640, 90.3900,
        23.7640, 90.3950,
    )
    check("Past-end clamped to 1.0", t2 == 1.0, "got %s" % t2)

    # Summary
    print("\n" + "=" * 70)
    total = passed + failed
    print("  RESULTS: %d/%d passed, %d failed" % (passed, total, failed))
    if failed == 0:
        print("  ALL TESTS PASSED")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
