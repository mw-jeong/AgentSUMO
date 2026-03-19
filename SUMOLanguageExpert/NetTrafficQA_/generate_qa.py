#!/usr/bin/env python3
"""
Generate QA pairs for different tasks in NetTrafficQA.
Tasks:
- feature_retrieval: "What is the id of the from-junction for the edge with id {edge}?"
- pathfinding: "What are the edge id(s) that come immediately after the edge with id {edge}?"
- network_comprehension: "List the junctions where the number of lanes decreases when moving from one edge to another."

Based on: sumolib and network files in grid_experiment
"""

import sys
import csv
import random
import argparse
import heapq
from pathlib import Path
from collections import defaultdict

import sumolib

# Setup paths
ROOT_DIR = Path(__file__).parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import utils

QA_ROOT = ROOT_DIR / "QAdataset"

def load_network(network_name):
    net_path = utils.XML_FILES[network_name]
    print(f"Loading network: {net_path}")
    return sumolib.net.readNet(str(net_path))

def generate_feature_retrieval(net, network_name, n=10):
    """
    Generate various feature retrieval questions.
    """
    edges = [e for e in net.getEdges() if not e.getID().startswith(":")]
    sampled_edges = random.sample(edges, min(n, len(edges)))
    
    qa_pairs = []
    for edge in sampled_edges:
        eid = edge.getID()
        from_id = edge.getFromNode().getID()
        to_id = edge.getToNode().getID()
        
        # 1. From-junction
        qa_pairs.append({
            "network": network_name,
            "type": "from_junction",
            "edge_id": eid,
            "question": f"What is the id of the from-junction for the edge with id {eid}? Please answer with the junction ID only.",
            "ground_truth": from_id
        })
        
        # 2. To-junction
        qa_pairs.append({
            "network": network_name,
            "type": "to_junction",
            "edge_id": eid,
            "question": f"What is the id of the to-junction for the edge with id {eid}? Please answer with the junction ID only.",
            "ground_truth": to_id
        })

        # 3. Both junctions
        qa_pairs.append({
            "network": network_name,
            "type": "both_junctions",
            "edge_id": eid,
            "question": f"What are the id of the from-junction and to-junction for the edge with id {eid}? Please provide the two IDs separated by a comma only.",
            "ground_truth": f"{from_id}, {to_id}"
        })

        # 4. Highway check
        highway_types = {"highway", "motorway", "trunk", "primary", "secondary"}
        is_highway = any(t in edge.getType().lower() for t in highway_types)
        qa_pairs.append({
            "network": network_name,
            "type": "is_highway",
            "edge_id": eid,
            "question": f"Is the edge with id {eid} a highway? Please answer with yes or no.",
            "ground_truth": "yes" if is_highway else "no"
        })

        # 5. Road type
        qa_pairs.append({
            "network": network_name,
            "type": "road_type",
            "edge_id": eid,
            "question": f"What is the road type of the edge with id {eid}? Please answer with the type string only.",
            "ground_truth": edge.getType()
        })
        
        # 6. Number of lanes
        qa_pairs.append({
            "network": network_name,
            "type": "num_lanes",
            "edge_id": eid,
            "question": f"How many lanes does the edge with id {eid} have? Please answer with the number only.",
            "ground_truth": str(edge.getLaneNumber())
        })

        # 7. Connected edges (before and after)
        incoming = sorted([e.getID() for e in edge.getIncoming() if not e.getID().startswith(":")])
        outgoing = sorted([e.getID() for e in edge.getOutgoing() if not e.getID().startswith(":")])
        qa_pairs.append({
            "network": network_name,
            "type": "connected_edges",
            "edge_id": eid,
            "question": f"Which edges are connected before and after the edge with id {eid}? Please follow the format: 'Before: {{ids}}; After: {{ids}}'.",
            "ground_truth": f"Before: {', '.join(incoming) if incoming else 'None'}; After: {', '.join(outgoing) if outgoing else 'None'}"
        })

    # 8. Junction coordinates
    nodes = [n for n in net.getNodes() if not n.getID().startswith(":")]
    sampled_nodes = random.sample(nodes, min(n, len(nodes)))
    for node in sampled_nodes:
        nid = node.getID()
        coord = node.getCoord()
        qa_pairs.append({
            "network": network_name,
            "type": "junction_coord",
            "edge_id": nid, # Using edge_id column for junction_id for simplicity in CSV structure
            "question": f"What are the x, y coordinates of the junction with id {nid}? Please provide the coordinates as 'x, y' only.",
            "ground_truth": f"{round(coord[0], 2)}, {round(coord[1], 2)}"
        })
        
    return qa_pairs

