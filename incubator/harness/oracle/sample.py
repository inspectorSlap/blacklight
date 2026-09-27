"""Independent sample-truth oracle for fixed categorical count vectors.

Contract section 4 requires "an independent sample-truth oracle for fixed
categorical count vectors". Given the exact count vectors that the harness
sends to the target, this module states exactly what every point estimate must
be. These are the values the target is held to *exactly*; interval bounds are
governed by `reports/AMBIGUITY-REGISTER-v1.0.md` AMB-01 instead.

Deterministic-fixture discipline: the count vectors are frozen in
`fixtures/scenarios/`, not drawn at run time, so there is no sampling noise
between this oracle and the target. Sampling appears only in the coverage
campaign, which compares realized dispositions against *population* truth from
`harness.oracle.population` under the approved simulation rule.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


from fractions import Fraction

from . import core


def cell_truth(counts):
    """Exact realized-sample quantities for a single cell count vector."""
    c = core._check_counts(counts)
    n = sum(c)
    if n == 0:
        raise core.OracleError("empty cell")
    return {
        "counts": c,
        "n": n,
        "collision": core.collision_from_counts(c),
        "collision_naive_prohibited": core.collision_naive(c),
        "floor_mass": core.floor_mass_from_counts(c),
        "ceiling_mass": core.ceiling_mass_from_counts(c),
        "m_hat": core.modal_mass(c),
        "occupied": core.occupied_categories(c),
        "modes": core.modal_categories(c),
    }


def specimen_truth(cells, d_near=Fraction(9, 10)):
    """Exact realized-sample truth for one specimen x light."""
    return core.specimen_metrics(cells, d_near=d_near)


def light_truth(specimen_cells, d_near=Fraction(9, 10)):
    """Exact realized-sample truth for one light's specimen vector.

    `specimen_cells` is an ordered list of four-cell count mappings. The order
    is the frozen scenario order and is also the leave-one-out index order.
    """
    per_specimen = [specimen_truth(cells, d_near=d_near) for cells in specimen_cells]
    p0s = [s["P0"] for s in per_specimen]
    ips = [s["I_P"] for s in per_specimen]
    qs = [s["Q"] for s in per_specimen]
    q0s = [s["component_q0"] for s in per_specimen]
    qbs = [s["component_qB"] for s in per_specimen]

    result = {
        "specimens": per_specimen,
        "P0_bar": core.equal_weight_mean(p0s),
        "I_P_bar": core.equal_weight_mean(ips),
        "b_values": [v - Fraction(1, 2) for v in p0s],
        "a_values": list(ips),
        "G_values": [s["G"] for s in per_specimen],
    }

    if any(v is None for v in qs):
        result.update({"Q_bar": None, "q0_bar": None, "qB_bar": None,
                       "Q_values": qs, "G_Q_values": [s["G_Q"] for s in per_specimen]})
    else:
        result.update({
            "Q_bar": core.equal_weight_mean(qs),
            "q0_bar": core.equal_weight_mean(q0s),
            "qB_bar": core.equal_weight_mean(qbs),
            "Q_values": list(qs),
            "G_Q_values": [s["G_Q"] for s in per_specimen],
        })
    return result


def prohibited_alternatives(specimen_cells):
    """Values a *wrong* target would produce, for positive defect identification.

    Anchors A07, A13 and A14 record these so that when the harness observes a
    mismatch it can say which registered error the target made rather than only
    that it disagreed.
    """
    out = {}
    try:
        out["call_pooled_P0"] = core.pooled_by_calls_PS(specimen_cells, "00", "0B")
        out["call_pooled_PA"] = core.pooled_by_calls_PS(specimen_cells, "A0", "AB")
    except core.OracleError:
        pass
    per = []
    for cells in specimen_cells:
        entry = {
            "P0_ties_discarded": core.ps_ties_discarded(cells["00"], cells["0B"]),
            "P0_ties_as_wins": core.ps_ties_as_wins(cells["00"], cells["0B"]),
            "PA_ties_discarded": core.ps_ties_discarded(cells["A0"], cells["AB"]),
            "PA_ties_as_wins": core.ps_ties_as_wins(cells["A0"], cells["AB"]),
            "K_A_no_half_credit": 1 - core.floor_mass_from_counts(cells["A0"]),
            "collision_naive": {
                name: core.collision_naive(cells[name]) for name in core.CELLS
            },
        }
        per.append(entry)
    out["per_specimen"] = per
    return out


def counts_from_scores(scores):
    """Build a 10-category count vector from a list of integer scores."""
    counts = [0] * core.K
    for s in scores:
        if not isinstance(s, int) or isinstance(s, bool) or not (1 <= s <= core.K):
            raise core.OracleError("score out of range: %r" % (s,))
        counts[s - 1] += 1
    return counts


def relabel_counts(counts, mapping):
    """Apply a category relabeling. `mapping` maps 1-based old -> 1-based new."""
    c = core._check_counts(counts)
    out = [0] * core.K
    seen = set()
    for old, new in mapping.items():
        if new in seen:
            raise core.OracleError("relabeling is not injective")
        seen.add(new)
        out[new - 1] += c[old - 1]
    if sum(out) != sum(c):
        raise core.OracleError("relabeling did not preserve total mass")
    return out


def scale_counts(counts, factor):
    """Replicate a count vector k-fold; used for the interval-shrinkage check."""
    return [v * factor for v in core._check_counts(counts)]
