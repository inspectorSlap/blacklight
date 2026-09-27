"""The adversarial check suite.

Each check returns a list of findings. A finding has a severity:

* ``FAIL``        -- a registered property was violated. One FAIL anywhere
                     yields ``ENGINE_REJECTED``.
* ``OBSERVATION`` -- something the harness records but does not treat as proof
                     of a defect, typically because an ambiguity in the
                     register prevents an exact expectation.
* ``BLOCKED``     -- the check could not run (undocumented schema, rejected
                     input). Blocks qualification without alleging a defect.

The severity split is the specificity discipline of amendment section 2: a
harness that called everything a FAIL would not be self-qualified.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import copy
import json
import math

from .. import adapter
from ..oracle import core, sample as smp
from . import rules

TOL = 1e-12
CELLS = ("00", "A0", "0B", "AB")


def finding(check, scenario_id, severity, message, evidence=None):
    return {
        "check": check,
        "scenario_id": scenario_id,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
    }


def close(a, b, tol=TOL):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def _by_id(items, key="light_id"):
    return {item[key]: item for item in items}


# ---------------------------------------------------------------------------
# 1. Point estimates against the exact oracle
# ---------------------------------------------------------------------------

POINT_FIELDS = ("P0", "PA", "I_P", "W0", "L0", "T0", "WA", "LA", "TA",
                "delta0", "deltaA", "I_delta", "p_floor_A0", "K_A", "G")
OPTIONAL_FIELDS = ("K_Q", "G_Q", "Q", "component_q0", "component_qB")


def _identify_wrong_formula(field, observed, cells, pooled=None):
    """Name the registered defect a mismatched value is consistent with."""
    candidates = []
    if field in ("P0", "PA"):
        x, y = (("00", "0B") if field == "P0" else ("A0", "AB"))
        discarded = core.ps_ties_discarded(cells[x], cells[y])
        if discarded is not None and close(observed, float(discarded), 1e-9):
            candidates.append("ties discarded (PS = W/(W+L))")
        if close(observed, float(core.ps_ties_as_wins(cells[x], cells[y])), 1e-9):
            candidates.append("ties promoted to full wins (PS = W+T)")
        if pooled is not None and close(observed, float(pooled), 1e-9):
            candidates.append("specimens pooled by calls")
    if field == "K_A":
        no_credit = 1 - core.floor_mass_from_counts(cells["A0"])
        if close(observed, float(no_credit), 1e-9):
            candidates.append("K_A computed without floor half-credit")
    if field in ("delta0", "deltaA"):
        base = core.ps_from_counts(*((cells["00"], cells["0B"])
                                     if field == "delta0"
                                     else (cells["A0"], cells["AB"])))
        if close(observed, float(base) - 0.5, 1e-9):
            candidates.append("Cliff transform computed as PS - 0.5")
    return candidates


def check_point_estimates(scenario, normalized):
    """Every point estimate must equal the independent exact oracle value."""
    findings = []
    scenario_id = scenario["scenario_id"]
    payload = scenario["payload"]
    d_near = payload["config"]["d_near"]

    for group_key, norm_key, count in (("semantic_specimens", "semantic_lights", 6),
                                       ("mechanical_specimens", "mechanical_lights", 4)):
        inputs = _by_id([{"light_id": l["id"], "specimens": l[group_key]}
                         for l in payload["lights"]])
        outputs = _by_id(normalized[norm_key])
        for light_id, light_in in sorted(inputs.items()):
            light_out = outputs.get(light_id)
            if light_out is None:
                findings.append(finding(
                    "point_estimates", scenario_id, "FAIL",
                    "light %r absent from the response" % light_id))
                continue
            cells_list = [{c: s["cells"][c]["counts"] for c in CELLS}
                          for s in light_in["specimens"]]
            truth = smp.light_truth(cells_list, d_near=d_near)
            prohibited = smp.prohibited_alternatives(cells_list)
            reported = _by_id(light_out["specimens"], "id")

            for specimen_in, metrics, cells in zip(
                    light_in["specimens"], truth["specimens"], cells_list):
                got = reported.get(specimen_in["id"])
                if got is None:
                    findings.append(finding(
                        "point_estimates", scenario_id, "FAIL",
                        "specimen %r absent from light %r"
                        % (specimen_in["id"], light_id)))
                    continue
                for field in POINT_FIELDS:
                    want = float(metrics[field])
                    if not close(got[field], want):
                        names = _identify_wrong_formula(field, got[field], cells)
                        findings.append(finding(
                            "point_estimates", scenario_id, "FAIL",
                            "%s.%s.%s = %r but the exact oracle gives %r"
                            % (light_id, specimen_in["id"], field,
                               got[field], want),
                            {"exact": core.to_exact_string(metrics[field]),
                             "observed": got[field],
                             "consistent_with": names}))
                for field in OPTIONAL_FIELDS:
                    want = metrics[field]
                    if want is None:
                        continue
                    if not close(got.get(field), float(want)):
                        names = _identify_wrong_formula(field, got.get(field), cells)
                        findings.append(finding(
                            "point_estimates", scenario_id, "FAIL",
                            "%s.%s.%s = %r but the exact oracle gives %r"
                            % (light_id, specimen_in["id"], field,
                               got.get(field), float(want)),
                            {"exact": core.to_exact_string(want),
                             "observed": got.get(field),
                             "consistent_with": names}))
                for cell in CELLS:
                    want = metrics["collision"][cell]
                    if want is None:
                        continue
                    observed = got["collision"].get(cell)
                    if not close(observed, float(want)):
                        naive = core.collision_naive(cells[cell])
                        names = (["naive squared-proportion collision"]
                                 if close(observed, float(naive), 1e-9) else [])
                        findings.append(finding(
                            "point_estimates", scenario_id, "FAIL",
                            "%s.%s.collision[%s] = %r but the exact oracle gives %r"
                            % (light_id, specimen_in["id"], cell, observed,
                               float(want)),
                            {"exact": core.to_exact_string(want),
                             "observed": observed, "consistent_with": names}))

            if norm_key == "semantic_lights":
                for field, want in (("P0_bar", truth["P0_bar"]),
                                    ("I_P_bar", truth["I_P_bar"])):
                    if not close(light_out[field], float(want)):
                        names = []
                        pooled_key = ("call_pooled_P0" if field == "P0_bar"
                                      else None)
                        if pooled_key and pooled_key in prohibited:
                            if close(light_out[field],
                                     float(prohibited[pooled_key]), 1e-9):
                                names.append("specimens pooled by calls")
                        if close(light_out[field],
                                 float(truth["specimens"][0][field[:-4]]), 1e-9):
                            names.append("aggregate replaced by the first "
                                         "specimen's effect")
                        findings.append(finding(
                            "point_estimates", scenario_id, "FAIL",
                            "%s.%s = %r but the equal-weight oracle gives %r"
                            % (light_id, field, light_out[field], float(want)),
                            {"exact": core.to_exact_string(want),
                             "observed": light_out[field],
                             "consistent_with": names}))
    return findings


# ---------------------------------------------------------------------------
# 2. Interval validity (AMB-01 necessary conditions, anchor A17)
# ---------------------------------------------------------------------------

def _interval_checks(scenario_id, label, interval, point, lo_limit, hi_limit,
                     findings):
    lo, hi = interval
    if lo > hi + TOL:
        findings.append(finding("interval_validity", scenario_id, "FAIL",
                                "%s has lower bound above upper bound" % label,
                                {"interval": interval}))
        return
    if hi - lo < 1e-9:
        findings.append(finding(
            "interval_validity", scenario_id, "FAIL",
            "%s has a prohibited zero-width finite-sample interval "
            "(width %.3g); anchor A17 routes this to INFERENCE_ENGINE_FAILURE, "
            "never to a confirmatory disposition" % (label, hi - lo),
            {"interval": interval}))
    if point is not None and not (lo - 1e-9 <= point <= hi + 1e-9):
        findings.append(finding(
            "interval_validity", scenario_id, "FAIL",
            "%s does not contain its own reported point estimate %r"
            % (label, point), {"interval": interval, "point": point}))
    if lo < lo_limit - 1e-9 or hi > hi_limit + 1e-9:
        findings.append(finding(
            "interval_validity", scenario_id, "FAIL",
            "%s leaves the physical range [%g, %g]" % (label, lo_limit, hi_limit),
            {"interval": interval}))
    for bound in interval:
        if math.isnan(bound) or math.isinf(bound):
            findings.append(finding("interval_validity", scenario_id, "FAIL",
                                    "%s contains a non-finite bound" % label,
                                    {"interval": interval}))


def check_interval_validity(scenario, normalized):
    findings = []
    scenario_id = scenario["scenario_id"]
    for light in normalized["semantic_lights"]:
        lid = light["light_id"]
        _interval_checks(scenario_id, "%s.P0_bar_interval" % lid,
                         light["P0_bar_interval"], light["P0_bar"],
                         0.0, 1.0, findings)
        _interval_checks(scenario_id, "%s.I_P_bar_interval" % lid,
                         light["I_P_bar_interval"], light["I_P_bar"],
                         -1.0, 1.0, findings)
        if light.get("Q_bar_interval") is not None:
            _interval_checks(scenario_id, "%s.Q_bar_interval" % lid,
                             light["Q_bar_interval"], light.get("Q_bar"),
                             -1.0, 1.0, findings)
        for specimen in light["specimens"]:
            _interval_checks(
                scenario_id, "%s.%s.G_interval" % (lid, specimen["id"]),
                specimen["G_interval"], specimen["G"], -1.0, 1.15, findings)
            if specimen.get("G_Q_interval") is not None:
                _interval_checks(
                    scenario_id, "%s.%s.G_Q_interval" % (lid, specimen["id"]),
                    specimen["G_Q_interval"], specimen.get("G_Q"),
                    -1.1, 1.0, findings)
    return findings


# ---------------------------------------------------------------------------
# 3. Decision consistency: the target's own numbers versus the registered rules
# ---------------------------------------------------------------------------

def check_decision_consistency(scenario, normalized):
    findings = []
    scenario_id = scenario["scenario_id"]

    for light in normalized["semantic_lights"]:
        lid = light["light_id"]
        expectations = rules.light_gate_expectations(light)

        for component, observed in (("c1", light["c1"]), ("c2", light["c2"]),
                                    ("c4", light["c4"])):
            expected = expectations.get("%s_expected" % component)
            forbidden = expectations.get("%s_forbidden" % component, set())
            if expected is not None and observed != expected:
                findings.append(finding(
                    "decision_consistency", scenario_id, "FAIL",
                    "%s.%s reported %s but the registered rule applied to the "
                    "target's own reported numbers gives %s"
                    % (lid, component, observed, expected),
                    {"reported_class": observed, "required_class": expected,
                     "computed_from": expectations}))
            elif observed in forbidden:
                findings.append(finding(
                    "decision_consistency", scenario_id, "FAIL",
                    "%s.%s reported %s, but a structural gate (validity=%s, "
                    "C1=%s, range=%s, A_l=%s) forbids any positive claim here"
                    % (lid, component, observed,
                       expectations["validity_cleared"],
                       expectations["computed_c1"],
                       expectations["computed_range_light"],
                       expectations["A_l_expected"]),
                    {"reported_class": observed,
                     "forbidden": sorted(forbidden)}))

        if light["range"] != expectations["range_expected"]:
            findings.append(finding(
                "decision_consistency", scenario_id, "FAIL",
                "%s.range reported %s but the reported per-specimen G intervals "
                "give %s under the all-six rule"
                % (lid, light["range"], expectations["range_expected"]),
                {"specimen_classes": expectations["computed_range_specimens"]}))

        for specimen, expected in zip(light["specimens"],
                                      expectations["computed_range_specimens"]):
            if specimen["range_class"] != expected:
                findings.append(finding(
                    "decision_consistency", scenario_id, "FAIL",
                    "%s.%s range disposition %s contradicts its own reported G "
                    "interval %r, which gives %s"
                    % (lid, specimen["id"], specimen["range_class"],
                       specimen["G_interval"], expected)))

        if light["A_l"] != expectations["A_l_expected"]:
            findings.append(finding(
                "decision_consistency", scenario_id, "FAIL",
                "%s.A_l reported %s but the four-way conjunction "
                "C1 AND RANGE AND VALIDITY AND C2 gives %s (anchor A19)"
                % (lid, light["A_l"], expectations["A_l_expected"]),
                {"computed": expectations}))

    mech_inputs = {l["id"]: l for l in scenario["payload"]["lights"]}
    for light in normalized["mechanical_lights"]:
        lid = light["light_id"]
        a_values = [s["I_P"] for s in light["specimens"]]
        if light["c5"] in rules.C5_CLAIM_CLASSES:
            validity = mech_inputs.get(lid, {}).get("validity", {})
            # Status-exact: a gate must be a JSON boolean. A status-bearing
            # value must never be coerced into a clearance by bool().
            for _gate, _value in sorted(validity.items()):
                if not isinstance(_value, bool):
                    raise adapter.UndocumentedSchema(
                        "%s.validity.%s" % (lid, _gate),
                        "validity gate must be a JSON boolean; a status-bearing value "
                        "must be consumed status-exactly, never coerced")
            if validity and not all(validity.values()):
                findings.append(finding(
                    "decision_consistency", scenario_id, "FAIL",
                    "%s.c5 emitted %s although the light fails a structural "
                    "validity gate" % (lid, light["c5"])))
            ranges = [rules.range_class(s["G_interval"]) for s in light["specimens"]]
            if not all(r == "RANGE_ADEQUATE" for r in ranges):
                findings.append(finding(
                    "decision_consistency", scenario_id, "FAIL",
                    "%s.c5 emitted %s although the all-four control range "
                    "requirement is not met: %s" % (lid, light["c5"], ranges)))
    return findings


# ---------------------------------------------------------------------------
# 4. Cross-light structure (anchors A20, AMB-04)
# ---------------------------------------------------------------------------

def check_cross_light(scenario, normalized):
    findings = []
    scenario_id = scenario["scenario_id"]
    cross = normalized["cross_light"]
    vector = [light["A_l"] for light in normalized["semantic_lights"]]

    if cross["A_vector"] != vector:
        findings.append(finding(
            "cross_light", scenario_id, "FAIL",
            "cross_light.A_vector %r disagrees with the per-light A_l values %r"
            % (cross["A_vector"], vector)))
    if cross["A_all"] != all(vector):
        findings.append(finding(
            "cross_light", scenario_id, "FAIL",
            "A_all reported %s but A_all is the conjunction of the three "
            "light claims %r, which is %s (anchor A20)"
            % (cross["A_all"], vector, all(vector))))
    if cross["pooled_verdict"] is not None:
        findings.append(finding(
            "cross_light", scenario_id, "FAIL",
            "an unregistered pooled cross-light verdict %r was emitted; the "
            "light vector is the primary reported object and no pooled "
            "headline may replace it" % (cross["pooled_verdict"],),
            {"pooled_verdict": cross["pooled_verdict"]}))
    if cross["c3"] != "C3_WITHHELD":
        findings.append(finding(
            "cross_light", scenario_id, "FAIL",
            "C3 reported %r but C3 remains withheld in this engine version "
            "(locked contract section 6) and its cross-light equivalence "
            "margin and procedure are unsealed; emitting any cross-light "
            "stability disposition is an unregistered claim"
            % (cross["c3_raw"],),
            {"c3_raw": cross["c3_raw"], "c3_class": cross["c3"]}))
    return findings


# ---------------------------------------------------------------------------
# 5. Frozen expected dispositions
# ---------------------------------------------------------------------------

EXPECTED_CLASS = dict(adapter.DISPOSITION_CLASSES)


def check_expected_dispositions(scenario, normalized, strict):
    """Compare against the frozen preregistered expectation for the scenario.

    `strict` is true for the sound reference (the specificity leg requires the
    reference to return the preregistered disposition for every scenario) and
    for scenarios whose assertion strength is ABSOLUTE. For REFERENCE_ONLY
    scenarios evaluated against a third-party target, a disagreement is an
    OBSERVATION, because the disposition can legitimately depend on the
    unsealed confidence-region construction (AMB-01).
    """
    findings = []
    scenario_id = scenario["scenario_id"]
    severity = "FAIL" if (strict or scenario["assertion_strength"] == "ABSOLUTE") \
        else "OBSERVATION"
    expected = scenario["expected"]
    outputs = _by_id(normalized["semantic_lights"])

    for entry in expected["semantic_lights"]:
        light = outputs.get(entry["light_id"])
        if light is None:
            findings.append(finding("expected_dispositions", scenario_id, "FAIL",
                                    "light %r missing" % entry["light_id"]))
            continue
        for key in ("c1", "range", "c2", "c4"):
            want = EXPECTED_CLASS.get(entry[key], entry[key])
            if light[key] != want:
                findings.append(finding(
                    "expected_dispositions", scenario_id, severity,
                    "%s.%s expected %s but observed %s"
                    % (entry["light_id"], key, entry[key], light["%s_raw" % key]),
                    {"expected_class": want, "observed_class": light[key]}))
        if light["A_l"] != entry["A_l"]:
            findings.append(finding(
                "expected_dispositions", scenario_id, severity,
                "%s.A_l expected %s but observed %s"
                % (entry["light_id"], entry["A_l"], light["A_l"])))

    mech_outputs = _by_id(normalized["mechanical_lights"])
    for entry in expected["mechanical_lights"]:
        light = mech_outputs.get(entry["light_id"])
        if light is None:
            continue
        want = EXPECTED_CLASS.get(entry["c5"], entry["c5"])
        if light["c5"] != want:
            findings.append(finding(
                "expected_dispositions", scenario_id, severity,
                "%s.c5 expected %s but observed %s"
                % (entry["light_id"], entry["c5"], light["c5_raw"])))

    cross = expected["cross_light"]
    if normalized["cross_light"]["A_all"] != cross["A_all"]:
        findings.append(finding(
            "expected_dispositions", scenario_id, severity,
            "A_all expected %s but observed %s"
            % (cross["A_all"], normalized["cross_light"]["A_all"])))
    return findings


# ---------------------------------------------------------------------------
# 6. Invariance and determinism (amendment section 5)
# ---------------------------------------------------------------------------

def _scientific_body(result):
    """Response content that must be identical under an exact repeat.

    Audit timestamps and transport headers are outside the equality rule
    (amendment section 5), so anything matching a timestamp-like key is
    stripped before comparison.
    """
    stripped = copy.deepcopy(result)

    def strip(node):
        if isinstance(node, dict):
            for key in list(node):
                if any(token in key.lower() for token in
                       ("timestamp", "elapsed", "duration", "request_id",
                        "received_at", "generated_at")):
                    del node[key]
                else:
                    strip(node[key])
        elif isinstance(node, list):
            for item in node:
                strip(item)

    strip(stripped)
    return json.dumps(stripped, sort_keys=True)


def _light_summary(normalized):
    return {
        light["light_id"]: {
            "c1": light["c1"], "c2": light["c2"], "range": light["range"],
            "c4": light["c4"], "A_l": light["A_l"],
            "P0_bar": round(light["P0_bar"], 12),
            "I_P_bar": round(light["I_P_bar"], 12),
        }
        for light in normalized["semantic_lights"]
    }


def occupied_categories(payload):
    """Every category carrying mass anywhere in the payload."""
    seen = set()
    for light in payload["lights"]:
        for key in ("semantic_specimens", "mechanical_specimens"):
            for specimen in light[key]:
                for cell in CELLS:
                    counts = specimen["cells"][cell]["counts"]
                    for index, value in enumerate(counts):
                        if value:
                            seen.add(index + 1)
    return sorted(seen)


def monotone_relabeling(occupied):
    """A non-trivial strictly increasing relabeling of the occupied categories.

    A strictly increasing bijection of {1..10} onto itself is necessarily the
    identity, so a non-trivial monotone relabeling must move the occupied
    categories onto a different increasing subset. Here they are compressed
    onto 1..k in order, which preserves every pairwise ordering and therefore
    must leave PS, W, L and T unchanged (anchor A15). Unoccupied categories are
    assigned the leftover labels purely to keep the mapping injective; they
    carry no mass and cannot affect any estimate.
    """
    if not occupied or len(occupied) >= 10:
        return None
    targets = list(range(1, len(occupied) + 1))
    if targets == occupied:
        # already compressed; shift upward instead, still strictly increasing
        if occupied[-1] + 1 > 10:
            return None
        targets = [c + 1 for c in occupied]
    mapping = dict(zip(occupied, targets))
    leftovers = [c for c in range(1, 11) if c not in targets]
    for category in range(1, 11):
        if category not in mapping:
            mapping[category] = leftovers.pop(0)
    return mapping


def check_invariance(target, scenario):
    """Determinism, order invariance and relabeling invariance."""
    findings = []
    scenario_id = scenario["scenario_id"]
    payload = scenario["payload"]

    try:
        first = target.analyze(copy.deepcopy(payload))
        second = target.analyze(copy.deepcopy(payload))
    except Exception as exc:  # pragma: no cover - surfaced as BLOCKED
        return [finding("invariance", scenario_id, "BLOCKED",
                        "repeat call failed: %s" % exc)]

    if _scientific_body(first) != _scientific_body(second):
        findings.append(finding(
            "invariance", scenario_id, "FAIL",
            "an exact repeat produced a different scientific body; the v0.1 "
            "target is declared deterministic (amendment section 5) and an "
            "undeclared stochastic target is not eligible for black-box "
            "qualification"))

    base = adapter.normalize(first)

    # (a) specimen order permutation
    permuted = copy.deepcopy(payload)
    for light in permuted["lights"]:
        light["semantic_specimens"] = list(reversed(light["semantic_specimens"]))
        light["mechanical_specimens"] = list(
            reversed(light["mechanical_specimens"]))
    try:
        permuted_norm = adapter.normalize(target.analyze(permuted))
        if _light_summary(permuted_norm) != _light_summary(base):
            findings.append(finding(
                "invariance", scenario_id, "FAIL",
                "reversing the specimen order changed a light-level result; "
                "the estimand is an equal-weight mean over a fixed corpus and "
                "is order-invariant",
                {"base": _light_summary(base),
                 "permuted": _light_summary(permuted_norm)}))
    except adapter.UndocumentedSchema as exc:
        findings.append(finding("invariance", scenario_id, "BLOCKED",
                                "specimen-permutation response unmapped: %s" % exc))

    # (b) light order permutation
    permuted = copy.deepcopy(payload)
    permuted["lights"] = list(reversed(permuted["lights"]))
    try:
        permuted_norm = adapter.normalize(target.analyze(permuted))
        if _light_summary(permuted_norm) != _light_summary(base):
            findings.append(finding(
                "invariance", scenario_id, "FAIL",
                "reversing the light order changed a per-light result; each "
                "light must receive its own result independently",
                {"base": _light_summary(base),
                 "permuted": _light_summary(permuted_norm)}))
    except adapter.UndocumentedSchema as exc:
        findings.append(finding("invariance", scenario_id, "BLOCKED",
                                "light-permutation response unmapped: %s" % exc))

    # (c) strictly monotone category relabeling: PS and collision invariant
    mono = monotone_relabeling(occupied_categories(payload))
    relabeled = copy.deepcopy(payload)
    ok = mono is not None
    if ok:
        for light in relabeled["lights"]:
            for key in ("semantic_specimens", "mechanical_specimens"):
                for specimen in light[key]:
                    for cell in CELLS:
                        try:
                            specimen["cells"][cell]["counts"] = smp.relabel_counts(
                                specimen["cells"][cell]["counts"], mono)
                        except core.OracleError:
                            ok = False
    if ok:
        try:
            relabeled_norm = adapter.normalize(target.analyze(relabeled))
            for base_light, new_light in zip(base["semantic_lights"],
                                             relabeled_norm["semantic_lights"]):
                for base_s, new_s in zip(base_light["specimens"],
                                         new_light["specimens"]):
                    for field in ("P0", "PA", "I_P", "W0", "L0", "T0"):
                        if not close(base_s[field], new_s[field], 1e-9):
                            findings.append(finding(
                                "invariance", scenario_id, "FAIL",
                                "%s.%s.%s changed under a strictly monotone "
                                "category relabeling (%r -> %r); probability of "
                                "superiority is invariant to every strictly "
                                "monotone relabeling (anchor A15)"
                                % (base_light["light_id"], base_s["id"], field,
                                   base_s[field], new_s[field])))
                    for cell in CELLS:
                        if not close(base_s["collision"][cell],
                                     new_s["collision"][cell], 1e-9):
                            findings.append(finding(
                                "invariance", scenario_id, "FAIL",
                                "%s.%s collision[%s] changed under a category "
                                "relabeling; collision probability depends only "
                                "on the multiset of masses (anchor A15)"
                                % (base_light["light_id"], base_s["id"], cell)))
        except adapter.UndocumentedSchema as exc:
            findings.append(finding("invariance", scenario_id, "BLOCKED",
                                    "relabeled response unmapped: %s" % exc))
    return findings


def check_alpha_nesting(target, scenario):
    """A tighter alpha must not widen the set of positive claims (AMB-01.4)."""
    findings = []
    scenario_id = scenario["scenario_id"]
    tight = copy.deepcopy(scenario["payload"])
    for key in ("primary", "c4", "c5"):
        tight["config"]["alpha"][key] = tight["config"]["alpha"][key] / 5.0
    try:
        base = adapter.normalize(target.analyze(copy.deepcopy(scenario["payload"])))
        tighter = adapter.normalize(target.analyze(tight))
    except adapter.UndocumentedSchema as exc:
        return [finding("interval_validity", scenario_id, "BLOCKED",
                        "alpha-nesting response unmapped: %s" % exc)]
    except Exception as exc:
        return [finding("interval_validity", scenario_id, "BLOCKED",
                        "alpha-nesting call failed: %s" % exc)]

    for base_light, tight_light in zip(base["semantic_lights"],
                                       tighter["semantic_lights"]):
        lo_b, hi_b = base_light["P0_bar_interval"]
        lo_t, hi_t = tight_light["P0_bar_interval"]
        if lo_t > lo_b + 1e-9 or hi_t < hi_b - 1e-9:
            findings.append(finding(
                "interval_validity", scenario_id, "FAIL",
                "%s.P0_bar_interval at a five-fold tighter alpha is not nested "
                "outside the original interval: %r vs %r"
                % (base_light["light_id"], tight_light["P0_bar_interval"],
                   base_light["P0_bar_interval"])))
        for component in ("c1", "c2", "c4"):
            if (tight_light[component] in rules.CLAIM_CLASSES
                    | rules.C4_CLAIM_CLASSES
                    and base_light[component] not in rules.CLAIM_CLASSES
                    | rules.C4_CLAIM_CLASSES):
                findings.append(finding(
                    "interval_validity", scenario_id, "FAIL",
                    "%s.%s earns %s at the tighter alpha but only %s at the "
                    "looser one; tightening alpha must never create a claim"
                    % (base_light["light_id"], component,
                       tight_light[component], base_light[component])))
    return findings


def check_interval_scaling(target, scenario):
    """Detect faster-than-root-n interval shrinkage on interior data.

    Replicating every count vector k-fold leaves every point estimate exactly
    unchanged while multiplying the sample size by k. For any valid interval on
    a bounded functional with non-degenerate variance, the width must shrink no
    faster than the parametric rate, so

        width(k n) / width(n)  ~  1 / sqrt(k)  = 0.5  at k = 4.

    A target that treats the n_X * n_Y cross-pairs as independent observations
    shrinks at 1/k = 0.25 instead. The threshold below sits at the geometric
    midpoint of the two rates, sqrt(0.25 * 0.5) = 0.354, so it separates them
    while leaving ordinary conservatism untouched.

    The check runs ONLY on scenarios whose cells are interior and
    non-degenerate. That restriction is essential rather than cosmetic: exact
    boundary methods such as Clopper-Pearson legitimately shrink like 1/n at a
    point mass, so applying this rule to a degenerate cell would manufacture a
    false accusation.
    """
    findings = []
    scenario_id = scenario["scenario_id"]
    if not scenario.get("interval_scaling_eligible"):
        return findings

    factor = 4
    scaled = copy.deepcopy(scenario["payload"])
    for light in scaled["lights"]:
        for key in ("semantic_specimens", "mechanical_specimens"):
            for specimen in light[key]:
                for cell in CELLS:
                    specimen["cells"][cell]["counts"] = smp.scale_counts(
                        specimen["cells"][cell]["counts"], factor)
    try:
        base = adapter.normalize(target.analyze(copy.deepcopy(scenario["payload"])))
        bigger = adapter.normalize(target.analyze(scaled))
    except adapter.UndocumentedSchema as exc:
        return [finding("interval_validity", scenario_id, "BLOCKED",
                        "scaled response unmapped: %s" % exc)]
    except Exception as exc:
        return [finding("interval_validity", scenario_id, "BLOCKED",
                        "scaled call failed: %s" % exc)]

    floor_ratio = math.sqrt(0.25 * 0.5)
    for base_light, big_light in zip(base["semantic_lights"],
                                     bigger["semantic_lights"]):
        for field in ("P0_bar_interval", "I_P_bar_interval"):
            base_width = base_light[field][1] - base_light[field][0]
            big_width = big_light[field][1] - big_light[field][0]
            if base_width <= 1e-9:
                continue
            ratio = big_width / base_width
            if ratio < floor_ratio:
                findings.append(finding(
                    "interval_validity", scenario_id, "FAIL",
                    "%s.%s shrinks by a factor of %.4f when every count vector "
                    "is replicated %d-fold; a valid interval on interior data "
                    "shrinks no faster than 1/sqrt(%d) = %.3f. A ratio near "
                    "1/%d = %.3f is the signature of treating the n_X*n_Y "
                    "cross-pairs as independent observations"
                    % (base_light["light_id"], field, ratio, factor, factor,
                       1.0 / math.sqrt(factor), factor, 1.0 / factor),
                    {"base_width": base_width, "scaled_width": big_width,
                     "ratio": ratio, "root_n_ratio": 1.0 / math.sqrt(factor),
                     "independent_pairs_ratio": 1.0 / factor}))
    return findings


def check_c4_noninterference(target, scenario_a, scenario_b):
    """Anchor A19: concentration structure must not move C1, range or C2."""
    scenario_id = "%s|%s" % (scenario_a["scenario_id"], scenario_b["scenario_id"])
    try:
        left = adapter.normalize(target.analyze(copy.deepcopy(scenario_a["payload"])))
        right = adapter.normalize(target.analyze(copy.deepcopy(scenario_b["payload"])))
    except adapter.UndocumentedSchema as exc:
        return [finding("c4_noninterference", scenario_id, "BLOCKED",
                        "response unmapped: %s" % exc)]

    findings = []
    for light_l, light_r in zip(left["semantic_lights"], right["semantic_lights"]):
        for field in ("c1", "range", "c2", "A_l"):
            if light_l[field] != light_r[field]:
                findings.append(finding(
                    "c4_noninterference", scenario_id, "FAIL",
                    "%s.%s differs across the non-interference pair (%s vs %s) "
                    "although P0, PA, I_P, p_floor,A0 and G are identical by "
                    "construction; C4 structure must never alter, protect, "
                    "rescue or invalidate C2 (anchor A19, amendment section 3)"
                    % (light_l["light_id"], field, light_l[field], light_r[field])))
        for field in ("P0_bar", "I_P_bar"):
            if not close(light_l[field], light_r[field], 1e-9):
                findings.append(finding(
                    "c4_noninterference", scenario_id, "FAIL",
                    "%s.%s differs across the non-interference pair (%r vs %r)"
                    % (light_l["light_id"], field, light_l[field], light_r[field])))
        for spec_l, spec_r in zip(light_l["specimens"], light_r["specimens"]):
            for field in ("P0", "PA", "I_P", "p_floor_A0", "K_A", "G"):
                if not close(spec_l[field], spec_r[field], 1e-9):
                    findings.append(finding(
                        "c4_noninterference", scenario_id, "FAIL",
                        "%s.%s.%s differs across the non-interference pair"
                        % (light_l["light_id"], spec_l["id"], field)))
    return findings
