"""Exact small-graph oracle: repeated edge relaxation (Bellman–Ford)."""
from .schema import validate


def solve(graph):
    validate(graph)
    distance = {vertex: None for vertex in graph["vertices"]}
    distance[graph["source"]] = 0
    for _ in range(len(graph["vertices"]) - 1):
        changed = False
        for edge in graph["edges"]:
            start = distance[edge["from"]]
            candidate = None if start is None else start + edge["weight"]
            current = distance[edge["to"]]
            if candidate is not None and (current is None or candidate < current):
                distance[edge["to"]] = candidate
                changed = True
        if not changed:
            break
    return {"distance": distance[graph["target"]]}
