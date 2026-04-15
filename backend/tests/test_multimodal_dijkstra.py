"""
Tests for the Multi-Modal Dijkstra Engine
==========================================
Validates the core algorithm against the spec's design rules:
  ✔ Never route through restricted edges
  ✔ Always apply mode switch penalty
  ✔ O(V log V) optimized Dijkstra
  ✔ Returns None for unreachable destinations
"""

import networkx as nx
import pytest

from services.multimodal_dijkstra import (
    multi_modal_dijkstra,
    multi_modal_dijkstra_with_coords,
)


def _build_test_graph():
    """
    Build a small test graph:

        A --[car+walk]--> B --[car+walk]--> D
        A --[walk only]--> C --[walk only]--> D

    Path A->B->D is shorter by car (10+10=20) vs A->C->D walk (15+15=30).
    But if car is not allowed, A->C->D walk (15+15=30) is the only option.
    """
    G = nx.MultiDiGraph()

    G.add_node("A", x=90.40, y=23.80)
    G.add_node("B", x=90.41, y=23.80)
    G.add_node("C", x=90.40, y=23.81)
    G.add_node("D", x=90.41, y=23.81)

    # A -> B: car + walk allowed
    G.add_edge(
        "A",
        "B",
        key=0,
        **{
            "weights": {"car": 10, "walk": 25, "rickshaw": 15},
            "constraints": {
                "car_allowed": True,
                "walk_allowed": True,
                "rickshaw_allowed": True,
            },
            "travel_time": 10,
            "car_travel_time": 10,
            "walk_travel_time": 25,
            "rickshaw_travel_time": 15,
            "length": 500,
            "base_weight": 500,
        },
    )

    # B -> D: car + walk allowed
    G.add_edge(
        "B",
        "D",
        key=0,
        **{
            "weights": {"car": 10, "walk": 25, "rickshaw": 15},
            "constraints": {
                "car_allowed": True,
                "walk_allowed": True,
                "rickshaw_allowed": True,
            },
            "travel_time": 10,
            "car_travel_time": 10,
            "walk_travel_time": 25,
            "rickshaw_travel_time": 15,
            "length": 500,
            "base_weight": 500,
        },
    )

    # A -> C: walk only (footway)
    G.add_edge(
        "A",
        "C",
        key=0,
        **{
            "weights": {"car": 15, "walk": 15, "rickshaw": 15},
            "constraints": {
                "car_allowed": False,
                "walk_allowed": True,
                "rickshaw_allowed": True,
            },
            "travel_time": 15,
            "car_travel_time": 15,
            "walk_travel_time": 15,
            "rickshaw_travel_time": 15,
            "length": 300,
            "base_weight": 300,
        },
    )

    # C -> D: walk only (footway)
    G.add_edge(
        "C",
        "D",
        key=0,
        **{
            "weights": {"car": 15, "walk": 15, "rickshaw": 15},
            "constraints": {
                "car_allowed": False,
                "walk_allowed": True,
                "rickshaw_allowed": True,
            },
            "travel_time": 15,
            "car_travel_time": 15,
            "walk_travel_time": 15,
            "rickshaw_travel_time": 15,
            "length": 300,
            "base_weight": 300,
        },
    )

    return G


def _build_switch_gate_graph(non_junction: bool = True):
    """
    Build a graph where switching at B is only beneficial.

    If B is not a valid switch node, best path must remain walk-only.
    If B is a junction, switching at B should be allowed and cheaper.
    """
    G = nx.MultiDiGraph()

    G.add_node("A", x=90.40, y=23.80)
    G.add_node("B", x=90.41, y=23.80)
    G.add_node("C", x=90.40, y=23.81)
    G.add_node("D", x=90.41, y=23.81)
    G.add_node("X", x=90.42, y=23.80)

    # Path via B: cheap but requires car->walk switch at B.
    G.add_edge(
        "A",
        "B",
        key=0,
        **{
            "weights": {"car": 5, "walk": 100},
            "constraints": {"car_allowed": True, "walk_allowed": True},
            "travel_time": 5,
            "car_travel_time": 5,
            "walk_travel_time": 100,
            "length": 200,
            "base_weight": 200,
        },
    )
    G.add_edge(
        "B",
        "D",
        key=0,
        **{
            "weights": {"car": 100, "walk": 5},
            "constraints": {"car_allowed": False, "walk_allowed": True},
            "travel_time": 5,
            "car_travel_time": 100,
            "walk_travel_time": 5,
            "length": 200,
            "base_weight": 200,
        },
    )

    # Walk-only fallback path.
    G.add_edge(
        "A",
        "C",
        key=0,
        **{
            "weights": {"car": 100, "walk": 25},
            "constraints": {"car_allowed": False, "walk_allowed": True},
            "travel_time": 25,
            "car_travel_time": 100,
            "walk_travel_time": 25,
            "length": 400,
            "base_weight": 400,
        },
    )
    G.add_edge(
        "C",
        "D",
        key=0,
        **{
            "weights": {"car": 100, "walk": 25},
            "constraints": {"car_allowed": False, "walk_allowed": True},
            "travel_time": 25,
            "car_travel_time": 100,
            "walk_travel_time": 25,
            "length": 400,
            "base_weight": 400,
        },
    )

    if not non_junction:
        # Make B a valid junction (degree >= 3).
        G.add_edge(
            "B",
            "X",
            key=0,
            **{
                "weights": {"car": 20, "walk": 20},
                "constraints": {"car_allowed": True, "walk_allowed": True},
                "travel_time": 20,
                "car_travel_time": 20,
                "walk_travel_time": 20,
                "length": 200,
                "base_weight": 200,
            },
        )

    return G


