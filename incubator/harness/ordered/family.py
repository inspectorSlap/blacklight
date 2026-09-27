"""The C2 v0.5 gated-stream family and the C4 v0.6 decision arithmetic.

The C2 manifest states its own runtime rule verbatim:

    runtime code must READ gated_streams and gated_stream_count from this
    verified manifest and require exact set equality with the streams it tallies
    over the full tuple (stream_id, configuration, n, event_name); it must not
    reconstruct the family from cell-id prefixes or naming conventions and must
    not hard-code the count; on divergence the implementation is wrong and the
    run stops

This module implements exactly that. The family is read from the digest-verified
manifest, never reconstructed from identifier prefixes, and
:func:`assert_exact_set_equality` stops the run on any divergence in either
direction.

The predecessor family is preserved rather than reasserted: the 125 streams
inherited from C2 v0.4 must be present as byte-identical objects, and
:func:`verify_predecessor_preservation` proves it against the authority copy
carried in the reviewed release.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os

from .canonical import canonical_sha256, sha256_hex

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = os.path.join(ROOT, "vendor", "blackbox-ordinal-v0.3.0-rc2")

C2_PATH = os.path.join(VENDOR, "contracts", "C2-event-family-v0.5.json")
C4_PATH = os.path.join(VENDOR, "contracts", "C4-statistical-amendment-v0.6.json")
C2_PREDECESSOR_PATH = os.path.join(VENDOR, "authority", "C2-event-family-v0.4.json")
DERIVATION_ALPHA_PATH = os.path.join(VENDOR, "contracts", "C2-derivation-alpha-v0.5.json")
DERIVATION_BETA_PATH = os.path.join(VENDOR, "contracts", "C2-derivation-beta-v0.5.json")

C2_FILE_SHA256 = "770db3a817f78e5a614ec925781421115108e8e4b71e12e4331d2697bc69e774"
C4_FILE_SHA256 = "9e996806a0696696f7f0e8e451613606ed605fb5fc8819985f0b66ea810e878c"
C2_PREDECESSOR_FILE_SHA256 = "fb948349d3fa0404a43b781f79a54bd69d61e75888ab0446431a73d5aee286c0"
DERIVATION_ALPHA_SHA256 = "9065b039db4d16c9fe9da08618f5587232064ff3b495233e286406c57cc1d6a1"
DERIVATION_BETA_SHA256 = "3b3176b950744a7ac477122f4bfe7511ca1acb58e2c83ff9ad7797f9588b6ba9"

C2_MANIFEST_DIGEST = "3bbda6c341543187adee2d4b4071b39bf78be7d84b6050939ff78676af16f52e"
C4_RECORD_DIGEST = "92537f83d40f9891bb55dfc71672b92cd67711d4421e3d5ce6c1889001219dd1"
C2_PREDECESSOR_MANIFEST_DIGEST = "0c47d35b80474a02dba212df367b62c8144ab01171c237b2890a7a3541ab6a42"

PREDECESSOR_STREAM_COUNT = 125


class FamilyViolation(Exception):
    """Raised when the runtime family does not match the verified manifest."""


def _load_verified(path, expected_sha256, label):
    with open(path, "rb") as handle:
        raw = handle.read()
    observed = sha256_hex(raw)
    if observed != expected_sha256:
        raise FamilyViolation(
            "%s file digest mismatch: expected %s, observed %s" % (label, expected_sha256, observed))
    return json.loads(raw.decode("utf-8"))


def _record_digest(document, key):
    material = {k: v for k, v in document.items() if k != key}
    return canonical_sha256(material)


def load_manifest():
    manifest = _load_verified(C2_PATH, C2_FILE_SHA256, "C2 v0.5 event-family manifest")
    observed = _record_digest(manifest, "manifest_digest")
    if observed != C2_MANIFEST_DIGEST:
        raise FamilyViolation(
            "C2 manifest digest mismatch: expected %s, observed %s" % (C2_MANIFEST_DIGEST, observed))
    if manifest.get("manifest_digest") != C2_MANIFEST_DIGEST:
        raise FamilyViolation("C2 manifest does not carry its own registered digest")
    declared = manifest["gated_stream_count"]
    streams = manifest["gated_streams"]
    if declared != len(streams):
        raise FamilyViolation(
            "C2 manifest declares %d gated streams but carries %d" % (declared, len(streams)))
    return manifest


def load_c4():
    contract = _load_verified(C4_PATH, C4_FILE_SHA256, "C4 v0.6 statistical amendment")
    observed = _record_digest(contract, "record_digest")
    if observed != C4_RECORD_DIGEST:
        raise FamilyViolation(
            "C4 record digest mismatch: expected %s, observed %s" % (C4_RECORD_DIGEST, observed))
    if contract["allocation"]["S"] != len(load_manifest()["gated_streams"]):
        raise FamilyViolation("C4 allocation S does not match the C2 gated stream count")
    return contract


MANIFEST = load_manifest()
C4 = load_c4()

GATED_STREAMS = tuple(MANIFEST["gated_streams"])
GATED_STREAM_COUNT = MANIFEST["gated_stream_count"]
SEGMENT_COUNT = MANIFEST["segment_count"]
PER_EVENT = dict(MANIFEST["per_event"])
STREAMS_PER_CONFIGURATION = dict(MANIFEST["streams_per_configuration"])
CANDIDATE_N = tuple(MANIFEST["n"])
ZERO_TOLERANCE = tuple(MANIFEST["zero_tolerance_structural"])
ZERO_TOLERANCE_COUNT = MANIFEST["zero_tolerance_count"]
ZERO_TOLERANCE_EVENTS = tuple(item["event_name"] for item in ZERO_TOLERANCE)
REPORT_ONLY = tuple(MANIFEST["report_only"])
REPORT_ONLY_EVENTS = tuple(item["event_name"] for item in REPORT_ONLY)
RUNTIME_RULE = MANIFEST["runtime_rule"]

# C4 v0.6 decision arithmetic, read rather than recomputed or hard-coded.
LOOKS = tuple(C4["looks"])
PASS_CRITICAL = tuple(C4["critical_values"]["PASS"])
FAIL_CRITICAL = tuple(C4["critical_values"]["FAIL"])
LAMBDA_F = C4["allocation"]["lambda_F"]
LAMBDA_P = C4["allocation"]["lambda_P"]
FIRST_LOOK_REQUESTS = C4["workload"]["first_look_requests"]
WORST_CASE_REQUESTS = C4["workload"]["worst_case_requests"]
CP01_ANCHORS = dict(C4["cp01_regression_anchors"])


def stream_tuple(stream):
    """The full identity tuple the runtime rule requires."""
    return (stream["stream_id"], stream["configuration"], stream["n"], stream["event_name"])


def stream_tuples():
    """Exact set of registered (stream_id, configuration, n, event_name) tuples."""
    tuples = {stream_tuple(stream) for stream in GATED_STREAMS}
    if len(tuples) != GATED_STREAM_COUNT:
        raise FamilyViolation(
            "manifest carries %d distinct stream tuples but declares %d"
            % (len(tuples), GATED_STREAM_COUNT))
    return tuples


def configurations():
    """Configuration identifiers named by the manifest, deduplicated in order."""
    seen, ordered = set(), []
    for stream in GATED_STREAMS:
        name = stream["configuration"]
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    if len(ordered) != SEGMENT_COUNT:
        raise FamilyViolation(
            "manifest names %d configurations but declares segment_count %d"
            % (len(ordered), SEGMENT_COUNT))
    return tuple(ordered)


def streams_for(configuration_id):
    return tuple(s for s in GATED_STREAMS if s["configuration"] == configuration_id)


def flat_key(stream_or_tuple):
    """The flat reporting key for a registered stream or its identity tuple."""
    identity = (stream_tuple(stream_or_tuple)
                if isinstance(stream_or_tuple, dict) else tuple(stream_or_tuple))
    return "|".join(str(part) for part in identity)


# Structured identity, derived once from the verified manifest. Reporting keys
# are flattened for JSON, so this is how a flat key is resolved back to the
# registered stream it names -- never by splitting the key on its delimiter,
# which the stream_id itself also contains.
FLAT_TO_STREAM = {flat_key(stream): stream for stream in GATED_STREAMS}


def stream_for_flat_key(flat):
    """The registered stream a flat reporting key names. Fails closed."""
    stream = FLAT_TO_STREAM.get(flat)
    if stream is None:
        raise FamilyViolation("reporting key %r names no registered stream" % (flat,))
    return stream


def configuration_of(flat):
    """The configuration a flat reporting key belongs to, from the manifest."""
    return stream_for_flat_key(flat)["configuration"]


def stream_tuples_for_configurations(configuration_ids):
    """Exact registered tuples for a set of configurations. Fails closed."""
    wanted = set(configuration_ids)
    unknown = sorted(wanted - set(configurations()))
    if unknown:
        raise FamilyViolation(
            "configuration(s) %s are not registered in the manifest" % unknown)
    return {stream_tuple(stream) for stream in GATED_STREAMS
            if stream["configuration"] in wanted}


def assert_exact_set_equality(observed, expected_configurations=None):
    """Stop the run unless the tallied family is exactly the expected family.

    ``observed`` is any iterable of (stream_id, configuration, n, event_name)
    tuples. Divergence in either direction is fatal, as the manifest requires.

    With ``expected_configurations`` the expectation is the exact registered
    subset carried by those configurations, which is what a second look over
    continuing configurations legitimately tallies. Without it the expectation
    is the complete registered family, which every final cumulative result must
    satisfy. The rule is unchanged: exact set equality against a registered
    expectation, never a relaxed or reconstructed one.
    """
    observed = set(observed)
    if expected_configurations is None:
        registered = stream_tuples()
        scope = "complete family"
    else:
        registered = stream_tuples_for_configurations(expected_configurations)
        scope = "registered subset for %d configuration(s)" % len(
            set(expected_configurations))
    missing = sorted(registered - observed)
    unregistered = sorted(observed - registered)
    if missing or unregistered:
        raise FamilyViolation(
            "gated-stream family divergence against the %s: %d expected streams "
            "not tallied, %d tallied streams not expected; first missing=%s "
            "first extra=%s"
            % (scope, len(missing), len(unregistered),
               missing[0] if missing else None,
               unregistered[0] if unregistered else None))
    return True


def verify_per_event_cardinality(observed, expected_configurations=None):
    """Per-event counts must reproduce the manifest's own per_event block.

    Scoped to a configuration subset when one is given, so a second look over
    continuing configurations is checked against the subset's registered
    per-event counts rather than the whole family's.
    """
    counts = {}
    for _, _, _, event_name in observed:
        counts[event_name] = counts.get(event_name, 0) + 1
    if expected_configurations is None:
        expected = PER_EVENT
    else:
        expected = {}
        for _, _, _, event_name in stream_tuples_for_configurations(
                expected_configurations):
            expected[event_name] = expected.get(event_name, 0) + 1
    if counts != expected:
        raise FamilyViolation(
            "per-event cardinality mismatch: expected=%s observed=%s"
            % (expected, counts))
    return True


def verify_predecessor_preservation():
    """The 125 C2 v0.4 streams must survive as byte-identical objects."""
    predecessor = _load_verified(C2_PREDECESSOR_PATH, C2_PREDECESSOR_FILE_SHA256,
                                 "C2 v0.4 predecessor authority")
    observed = _record_digest(predecessor, "manifest_digest")
    if observed != C2_PREDECESSOR_MANIFEST_DIGEST:
        raise FamilyViolation(
            "C2 v0.4 predecessor digest mismatch: expected %s, observed %s"
            % (C2_PREDECESSOR_MANIFEST_DIGEST, observed))

    old_streams = predecessor["gated_streams"]
    if len(old_streams) != PREDECESSOR_STREAM_COUNT:
        raise FamilyViolation(
            "C2 v0.4 carries %d gated streams, expected %d"
            % (len(old_streams), PREDECESSOR_STREAM_COUNT))

    successor_by_digest = {}
    for stream in GATED_STREAMS:
        successor_by_digest.setdefault(canonical_sha256(stream), []).append(stream)

    preserved, altered = [], []
    for stream in old_streams:
        digest = canonical_sha256(stream)
        if digest in successor_by_digest:
            preserved.append(stream["stream_id"])
        else:
            altered.append(stream["stream_id"])
    if altered:
        raise FamilyViolation(
            "%d predecessor streams are not preserved byte-identically; first: %s"
            % (len(altered), altered[0]))

    added = GATED_STREAM_COUNT - PREDECESSOR_STREAM_COUNT
    declared = MANIFEST["change_from_predecessor"]
    if declared["added_streams"] != added or declared["existing_streams_modified"] != 0:
        raise FamilyViolation(
            "change_from_predecessor block disagrees with the observed difference")
    return {
        "predecessor_streams": len(old_streams),
        "preserved_byte_identical": len(preserved),
        "modified": 0,
        "added": added,
        "successor_total": GATED_STREAM_COUNT,
    }


def added_stream_tuples():
    """The (configuration, n, event_name) tuples the successor adds to C2 v0.4.

    Derived by difference from the predecessor authority, never by naming
    convention, so the two independent derivations can be checked against
    something this module did not itself assume.
    """
    predecessor = _load_verified(C2_PREDECESSOR_PATH, C2_PREDECESSOR_FILE_SHA256,
                                 "C2 v0.4 predecessor authority")
    old = {(s["configuration"], s["n"], s["event_name"]) for s in predecessor["gated_streams"]}
    new = {(s["configuration"], s["n"], s["event_name"]) for s in GATED_STREAMS}
    return new - old


def verify_two_derivations():
    """Both independent derivations must agree, exactly, on the added tuples."""
    alpha = _load_verified(DERIVATION_ALPHA_PATH, DERIVATION_ALPHA_SHA256, "C2 derivation alpha")
    beta = _load_verified(DERIVATION_BETA_PATH, DERIVATION_BETA_SHA256, "C2 derivation beta")

    problems = []
    parsed = {}
    for name, derivation in (("alpha", alpha), ("beta", beta)):
        observed = _record_digest(derivation, "record_digest")
        if observed != derivation.get("record_digest"):
            problems.append("%s does not carry its own registered record digest" % name)
        tuples = {tuple(item) for item in derivation["tuples"]}
        if len(tuples) != len(derivation["tuples"]):
            problems.append("%s carries duplicate tuples" % name)
        parsed[name] = tuples

    if parsed["alpha"] != parsed["beta"]:
        problems.append("the two derivations disagree: %d tuples differ"
                        % len(parsed["alpha"] ^ parsed["beta"]))

    expected_added = added_stream_tuples()
    if parsed["alpha"] != expected_added:
        problems.append(
            "derivations cover %d tuples but the successor adds %d to the predecessor family"
            % (len(parsed["alpha"]), len(expected_added)))

    registered = {(s["configuration"], s["n"], s["event_name"]) for s in GATED_STREAMS}
    orphaned = sorted(parsed["alpha"] - registered)
    if orphaned:
        problems.append("derivation tuple not present in the manifest: %s" % (orphaned[0],))

    if problems:
        raise FamilyViolation("; ".join(problems))
    return {
        "alpha_tuples": len(parsed["alpha"]),
        "beta_tuples": len(parsed["beta"]),
        "derivations_agree": True,
        "added_streams_confirmed": len(expected_added),
        "all_present_in_manifest": True,
    }


def describe():
    return {
        "c2_manifest_digest": C2_MANIFEST_DIGEST,
        "c2_file_sha256": C2_FILE_SHA256,
        "c4_record_digest": C4_RECORD_DIGEST,
        "c4_file_sha256": C4_FILE_SHA256,
        "gated_stream_count": GATED_STREAM_COUNT,
        "segment_count": SEGMENT_COUNT,
        "n": list(CANDIDATE_N),
        "per_event": PER_EVENT,
        "streams_per_configuration": STREAMS_PER_CONFIGURATION,
        "zero_tolerance_count": ZERO_TOLERANCE_COUNT,
        "zero_tolerance_events": list(ZERO_TOLERANCE_EVENTS),
        "report_only_events": list(REPORT_ONLY_EVENTS),
        "looks": list(LOOKS),
        "pass_critical_values": list(PASS_CRITICAL),
        "fail_critical_values": list(FAIL_CRITICAL),
        "lambda_F": LAMBDA_F,
        "lambda_P": LAMBDA_P,
        "first_look_requests": FIRST_LOOK_REQUESTS,
        "worst_case_requests": WORST_CASE_REQUESTS,
        "cp01_regression_anchors": CP01_ANCHORS,
        "runtime_rule": RUNTIME_RULE,
        "family_read_from_manifest": True,
        "family_reconstructed_from_prefixes": False,
        "count_hard_coded": False,
    }
