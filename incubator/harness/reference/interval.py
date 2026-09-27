"""Boundary-valid uncertainty construction "HB-1" for the sound reference target.

INDEPENDENCE STATEMENT (amendment section 2)
--------------------------------------------
This package is the *sound reference target*. It imports nothing from
`harness.oracle`, `harness.checks`, `harness.mutants`, `harness.runner`, or any
expected-answer generator. It re-derives every quantity from
`docs/PROFILE.md` in ordinary floating point, using a
different algebraic route from the exact-rational oracle. The only shared
lineage is the preregistration itself and the Python standard library. Agreement
between this target, the oracle and the hand anchors is therefore meaningful
evidence rather than a tautology.

WHAT THIS CONSTRUCTION IS, AND IS NOT
-------------------------------------
The preregistration deliberately leaves the confidence-region construction open
(sections 3.4 and 12.2, open question 2); see
`reports/AMBIGUITY-REGISTER-v1.0.md` AMB-01. HB-1 is therefore *a* valid
construction chosen and declared by this reference, not a reconstruction of the
registered method and not a claim about what the real engine should return. The
harness never asserts HB-1's numbers against the real engine.

VALIDITY ARGUMENT
-----------------
Every primary functional is an equally weighted combination of two-sample or
one-sample U-statistics with kernels bounded in [0,1]:

  PS(X,Y) = E[h(X,Y)],  h in {0, 0.5, 1}
  C       = P(Y = Y'),  kernel 1{Y = Y'} in {0,1}

By Hoeffding's permutation decomposition, a two-sample U-statistic with samples
of size n_X and n_Y equals an average over permutations of an average of
m = min(n_X, n_Y) i.i.d. bounded terms; a one-sample degree-2 U-statistic
likewise reduces to an average of floor(n/2) i.i.d. terms. Because the
exponential bound is convex, Jensen's inequality transfers Hoeffding's
inequality from each inner average to the permutation average. For a weighted
sum of independent terms in an interval of length `span` with weights w_k,

    P(|sum_k w_k (Z_k - E Z_k)| >= t) <= 2 exp(-2 t^2 / (span^2 sum_k w_k^2)),

which inverts to the half-width used throughout this module. The bound holds
for *every* finite n with no distributional assumption, which is exactly the
boundary-validity property section 12.2 requires: it does not degenerate when a
cell is empirically degenerate or when categories have zero counts, and its
width is strictly positive for every finite n. That is the structural reason
this reference can never emit the prohibited zero-width finite-sample interval
of anchor A17.

Floor mass is a plain binomial proportion and uses exact Clopper-Pearson
inversion instead, which is sharper and likewise exact for all n including the
zero-count and full-count boundaries.

Simultaneity is obtained by Bonferroni allocation across the three light-level
claims and, within a light, across the declared component bounds. Declaring
support therefore requires every component lower bound to clear, which is an
intersection-union test over the whole registered chain -- the construction
section 12.3 describes when implemented by inversion.

HB-1 is conservative. Coverage exceeds nominal, sometimes substantially. That
is a disclosed property: a conservative reference can fail to *earn* a
disposition, but it cannot manufacture one, which is the direction that matters
for a specificity leg.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import math

SPAN_PS = 1.0  # tie-adjusted comparison kernel h(a,b) lies in [0, 1]
MIN_WIDTH = 1e-9  # anchor A17 floor on any decision-bearing interval


class IntervalError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Hoeffding half-widths
# ---------------------------------------------------------------------------

def halfwidth(gamma, sum_w2, span=SPAN_PS):
    """Two-sided Hoeffding half-width for a weighted sum of bounded terms.

    `sum_w2` is sum_k w_k^2 over the independent terms; for an equally weighted
    average of N terms it is 1/N and this reduces to span*sqrt(ln(2/gamma)/(2N)).
    """
    if not (0.0 < gamma < 1.0):
        raise IntervalError("gamma must lie in (0,1)")
    if sum_w2 <= 0:
        raise IntervalError("sum of squared weights must be positive")
    return span * math.sqrt(math.log(2.0 / gamma) * sum_w2 / 2.0)


def effective_terms_two_sample(n_x, n_y):
    """Hoeffding's i.i.d. term count for a two-sample U-statistic."""
    m = min(int(n_x), int(n_y))
    if m < 1:
        raise IntervalError("a cell pair needs at least one call in each cell")
    return m


