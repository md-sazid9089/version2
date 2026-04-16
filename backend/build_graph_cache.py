#!/usr/bin/env python3
"""
Build Graph Cache Script
========================
Pre-builds and serializes the OSM graph for Dhaka.
Run this once locally, commit the .pkl file, and startup loads it instantly.

Usage:
  python build_graph_cache.py               # Rebuild for Dhaka
  python build_graph_cache.py --location "New York, USA"  # Other locations

Output:
  - Saves graph to: backend/data/osm_cache/dhaka_graph.pkl
  - Includes metadata: hash, build time, node/edge counts
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.osm_graph_builder import build_graph, print_graph_stats, save_graph_cache_pkl


def main():
    parser = argparse.ArgumentParser(description="Pre-build and cache OSM graph")
    parser.add_argument(
        "--location",
        default="Dhaka, Bangladesh",
        help="OSM location string (e.g., 'Dhaka, Bangladesh')"
    )
    parser.add_argument(
        "--output-dir",
        default="./data/osm_cache",
        help="Output directory for cached graph"
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Skip cache and re-download from OSM"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"Building Graph Cache")
    print(f"{'='*70}")
    print(f"Location: {args.location}")
    print(f"Output:   {output_dir.resolve()}")
    print(f"Force Download: {args.force_download}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'='*70}\n")
    
    # Build the graph
    start_time = time.time()
    print("[1/3] Building graph from OSM...")
    try:
        graph = build_graph(
            location=args.location,
            cache_dir=str(output_dir),
            force_download=args.force_download
        )
        build_time = time.time() - start_time
        print(f"✓ Graph built in {build_time:.2f}s")
    except Exception as e:
        print(f"✗ Failed to build graph: {e}")
        sys.exit(1)
    
    # Print stats
    print("\n[2/3] Graph Statistics:")
    print_graph_stats(graph)
    
    # Save to pickle (with metadata)
    print("[3/3] Serializing graph to pickle...")
    cache_start = time.time()
    try:
        cache_path = save_graph_cache_pkl(
            graph,
            location=args.location,
            output_dir=str(output_dir)
        )
        cache_time = time.time() - cache_start
        print(f"✓ Graph cached in {cache_time:.2f}s")
        
        # Get file size
        cache_file = Path(cache_path)
        file_size_mb = cache_file.stat().st_size / (1024 * 1024)
        
        print(f"\nCache file: {cache_file.name}")
        print(f"File size:  {file_size_mb:.2f} MB")
        print(f"Nodes:      {graph.number_of_nodes()}")
        print(f"Edges:      {graph.number_of_edges()}")
        
    except Exception as e:
        print(f"✗ Failed to cache graph: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"✓ SUCCESS! Cache ready for deployment.")
    print(f"Total time: {total_time:.2f}s")
    print(f"{'='*70}\n")
    print("Next steps:")
    print(f"  1. Commit {cache_file} to git")
    print(f"  2. Set environment: export USE_GRAPH_CACHE=1")
    print(f"  3. Restart backend - graph loads instantly!")


if __name__ == "__main__":
    main()
