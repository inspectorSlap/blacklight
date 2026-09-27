"""Exact contract oracle, independent of the reference implementation."""


def transform(payload):
    if not isinstance(payload, dict) or set(payload) != {"records", "minimum"}:
        raise ValueError("expected records and minimum")
    records, minimum = payload["records"], payload["minimum"]
    if not isinstance(records, list) or type(minimum) is not int:
        raise ValueError("invalid records or minimum")
    if any(not isinstance(r, dict) or set(r) != {"id", "value"}
           or not isinstance(r["id"], str) or not r["id"]
           or type(r["value"]) is not int for r in records):
        raise ValueError("invalid record")
    selected = [r for r in records if r["value"] >= minimum]
    return {"ids": [r["id"] for r in selected],
            "total": sum(r["value"] for r in selected),
            "count": len(selected)}
