import os
import json
import re
from collections import defaultdict

# 🔥 CHANGE: point to your runtime graph folder
INPUT_ROOT = "workspace/graphs/runtime"
OUTPUT_ROOT = "workspace/graphs_simplified"

GRAPH_TYPES = ["ast", "cfg", "pdg"]


def load_graph(path):

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        text = text.replace("\0", "")
        text = text.replace("\x00", "")
        text = re.sub(r'\\+', r'\\\\', text)
        return json.loads(text)


def save_graph(graph, path):

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)


def simplify_graph(graph):

    nodes = graph["nodes"]
    edges = graph.get("edges", [])

    groups = defaultdict(list)

    for node in nodes:
        line = node.get("line", -1)
        groups[line].append(node)

    # Skip graphs with only one subblock
    if len(groups) <= 1:
        return graph, False

    new_nodes = []
    node_map = {}

    new_id = 0

    for line, group_nodes in groups.items():

        merged_label = "|".join(
            n.get("label", "") for n in group_nodes
        )

        merged_code = " <SEP> ".join(
            n.get("code", "") for n in group_nodes
        )

        supernode = {
            "id": new_id,
            "label": merged_label,
            "code": merged_code,
            "line": line
        }

        new_nodes.append(supernode)

        for n in group_nodes:
            node_map[n["id"]] = new_id

        new_id += 1

    new_edges = set()

    for edge in edges:

        src = node_map.get(edge["source"])
        dst = node_map.get(edge["target"])

        if src is None or dst is None:
            continue

        if src != dst:
            new_edges.add((src, dst, edge["type"]))

    edge_list = [
        {"source": s, "target": d, "type": t}
        for s, d, t in new_edges
    ]

    simplified_graph = {
        "method": graph.get("method"),
        "id": graph.get("id"),
        "nodes": new_nodes,
        "edges": edge_list
    }

    return simplified_graph, True


# 🔥 NEW: callable pipeline function
def run_simplification():

    print("\n===== GRAPH SIMPLIFICATION STARTED =====\n")

    total_files = 0
    simplified_count = 0

    for gtype in GRAPH_TYPES:

        print(f"\nProcessing GRAPH TYPE: {gtype}")

        input_dir = os.path.join(INPUT_ROOT, gtype)
        output_dir = os.path.join(OUTPUT_ROOT, gtype)

        if not os.path.exists(input_dir):
            print(f"Skipping {gtype} (no folder found)")
            continue

        os.makedirs(output_dir, exist_ok=True)

        files = [f for f in os.listdir(input_dir) if f.endswith(".json")]

        print(f"Graph Type: {gtype} | Files: {len(files)}")

        for i, fname in enumerate(files, 1):

            path = os.path.join(input_dir, fname)

            graph = load_graph(path)

            simplified, changed = simplify_graph(graph)

            save_graph(
                simplified,
                os.path.join(output_dir, fname)
            )

            if changed:
                simplified_count += 1

            if i % 50 == 0 or i == len(files):
                print(f"{i}/{len(files)} processed")

            total_files += 1

    print("\n===== SIMPLIFICATION COMPLETE =====")
    print("Total graphs processed:", total_files)
    print("Graphs simplified:", simplified_count)