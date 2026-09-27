"""Registered defective-target panel.

Each mutant is the sound reference with exactly one registered defect injected.
Using the sound reference as the base is deliberate: it isolates the defect, so
a detection is attributable to that defect and not to incidental differences
between two unrelated implementations. Every mutant declares the defect class
it realises, the dangerous direction it pushes, and the harness check expected
to catch it; `harness.selfqual` requires that the *named* check actually fires.

A mutant that is caught only by an unrelated check is reported as a
MISATTRIBUTED detection and does not satisfy its registry row.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import contextlib
import copy

from ..reference import archive as archive_mod
from ..reference import interval as iv
from ..reference import sound_reference as sr


@contextlib.contextmanager
def patched(*pairs):
    """Temporarily replace (module, attribute, replacement) triples."""
    saved = []
    try:
        for module, name, replacement in pairs:
            saved.append((module, name, getattr(module, name)))
            setattr(module, name, replacement)
        yield
    finally:
        for module, name, original in reversed(saved):
            setattr(module, name, original)


# ---------------------------------------------------------------------------
# Estimator-level defects
# ---------------------------------------------------------------------------

class Mutant(object):
    defect_class = ""
    dangerous_direction = ""
    expected_check = ""
    target = "analyze"

    def analyze(self, payload):
        return sr.analyze(payload)

    def aggregate(self, payload):
        return archive_mod.aggregate(payload)


class TiesDiscarded(Mutant):
    """Ties dropped from the denominator: PS = W / (W + L)."""
    defect_class = "ties discarded"
    dangerous_direction = "inflates or deflates measured discrimination"
    expected_check = "point_estimates"

    def analyze(self, payload):
        original = sr.wlt

        def mutant_wlt(x_counts, y_counts):
            w, l, t = original(x_counts, y_counts)
            if w + l == 0:
                return 0.5, 0.5, 0.0
            return w / (w + l), l / (w + l), 0.0

        with patched((sr, "wlt", mutant_wlt)):
            return sr.analyze(payload)


class TiesAsWins(Mutant):
    """Ties promoted to full wins: PS = W + T."""
    defect_class = "ties promoted to full wins"
    dangerous_direction = "false SUPPORTED"
    expected_check = "point_estimates"

    def analyze(self, payload):
        original = sr.wlt

        def mutant_wlt(x_counts, y_counts):
            w, l, t = original(x_counts, y_counts)
            return w + t, l, 0.0

        with patched((sr, "wlt", mutant_wlt)):
            return sr.analyze(payload)


class NaiveCollision(Mutant):
    """Squared-proportion plug-in instead of the distinct-pair estimator."""
    defect_class = "naive squared-proportion collision"
    dangerous_direction = "biases C4 and the concentration-capacity gate"
    expected_check = "point_estimates"

    def analyze(self, payload):
        def mutant_collision(counts):
            n = sum(counts)
            if n < 2:
                return None
            return sum((v / float(n)) ** 2 for v in counts)

        with patched((sr, "collision", mutant_collision)):
            return sr.analyze(payload)


class CapacityNoHalfCredit(Mutant):
    """K_A = 1 - p_floor: floor ties denied their half credit."""
    defect_class = "ordinal capacity without floor half-credit"
    dangerous_direction = "false FLOOR_LIMITED / false range withholding"
    expected_check = "point_estimates"

    def analyze(self, payload):
        original = sr.specimen_report

        def mutant_report(specimen, d_near):
            report = original(specimen, d_near)
            report["K_A"] = 1.0 - report["p_floor_A0"]
            report["K_A_cliff"] = 2.0 * report["K_A"] - 1.0
            report["G"] = report["K_A"] - (report["P0"] - sr.M_I_P)
            return report

        with patched((sr, "specimen_report", mutant_report)):
            return sr.analyze(payload)


class CliffTransformWrong(Mutant):
    """delta = PS - 0.5 instead of 2 PS - 1."""
    defect_class = "incorrect Cliff-scale transform"
    dangerous_direction = "misreports the registered reporting scale"
    expected_check = "point_estimates"

    def analyze(self, payload):
        original = sr.specimen_report

        def mutant_report(specimen, d_near):
            report = original(specimen, d_near)
            report["delta0"] = report["P0"] - 0.5
            report["deltaA"] = report["PA"] - 0.5
            report["I_delta"] = report["I_P"]
            return report

        with patched((sr, "specimen_report", mutant_report)):
            return sr.analyze(payload)


class CategoryDistanceKernel(Mutant):
    """Comparison kernel weighted by category distance rather than order."""
    defect_class = "ordinal estimand replaced by an interval-scale one"
    dangerous_direction = "breaks monotone-relabeling invariance"
    expected_check = "invariance"

    def analyze(self, payload):
        def mutant_wlt(x_counts, y_counts):
            nx, ny = sum(x_counts), sum(y_counts)
            if nx == 0 or ny == 0:
                raise sr.Rejected("EMPTY_CELL", "empty cell")
            total = 0.0
            ties = 0
            for a in range(sr.K):
                for b in range(sr.K):
                    pairs = x_counts[a] * y_counts[b]
                    if not pairs:
                        continue
                    if a == b:
                        ties += pairs
                    else:
                        total += pairs * max(0.0, min(1.0, (a - b) / 9.0 + 0.5))
            denom = float(nx * ny)
            w = total / denom
            t = ties / denom
            return w, max(0.0, 1.0 - w - t), t

        with patched((sr, "wlt", mutant_wlt)):
            return sr.analyze(payload)


class PooledByCalls(Mutant):
    """Specimens pooled by call count instead of equally weighted."""
    defect_class = "specimens pooled by calls instead of equally weighted"
    dangerous_direction = "a single high-replicate specimen dominates the corpus"
    expected_check = "point_estimates"

    def analyze(self, payload):
        original = sr.analyze_semantic_light

        def mutant_light(light, config):
            result = original(light, config)
            reports = result["specimens"]
            weights = [float(r["n"]["00"] + r["n"]["0B"]) for r in reports]
            total = sum(weights)
            result["P0_bar"] = sum(r["P0"] * w for r, w in zip(reports, weights)) / total
            result["I_P_bar"] = sum(
                r["I_P"] * w for r, w in zip(reports, weights)) / total
            return result

        with patched((sr, "analyze_semantic_light", mutant_light)):
            return sr.analyze(payload)


# ---------------------------------------------------------------------------
# Uncertainty-level defects
# ---------------------------------------------------------------------------

class CrossPairsIndependent(Mutant):
    """n_X * n_Y cross-pairs treated as independent observations."""
    defect_class = "cross-pairs incorrectly treated as independent observations"
    dangerous_direction = "false SUPPORTED and false EQUIVALENTLY_ABSENT"
    expected_check = "interval_validity"

    def analyze(self, payload):
        def mutant_effective(n_x, n_y):
            return int(n_x) * int(n_y)

        with patched((iv, "effective_terms_two_sample", mutant_effective)):
            return sr.analyze(payload)


class PointMassBootstrap(Mutant):
    """Empirical bootstrap used as confirmatory uncertainty.

    An observed point mass resamples as a point mass, so every interval on a
    degenerate cell collapses to zero width -- the prohibited finite-sample
    behaviour of preregistration section 12.2.
    """
    defect_class = "point-mass empirical bootstrap as confirmatory uncertainty"
    dangerous_direction = "prohibited zero-width interval routed to SUPPORTED"
    expected_check = "interval_validity"

    def analyze(self, payload):
        original_ps = iv.ps_mean_interval
        original_ip = iv.interaction_mean_interval
        original_widen = iv.widen_to_minimum

        def degenerate(payload_lights):
            for light in payload_lights:
                for key in ("semantic_specimens", "mechanical_specimens"):
                    for specimen in light[key]:
                        for cell in specimen["cells"].values():
                            counts = cell["counts"]
                            if max(counts) == sum(counts):
                                return True
            return False

        collapse = degenerate(payload["lights"])

        def mutant_ps(point, cell_sizes, gamma):
            if collapse:
                return point, point
            return original_ps(point, cell_sizes, gamma)

        def mutant_ip(point, quad_sizes, gamma):
            if collapse:
                return point, point
            return original_ip(point, quad_sizes, gamma)

        def mutant_widen(lo, hi, floor_lo=None, floor_hi=None):
            return lo, hi

        with patched((iv, "ps_mean_interval", mutant_ps),
                     (iv, "interaction_mean_interval", mutant_ip),
                     (iv, "widen_to_minimum", mutant_widen)):
            return sr.analyze(payload)


class EquivalenceMarginWidened(Mutant):
    """Equivalence margin widened from 0.05 to 0.07 after a near miss."""
    defect_class = "equivalence margin widened after a near miss"
    dangerous_direction = "false EQUIVALENTLY_ABSENT"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        original = sr.c2_disposition

        def mutant_c2(ip_interval, a_values):
            disposition, guards = original(ip_interval, a_values)
            if disposition == "INDETERMINATE":
                lo, hi = ip_interval
                if -0.07 <= lo and hi <= 0.07:
                    if guards["no_cancellation"]:
                        return "EQUIVALENTLY_ABSENT", guards
            return disposition, guards

        with patched((sr, "c2_disposition", mutant_c2)):
            return sr.analyze(payload)


class DegeneracyIsEngineFailure(Mutant):
    """Any empirically degenerate cell routed to INFERENCE_ENGINE_FAILURE.

    Contract section 7 is explicit that degeneracy alone is NOT an inference
    engine failure. This is the false-withholding direction.
    """
    defect_class = "degeneracy misrouted to inference-engine failure"
    dangerous_direction = "false withholding of a valid disposition"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        result = sr.analyze(payload)
        for light in result["semantic_lights"]:
            degenerate = any(
                flag == "EMPIRICALLY_DEGENERATE"
                for specimen in light["specimens"]
                for flag in specimen["degeneracy"].values())
            if degenerate:
                light["c1"]["disposition"] = "INFERENCE_ENGINE_FAILURE"
                light["c2"]["disposition"] = "INFERENCE_ENGINE_FAILURE"
                light["inference_engine"]["status"] = "INFERENCE_ENGINE_FAILURE"
                light["A_l"] = False
        result["cross_light"]["A_vector"] = [
            l["A_l"] for l in result["semantic_lights"]]
        result["cross_light"]["A_all"] = all(result["cross_light"]["A_vector"])
        return result


# ---------------------------------------------------------------------------
# Topology-level defects
# ---------------------------------------------------------------------------

class GuardsIgnored(Mutant):
    """Recurrence and anti-singleton guards deleted."""
    defect_class = "positive-support guard creates rather than withholds"
    dangerous_direction = "false SUPPORTED"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        result = sr.analyze(payload)
        for light in result["semantic_lights"]:
            for key in ("c1", "c2"):
                if light[key]["disposition"] == "INDETERMINATE_GUARD_NOT_MET":
                    light[key]["disposition"] = "SUPPORTED"
            if (light["c1"]["disposition"] == "SUPPORTED"
                    and light["range"]["disposition"] == "RANGE_CLEARED"
                    and light["c2"]["disposition"] == "SUPPORTED"
                    and light["validity"]["cleared"]):
                light["A_l"] = True
        result["cross_light"]["A_vector"] = [
            l["A_l"] for l in result["semantic_lights"]]
        result["cross_light"]["A_all"] = all(result["cross_light"]["A_vector"])
        return result


class HeterogeneityGuardIgnored(Mutant):
    """Equivalence heterogeneity guards deleted."""
    defect_class = "heterogeneity guard creates equivalence"
    dangerous_direction = "false EQUIVALENTLY_ABSENT"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        result = sr.analyze(payload)
        for light in result["semantic_lights"]:
            for key in ("c1", "c2"):
                if light[key]["disposition"] == "HETEROGENEITY_NOT_CLEARED":
                    light[key]["disposition"] = "EQUIVALENTLY_ABSENT"
        return result


class RangeFiveOfSix(Mutant):
    """All-six range rule relaxed to five of six."""
    defect_class = "one failed specimen removed from the all-six range rule"
    dangerous_direction = "false clearance of the identification gate"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        original = sr.analyze_semantic_light

        def mutant_light(light, config):
            result = original(light, config)
            dispositions = result["range"]["specimen_dispositions"]
            adequate = sum(1 for d in dispositions if d == "RANGE_ADEQUATE")
            if adequate >= 5 and result["range"]["disposition"] == "RANGE_NOT_CLEARED":
                result["range"]["disposition"] = "RANGE_CLEARED"
                if result["c1"]["disposition"] == "SUPPORTED":
                    disposition, guards = sr.c2_disposition(
                        result["I_P_bar_interval"], result["a_values"])
                    result["c2"] = {"disposition": disposition, "guards": guards}
                    result["A_l"] = (result["validity"]["cleared"]
                                     and disposition == "SUPPORTED")
            return result

        with patched((sr, "analyze_semantic_light", mutant_light)):
            result = sr.analyze(payload)
        result["cross_light"]["A_vector"] = [
            l["A_l"] for l in result["semantic_lights"]]
        result["cross_light"]["A_all"] = all(result["cross_light"]["A_vector"])
        return result


class RangeGateIgnored(Mutant):
    """C2 declared without consulting the range gate at all."""
    defect_class = "identification gate bypassed"
    dangerous_direction = "false SUPPORTED under ordinal censoring"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        original = sr.analyze_semantic_light

        def mutant_light(light, config):
            result = original(light, config)
            if result["c2"]["disposition"] == "RANGE_NOT_CLEARED":
                disposition, guards = sr.c2_disposition(
                    result["I_P_bar_interval"], result["a_values"])
                result["c2"] = {"disposition": disposition, "guards": guards}
                result["A_l"] = (result["validity"]["cleared"]
                                 and result["c1"]["disposition"] == "SUPPORTED"
                                 and disposition == "SUPPORTED")
            return result

        with patched((sr, "analyze_semantic_light", mutant_light)):
            result = sr.analyze(payload)
        result["cross_light"]["A_vector"] = [
            l["A_l"] for l in result["semantic_lights"]]
        result["cross_light"]["A_all"] = all(result["cross_light"]["A_vector"])
        return result


class ValidityIgnored(Mutant):
    """Structural validity gates ignored for the confirmatory disposition."""
    defect_class = "structural eligibility gate bypassed"
    dangerous_direction = "false SUPPORTED on an ineligible instrument"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        stripped = copy.deepcopy(payload)
        flags = {}
        for light in stripped["lights"]:
            flags[light["id"]] = dict(light["validity"])
            for key in light["validity"]:
                light["validity"][key] = True
        result = sr.analyze(stripped)
        for light in result["semantic_lights"]:
            light["validity"]["flags"] = flags[light["light_id"]]
            light["validity"]["cleared"] = all(flags[light["light_id"]].values())
        for light in result["mechanical_lights"]:
            light["validity"]["flags"] = flags[light["light_id"]]
            light["validity"]["cleared"] = all(flags[light["light_id"]].values())
        return result


class C1GateSkipped(Mutant):
    """C2 opened for lights whose C1 is not supported."""
    defect_class = "attenuation chain broken"
    dangerous_direction = "false SUPPORTED without standalone discrimination"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        original = sr.analyze_semantic_light

        def mutant_light(light, config):
            result = original(light, config)
            if result["c2"]["disposition"] == "NOT_OPENED_C1_NOT_SUPPORTED":
                disposition, guards = sr.c2_disposition(
                    result["I_P_bar_interval"], result["a_values"])
                result["c2"] = {"disposition": disposition, "guards": guards}
            return result

        with patched((sr, "analyze_semantic_light", mutant_light)):
            return sr.analyze(payload)


class C4OverwritesC2(Mutant):
    """C4 allowed to rewrite the C2 disposition."""
    defect_class = "C4 allowed to overwrite C2"
    dangerous_direction = "false EQUIVALENTLY_ABSENT and false rescue"
    expected_check = "c4_noninterference"

    def analyze(self, payload):
        result = sr.analyze(payload)
        for light in result["semantic_lights"]:
            c4 = light["c4"].get("disposition")
            if c4 == "GENERAL_RESOLUTION_LOSS_EQUIVALENTLY_ABSENT":
                light["c2"]["disposition"] = "EQUIVALENTLY_ABSENT"
                light["A_l"] = False
            elif c4 == "C4_CONCENTRATION_CAPACITY_NOT_CLEARED":
                light["c2"]["disposition"] = "INDETERMINATE"
                light["A_l"] = False
        result["cross_light"]["A_vector"] = [
            l["A_l"] for l in result["semantic_lights"]]
        result["cross_light"]["A_all"] = all(result["cross_light"]["A_vector"])
        return result


class C4CapacityGateIgnored(Mutant):
    """The all-six concentration-capacity gate skipped.

    This is the defect the preregistration names explicitly in section 5.5:
    without the gate, a ceiling-concentrated baseline "manufactures an C4
    equivalence conclusion merely because Q had little remaining room to
    increase". On CL-11 the baselines are degenerate, so K_Q = 0 and every
    collision contrast is exactly zero -- the mutant reads that as evidence of
    absence rather than as absence of evidence.
    """
    defect_class = "C4 concentration-capacity gate bypassed"
    dangerous_direction = "false GENERAL_RESOLUTION_LOSS_EQUIVALENTLY_ABSENT"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        result = sr.analyze(payload)
        for light in result["semantic_lights"]:
            block = light["c4"]
            if block.get("disposition") != "C4_CONCENTRATION_CAPACITY_NOT_CLEARED":
                continue
            if block.get("Q_bar_interval") is None:
                continue
            q_values = [s["Q"] for s in light["specimens"]]
            if any(v is None for v in q_values):
                continue
            disposition, guards = sr.c4_disposition(
                block["Q_bar_interval"], q_values,
                block["component_q0_bar"], block["component_qB_bar"])
            block["disposition"] = disposition
            block["guards"] = guards
            block["capacity_cleared"] = True
        return result


class C4EquivalenceMarginWidened(Mutant):
    """C4 equivalence half-width widened from 0.05 to 0.10."""
    defect_class = "C4 equivalence margin widened"
    dangerous_direction = "false C4 equivalence displacing C4 indeterminacy"
    expected_check = "decision_consistency"

    def analyze(self, payload):
        original = sr.c4_disposition

        def mutant_c4(q_interval, q_values, q0_bar, qb_bar):
            disposition, guards = original(q_interval, q_values, q0_bar, qb_bar)
            if disposition == "GENERAL_RESOLUTION_LOSS_INDETERMINATE":
                lo, hi = q_interval
                if -0.10 <= lo and hi <= 0.10 and guards["no_cancellation"]:
                    return "GENERAL_RESOLUTION_LOSS_EQUIVALENTLY_ABSENT", guards
            return disposition, guards

        with patched((sr, "c4_disposition", mutant_c4)):
            return sr.analyze(payload)


class AllLightsMajority(Mutant):
    """A_all earned by a two-of-three majority instead of the conjunction."""
    defect_class = "cross-light conjunction replaced by a vote"
    dangerous_direction = "false cross-light generalization"
    expected_check = "cross_light"

    def analyze(self, payload):
        result = sr.analyze(payload)
        vector = result["cross_light"]["A_vector"]
        result["cross_light"]["A_all"] = sum(1 for v in vector if v) >= 2
        return result


class PooledCrossLightVerdict(Mutant):
    """A mixed light vector replaced by an unregistered pooled verdict."""
    defect_class = "mixed light vector replaced by a pooled verdict"
    dangerous_direction = "false generalization, suppressed heterogeneity"
    expected_check = "cross_light"

    def analyze(self, payload):
        result = sr.analyze(payload)
        vector = result["cross_light"]["A_vector"]
        result["cross_light"]["pooled_verdict"] = (
            "POOLED_ATTENUATION_SUPPORTED" if any(vector)
            else "POOLED_ATTENUATION_NOT_SUPPORTED")
        return result


class C3Emitted(Mutant):
    """An C3 cross-light stability disposition emitted despite being withheld."""
    defect_class = "withheld hypothesis emitted"
    dangerous_direction = "unregistered stability claim"
    expected_check = "cross_light"

    def analyze(self, payload):
        result = sr.analyze(payload)
        result["cross_light"]["c3"] = {
            "disposition": "CROSS_LIGHT_STABILITY_SUPPORTED",
            "reason": "pairwise differences within an unsealed margin",
        }
        return result


class SpecimenOrderDependent(Mutant):
    """Aggregate computed from the first specimen's effect alone."""
    defect_class = "input-order dependence"
    dangerous_direction = "single dominant specimen drives the corpus result"
    expected_check = "invariance"

    def analyze(self, payload):
        original = sr.analyze_semantic_light

        def mutant_light(light, config):
            result = original(light, config)
            first = result["specimens"][0]
            result["P0_bar"] = first["P0"]
            result["I_P_bar"] = first["I_P"]
            return result

        with patched((sr, "analyze_semantic_light", mutant_light)):
            return sr.analyze(payload)


