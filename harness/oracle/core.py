"""Independent exact oracle for the ordinal-profile ordinal estimands.

Derived solely from `docs/PROFILE.md` sections 3, 4,
5 and 12, and checked against `docs/ANCHORS.md`. No
engine source was read and no target response was used to derive any formula
here.

Everything is computed in `fractions.Fraction`, so every point estimate in this
module is exact. Floating point appears only at the serialization boundary.

Independence note (amendment section 2 disclosure): this module is imported by
the harness and by the expected-answer generator. It is NOT imported by the
sound reference target in `harness/reference/`, which re-derives the same
quantities from the preregistration independently. The two implementations are
cross-checked against each other and against the hand anchors; agreement of all
three is a precondition of self-qualification.
"""

from fractions import Fraction

K = 10  # score categories 1..10, index 0 == category 1

HALF = Fraction(1, 2)

# Frozen primary thresholds, preregistration section 3.4.
T_B_P = Fraction(1, 5)  # 0.20 -> C1 boundary at 0.70
C1_BOUNDARY = HALF + T_B_P  # 0.70
M_I_P = Fraction(3, 20)  # 0.15
E_B_P = Fraction(1, 20)  # 0.05 -> C1 equivalence region [0.45, 0.55]
E_I_P = Fraction(1, 20)  # 0.05 -> C2 equivalence region [-0.05, 0.05]
M_C = Fraction(1, 10)  # 0.10
E_C = Fraction(1, 20)  # 0.05

C1_EQ_LO = HALF - E_B_P
C1_EQ_HI = HALF + E_B_P

# Qualitative cancellation thresholds, preregistration section 4.
C1_CANCEL = Fraction(1, 5)  # +/- 0.20 on centered b_il
C2_CANCEL = Fraction(3, 20)  # +/- 0.15 on a_il
C4_CANCEL = Fraction(1, 10)  # +/- 0.10 on Q_il

CELLS = ("00", "A0", "0B", "AB")


class OracleError(ValueError):
    """Raised when an input cannot carry the registered estimand."""


def _check_counts(counts):
    if len(counts) != K:
        raise OracleError("count vector must have exactly %d categories" % K)
    for c in counts:
        if not isinstance(c, int) or isinstance(c, bool) or c < 0:
            raise OracleError("counts must be non-negative integers")
    return list(counts)


def _check_probs(probs):
    if len(probs) != K:
        raise OracleError("probability vector must have exactly %d categories" % K)
    p = [Fraction(x) for x in probs]
    if any(v < 0 for v in p):
        raise OracleError("probabilities must be non-negative")
    if sum(p) != 1:
        raise OracleError("probabilities must sum to exactly 1")
    return p


# ---------------------------------------------------------------------------
# Section 3.1 / 12.1 -- win, loss, tie and tie-adjusted probability of superiority
# ---------------------------------------------------------------------------

def wlt_from_counts(x_counts, y_counts):
    """Exact (W, L, T) for the cross-tabulation of two realized count vectors.

    Anchor A03: W + L + T == 1 exactly.
    """
    x = _check_counts(x_counts)
    y = _check_counts(y_counts)
    nx, ny = sum(x), sum(y)
    if nx == 0 or ny == 0:
        raise OracleError("cannot form cross-pairs with an empty cell")
    wins = 0
    ties = 0
    for a in range(K):
        if not x[a]:
            continue
        for b in range(K):
            if not y[b]:
                continue
            if a > b:
                wins += x[a] * y[b]
            elif a == b:
                ties += x[a] * y[b]
    denom = nx * ny
    losses = denom - wins - ties
    return (Fraction(wins, denom), Fraction(losses, denom), Fraction(ties, denom))


def wlt_from_probs(p_probs, q_probs):
    """Exact population (W, L, T) for two categorical distributions."""
    p = _check_probs(p_probs)
    q = _check_probs(q_probs)
    wins = Fraction(0)
    ties = Fraction(0)
    for a in range(K):
        if not p[a]:
            continue
        for b in range(K):
            if not q[b]:
                continue
            if a > b:
                wins += p[a] * q[b]
            elif a == b:
                ties += p[a] * q[b]
    losses = Fraction(1) - wins - ties
    return (wins, losses, ties)


