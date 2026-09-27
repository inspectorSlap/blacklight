"""Coverage-campaign machinery: frozen grid, deterministic seeds, acceptance rule.

This module contains the generator, the seed derivation and the acceptance
arithmetic for the coverage and false-disposition campaign. The campaign itself
is NOT run here: contract section 8 requires the prospective
simulation-acceptance proposal to be approved by the operator before large
simulation begins, and the phase gate in `harness/cli.py` enforces that.

Everything here is exactly reproducible. A replication is identified by
(cell_id, replication_index); its seed is derived by hashing the master seed
with those two values, so any single replication can be regenerated and
re-examined in isolation without replaying the campaign.

The acceptance rule is stated on exact binomial confidence bounds, never on a
raw empirical rate. Contract section 8 is explicit: "A raw empirical rate
compared directly with a nominal percentage is insufficient", and the
qualification report "must not call an observed rate of exactly the nominal
target proof of adequate coverage."
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import json
import math
import os
import random
from fractions import Fraction

from . import roster
from .oracle import core, population as pop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRID_VERSION = "1.0"
GENERATOR_VERSION = "blackbox-ordinal-harness-simgen-1.0"
MASTER_SEED = 20260920

CANDIDATE_N = (8, 10, 12, 16, 20, 30)

# Two-stage replication budget, frozen prospectively.
STAGE_1_REPLICATIONS = 500
STAGE_2_REPLICATIONS = 2000

# Per-cell decision level and the multiplicity adjustment used for FAIL calls.
CELL_LEVEL = 0.01


# ---------------------------------------------------------------------------
# Distribution constructors with exact target functionals
# ---------------------------------------------------------------------------

def pair_for_ps(target_ps):
    """Return (X, Y) distributions with PS(X, Y) exactly `target_ps`.

    X is a point mass at category 6. Y places mass a at category 1 (X wins),
    b at category 6 (tie) and c at category 10 (X loses), so
    PS = a + 0.5 b. For ps >= 1/2 take (a, b, c) = (2ps-1, 2-2ps, 0); for
    ps < 1/2 take (0, 2ps, 1-2ps). Both are exact rationals and both sum to 1.
    """
    ps = Fraction(target_ps)
    if not 0 <= ps <= 1:
        raise ValueError("PS must lie in [0,1]")
    x = pop.point_mass(6)
    y = [Fraction(0)] * core.K
    if ps >= Fraction(1, 2):
        y[0] = 2 * ps - 1
        y[5] = 2 - 2 * ps
    else:
        y[5] = 2 * ps
        y[9] = 1 - 2 * ps
    if sum(y) != 1:
        raise AssertionError("constructed distribution does not sum to 1")
    return x, y


def a0_with_floor(floor_mass):
    """A0 distribution with an exact floor mass, remainder at category 6."""
    f = Fraction(floor_mass)
    dist = [Fraction(0)] * core.K
    dist[0] = f
    dist[5] = 1 - f
    return dist


def concentrated(mass_on_mode, mode=6, spread=(5, 7, 8)):
    """A distribution with an exact modal mass, remainder spread evenly."""
    m = Fraction(mass_on_mode)
    dist = [Fraction(0)] * core.K
    dist[mode - 1] = m
    rest = 1 - m
    if rest:
        for category in spread:
            dist[category - 1] += rest / len(spread)
    return dist


def specimen_distributions(ps0, psa, floor_mass=0, concentration=None):
    """Four cell distributions for one specimen with exact P0 and PA."""
    x0, y0 = pair_for_ps(ps0)
    xa, ya = pair_for_ps(psa)
    cells = {"00": x0, "0B": y0, "A0": xa, "AB": ya}
    if floor_mass:
        # Move mass to the score floor in A0 while preserving PA is not
        # generally possible, so floor-mass rows declare their own PA.
        cells["A0"] = a0_with_floor(floor_mass)
    if concentration:
        for name, value in concentration.items():
            cells[name] = concentrated(value)
    return cells


# ---------------------------------------------------------------------------
# The frozen grid
# ---------------------------------------------------------------------------

def _uniform_light(ps0, psa, count=6, **kwargs):
    return [specimen_distributions(ps0, psa, **kwargs) for _ in range(count)]


def _split_light(spec_a, spec_b, count=6):
    half = count // 2
    return [dict(spec_a) for _ in range(half)] + [dict(spec_b)
                                                  for _ in range(count - half)]


def build_grid():
    """The complete prospective configuration family.

    Every configuration declares its POPULATION truth. False-disposition rates
    are measured against that truth, never against the realized sample, because
    contract section 5 requires population and sample truth to remain separate.
    """
    cells = []

    def add(cell_id, family, description, semantic, mechanical, targets,
            primary=True):
        cells.append({
            "cell_id": cell_id,
            "family": family,
            "description": description,
            "primary": primary,
            "semantic": semantic,
            "mechanical": mechanical,
            "population_targets": targets,
        })

    mech_null = _uniform_light(Fraction(1, 2), Fraction(1, 2), count=4)
    mech_strong = _uniform_light(Fraction(1), Fraction(1, 2), count=4)

    # G1 -- C1 composite null, including the boundary itself.
    for ps0 in ("1/2", "3/5", "13/20", "69/100", "7/10"):
        add("G1-C1-NULL-P0-%s" % ps0.replace("/", "_"), "FALSE-SUPPORT",
            "C1 composite null at P0_bar = %s (the 0.70 boundary is part of "
            "the null: the registered rule requires the interval to lie WHOLLY "
            "at or above 0.70)" % ps0,
            _uniform_light(Fraction(ps0), Fraction(1, 2)), mech_null,
            {"P0_bar": ps0, "I_P_bar": str(Fraction(ps0) - Fraction(1, 2))})

    # G2 -- declared C1 power alternatives, strictly above the boundary.
    for ps0 in ("3/4", "4/5", "9/10"):
        add("G2-C1-POWER-P0-%s" % ps0.replace("/", "_"), "POWER",
            "declared C1 alternative at P0_bar = %s" % ps0,
            _uniform_light(Fraction(ps0), Fraction(1, 2)), mech_strong,
            {"P0_bar": ps0}, primary=False)

    # G3 -- C2 composite null with C1 true, including the boundary.
    for ip in ("0", "1/20", "1/10", "149/1000", "3/20"):
        ps_a = Fraction(1) - Fraction(ip)
        add("G3-C2-NULL-IP-%s" % ip.replace("/", "_"), "FALSE-SUPPORT",
            "C2 composite null at I_P_bar = %s with P0 = 1 so C1 is true" % ip,
            _uniform_light(Fraction(1), ps_a), mech_null,
            {"P0_bar": "1", "I_P_bar": ip})

    # G4 -- declared C2 power alternatives.
    for ip in ("1/5", "3/10", "1/2"):
        add("G4-C2-POWER-IP-%s" % ip.replace("/", "_"), "POWER",
            "declared C2 alternative at I_P_bar = %s" % ip,
            _uniform_light(Fraction(1), Fraction(1) - Fraction(ip)), mech_strong,
            {"I_P_bar": ip}, primary=False)

    # G5 -- C1 equivalence interior, boundaries, and just outside both sides.
    for ps0 in ("1/2", "9/20", "11/20", "44/100", "56/100"):
        outside = not (Fraction(9, 20) <= Fraction(ps0) <= Fraction(11, 20))
        add("G5-C1-EQUIV-P0-%s" % ps0.replace("/", "_"), "FALSE-EQUIVALENCE",
            "C1 equivalence probe at P0_bar = %s (%s the registered region)"
            % (ps0, "outside" if outside else "inside"),
            _uniform_light(Fraction(ps0), Fraction(1, 2)), mech_null,
            {"P0_bar": ps0, "outside_equivalence_region": outside})

    # G6 -- C2 equivalence interior, boundaries, and just outside both sides.
    for ip in ("0", "-1/20", "1/20", "-6/100", "6/100"):
        outside = not (Fraction(-1, 20) <= Fraction(ip) <= Fraction(1, 20))
        ps_a = Fraction(1) - Fraction(ip)
        if ps_a > 1:
            base = Fraction(9, 10)
            ps_a = base - Fraction(ip)
        else:
            base = Fraction(1)
        add("G6-C2-EQUIV-IP-%s" % ip.replace("/", "_").replace("-", "neg"),
            "FALSE-EQUIVALENCE",
            "C2 equivalence probe at I_P_bar = %s (%s the registered region)"
            % (ip, "outside" if outside else "inside"),
            _uniform_light(base, ps_a), mech_null,
            {"I_P_bar": ip, "outside_equivalence_region": outside})

    # G7 -- zero, one, two and three truly attenuating lights.
    for attenuating in range(4):
        add("G7-ATTENUATING-LIGHTS-%d" % attenuating, "CROSS-LIGHT",
            "%d of three lights truly attenuating; A_all is earned only by all "
            "three" % attenuating,
            None, mech_null,
            {"attenuating_lights": attenuating})
        cells[-1]["per_light"] = [
            _uniform_light(Fraction(1), Fraction(1, 2) if i < attenuating
                           else Fraction(1))
            for i in range(3)]

    # G8 -- mixed support / equivalence / indeterminate vectors.
    add("G8-MIXED-VECTOR", "CROSS-LIGHT",
        "one attenuating light, one true-zero-interaction light and one "
        "neutral light: a mixed vector must never become a pooled verdict",
        None, mech_null, {"mixed": True})
    cells[-1]["per_light"] = [
        _uniform_light(Fraction(1), Fraction(1, 2)),
        _uniform_light(Fraction(1), Fraction(1)),
        _uniform_light(Fraction(1, 2), Fraction(1, 2)),
    ]

    # G9 -- heterogeneous and sign-cancelling specimen vectors.
    add("G9-SIGN-CANCELLING", "HETEROGENEITY",
        "three specimens at I_P = +0.20 and three at I_P = -0.15 around a "
        "P0 = 0.85 baseline: the mean enters the equivalence region while the "
        "corpus contains opposing meaningful effects",
        _split_light(specimen_distributions(Fraction(17, 20), Fraction(13, 20)),
                     specimen_distributions(Fraction(17, 20), Fraction(1))),
        mech_null, {"cancelling": True})
    add("G9-DOMINANT-SPECIMEN", "HETEROGENEITY",
        "a single dominant specimen at I_P = 0.9 with five at zero: the "
        "leave-one-out guard must withhold support",
        [specimen_distributions(Fraction(1), Fraction(1, 10))]
        + [specimen_distributions(Fraction(1), Fraction(1))] * 5,
        mech_null, {"dominant": True})

    # G10 -- degeneracy and rare-category cases from contract section 7.
    degenerate = [
        ("SAME-POINT-MASS", {"00": pop.point_mass(5), "A0": pop.point_mass(5),
                             "0B": pop.point_mass(5), "AB": pop.point_mass(5)}),
        ("DIFFERENT-POINT-MASS", {"00": pop.point_mass(10),
                                  "A0": pop.point_mass(6),
                                  "0B": pop.point_mass(1),
                                  "AB": pop.point_mass(6)}),
        ("FLOOR-POINT-MASS", {"00": pop.point_mass(1), "A0": pop.point_mass(1),
                              "0B": pop.point_mass(1), "AB": pop.point_mass(1)}),
        ("CEILING-POINT-MASS", {"00": pop.point_mass(10),
                                "A0": pop.point_mass(10),
                                "0B": pop.point_mass(10),
                                "AB": pop.point_mass(10)}),
        ("NEAR-POINT-MASS-RARE", {"00": pop.mixture([(10, 99), (9, 1)]),
                                  "A0": pop.mixture([(6, 99), (5, 1)]),
                                  "0B": pop.mixture([(1, 99), (2, 1)]),
                                  "AB": pop.mixture([(6, 99), (7, 1)])}),
        ("HIGH-TIE", {"00": pop.mixture([(7, 9), (8, 1)]),
                      "A0": pop.mixture([(6, 9), (7, 1)]),
                      "0B": pop.mixture([(7, 9), (6, 1)]),
                      "AB": pop.mixture([(6, 9), (5, 1)])}),
        ("CONCENTRATED-NON-BOUNDARY", {"00": concentrated(Fraction(9, 10), 7),
                                       "A0": concentrated(Fraction(9, 10), 6),
                                       "0B": concentrated(Fraction(9, 10), 3),
                                       "AB": concentrated(Fraction(9, 10), 6)}),
    ]
    for label, spec in degenerate:
        add("G10-DEGENERACY-%s" % label, "DEGENERACY",
            "degeneracy case: %s. An empirically degenerate finite sample must "
            "retain nonzero uncertainty; degeneracy alone is not an "
            "inference-engine failure" % label.lower().replace("-", " "),
            [dict(spec) for _ in range(6)], mech_null, {"degeneracy": label})

    # G11 -- capacity surplus G immediately below, at, and above zero.
    for label, floor_mass, ps0 in (("BELOW", "1", "19/20"),
                                   ("AT", "2/5", "19/20"),
                                   ("ABOVE", "0", "19/20")):
        specimens = []
        for _ in range(6):
            cells_map = specimen_distributions(Fraction(ps0), Fraction(1, 2))
            cells_map["A0"] = a0_with_floor(Fraction(floor_mass))
            specimens.append(cells_map)
        add("G11-RANGE-G-%s" % label, "RANGE-GATE",
            "ordinal capacity surplus G %s zero (p_floor,A0 = %s, P0 = %s)"
            % (label.lower(), floor_mass, ps0),
            specimens, mech_null,
            {"p_floor_A0": floor_mass, "P0_bar": ps0})

    # G12 -- concentration capacity G_Q below, at and above zero, and
    # opposite-sign C4 component contrasts.
    for label, base in (("BELOW", Fraction(1)), ("AT", Fraction(9, 10)),
                        ("ABOVE", Fraction(1, 4))):
        specimens = []
        for _ in range(6):
            cells_map = specimen_distributions(Fraction(1), Fraction(1, 2))
            cells_map["00"] = concentrated(base, 10, spread=(7, 8, 9))
            cells_map["0B"] = concentrated(base, 1, spread=(2, 3, 4))
            specimens.append(cells_map)
        add("G12-CAPACITY-GQ-%s" % label, "C4-CAPACITY",
            "concentration capacity G_Q %s zero (baseline modal mass %s); the "
            "ceiling-concentrated baseline must not manufacture an C4 "
            "equivalence conclusion" % (label.lower(), base),
            specimens, mech_null, {"baseline_modal_mass": str(base)})

    add("G12-C4-OPPOSITE-COMPONENTS", "C4-CAPACITY",
        "opposite-sign C4 component contrasts: their average may not conceal "
        "them",
        [{"00": pop.uniform([7, 8, 9, 10]), "A0": concentrated(Fraction(17, 20)),
          "0B": pop.uniform([1, 2]),
          "AB": pop.mixture([(5, 4), (6, 3), (7, 2), (8, 1)])}
         for _ in range(6)], mech_null, {"opposite_components": True})

    # G13 -- ceiling-concentrated baselines with mid-range A-present cells.
    add("G13-CEILING-BASELINE", "FALSE-EQUIVALENCE",
        "ceiling-concentrated 00 and 0B baselines paired with mid-range "
        "A-present cells: C4 may withhold, but must never protect, overwrite, "
        "rescue or invalidate C2",
        [{"00": concentrated(Fraction(19, 20), 10, spread=(8, 9)),
          "0B": concentrated(Fraction(19, 20), 1, spread=(2, 3)),
          "A0": pop.uniform([5, 6, 7]), "AB": pop.uniform([5, 6, 7])}
         for _ in range(6)], mech_null, {"ceiling_baseline": True})

    # G14 -- C4 meaningful boundary and equivalence edges.
    for label, a_mass in (("BELOW", Fraction(1, 2)), ("AT", Fraction(3, 5)),
                          ("ABOVE", Fraction(4, 5))):
        add("G14-C4-Q-%s" % label, "C4",
            "C4 concentration contrast %s the 0.10 boundary (A-present modal "
            "mass %s)" % (label.lower(), a_mass),
            [{"00": pop.uniform([7, 8, 9, 10]), "0B": pop.uniform([1, 2, 3, 4]),
              "A0": concentrated(a_mass), "AB": concentrated(a_mass)}
             for _ in range(6)], mech_null, {"a_present_modal_mass": str(a_mass)})

    # G15 -- C5 control eligibility and dispositions.
    add("G15-C5-ELIGIBLE-NULL", "C5",
        "mechanical controls eligible with a true zero interaction",
        _uniform_light(Fraction(1), Fraction(1, 2)),
        _uniform_light(Fraction(1), Fraction(1), count=4),
        {"control_interaction": "0"})
    add("G15-C5-INELIGIBLE", "C5",
        "mechanical controls without standalone discrimination: C5 ineligible",
        _uniform_light(Fraction(1), Fraction(1, 2)), mech_null,
        {"control_eligible": False})

    for cell in cells:
        cell["candidate_N"] = list(CANDIDATE_N)
    return cells


# ---------------------------------------------------------------------------
# Deterministic seeds
# ---------------------------------------------------------------------------

def derive_seed(cell_id, replication, n, master=MASTER_SEED):
    """Seed for one replication, reproducible in isolation."""
    material = "%d|%s|%d|%d|%s" % (master, cell_id, n, replication,
                                   GENERATOR_VERSION)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def sample_counts(distribution, n, rng):
    """Draw n i.i.d. categories from an exact rational distribution."""
    thresholds = []
    total = Fraction(0)
    for index, mass in enumerate(distribution):
        total += Fraction(mass)
        thresholds.append((float(total), index))
    counts = [0] * core.K
    for _ in range(n):
        draw = rng.random()
        for threshold, index in thresholds:
            if draw < threshold:
                counts[index] += 1
                break
        else:
            counts[thresholds[-1][1]] += 1
    return counts


def build_payload(cell, n, replication, alpha=None, d_near=0.9,
                  master=MASTER_SEED):
    """Build one replication's analyze payload from the frozen cell."""
    seed = derive_seed(cell["cell_id"], replication, n, master)
    rng = random.Random(seed)
    alpha = alpha or {"primary": 0.05, "c4": 0.05, "c5": 0.05}

    lights = []
    for light_index in range(3):
        if cell.get("per_light"):
            semantic = cell["per_light"][light_index]
        else:
            semantic = cell["semantic"]
        mechanical = cell["mechanical"]
        light = {"id": "L%d" % (light_index + 1),
                 "validity": {"provenance": True, "cache": True, "schema": True,
                              "local_lens": True, "refusal": True},
                 "semantic_specimens": [], "mechanical_specimens": []}
        for group_key, group in (("semantic_specimens", semantic),
                                 ("mechanical_specimens", mechanical)):
            for index, spec in enumerate(group):
                cells_map = {}
                for name in ("00", "A0", "0B", "AB"):
                    cells_map[name] = {"counts": sample_counts(spec[name], n, rng)}
                naming = (roster.semantic_id
                          if group_key.startswith("semantic")
                          else roster.mechanical_id)
                light[group_key].append({"id": naming(index),
                                         "cells": cells_map})
        lights.append(light)

    return {
        "schema_version": "blackbox.ordinal.ordinal-counts.v0.1",
        "analysis_id": "%s|N=%d|rep=%d" % (cell["cell_id"], n, replication),
        "config": {"alpha": alpha, "d_near": d_near},
        "lights": lights,
    }, seed


