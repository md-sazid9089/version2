#!/usr/bin/env python3
"""
OSM Graph Builder - Comprehensive Test Script
==============================================

Demonstrates the multi-modal road network graph extraction with:
  - Vehicle-specific attributes (car, rickshaw, walk, transit)
  - Road type classification (major, secondary, alleys)
  - Travel time calculations per vehicle mode
  - Shortest-path routing with NetworkX
  - Graph caching for offline use

Usage:
  python test_osm_graph.py
"""

import asyncio
from pathlib import Path
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.osm_graph_builder import build_graph, print_graph_stats
from services.graph_service import graph_service
from services.routing_engine import routing_engine
from models.route_models import RouteRequest, LatLng


async def test_graph_loading():
    """Test 1: Graph Loading & Statistics"""
    print("\n" + "="*70)
    print("TEST 1: Graph Loading & Statistics")
    print("="*70)
    
    graph = build_graph("Dhaka, Bangladesh")
    print_graph_stats(graph)
    
    return graph


async def test_vehicle_attributes(graph):
    """Test 2: Vehicle Attributes on Edges"""
    print("\n" + "="*70)
    print("TEST 2: Vehicle Attributes Demo")
    print("="*70)
    
    print("\nEdge Attributes for First 5 Edges:")
    print("-" * 70)
    
    for i, (u, v, k, data) in enumerate(graph.edges(keys=True, data=True)):
        if i >= 5:
            break
        
        print(f"\n{i+1}. {u} → {v}")
        print(f"   Highway Type: {data.get('highway', 'unknown')}")
        print(f"   Length: {data.get('length', 0):.0f}m")
        print(f"   Road Classification: {data.get('road_classification', 'unknown')}")
        print(f"   Vehicles Allowed:")
        
        for vehicle in ['car', 'rickshaw', 'walk', 'transit']:
            allowed = data.get(f'{vehicle}_allowed', False)
            symbol = "✅" if allowed else "❌"
            print(f"      {symbol} {vehicle}")
        
        travel_times = data.get('travel_time_per_mode', {})
        if travel_times:
            print(f"   Travel Times Per Mode:")
            for mode, time_s in travel_times.items():
                if time_s != float('inf'):
                    print(f"      • {mode}: {time_s:.1f}s")
                else:
                    print(f"      • {mode}: Not Allowed")


async def test_routing():
    """Test 3: Multi-Modal Routing"""
    print("\n" + "="*70)
    print("TEST 3: Multi-Modal Routing Examples")
    print("="*70)
    
    # Initialize graph service
    graph_service.load_graph()
    
    # Test different modes
    routes_to_test = [
        {
            "modes": ["car"],
            "origin": (23.8090, 90.4105),
            "destination": (23.8130, 90.4175),
        },
        {
            "modes": ["walk"],
            "origin": (23.8090, 90.4105),
            "destination": (23.8130, 90.4175),
        },
        {
            "modes": ["walk", "transit", "walk"],
            "origin": (23.8090, 90.4105),
            "destination": (23.8130, 90.4175),
        },
    ]
    
    for test_case in routes_to_test:
        modes = test_case["modes"]
        origin_lat, origin_lng = test_case["origin"]
        dest_lat, dest_lng = test_case["destination"]
        
        mode_str = " → ".join(modes)
        print(f"\n📍 Route: {mode_str}")
        print("-" * 70)
        
        try:
            request = RouteRequest(
                origin=LatLng(lat=origin_lat, lng=origin_lng),
                destination=LatLng(lat=dest_lat, lng=dest_lng),
                modes=modes,
                optimize="time",
                avoid_anomalies=True,
            )
            
            result = await routing_engine.compute(request)
            
            print(f"Distance: {result.total_distance_m:.0f} meters")
            print(f"Duration: {result.total_duration_s:.1f} seconds")
            print(f"Cost: ${result.total_cost:.2f}")
            print(f"Legs: {len(result.legs)}")
            print(f"Mode Switches: {len(result.mode_switches)}")
            
            # Print waypoints for first leg
            if result.legs:
                geo = result.legs[0].geometry
                print(f"First Leg Waypoints: {len(geo)}")
                for j, point in enumerate(geo[:3]):
                    print(f"  {j+1}. [{point.lat:.4f}, {point.lng:.4f}]")
                if len(geo) > 3:
                    print(f"  ... ({len(geo)-3} more waypoints)")
        
        except Exception as e:
            print(f"❌ Routing failed: {e}")


async def test_road_type_filtering():
    """Test 4: Road Type Filtering"""
    print("\n" + "="*70)
    print("TEST 4: Road Type Distribution")
    print("="*70)
    
    graph = build_graph("Dhaka, Bangladesh")
    
    road_types = {}
    for _, _, data in graph.edges(data=True):
        hw = data.get('highway', 'unknown')
        road_types[hw] = road_types.get(hw, 0) + 1
    
    print("\nRoad Types in Network:")
    for hw, count in sorted(road_types.items(), key=lambda x: x[1], reverse=True):
        classification = None
        if hw in {'motorway', 'trunk', 'primary', 'secondary'}:
            classification = "Major"
        elif hw in {'tertiary', 'unclassified'}:
            classification = "Secondary"
        else:
            classification = "Small/Alley"
        
        print(f"  • {hw:20} {count:3} edges  [{classification}]")
    
    # Vehicle coverage
    print("\nVehicle Coverage:")
    total_edges = graph.number_of_edges()
    
    for vehicle in ['car', 'rickshaw', 'walk', 'transit']:
        allowed_edges = sum(
            1 for _, _, d in graph.edges(data=True) 
            if d.get(f'{vehicle}_allowed', False)
        )
        percentage = (allowed_edges / total_edges * 100) if total_edges > 0 else 0
        print(f"  • {vehicle:15} {allowed_edges:3}/{total_edges} edges ({percentage:.1f}%)")


async def main():
    """Run all tests"""
    print("\n" + "█"*70)
    print("█ OSM GRAPH BUILDER - COMPREHENSIVE TEST SUITE")
    print("█"*70)
    
    # Test 1: Graph Loading
    graph = await test_graph_loading()
    
    # Test 2: Vehicle Attributes
    await test_vehicle_attributes(graph)
    
    # Test 3: Road Type Analysis
    await test_road_type_filtering()
    
    # Test 4: Routing
    await test_routing()
    
    print("\n" + "█"*70)
    print("█ ALL TESTS COMPLETED")
    print("█"*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