def ps_from_wlt(w, _l, t):
    """PS = W + 0.5 T  (preregistration section 3.1)."""
    return w + HALF * t


def ps_from_counts(x_counts, y_counts):
    return ps_from_wlt(*wlt_from_counts(x_counts, y_counts))


def ps_from_probs(p_probs, q_probs):
    return ps_from_wlt(*wlt_from_probs(p_probs, q_probs))


def cliff_delta(ps):
    """delta = 2 PS - 1 (anchor A04); equals W - L by anchor A03."""
    return 2 * Fraction(ps) - 1


def ps_from_cliff(delta):
    return (Fraction(delta) + 1) / 2


# ---------------------------------------------------------------------------
# Prohibited alternatives, retained so the harness can positively identify a
# wrong formula rather than merely observe a mismatch (anchors A07, A13, A14).
# ---------------------------------------------------------------------------

def ps_ties_discarded(x_counts, y_counts):
    w, l, _t = wlt_from_counts(x_counts, y_counts)
    if w + l == 0:
        return None
    return w / (w + l)


def ps_ties_as_wins(x_counts, y_counts):
    w, _l, t = wlt_from_counts(x_counts, y_counts)
    return w + t


def collision_naive(counts):
    """Prohibited squared-proportion plug-in (anchor A07)."""
    c = _check_counts(counts)
    n = sum(c)
    if n == 0:
        raise OracleError("empty cell")
    return sum(Fraction(v, n) ** 2 for v in c)


# ---------------------------------------------------------------------------
# Section 5.5 / 12.1 -- within-cell collision probability
# ---------------------------------------------------------------------------

def collision_from_counts(counts):
    """Unbiased distinct-pair collision estimate (anchor A06).

    Returns None when n < 2, where the estimand is undefined rather than zero.
    """
    c = _check_counts(counts)
    n = sum(c)
    if n < 2:
        return None
    return Fraction(sum(v * (v - 1) for v in c), n * (n - 1))


def collision_from_probs(probs):
    """Population collision probability sum_k p_k^2 (section 4, C4)."""
    p = _check_probs(probs)
    return sum(v * v for v in p)


def modal_mass(counts):
    """m_hat = max_k n_k / n, the section 12.2 degeneracy statistic."""
    c = _check_counts(counts)
    n = sum(c)
    if n == 0:
        raise OracleError("empty cell")
    return Fraction(max(c), n)


def degeneracy_flag(counts, d_near):
    """Section 12.2 classification. `d_near` is supplied, never guessed."""
    m = modal_mass(counts)
    d = Fraction(d_near)
    if m == 1:
        return "EMPIRICALLY_DEGENERATE"
    if d <= m < 1:
        return "EMPIRICALLY_NEAR_DEGENERATE"
    return "EMPIRICALLY_NONDEGENERATE"


def occupied_categories(counts):
    return sum(1 for v in _check_counts(counts) if v > 0)


def modal_categories(counts):
    c = _check_counts(counts)
    top = max(c)
    return [i + 1 for i, v in enumerate(c) if v == top and top > 0]


# ---------------------------------------------------------------------------
# Section 5.1 -- ordinal capacity
# ---------------------------------------------------------------------------

def floor_mass_from_counts(counts):
    """p_floor = P(Y = 1), the mass at the score floor."""
    c = _check_counts(counts)
    n = sum(c)
    if n == 0:
        raise OracleError("empty cell")
    return Fraction(c[0], n)


def ceiling_mass_from_counts(counts):
    c = _check_counts(counts)
    n = sum(c)
    if n == 0:
        raise OracleError("empty cell")
    return Fraction(c[K - 1], n)


def capacity_K_A(p_floor_a0):
    """K_A = 1 - 0.5 p_floor,A0  (anchor A08)."""
    return 1 - HALF * Fraction(p_floor_a0)


def capacity_K_A_cliff(p_floor_a0):
    """K_A^delta = 2 K_A - 1 = 1 - p_floor,A0 (anchor A04/A08)."""
    return 1 - Fraction(p_floor_a0)