def population_truth(cell):
    """Exact population values for the configuration, by light."""
    out = []
    for light_index in range(3):
        semantic = (cell["per_light"][light_index] if cell.get("per_light")
                    else cell["semantic"])
        truth = pop.light_truth(semantic)
        out.append({
            "P0_bar": core.to_exact_string(truth["P0_bar"]),
            "I_P_bar": core.to_exact_string(truth["I_P_bar"]),
            "Q_bar": core.to_exact_string(truth["Q_bar"]),
            "P0_bar_decimal": float(truth["P0_bar"]),
            "I_P_bar_decimal": float(truth["I_P_bar"]),
            "Q_bar_decimal": float(truth["Q_bar"]),
        })
    return out


# ---------------------------------------------------------------------------
# Exact binomial bounds for the acceptance rule
# ---------------------------------------------------------------------------

def _log_tail_ge(n, x, p):
    if x <= 0:
        return 0.0
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return 0.0
    terms = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
             + k * math.log(p) + (n - k) * math.log1p(-p)
             for k in range(x, n + 1)]
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def _log_tail_le(n, x, p):
    if x >= n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return float("-inf")
    terms = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
             + k * math.log(p) + (n - k) * math.log1p(-p)
             for k in range(0, x + 1)]
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def binomial_upper_bound(events, trials, level, iterations=200):
    """One-sided exact (Clopper-Pearson) upper bound at confidence 1 - level."""
    if trials <= 0:
        raise ValueError("trials must be positive")
    if events >= trials:
        return 1.0
    target = math.log(level)
    lo, hi = 0.0, 1.0
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        if _log_tail_le(trials, events, mid) > target:
            lo = mid
        else:
            hi = mid
    return hi