def generate_network_comprehension(net, network_name):
    """
    Generate various network-wide comprehension questions.
    """
    qa_pairs = []
    
    # 1, 2. Lane changes
    decreasing_junctions = set()
    increasing_junctions = set()
    for node in net.getNodes():
        for i in node.getIncoming():
            if i.getID().startswith(":"): continue
            for o in node.getOutgoing():
                if o.getID().startswith(":"): continue
                if o.getLaneNumber() < i.getLaneNumber():
                    decreasing_junctions.add(node.getID())
                elif o.getLaneNumber() > i.getLaneNumber():
                    increasing_junctions.add(node.getID())
    
    qa_pairs.append({
        "network": network_name, "type": "lane_decrease",
        "question": "List the junctions where the number of lanes decreases when moving from one edge to another (e.g., from an incoming edge to an outgoing edge at that junction). Please provide the junction IDs separated by commas, or 'None'.",
        "ground_truth": ", ".join(sorted(list(decreasing_junctions))) if decreasing_junctions else "None"
    })
    qa_pairs.append({
        "network": network_name, "type": "lane_increase",
        "question": "List the junctions where the number of lanes increases when moving from one edge to another. Please provide the junction IDs separated by commas, or 'None'.",
        "ground_truth": ", ".join(sorted(list(increasing_junctions))) if increasing_junctions else "None"
    })

    # 3, 4, 5, 8. Highway concepts (Entrance/Exit)
    highway_types = {"highway", "motorway", "trunk", "primary"}
    def is_h(e): return any(t in e.getType().lower() for t in highway_types)

    entrances = []
    exits = []
    for edge in net.getEdges():
        if edge.getID().startswith(":"): continue
        # Entrance: not highway -> is highway
        if is_h(edge):
            if any(not is_h(i) for i in edge.getIncoming() if not i.getID().startswith(":")):
                entrances.append(edge.getID())
        # Exit: is highway -> not highway
        if is_h(edge):
            if any(not is_h(o) for o in edge.getOutgoing() if not o.getID().startswith(":")):
                exits.append(edge.getID())

    qa_pairs.append({
        "network": network_name, "type": "highway_entrances",
        "question": "Considering the entire network, which edges can be regarded as highway entrances (i.e., highway edges that have non-highway incoming edges)?",
        "ground_truth": ", ".join(sorted(entrances)) if entrances else "None"
    })
    qa_pairs.append({
        "network": network_name, "type": "highway_exits",
        "question": "Considering the entire network, which edges can be regarded as highway exits (i.e., highway edges that lead to non-highway outgoing edges)?",
        "ground_truth": ", ".join(sorted(exits)) if exits else "None"
    })
    qa_pairs.append({
        "network": network_name, "type": "num_highway_entrances",
        "question": "How many highway entrance edges are there in the network?",
        "ground_truth": str(len(entrances))
    })
    qa_pairs.append({
        "network": network_name, "type": "ramp_metering_potential",
        "question": "List the edges where ramp metering could potentially be installed on the highway (typically at highway entrances).",
        "ground_truth": ", ".join(sorted(entrances)) if entrances else "None"
    })

    # 7. Speed limit changes
    speed_changes = []
    for node in net.getNodes():
        for i in node.getIncoming():
            if i.getID().startswith(":"): continue
            for o in node.getOutgoing():
                if o.getID().startswith(":"): continue
                if abs(o.getSpeed() - i.getSpeed()) > 0.01:
                    speed_changes.append(f"({i.getID()}, {o.getID()})")
    
    qa_pairs.append({
        "network": network_name, "type": "speed_limit_changes",
        "question": "List the edge pairs (E1, E2) where the road speed limit changes when moving from one edge to another at a junction. Please provide the pairs separated by commas, or 'None'.",
        "ground_truth": ", ".join(sorted(list(set(speed_changes)))) if speed_changes else "None"
    })

    # 9, 10. EB/WB Highways
    eb_h = []
    wb_h = []
    for edge in net.getEdges():
        if edge.getID().startswith(":") or not is_h(edge): continue
        from_x = edge.getFromNode().getCoord()[0]
        to_x = edge.getToNode().getCoord()[0]
        if to_x > from_x + 10: eb_h.append(edge.getID())
        elif to_x < from_x - 10: wb_h.append(edge.getID())

    qa_pairs.append({
        "network": network_name, "type": "wb_highways",
        "question": "List the edges that can be considered as westbound (leftward) highways. Please provide the edge IDs separated by commas, or 'None'.",
        "ground_truth": ", ".join(sorted(wb_h)) if wb_h else "None"
    })
    qa_pairs.append({
        "network": network_name, "type": "eb_highways",
        "question": "List the edges that can be considered as eastbound (rightward) highways. Please provide the edge IDs separated by commas, or 'None'.",
        "ground_truth": ", ".join(sorted(eb_h)) if eb_h else "None"
    })

    # 11, 12. Source/Sink and O-D pairs
    sources = [n.getID() for n in net.getNodes() if len(n.getIncoming()) == 0 and len(n.getOutgoing()) > 0]
    sinks = [n.getID() for n in net.getNodes() if len(n.getOutgoing()) == 0 and len(n.getIncoming()) > 0]
    
    qa_pairs.append({
        "network": network_name, "type": "source_sink_junctions",
        "question": "List the junctions that can be considered as source and sink for vehicle generation based on the terminal ends of roads (no incoming or no outgoing edges). Please follow the format: 'Sources: {{ids}}; Sinks: {{ids}}'.",
        "ground_truth": f"Sources: {', '.join(sorted(sources)) if sources else 'None'}; Sinks: {', '.join(sorted(sinks)) if sinks else 'None'}"
    })
    qa_pairs.append({
        "network": network_name, "type": "od_pairs_count",
        "question": "How many possible origin-destination (O-D) pairs can be formed based on the identified source and sink junctions? Please answer with the number only.",
        "ground_truth": str(len(sources) * len(sinks))
    })

    return qa_pairs

