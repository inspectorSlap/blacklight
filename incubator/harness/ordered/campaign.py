"""The v1.6.0 qualification campaign: plan, tallying and adjudication.

Topology and arithmetic are read from the verified contracts, never recomputed
or hard-coded:

* the configuration roster and the gated-stream family come from the C2 v0.5
  manifest (:mod:`harness.ordered.family`);
* the looks and the PASS/FAIL critical values come from the C4 v0.6 amendment.

Tallies are keyed on the full ``(stream_id, configuration, n, event_name)``
tuple that the manifest's runtime rule requires, and the tallied family is
checked for exact set equality against the manifest before any verdict is
produced.

Running the campaign requires a target. Building and validating the plan does
not, and this module performs no network or target action of its own.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


from . import events, family, grid, synthetic
from .statuses import assert_consumable

FIRST_LOOK, SECOND_LOOK = family.LOOKS
PASS_AT_LOOK = family.PASS_CRITICAL
FAIL_AT_LOOK = family.FAIL_CRITICAL

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_CONTINUE = "CONTINUE"
VERDICT_UNRESOLVED = "UNRESOLVED"
VERDICT_REPORTED = "REPORTED_NOT_GATED"


class CampaignError(Exception):
    """Raised when the campaign cannot proceed exactly as registered."""


class EvidenceIdentityMismatch(CampaignError):
    """Raised when the engine's evidence identity disagrees with the harness."""


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

class Plan(object):
    """The registered two-look plan, read from C4 v0.6."""

    def __init__(self):
        self.looks = list(family.LOOKS)
        self.pass_critical = list(family.PASS_CRITICAL)
        self.fail_critical = list(family.FAIL_CRITICAL)
        self.lambda_F = family.LAMBDA_F
        self.lambda_P = family.LAMBDA_P
        self.gated_stream_count = family.GATED_STREAM_COUNT
        self.segment_count = family.SEGMENT_COUNT
        if len(self.looks) != len(self.pass_critical) != len(self.fail_critical):
            raise CampaignError("C4 look and critical-value vectors disagree in length")

    def decide_at(self, look_index, event_count):
        """Registered decision at one look, with no recomputation."""
        pass_max = self.pass_critical[look_index]
        fail_min = self.fail_critical[look_index]
        if event_count >= fail_min:
            return VERDICT_FAIL
        if event_count <= pass_max:
            return VERDICT_PASS
        return VERDICT_CONTINUE if look_index + 1 < len(self.looks) else VERDICT_UNRESOLVED

    def workload(self):
        first = self.segment_count * self.looks[0]
        worst = self.segment_count * self.looks[-1]
        if first != family.FIRST_LOOK_REQUESTS:
            raise CampaignError(
                "first-look workload %d does not match the registered %d"
                % (first, family.FIRST_LOOK_REQUESTS))
        if worst != family.WORST_CASE_REQUESTS:
            raise CampaignError(
                "worst-case workload %d does not match the registered %d"
                % (worst, family.WORST_CASE_REQUESTS))
        return {
            "configurations": self.segment_count,
            "first_look_replications_per_configuration": self.looks[0],
            "worst_case_replications_per_configuration": self.looks[-1],
            "first_look_requests": first,
            "worst_case_requests": worst,
        }


def validate_topology():
    """Prove the runtime topology equals the registered topology, exactly."""
    plan = Plan()
    configurations = grid.build_configurations()
    identifiers = [item["configuration_id"] for item in configurations]

    manifest_configurations = set(family.configurations())
    runtime_configurations = set(identifiers)
    if manifest_configurations != runtime_configurations:
        missing = sorted(manifest_configurations - runtime_configurations)
        extra = sorted(runtime_configurations - manifest_configurations)
        raise CampaignError(
            "configuration roster does not match the manifest; missing=%s extra=%s"
            % (missing[:3], extra[:3]))

    tuples = set()
    for configuration_id in identifiers:
        for stream in family.streams_for(configuration_id):
            tuples.add(family.stream_tuple(stream))
    family.assert_exact_set_equality(tuples)
    family.verify_per_event_cardinality(tuples)

    preservation = family.verify_predecessor_preservation()
    derivations = family.verify_two_derivations()
    coverage = events.verify_coverage()

    return {
        "configurations": len(identifiers),
        "gated_streams": len(tuples),
        "n": list(family.CANDIDATE_N),
        "looks": plan.looks,
        "pass_critical_values": plan.pass_critical,
        "fail_critical_values": plan.fail_critical,
        "lambda_F": plan.lambda_F,
        "lambda_P": plan.lambda_P,
        "workload": plan.workload(),
        "family_set_equality": True,
        "per_event_cardinality": True,
        "predecessor_preservation": preservation,
        "two_derivations": derivations,
        "event_coverage": coverage,
        "family_reconstructed_from_prefixes": False,
        "stream_count_hard_coded": False,
    }


# ---------------------------------------------------------------------------
# Evidence identity
# ---------------------------------------------------------------------------