def effective_terms_one_sample(n):
    """Hoeffding's i.i.d. term count for a degree-2 one-sample U-statistic."""
    m = int(n) // 2
    if m < 1:
        raise IntervalError("collision needs at least two calls in the cell")
    return m


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def widen_to_minimum(lo, hi, floor_lo=None, floor_hi=None):
    """Guarantee strictly positive width (anchor A17) after clamping."""
    if hi - lo >= MIN_WIDTH:
        return lo, hi
    pad = (MIN_WIDTH - (hi - lo)) / 2.0
    lo -= pad
    hi += pad
    if floor_lo is not None:
        lo = max(lo, floor_lo)
    if floor_hi is not None:
        hi = min(hi, floor_hi)
    if hi - lo < MIN_WIDTH:  # pinned against both physical limits
        raise IntervalError("cannot maintain positive interval width")
    return lo, hi


# ---------------------------------------------------------------------------
# Exact Clopper-Pearson inversion for a binomial proportion
# ---------------------------------------------------------------------------

def _log_binom_tail_ge(n, x, p):
    """log P(Binomial(n,p) >= x), computed in log space."""
    if x <= 0:
        return 0.0
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return 0.0
    terms = []
    for k in range(x, n + 1):
        terms.append(
            math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p)
        )
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def _log_binom_tail_le(n, x, p):
    """log P(Binomial(n,p) <= x)."""
    if x >= n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return float("-inf")
    terms = []
    for k in range(0, x + 1):
        terms.append(
            math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p)
        )
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def clopper_pearson(x, n, gamma, iterations=200):
    """Two-sided exact binomial interval at confidence 1 - gamma.

    Exact for every n, including x = 0 and x = n, where it returns a strictly
    one-sided but still non-degenerate interval.
    """
    x = int(x)
    n = int(n)
    if n <= 0:
        raise IntervalError("binomial n must be positive")
    if not (0 <= x <= n):
        raise IntervalError("binomial x out of range")
    tail = math.log(gamma / 2.0)

    if x == 0:
        lo = 0.0
    else:
        a, b = 0.0, 1.0
        for _ in range(iterations):
            mid = (a + b) / 2.0
            if _log_binom_tail_ge(n, x, mid) < tail:
                a = mid
            else:
                b = mid
        lo = a

    if x == n:
        hi = 1.0
    else:
        a, b = 0.0, 1.0
        for _ in range(iterations):
            mid = (a + b) / 2.0
            if _log_binom_tail_le(n, x, mid) > tail:
                a = mid
            else:
                b = mid
        hi = b

    return clamp(lo, 0.0, 1.0), clamp(hi, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Functional bounds
# ---------------------------------------------------------------------------

def ps_interval(point, n_x, n_y, gamma):
    """Interval for a single tie-adjusted probability of superiority."""
    m = effective_terms_two_sample(n_x, n_y)
    t = halfwidth(gamma, 1.0 / m, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, 0.0, 1.0),
                              clamp(point + t, 0.0, 1.0), 0.0, 1.0)
    return lo, hi


def ps_mean_interval(point, cell_sizes, gamma):
    """Interval for an equal-weight mean of per-specimen PS values.

    `cell_sizes` is a list of (n_x, n_y) pairs, one per specimen.
    """
    s = len(cell_sizes)
    if s == 0:
        raise IntervalError("empty specimen vector")
    sum_w2 = sum(1.0 / effective_terms_two_sample(nx, ny) for nx, ny in cell_sizes)
    sum_w2 /= float(s * s)
    t = halfwidth(gamma, sum_w2, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, 0.0, 1.0),
                              clamp(point + t, 0.0, 1.0), 0.0, 1.0)
    return lo, hi


def interaction_interval(point, quad_sizes, gamma):
    """Interval for I_P = PS(00,0B) - PS(A0,AB) on one specimen.

    `quad_sizes` is ((n00, n0B), (nA0, nAB)).
    """
    (n00, n0b), (na0, nab) = quad_sizes
    sum_w2 = (1.0 / effective_terms_two_sample(n00, n0b)
              + 1.0 / effective_terms_two_sample(na0, nab))
    t = halfwidth(gamma, sum_w2, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, -1.0, 1.0),
                              clamp(point + t, -1.0, 1.0), -1.0, 1.0)
    return lo, hi