def generate_pathfinding(net, network_name, n=10):
    """
    Generate various pathfinding questions.
    """
    edges = [e for e in net.getEdges() if not e.getID().startswith(":")]
    nodes = [n for n in net.getNodes() if not n.getID().startswith(":")]
    qa_pairs = []

    # 1. Immediate Successors (already exists in some form)
    sampled_edges = random.sample(edges, min(n, len(edges)))
    for edge in sampled_edges:
        eid = edge.getID()
        successors = sorted([e.getID() for e in edge.getOutgoing() if not e.getID().startswith(":")])
        qa_pairs.append({
            "network": network_name,
            "type": "immediate_successors",
            "edge_id": eid,
            "question": f"What are the edge id(s) that come immediately after the edge with id {eid}? Please provide the IDs separated by commas, or 'None'.",
            "ground_truth": ", ".join(successors) if successors else "None"
        })

    # 2. Immediate Predecessors
    sampled_edges_pre = random.sample(edges, min(n, len(edges)))
    for edge in sampled_edges_pre:
        eid = edge.getID()
        predecessors = sorted([e.getID() for e in edge.getIncoming() if not e.getID().startswith(":")])
        qa_pairs.append({
            "network": network_name,
            "type": "immediate_predecessors",
            "edge_id": eid,
            "question": f"What are the edge id(s) that can come immediately before the edge with id {eid}? Please provide the IDs separated by commas, or 'None'.",
            "ground_truth": ", ".join(predecessors) if predecessors else "None"
        })

    # Dijkstra helper
    def get_path_info(net, start_id, end_id, avoid_edge=None):
        pq = [(0, start_id, [], [start_id])] # (dist, curr_node, edges, nodes)
        visited = {}
        while pq:
            d, curr, path_e, path_n = heapq.heappop(pq)
            if curr in visited and visited[curr] <= d: continue
            visited[curr] = d
            if curr == end_id: return d, path_e, path_n
            node = net.getNode(curr)
            for out_edge in node.getOutgoing():
                if out_edge.getID().startswith(":"): continue
                if out_edge.getID() == avoid_edge: continue
                target = out_edge.getToNode().getID()
                heapq.heappush(pq, (d + out_edge.getLength(), target, path_e + [out_edge.getID()], path_n + [target]))
        return None, None, None

    # 3, 4, 5. Shortest path (edges, edges+nodes, distance)
    attempts = 0
    while len([q for q in qa_pairs if q["type"] == "shortest_path_edges"]) < n and attempts < n * 5:
        attempts += 1
        n1, n2 = random.sample(nodes, 2)
        d, pe, pn = get_path_info(net, n1.getID(), n2.getID())
        if d is not None and len(pe) > 1:
            n1id, n2id = n1.getID(), n2.getID()
            # 3. Path edges
            qa_pairs.append({
                "network": network_name,
                "type": "shortest_path_edges",
                "question": f"What is the shortest path from junction {n1id} to junction {n2id}? List the edges in order, separated by ' -> '.",
                "ground_truth": " -> ".join(pe)
            })
            # 4. Path edges and junctions
            full_path = []
            for i in range(len(pe)):
                full_path.append(pn[i])
                full_path.append(pe[i])
            full_path.append(pn[-1])
            qa_pairs.append({
                "network": network_name,
                "type": "shortest_path_full",
                "question": f"What is the shortest path from junction {n1id} to junction {n2id}? List the edges and junctions in order.",
                "ground_truth": " -> ".join(full_path)
            })
            # 5. Distance by length
            qa_pairs.append({
                "network": network_name,
                "type": "shortest_path_length",
                "question": f"What is the shortest path distance (by length in meters) from junction {n1id} to junction {n2id}?",
                "ground_truth": str(round(d, 2))
            })

    # 6. Path with edge removal
    attempts = 0
    while len([q for q in qa_pairs if q["type"] == "shortest_path_edge_removal"]) < n and attempts < n * 5:
        attempts += 1
        n1, n2 = random.sample(nodes, 2)
        d, pe, pn = get_path_info(net, n1.getID(), n2.getID())
        if d is not None and len(pe) > 2:
            removed_edge = random.choice(pe)
            d2, pe2, pn2 = get_path_info(net, n1.getID(), n2.getID(), avoid_edge=removed_edge)
            if d2 is not None:
                qa_pairs.append({
                    "network": network_name,
                    "type": "shortest_path_edge_removal",
                    "question": f"Assuming edge {removed_edge} is removed, what is the shortest path from junction {n1.getID()} to junction {n2.getID()}? List the edges in order.",
                    "ground_truth": " -> ".join(pe2)
                })

    return qa_pairs

