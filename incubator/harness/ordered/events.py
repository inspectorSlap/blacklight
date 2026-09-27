"""Event extraction from reviewed-engine output.

Every evaluator here implements one named event from the C2 v0.5 manifest and
carries the manifest's own definition text. :func:`verify_definitions` compares
the carried text against the manifest on load, so an evaluator cannot drift away
from the definition it claims to implement.

Nothing is inferred from identifier prefixes. Which streams exist at which
configuration is decided entirely by the manifest (see
:mod:`harness.ordered.family`); this module only answers, for one replication,
whether a named event fired.

Every disposition is read through :mod:`harness.ordered.statuses`, which fails
closed rather than coercing. No evaluator calls ``bool()`` on engine output.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


from fractions import Fraction

from . import family
from .statuses import (
    LIGHTS,
    StatusContractViolation,
    find_boolean_dispositions,
    read_estimand_state,
    read_interval,
    read_status,
)

# Registered validity margins (C1 v0.6 validity.margins).
VALIDITY_MARGINS = {
    "overall_refusal": Fraction(1, 20),
    "overall_invalid": Fraction(1, 20),
    "differential_refusal": Fraction(1, 20),
    "differential_invalid": Fraction(1, 20),
}

DEGENERACY_PREFIX = "G10-"
POWER_FAMILY = "POWER"


class EventEvaluationError(Exception):
    """Raised when an event cannot be evaluated exactly."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _semantic(result):
    return result["semantic_lights"]


def _mechanical(result):
    return result["mechanical_lights"]


def _any_light_supported(lights, path_key, label):
    for index, light in enumerate(lights):
        if read_status(light[path_key], "%s[%d].%s" % (label, index, path_key)) == "SUPPORTED":
            return True
    return False


def _exact(value):
    """Exact rational view of a reported floating-point endpoint."""
    return Fraction(value).limit_denominator() if isinstance(value, Fraction) else Fraction(value)


def _covers(interval, population):
    lower, upper = interval
    return Fraction(lower) <= population <= Fraction(upper)


# ---------------------------------------------------------------------------
# Validity population parameters
# ---------------------------------------------------------------------------

def adverse_validity_components(configuration, corpus):
    """Registered validity parameters at or above their adverse boundary.

    Computed from the configuration's declared population, never from observed
    output. A configuration with no declared validity population has none.
    """
    population = configuration.get("validity_population")
    if population is None:
        return []
    rates = population[corpus]
    adverse = []
    for kind, margin_key in (("refusal", "overall_refusal"), ("invalid", "overall_invalid")):
        cells = rates[kind]
        overall = sum(Fraction(str(cells[cell])) for cell in cells) / len(cells)
        if overall >= VALIDITY_MARGINS[margin_key]:
            adverse.append({"component": "overall_%s" % kind, "value": str(overall),
                            "boundary": str(VALIDITY_MARGINS[margin_key])})
        differential_key = "differential_%s" % kind
        for label, left, right in (("00_0B", "00", "0B"), ("A0_AB", "A0", "AB")):
            value = abs(Fraction(str(cells[left])) - Fraction(str(cells[right])))
            if value >= VALIDITY_MARGINS[differential_key]:
                adverse.append({"component": "%s_diff_%s" % (kind, label), "value": str(value),
                                "boundary": str(VALIDITY_MARGINS[differential_key])})
    return adverse


# ---------------------------------------------------------------------------
# Gated event evaluators
# ---------------------------------------------------------------------------

def _c1_false_support(result, context):
    return _any_light_supported(_semantic(result), "c1", "semantic_lights")


def _c2_false_support(result, context):
    return _any_light_supported(_semantic(result), "c2", "semantic_lights")


def _range_gate_false_clearance(result, context):
    return _any_light_supported(_semantic(result), "range", "semantic_lights")


def _c5_false_support(result, context):
    return _any_light_supported(_mechanical(result), "c5", "mechanical_lights")


def _c5_false_eligibility_clearance(result, context):
    return _any_light_supported(_mechanical(result), "c5_eligibility", "mechanical_lights")


def _cross_light_false_support(result, context):
    return read_status(result["cross_light"]["A_all"], "cross_light.A_all") == "SUPPORTED"


def _p0_noncoverage(result, context):
    return _estimand_noncoverage(result, context, "P0_bar", "P0_bar")


def _ip_noncoverage(result, context):
    return _estimand_noncoverage(result, context, "I_P_bar", "I_P_bar")


