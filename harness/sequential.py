"""Valid two-look sequential decision rule (harness v1.1).

WHY v1.0's RULE WAS WRONG
-------------------------
v1.0 evaluated each segment at 500 replications and, if unresolved, again at
2000 -- using the FULL per-cell level at BOTH looks. That spends the error
budget twice. The probability of a false decision under "decide at look 1 OR
look 2" is bounded by the sum of the per-look levels, not by either one, so the
realised error could reach roughly twice the stated level. The stated error
control was therefore not the achieved error control.

THE v1.1 CONSTRUCTION
---------------------
The per-cell budget is SPLIT across the looks before any data are seen:

    level(look 1) + level(look 2) <= CELL_LEVEL

with an equal split by default. Validity then follows from the union bound:
for a true rate in the null region,

    P(false decision at look 1 OR look 2)
        <= P(false at look 1) + P(false at look 2)
        <= level_1 + level_2
        =  CELL_LEVEL.

Two properties make this argument airtight, and both matter:

1. **Clopper-Pearson bounds are exactly valid at every finite n**, so each
   per-look term is bounded by its own level with no asymptotics.
2. **The union bound requires no independence.** The two looks are nested --
   look 2 literally contains look 1's observations -- so any argument needing
   independent increments would be invalid here. The union bound does not.

A FIXED-STAGE alternative is also provided and is selectable prospectively: a
single look at the full replication count spending the entire budget at once.
It is uniformly more powerful at the final count but forfeits early stopping.
The campaign declares which plan it uses before running.

Both plans are expressed through integer CRITICAL VALUES computed once per
look. Because the Clopper-Pearson bounds are monotone in the event count, the
decision reduces to two comparisons, which is what makes the error-control
demonstration in `verify_error_control` cheap enough to run at high precision.
"""

import bisect
import math
import random

from .simulation import binomial_lower_bound, binomial_upper_bound


class Plan(object):
    """A prospective sequential (or fixed-stage) decision plan (v1.2 topology).

    THE TWO DIRECTIONS HAVE DIFFERENT MULTIPLICITY STRUCTURES, because they are
    different logical claims -- not because one deserves more protection.

    **PASS / false qualification.** Qualifying a candidate `N` requires EVERY
    applicable segment and gated event at that `N` to pass. Within an `N` that
    is an intersection-union claim: if the `N` is invalid then at least one of
    its 53 segments is invalid, and falsely qualifying the `N` requires falsely
    passing that particular invalid segment. No correction across the 53
    conjunctive segments is therefore required or appropriate. Across the six
    candidate `N`, however, qualification is a UNION: the apparatus may select
    any `N` that fully qualifies, so six separate opportunities to be wrong
    exist. The budget is divided there and nowhere else:

        pass level per look = pass_level_family / candidate_count / n_looks

    giving, for any invalid candidate `N`,
    `P(falsely qualifying N) <= pass_level_family / candidate_count`, and by
    the union bound across the six candidates,
    `P(falsely qualifying any invalid N) <= pass_level_family`.

    **FAIL / false accusation.** A false FAIL can arise at any one of the 318
    segments independently, so the budget is divided across all of them and
    then across looks:

        fail level per look = fail_level_family / segment_count / n_looks

    giving `P(any false FAIL among the 318 segments) <= fail_level_family`.

    NOTE ON A CORRECTED CLAIM. An earlier version of this docstring asserted
    that correcting PASS across the 53 segments would make it "easier" to clear
    a defective engine. That sign was wrong: a smaller tail level produces a
    MORE conservative upper bound and therefore makes PASS HARDER, not easier.
    The reason not to divide PASS across the 53 segments is the
    intersection-union topology described above, not any effect on stringency.

    Both guarantees rest on union bounds, which require no independence -- and
    that matters here, because the looks are nested and the segments within an
    `N` are not independent claims. Clopper-Pearson is exact at every finite n.
    """

    def __init__(self, looks, nominal, pass_level_family, fail_level_family,
                 label, candidate_count=1, segment_count=1):
        """`looks` is a list of replication counts, ascending."""
        self.looks = list(looks)
        self.nominal = nominal
        self.pass_level_family = pass_level_family
        self.fail_level_family = fail_level_family
        self.candidate_count = max(1, int(candidate_count))
        self.segment_count = max(1, int(segment_count))
        self.label = label
        if sorted(self.looks) != self.looks or len(set(self.looks)) != len(self.looks):
            raise ValueError("looks must be strictly ascending")

        n_looks = float(len(self.looks))
        self.pass_level_per_candidate = (pass_level_family
                                         / float(self.candidate_count))
        self.fail_level_per_segment = (fail_level_family
                                       / float(self.segment_count))
        self.pass_levels = [self.pass_level_per_candidate / n_looks] * len(self.looks)
        self.fail_levels = [self.fail_level_per_segment / n_looks] * len(self.looks)
        self.criticals = [
            critical_values(n, self.pass_levels[i], self.fail_levels[i], nominal)
            for i, n in enumerate(self.looks)]

    # Backwards-compatible aliases used by older callers and reports.
    @property
    def pass_level(self):
        return self.pass_level_per_candidate

    @property
    def fail_level(self):
        return self.fail_level_family

    def budgets(self):
        return {
            "pass_family": self.pass_level_family,
            "pass_per_candidate_N": self.pass_level_per_candidate,
            "pass_per_look": self.pass_levels[0],
            "fail_family": self.fail_level_family,
            "fail_per_segment": self.fail_level_per_segment,
            "fail_per_look": self.fail_levels[0],
            "candidate_count": self.candidate_count,
            "segment_count": self.segment_count,
            "looks": len(self.looks),
        }

    def describe(self):
        return {
            "label": self.label,
            "looks": self.looks,
            "nominal": self.nominal,
            "candidate_count": self.candidate_count,
            "segment_count": self.segment_count,
            "budgets": self.budgets(),
            "pass_level_per_look": self.pass_levels,
            "fail_level_per_look": self.fail_levels,
            "critical_values": [
                {"look": i + 1, "replications": n,
                 "pass_if_events_at_most": self.criticals[i][0],
                 "fail_if_events_at_least": self.criticals[i][1]}
                for i, n in enumerate(self.looks)],
            "pass_error_control": (
                "Within a candidate N, qualification is an intersection-union "
                "claim over its %d conjunctive segments, so the budget is NOT "
                "divided across them. Across the %d candidate N it is a union "
                "of qualification opportunities, so the budget is divided "
                "there: P(falsely qualifying any invalid candidate N) <= %.4g "
                "by the union bound, which requires no independence."
                % (self.segment_count // max(1, self.candidate_count),
                   self.candidate_count, self.pass_level_family)),
            "fail_error_control": (
                "FAIL is divided across all %d segments and then across nested "
                "looks: P(any false FAIL among the segments) <= %.4g by two "
                "union bounds."
                % (self.segment_count, self.fail_level_family)),
        }

    def decide_at(self, look_index, events):
        pass_max, fail_min = self.criticals[look_index]
        if events <= pass_max:
            return "PASS"
        if events >= fail_min:
            return "FAIL"
        return "CONTINUE" if look_index + 1 < len(self.looks) else "UNRESOLVED"

    def decide_sequence(self, events_by_look):
        """Walk the looks, returning (verdict, look_number_1_based)."""
        for index, events in enumerate(events_by_look):
            verdict = self.decide_at(index, events)
            if verdict in ("PASS", "FAIL"):
                return verdict, index + 1
            if verdict == "UNRESOLVED":
                return "UNRESOLVED", index + 1
        return "UNRESOLVED", len(self.looks)