def binomial_lower_bound(events, trials, level, iterations=200):
    if trials <= 0:
        raise ValueError("trials must be positive")
    if events <= 0:
        return 0.0
    target = math.log(level)
    lo, hi = 0.0, 1.0
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        if _log_tail_ge(trials, events, mid) < target:
            lo = mid
        else:
            hi = mid
    return lo


def evaluate_rate(events, trials, nominal, cell_count, stage):
    """Apply the frozen acceptance rule to one cell's event tally.

    Returns a verdict of PASS, FAIL or UNRESOLVED. Note the deliberate
    asymmetry:

    * PASS requires the *unadjusted* one-sided upper bound to sit at or below
      the nominal rate. This is the strict direction, so no multiplicity
      allowance is granted to the target.
    * FAIL requires the *Bonferroni-adjusted* lower bound to sit strictly above
      the nominal rate. Accusing an engine of invalidity is the direction where
      a false positive is most costly to the operator, so the multiplicity
      correction is spent there.
    * Anything else is UNRESOLVED, which escalates at stage 1 and yields
      ENGINE_NOT_YET_QUALIFIABLE at stage 2. An unresolved cell is never
      silently treated as a pass.
    """
    upper = binomial_upper_bound(events, trials, CELL_LEVEL)
    adjusted_level = CELL_LEVEL / max(1, cell_count)
    lower = binomial_lower_bound(events, trials, adjusted_level)
    if upper <= nominal:
        verdict = "PASS"
    elif lower > nominal:
        verdict = "FAIL"
    else:
        verdict = "UNRESOLVED"
    return {
        "events": events,
        "trials": trials,
        "observed_rate": events / float(trials),
        "nominal": nominal,
        "one_sided_upper_99": upper,
        "adjusted_lower_bound": lower,
        "adjusted_level": adjusted_level,
        "stage": stage,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Serialization of the frozen grid and seed record
# ---------------------------------------------------------------------------

def _serialize_distribution(distribution):
    return [core.to_exact_string(v) for v in distribution]


def serialize_grid(cells):
    out = []
    for cell in cells:
        entry = {k: v for k, v in cell.items()
                 if k not in ("semantic", "mechanical", "per_light")}
        entry["population_truth_by_light"] = population_truth(cell)
        if cell.get("per_light"):
            entry["per_light_specimens"] = [
                [{name: _serialize_distribution(spec[name])
                  for name in ("00", "A0", "0B", "AB")} for spec in light]
                for light in cell["per_light"]]
        else:
            entry["semantic_specimens"] = [
                {name: _serialize_distribution(spec[name])
                 for name in ("00", "A0", "0B", "AB")}
                for spec in cell["semantic"]]
        entry["mechanical_specimens"] = [
            {name: _serialize_distribution(spec[name])
             for name in ("00", "A0", "0B", "AB")}
            for spec in cell["mechanical"]]
        out.append(entry)
    return out


def write_grid_and_seeds():
    cells = build_grid()
    grid = {
        "grid_version": GRID_VERSION,
        "generator_version": GENERATOR_VERSION,
        "status": "FROZEN_CANDIDATE_PENDING_OPERATOR_APPROVAL",
        "candidate_N": list(CANDIDATE_N),
        "configuration_count": len(cells),
        "cell_count": len(cells) * len(CANDIDATE_N),
        "cells": serialize_grid(cells),
    }
    grid_path = os.path.join(ROOT, "fixtures", "simulation-grid-v1.0.json")
    with open(grid_path, "w") as handle:
        json.dump(grid, handle, indent=2, sort_keys=True)
        handle.write("\n")

    seeds = {
        "seed_record_version": "1.0",
        "master_seed": MASTER_SEED,
        "generator_version": GENERATOR_VERSION,
        "derivation": ("seed = int(sha256('<master>|<cell_id>|<N>|<replication>"
                       "|<generator_version>').hexdigest()[:16], 16), consumed "
                       "by random.Random"),
        "rng": "python stdlib random.Random (Mersenne Twister), stdlib only",
        "stage_1_replications": STAGE_1_REPLICATIONS,
        "stage_2_replications": STAGE_2_REPLICATIONS,
        "reproduction_note": ("any single replication is regenerable in "
                             "isolation from (cell_id, N, replication_index) "
                             "without replaying the campaign"),
        "worked_examples": [
            {"cell_id": cells[0]["cell_id"], "N": 30, "replication": 0,
             "seed": derive_seed(cells[0]["cell_id"], 0, 30)},
            {"cell_id": cells[0]["cell_id"], "N": 30, "replication": 1,
             "seed": derive_seed(cells[0]["cell_id"], 1, 30)},
            {"cell_id": cells[-1]["cell_id"], "N": 8, "replication": 499,
             "seed": derive_seed(cells[-1]["cell_id"], 499, 8)},
        ],
        "deterministic_scenario_panels": {
            "clean": "fixtures/scenarios/clean (no sampling; frozen counts)",
            "archive": "fixtures/scenarios/archive (no sampling)",
            "anchors": "fixtures/scenarios/anchors (no sampling)",
        },
    }
    seeds_path = os.path.join(ROOT, "fixtures", "seeds.json")
    with open(seeds_path, "w") as handle:
        json.dump(seeds, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return grid_path, seeds_path, grid


def main():
    grid_path, seeds_path, grid = write_grid_and_seeds()
    print(grid_path)
    print(seeds_path)
    print("configurations: %d" % grid["configuration_count"])
    print("cells (configuration x N): %d" % grid["cell_count"])
    print("stage-1 evaluations: %d" % (grid["cell_count"] * STAGE_1_REPLICATIONS))
    print("worst-case stage-2 evaluations: %d"
          % (grid["cell_count"] * STAGE_2_REPLICATIONS))


if __name__ == "__main__":
    main()
