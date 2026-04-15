import networkx as nx

from config import settings
from services.graph_service import GraphService


def _build_sample_graph():
    g = nx.MultiDiGraph()
    g.add_node("a", x=90.4125, y=23.8103)
    g.add_node("b", x=90.4130, y=23.8107)
    g.add_node("c", x=90.4135, y=23.8110)

    # Residential edge should be allowed for car, bike, and walk in config.
    g.add_edge("a", "b", key=0, length=100.0, highway="residential", speed_kph=20.0)
    # Motorway edge is typically disallowed for walk and bike in config.
    g.add_edge("b", "c", key=0, length=140.0, highway="motorway", speed_kph=50.0)
    return g


def test_graph_loads_with_nodes_edges_and_vehicle_attributes(monkeypatch):
    service = GraphService()

    graph = _build_sample_graph()

    monkeypatch.setattr("services.graph_service.ox.graph_from_place", lambda *args, **kwargs: graph)
    monkeypatch.setattr("services.graph_service.ox.add_edge_speeds", lambda g: g)
    monkeypatch.setattr("services.graph_service.ox.add_edge_travel_times", lambda g: g)

    service.load_graph("Test City")

    assert service.is_loaded() is True
    assert service.node_count() == 3
    assert service.edge_count() == 2

    edge_data = service._graph["a"]["b"][0]
    assert edge_data["road_type"] == "residential"
    assert "base_travel_time" in edge_data
    assert "anomaly_multiplier" in edge_data
    assert "mode_travel_time_s" in edge_data

    for mode in settings.vehicle_types.keys():
        assert f"{mode}_allowed" in edge_data


def test_subgraph_filters_edges_by_vehicle_permissions():
    service = GraphService()
    service._graph = _build_sample_graph()
    service._annotate_graph_edges()
    service._loaded = True

    walk_subgraph = service.get_subgraph_for_mode("walk")
    car_subgraph = service.get_subgraph_for_mode("car")

    walk_edges = list(walk_subgraph.edges(data=True, keys=True))
    car_edges = list(car_subgraph.edges(data=True, keys=True))

    # Walk should avoid motorway and keep residential edge.
    assert len(walk_edges) == 1
    assert walk_edges[0][0] == "a" and walk_edges[0][1] == "b"

    # Car should keep both edges for this sample config.
    assert len(car_edges) == 2