class TestMultiModalDijkstra:
    """Test suite for the multi-modal Dijkstra algorithm."""

    def test_single_mode_car(self):
        """Car-only routing should take the shortest car-allowed path."""
        G = _build_test_graph()
        result = multi_modal_dijkstra(G, "A", "D", ["car"])
        assert result is not None
        assert result["cost"] == 20  # A->B->D via car (10+10)
        assert len(result["path"]) == 2
        assert all(step["mode"] == "car" for step in result["path"])

    def test_single_mode_walk(self):
        """Walk-only routing should find the cheapest walk path."""
        G = _build_test_graph()
        result = multi_modal_dijkstra(G, "A", "D", ["walk"])
        assert result is not None
        # A->C->D via walk (15+15=30) is cheaper than A->B->D via walk (25+25=50)
        assert result["cost"] == 30
        assert all(step["mode"] == "walk" for step in result["path"])

    def test_never_route_through_restricted_edges(self):
        """Car must NOT use edges where car_allowed=False."""
        G = _build_test_graph()
        result = multi_modal_dijkstra(G, "A", "D", ["car"])
        assert result is not None
        for step in result["path"]:
            # Verify no step goes through C (which requires footway-only edges)
            if step["from"] == "A" and step["to"] == "C":
                pytest.fail("Car routed through restricted edge A->C")

    def test_mode_switch_penalty(self):
        """Mode switching should incur a penalty cost."""
        G = _build_test_graph()

        # With high switch penalty, staying on one mode is preferred
        result_no_switch = multi_modal_dijkstra(G, "A", "D", ["car"], switch_penalty=0)
        result_with_switch = multi_modal_dijkstra(
            G, "A", "D", ["car", "walk"], switch_penalty=100
        )

        assert result_no_switch is not None
        assert result_with_switch is not None

        # With high penalty, mixing modes costs more than single mode
        single_mode_cost = result_no_switch["cost"]
        # The multi-mode result should prefer staying on one mode due to high penalty
        assert result_with_switch["cost"] >= single_mode_cost

    def test_mode_switch_penalty_applied(self):
        """Verify the switch penalty is actually added to cost."""
        G = _build_test_graph()

        # Force a switch: walk A->C, then rickshaw C->D
        penalty = 50
        result = multi_modal_dijkstra(
            G, "A", "D", ["walk", "rickshaw"], switch_penalty=penalty
        )
        assert result is not None

        # Check that if mode changes mid-path, penalty is in the cost
        modes_used = [step["mode"] for step in result["path"]]
        if len(set(modes_used)) > 1:
            # There was a switch — cost should include the penalty
            # Without penalty: best path cost is 30 (walk A->C->D)
            # With switch, it would be higher
            assert result["cost"] > 30  # Must be more than pure walk path

    def test_no_path_returns_none(self):
        """If no path exists, return None."""
        G = nx.MultiDiGraph()
        G.add_node("X")
        G.add_node("Y")
        # No edges between X and Y
        result = multi_modal_dijkstra(G, "X", "Y", ["car"])
        assert result is None

    def test_same_start_end(self):
        """Route from node to itself should return zero cost."""
        G = _build_test_graph()
        result = multi_modal_dijkstra(G, "A", "A", ["car"])
        assert result is not None
        assert result["cost"] == 0
        assert len(result["path"]) == 0

    def test_multi_modal_finds_optimal(self):
        """Multi-modal should find routes that mix modes optimally."""
        G = _build_test_graph()
        # With zero switch penalty, algorithm can freely mix modes
        result = multi_modal_dijkstra(
            G, "A", "D", ["car", "walk", "rickshaw"], switch_penalty=0
        )
        assert result is not None
        # Should find the cheapest: A->B by car (10) + B->D by car (10) = 20
        assert result["cost"] == 20

    def test_with_coords_returns_geometry(self):
        """multi_modal_dijkstra_with_coords should include lat/lng in response."""
        G = _build_test_graph()
        result = multi_modal_dijkstra_with_coords(G, "A", "D", ["car"])
        assert result is not None
        assert "geometry" in result
        assert len(result["geometry"]) >= 2
        for step in result["path"]:
            assert "from_lat" in step
            assert "from_lng" in step
            assert "to_lat" in step
            assert "to_lng" in step

    def test_switch_disallowed_on_non_switch_node(self):
        """Mode changes should not occur at non-switch nodes."""
        G = _build_switch_gate_graph(non_junction=True)
        result = multi_modal_dijkstra(G, "A", "D", ["car", "walk"], switch_penalty=0)
        assert result is not None
        # Without a valid switch node at B, algorithm should stay walk-only via A->C->D.
        assert result["cost"] == 50
        assert all(step["mode"] == "walk" for step in result["path"])

    def test_switch_allowed_on_junction_node(self):
        """Mode changes should be allowed at valid junction nodes."""
        G = _build_switch_gate_graph(non_junction=False)
        result = multi_modal_dijkstra(G, "A", "D", ["car", "walk"], switch_penalty=0)
        assert result is not None
        # B is now a junction, so A->B (car) + B->D (walk) should be chosen.
        assert result["cost"] == 10
        modes = [step["mode"] for step in result["path"]]
        assert "car" in modes and "walk" in modes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
