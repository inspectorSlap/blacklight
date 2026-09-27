"""C1 v0.6 status vocabulary and the harness's strict, coercion-free readers.

The predecessor harness consumed dispositions through ``bool(...)``. Under C1
v0.6 that is forbidden outright: scientific meaning is carried only by the
enumerated status strings, and a Boolean at a disposition-bearing location is
itself a zero-tolerance event.

Every reader here fails closed. A missing status, a status outside the
registered vocabulary, a Boolean where a status belongs, or a forbidden parallel
carrier raises :class:`StatusContractViolation` rather than resolving to a
default. Nothing in this module coerces, defaults, or infers a disposition.

The vocabulary and precedence are read from the verified contract rather than
hard-coded, and the contract is digest-checked on load.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os

from .canonical import canonical_sha256, sha256_hex

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = os.path.join(ROOT, "vendor", "blackbox-ordinal-v0.3.0-rc2")
C1_PATH = os.path.join(VENDOR, "contracts", "C1-successor-v0.6.json")

# Identities recorded by the C2 v0.5 manifest for this exact contract.
C1_FILE_SHA256 = "43256e9f067ac536d1e1fdc3ef4b609ed2a854e13652830a5ff5ef36488f398d"
C1_CONTRACT_DIGEST = "8ad5f449aa2848f134fa981c5b5cdc7baf6e3324cd09404e6ffa7cbc3581db42"

# Locations where the document schema permits a JSON boolean. Everywhere else a
# boolean is a forbidden disposition carrier (C2 v0.5 FE-05).
PERMITTED_BOOLEAN_KEYS = frozenset({"sealed", "confirmatory_ready"})


class StatusContractViolation(Exception):
    """Raised when engine output cannot be consumed status-exactly."""


def _load_contract():
    with open(C1_PATH, "rb") as handle:
        raw = handle.read()
    observed_file = sha256_hex(raw)
    if observed_file != C1_FILE_SHA256:
        raise StatusContractViolation(
            "C1 successor contract file digest mismatch: expected %s, observed %s"
            % (C1_FILE_SHA256, observed_file))
    contract = json.loads(raw.decode("utf-8"))
    material = {k: v for k, v in contract.items() if k != "contract_digest"}
    observed_digest = canonical_sha256(material)
    if observed_digest != C1_CONTRACT_DIGEST:
        raise StatusContractViolation(
            "C1 successor contract digest mismatch: expected %s, observed %s"
            % (C1_CONTRACT_DIGEST, observed_digest))
    if contract.get("contract_digest") != C1_CONTRACT_DIGEST:
        raise StatusContractViolation("C1 contract does not carry its own registered digest")
    if contract.get("consumption", {}).get("status_blind_consumption") != "FORBIDDEN":
        raise StatusContractViolation("C1 contract no longer forbids status-blind consumption")
    return contract


CONTRACT = _load_contract()

STATUS_VOCABULARY = tuple(CONTRACT["status_vocabulary"])
EMITTABLE = tuple(CONTRACT["emittable"])
PRECEDENCE = tuple(CONTRACT["precedence"])
FORBIDDEN_FIELDS = frozenset(CONTRACT["consumption"]["forbidden_fields"])
REQUIRED_DIGESTS = tuple(CONTRACT["ordered_evidence"]["digests_required"])
DOCUMENT_SCHEMA = CONTRACT["document_schema"]
INPUT_SCHEMA = CONTRACT["input_schema"]
LIGHTS = tuple(CONTRACT["fixed_design"]["lights"])
CELLS = tuple(CONTRACT["fixed_design"]["cells"])
SEMANTIC_SPECIMENS = tuple(CONTRACT["fixed_design"]["semantic_specimens"])
MECHANICAL_SPECIMENS = tuple(CONTRACT["fixed_design"]["mechanical_specimens"])
N = CONTRACT["fixed_design"]["N"]


def precedence_rank(status):
    """Position of ``status`` in the registered blocking precedence.

    Lower is more blocking. A status outside the precedence list (``SUPPORTED``)
    returns a rank above every blocking status.
    """
    if status not in STATUS_VOCABULARY:
        raise StatusContractViolation("status %r is outside the registered vocabulary" % (status,))
    if status in PRECEDENCE:
        return PRECEDENCE.index(status)
    return len(PRECEDENCE)


def read_status(node, path):
    """Return the exact enumerated status at ``node``.

    Fails closed on a missing node, a missing status, a Boolean, or any value
    outside the registered emittable vocabulary. There is no default.
    """
    if not isinstance(node, dict):
        raise StatusContractViolation("%s is not a claim object" % path)
    if "status" not in node:
        raise StatusContractViolation("%s carries no status" % path)
    status = node["status"]
    if isinstance(status, bool):
        raise StatusContractViolation("%s carries a Boolean where a status is required" % path)
    if not isinstance(status, str):
        raise StatusContractViolation("%s status is not a string" % path)
    if status not in EMITTABLE:
        raise StatusContractViolation(
            "%s carries status %r, which is not emittable under C1 v0.6" % (path, status))
    return status


def is_supported(node, path):
    """Exact equality against the registered ``SUPPORTED`` status.

    This is the only permitted way for the harness to ask whether a claim was
    supported. It never coerces and never treats a non-``SUPPORTED`` status as
    a falsey value.
    """
    return read_status(node, path) == "SUPPORTED"


def read_estimand_state(node, path):
    """Return ``PRODUCED`` or ``NOT_PRODUCED`` for an estimand result object."""
    if not isinstance(node, dict):
        raise StatusContractViolation("%s is not an estimand object" % path)
    state = node.get("state")
    if state not in {"PRODUCED", "NOT_PRODUCED"}:
        raise StatusContractViolation("%s carries an unregistered estimand state %r" % (path, state))
    return state


def read_interval(node, path):
    """Return the closed interval of a PRODUCED estimand as (lower, upper)."""
    if read_estimand_state(node, path) != "PRODUCED":
        raise StatusContractViolation("%s has no interval; it is NOT_PRODUCED" % path)
    interval = node.get("interval")
    if not isinstance(interval, dict):
        raise StatusContractViolation("%s carries no interval object" % path)
    for key in ("lower", "upper"):
        value = interval.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StatusContractViolation("%s interval %s is not numeric" % (path, key))
    return float(interval["lower"]), float(interval["upper"])


def find_boolean_dispositions(document):
    """Every JSON boolean outside the two permitted document locations.

    This is the harness's independent detector for the C2 v0.5 zero-tolerance
    event ``boolean_disposition_emitted``. It does not call, trust, or reuse the
    engine's own ``assert_status_safe``.
    """
    found = []

    def visit(value, path, key):
        if key in FORBIDDEN_FIELDS:
            found.append({"path": path, "reason": "forbidden_parallel_carrier", "field": key})
            return
        if isinstance(value, bool):
            if key not in PERMITTED_BOOLEAN_KEYS:
                found.append({"path": path, "reason": "boolean_at_disposition_location"})
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, "%s.%s" % (path, child_key) if path else child_key, child_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, "%s[%d]" % (path, index), None)

    visit(document, "", None)
    return found


def assert_consumable(document):
    """Fail closed unless the document can be consumed status-exactly.

    Checks the document schema, the presence of every required evidence digest,
    and the absence of Boolean or parallel disposition carriers.
    """
    if not isinstance(document, dict):
        raise StatusContractViolation("engine output is not an object")
    if document.get("schema_version") != DOCUMENT_SCHEMA:
        raise StatusContractViolation(
            "engine output schema %r is not the registered %r"
            % (document.get("schema_version"), DOCUMENT_SCHEMA))
    booleans = find_boolean_dispositions(document)
    if booleans:
        raise StatusContractViolation(
            "engine output carries %d forbidden Boolean or parallel disposition carrier(s): %s"
            % (len(booleans), booleans[:3]))
    identity = document.get("evidence_identity")
    if not isinstance(identity, dict):
        raise StatusContractViolation("engine output carries no evidence_identity block")
    for name in ("attempt_archive_sha256", "ordered_input_sha256", "scientific_roster_sha256"):
        value = identity.get(name)
        if not isinstance(value, str) or len(value) != 64:
            raise StatusContractViolation("evidence_identity.%s is missing or malformed" % name)
    per_light = identity.get("per_light")
    if not isinstance(per_light, list) or len(per_light) != len(LIGHTS):
        raise StatusContractViolation("evidence_identity.per_light must carry one entry per light")
    for entry in per_light:
        for name in ("semantic_ordered_observation_sha256", "semantic_recomputed_count_sha256",
                     "mechanical_ordered_observation_sha256", "mechanical_recomputed_count_sha256"):
            value = entry.get(name) if isinstance(entry, dict) else None
            if not isinstance(value, str) or len(value) != 64:
                raise StatusContractViolation("evidence_identity.per_light.%s is missing" % name)
    return True