def critical_values(trials, pass_level, fail_level, nominal):
    """Integer thresholds equivalent to the exact-binomial bound comparisons.

    Both Clopper-Pearson bounds are non-decreasing in the event count, so
    "upper <= nominal" is downward closed and "lower > nominal" is upward
    closed. Each therefore reduces to a single integer threshold found by
    bisection, after which a decision costs two comparisons instead of two
    bound inversions.
    """
    lo, hi = 0, trials
    pass_max = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if binomial_upper_bound(mid, trials, pass_level) <= nominal:
            pass_max = mid
            lo = mid + 1
        else:
            hi = mid - 1

    lo, hi = 0, trials
    fail_min = trials + 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if binomial_lower_bound(mid, trials, fail_level) > nominal:
            fail_min = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return pass_max, fail_min


# ---------------------------------------------------------------------------
# Exact binomial sampling for the error-control demonstration
# ---------------------------------------------------------------------------

def binomial_cdf(n, p):
    """Exact binomial CDF, computed in log space and exponentiated."""
    if p <= 0.0:
        return [1.0] * (n + 1)
    if p >= 1.0:
        return [0.0] * n + [1.0]
    out = []
    total = 0.0
    for k in range(n + 1):
        logpmf = (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                  + k * math.log(p) + (n - k) * math.log1p(-p))
        total += math.exp(logpmf)
        out.append(min(1.0, total))
    out[-1] = 1.0
    return out


class BinomialSampler(object):
    """Inverse-CDF binomial sampler with a cached CDF.

    Sampling the count directly, rather than summing individual Bernoulli
    draws, is what makes a 100k-replication error-control demonstration
    tractable in pure Python.
    """

    def __init__(self, n, p):
        self.n = n
        self.cdf = binomial_cdf(n, p)

    def draw(self, rng):
        return bisect.bisect_left(self.cdf, rng.random())


def verify_error_control(plan, true_rate, replications, seed=20260920,
                         count_verdict="FAIL"):
    """Monte Carlo check that the plan's realised error respects its bound.

    Simulates the NESTED look structure honestly: look 2's event count is
    look 1's count plus an increment drawn over the additional replications,
    so the two looks share observations exactly as they do in the campaign.
    """
    rng = random.Random(seed)
    first = plan.looks[0]
    increments = [plan.looks[i] - plan.looks[i - 1]
                  for i in range(1, len(plan.looks))]
    samplers = [BinomialSampler(first, true_rate)] + [
        BinomialSampler(step, true_rate) for step in increments]

    hits = 0
    by_look = [0] * len(plan.looks)
    for _ in range(replications):
        events = 0
        counts = []
        for sampler in samplers:
            events += sampler.draw(rng)
            counts.append(events)
        verdict, look = plan.decide_sequence(counts)
        if verdict == count_verdict:
            hits += 1
            by_look[look - 1] += 1

    # The per-SEGMENT bound is what a single-segment simulation can test; the
    # familywise bound follows from it by the union bound across segments.
    bound = (plan.fail_level_per_segment if count_verdict == "FAIL"
             else plan.pass_level)
    observed = hits / float(replications)
    # Exact one-sided 99.9% upper bound on the realised error rate.
    upper = binomial_upper_bound(hits, replications, 0.001)
    return {
        "plan": plan.label,
        "true_rate": true_rate,
        "nominal": plan.nominal,
        "segment_count": plan.segment_count,
        "bound_scope": ("per-segment (familywise follows by the union bound "
                        "across %d segments)" % plan.segment_count),
        "counted_verdict": count_verdict,
        "replications": replications,
        "events": hits,
        "observed_error_rate": observed,
        "observed_error_upper_999": upper,
        "stated_bound": bound,
        "bound_respected": upper <= bound or observed <= bound,
        "strictly_within_bound": upper <= bound,
        "decisions_by_look": by_look,
        "nested_looks": True,
    }