def range_surplus_G(k_a, p0, m_i=M_I_P):
    """G = K_A - (P0 - M_I^P)  (anchor A11)."""
    return Fraction(k_a) - (Fraction(p0) - Fraction(m_i))


def capacity_K_Q(c00, c0b):
    """K_Q = 1 - 0.5 (C_00 + C_0B)  (anchor A12)."""
    return 1 - HALF * (Fraction(c00) + Fraction(c0b))


def concentration_surplus_G_Q(k_q, m_c=M_C):
    return Fraction(k_q) - Fraction(m_c)


def concentration_contrast_Q(c00, ca0, c0b, cab):
    """Q = 0.5[(C_A0 - C_00) + (C_AB - C_0B)]  (section 4, C4)."""
    return HALF * ((Fraction(ca0) - Fraction(c00)) + (Fraction(cab) - Fraction(c0b)))


# ---------------------------------------------------------------------------
# Specimen-level bundle
# ---------------------------------------------------------------------------

def specimen_metrics(cells, d_near=Fraction(9, 10)):
    """Complete exact metric bundle for one specimen x light.

    `cells` maps "00"/"A0"/"0B"/"AB" to 10-category count vectors.
    """
    for name in CELLS:
        if name not in cells:
            raise OracleError("missing cell %r" % name)

    c00, ca0, c0b, cab = (cells["00"], cells["A0"], cells["0B"], cells["AB"])

    w0, l0, t0 = wlt_from_counts(c00, c0b)
    p0 = ps_from_wlt(w0, l0, t0)
    wa, la, ta = wlt_from_counts(ca0, cab)
    pa = ps_from_wlt(wa, la, ta)
    i_p = p0 - pa

    p_floor_a0 = floor_mass_from_counts(ca0)
    k_a = capacity_K_A(p_floor_a0)
    g = range_surplus_G(k_a, p0)

    coll = {}
    for name in CELLS:
        coll[name] = collision_from_counts(cells[name])
    if any(v is None for v in coll.values()):
        k_q = None
        g_q = None
        q = None
    else:
        k_q = capacity_K_Q(coll["00"], coll["0B"])
        g_q = concentration_surplus_G_Q(k_q)
        q = concentration_contrast_Q(coll["00"], coll["A0"], coll["0B"], coll["AB"])

    return {
        "W0": w0, "L0": l0, "T0": t0, "P0": p0,
        "WA": wa, "LA": la, "TA": ta, "PA": pa,
        "I_P": i_p,
        "delta0": cliff_delta(p0),
        "deltaA": cliff_delta(pa),
        "I_delta": 2 * i_p,
        "p_floor_A0": p_floor_a0,
        "K_A": k_a,
        "K_A_cliff": capacity_K_A_cliff(p_floor_a0),
        "G": g,
        "collision": coll,
        "component_q0": (None if coll["A0"] is None or coll["00"] is None
                         else coll["A0"] - coll["00"]),
        "component_qB": (None if coll["AB"] is None or coll["0B"] is None
                         else coll["AB"] - coll["0B"]),
        "K_Q": k_q,
        "G_Q": g_q,
        "Q": q,
        "n": {name: sum(cells[name]) for name in CELLS},
        "m_hat": {name: modal_mass(cells[name]) for name in CELLS},
        "degeneracy": {name: degeneracy_flag(cells[name], d_near) for name in CELLS},
        "floor_mass": {name: floor_mass_from_counts(cells[name]) for name in CELLS},
        "ceiling_mass": {name: ceiling_mass_from_counts(cells[name]) for name in CELLS},
        "occupied": {name: occupied_categories(cells[name]) for name in CELLS},
        "modes": {name: modal_categories(cells[name]) for name in CELLS},
    }


# ---------------------------------------------------------------------------
# Section 3.2 -- equal-weight aggregation and leave-one-out means
# ---------------------------------------------------------------------------

def equal_weight_mean(values):
    """Equal specimen weights (anchor A13). Never weighted by replicate count."""
    vals = [Fraction(v) for v in values]
    if not vals:
        raise OracleError("empty specimen vector")
    return sum(vals) / len(vals)


