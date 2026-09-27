"""Verification of the hand-computed anchors (amendment section 4).

Three independent artifacts must each reproduce the same immutable hand
calculations:

1. the exact oracle  -- `verify_oracle()`, symbolic, exact rational equality;
2. the sound reference and any other target -- `verify_target()`, by running the
   anchor-realization panel and comparing reported values;
3. the harness's own decision rules -- covered by the structural anchors, which
   `harness.selfqual` asserts through the clean and mutant panels.

Any disagreement among them blocks self-qualification and must not be resolved
by consulting the real target.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os
from fractions import Fraction

from .. import adapter
from ..oracle import core, population as pop
from .checks import finding

ANCHOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "fixtures", "anchors", "hand-anchors-v1.0.json")


def load_anchors(path=ANCHOR_PATH):
    with open(path, "r") as handle:
        return json.load(handle)


def _fraction(text):
    return Fraction(text)


def _counts(vector):
    return [int(v) for v in vector]


# ---------------------------------------------------------------------------
# Symbolic verification of the oracle
# ---------------------------------------------------------------------------

def _evaluate(anchor):
    """Compute the anchor's quantities with the independent exact oracle."""
    inputs = anchor["inputs"]
    kind = inputs["kind"]

    if kind == "point_mass_pair":
        x = [0] * core.K
        y = [0] * core.K
        x[inputs["x_category"] - 1] = 1
        y[inputs["y_category"] - 1] = 1
        w, l, t = core.wlt_from_counts(x, y)
        ps = core.ps_from_wlt(w, l, t)
        return {"W": w, "L": l, "T": t, "PS": ps,
                "cliff_delta": core.cliff_delta(ps)}

    if kind == "transform":
        ps = _fraction(inputs["PS"])
        return {"cliff_delta": core.cliff_delta(ps)}

    if kind == "transform_interaction":
        return {"I_delta": 2 * _fraction(inputs["I_P"])}

    if kind == "transform_region":
        return {"cliff_lo": core.cliff_delta(_fraction(inputs["lo"])),
                "cliff_hi": core.cliff_delta(_fraction(inputs["hi"]))}

    if kind == "counts":
        counts = _counts(inputs["counts"])
        return {"C_hat": core.collision_from_counts(counts)}

    if kind == "capacity":
        floor = _fraction(inputs["p_floor_A0"])
        return {"K_A": core.capacity_K_A(floor),
                "K_A_cliff": core.capacity_K_A_cliff(floor)}

    if kind == "cell_pair":
        if "A0_counts" in inputs:
            a0 = _counts(inputs["A0_counts"])
            ab = _counts(inputs["AB_counts"])
            floor = core.floor_mass_from_counts(a0)
            pa = core.ps_from_counts(a0, ab)
            return {"p_floor_A0": floor, "K_A": core.capacity_K_A(floor),
                    "PA": pa, "cliff_delta_A": core.cliff_delta(pa)}
        x = _counts(inputs["X_counts"])
        y = _counts(inputs["Y_counts"])
        w, l, t = core.wlt_from_counts(x, y)
        ps = core.ps_from_wlt(w, l, t)
        return {"W": w, "L": l, "T": t, "PS": ps,
                "cliff_delta": core.cliff_delta(ps)}

    if kind == "range_surplus":
        k_a = core.capacity_K_A(_fraction(inputs["p_floor_A0"]))
        return {"K_A": k_a,
                "G": core.range_surplus_G(k_a, _fraction(inputs["P0"]),
                                          _fraction(inputs["M_I"]))}

    if kind == "concentration_capacity":
        k_q = core.capacity_K_Q(_fraction(inputs["C_00"]), _fraction(inputs["C_0B"]))
        return {"K_Q": k_q,
                "G_Q": core.concentration_surplus_G_Q(k_q,
                                                      _fraction(inputs["M_C"]))}

    if kind == "two_specimen_aggregate":
        s1 = inputs["specimen_1"]
        s2 = inputs["specimen_2"]
        ps1 = core.ps_from_counts(_counts(s1["00_counts"]), _counts(s1["0B_counts"]))
        ps2 = core.ps_from_counts(_counts(s2["00_counts"]), _counts(s2["0B_counts"]))
        cells = [{"00": _counts(s1["00_counts"]), "0B": _counts(s1["0B_counts"])},
                 {"00": _counts(s2["00_counts"]), "0B": _counts(s2["0B_counts"])}]
        return {"PS_specimen_1": ps1, "PS_specimen_2": ps2,
                "equal_weight_mean": core.equal_weight_mean([ps1, ps2]),
                "call_pooled": core.pooled_by_calls_PS(cells, "00", "0B")}

    raise ValueError("unknown anchor input kind %r" % kind)


