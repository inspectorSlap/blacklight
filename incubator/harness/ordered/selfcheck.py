"""Mandatory separation proofs for the synthetic qualification path.

The approved clarification requires the v1.6.0 candidate to prove both
directions of the separation between synthetic C2/C4 qualification evidence and
real ordinal-profile acquisition evidence. Each proof below is deterministic, runs entirely
in process against the vendored byte-verified engine, and makes no network or
target call.

A proof that cannot be established raises; nothing here downgrades a failure to
a warning.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import copy

from . import engine_bridge as eb
from . import events, family, grid, synthetic
from .canonical import canonical_sha256
from .statuses import StatusContractViolation, assert_consumable

# A predecessor configuration carries clean validity (R=0, I=0), so its archive
# costs no replacements and is lawful under the operational budgets too.
CLEAN_CONFIGURATION = "G1-C1-NULL-P0-1_2"
# A validity configuration whose invalidity population is far above what the
# operational replacement budget can pay for.
HIGH_INVALIDITY_CONFIGURATION = "V7-VALIDITY-COMBINED-ABOVE"


class SeparationProofFailed(Exception):
    """Raised when a required separation property cannot be established."""


def _configuration(name):
    return grid.configuration_index()[name]


# ---------------------------------------------------------------------------
# Proof 1 -- synthetic configurations reach the engine by the direct route
# ---------------------------------------------------------------------------

def proof_synthetic_direct_path(replications=3):
    """All seven validity configurations analyse with validity as sole adverse component."""
    rows = []
    for configuration in grid.build_configurations():
        if configuration["source"] != grid.VALIDITY_SOURCE:
            continue
        truth = grid.population_truth(configuration)
        streams = family.streams_for(configuration["configuration_id"])
        for replication in range(replications):
            payload, archive = synthetic.build_ordered_input(configuration, replication)
            synthetic.verify_replication(configuration, replication, payload, archive)
            result = eb.analyze(payload)
            assert_consumable(result)
            observed = events.evaluate(result, configuration, truth, streams)

            structural = [
                light[group]["structural_state"]
                for light in payload["lights"] for group in ("semantic", "mechanical")
            ]
            if any(state != "ELIGIBLE" for state in structural):
                raise SeparationProofFailed(
                    "%s replication %d is structurally ineligible on the synthetic path"
                    % (configuration["configuration_id"], replication))

            inference = [light["inference_engine"]["status"] for light in result["semantic_lights"]]
            inference += [light["inference_engine"]["status"] for light in result["mechanical_lights"]]
            if any(status != "SUPPORTED" for status in inference):
                raise SeparationProofFailed(
                    "%s replication %d did not reach the scientific engine"
                    % (configuration["configuration_id"], replication))

            validity = [light["validity"]["status"] for light in result["semantic_lights"]]
            validity += [light["validity"]["status"] for light in result["mechanical_lights"]]
            if any(status not in {"SUPPORTED", "FAILED_VALIDITY"} for status in validity):
                raise SeparationProofFailed(
                    "%s replication %d routed validity to %s rather than the validity gate"
                    % (configuration["configuration_id"], replication, validity))

            rows.append({
                "configuration_id": configuration["configuration_id"],
                "replication": replication,
                "structural_state": "ELIGIBLE",
                "validity_statuses": validity,
                "gated_events_fired": sorted(k[3] for k, v in observed["gated"].items() if v),
                "zero_tolerance_fired": sorted(k for k, v in observed["zero_tolerance"].items() if v),
            })
    return {
        "configurations_proved": len({r["configuration_id"] for r in rows}),
        "replications": len(rows),
        "all_reached_engine_by_direct_ordered_input": True,
        "validity_is_sole_adverse_component": True,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Proof 2 -- the operational budget gate is unchanged and still bites
# ---------------------------------------------------------------------------

def proof_operational_budget_gate_still_bites():
    """The same virtual archive, offered as acquisition evidence, fails P7."""
    configuration = _configuration(HIGH_INVALIDITY_CONFIGURATION)
    _, archive = synthetic.build_ordered_input(configuration, 0)
    acquisition = synthetic.as_acquisition_archive(archive)

    aggregate = eb.aggregate_attempt_archive(acquisition)
    reasons, states = set(), set()
    for light in aggregate["ordered_input"]["lights"]:
        for group in ("semantic", "mechanical"):
            states.add(light[group]["structural_state"])
            reasons.update(light[group]["structural_reason_codes"])

    if "STRUCTURAL_GATE_P7_RETRY_BUDGET" not in reasons:
        raise SeparationProofFailed(
            "the operational replacement-budget gate did not fire on a high-invalidity archive; "
            "observed reasons %s" % sorted(reasons))
    if states != {"INELIGIBLE"}:
        raise SeparationProofFailed(
            "acquisition path did not route every corpus to INELIGIBLE; observed %s" % sorted(states))

    return {
        "configuration_id": HIGH_INVALIDITY_CONFIGURATION,
        "replacement_count": aggregate["replacement_count"],
        "campaign_replacement_budget": 48,
        "per_light_replacement_budget": 16,
        "acquisition_structural_states": sorted(states),
        "acquisition_reason_codes": sorted(reasons),
        "budget_gate_unchanged_and_enforced": True,
    }


# ---------------------------------------------------------------------------
# Proof 3 -- real acquisition cannot opt into synthetic treatment
# ---------------------------------------------------------------------------

def proof_no_acquisition_opt_in():
    """Synthetic evidence is refused wherever real acquisition is required."""
    configuration = _configuration(HIGH_INVALIDITY_CONFIGURATION)
    payload, archive = synthetic.build_ordered_input(configuration, 0)

    refused = []
    for label, candidate in (("ordered_input", payload), ("expanded_archive", archive)):
        try:
            synthetic.assert_not_synthetic(candidate, "acquisition")
        except synthetic.SyntheticEvidenceError:
            refused.append(label)
        else:
            raise SeparationProofFailed(
                "the acquisition guard accepted synthetic %s" % label)

    # A real acquisition payload, with no synthetic markings, passes the guard.
    clean = {"analysis_id": "ordinal-profile|REAL|rep=0", "bindings": {"study": "s1"}}
    synthetic.assert_not_synthetic(clean, "acquisition")

    # Stripping the binding is not enough: the analysis identifier still marks it.
    stripped = copy.deepcopy(payload)
    stripped["bindings"] = {"study": "s1"}
    try:
        synthetic.assert_not_synthetic(stripped, "acquisition")
    except synthetic.SyntheticEvidenceError:
        refused.append("ordered_input_with_bindings_stripped")
    else:
        raise SeparationProofFailed(
            "removing the evidence-kind binding let synthetic evidence into acquisition")

    return {
        "synthetic_inputs_refused_by_acquisition_guard": refused,
        "real_acquisition_input_accepted": True,
        "synthetic_switch_reachable_from_acquisition": False,
    }


# ---------------------------------------------------------------------------
# Proof 4 -- synthetic and real evidence identities cannot collide
# ---------------------------------------------------------------------------

def proof_identity_separation():
    """Synthetic and real inputs differ in every identity the engine emits."""
    configuration = _configuration(CLEAN_CONFIGURATION)
    payload, archive = synthetic.build_ordered_input(configuration, 0)
    synthetic_result = eb.analyze(payload)

    acquisition = synthetic.as_acquisition_archive(archive)
    acquisition_aggregate = eb.aggregate_attempt_archive(acquisition)
    acquisition_input = acquisition_aggregate["ordered_input"]
    acquisition_result = eb.analyze(acquisition_input)

    synthetic_identity = synthetic_result["evidence_identity"]
    acquisition_identity = acquisition_result["evidence_identity"]

    collisions = [
        name for name in ("attempt_archive_sha256", "ordered_input_sha256", "scientific_roster_sha256")
        if synthetic_identity[name] == acquisition_identity[name]
    ]
    if collisions:
        raise SeparationProofFailed(
            "synthetic and acquisition evidence share identities: %s" % collisions)

    if not synthetic.is_synthetic_analysis_id(payload["analysis_id"]):
        raise SeparationProofFailed("synthetic payload does not carry a synthetic analysis identifier")
    if synthetic.is_synthetic_analysis_id(acquisition_input["analysis_id"]):
        raise SeparationProofFailed("an acquisition payload carries a synthetic analysis identifier")

    return {
        "distinct_identities": ["attempt_archive_sha256", "ordered_input_sha256",
                                "scientific_roster_sha256"],
        "synthetic_analysis_id_prefix": synthetic.ANALYSIS_ID_PREFIX,
        "collisions": [],
        "synthetic_roster_digest": synthetic_identity["scientific_roster_sha256"],
        "acquisition_roster_digest": acquisition_identity["scientific_roster_sha256"],
    }


# ---------------------------------------------------------------------------
# Proof 5 -- tampering fails before a disposition
# ---------------------------------------------------------------------------

def proof_tamper_detection():
    """Every registered tamper is caught before any disposition is produced."""
    configuration = _configuration(HIGH_INVALIDITY_CONFIGURATION)
    payload, archive = synthetic.build_ordered_input(configuration, 0)

    def tamper_binding(p, a):
        p["bindings"]["generator_version"] = "9.9"
        return p, a

    def tamper_seed(p, a):
        p["bindings"]["configuration_seed"] = "0" * 64
        return p, a

    def tamper_indicator(p, a):
        p["lights"][0]["semantic"]["validity_indicators"]["R_overall"][0] ^= 1
        return p, a

    def tamper_slot_row(p, a):
        p["lights"][0]["semantic"]["slot_validity_rows"][0]["I"] ^= 1
        return p, a

    def tamper_score(p, a):
        cells = p["lights"][0]["semantic"]["specimens"][0]["cells"]
        cell = sorted(cells)[0]
        cells[cell]["scores"][0] = 1 if cells[cell]["scores"][0] != 1 else 2
        return p, a

    def tamper_attempt_order(p, a):
        a["attempts"][0], a["attempts"][1] = a["attempts"][1], a["attempts"][0]
        return p, a

    def tamper_archive_digest(p, a):
        p["attempt_archive_sha256"] = "0" * 64
        return p, a

    def tamper_ordered_digest(p, a):
        p["ordered_input_sha256"] = "0" * 64
        return p, a

    tampers = {
        "generator_binding": tamper_binding,
        "configuration_seed": tamper_seed,
        "validity_indicator": tamper_indicator,
        "slot_validity_row": tamper_slot_row,
        "ordered_score": tamper_score,
        "attempt_order": tamper_attempt_order,
        "attempt_archive_digest": tamper_archive_digest,
        "ordered_input_digest": tamper_ordered_digest,
    }

    rows = {}
    for name, mutate in tampers.items():
        mutated_payload, mutated_archive = mutate(copy.deepcopy(payload), copy.deepcopy(archive))
        caught_by = None
        try:
            synthetic.verify_replication(configuration, 0, mutated_payload, mutated_archive)
        except synthetic.SyntheticEvidenceError:
            caught_by = "synthetic_verification"
        if caught_by is None:
            # The harness did not catch it; the engine must refuse it before adjudicating.
            try:
                eb.analyze(mutated_payload)
            except (eb.InputError, eb.ContractViolation):
                caught_by = "engine_input_validation"
        if caught_by is None:
            raise SeparationProofFailed(
                "tampering with %s produced a disposition instead of failing closed" % name)
        rows[name] = caught_by
    return {"tampers_tested": len(rows), "all_failed_closed": True, "caught_by": rows}


# ---------------------------------------------------------------------------
# Proof 6 -- the 28 new streams observe intended events
# ---------------------------------------------------------------------------

def proof_new_streams_live(replications=3):
    """The added validity streams measure their event, not structural ineligibility."""
    added = family.added_stream_tuples()
    observed_structural_ineligibility = 0
    coverage_events = 0
    clearance_streams = 0
    rows = []

    for configuration in grid.build_configurations():
        if configuration["source"] != grid.VALIDITY_SOURCE:
            continue
        truth = grid.population_truth(configuration)
        streams = family.streams_for(configuration["configuration_id"])
        for replication in range(replications):
            payload, archive = synthetic.build_ordered_input(configuration, replication)
            result = eb.analyze(payload)
            observed = events.evaluate(result, configuration, truth, streams)
            for stream_key, fired in observed["gated"].items():
                event_name = stream_key[3]
                if event_name in ("p0_noncoverage", "ip_noncoverage") and fired:
                    coverage_events += 1
                if event_name.endswith("validity_false_clearance"):
                    clearance_streams += 1
            for light in result["semantic_lights"] + result["mechanical_lights"]:
                if light["inference_engine"]["status"] != "SUPPORTED":
                    observed_structural_ineligibility += 1
            rows.append({
                "configuration_id": configuration["configuration_id"],
                "replication": replication,
                "fired": sorted(k[3] for k, v in observed["gated"].items() if v),
            })

    if observed_structural_ineligibility:
        raise SeparationProofFailed(
            "%d corpus/light combinations were structurally ineligible; the added streams "
            "would be measuring structural failure rather than their registered event"
            % observed_structural_ineligibility)
    if coverage_events:
        raise SeparationProofFailed(
            "coverage streams fired %d times against a correct engine at the validity "
            "configurations" % coverage_events)
    if not clearance_streams:
        raise SeparationProofFailed("no validity false-clearance stream was evaluated")

    return {
        "added_streams": len(added),
        "validity_configurations": len({r["configuration_id"] for r in rows}),
        "replications": len(rows),
        "structural_ineligibility_observed": 0,
        "coverage_events_against_correct_engine": 0,
        "validity_clearance_streams_evaluated": clearance_streams,
        "streams_observe_their_registered_event": True,
    }


# ---------------------------------------------------------------------------
# Proof 7 -- the direct route reproduces the normalizer exactly where lawful
# ---------------------------------------------------------------------------

def proof_normalizer_equivalence():
    """Where the budgets do not bite, both routes produce identical science.

    For a clean configuration the synthetic archive is lawful acquisition
    evidence, so the operational normalizer and the direct constructor must
    agree byte-for-byte on the scientific content of the ordered input. This
    bounds the direct route: it differs from the normalizer only where the
    clarification says it may, which is the budget gate.
    """
    configuration = _configuration(CLEAN_CONFIGURATION)
    payload, archive = synthetic.build_ordered_input(configuration, 0)
    acquisition = synthetic.as_acquisition_archive(archive)
    aggregate = eb.aggregate_attempt_archive(acquisition)

    if aggregate["replacement_count"] != 0:
        raise SeparationProofFailed(
            "the clean configuration unexpectedly consumed %d replacements"
            % aggregate["replacement_count"])

    direct = canonical_sha256(payload["lights"])
    normalized = canonical_sha256(aggregate["ordered_input"]["lights"])
    if direct != normalized:
        raise SeparationProofFailed(
            "the direct constructor and the operational normalizer disagree on the "
            "scientific content of the ordered input")

    return {
        "configuration_id": CLEAN_CONFIGURATION,
        "replacements_consumed": 0,
        "scientific_content_digest": direct,
        "direct_route_matches_operational_normalizer": True,
    }


# ---------------------------------------------------------------------------
# Proof 8 -- the harness digest convention agrees with the engine's
# ---------------------------------------------------------------------------

ADVERSARIAL_DIGEST_CASES = [
    {},
    {"b": 1, "a": 2},
    {"nested": {"z": [1, 2, {"y": None}], "a": "unicode é中"}},
    [1, -1, 0, 10 ** 18],
    {"float": 0.1, "int": 1, "str": "1"},
    {"empty_list": [], "empty_obj": {}, "null": None},
    {"key with spaces": "v", "é": "accent"},
    [[[[1]]]],
]


def proof_canonical_digest_agreement():
    """The harness's independent digest must equal the engine's on every case."""
    divergent = []
    for case in ADVERSARIAL_DIGEST_CASES:
        if canonical_sha256(case) != eb.engine_canonical_sha256(case):
            divergent.append(case)
    if divergent:
        raise SeparationProofFailed(
            "harness and engine canonical digests diverge on %d structures" % len(divergent))
    return {"cases": len(ADVERSARIAL_DIGEST_CASES), "agree": True}


# ---------------------------------------------------------------------------
# Proof 9 -- every wrapper terminates in the same scientific function
# ---------------------------------------------------------------------------

def proof_wrapper_termination():
    """CLI, endpoint, batch and archive wrappers all reach engine.analyze."""
    targets = eb.wrapper_targets()
    scientific = eb.SCIENTIFIC_FUNCTION
    divergent = [name for name, function in targets.items() if function is not scientific]
    if divergent:
        raise SeparationProofFailed(
            "these wrappers do not resolve to ordinal_engine.engine.analyze: %s" % divergent)

    configuration = _configuration(CLEAN_CONFIGURATION)
    payload, archive = synthetic.build_ordered_input(configuration, 0)

    direct = eb.analyze(copy.deepcopy(payload))
    endpoint = eb.analyze_endpoint(copy.deepcopy(payload))
    batch = eb.analyze_batch([copy.deepcopy(payload)])[0]

    digests = {
        "engine.analyze": canonical_sha256(direct),
        "api.analyze_endpoint": canonical_sha256(endpoint),
        "api.analyze_batch": canonical_sha256(batch),
    }
    if len(set(digests.values())) != 1:
        raise SeparationProofFailed("wrappers produced different results: %s" % digests)

    acquisition = synthetic.as_acquisition_archive(archive)
    archive_endpoint = eb.analyze_archive_endpoint(acquisition)
    digests["api.analyze_archive_endpoint"] = canonical_sha256(archive_endpoint)

    return {
        "wrappers_resolving_to_scientific_function": sorted(targets),
        "identical_output_digest": digests["engine.analyze"],
        "wrapper_digests": digests,
        "archive_endpoint_reaches_same_function": True,
        "second_scientific_engine": False,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

PROOFS = (
    ("synthetic_direct_path", proof_synthetic_direct_path),
    ("operational_budget_gate_still_bites", proof_operational_budget_gate_still_bites),
    ("no_acquisition_opt_in", proof_no_acquisition_opt_in),
    ("identity_separation", proof_identity_separation),
    ("tamper_detection", proof_tamper_detection),
    ("new_streams_live", proof_new_streams_live),
    ("normalizer_equivalence", proof_normalizer_equivalence),
    ("canonical_digest_agreement", proof_canonical_digest_agreement),
    ("wrapper_termination", proof_wrapper_termination),
)


def run_all():
    results, failures = {}, []
    for name, proof in PROOFS:
        try:
            results[name] = {"passed": True, "detail": proof()}
        except Exception as error:  # noqa: BLE001 - recorded, never masked
            results[name] = {"passed": False, "error": "%s: %s" % (type(error).__name__, error)}
            failures.append(name)
    return {
        "proofs_run": len(PROOFS),
        "passed": len(PROOFS) - len(failures),
        "failed": failures,
        "all_passed": not failures,
        "results": results,
    }