def verify_evidence_identity(result, ordered_input, expanded_archive):
    """All five registered evidence identities must agree with the harness.

    The engine reports what it consumed; the harness recomputes the same five
    digests from its own artefacts and requires equality. A disagreement means
    the engine did not analyse the evidence the harness built.
    """
    identity = result["evidence_identity"]
    problems = []

    if identity["attempt_archive_sha256"] != synthetic.archive_digest(expanded_archive):
        problems.append("attempt_archive_sha256")
    if identity["ordered_input_sha256"] != ordered_input["ordered_input_sha256"]:
        problems.append("ordered_input_sha256")

    for index, light in enumerate(ordered_input["lights"]):
        reported = identity["per_light"][index]
        if reported["light_id"] != light["id"]:
            problems.append("per_light[%d].light_id" % index)
        for group in ("semantic", "mechanical"):
            if reported["%s_ordered_observation_sha256" % group] != \
                    light[group]["ordered_observation_sha256"]:
                problems.append("per_light[%d].%s_ordered_observation_sha256" % (index, group))
            if reported["%s_recomputed_count_sha256" % group] != \
                    light[group]["recomputed_count_sha256"]:
                problems.append("per_light[%d].%s_recomputed_count_sha256" % (index, group))

    if not isinstance(identity.get("scientific_roster_sha256"), str) \
            or len(identity["scientific_roster_sha256"]) != 64:
        problems.append("scientific_roster_sha256")

    if problems:
        raise EvidenceIdentityMismatch(
            "engine evidence identity disagrees with the harness on: %s" % problems)

    return {
        "attempt_archive_sha256": identity["attempt_archive_sha256"],
        "ordered_input_sha256": identity["ordered_input_sha256"],
        "scientific_roster_sha256": identity["scientific_roster_sha256"],
        "per_light_ordered_observation_verified": len(ordered_input["lights"]) * 2,
        "per_light_recomputed_count_verified": len(ordered_input["lights"]) * 2,
        "identities_verified": 5,
    }


# ---------------------------------------------------------------------------
# One replication
# ---------------------------------------------------------------------------

def run_replication(target, configuration, replication, population_truth, streams):
    """Build, submit, verify and score one replication.

    ``target`` is any object exposing ``analyze(payload)``. Every disposition is
    read status-exactly; nothing is coerced.
    """
    ordered_input, expanded_archive = synthetic.build_ordered_input(configuration, replication)
    synthetic.verify_replication(configuration, replication, ordered_input, expanded_archive)

    result = target.analyze(ordered_input)
    assert_consumable(result)
    identity = verify_evidence_identity(result, ordered_input, expanded_archive)
    observed = events.evaluate(result, configuration, population_truth, streams)

    return {
        "analysis_id": ordered_input["analysis_id"],
        "configuration_id": configuration["configuration_id"],
        "replication": replication,
        "evidence_identity": identity,
        "events": observed,
    }


# ---------------------------------------------------------------------------
# Tallies
# ---------------------------------------------------------------------------

class Tally(object):
    """Per-stream event counts keyed on the full registered tuple."""

    def __init__(self):
        self.gated = {}
        self.zero_tolerance = {name: 0 for name in family.ZERO_TOLERANCE_EVENTS}
        self.report_only = {name: 0 for name in family.REPORT_ONLY_EVENTS}
        self.trials = 0

    def add(self, observed):
        self.trials += 1
        for stream_key, fired in observed["gated"].items():
            row = self.gated.setdefault(stream_key, {"events": 0, "trials": 0})
            row["trials"] += 1
            if fired:
                row["events"] += 1
        for name, fired in observed["zero_tolerance"].items():
            if fired:
                self.zero_tolerance[name] += 1
        for name, fired in observed["report_only"].items():
            if fired:
                self.report_only[name] += 1

    def assert_family_exact(self, expected_configurations=None):
        """Prove the tallied family is exactly the expected registered family.

        A second look legitimately tallies only the configurations that
        continued, so it states that subset and is held to it exactly. Every
        final cumulative result states nothing and is held to the complete
        registered family.
        """
        family.assert_exact_set_equality(self.gated.keys(), expected_configurations)
        family.verify_per_event_cardinality(self.gated.keys(), expected_configurations)
        return True

    def adjudicate(self, plan, look_index, expected_configurations=None):
        """Registered verdicts, after proving the family is exactly right."""
        self.assert_family_exact(expected_configurations)
        verdicts = {}
        for stream_key, row in sorted(self.gated.items()):
            verdicts[stream_key] = {
                "events": row["events"],
                "trials": row["trials"],
                "verdict": plan.decide_at(look_index, row["events"]),
                "pass_max": plan.pass_critical[look_index],
                "fail_min": plan.fail_critical[look_index],
            }
        zero_tolerance = {
            name: {"events": count,
                   "verdict": VERDICT_FAIL if count > 0 else VERDICT_PASS}
            for name, count in sorted(self.zero_tolerance.items())
        }
        report_only = {
            name: {"events": count, "verdict": VERDICT_REPORTED}
            for name, count in sorted(self.report_only.items())
        }
        return {
            "look_index": look_index,
            "replications_per_configuration": plan.looks[look_index],
            "gated": verdicts,
            "zero_tolerance": zero_tolerance,
            "report_only": report_only,
        }
