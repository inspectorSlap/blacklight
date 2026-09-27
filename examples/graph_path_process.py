#!/usr/bin/env python3
"""Standalone synthetic shortest-path target for Blacklight examples only."""
import heapq
import json
import sys


def solve(graph):
    adjacency = {vertex: [] for vertex in graph["vertices"]}
    for edge in graph["edges"]:
        adjacency[edge["from"]].append((edge["to"], edge["weight"]))
    costs = {graph["source"]: 0}
    queue = [(0, graph["source"])]
    while queue:
        cost, vertex = heapq.heappop(queue)
        if costs.get(vertex) != cost:
            continue
        if vertex == graph["target"]:
            return {"distance": cost}
        for neighbor, weight in adjacency[vertex]:
            proposed = cost + weight
            if neighbor not in costs or proposed < costs[neighbor]:
                costs[neighbor] = proposed
                heapq.heappush(queue, (proposed, neighbor))
    return {"distance": None}


request = json.load(sys.stdin)
json.dump({"target_id": "toy-graph-v1", "output": solve(request["input"])}, sys.stdout)
