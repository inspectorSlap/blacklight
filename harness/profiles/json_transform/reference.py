"""Separate implementation of the transformation contract.

No import from the oracle, mutation or checker modules is permitted here.
"""


def transform(payload):
    if type(payload) is not dict or len(payload) != 2:
        raise ValueError("expected two input fields")
    if "minimum" not in payload or "records" not in payload:
        raise ValueError("missing input field")
    boundary = payload["minimum"]
    source = payload["records"]
    if type(boundary) is not int or type(source) is not list:
        raise ValueError("invalid input field")
    ids = []
    total = 0
    index = 0
    while index < len(source):
        item = source[index]
        if type(item) is not dict or len(item) != 2 or "id" not in item or "value" not in item:
            raise ValueError("invalid record shape")
        name, value = item["id"], item["value"]
        if type(name) is not str or not name or type(value) is not int:
            raise ValueError("invalid record value")
        if value > boundary or value == boundary:
            ids.append(name)
            total += value
        index += 1
    return {"ids": ids, "total": total, "count": len(ids)}