def write_csv(filename, fieldnames, rows):
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Generate QA pairs for NetTrafficQA.")
    parser.add_argument("--network", choices=["grid_11x11", "random", "all"], default="all",
                        help="Network to generate questions for")
    parser.add_argument("--category", choices=["feature_retrieval", "pathfinding", "network_comprehension", "all"], default="all",
                        help="QA category to generate")
    parser.add_argument("--n", type=int, default=10, help="Number of samples to generate per question type")
    args = parser.parse_args()

    random.seed(42)
    networks = ["grid_11x11", "random"] if args.network == "all" else [args.network]
    
    for network_name in networks:
        net = load_network(network_name)
        
        feature_retrieval = []
        pathfinding = []
        network_comprehension = []

        if args.category in ["feature_retrieval", "all"]:
            feature_retrieval = generate_feature_retrieval(net, network_name, n=args.n)
        
        if args.category in ["pathfinding", "all"]:
            pathfinding = generate_pathfinding(net, network_name, n=args.n)
            
        if args.category in ["network_comprehension", "all"]:
            # Note: comprehension currently finds all instances (no sampling applied yet)
            network_comprehension = generate_network_comprehension(net, network_name)

        # Write feature_retrieval
        if feature_retrieval:
            by_type = defaultdict(list)
            for row in feature_retrieval: by_type[row["type"]].append(row)
            for qtype, rows in by_type.items():
                write_csv(
                    QA_ROOT / "feature_retrieval" / "questions" / f"{network_name}_{qtype}.csv",
                    ["network", "type", "edge_id", "question", "ground_truth"],
                    rows
                )
        
        # Write pathfinding
        if pathfinding:
            by_type = defaultdict(list)
            for row in pathfinding: by_type[row["type"]].append(row)
            for qtype, rows in by_type.items():
                # Get fieldnames from row keys
                fieldnames = list(rows[0].keys())
                write_csv(
                    QA_ROOT / "pathfinding" / "questions" / f"{network_name}_{qtype}.csv",
                    fieldnames,
                    rows
                )
        
        # Write network_comprehension
        if network_comprehension:
            by_type = defaultdict(list)
            for row in network_comprehension: by_type[row["type"]].append(row)
            for qtype, rows in by_type.items():
                write_csv(
                    QA_ROOT / "network_comprehension" / "questions" / f"{network_name}_{qtype}.csv",
                    ["network", "type", "question", "ground_truth"],
                    rows
                )

if __name__ == "__main__":
    main()