# ---------------------------------------------------------------------------
# Archive-level defects
# ---------------------------------------------------------------------------

class FavourableReplacement(Mutant):
    """The most favourable valid attempt selected instead of the first."""
    defect_class = "a later favorable attempt selected after a valid earlier response"
    dangerous_direction = "upward bias in every cell it touches"
    expected_check = "archive_invariants"
    target = "aggregate"

    def aggregate(self, payload):
        original = archive_mod.aggregate
        reordered = copy.deepcopy(payload)
        # Re-index attempts so the highest-scoring valid attempt in each group
        # appears first in attempt order.
        groups = {}
        for record in reordered["attempts"]:
            key = (record["light_id"], record["specimen_id"], record["cell"],
                   record["replicate_index"])
            groups.setdefault(key, []).append(record)
        for records in groups.values():
            valid = [r for r in records
                     if r["transport_status"] == "OK" and r["schema_valid"]
                     and r["stamp_valid"] and r["route_match"]
                     and r["lens_valid"] and r["score"] is not None
                     and not r["cache_hit"]]
            if len(valid) < 2:
                continue
            indices = sorted(r["attempt_index"] for r in valid)
            for record, index in zip(
                    sorted(valid, key=lambda r: -r["score"]), indices):
                record["attempt_index"] = index
        return original(reordered)


