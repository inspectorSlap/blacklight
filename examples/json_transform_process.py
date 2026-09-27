#!/usr/bin/env python3
"""Toy process target for the JSON transformation profile."""
import json
import sys


def transform(payload):
    chosen = []
    for row in payload["records"]:
        if row["value"] >= payload["minimum"]:
            chosen.append(row)
    return {"ids": [row["id"] for row in chosen],
            "total": sum(row["value"] for row in chosen),
            "count": len(chosen)}


def main():
    request = json.load(sys.stdin)
    if request["profile"] != "json-transform-v1":
        raise ValueError("unsupported profile")
    json.dump({"target_id": "toy-json-v1", "output": transform(request["input"])}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
