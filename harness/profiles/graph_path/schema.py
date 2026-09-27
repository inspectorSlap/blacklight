"""Shared input shape; oracle and reference algorithms remain separate."""
import re


def validate(graph):
    if type(graph) is not dict or set(graph) != {"vertices", "edges", "source", "target"}:
        raise ValueError("graph must contain vertices, edges, source and target")
    vertices, edges = graph["vertices"], graph["edges"]
    if type(vertices) is not list or not 2 <= len(vertices) <= 12 \
            or any(type(v) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", v) for v in vertices) \
            or len(set(vertices)) != len(vertices):
        raise ValueError("vertices must be 2–12 unique short IDs")
    if graph["source"] not in vertices or graph["target"] not in vertices \
            or type(graph["source"]) is not str or type(graph["target"]) is not str:
        raise ValueError("source and target must be vertices")
    if type(edges) is not list or not 1 <= len(edges) <= 40:
        raise ValueError("edges must contain 1–40 directed links")
    for edge in edges:
        if type(edge) is not dict or set(edge) != {"from", "to", "weight"} \
                or type(edge["from"]) is not str or edge["from"] not in vertices \
                or type(edge["to"]) is not str or edge["to"] not in vertices \
                or type(edge["weight"]) is not int or not 0 <= edge["weight"] <= 100:
            raise ValueError("edge must have known endpoints and integer weight 0–100")
    return graph
