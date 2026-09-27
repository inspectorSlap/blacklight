"""Prospective operating characteristics of the candidate decision plans.

Produces the comparison the operator needs before selecting decision D6. Every
probability here is computed **exactly**, not simulated: a decision is a
function of binomial event counts, so the whole operating characteristic is a
finite sum over the binomial mass function.

For a single look with critical values (a, b) and X ~ Bin(n, p):

    P(PASS) = P(X <= a),  P(FAIL) = P(X >= b),  P(UNRESOLVED) = 1 - both.

For two nested looks, the second look's count is the first look's count plus an
independent increment over the additional replications, so with
X1 ~ Bin(n1, p) and D ~ Bin(n2-n1, p):

    P(PASS) = P(X1 <= a1) + sum_{a1<k<b1} P(X1=k) P(D <= a2-k)
    P(FAIL) = P(X1 >= b1) + sum_{a1<k<b1} P(X1=k) P(D >= b2-k)

with the remainder unresolved. `p` is the per-replication probability that the
event fires; it is a property of the engine under test and is therefore
**unknown before the campaign**. The tables below are consequently reported as
a function of `p` -- that part is assumption-free -- and the aggregate cost
projections are reported under explicitly declared behavioural scenarios which
are labelled as assumptions, not measurements.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import math
import os

from . import batching, sequential
from . import simulation as sim

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OC_VERSION = "1.2"


def requests_for(replications, batch_size=batching.MAX_BATCH_ITEMS):
    """HTTP batch requests for a replication count, including a partial final
    batch. Concurrency affects elapsed time, not request count."""
    return int(math.ceil(replications / float(batch_size)))


def segment_requests(plan, p_continue, batch_size=batching.MAX_BATCH_ITEMS):
    """Expected and worst-case requests for ONE segment under a plan.

    Batching is per segment, so a segment that stops at look 1 issues
    ceil(500/32) = 16 requests, and one that continues issues a further
    ceil(1500/32) = 47 -- not ceil(2000/32) - 16, because the additional
    replications are batched from a fresh boundary.
    """
    first = requests_for(plan.looks[0], batch_size)
    if len(plan.looks) == 1:
        return {"look_1_requests": first, "continuation_requests": 0,
                "expected_requests": first, "worst_case_requests": first}
    extra = requests_for(plan.looks[1] - plan.looks[0], batch_size)
    return {
        "look_1_requests": first,
        "continuation_requests": extra,
        "expected_requests": first + p_continue * extra,
        "worst_case_requests": first + extra,
    }

# Measured on 600 sound-reference responses at gzip -9, per-cell JSONL.
BYTES_PER_REPLICATION = {
    "compressed_response": 2568,
    "compressed_request": 550,
    "index_record": 320,
}
BYTES_TOTAL_PER_REPLICATION = sum(BYTES_PER_REPLICATION.values())

# The probability grid. 0.05 is the nominal; the boundary scenarios are the
# ones where a sound engine's event rate can legitimately approach it.
P_GRID = (0.0, 0.001, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05,
          0.06, 0.08, 0.10, 0.15, 0.25, 0.50, 1.0)


def log_pmf(n, k, p):
    if k < 0 or k > n:
        return float("-inf")
    if p <= 0.0:
        return 0.0 if k == 0 else float("-inf")
    if p >= 1.0:
        return 0.0 if k == n else float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def pmf_vector(n, p):
    return [math.exp(log_pmf(n, k, p)) for k in range(n + 1)]


def cdf_vector(pmf):
    out = []
    total = 0.0
    for value in pmf:
        total += value
        out.append(min(1.0, total))
    return out


def plan_oc(plan, p):
    """Exact operating characteristic of a plan at event probability `p`."""
    first = plan.looks[0]
    pmf1 = pmf_vector(first, p)
    cdf1 = cdf_vector(pmf1)
    a1, b1 = plan.criticals[0]

    p_pass_1 = cdf1[a1] if a1 >= 0 else 0.0
    p_fail_1 = 1.0 - (cdf1[b1 - 1] if b1 - 1 >= 0 else 0.0) if b1 <= first else 0.0
    p_continue = max(0.0, 1.0 - p_pass_1 - p_fail_1)

    if len(plan.looks) == 1:
        return {
            "p": p,
            "P_PASS": p_pass_1,
            "P_FAIL": p_fail_1,
            "P_UNRESOLVED": p_continue,
            "P_early_stop": 0.0,
            "P_stop_at_look_1": p_pass_1 + p_fail_1,
            "expected_replications": float(first),
            "max_replications": first,
            "looks": 1,
        }

    second = plan.looks[1]
    step = second - first
    pmf_step = pmf_vector(step, p)
    cdf_step = cdf_vector(pmf_step)
    a2, b2 = plan.criticals[1]

    p_pass_2 = 0.0
    p_fail_2 = 0.0
    lower = (a1 + 1) if a1 >= 0 else 0
    upper = min(b1 - 1, first)
    for k in range(max(0, lower), upper + 1):
        weight = pmf1[k]
        if weight <= 0.0:
            continue
        need_pass = a2 - k
        if need_pass >= step:
            p_pass_2 += weight
        elif need_pass >= 0:
            p_pass_2 += weight * cdf_step[need_pass]
        need_fail = b2 - k
        if need_fail <= 0:
            p_fail_2 += weight
        elif need_fail <= step:
            p_fail_2 += weight * (1.0 - (cdf_step[need_fail - 1]
                                         if need_fail - 1 >= 0 else 0.0))

    total_pass = p_pass_1 + p_pass_2
    total_fail = p_fail_1 + p_fail_2
    unresolved = max(0.0, 1.0 - total_pass - total_fail)
    early = p_pass_1 + p_fail_1
    expected = first * early + second * (1.0 - early)

    return {
        "p": p,
        "P_PASS": total_pass,
        "P_FAIL": total_fail,
        "P_UNRESOLVED": unresolved,
        "P_early_stop": early,
        "P_stop_at_look_1": early,
        "P_pass_at_look_1": p_pass_1,
        "P_fail_at_look_1": p_fail_1,
        "P_pass_at_look_2": p_pass_2,
        "P_fail_at_look_2": p_fail_2,
        "expected_replications": expected,
        "max_replications": second,
        "looks": 2,
    }


# ---------------------------------------------------------------------------
# Scenario families and their declared behavioural assumptions
# ---------------------------------------------------------------------------

def scenario_families():
    """Group the frozen grid by the kind of event each family gates.

    `assumed_p_sound` and `assumed_p_defective` are ASSUMPTIONS about engine
    behaviour used only to project aggregate cost. They are not measurements
    and no acceptance decision depends on them.
    """
    grid = sim.build_grid()
    families = {}
    for cell in grid:
        cell_id = cell["cell_id"]
        if cell_id.startswith("G1-") or cell_id.startswith("G3-"):
            boundary = cell_id.endswith(("7_10", "3_20"))
            key = ("MEANINGFUL_BOUNDARY_NULL" if boundary
                   else "INTERIOR_NULL")
        elif cell_id.startswith("G2-") or cell_id.startswith("G4-"):
            key = "POWER_ALTERNATIVE"
        elif cell_id.startswith("G5-") or cell_id.startswith("G6-"):
            outside = cell["population_targets"].get(
                "outside_equivalence_region")
            key = ("EQUIVALENCE_JUST_OUTSIDE" if outside
                   else "EQUIVALENCE_INTERIOR")
        elif cell_id.startswith("G11-") or cell_id.startswith("G12-"):
            key = ("CAPACITY_BOUNDARY" if cell_id.endswith("AT")
                   else "CAPACITY_OFF_BOUNDARY")
        elif cell_id.startswith("G14-"):
            key = ("C4_BOUNDARY" if cell_id.endswith("AT") else "C4_OFF_BOUNDARY")
        elif cell_id.startswith("G10-"):
            key = "DEGENERACY"
        else:
            key = "STRUCTURAL_AND_CONTROL"
        families.setdefault(key, []).append(cell_id)

    # Declared assumptions, stated openly.
    assumptions = {
        "MEANINGFUL_BOUNDARY_NULL": {
            "assumed_p_sound": 0.05,
            "rationale": "exactly at the meaningful-effect boundary the null is "
                         "least favourable, so a valid engine's event rate may "
                         "legitimately approach the nominal"},
        "INTERIOR_NULL": {
            "assumed_p_sound": 0.01,
            "rationale": "strictly inside the null region a valid engine should "
                         "fire well below nominal; HB-1 is markedly "
                         "conservative"},
        "EQUIVALENCE_JUST_OUTSIDE": {
            "assumed_p_sound": 0.05,
            "rationale": "immediately outside the equivalence region is the "
                         "least-favourable point for false equivalence"},
        "EQUIVALENCE_INTERIOR": {
            "assumed_p_sound": 0.01,
            "rationale": "inside the region the gated event is rare"},
        "CAPACITY_BOUNDARY": {
            "assumed_p_sound": 0.05,
            "rationale": "G or G_Q exactly at zero is the least-favourable "
                         "point for false gate clearance"},
        "CAPACITY_OFF_BOUNDARY": {"assumed_p_sound": 0.005,
                                  "rationale": "away from the boundary the gate "
                                               "resolves decisively"},
        "C4_BOUNDARY": {"assumed_p_sound": 0.05,
                        "rationale": "Q exactly at 0.10 is least favourable"},
        "C4_OFF_BOUNDARY": {"assumed_p_sound": 0.005,
                            "rationale": "away from 0.10 the diagnostic resolves"},
        "POWER_ALTERNATIVE": {"assumed_p_sound": 0.0,
                              "rationale": "report-only; no gated false-"
                                           "disposition event is defined"},
        "DEGENERACY": {"assumed_p_sound": 0.0,
                       "rationale": "coverage events only; HB-1 cannot produce "
                                    "a zero-width interval by construction"},
        "STRUCTURAL_AND_CONTROL": {"assumed_p_sound": 0.01,
                                   "rationale": "cross-light, heterogeneity and "
                                                "control families"},
    }
    out = []
    for key in sorted(families):
        entry = dict(assumptions.get(key, {"assumed_p_sound": 0.01,
                                           "rationale": "unclassified"}))
        entry.update({"family": key, "configurations": sorted(families[key]),
                      "configuration_count": len(families[key])})
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Aggregate cost
# ---------------------------------------------------------------------------

def aggregate_cost(expected_replications_per_segment, segments,
                   requests_per_segment, batch_size=batching.MAX_BATCH_ITEMS):
    """Aggregate cost. Requests are summed PER SEGMENT, not over a pooled
    replication total, because batching happens within a segment."""
    total_reps = expected_replications_per_segment * segments
    total_requests = requests_per_segment * segments
    storage = total_reps * BYTES_TOTAL_PER_REPLICATION
    return {
        "segments": segments,
        "expected_replications_per_segment": round(
            expected_replications_per_segment, 1),
        "total_replications": int(round(total_reps)),
        "batch_size": batch_size,
        "requests_per_segment": round(requests_per_segment, 2),
        "aggregate_requests": int(math.ceil(total_requests)),
        "identity_requests": 2,
        "projected_storage_bytes": int(storage),
        "projected_storage_gb": round(storage / 1e9, 3),
        "request_caveat": ("single-request fallbacks, triggered by an "
                           "interrupted or envelope-rejected batch, would "
                           "increase the actual request count"),
    }


def resolving_band(plan, threshold=0.90, resolution=2000):
    """The event rates at which each plan reliably resolves.

    Returns the largest p at which PASS is reached with probability >=
    `threshold`, the smallest p at which FAIL is, and the band between them
    where the plan is more likely than not to end UNRESOLVED. This is the most
    decision-relevant summary of a plan: it states what the campaign can and
    cannot settle.
    """
    grid = [i / float(resolution) for i in range(resolution + 1)]
    pass_max = None
    fail_min = None
    worst_unresolved = (0.0, 0.0)
    for p in grid:
        oc = plan_oc(plan, p)
        if oc["P_PASS"] >= threshold:
            pass_max = p
        if fail_min is None and oc["P_FAIL"] >= threshold:
            fail_min = p
        if oc["P_UNRESOLVED"] > worst_unresolved[1]:
            worst_unresolved = (p, oc["P_UNRESOLVED"])
    return {
        "threshold": threshold,
        "pass_reliable_up_to_p": pass_max,
        "fail_reliable_from_p": fail_min,
        "indeterminate_band": [pass_max, fail_min],
        "worst_case_p_for_unresolved": worst_unresolved[0],
        "worst_case_P_unresolved": worst_unresolved[1],
        "at_nominal": plan_oc(plan, plan.nominal),
    }


def correct_disposition_probability(oc, p, nominal):
    """P(the prospectively correct disposition).

    A candidate whose true event rate is at or below the nominal is valid, so
    PASS is correct; above it the candidate is invalid, so FAIL is correct.
    UNRESOLVED is never "correct", though it is always honest.
    """
    return oc["P_PASS"] if p <= nominal else oc["P_FAIL"]


def build_report():
    configurations = len(sim.build_grid())
    candidates = len(sim.CANDIDATE_N)
    segments = configurations * candidates

    def make(looks, label):
        return sequential.Plan(
            looks=looks, nominal=0.05,
            pass_level_family=sim.CELL_LEVEL,
            fail_level_family=sim.CELL_LEVEL, label=label,
            candidate_count=candidates, segment_count=segments)

    two_look = make([sim.STAGE_1_REPLICATIONS, sim.STAGE_2_REPLICATIONS],
                    "corrected_two_look")
    fixed = make([sim.STAGE_2_REPLICATIONS], "corrected_fixed_stage")
    plans = {"corrected_two_look": two_look, "corrected_fixed_stage": fixed}

    curves = {}
    for name, plan in plans.items():
        rows = []
        for p in P_GRID:
            oc = plan_oc(plan, p)
            oc["P_correct_disposition"] = correct_disposition_probability(
                oc, p, plan.nominal)
            oc["requests_per_segment"] = segment_requests(
                plan, 1.0 - oc["P_stop_at_look_1"])["expected_requests"]
            rows.append(oc)
        curves[name] = rows

    # Honest comparison of the two plans: both the shift in the underlying
    # event-rate cutoff AND the difference in disposition probability, which
    # are different quantities and must not be conflated.
    deltas = []
    for index, p in enumerate(P_GRID):
        a = curves["corrected_two_look"][index]
        b = curves["corrected_fixed_stage"][index]
        deltas.append({
            "p": p,
            "delta_P_PASS_percentage_points": (b["P_PASS"] - a["P_PASS"]) * 100.0,
            "delta_P_FAIL_percentage_points": (b["P_FAIL"] - a["P_FAIL"]) * 100.0,
            "delta_P_UNRESOLVED_percentage_points": (
                b["P_UNRESOLVED"] - a["P_UNRESOLVED"]) * 100.0,
        })
    max_pass_delta = max(deltas, key=lambda d: abs(
        d["delta_P_PASS_percentage_points"]))
    max_fail_delta = max(deltas, key=lambda d: abs(
        d["delta_P_FAIL_percentage_points"]))

    families = scenario_families()
    per_family = []
    for family in families:
        p = family["assumed_p_sound"]
        entry = {"family": family["family"],
                 "configuration_count": family["configuration_count"],
                 "assumed_p_sound": p, "rationale": family["rationale"],
                 "plans": {}}
        for name, plan in plans.items():
            oc = plan_oc(plan, p)
            entry["plans"][name] = {
                "P_PASS": oc["P_PASS"], "P_FAIL": oc["P_FAIL"],
                "P_UNRESOLVED": oc["P_UNRESOLVED"],
                "P_early_stop": oc["P_early_stop"],
                "expected_replications": oc["expected_replications"]}
        per_family.append(entry)

    def weighted_cost(plan):
        reps = 0.0
        reqs = 0.0
        for family in families:
            oc = plan_oc(plan, family["assumed_p_sound"])
            count = family["configuration_count"]
            reps += oc["expected_replications"] * count
            reqs += segment_requests(
                plan, 1.0 - oc["P_stop_at_look_1"])["expected_requests"] * count
        return reps / float(configurations), reqs / float(configurations)

    per_n = []
    for n in sim.CANDIDATE_N:
        row = {"N": n, "segments_at_this_N": configurations, "plans": {}}
        for name, plan in plans.items():
            reps, reqs = weighted_cost(plan)
            row["plans"][name] = aggregate_cost(reps, configurations, reqs)
        per_n.append(row)

    totals = {}
    for name, plan in plans.items():
        reps, reqs = weighted_cost(plan)
        worst_reqs = segment_requests(plan, 1.0)["worst_case_requests"]
        best_reqs = segment_requests(plan, 0.0)["expected_requests"]
        totals[name] = {
            "expected_under_declared_assumptions":
                aggregate_cost(reps, segments, reqs),
            "worst_case_all_segments_to_final_look":
                aggregate_cost(float(plan.looks[-1]), segments, worst_reqs),
            "best_case_all_segments_stop_at_first_look":
                aggregate_cost(float(plan.looks[0]), segments, best_reqs),
            "requests_per_segment_detail": segment_requests(plan, 1.0),
            "decision_plan": plan.describe(),
        }

    return {
        "oc_version": OC_VERSION,
        "status": "PROSPECTIVE_FOR_OPERATOR_REVIEW",
        "purpose": ("Exact operating characteristics of the two candidate "
                    "decision plans, to inform operator decision D6. No "
                    "real-target call was made to produce this report."),
        "computation": "exact binomial summation; no simulation",
        "real_target_calls": 0,
        "segments": segments,
        "candidate_N": list(sim.CANDIDATE_N),
        "candidate_count": candidates,
        "configurations": configurations,
        "inference_topology": {
            "segment_count": segments,
            "candidate_count": candidates,
            "segments_per_candidate_N": configurations,
            "pass_family_budget": sim.CELL_LEVEL,
            "pass_per_candidate_N_budget": two_look.pass_level_per_candidate,
            "pass_per_look_two_look": two_look.pass_levels[0],
            "pass_per_look_fixed_stage": fixed.pass_levels[0],
            "fail_family_budget": sim.CELL_LEVEL,
            "fail_per_segment_budget": two_look.fail_level_per_segment,
            "fail_per_look_two_look": two_look.fail_levels[0],
            "fail_per_look_fixed_stage": fixed.fail_levels[0],
            "pass_rationale": (
                "Within a candidate N, qualification requires every applicable "
                "segment and gated event to PASS -- an intersection-union "
                "claim over %d conjunctive segments -- so the budget is NOT "
                "divided across them: falsely qualifying an invalid N requires "
                "falsely passing the particular segment that makes it invalid. "
                "Across the %d candidate N, qualification is a union of "
                "selection opportunities, so the budget is divided there."
                % (configurations, candidates)),
            "fail_rationale": (
                "A false FAIL can arise at any one of the %d segments, so the "
                "budget is divided across all of them and then across looks."
                % segments),
            "corrected_claim": (
                "An earlier version stated that correcting PASS across the 53 "
                "segments would make qualification easier. That sign was "
                "wrong: a smaller tail level yields a more conservative upper "
                "bound and makes PASS harder. The reason not to divide is the "
                "intersection-union topology, not stringency."),
        },
        "plan_difference": {
            "note": ("A shift in the event-rate cutoff and a difference in "
                     "disposition probability are different quantities and "
                     "must not be conflated. Both are reported."),
            "per_p": deltas,
            "max_abs_delta_P_PASS": max_pass_delta,
            "max_abs_delta_P_FAIL": max_fail_delta,
        },
        "gross_defect_detection": {
            name: {"p": 0.15,
                   "P_stop_at_look_1": plan_oc(plan, 0.15)["P_stop_at_look_1"],
                   "P_FAIL": plan_oc(plan, 0.15)["P_FAIL"],
                   "note": "reported exactly; not described as certainty"}
            for name, plan in plans.items()},
        "bytes_per_replication": dict(
            BYTES_PER_REPLICATION, total=BYTES_TOTAL_PER_REPLICATION,
            basis="measured on 600 sound-reference responses at gzip -9, "
                  "per-cell JSONL; to be re-measured against real responses by "
                  "the storage-only checkpoint"),
        "probability_grid": list(P_GRID),
        "curves": curves,
        "scenario_families": families,
        "per_family": per_family,
        "per_N": per_n,
        "totals": totals,
        "resolving_band": {name: resolving_band(plan)
                           for name, plan in plans.items()},
        "assumption_note": (
            "P_PASS/P_FAIL/P_UNRESOLVED as a function of p are exact and "
            "assumption-free. The per-family and aggregate cost projections "
            "additionally assume a per-replication event rate for each family, "
            "declared in scenario_families; those are assumptions about engine "
            "behaviour, not measurements, and no acceptance decision depends "
            "on them."),
        "d6_status": "NOT_SELECTED",
    }


def write(report):
    path = os.path.join(ROOT, "results", "operating-characteristics-v1.2.json")
    with open(path, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path
