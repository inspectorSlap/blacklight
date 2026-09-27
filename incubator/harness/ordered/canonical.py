"""The registered canonical JSON digest convention, implemented independently.

The approved method fixes one convention for every scientific boundary
(method contract section 8.3): SHA-256 over UTF-8 JSON with ``sort_keys=true``
and separators ``(',', ':')``.

The harness deliberately implements this itself rather than importing the
engine's helper. An oracle that borrows the target's serializer cannot detect a
serializer defect. ``harness.ordered.selfcheck`` proves this implementation and
the engine's agree on adversarial structures; if they ever diverge, that
divergence is a finding rather than a silent agreement.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import json


def canonical_bytes(value):
    """Return the registered canonical JSON representation of ``value``."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value):
    """SHA-256 over :func:`canonical_bytes`."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_hex(data):
    """SHA-256 over raw bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
