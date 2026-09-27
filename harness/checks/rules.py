"""Registered decision rules, implemented independently for auditing.

This is the harness's THIRD implementation of the ordinal-profile topology, after the exact
oracle (point estimates) and the sound reference (a complete target). It exists
so the harness can answer one question without any reference to how the target
was built:

    Given the numbers the target itself reported, is the disposition it emitted
    the one the registered rules assign to those numbers?

That question is answerable even though the confidence-region construction is
unsealed (AMB-01), because the rules are stated on *the interval*, whatever
interval the target chose to produce. It is the strongest total check available
over the decision topology, and it is exactly what a target cannot satisfy
while quietly relabelling its own outputs.

Where the distribution forces an answer, `expected_class` is returned and the
harness asserts equality. Where it does not, `forbidden_classes` is returned
and the harness asserts only non-membership. Both come from the same rules,
derived here from preregistration sections 4, 5.3, 5.5, 5.6 and 12.3.
"""

# Frozen thresholds, preregistration section 3.4.
C1_BOUNDARY = 0.70
C1_EQ_LO, C1_EQ_HI = 0.45, 0.55
M_I_P = 0.15
E_I_P = 0.05
M_C = 0.10
E_C = 0.05
C1_CANCEL = 0.20
C2_CANCEL = 0.15
C4_CANCEL = 0.10

CLAIM_CLASSES = {"SUPPORTED", "EQUIVALENTLY_ABSENT"}
C4_CLAIM_CLASSES = {"C4_SUPPORTED", "C4_EQUIVALENTLY_ABSENT"}
C5_CLAIM_CLASSES = {"C5_SUPPORTED", "C5_EQUIVALENTLY_ABSENT"}

TOL = 1e-12


def _leave_one_out(values):
    n = len(values)
    total = sum(values)
    return [(total - values[i]) / float(n - 1) for i in range(n)]


def _ge(a, b):
    return a >= b - TOL


def _le(a, b):
    return a <= b + TOL


def c1_class(interval, b_values):
    """Semantic class the registered C1 rule assigns to these numbers."""
    lo, hi = interval
    loo = _leave_one_out(b_values)
    recurrence = sum(1 for v in b_values if v > TOL) >= 4
    anti_singleton = all(v > TOL for v in loo)
    equivalence_loo = all(_ge(v, -E_I_P) and _le(v, E_I_P) for v in loo)
    cancellation = (any(_ge(v, C1_CANCEL) for v in b_values)
                    and any(_le(v, -C1_CANCEL) for v in b_values))
    if _ge(lo, C1_BOUNDARY):
        return "SUPPORTED" if (recurrence and anti_singleton) else "GUARD_NOT_MET"
    if _ge(lo, C1_EQ_LO) and _le(hi, C1_EQ_HI):
        if equivalence_loo and not cancellation:
            return "EQUIVALENTLY_ABSENT"
        return "HETEROGENEITY_NOT_CLEARED"
    return "INDETERMINATE"


def c2_class(interval, a_values):
    lo, hi = interval
    loo = _leave_one_out(a_values)
    recurrence = sum(1 for v in a_values if v > TOL) >= 4
    anti_singleton = all(v > TOL for v in loo)
    equivalence_loo = all(_ge(v, -E_I_P) and _le(v, E_I_P) for v in loo)
    cancellation = (any(_ge(v, C2_CANCEL) for v in a_values)
                    and any(_le(v, -C2_CANCEL) for v in a_values))
    if _ge(lo, M_I_P):
        return "SUPPORTED" if (recurrence and anti_singleton) else "GUARD_NOT_MET"
    if _ge(lo, -E_I_P) and _le(hi, E_I_P):
        if equivalence_loo and not cancellation:
            return "EQUIVALENTLY_ABSENT"
        return "HETEROGENEITY_NOT_CLEARED"
    return "INDETERMINATE"


def c5_class(interval, a_values):
    """Mechanical controls use a three-of-four recurrence rule (section 5.6)."""
    lo, hi = interval
    loo = _leave_one_out(a_values)
    recurrence = sum(1 for v in a_values if v > TOL) >= 3
    anti_singleton = all(v > TOL for v in loo)
    equivalence_loo = all(_ge(v, -E_I_P) and _le(v, E_I_P) for v in loo)
    cancellation = (any(_ge(v, C2_CANCEL) for v in a_values)
                    and any(_le(v, -C2_CANCEL) for v in a_values))
    if _ge(lo, M_I_P):
        return "C5_SUPPORTED" if (recurrence and anti_singleton) else "C5_GUARD_NOT_MET"
    if _ge(lo, -E_I_P) and _le(hi, E_I_P):
        if equivalence_loo and not cancellation:
            return "C5_EQUIVALENTLY_ABSENT"
        return "C5_HETEROGENEITY_NOT_CLEARED"
    return "C5_INDETERMINATE"


def range_class(interval):
    """Section 5.3 dispositions, stated on the interval for G (anchor A11)."""
    lo, hi = interval
    if lo > TOL:
        return "RANGE_ADEQUATE"
    if hi < -TOL:
        return "FLOOR_LIMITED"
    return "RANGE_INDETERMINATE"