def leave_one_out_means(values):
    """b_hat_-i: equal-weight mean of every value except index i."""
    vals = [Fraction(v) for v in values]
    n = len(vals)
    if n < 2:
        raise OracleError("leave-one-out needs at least two specimens")
    total = sum(vals)
    return [(total - vals[i]) / (n - 1) for i in range(n)]


def pooled_by_calls_PS(specimen_cells, x_cell, y_cell):
    """Prohibited call-level pooling across specimens (anchor A13).

    Retained only so the harness can positively identify this defect class.
    """
    px = [0] * K
    py = [0] * K
    for cells in specimen_cells:
        for i in range(K):
            px[i] += cells[x_cell][i]
            py[i] += cells[y_cell][i]
    return ps_from_counts(px, py)


# ---------------------------------------------------------------------------
# Section 4 -- registered point-estimate guards
# ---------------------------------------------------------------------------

def count_strictly_positive(values):
    return sum(1 for v in values if Fraction(v) > 0)


def all_strictly_positive(values):
    return all(Fraction(v) > 0 for v in values)


def all_within(values, lo, hi):
    lo, hi = Fraction(lo), Fraction(hi)
    return all(lo <= Fraction(v) <= hi for v in values)


def has_opposing_meaningful_effects(values, threshold):
    """Qualitative meaningful-effect cancellation (sections 4 C1/C2/C4/C5)."""
    th = Fraction(threshold)
    return (any(Fraction(v) >= th for v in values)
            and any(Fraction(v) <= -th for v in values))


def c1_guards(b_values, required_positive=4):
    """C1 recurrence, anti-singleton, and equivalence guards.

    `b_values` are the centered specimen effects b_il = P0_il - 0.5.
    """
    loo = leave_one_out_means(b_values)
    return {
        "recurrence": count_strictly_positive(b_values) >= required_positive,
        "positive_count": count_strictly_positive(b_values),
        "anti_singleton": all_strictly_positive(loo),
        "loo": loo,
        "equivalence_loo": all_within(loo, -E_B_P, E_B_P),
        "no_cancellation": not has_opposing_meaningful_effects(b_values, C1_CANCEL),
    }


def c2_guards(a_values, required_positive=4):
    """C2 guards on the specimen interactions a_il = I_P_il."""
    loo = leave_one_out_means(a_values)
    return {
        "recurrence": count_strictly_positive(a_values) >= required_positive,
        "positive_count": count_strictly_positive(a_values),
        "anti_singleton": all_strictly_positive(loo),
        "loo": loo,
        "equivalence_loo": all_within(loo, -E_I_P, E_I_P),
        "no_cancellation": not has_opposing_meaningful_effects(a_values, C2_CANCEL),
    }


def c4_guards(q_values, component_q0_mean, component_qB_mean, required_positive=4):
    """C4 guards: both component means plus recurrence and leave-one-out."""
    loo = leave_one_out_means(q_values)
    return {
        "components_positive": (Fraction(component_q0_mean) > 0
                                and Fraction(component_qB_mean) > 0),
        "components_in_band": (all_within([component_q0_mean], -E_C, E_C)
                               and all_within([component_qB_mean], -E_C, E_C)),
        "recurrence": count_strictly_positive(q_values) >= required_positive,
        "positive_count": count_strictly_positive(q_values),
        "anti_singleton": all_strictly_positive(loo),
        "loo": loo,
        "equivalence_loo": all_within(loo, -E_C, E_C),
        "no_cancellation": not has_opposing_meaningful_effects(q_values, C4_CANCEL),
    }


def c5_standalone_guards(b_values, required_positive=3):
    """C5 eligibility guards over the four mechanical controls (section 5.6)."""
    return c1_guards(b_values, required_positive=required_positive)


def c5_interaction_guards(a_values, required_positive=3):
    return c2_guards(a_values, required_positive=required_positive)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def to_float(value):
    if value is None:
        return None
    return float(Fraction(value))


def to_exact_string(value):
    if value is None:
        return None
    f = Fraction(value)
    return "%d/%d" % (f.numerator, f.denominator)


def jsonable(obj):
    """Recursively convert Fractions to {exact, decimal} pairs for archiving."""
    if isinstance(obj, Fraction):
        return {"exact": to_exact_string(obj), "decimal": float(obj)}
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj
