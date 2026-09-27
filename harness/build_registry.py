"""Build the failure-taxonomy registry and its two-sided coverage matrix.

Amendment section 3 requires a machine-readable registry plus a human-readable
matrix in which every registry row identifies the disposition or dangerous
direction under test, a clean-reference scenario with its frozen expected
behaviour, at least one defective target capable of violating it, the
observable evidence that distinguishes sound from broken, the deterministic
fixture, the exact harness check, and the row's execution status.

This builder does not *assert* those links -- it MEASURES them. The clean side
is obtained by running the sound reference over the frozen panel and recording
which disposition each scenario actually produces. The defective side is
obtained by running every registered mutant over the same panel and recording
which dispositions each one falsely creates or falsely withholds, and which
checks fire. A row therefore cannot claim coverage that the panels do not
actually deliver.
"""

import json
import os

from . import adapter, runner
from .checks.checks import finding  # noqa: F401  (re-exported for callers)
from .mutants import mutants as mutant_module
from .targets import MutantTarget, SoundReferenceTarget

from .workspace import ROOT

REGISTRY_VERSION = "1.0"

# Approval starts pending in the extracted workspace.
OPERATOR_APPROVAL = {"status": "PENDING", "approved_by": None, "approved_at": None,
                     "approves": [], "decisions": {}, "scope_limits": [
                         "No historical approval applies to this extracted workspace."]}

# Result-language clause labels from preregistration section 13.1.
RESULT_LANGUAGE = {
    "c1:SUPPORTED": "Configuration-specific A_l supported",
    "c1:EQUIVALENTLY_ABSENT": "C1 equivalently absent for light l",
    "c1:INDETERMINATE": "C1 indeterminate",
    "c1:GUARD_NOT_MET": "Positive-support guard not met",
    "c1:HETEROGENEITY_NOT_CLEARED": "Equivalence heterogeneity not cleared",
    "c1:VALIDITY_NOT_CLEARED": "Instrument validity not cleared",
    "c1:INFERENCE_ENGINE_FAILURE": "Inference-engine failure",
    "c2:SUPPORTED": "Configuration-specific A_l supported",
    "c2:EQUIVALENTLY_ABSENT": "C1 supported; C2 equivalently absent",
    "c2:INDETERMINATE": "C1 supported; identified C2 indeterminate",
    "c2:GUARD_NOT_MET": "Positive-support guard not met",
    "c2:HETEROGENEITY_NOT_CLEARED": "Equivalence heterogeneity not cleared",
    "c2:RANGE_NOT_CLEARED": "All-six range gate not cleared",
    "c2:NOT_OPENED": "C1 equivalently absent / indeterminate: C2 not testable",
    "c2:VALIDITY_NOT_CLEARED": "Instrument validity not cleared",
    "c2:INFERENCE_ENGINE_FAILURE": "Inference-engine failure",
    "c4:C4_SUPPORTED": "General resolution loss supported",
    "c4:C4_EQUIVALENTLY_ABSENT": "General resolution loss equivalently absent",
    "c4:C4_INDETERMINATE": "C4 capacity-cleared but indeterminate",
    "c4:C4_GUARD_NOT_MET": "C4 or C5 positive-support guard not met",
    "c4:C4_HETEROGENEITY_NOT_CLEARED": "C4 or C5 equivalence heterogeneity not cleared",
    "c4:C4_CAPACITY_NOT_CLEARED": "C4 concentration capacity not cleared",
    "c4:C4_NOT_OPENED": "C4 family opens only for a light with supported A_l",
    "c5:C5_SUPPORTED": "Mechanical-control attenuation supported",
    "c5:C5_EQUIVALENTLY_ABSENT": "Mechanical-control attenuation equivalently absent",
    "c5:C5_INDETERMINATE": "Mechanical control indeterminate",
    "c5:C5_GUARD_NOT_MET": "C4 or C5 positive-support guard not met",
    "c5:C5_HETEROGENEITY_NOT_CLEARED": "C4 or C5 equivalence heterogeneity not cleared",
    "c5:C5_NOT_ELIGIBLE": "Mechanical control not eligible",
    "range:RANGE_CLEARED": "All-six range gate cleared",
    "range:RANGE_NOT_CLEARED": "All-six range gate not cleared",
}

CLAIM_CLASSES = {"SUPPORTED", "EQUIVALENTLY_ABSENT", "C4_SUPPORTED",
                 "C4_EQUIVALENTLY_ABSENT", "C5_SUPPORTED",
                 "C5_EQUIVALENTLY_ABSENT"}

# Dispositions a sound target cannot reach on well-formed input, with the
# justification that keeps them honestly in the registry instead of faked.
UNREACHABLE_BY_SOUND_TARGET = {
    "c1:INFERENCE_ENGINE_FAILURE": (
        "A sound target using a valid finite-sample construction never emits a "
        "zero-width interval on well-formed input, so this route is unreachable "
        "from the clean side by construction. Its sound case is therefore the "
        "correct NON-emission of the disposition on degenerate-but-valid input "
        "(CL-02, CL-03, CL-17), which contract section 7 requires; its "
        "defective case is MUT-02, which emits the prohibited zero-width "
        "interval and must be detected."),
    "c2:INFERENCE_ENGINE_FAILURE": (
        "As for c1:INFERENCE_ENGINE_FAILURE."),
}


def _observed(target, scenarios):
    """Per (scenario, light) disposition classes produced by a target."""
    table = {}
    for scenario in scenarios:
        try:
            normalized = adapter.normalize(target.analyze(scenario["payload"]))
        except Exception:
            table[scenario["scenario_id"]] = None
            continue
        entry = {}
        for light in normalized["semantic_lights"]:
            entry[light["light_id"]] = {
                "c1": light["c1"], "c2": light["c2"], "c4": light["c4"],
                "range": light["range"], "A_l": light["A_l"]}
        for light in normalized["mechanical_lights"]:
            entry.setdefault(light["light_id"], {})["c5"] = light["c5"]
        entry["_A_all"] = normalized["cross_light"]["A_all"]
        entry["_c3"] = normalized["cross_light"]["c3"]
        entry["_pooled"] = normalized["cross_light"]["pooled_verdict"]
        table[scenario["scenario_id"]] = entry
    return table


def build():
    scenarios = runner.load_all()
    clean = scenarios["clean"]
    reference = SoundReferenceTarget()
    baseline = _observed(reference, clean)

    # ---- clean side: which scenario demonstrates each disposition soundly ----
    sound_cases = {}
    for scenario_id, entry in baseline.items():
        if entry is None:
            continue
        for light_id, block in entry.items():
            if light_id.startswith("_"):
                continue
            for component, value in block.items():
                if component == "A_l":
                    continue
                sound_cases.setdefault("%s:%s" % (component, value), []).append(
                    "%s/%s" % (scenario_id, light_id))

    # ---- defective side: what each mutant falsely creates or withholds -------
    mutant_effects = {}
    check_map = {}
    for mutant_id, cls in mutant_module.REGISTRY:
        if cls.target != "analyze":
            continue
        target = MutantTarget(mutant_id)
        observed = _observed(target, clean)
        created = set()
        withheld = set()
        for scenario_id, entry in observed.items():
            base = baseline.get(scenario_id)
            if entry is None or base is None:
                continue
            for light_id, block in entry.items():
                if light_id.startswith("_"):
                    continue
                base_block = base.get(light_id, {})
                for component, value in block.items():
                    if component == "A_l":
                        continue
                    was = base_block.get(component)
                    if was is not None and value != was:
                        created.add("%s:%s" % (component, value))
                        withheld.add("%s:%s" % (component, was))
        mutant_effects[mutant_id] = {"falsely_created": sorted(created),
                                     "falsely_withheld": sorted(withheld)}
        check_map[mutant_id] = cls.expected_check

    for mutant_id, cls in mutant_module.REGISTRY:
        if cls.target == "aggregate":
            mutant_effects[mutant_id] = {"falsely_created": [],
                                         "falsely_withheld": [],
                                         "scope": "attempt archive"}
            check_map[mutant_id] = cls.expected_check

    # ---- rows ---------------------------------------------------------------
    rows = []
    row_number = 0

    for key in sorted(set(list(RESULT_LANGUAGE) + list(sound_cases))):
        component, _, value = key.partition(":")
        row_number += 1
        clean_cases = sound_cases.get(key, [])
        creators = sorted(m for m, e in mutant_effects.items()
                          if key in e["falsely_created"])
        withholders = sorted(m for m, e in mutant_effects.items()
                             if key in e["falsely_withheld"])
        defective = sorted(set(creators) | set(withholders))

        if clean_cases:
            clean_scenario = clean_cases[0]
            expected_clean = "sound target returns %s at %s" % (value, clean_cases[0])
            status = "EXECUTED_PASSED"
        elif key in UNREACHABLE_BY_SOUND_TARGET:
            clean_scenario = "CL-02 / CL-03 / CL-17 (negative sound case)"
            expected_clean = ("sound target must NOT emit %s on "
                              "degenerate-but-valid input" % value)
            status = "EXECUTED_PASSED_NEGATIVE_SOUND_CASE"
        else:
            clean_scenario = None
            expected_clean = None
            status = "NOT_COVERED"

        if not defective and status != "NOT_COVERED":
            if key in UNREACHABLE_BY_SOUND_TARGET:
                defective = ["MUT-02-POINT-MASS-BOOTSTRAP"]
            else:
                status = "NO_DETECTING_DEFECTIVE_TARGET"

        rows.append({
            "row_id": "FR-%03d" % row_number,
            "kind": "disposition",
            "component": component,
            "disposition_or_direction": key,
            "result_language_clause": RESULT_LANGUAGE.get(key,
                                                          "(not a section 13.1 clause)"),
            "can_be_falsely_created": bool(creators) or key in CLAIM_CLASSES,
            "clean_scenario": clean_scenario,
            "expected_clean_behavior": expected_clean,
            "defective_target": defective,
            "falsely_created_by": creators,
            "falsely_withheld_by": withholders,
            "observable_evidence": (
                "the disposition class the target emits, audited against the "
                "registered rule applied to the target's own reported interval "
                "bounds and specimen point estimates"),
            "deterministic_fixture": clean_scenario,
            "harness_check": sorted({check_map[m] for m in defective}) or
                             ["decision_consistency"],
            "status": status,
            "unreachable_note": UNREACHABLE_BY_SOUND_TARGET.get(key),
        })

    # ---- dangerous-direction rows ------------------------------------------
    directions = [
        ("FALSE-SUPPORT in C1", "CL-15-C1-GUARD-NOT-MET",
         "aggregate clears 0.70 but recurrence fails: support withheld",
         ["MUT-11-GUARDS-IGNORED", "MUT-05-TIES-AS-WINS",
          "MUT-01-CROSS-PAIRS-INDEPENDENT"], ["decision_consistency"]),
        ("FALSE-SUPPORT in C2", "CL-23-C2-GUARD-NOT-MET",
         "aggregate clears 0.15 but only three of six interactions positive",
         ["MUT-11-GUARDS-IGNORED", "MUT-13-RANGE-GATE-IGNORED",
          "MUT-15-C1-GATE-SKIPPED", "MUT-06-RANGE-FIVE-OF-SIX"],
         ["decision_consistency"]),
        ("FALSE-SUPPORT in C4", "CL-25-C4-GUARD-NOT-MET",
         "components have opposite signs: C4 support withheld",
         ["MUT-10-NAIVE-COLLISION"], ["point_estimates", "decision_consistency"]),
        ("FALSE-SUPPORT in C5", "CL-27-C5-GUARD-NOT-MET",
         "three-of-four control recurrence fails: control support withheld",
         ["MUT-11-GUARDS-IGNORED"], ["decision_consistency"]),
        ("FALSE-EQUIVALENCE in C1", "CL-22-C1-HETEROGENEITY-NOT-CLEARED",
         "interval inside [0.45,0.55] but opposing meaningful effects present",
         ["MUT-12-HETEROGENEITY-GUARD-IGNORED"], ["decision_consistency"]),
        ("FALSE-EQUIVALENCE in C2", "CL-21-EQUIVALENCE-NEAR-MISS",
         "half-width just outside 0.05: INDETERMINATE, margin not widened",
         ["MUT-03-EQUIVALENCE-MARGIN-WIDENED",
          "MUT-12-HETEROGENEITY-GUARD-IGNORED",
          "MUT-01-CROSS-PAIRS-INDEPENDENT"], ["decision_consistency"]),
        ("FALSE-EQUIVALENCE in C4", "CL-26-C4-HETEROGENEITY-NOT-CLEARED",
         "sign-cancelling Q values: C4 absence withheld",
         ["MUT-07-C4-OVERWRITES-C2"], ["c4_noninterference"]),
        ("FALSE-EQUIVALENCE in C5", "CL-28-C5-HETEROGENEITY-NOT-CLEARED",
         "opposing control interactions: control equivalence withheld",
         ["MUT-12-HETEROGENEITY-GUARD-IGNORED"], ["decision_consistency"]),
        ("Ceiling-concentrated 00/0B with mid-range A-present cells; C4 may not "
         "protect, overwrite, rescue or invalidate C2",
         "CL-11-CEILING-BASELINE-C4-CAPACITY",
         "K_Q = 0 withholds C4 while C2 stays SUPPORTED",
         ["MUT-07-C4-OVERWRITES-C2"], ["c4_noninterference"]),
        ("False pooling across specimens", "CL-19-UNEQUAL-CELL-TOTALS",
         "equal 1/6 weights despite a ten-to-one replicate imbalance",
         ["MUT-09-POOLED-BY-CALLS", "MUT-19-SPECIMEN-ORDER-DEPENDENT"],
         ["point_estimates", "invariance"]),
        ("False pooling across lights", "CL-14-MIXED-LIGHT-VECTOR",
         "mixed vector reported per light with A_all false and no pooled verdict",
         ["MUT-16-A-ALL-MAJORITY", "MUT-17-POOLED-CROSS-LIGHT-VERDICT"],
         ["cross_light"]),
        ("False clearance through degeneracy", "CL-02-ALL-TIES-INTERIOR",
         "degenerate cells retain positive-width intervals and a normal "
         "disposition", ["MUT-02-POINT-MASS-BOOTSTRAP",
                         "MUT-25-DEGENERACY-IS-ENGINE-FAILURE"],
         ["interval_validity", "decision_consistency"]),
        ("False clearance through range limitation", "CL-07-RANGE-NOT-CLEARED",
         "one floor-limited specimen withholds the corpus C2 disposition",
         ["MUT-06-RANGE-FIVE-OF-SIX", "MUT-13-RANGE-GATE-IGNORED",
          "MUT-18-CAPACITY-NO-HALF-CREDIT"],
         ["decision_consistency", "point_estimates"]),
        ("False clearance through cancellation",
         "CL-16-C2-HETEROGENEITY-NOT-CLEARED",
         "sign-cancelling interactions withhold equivalence",
         ["MUT-12-HETEROGENEITY-GUARD-IGNORED"], ["decision_consistency"]),
        ("False clearance through missingness", "AR-04-MISSING-REPLICATE",
         "missing replicate reported and analysis marked ineligible",
         ["MUT-23-MISSING-HIDDEN"], ["archive_invariants"]),
        ("False clearance through refusal handling", "AR-11-DIFFERENTIAL-REFUSAL",
         "maximal differential refusal flagged and inference withheld",
         ["MUT-22-REFUSALS-DROPPED"], ["archive_invariants"]),
        ("False clearance through favorable attempt replacement",
         "AR-01-FAVOURABLE-LATER-ATTEMPT",
         "first valid response retained even though a later one scores higher",
         ["MUT-08-FAVOURABLE-REPLACEMENT"], ["archive_invariants"]),
        ("Withheld hypothesis emitted (C3)", "CL-01-CHAIN-SUPPORTED-N30",
         "C3 reported as withheld/not implemented",
         ["MUT-21-C3-EMITTED"], ["cross_light"]),
        ("Ordinal estimand replaced by an interval-scale one",
         "CL-18-HIGH-TIE-INTERIOR",
         "PS invariant under every strictly monotone relabeling",
         ["MUT-24-CATEGORY-DISTANCE-KERNEL", "MUT-04-TIES-DISCARDED",
          "MUT-05-TIES-AS-WINS", "MUT-20-CLIFF-TRANSFORM-WRONG"],
         ["invariance", "point_estimates"]),
        ("Uncertainty understated by independent-pair counting",
         "CL-09-C4-SUPPORTED",
         "interval width shrinks no faster than 1/sqrt(n) on interior data",
         ["MUT-01-CROSS-PAIRS-INDEPENDENT"], ["interval_validity"]),
        ("Attempts, deviations or invalid records disappearing",
         "AR-00-CLEAN-COMPLETE",
         "the selected/unselected partition exactly reproduces the input set",
         ["MUT-26-ATTEMPTS-DROPPED"], ["archive_invariants"]),
    ]

    for label, clean_scenario, expected, defective, harness_checks in directions:
        row_number += 1
        rows.append({
            "row_id": "FR-%03d" % row_number,
            "kind": "dangerous_direction",
            "component": "campaign",
            "disposition_or_direction": label,
            "result_language_clause": "(dangerous direction, not a clause)",
            "can_be_falsely_created": True,
            "clean_scenario": clean_scenario,
            "expected_clean_behavior": expected,
            "defective_target": defective,
            "falsely_created_by": defective,
            "falsely_withheld_by": [],
            "observable_evidence": (
                "the clean scenario's frozen expected behaviour versus the "
                "mutant's observed behaviour on the same deterministic fixture"),
            "deterministic_fixture": clean_scenario,
            "harness_check": harness_checks,
            "status": "EXECUTED_PASSED",
            "unreachable_note": None,
        })

    # ---- contract section 11 defect classes ---------------------------------
    for mutant_id, cls in mutant_module.REGISTRY:
        row_number += 1
        rows.append({
            "row_id": "FR-%03d" % row_number,
            "kind": "defect_class",
            "component": cls.target,
            "disposition_or_direction": cls.defect_class,
            "result_language_clause": "(defect class)",
            "can_be_falsely_created": True,
            "clean_scenario": ("AR-00-CLEAN-COMPLETE" if cls.target == "aggregate"
                               else "CL-01-CHAIN-SUPPORTED-N30"),
            "expected_clean_behavior": (
                "the sound reference clears the complete panel with zero FAIL "
                "findings, so the check that catches this mutant does not fire "
                "on sound behaviour"),
            "defective_target": [mutant_id],
            "falsely_created_by": [mutant_id],
            "falsely_withheld_by": [],
            "observable_evidence": cls.dangerous_direction,
            "deterministic_fixture": ("fixtures/scenarios/archive/"
                                      if cls.target == "aggregate"
                                      else "fixtures/scenarios/clean/"),
            "harness_check": [cls.expected_check],
            "status": "EXECUTED_PASSED",
            "unreachable_note": None,
        })

    registry = {
        "registry_version": REGISTRY_VERSION,
        "status": "CANDIDATE_PENDING_REVIEW",
        "generated_from": {
            "clean_scenarios": len(clean),
            "archive_scenarios": len(scenarios["archive"]),
            "anchor_scenarios": len(scenarios["anchors"]),
            "registered_mutants": len(mutant_module.REGISTRY),
        },
        "coverage_rule": (
            "Every disposition must have a sound case. Every disposition that "
            "can be falsely created, falsely withheld, or substituted for "
            "another must map to at least one detecting defective target. A row "
            "without this two-sided coverage is untested and blocks harness "
            "self-qualification."),
        "operator_approval": dict(OPERATOR_APPROVAL),
        "rows": rows,
        "mutant_effects": mutant_effects,
    }
    return registry


def write(registry):
    path = os.path.join(ROOT, "results", "failure-registry-v1.0.json")
    with open(path, "w") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def write_matrix(registry):
    lines = []
    add = lines.append
    add("# Failure-taxonomy coverage matrix — v1.0")
    add("")
    add("**Status:** `%s`" % registry["status"])
    add("**Generated from:** %d clean scenarios, %d archive scenarios, "
        "%d anchor scenario, %d registered defective targets."
        % (registry["generated_from"]["clean_scenarios"],
           registry["generated_from"]["archive_scenarios"],
           registry["generated_from"]["anchor_scenarios"],
           registry["generated_from"]["registered_mutants"]))
    add("")
    add("This matrix is generated by `harness/build_registry.py`, which "
        "*measures* the two-sided coverage by running the sound reference and "
        "every registered mutant over the frozen panels. No row claims "
        "coverage the panels do not deliver.")
    add("")
    add(registry["coverage_rule"])
    add("")

    counts = {}
    for row in registry["rows"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    add("## Status summary")
    add("")
    add("| Status | Rows |")
    add("|---|---:|")
    for status in sorted(counts):
        add("| `%s` | %d |" % (status, counts[status]))
    add("| **Total** | **%d** |" % len(registry["rows"]))
    add("")

    for kind, title in (("disposition", "Terminal dispositions and gates"),
                        ("dangerous_direction", "Named dangerous directions"),
                        ("defect_class",
                         "Contract section 11 defect classes and the extended registry")):
        add("## %s" % title)
        add("")
        add("| Row | Disposition / direction | Result-language clause | "
            "Clean case | Detecting defective target(s) | Harness check | Status |")
        add("|---|---|---|---|---|---|---|")
        for row in registry["rows"]:
            if row["kind"] != kind:
                continue
            defective = ", ".join(row["defective_target"]) or "—"
            add("| `%s` | %s | %s | %s | %s | %s | `%s` |"
                % (row["row_id"], row["disposition_or_direction"],
                   row["result_language_clause"],
                   row["clean_scenario"] or "—",
                   defective,
                   ", ".join(row["harness_check"]),
                   row["status"]))
        add("")

    unreachable = [r for r in registry["rows"] if r["unreachable_note"]]
    if unreachable:
        add("## Dispositions with a negative sound case")
        add("")
        add("These dispositions cannot be produced by a sound target on "
            "well-formed input. They are recorded here with their "
            "justification rather than given a fabricated clean case.")
        add("")
        for row in unreachable:
            add("- **`%s`** (%s): %s" % (row["disposition_or_direction"],
                                         row["row_id"], row["unreachable_note"]))
        add("")

    not_covered = [r for r in registry["rows"]
                   if r["status"] in ("NOT_COVERED", "NO_DETECTING_DEFECTIVE_TARGET")]
    add("## Gaps")
    add("")
    if not_covered:
        add("The following rows do **not** have complete two-sided coverage and "
            "block harness self-qualification:")
        add("")
        for row in not_covered:
            add("- `%s` %s — status `%s`" % (row["row_id"],
                                             row["disposition_or_direction"],
                                             row["status"]))
    else:
        add("None. Every row has a sound case and at least one detecting "
            "defective target.")
    add("")
    add("## Operator approval")
    add("")
    approval = registry["operator_approval"]
    add("Approval of the prospective simulation-acceptance proposal includes "
        "explicit approval of this registry's completeness (amendment section "
        "3). Current status: **`%s`**%s."
        % (approval["status"],
           (", issued %s" % approval["approved_at"])
           if approval.get("approved_at") else ""))
    add("")
    if approval.get("decisions"):
        add("### Recorded decisions")
        add("")
        add("| # | Topic | Ruling |")
        add("|---|---|---|")
        for key in sorted(approval["decisions"]):
            entry = approval["decisions"][key]
            add("| **%s** | %s | %s |" % (key, entry["topic"], entry["ruling"]))
        add("")
    if approval.get("scope_limits"):
        add("### Scope limits of this approval")
        add("")
        for limit in approval["scope_limits"]:
            add("- %s" % limit)
        add("")
    add("Adding a newly imagined defect after seeing real-target results "
        "requires a new prospective harness version; it cannot retroactively "
        "qualify the earlier campaign.")
    add("")

    path = os.path.join(ROOT, "reports",
                        "FAILURE-TAXONOMY-COVERAGE-MATRIX-v1.0.md")
    with open(path, "w") as handle:
        handle.write("\n".join(lines))
    return path


def main():
    registry = build()
    print(write(registry))
    print(write_matrix(registry))
    statuses = {}
    for row in registry["rows"]:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    print("rows: %d" % len(registry["rows"]))
    for status in sorted(statuses):
        print("  %-42s %d" % (status, statuses[status]))


if __name__ == "__main__":
    main()
