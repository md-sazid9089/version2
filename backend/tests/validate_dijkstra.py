"""Quick validation script for the multi-modal Dijkstra engine."""
import sys
sys.path.insert(0, ".")

import networkx as nx
from services.multimodal_dijkstra import multi_modal_dijkstra, multi_modal_dijkstra_with_coords


def build_test_graph():
    G = nx.MultiDiGraph()
    G.add_node("A", x=90.40, y=23.80)
    G.add_node("B", x=90.41, y=23.80)
    G.add_node("C", x=90.40, y=23.81)
    G.add_node("D", x=90.41, y=23.81)

    # A->B: car+walk+rickshaw
    G.add_edge("A", "B", key=0,
        weights={"car": 10, "walk": 25, "rickshaw": 15},
        constraints={"car_allowed": True, "walk_allowed": True, "rickshaw_allowed": True},
        travel_time=10, length=500)

    # B->D: car+walk+rickshaw
    G.add_edge("B", "D", key=0,
        weights={"car": 10, "walk": 25, "rickshaw": 15},
        constraints={"car_allowed": True, "walk_allowed": True, "rickshaw_allowed": True},
        travel_time=10, length=500)

    # A->C: walk+rickshaw only (footway, car blocked)
    G.add_edge("A", "C", key=0,
        weights={"car": 15, "walk": 15, "rickshaw": 15},
        constraints={"car_allowed": False, "walk_allowed": True, "rickshaw_allowed": True},
        travel_time=15, length=300)

    # C->D: walk+rickshaw only (footway, car blocked)
    G.add_edge("C", "D", key=0,
        weights={"car": 15, "walk": 15, "rickshaw": 15},
        constraints={"car_allowed": False, "walk_allowed": True, "rickshaw_allowed": True},
        travel_time=15, length=300)

    return G


def test_all():
    G = build_test_graph()
    passed = 0
    failed = 0

    # Test 1: Car-only finds shortest car path
    r = multi_modal_dijkstra(G, "A", "D", ["car"])
    assert r is not None, "FAIL: car route should exist"
    assert r["cost"] == 20, f"FAIL: car cost should be 20, got {r['cost']}"
    assert all(s["mode"] == "car" for s in r["path"]), "FAIL: all steps should be car"
    print(f"  [PASS] Test 1: Car-only route, cost={r['cost']}")
    passed += 1

    # Test 2: Walk-only finds shortest walk path
    r = multi_modal_dijkstra(G, "A", "D", ["walk"])
    assert r is not None
    assert r["cost"] == 30, f"FAIL: walk cost should be 30, got {r['cost']}"
    assert all(s["mode"] == "walk" for s in r["path"])
    print(f"  [PASS] Test 2: Walk-only route, cost={r['cost']}")
    passed += 1

    # Test 3: Car never routes through restricted edges
    r = multi_modal_dijkstra(G, "A", "D", ["car"])
    for step in r["path"]:
        assert not (step["from"] == "A" and step["to"] == "C"), "FAIL: car used restricted edge"
    print(f"  [PASS] Test 3: Car respects restricted edges")
    passed += 1

    # Test 4: Mode switch penalty is applied
    r_free = multi_modal_dijkstra(G, "A", "D", ["car"], switch_penalty=0)
    r_high = multi_modal_dijkstra(G, "A", "D", ["car", "walk"], switch_penalty=100)
    assert r_high["cost"] >= r_free["cost"]
    print(f"  [PASS] Test 4: Mode switch penalty (free={r_free['cost']}, high={r_high['cost']})")
    passed += 1

    # Test 5: No path returns None
    G2 = nx.MultiDiGraph()
    G2.add_node("X")
    G2.add_node("Y")
    r = multi_modal_dijkstra(G2, "X", "Y", ["car"])
    assert r is None, "FAIL: should return None for no path"
    print(f"  [PASS] Test 5: No path returns None")
    passed += 1

    # Test 6: Same start/end returns zero cost
    r = multi_modal_dijkstra(G, "A", "A", ["car"])
    assert r is not None
    assert r["cost"] == 0
    assert len(r["path"]) == 0
    print(f"  [PASS] Test 6: Same node, cost=0")
    passed += 1

    # Test 7: Multi-modal finds optimal with zero penalty
    r = multi_modal_dijkstra(G, "A", "D", ["car", "walk", "rickshaw"], switch_penalty=0)
    assert r is not None
    assert r["cost"] == 20
    print(f"  [PASS] Test 7: Multi-modal optimal, cost={r['cost']}")
    passed += 1

    # Test 8: Coords version includes geometry
    r = multi_modal_dijkstra_with_coords(G, "A", "D", ["car"])
    assert r is not None
    assert "geometry" in r
    assert len(r["geometry"]) >= 2
    for step in r["path"]:
        assert "from_lat" in step and "to_lng" in step
    print(f"  [PASS] Test 8: Coords version has geometry ({len(r['geometry'])} points)")
    passed += 1

    # Test 9: Rickshaw can use both paths equally (both cost 30)
    r_rick = multi_modal_dijkstra(G, "A", "D", ["rickshaw"])
    assert r_rick is not None
    assert r_rick["cost"] == 30, f"FAIL: rickshaw cost should be 30, got {r_rick['cost']}"
    assert len(r_rick["path"]) == 2
    assert all(s["mode"] == "rickshaw" for s in r_rick["path"])
    # Rickshaw has access to BOTH paths (including footway), verify it found optimal
    print(f"  [PASS] Test 9: Rickshaw routing, cost={r_rick['cost']}, path={[(s['from'],s['to']) for s in r_rick['path']]}")
    passed += 1

    print(f"\n{'='*50}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*50}")

    return failed == 0


if __name__ == "__main__":
    print("Multi-Modal Dijkstra Engine — Validation Tests")
    print("=" * 50)
    success = test_all()
    sys.exit(0 if success else 1)
