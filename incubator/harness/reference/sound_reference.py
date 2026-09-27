"""Sound reference target for the ordinal-profile ordinal engine (separately executable).

Run as a program:

    python3 -m harness.reference.sound_reference analyze  < counts.json
    python3 -m harness.reference.sound_reference aggregate < archive.json

INDEPENDENCE (amendment section 2)
----------------------------------
This module imports only the Python standard library and its sibling
`harness.reference.interval` / `harness.reference.archive`. It does NOT import
`harness.oracle` (the exact expected-answer generator), `harness.checks` (the
decision assertions), `harness.mutants`, or the harness runner. Its estimators
are written in floating point directly from the preregistration's own
definitions, by a different algebraic route than the oracle's exact-rational
implementation: for example the oracle sums Fraction cross-products while this
module accumulates integer win/tie counts and divides once at the end.

Remaining shared lineage, disclosed as required: both implementations were
authored by the same agent from the same preregistration, and both use the
same category convention (index 0 == score 1). They share no code.

A "sound" target here means: it implements the registered decision topology
faithfully and uses a valid (conservative) uncertainty construction. It is not
claimed to be the registered construction -- see AMB-01.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import sys

from . import interval as iv
from . import archive as archive_mod

K = 10
ENGINE_VERSION = "sound-reference-1.0"
ANALYSIS_SCHEMA = "blackbox.ordinal.ordinal-analysis.v0.1"
COUNTS_SCHEMA = "blackbox.ordinal.ordinal-counts.v0.1"

# Frozen primary thresholds, preregistration section 3.4.
C1_BOUNDARY = 0.70
C1_EQ_LO, C1_EQ_HI = 0.45, 0.55
M_I_P = 0.15
E_I_P = 0.05
M_C = 0.10
E_C = 0.05
C1_CANCEL = 0.20
C2_CANCEL = 0.15
C4_CANCEL = 0.10

CELLS = ("00", "A0", "0B", "AB")

BLOCKING_CONDITIONS = [
    "development target: not execution eligible",
    "confidence-region construction is HB-1, a reference choice, not a sealed ordinal-profile method",
    "alpha values, dependence unit and D_NEAR are supplied as inputs, not sealed",
    "C3 cross-light equivalence procedure is not implemented in this engine version",
]


VALIDITY_GATES = ("provenance", "cache", "schema", "local_lens", "refusal")


class Rejected(Exception):
    """Input rejection, transported as HTTP 422 by a gateway."""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Estimators (independent float implementation)
# ---------------------------------------------------------------------------

def _strict_validity_cleared(validity):
    """Whether every registered validity gate is open, without coercion.

    C1 v0.6 forbids status-blind consumption. A gate must be a genuine JSON
    boolean; a status-bearing value such as "NOT_CLEARED" is truthy and would
    silently have been read as a clearance under ``bool()``. Anything that is
    not a boolean fails closed here instead.
    """
    for gate in VALIDITY_GATES:
        value = validity[gate]
        if not isinstance(value, bool):
            raise Rejected(
                "validity gate %r must be a JSON boolean; a status-bearing value must "
                "be consumed status-exactly, never coerced" % gate)
    return all(validity[gate] for gate in VALIDITY_GATES)


def wlt(x_counts, y_counts):
    """Win/loss/tie proportions by direct integer accumulation."""
    nx = sum(x_counts)
    ny = sum(y_counts)
    if nx == 0 or ny == 0:
        raise Rejected("EMPTY_CELL", "a compared cell has no valid responses")
    wins = 0
    ties = 0
    running_below = 0  # number of y-calls strictly below the current category
    for a in range(K):
        xa = x_counts[a]
        if xa:
            wins += xa * running_below
            ties += xa * y_counts[a]
        running_below += y_counts[a]
    denom = float(nx * ny)
    w = wins / denom
    t = ties / denom
    return w, 1.0 - w - t, t


def ps(x_counts, y_counts):
    w, _l, t = wlt(x_counts, y_counts)
    return w + 0.5 * t


def collision(counts):
    n = sum(counts)
    if n < 2:
        return None
    num = 0
    for v in counts:
        num += v * (v - 1)
    return num / float(n * (n - 1))


def floor_mass(counts):
    n = sum(counts)
    if n == 0:
        raise Rejected("EMPTY_CELL", "cell has no valid responses")
    return counts[0] / float(n)


def ceiling_mass(counts):
    n = sum(counts)
    return counts[K - 1] / float(n)


def modal_mass(counts):
    n = sum(counts)
    return max(counts) / float(n)


def degeneracy(counts, d_near):
    m = modal_mass(counts)
    if m >= 1.0:
        return "EMPIRICALLY_DEGENERATE"
    if m >= d_near:
        return "EMPIRICALLY_NEAR_DEGENERATE"
    return "EMPIRICALLY_NONDEGENERATE"


def mean(values):
    return sum(values) / float(len(values))


def leave_one_out(values):
    n = len(values)
    total = sum(values)
    return [(total - values[i]) / float(n - 1) for i in range(n)]


# ---------------------------------------------------------------------------
# Input validation (the schema is enforced here, not assumed)
# ---------------------------------------------------------------------------

def _require(condition, code, message):
    if not condition:
        raise Rejected(code, message)


def validate_counts_payload(payload):
    _require(isinstance(payload, dict), "NOT_AN_OBJECT", "payload must be an object")
    _require(payload.get("schema_version") == COUNTS_SCHEMA,
             "BAD_SCHEMA_VERSION", "schema_version must be %s" % COUNTS_SCHEMA)
    allowed = {"schema_version", "analysis_id", "config", "lights"}
    extra = set(payload) - allowed
    _require(not extra, "ADDITIONAL_PROPERTIES",
             "unexpected top-level properties: %s" % sorted(extra))

    config = payload.get("config")
    _require(isinstance(config, dict), "BAD_CONFIG", "config must be an object")
    alpha = config.get("alpha")
    _require(isinstance(alpha, dict), "BAD_ALPHA", "config.alpha must be an object")
    for key in ("primary", "c4", "c5"):
        value = alpha.get(key)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool),
                 "BAD_ALPHA", "config.alpha.%s must be a number" % key)
        _require(0.0 < float(value) < 1.0, "BAD_ALPHA",
                 "config.alpha.%s must lie in (0,1)" % key)
    d_near = config.get("d_near")
    _require(isinstance(d_near, (int, float)) and not isinstance(d_near, bool),
             "BAD_D_NEAR", "config.d_near must be a number")
    _require(0.0 < float(d_near) < 1.0, "BAD_D_NEAR",
             "config.d_near must lie in (0,1)")

    lights = payload.get("lights")
    _require(isinstance(lights, list) and len(lights) == 3,
             "BAD_LIGHT_COUNT", "exactly three lights are required")
    seen_ids = set()
    for light in lights:
        _require(isinstance(light, dict), "BAD_LIGHT", "light must be an object")
        light_id = light.get("id")
        _require(isinstance(light_id, str) and light_id,
                 "BAD_LIGHT_ID", "light id must be a non-empty string")
        _require(light_id not in seen_ids, "DUPLICATE_LIGHT_ID",
                 "duplicate light id %r" % light_id)
        seen_ids.add(light_id)
        validity = light.get("validity")
        _require(isinstance(validity, dict), "BAD_VALIDITY",
                 "light.validity must be an object")
        for key in ("provenance", "cache", "schema", "local_lens", "refusal"):
            _require(isinstance(validity.get(key), bool), "BAD_VALIDITY",
                     "light.validity.%s must be a boolean" % key)
        _validate_group(light.get("semantic_specimens"), 6, "semantic_specimens")
        _validate_group(light.get("mechanical_specimens"), 4, "mechanical_specimens")
    return payload


def _validate_group(group, expected, label):
    _require(isinstance(group, list) and len(group) == expected,
             "BAD_SPECIMEN_COUNT", "%s must contain exactly %d specimens"
             % (label, expected))
    seen = set()
    for specimen in group:
        _require(isinstance(specimen, dict), "BAD_SPECIMEN",
                 "specimen must be an object")
        sid = specimen.get("id")
        _require(isinstance(sid, str) and sid, "BAD_SPECIMEN_ID",
                 "specimen id must be a non-empty string")
        _require(sid not in seen, "DUPLICATE_SPECIMEN_ID",
                 "duplicate specimen id %r in %s" % (sid, label))
        seen.add(sid)
        cells = specimen.get("cells")
        _require(isinstance(cells, dict), "BAD_CELLS", "cells must be an object")
        _require(set(cells) == set(CELLS), "BAD_CELLS",
                 "cells must be exactly %s" % (sorted(CELLS),))
        for name in CELLS:
            cell = cells[name]
            _require(isinstance(cell, dict), "BAD_CELL", "cell must be an object")
            counts = cell.get("counts")
            _require(isinstance(counts, list) and len(counts) == K,
                     "BAD_COUNTS", "cell %s counts must have %d entries" % (name, K))
            for value in counts:
                _require(isinstance(value, int) and not isinstance(value, bool),
                         "BAD_COUNTS", "counts must be integers")
                _require(value >= 0, "BAD_COUNTS", "counts must be non-negative")
            _require(sum(counts) > 0, "EMPTY_CELL",
                     "cell %s has no valid responses" % name)


# ---------------------------------------------------------------------------
# Specimen computation
# ---------------------------------------------------------------------------

def specimen_report(specimen, d_near):
    cells = {name: specimen["cells"][name]["counts"] for name in CELLS}
    n = {name: sum(cells[name]) for name in CELLS}

    w0, l0, t0 = wlt(cells["00"], cells["0B"])
    p0 = w0 + 0.5 * t0
    wa, la, ta = wlt(cells["A0"], cells["AB"])
    pa = wa + 0.5 * ta
    i_p = p0 - pa

    coll = {name: collision(cells[name]) for name in CELLS}
    p_floor_a0 = floor_mass(cells["A0"])
    k_a = 1.0 - 0.5 * p_floor_a0

    report = {
        "id": specimen["id"],
        "n": n,
        "counts": cells,
        "W0": w0, "L0": l0, "T0": t0, "P0": p0,
        "WA": wa, "LA": la, "TA": ta, "PA": pa,
        "I_P": i_p,
        "delta0": 2.0 * p0 - 1.0,
        "deltaA": 2.0 * pa - 1.0,
        "I_delta": 2.0 * i_p,
        "p_floor_A0": p_floor_a0,
        "K_A": k_a,
        "K_A_cliff": 2.0 * k_a - 1.0,
        "G": k_a - (p0 - M_I_P),
        "collision": coll,
        "floor_mass": {name: floor_mass(cells[name]) for name in CELLS},
        "ceiling_mass": {name: ceiling_mass(cells[name]) for name in CELLS},
        "modal_mass": {name: modal_mass(cells[name]) for name in CELLS},
        "occupied_categories": {
            name: sum(1 for v in cells[name] if v > 0) for name in CELLS},
        "modal_categories": {
            name: [i + 1 for i, v in enumerate(cells[name])
                   if v == max(cells[name])] for name in CELLS},
        "degeneracy": {name: degeneracy(cells[name], d_near) for name in CELLS},
    }

    if any(v is None for v in coll.values()):
        report.update({"K_Q": None, "G_Q": None, "Q": None,
                       "component_q0": None, "component_qB": None,
                       "concentration_measurable": False})
    else:
        report.update({
            "component_q0": coll["A0"] - coll["00"],
            "component_qB": coll["AB"] - coll["0B"],
            "Q": 0.5 * ((coll["A0"] - coll["00"]) + (coll["AB"] - coll["0B"])),
            "K_Q": 1.0 - 0.5 * (coll["00"] + coll["0B"]),
            "concentration_measurable": True,
        })
        report["G_Q"] = report["K_Q"] - M_C
    return report


# ---------------------------------------------------------------------------
# Registered dispositions
# ---------------------------------------------------------------------------

def c1_disposition(p0_interval, b_values):
    lo, hi = p0_interval
    loo = leave_one_out(b_values)
    guards = {
        "recurrence_positive_count": sum(1 for v in b_values if v > 0),
        "recurrence": sum(1 for v in b_values if v > 0) >= 4,
        "anti_singleton": all(v > 0 for v in loo),
        "leave_one_out": loo,
        "equivalence_leave_one_out": all(-0.05 <= v <= 0.05 for v in loo),
        "no_cancellation": not (any(v >= C1_CANCEL for v in b_values)
                                and any(v <= -C1_CANCEL for v in b_values)),
    }
    if lo >= C1_BOUNDARY:
        if guards["recurrence"] and guards["anti_singleton"]:
            return "SUPPORTED", guards
        return "INDETERMINATE_GUARD_NOT_MET", guards
    if C1_EQ_LO <= lo and hi <= C1_EQ_HI:
        if guards["equivalence_leave_one_out"] and guards["no_cancellation"]:
            return "EQUIVALENTLY_ABSENT", guards
        return "HETEROGENEITY_NOT_CLEARED", guards
    return "INDETERMINATE", guards


def range_disposition(g_interval):
    lo, hi = g_interval
    if lo > 0.0:
        return "RANGE_ADEQUATE"
    if hi < 0.0:
        return "FLOOR_LIMITED"
    return "RANGE_INDETERMINATE"


def c2_disposition(ip_interval, a_values):
    lo, hi = ip_interval
    loo = leave_one_out(a_values)
    guards = {
        "recurrence_positive_count": sum(1 for v in a_values if v > 0),
        "recurrence": sum(1 for v in a_values if v > 0) >= 4,
        "anti_singleton": all(v > 0 for v in loo),
        "leave_one_out": loo,
        "equivalence_leave_one_out": all(-E_I_P <= v <= E_I_P for v in loo),
        "no_cancellation": not (any(v >= C2_CANCEL for v in a_values)
                                and any(v <= -C2_CANCEL for v in a_values)),
    }
    if lo >= M_I_P:
        if guards["recurrence"] and guards["anti_singleton"]:
            return "SUPPORTED", guards
        return "INDETERMINATE_GUARD_NOT_MET", guards
    if -E_I_P <= lo and hi <= E_I_P:
        if guards["equivalence_leave_one_out"] and guards["no_cancellation"]:
            return "EQUIVALENTLY_ABSENT", guards
        return "HETEROGENEITY_NOT_CLEARED", guards
    return "INDETERMINATE", guards


def concentration_range_disposition(gq_interval):
    lo, hi = gq_interval
    if lo > 0.0:
        return "CONCENTRATION_RANGE_ADEQUATE"
    if hi < 0.0:
        return "CONCENTRATION_RANGE_LIMITED"
    return "CONCENTRATION_RANGE_INDETERMINATE"


def c4_disposition(q_interval, q_values, q0_bar, qb_bar):
    lo, hi = q_interval
    loo = leave_one_out(q_values)
    guards = {
        "component_q0_bar": q0_bar,
        "component_qB_bar": qb_bar,
        "components_positive": q0_bar > 0.0 and qb_bar > 0.0,
        "components_in_band": (-E_C <= q0_bar <= E_C) and (-E_C <= qb_bar <= E_C),
        "recurrence_positive_count": sum(1 for v in q_values if v > 0),
        "recurrence": sum(1 for v in q_values if v > 0) >= 4,
        "anti_singleton": all(v > 0 for v in loo),
        "leave_one_out": loo,
        "equivalence_leave_one_out": all(-E_C <= v <= E_C for v in loo),
        "no_cancellation": not (any(v >= C4_CANCEL for v in q_values)
                                and any(v <= -C4_CANCEL for v in q_values)),
    }
    if lo >= M_C:
        if (guards["components_positive"] and guards["recurrence"]
                and guards["anti_singleton"]):
            return "GENERAL_RESOLUTION_LOSS_SUPPORTED", guards
        return "C4_INDETERMINATE_GUARD_NOT_MET", guards
    if -E_C <= lo and hi <= E_C:
        if (guards["components_in_band"] and guards["equivalence_leave_one_out"]
                and guards["no_cancellation"]):
            return "GENERAL_RESOLUTION_LOSS_EQUIVALENTLY_ABSENT", guards
        return "C4_HETEROGENEITY_NOT_CLEARED", guards
    return "GENERAL_RESOLUTION_LOSS_INDETERMINATE", guards


def c5_disposition(ip_interval, a_values):
    """Mechanical-control interaction disposition, three-of-four recurrence."""
    lo, hi = ip_interval
    loo = leave_one_out(a_values)
    guards = {
        "recurrence_positive_count": sum(1 for v in a_values if v > 0),
        "recurrence": sum(1 for v in a_values if v > 0) >= 3,
        "anti_singleton": all(v > 0 for v in loo),
        "leave_one_out": loo,
        "equivalence_leave_one_out": all(-E_I_P <= v <= E_I_P for v in loo),
        "no_cancellation": not (any(v >= C2_CANCEL for v in a_values)
                                and any(v <= -C2_CANCEL for v in a_values)),
    }
    if lo >= M_I_P:
        if guards["recurrence"] and guards["anti_singleton"]:
            return "CONTROL_ATTENUATION_SUPPORTED", guards
        return "CONTROL_INDETERMINATE_GUARD_NOT_MET", guards
    if -E_I_P <= lo and hi <= E_I_P:
        if guards["equivalence_leave_one_out"] and guards["no_cancellation"]:
            return "CONTROL_ATTENUATION_EQUIVALENTLY_ABSENT", guards
        return "CONTROL_HETEROGENEITY_NOT_CLEARED", guards
    return "CONTROL_INDETERMINATE", guards


# ---------------------------------------------------------------------------
# Light-level assembly
# ---------------------------------------------------------------------------

def _quad_sizes(reports):
    return [((r["n"]["00"], r["n"]["0B"]), (r["n"]["A0"], r["n"]["AB"]))
            for r in reports]


def _zero_width(intervals):
    for name, bounds in intervals:
        if bounds is None:
            continue
        if bounds[1] - bounds[0] < iv.MIN_WIDTH:
            return name
    return None


def analyze_semantic_light(light, config):
    alpha = config["alpha"]
    d_near = float(config["d_near"])
    gamma_light = float(alpha["primary"]) / 3.0
    gamma_c1 = gamma_light / 3.0
    gamma_c2 = gamma_light / 3.0
    gamma_range = gamma_light / 3.0 / 6.0
    gamma_c4_light = float(alpha["c4"]) / 3.0
    gamma_c4_q = gamma_c4_light / 2.0
    gamma_c4_cap = gamma_c4_light / 2.0 / 6.0

    reports = [specimen_report(s, d_near) for s in light["semantic_specimens"]]

    p0_values = [r["P0"] for r in reports]
    b_values = [v - 0.5 for v in p0_values]
    a_values = [r["I_P"] for r in reports]

    p0_bar = mean(p0_values)
    ip_bar = mean(a_values)
    p0_bar_interval = list(iv.ps_mean_interval(
        p0_bar, [(r["n"]["00"], r["n"]["0B"]) for r in reports], gamma_c1))
    ip_bar_interval = list(iv.interaction_mean_interval(
        ip_bar, _quad_sizes(reports), gamma_c2))

    for r in reports:
        joint = iv.range_surplus_interval(
            r["counts"]["A0"][0], r["n"]["A0"], r["P0"],
            r["n"]["00"], r["n"]["0B"], gamma_range, M_I_P)
        r["p_floor_A0_interval"] = joint["p_floor_interval"]
        r["K_A_interval"] = joint["K_A_interval"]
        r["P0_interval"] = joint["P0_interval"]
        r["G_interval"] = joint["G_interval"]
        r["range_disposition"] = range_disposition(joint["G_interval"])

        if r["concentration_measurable"]:
            cap = iv.concentration_capacity_interval(
                r["collision"]["00"], r["n"]["00"],
                r["collision"]["0B"], r["n"]["0B"], gamma_c4_cap, M_C)
            r["K_Q_interval"] = cap["K_Q_interval"]
            r["G_Q_interval"] = cap["G_Q_interval"]
            r["concentration_range_disposition"] = concentration_range_disposition(
                cap["G_Q_interval"])
        else:
            r["K_Q_interval"] = None
            r["G_Q_interval"] = None
            r["concentration_range_disposition"] = "CONCENTRATION_RANGE_INDETERMINATE"

    validity = dict(light["validity"])
    validity_cleared = _strict_validity_cleared(validity)

    engine_failure = _zero_width([
        ("P0_bar", p0_bar_interval),
        ("I_P_bar", ip_bar_interval),
    ] + [("G[%s]" % r["id"], r["G_interval"]) for r in reports])

    c1, c1_guards = c1_disposition(p0_bar_interval, b_values)
    range_dispositions = [r["range_disposition"] for r in reports]
    range_cleared = all(d == "RANGE_ADEQUATE" for d in range_dispositions)
    light_range = "RANGE_CLEARED" if range_cleared else "RANGE_NOT_CLEARED"

    if c1 == "SUPPORTED" and range_cleared:
        c2, c2_guards = c2_disposition(ip_bar_interval, a_values)
    else:
        c2, c2_guards = c2_disposition(ip_bar_interval, a_values)
        c2_guards["computed_but_withheld"] = True
        if c1 != "SUPPORTED":
            c2 = "NOT_OPENED_C1_NOT_SUPPORTED"
        else:
            c2 = "RANGE_NOT_CLEARED"

    if engine_failure is not None:
        c1 = "INFERENCE_ENGINE_FAILURE"
        c2 = "INFERENCE_ENGINE_FAILURE"
    elif not validity_cleared:
        c1 = "INSTRUMENT_VALIDITY_NOT_CLEARED"
        c2 = "INSTRUMENT_VALIDITY_NOT_CLEARED"

    a_l = (validity_cleared and engine_failure is None
           and c1 == "SUPPORTED" and range_cleared and c2 == "SUPPORTED")

    # C4 opens only for a light with supported A_l (section 12.3).
    if not a_l:
        c4_block = {
            "disposition": "C4_NOT_OPENED",
            "eligible": False,
            "reason": "C4 opens only for a light with supported A_l",
        }
    else:
        measurable = all(r["concentration_measurable"] for r in reports)
        capacity_cleared = measurable and all(
            r["concentration_range_disposition"] == "CONCENTRATION_RANGE_ADEQUATE"
            for r in reports)
        q_values = [r["Q"] for r in reports]
        q0_bar = mean([r["component_q0"] for r in reports]) if measurable else None
        qb_bar = mean([r["component_qB"] for r in reports]) if measurable else None
        q_bar = mean(q_values) if measurable else None
        if measurable:
            q_bar_interval = list(iv.collision_combo_mean_interval(
                q_bar,
                [[(0.5, r["n"]["A0"]), (-0.5, r["n"]["00"]),
                  (0.5, r["n"]["AB"]), (-0.5, r["n"]["0B"])] for r in reports],
                gamma_c4_q, -1.0, 1.0))
        else:
            q_bar_interval = None
        if not capacity_cleared:
            c4_block = {
                "disposition": "C4_CONCENTRATION_CAPACITY_NOT_CLEARED",
                "eligible": True,
                "capacity_cleared": False,
                "Q_bar": q_bar,
                "Q_bar_interval": q_bar_interval,
                "component_q0_bar": q0_bar,
                "component_qB_bar": qb_bar,
                "specimen_capacity": [
                    r["concentration_range_disposition"] for r in reports],
            }
        else:
            disp, guards = c4_disposition(q_bar_interval, q_values, q0_bar, qb_bar)
            c4_block = {
                "disposition": disp,
                "eligible": True,
                "capacity_cleared": True,
                "Q_bar": q_bar,
                "Q_bar_interval": q_bar_interval,
                "component_q0_bar": q0_bar,
                "component_qB_bar": qb_bar,
                "guards": guards,
                "specimen_capacity": [
                    r["concentration_range_disposition"] for r in reports],
            }

    return {
        "light_id": light["id"],
        "validity": {"flags": validity, "cleared": validity_cleared},
        "inference_engine": {
            "status": "OK" if engine_failure is None else "INFERENCE_ENGINE_FAILURE",
            "zero_width_quantity": engine_failure,
        },
        "specimens": reports,
        "P0_bar": p0_bar,
        "P0_bar_interval": p0_bar_interval,
        "I_P_bar": ip_bar,
        "I_P_bar_interval": ip_bar_interval,
        "delta0_bar": 2.0 * p0_bar - 1.0,
        "I_delta_bar": 2.0 * ip_bar,
        "b_values": b_values,
        "a_values": a_values,
        "c1": {"disposition": c1, "guards": c1_guards},
        "range": {
            "disposition": light_range,
            "specimen_dispositions": range_dispositions,
            "all_six_required": True,
        },
        "c2": {"disposition": c2, "guards": c2_guards},
        "c4": c4_block,
        "A_l": a_l,
    }


def analyze_mechanical_light(light, config):
    alpha = config["alpha"]
    d_near = float(config["d_near"])
    gamma_light = float(alpha["c5"]) / 3.0
    gamma_standalone = gamma_light / 3.0
    gamma_interaction = gamma_light / 3.0
    gamma_range = gamma_light / 3.0 / 4.0

    reports = [specimen_report(s, d_near) for s in light["mechanical_specimens"]]
    p0_values = [r["P0"] for r in reports]
    b_values = [v - 0.5 for v in p0_values]
    a_values = [r["I_P"] for r in reports]

    p0_bar = mean(p0_values)
    ip_bar = mean(a_values)
    p0_bar_interval = list(iv.ps_mean_interval(
        p0_bar, [(r["n"]["00"], r["n"]["0B"]) for r in reports], gamma_standalone))
    ip_bar_interval = list(iv.interaction_mean_interval(
        ip_bar, _quad_sizes(reports), gamma_interaction))

    for r in reports:
        joint = iv.range_surplus_interval(
            r["counts"]["A0"][0], r["n"]["A0"], r["P0"],
            r["n"]["00"], r["n"]["0B"], gamma_range, M_I_P)
        r["G_interval"] = joint["G_interval"]
        r["K_A_interval"] = joint["K_A_interval"]
        r["range_disposition"] = range_disposition(joint["G_interval"])

    validity = dict(light["validity"])
    validity_cleared = _strict_validity_cleared(validity)

    loo_b = leave_one_out(b_values)
    eligibility = {
        "standalone_interval_clears": p0_bar_interval[0] >= C1_BOUNDARY,
        "standalone_recurrence_3_of_4": sum(1 for v in b_values if v > 0) >= 3,
        "standalone_anti_singleton": all(v > 0 for v in loo_b),
        "all_four_range_adequate": all(
            r["range_disposition"] == "RANGE_ADEQUATE" for r in reports),
        "validity_cleared": validity_cleared,
    }
    eligible = all(eligibility.values())

    if not eligible:
        c5 = {"disposition": "CONTROL_NOT_ELIGIBLE", "eligibility": eligibility}
    else:
        disp, guards = c5_disposition(ip_bar_interval, a_values)
        c5 = {"disposition": disp, "eligibility": eligibility, "guards": guards}

    return {
        "light_id": light["id"],
        "validity": {"flags": validity, "cleared": validity_cleared},
        "specimens": reports,
        "P0_bar_mech": p0_bar,
        "P0_bar_mech_interval": p0_bar_interval,
        "I_P_bar_mech": ip_bar,
        "I_P_bar_mech_interval": ip_bar_interval,
        "b_values": b_values,
        "a_values": a_values,
        "range": {
            "specimen_dispositions": [r["range_disposition"] for r in reports],
            "all_four_required": True,
        },
        "c5": c5,
        "pooled_with_primary": False,
    }


def analyze(payload):
    validate_counts_payload(payload)
    config = payload["config"]
    semantic = [analyze_semantic_light(l, config) for l in payload["lights"]]
    mechanical = [analyze_mechanical_light(l, config) for l in payload["lights"]]

    a_vector = [l["A_l"] for l in semantic]
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "apparatus_status": "DEVELOPMENT_ONLY_NOT_EXECUTION_ELIGIBLE",
        "confirmatory_ready": False,
        "blocking_conditions": list(BLOCKING_CONDITIONS),
        "analysis_id": payload.get("analysis_id"),
        "uncertainty_construction": "HB-1",
        "semantic_lights": semantic,
        "mechanical_lights": mechanical,
        "cross_light": {
            "A_vector": a_vector,
            "A_all": all(a_vector),
            "light_ids": [l["light_id"] for l in semantic],
            "c3": {
                "disposition": "WITHHELD_NOT_IMPLEMENTED",
                "reason": "C3 cross-light equivalence procedure is not implemented "
                          "or sealed in this engine version",
            },
            "pooled_verdict": None,
        },
    }


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 1 or argv[0] not in ("analyze", "aggregate"):
        sys.stderr.write("usage: sound_reference {analyze|aggregate} [input.json]\n")
        return 2
    mode = argv[0]
    if len(argv) > 1:
        with open(argv[1], "r") as handle:
            payload = json.load(handle)
    else:
        payload = json.load(sys.stdin)
    try:
        result = analyze(payload) if mode == "analyze" else archive_mod.aggregate(payload)
    except Rejected as exc:
        json.dump({"error": {"code": exc.code, "message": exc.message}}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    except archive_mod.Rejected as exc:  # pragma: no cover - alias safety
        json.dump({"error": {"code": exc.code, "message": exc.message}}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
