"""Known broken transformations, each with a named owning check."""


def exclusive_boundary(payload):
    selected = [r for r in payload["records"] if r["value"] > payload["minimum"]]
    return {"ids": [r["id"] for r in selected], "total": sum(r["value"] for r in selected), "count": len(selected)}


def sorted_ids(payload):
    selected = [r for r in payload["records"] if r["value"] >= payload["minimum"]]
    return {"ids": sorted(r["id"] for r in selected), "total": sum(r["value"] for r in selected), "count": len(selected)}


def unfiltered_total(payload):
    selected = [r for r in payload["records"] if r["value"] >= payload["minimum"]]
    return {"ids": [r["id"] for r in selected], "total": sum(r["value"] for r in payload["records"]), "count": len(selected)}


def incorrect_count(payload):
    selected = [r for r in payload["records"] if r["value"] >= payload["minimum"]]
    return {"ids": [r["id"] for r in selected], "total": sum(r["value"] for r in selected), "count": len(payload["records"])}


def unexpected_field(payload):
    selected = [r for r in payload["records"] if r["value"] >= payload["minimum"]]
    return {"ids": [r["id"] for r in selected], "total": sum(r["value"] for r in selected),
            "count": len(selected), "debug": "internal"}


REGISTRY = (
    ("exclusive-boundary", "selection", exclusive_boundary),
    ("sorted-ids", "order", sorted_ids),
    ("unfiltered-total", "total", unfiltered_total),
    ("incorrect-count", "count", incorrect_count),
    ("unexpected-field", "schema", unexpected_field),
)
