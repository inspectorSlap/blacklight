"""Deliberately broken targets for named exact and relational checks."""
from collections import deque
from . import reference
from .schema import validate


def one_pass(graph):
    validate(graph)
    distance = {vertex: None for vertex in graph["vertices"]}
    distance[graph["source"]] = 0
    for edge in graph["edges"]:
        start = distance[edge["from"]]
        current = distance[edge["to"]]
        if start is not None and (current is None or start + edge["weight"] < current):
            distance[edge["to"]] = start + edge["weight"]
    return {"distance": distance[graph["target"]]}


def undirected(graph):
    validate(graph)
    changed = dict(graph)
    changed["edges"] = list(graph["edges"]) + [
        {"from": edge["to"], "to": edge["from"], "weight": edge["weight"]}
        for edge in graph["edges"]]
    return reference.solve(changed)


def unit_weights(graph):
    validate(graph)
    adjacency = {vertex: [] for vertex in graph["vertices"]}
    for edge in graph["edges"]:
        adjacency[edge["from"]].append(edge["to"])
    distances = {graph["source"]: 0}
    todo = deque([graph["source"]])
    while todo:
        vertex = todo.popleft()
        for neighbor in adjacency[vertex]:
            if neighbor not in distances:
                distances[neighbor] = distances[vertex] + 1
                todo.append(neighbor)
    return {"distance": distances.get(graph["target"])}


def isolated_penalty(graph):
    answer = reference.solve(graph)
    incident = {edge["from"] for edge in graph["edges"]} | {edge["to"] for edge in graph["edges"]}
    if answer["distance"] is not None and any(vertex not in incident for vertex in graph["vertices"]):
        return {"distance": answer["distance"] + 1}
    return answer


def clamped_weights(graph):
    validate(graph)
    changed = dict(graph)
    changed["edges"] = [dict(edge, weight=min(edge["weight"], 5)) for edge in graph["edges"]]
    return reference.solve(changed)


def unreachable_zero(graph):
    answer = reference.solve(graph)
    return {"distance": 0 if answer["distance"] is None else answer["distance"]}


REGISTRY = (
    ("single-relaxation-pass", "edge-order", one_pass),
    ("undirected-links", "reachability", undirected),
    ("unit-weight-search", "distance", unit_weights),
    ("isolated-vertex-penalty", "isolated-vertex", isolated_penalty),
    ("clamped-weights", "positive-scaling", clamped_weights),
    ("unreachable-is-zero", "reachability", unreachable_zero),
)
