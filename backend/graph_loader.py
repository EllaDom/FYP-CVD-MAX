import os
import json

BASE = "workspace/graphs/runtime"


def load_graph(graph_type):
    folder = os.path.join(BASE, graph_type)

    if not os.path.exists(folder):
        return None

    files = os.listdir(folder)
    if not files:
        return None

    graphs = []

    for file in files:
        path = os.path.join(folder, file)

        try:
            with open(path) as f:
                data = json.load(f)

                if isinstance(data, dict) and "edges" in data:
                    graphs.append(data)

        except Exception as e:
            print(f"Skipping invalid file {file}: {e}")

    return graphs if graphs else None