class RefusalsDropped(Mutant):
    """Refusal responses removed from the count payload and the denominator."""
    defect_class = "refusals disappear through a denominator change"
    dangerous_direction = "hides differential refusal"
    expected_check = "archive_invariants"
    target = "aggregate"

    def aggregate(self, payload):
        result = archive_mod.aggregate(payload)
        kept = [row for row in result["selected_responses"] if not row["refusal"]]
        dropped = [row for row in result["selected_responses"] if row["refusal"]]
        result["selected_responses"] = kept
        result["selected_response_count"] = len(kept)
        result["refusal_summary"]["overall_rate"] = 0.0
        result["refusal_summary"]["overall_refusals"] = 0
        result["refusal_summary"]["limit_crossings"] = []
        result["refusal_summary"]["differentials"] = []
        result["global_deviations"] = [
            d for d in result["global_deviations"]
            if d.get("class") != "REFUSAL_LIMIT_CROSSED"]
        payload_copy, _totals = archive_mod._build_count_payload(
            kept, payload.get("analysis_config", {}))
        if payload_copy is not None:
            result["count_payload"] = payload_copy
        result["dropped_refusals"] = len(dropped)
        result["analysis_eligible"] = not result["missing_replicates"]
        return result


class MissingHidden(Mutant):
    """Missing replicates suppressed and the denominator quietly shrunk."""
    defect_class = "missingness disappears through a denominator change"
    dangerous_direction = "false clearance of instrument validity"
    expected_check = "archive_invariants"
    target = "aggregate"

    def aggregate(self, payload):
        result = archive_mod.aggregate(payload)
        result["missing_replicates"] = []
        result["unequal_valid_response_totals"] = []
        result["analysis_eligible"] = True
        return result


class AttemptsDropped(Mutant):
    """Invalid attempts removed from the record entirely."""
    defect_class = "invalid attempts disappear from the archive"
    dangerous_direction = "deviations become unobservable"
    expected_check = "archive_invariants"
    target = "aggregate"

    def aggregate(self, payload):
        result = archive_mod.aggregate(payload)
        result["technical_or_unselected_attempts"] = []
        result["global_deviations"] = []
        result["attempt_count"] = result["selected_response_count"]
        result["analysis_eligible"] = not result["missing_replicates"]
        return result


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY = [
    ("MUT-01-CROSS-PAIRS-INDEPENDENT", CrossPairsIndependent),
    ("MUT-02-POINT-MASS-BOOTSTRAP", PointMassBootstrap),
    ("MUT-03-EQUIVALENCE-MARGIN-WIDENED", EquivalenceMarginWidened),
    ("MUT-04-TIES-DISCARDED", TiesDiscarded),
    ("MUT-05-TIES-AS-WINS", TiesAsWins),
    ("MUT-06-RANGE-FIVE-OF-SIX", RangeFiveOfSix),
    ("MUT-07-C4-OVERWRITES-C2", C4OverwritesC2),
    ("MUT-08-FAVOURABLE-REPLACEMENT", FavourableReplacement),
    ("MUT-09-POOLED-BY-CALLS", PooledByCalls),
    ("MUT-10-NAIVE-COLLISION", NaiveCollision),
    ("MUT-11-GUARDS-IGNORED", GuardsIgnored),
    ("MUT-12-HETEROGENEITY-GUARD-IGNORED", HeterogeneityGuardIgnored),
    ("MUT-13-RANGE-GATE-IGNORED", RangeGateIgnored),
    ("MUT-14-VALIDITY-IGNORED", ValidityIgnored),
    ("MUT-15-C1-GATE-SKIPPED", C1GateSkipped),
    ("MUT-16-A-ALL-MAJORITY", AllLightsMajority),
    ("MUT-17-POOLED-CROSS-LIGHT-VERDICT", PooledCrossLightVerdict),
    ("MUT-18-CAPACITY-NO-HALF-CREDIT", CapacityNoHalfCredit),
    ("MUT-19-SPECIMEN-ORDER-DEPENDENT", SpecimenOrderDependent),
    ("MUT-20-CLIFF-TRANSFORM-WRONG", CliffTransformWrong),
    ("MUT-21-C3-EMITTED", C3Emitted),
    ("MUT-22-REFUSALS-DROPPED", RefusalsDropped),
    ("MUT-23-MISSING-HIDDEN", MissingHidden),
    ("MUT-24-CATEGORY-DISTANCE-KERNEL", CategoryDistanceKernel),
    ("MUT-25-DEGENERACY-IS-ENGINE-FAILURE", DegeneracyIsEngineFailure),
    ("MUT-26-ATTEMPTS-DROPPED", AttemptsDropped),
    ("MUT-27-C4-CAPACITY-GATE-IGNORED", C4CapacityGateIgnored),
    ("MUT-28-C4-EQUIVALENCE-MARGIN-WIDENED", C4EquivalenceMarginWidened),
]

BY_ID = dict(REGISTRY)


def describe():
    return [
        {
            "mutant_id": mutant_id,
            "defect_class": cls.defect_class,
            "dangerous_direction": cls.dangerous_direction,
            "expected_check": cls.expected_check,
            "target": cls.target,
        }
        for mutant_id, cls in REGISTRY
    ]