def verify_oracle(anchors=None):
    """Exact rational comparison of the oracle against every numeric anchor."""
    anchors = anchors or load_anchors()
    findings = []
    checked = 0
    for anchor in anchors["numeric_anchors"]:
        computed = _evaluate(anchor)
        for key, text in anchor["expected"].items():
            want = _fraction(text)
            got = computed.get(key)
            checked += 1
            if got is None:
                findings.append(finding(
                    "anchors", anchor["id"], "FAIL",
                    "oracle produced no value for %s" % key))
            elif Fraction(got) != want:
                findings.append(finding(
                    "anchors", anchor["id"], "FAIL",
                    "oracle gives %s = %s but the hand derivation fixes %s; a "
                    "disagreement between the oracle and the hand calculation "
                    "blocks self-qualification and must not be resolved by "
                    "consulting the target"
                    % (key, core.to_exact_string(Fraction(got)), text),
                    {"derivation": anchor["derivation"]}))
        for key, text in (anchor.get("prohibited_alternative") or {}).items():
            want = _fraction(text)
            got = computed.get(_PROHIBITED_KEYS.get(key, key))
            if got is not None and Fraction(got) != want:
                findings.append(finding(
                    "anchors", anchor["id"], "OBSERVATION",
                    "the recorded prohibited value %s = %s was not reproduced "
                    "(oracle gives %s); the harness can still detect the defect "
                    "but cannot name it positively"
                    % (key, text, core.to_exact_string(Fraction(got)))))
    return findings, checked


_PROHIBITED_KEYS = {
    "naive_squared_proportion": "C_naive",
    "call_pooled_PS": "call_pooled",
    "no_half_credit": "K_A_no_half_credit",
    "ties_discarded": "PS_ties_discarded",
    "ties_as_wins": "PS_ties_as_wins",
}


def verify_structural_anchors(anchors=None):
    """Confirm that every structural anchor has an owning harness check."""
    anchors = anchors or load_anchors()
    owners = {
        "A02.complement_identity": "point_estimates",
        "A03.wlt_partition": "point_estimates",
        "A06.collision_formula": "point_estimates",
        "A15.monotone_relabel_invariance": "invariance",
        "A16.first_valid_selection": "archive_invariants",
        "A16.attempt_order_invariance": "archive_invariants",
        "A17.no_zero_width_interval": "interval_validity",
        "A18.guards_withhold_only": "decision_consistency",
        "A19.attenuation_chain": "decision_consistency",
        "A19.c4_noninterference": "c4_noninterference",
        "A20.a_all_conjunction": "cross_light",
    }
    findings = []
    for anchor in anchors["structural_anchors"]:
        if anchor["id"] not in owners:
            findings.append(finding(
                "anchors", anchor["id"], "FAIL",
                "structural anchor has no owning harness check; an unowned "
                "anchor is an untested requirement"))
    return findings, owners


# ---------------------------------------------------------------------------
# Target verification through the anchor-realization panel
# ---------------------------------------------------------------------------

def _lookup(normalized, group, specimen_id, field):
    key = "semantic_lights" if group == "semantic" else "mechanical_lights"
    light = normalized[key][0]
    for specimen in light["specimens"]:
        if specimen["id"] == specimen_id:
            if field.startswith("collision."):
                return specimen["collision"].get(field.split(".", 1)[1])
            return specimen.get(field)
    return None


def verify_target(target, scenario):
    """Check a target's reported values directly against the hand anchors."""
    findings = []
    try:
        raw = target.analyze(scenario["payload"])
    except Exception as exc:
        return [finding("anchors", scenario["scenario_id"], "BLOCKED",
                        "target rejected the anchor panel: %s" % exc)]
    try:
        normalized = adapter.normalize(raw)
    except adapter.UndocumentedSchema as exc:
        return [finding("anchors", scenario["scenario_id"], "BLOCKED",
                        "anchor-panel response unmapped: %s" % exc)]

    for assertion in scenario["anchor_assertions"]:
        want = float(_fraction(assertion["exact"]))
        got = _lookup(normalized, assertion["group"], assertion["specimen"],
                      assertion["field"])
        if got is None:
            findings.append(finding(
                "anchors", scenario["scenario_id"], "FAIL",
                "target reported no value for %s.%s (anchor %s)"
                % (assertion["specimen"], assertion["field"],
                   assertion["anchor"])))
            continue
        if abs(float(got) - want) > 1e-12:
            named = []
            for label, text in (assertion.get("prohibited") or {}).items():
                if abs(float(got) - float(_fraction(text))) <= 1e-9:
                    named.append(label)
            findings.append(finding(
                "anchors", scenario["scenario_id"], "FAIL",
                "target reports %s.%s = %r but hand anchor %s fixes %s (= %r)"
                % (assertion["specimen"], assertion["field"], got,
                   assertion["anchor"], assertion["exact"], want),
                {"anchor": assertion["anchor"], "observed": got,
                 "required_exact": assertion["exact"],
                 "consistent_with": named}))
    return findings