def concentration_range_class(interval):
    lo, hi = interval
    if lo > TOL:
        return "CONCENTRATION_RANGE_ADEQUATE"
    if hi < -TOL:
        return "CONCENTRATION_RANGE_LIMITED"
    return "CONCENTRATION_RANGE_INDETERMINATE"


def c4_class(interval, q_values, q0_bar, qb_bar):
    lo, hi = interval
    loo = _leave_one_out(q_values)
    components_positive = q0_bar > TOL and qb_bar > TOL
    components_in_band = (_ge(q0_bar, -E_C) and _le(q0_bar, E_C)
                          and _ge(qb_bar, -E_C) and _le(qb_bar, E_C))
    recurrence = sum(1 for v in q_values if v > TOL) >= 4
    anti_singleton = all(v > TOL for v in loo)
    equivalence_loo = all(_ge(v, -E_C) and _le(v, E_C) for v in loo)
    cancellation = (any(_ge(v, C4_CANCEL) for v in q_values)
                    and any(_le(v, -C4_CANCEL) for v in q_values))
    if _ge(lo, M_C):
        if components_positive and recurrence and anti_singleton:
            return "C4_SUPPORTED"
        return "C4_GUARD_NOT_MET"
    if _ge(lo, -E_C) and _le(hi, E_C):
        if components_in_band and equivalence_loo and not cancellation:
            return "C4_EQUIVALENTLY_ABSENT"
        return "C4_HETEROGENEITY_NOT_CLEARED"
    return "C4_INDETERMINATE"


# ---------------------------------------------------------------------------
# Gate structure (anchor A19)
# ---------------------------------------------------------------------------

def light_gate_expectations(light):
    """What the registered chain forces for one normalized semantic light.

    Returns a dict describing, for each component, either an exact expected
    class or a set of forbidden classes. Ambiguities recorded in the ambiguity
    register become forbidden-class assertions rather than equalities.
    """
    validity_cleared = light.get("validity_cleared")
    engine_ok = light.get("inference_engine_status") in (None, "OK")

    b_values = [s["P0"] - 0.5 for s in light["specimens"]]
    a_values = [s["I_P"] for s in light["specimens"]]

    out = {
        "computed_c1": c1_class(light["P0_bar_interval"], b_values),
        "computed_c2": c2_class(light["I_P_bar_interval"], a_values),
        "computed_range_specimens": [range_class(s["G_interval"])
                                     for s in light["specimens"]],
        "validity_cleared": validity_cleared,
        "engine_ok": engine_ok,
    }
    out["computed_range_light"] = (
        "RANGE_CLEARED"
        if all(c == "RANGE_ADEQUATE" for c in out["computed_range_specimens"])
        else "RANGE_NOT_CLEARED")

    # C1: forced exactly when no structural gate has pre-empted it.
    if validity_cleared is False or not engine_ok:
        out["c1_expected"] = None
        out["c1_forbidden"] = set(CLAIM_CLASSES)
    else:
        out["c1_expected"] = out["computed_c1"]
        out["c1_forbidden"] = set()

    # Range is a pure function of the reported G intervals.
    out["range_expected"] = out["computed_range_light"]

    # C2 opens only after validity, C1 support and the all-six range gate.
    gates_open = (validity_cleared is not False and engine_ok
                  and out["computed_c1"] == "SUPPORTED"
                  and out["computed_range_light"] == "RANGE_CLEARED")
    if gates_open:
        out["c2_expected"] = out["computed_c2"]
        out["c2_forbidden"] = set()
    else:
        out["c2_expected"] = None
        out["c2_forbidden"] = set(CLAIM_CLASSES)
    out["c2_gates_open"] = gates_open

    out["A_l_expected"] = bool(
        validity_cleared is not False and engine_ok
        and out["computed_c1"] == "SUPPORTED"
        and out["computed_range_light"] == "RANGE_CLEARED"
        and out["computed_c2"] == "SUPPORTED")

    # C4 opens only for a light with supported A_l, and then only when every
    # specimen clears its concentration capacity.
    if not out["A_l_expected"]:
        out["c4_forbidden"] = set(C4_CLAIM_CLASSES)
        out["c4_expected"] = None
    else:
        capacities = []
        for specimen in light["specimens"]:
            if specimen.get("G_Q_interval") is None:
                capacities.append("CONCENTRATION_RANGE_INDETERMINATE")
            else:
                capacities.append(
                    concentration_range_class(specimen["G_Q_interval"]))
        out["computed_capacity"] = capacities
        capacity_cleared = all(c == "CONCENTRATION_RANGE_ADEQUATE"
                               for c in capacities)
        out["capacity_cleared"] = capacity_cleared
        if not capacity_cleared:
            out["c4_forbidden"] = set(C4_CLAIM_CLASSES)
            out["c4_expected"] = None
        elif (light.get("Q_bar_interval") is not None
              and all(s.get("Q") is not None for s in light["specimens"])):
            q_values = [s["Q"] for s in light["specimens"]]
            q0_bar = sum(s["component_q0"] for s in light["specimens"]) / 6.0
            qb_bar = sum(s["component_qB"] for s in light["specimens"]) / 6.0
            out["c4_expected"] = c4_class(light["Q_bar_interval"], q_values,
                                          q0_bar, qb_bar)
            out["c4_forbidden"] = set()
        else:
            out["c4_expected"] = None
            out["c4_forbidden"] = set()
    return out
