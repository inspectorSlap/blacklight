"""Independent clean implementation: priority-queue Dijkstra search."""
import heapq
from .schema import validate


def solve(graph):
    validate(graph)
    adjacency = {vertex: [] for vertex in graph["vertices"]}
    for edge in graph["edges"]:
        adjacency[edge["from"]].append((edge["weight"], edge["to"]))
    best = {graph["source"]: 0}
    pending = [(0, graph["source"])]
    while pending:
        cost, vertex = heapq.heappop(pending)
        if best.get(vertex) != cost:
            continue
        if vertex == graph["target"]:
            return {"distance": cost}
        for weight, neighbor in adjacency[vertex]:
            candidate = cost + weight
            if neighbor not in best or candidate < best[neighbor]:
                best[neighbor] = candidate
                heapq.heappush(pending, (candidate, neighbor))
    return {"distance": None}