def interaction_mean_interval(point, quad_sizes_per_specimen, gamma):
    """Interval for the equal-weight mean interaction I_P_bar over specimens."""
    s = len(quad_sizes_per_specimen)
    if s == 0:
        raise IntervalError("empty specimen vector")
    total = 0.0
    for (n00, n0b), (na0, nab) in quad_sizes_per_specimen:
        total += (1.0 / effective_terms_two_sample(n00, n0b)
                  + 1.0 / effective_terms_two_sample(na0, nab))
    sum_w2 = total / float(s * s)
    t = halfwidth(gamma, sum_w2, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, -1.0, 1.0),
                              clamp(point + t, -1.0, 1.0), -1.0, 1.0)
    return lo, hi


def collision_interval(point, n, gamma):
    """Interval for a within-cell collision probability."""
    m = effective_terms_one_sample(n)
    t = halfwidth(gamma, 1.0 / m, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, 0.0, 1.0),
                              clamp(point + t, 0.0, 1.0), 0.0, 1.0)
    return lo, hi


def collision_combo_interval(point, weighted_cells, gamma, lo_limit, hi_limit):
    """Interval for a signed linear combination of collision probabilities.

    `weighted_cells` is a list of (weight, n) pairs. Used for Q, its two
    component contrasts, and K_Q.
    """
    sum_w2 = 0.0
    for weight, n in weighted_cells:
        m = effective_terms_one_sample(n)
        sum_w2 += (weight * weight) / m
    t = halfwidth(gamma, sum_w2, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, lo_limit, hi_limit),
                              clamp(point + t, lo_limit, hi_limit),
                              lo_limit, hi_limit)
    return lo, hi


def collision_combo_mean_interval(point, per_specimen_weighted_cells, gamma,
                                  lo_limit, hi_limit):
    """Interval for the equal-weight mean of a collision combination."""
    s = len(per_specimen_weighted_cells)
    if s == 0:
        raise IntervalError("empty specimen vector")
    total = 0.0
    for weighted_cells in per_specimen_weighted_cells:
        for weight, n in weighted_cells:
            m = effective_terms_one_sample(n)
            total += (weight * weight) / m
    sum_w2 = total / float(s * s)
    t = halfwidth(gamma, sum_w2, SPAN_PS)
    lo, hi = widen_to_minimum(clamp(point - t, lo_limit, hi_limit),
                              clamp(point + t, lo_limit, hi_limit),
                              lo_limit, hi_limit)
    return lo, hi


def range_surplus_interval(p_floor_count, n_a0, p0_point, n00, n0b, gamma, m_i):
    """Joint interval for G = K_A - (P0 - M_I), preserving both uncertainties.

    Section 5.3 forbids "subtracting unrelated marginal confidence bounds". The
    two inputs here are not unrelated marginals of one estimate: p_floor,A0 is a
    functional of the A0 cell and P0 is a functional of the 00 and 0B cells,
    which are independent samples. The joint region is their product at a
    Bonferroni-split level, and G is bounded by its monotone image over that
    product -- G is decreasing in p_floor,A0 and decreasing in P0, so the
    extremes are attained at the corners. The dependence that section 5.3
    protects (P0 appearing in both G and the C2 outcome) is preserved because
    the same P0 bound object is reused rather than recomputed.
    """
    half = gamma / 2.0
    pf_lo, pf_hi = clopper_pearson(p_floor_count, n_a0, half)
    p0_lo, p0_hi = ps_interval(p0_point, n00, n0b, half)
    k_a_lo = 1.0 - 0.5 * pf_hi
    k_a_hi = 1.0 - 0.5 * pf_lo
    g_lo = k_a_lo - (p0_hi - m_i)
    g_hi = k_a_hi - (p0_lo - m_i)
    g_lo, g_hi = widen_to_minimum(g_lo, g_hi)
    return {
        "p_floor_interval": [pf_lo, pf_hi],
        "K_A_interval": [k_a_lo, k_a_hi],
        "P0_interval": [p0_lo, p0_hi],
        "G_interval": [g_lo, g_hi],
    }


def concentration_capacity_interval(c00, n00, c0b, n0b, gamma, m_c):
    """Joint interval for K_Q = 1 - 0.5(C_00 + C_0B) and G_Q = K_Q - M_C."""
    point_kq = 1.0 - 0.5 * (c00 + c0b)
    kq_lo, kq_hi = collision_combo_interval(
        point_kq, [(-0.5, n00), (-0.5, n0b)], gamma, 0.0, 1.0)
    gq_lo, gq_hi = widen_to_minimum(kq_lo - m_c, kq_hi - m_c)
    return {
        "K_Q_interval": [kq_lo, kq_hi],
        "G_Q_interval": [gq_lo, gq_hi],
    }
