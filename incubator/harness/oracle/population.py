"""Independent population-truth oracle.

Contract section 4 requires "an independent population-truth oracle for
specified categorical distributions". This module computes the *parameter*
values implied by fully specified categorical distributions, in exact rational
arithmetic. These are the values a scenario's generating distributions possess
by construction.

Contract section 5 is explicit that population truth and realized-sample truth
must remain separate: "Random sample estimates are not expected to equal their
generating population values exactly." Nothing in this module may be used as an
expected answer for a finite realized sample; that is the job of
`harness.oracle.sample`. The two are deliberately kept in separate modules so
that a scenario cannot accidentally assert one against the other -- the
scenario loader records which oracle governs each frozen expectation.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


from fractions import Fraction

from . import core


def cell_truth(probs):
    """Population quantities for a single cell distribution."""
    p = core._check_probs(probs)
    return {
        "probs": p,
        "collision": core.collision_from_probs(p),
        "floor_mass": p[0],
        "ceiling_mass": p[core.K - 1],
        "modal_mass": max(p),
        "support_size": sum(1 for v in p if v > 0),
    }


def specimen_truth(cell_probs):
    """Population truth for one specimen x light from four cell distributions.

    `cell_probs` maps "00"/"A0"/"0B"/"AB" to exact probability vectors.
    """
    for name in core.CELLS:
        if name not in cell_probs:
            raise core.OracleError("missing cell %r" % name)

    p00 = core._check_probs(cell_probs["00"])
    pa0 = core._check_probs(cell_probs["A0"])
    p0b = core._check_probs(cell_probs["0B"])
    pab = core._check_probs(cell_probs["AB"])

    w0, l0, t0 = core.wlt_from_probs(p00, p0b)
    p0 = core.ps_from_wlt(w0, l0, t0)
    wa, la, ta = core.wlt_from_probs(pa0, pab)
    pa = core.ps_from_wlt(wa, la, ta)

    c = {
        "00": core.collision_from_probs(p00),
        "A0": core.collision_from_probs(pa0),
        "0B": core.collision_from_probs(p0b),
        "AB": core.collision_from_probs(pab),
    }

    p_floor_a0 = pa0[0]
    k_a = core.capacity_K_A(p_floor_a0)
    k_q = core.capacity_K_Q(c["00"], c["0B"])

    return {
        "W0": w0, "L0": l0, "T0": t0, "P0": p0,
        "WA": wa, "LA": la, "TA": ta, "PA": pa,
        "I_P": p0 - pa,
        "delta0": core.cliff_delta(p0),
        "deltaA": core.cliff_delta(pa),
        "I_delta": 2 * (p0 - pa),
        "p_floor_A0": p_floor_a0,
        "K_A": k_a,
        "G": core.range_surplus_G(k_a, p0),
        "collision": c,
        "component_q0": c["A0"] - c["00"],
        "component_qB": c["AB"] - c["0B"],
        "K_Q": k_q,
        "G_Q": core.concentration_surplus_G_Q(k_q),
        "Q": core.concentration_contrast_Q(c["00"], c["A0"], c["0B"], c["AB"]),
    }


def light_truth(specimen_cell_probs):
    """Population truth for a light: six or four specimens, equal weights."""
    per_specimen = [specimen_truth(cp) for cp in specimen_cell_probs]
    p0s = [s["P0"] for s in per_specimen]
    ips = [s["I_P"] for s in per_specimen]
    qs = [s["Q"] for s in per_specimen]
    return {
        "specimens": per_specimen,
        "P0_bar": core.equal_weight_mean(p0s),
        "I_P_bar": core.equal_weight_mean(ips),
        "Q_bar": core.equal_weight_mean(qs),
        "q0_bar": core.equal_weight_mean([s["component_q0"] for s in per_specimen]),
        "qB_bar": core.equal_weight_mean([s["component_qB"] for s in per_specimen]),
        "b_values": [v - Fraction(1, 2) for v in p0s],
        "a_values": list(ips),
        "Q_values": list(qs),
    }


def uniform(categories):
    """Uniform distribution on the given 1-based categories."""
    p = [Fraction(0)] * core.K
    n = len(categories)
    if n == 0:
        raise core.OracleError("empty support")
    for c in categories:
        p[c - 1] += Fraction(1, n)
    return p


def point_mass(category):
    p = [Fraction(0)] * core.K
    p[category - 1] = Fraction(1)
    return p


def mixture(pairs):
    """Distribution from (category, weight) pairs; weights are normalized."""
    p = [Fraction(0)] * core.K
    total = sum(Fraction(w) for _c, w in pairs)
    if total <= 0:
        raise core.OracleError("weights must sum to a positive value")
    for c, w in pairs:
        p[c - 1] += Fraction(w) / total
    return p