def _estimand_noncoverage(result, context, estimand_key, truth_key):
    truths = context["population_truth"]
    for index, light in enumerate(_semantic(result)):
        path = "semantic_lights[%d].estimands.%s" % (index, estimand_key)
        node = light["estimands"][estimand_key]
        if read_estimand_state(node, path) == "NOT_PRODUCED":
            return True
        interval = read_interval(node, path)
        if not _covers(interval, truths[index][truth_key]):
            return True
    return False


def _semantic_validity_false_clearance(result, context):
    return _validity_false_clearance(result, context, _semantic(result), "semantic", "semantic_lights")


def _mechanical_validity_false_clearance(result, context):
    return _validity_false_clearance(result, context, _mechanical(result), "mechanical", "mechanical_lights")


def _validity_false_clearance(result, context, lights, corpus, label):
    adverse = adverse_validity_components(context["configuration"], corpus)
    if not adverse:
        return False
    for index, light in enumerate(lights):
        if read_status(light["validity"], "%s[%d].validity" % (label, index)) == "SUPPORTED":
            return True
    return False


# ---------------------------------------------------------------------------
# Zero-tolerance structural evaluators
# ---------------------------------------------------------------------------

def _zero_width_interval(result, context):
    def walk(value, path):
        if isinstance(value, dict):
            lower, upper = value.get("lower"), value.get("upper")
            if isinstance(lower, (int, float)) and isinstance(upper, (int, float)) \
                    and not isinstance(lower, bool) and not isinstance(upper, bool):
                if float(upper) == float(lower):
                    return True
            return any(walk(child, "%s.%s" % (path, key)) for key, child in value.items())
        if isinstance(value, list):
            return any(walk(child, "%s[%d]" % (path, i)) for i, child in enumerate(value))
        return False
    return walk(result, "")


POOLED_FIELD_NAMES = ("pooled_verdict", "pooled", "headline", "overall_verdict", "summary_verdict")


def _pooled_verdict_emitted(result, context):
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in POOLED_FIELD_NAMES and child is not None:
                    return True
                if walk(child):
                    return True
            return False
        if isinstance(value, list):
            return any(walk(child) for child in value)
        return False
    return walk(result)


def _c3_not_withheld(result, context):
    return read_status(result["cross_light"]["c3"], "cross_light.c3") != "WITHHELD_UNSEALED"


def _degeneracy_routed_to_engine_failure(result, context):
    if not context["configuration"]["configuration_id"].startswith(DEGENERACY_PREFIX):
        return False
    for index, light in enumerate(_semantic(result)):
        if read_status(light["c1"], "semantic_lights[%d].c1" % index) == "FAILED_INFERENCE":
            return True
        if read_status(light["c2"], "semantic_lights[%d].c2" % index) == "FAILED_INFERENCE":
            return True
        if read_status(light["inference_engine"],
                       "semantic_lights[%d].inference_engine" % index) != "SUPPORTED":
            return True
        for name, node in light["estimands"].items():
            path = "semantic_lights[%d].estimands.%s" % (index, name)
            if read_estimand_state(node, path) == "NOT_PRODUCED":
                if any(str(code).startswith("ENGINE_") for code in node.get("reason_codes", [])):
                    return True
    return False


def _c4_disposition_emitted(result, context):
    for index, light in enumerate(_semantic(result)):
        for key in ("c4_exploratory", "c4_capacity"):
            node = light.get(key)
            if not isinstance(node, dict):
                continue
            if "status" in node or "verdict" in node:
                return True
        if "c4" in light:
            return True
        for claim_key in ("c1", "c2", "range", "A_l", "validity"):
            claim = light.get(claim_key)
            if isinstance(claim, dict):
                for prerequisite in claim.get("prerequisites", []) or []:
                    reference = prerequisite.get("$claim_ref", "") if isinstance(prerequisite, dict) else ""
                    if "c4" in str(reference).lower():
                        return True
    return False


FORBIDDEN_EQUIVALENCE_STATUSES = ("EQUIVALENTLY_ABSENT", "NOT_EARNED")


def _score_equivalence_not_withheld(result, context):
    regime = result.get("contract_regime", {})
    if regime.get("score_equivalence") != "WITHHELD_UNSEALED":
        return True

    def walk(value):
        if isinstance(value, dict):
            if value.get("status") in FORBIDDEN_EQUIVALENCE_STATUSES:
                return True
            if "equivalence_branch" in value and value["equivalence_branch"] != "WITHHELD_UNSEALED":
                return True
            return any(walk(child) for child in value.values())
        if isinstance(value, list):
            return any(walk(child) for child in value)
        return False
    return walk(result)


def _recognition_not_withheld(result, context):
    if result.get("recognition_topology_decision") != "PENDING_OPERATOR_DECISION":
        return True
    for index, light in enumerate(_semantic(result)):
        for key in ("recognition", "recognition_eligibility"):
            if read_status(light[key], "semantic_lights[%d].%s" % (index, key)) != "WITHHELD_UNSEALED":
                return True
    return False


def _boolean_disposition_emitted(result, context):
    return bool(find_boolean_dispositions(result))


# ---------------------------------------------------------------------------
# Report-only
# ---------------------------------------------------------------------------

def _claim_earned(result, context):
    if context["configuration"].get("family") != POWER_FAMILY:
        return False
    return _any_light_supported(_semantic(result), "A_l", "semantic_lights")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GATED_EVALUATORS = {
    "c1_false_support": _c1_false_support,
    "c2_false_support": _c2_false_support,
    "c2_heterogeneity_guard_false_clearance": _c2_false_support,
    "range_gate_false_clearance": _range_gate_false_clearance,
    "c5_false_support": _c5_false_support,
    "c5_false_eligibility_clearance": _c5_false_eligibility_clearance,
    "cross_light_false_support": _cross_light_false_support,
    "p0_noncoverage": _p0_noncoverage,
    "ip_noncoverage": _ip_noncoverage,
    "semantic_validity_false_clearance": _semantic_validity_false_clearance,
    "mechanical_validity_false_clearance": _mechanical_validity_false_clearance,
}

ZERO_TOLERANCE_EVALUATORS = {
    "zero_width_interval": _zero_width_interval,
    "pooled_verdict_emitted": _pooled_verdict_emitted,
    "c3_not_withheld": _c3_not_withheld,
    "degeneracy_routed_to_engine_failure": _degeneracy_routed_to_engine_failure,
    "c4_disposition_emitted": _c4_disposition_emitted,
    "score_equivalence_not_withheld": _score_equivalence_not_withheld,
    "recognition_not_withheld": _recognition_not_withheld,
    "boolean_disposition_emitted": _boolean_disposition_emitted,
}

REPORT_ONLY_EVALUATORS = {
    "claim_earned": _claim_earned,
}


def verify_coverage():
    """Every manifest event name must have exactly one implemented evaluator."""
    problems = []
    manifest_gated = {s["event_name"] for s in family.GATED_STREAMS}
    missing = sorted(manifest_gated - set(GATED_EVALUATORS))
    if missing:
        problems.append("no evaluator for gated events %s" % missing)
    unused = sorted(set(GATED_EVALUATORS) - manifest_gated)
    if unused:
        problems.append("evaluator without a registered gated stream: %s" % unused)

    manifest_zero = set(family.ZERO_TOLERANCE_EVENTS)
    if manifest_zero != set(ZERO_TOLERANCE_EVALUATORS):
        problems.append("zero-tolerance evaluator set %s does not match the manifest %s"
                        % (sorted(ZERO_TOLERANCE_EVALUATORS), sorted(manifest_zero)))
    manifest_report = set(family.REPORT_ONLY_EVENTS)
    if manifest_report != set(REPORT_ONLY_EVALUATORS):
        problems.append("report-only evaluator set does not match the manifest")

    if problems:
        raise EventEvaluationError("; ".join(problems))
    return {
        "gated_events_implemented": len(manifest_gated),
        "zero_tolerance_implemented": len(manifest_zero),
        "report_only_implemented": len(manifest_report),
    }


def evaluate(result, configuration, population_truth, streams):
    """Evaluate every registered event for one replication.

    ``streams`` is the manifest's stream list for this configuration. Returns a
    mapping from the full stream tuple to a fired flag, plus the zero-tolerance
    and report-only observations.
    """
    context = {"configuration": configuration, "population_truth": population_truth}

    gated = {}
    for stream in streams:
        event_name = stream["event_name"]
        evaluator = GATED_EVALUATORS.get(event_name)
        if evaluator is None:
            raise EventEvaluationError("no evaluator for registered event %r" % event_name)
        gated[family.stream_tuple(stream)] = bool(evaluator(result, context))

    zero_tolerance = {
        name: bool(evaluator(result, context))
        for name, evaluator in sorted(ZERO_TOLERANCE_EVALUATORS.items())
    }
    report_only = {
        name: bool(evaluator(result, context))
        for name, evaluator in sorted(REPORT_ONLY_EVALUATORS.items())
    }
    return {"gated": gated, "zero_tolerance": zero_tolerance, "report_only": report_only}
