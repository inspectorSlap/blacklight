"""The two-sided, conjunctive harness self-qualification gate.

Amendment section 2 requires BOTH legs before the real engine may be touched:

* **Sensitivity** -- every registered defective target is detected, and (this
  harness adds the stricter reading) detected by the check the registry names
  for it. A detection by an unrelated check is reported as MISATTRIBUTED and
  does not satisfy the row.
* **Specificity** -- the sound reference clears the complete applicable clean
  panel with zero FAIL findings while still returning the preregistered
  expected disposition for every scenario.

Plus the two gates from section 2's failure list:

* every hand-computed anchor reproduced exactly by the oracle AND the sound
  reference; and
* a complete, approved failure-taxonomy coverage matrix.

"No aggregate sensitivity or specificity percentage may conceal a single
required miss. The gate is conjunctive." -- so this module reports per-row
outcomes and refuses to compute a passing score from a partial panel.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os

from . import runner
from .checks import anchor_checks
from .checks.checks import finding
from .mutants import mutants as mutant_module
from .targets import MutantTarget, SoundReferenceTarget

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESULT_STATES = ("HARNESS_NOT_SELF_QUALIFIED", "ENGINE_REJECTED",
                 "ENGINE_NOT_YET_QUALIFIABLE", "ENGINE_CANDIDATE_QUALIFIED")


def _fails(findings):
    return [f for f in findings if f["severity"] == "FAIL"]


def run_specificity(scenarios):
    """The sound reference must clear everything without alleging a defect."""
    target = SoundReferenceTarget()
    findings = []
    findings += runner.run_analysis_panel(target, scenarios["clean"], strict=True)
    findings += runner.run_analysis_panel(target, scenarios["anchors"], strict=True)
    findings += runner.run_archive_panel(target, scenarios["archive"])
    findings += runner.run_anchor_panel(target, scenarios["anchors"])
    failures = _fails(findings)
    return {
        "leg": "specificity",
        "target": target.target_id,
        "scenarios_run": (len(scenarios["clean"]) + len(scenarios["anchors"])
                          + len(scenarios["archive"])),
        "passed": not failures,
        "failures": failures,
        "findings": findings,
        "summary": runner.summarize(findings),
    }


def run_sensitivity(scenarios):
    """Every registered mutant must be detected by the check that owns it."""
    rows = []
    for mutant_id, cls in mutant_module.REGISTRY:
        target = MutantTarget(mutant_id)
        if cls.target == "aggregate":
            findings = runner.run_archive_panel(target, scenarios["archive"])
        else:
            findings = runner.run_analysis_panel(
                target, scenarios["clean"], strict=False)
            findings += runner.run_anchor_panel(target, scenarios["anchors"])
            findings += runner.run_analysis_panel(
                target, scenarios["anchors"], strict=False)
        failures = _fails(findings)
        checks_that_fired = sorted({f["check"] for f in failures})
        expected = cls.expected_check
        detected = bool(failures)
        # The named check must be among those that fired. `anchors` and
        # `point_estimates` are treated as a single attribution family because
        # the anchor panel is the point oracle applied to the frozen anchors.
        family = {expected}
        if expected == "point_estimates":
            family.add("anchors")
        if expected == "interval_validity":
            family.add("decision_consistency")
        attributed = bool(family & set(checks_that_fired))
        rows.append({
            "mutant_id": mutant_id,
            "defect_class": cls.defect_class,
            "dangerous_direction": cls.dangerous_direction,
            "target": cls.target,
            "expected_check": expected,
            "detected": detected,
            "checks_that_fired": checks_that_fired,
            "attributed_to_expected_check": attributed,
            "failure_count": len(failures),
            "first_evidence": failures[0]["message"] if failures else None,
            "row_passed": detected and attributed,
            "row_status": ("DETECTED" if detected and attributed
                           else "MISATTRIBUTED" if detected
                           else "ESCAPED"),
        })
    return {
        "leg": "sensitivity",
        "mutants_run": len(rows),
        "passed": all(row["row_passed"] for row in rows),
        "escaped": [r["mutant_id"] for r in rows if r["row_status"] == "ESCAPED"],
        "misattributed": [r["mutant_id"] for r in rows
                          if r["row_status"] == "MISATTRIBUTED"],
        "rows": rows,
    }


def run_anchor_gate():
    """Oracle, structural ownership, and the sound reference against anchors."""
    anchors = anchor_checks.load_anchors()
    oracle_findings, checked = anchor_checks.verify_oracle(anchors)
    structural_findings, owners = anchor_checks.verify_structural_anchors(anchors)
    scenarios = runner.load_family("anchors")
    reference_findings = runner.run_anchor_panel(SoundReferenceTarget(), scenarios)
    findings = oracle_findings + structural_findings + reference_findings
    failures = _fails(findings)
    return {
        "leg": "anchors",
        "numeric_values_checked": checked,
        "structural_anchor_owners": owners,
        "oracle_passed": not _fails(oracle_findings),
        "reference_passed": not _fails(reference_findings),
        "passed": not failures,
        "failures": failures,
        "findings": findings,
    }


def run_registry_gate():
    """The coverage matrix must be complete and operator-approved."""
    path = os.path.join(ROOT, "results", "failure-registry-v1.0.json")
    if not os.path.isfile(path):
        return {"leg": "failure_registry", "passed": False,
                "reason": "failure registry not present"}
    with open(path, "r") as handle:
        registry = json.load(handle)

    incomplete = []
    for row in registry["rows"]:
        missing = [field for field in
                   ("disposition_or_direction", "clean_scenario",
                    "expected_clean_behavior", "defective_target",
                    "observable_evidence", "deterministic_fixture",
                    "harness_check", "status")
                   if not row.get(field)]
        if missing:
            incomplete.append({"row_id": row.get("row_id"), "missing": missing})

    approval = registry.get("operator_approval", {})
    approved = approval.get("status") == "APPROVED"
    return {
        "leg": "failure_registry",
        "rows": len(registry["rows"]),
        "incomplete_rows": incomplete,
        "operator_approval_status": approval.get("status", "ABSENT"),
        "complete": not incomplete,
        "approved": approved,
        "passed": bool(not incomplete and approved),
        "reason": (None if (not incomplete and approved)
                   else "registry incomplete" if incomplete
                   else "operator approval of the registry and the "
                        "simulation-acceptance proposal has not been recorded"),
    }


def run_gate():
    """Run the complete conjunctive gate and return its verdict."""
    scenarios = runner.load_all()
    anchors = run_anchor_gate()
    specificity = run_specificity(scenarios)
    sensitivity = run_sensitivity(scenarios)
    registry = run_registry_gate()

    legs = {"anchors": anchors, "specificity": specificity,
            "sensitivity": sensitivity, "failure_registry": registry}
    blocking = [name for name, leg in legs.items() if not leg["passed"]]

    verdict = "HARNESS_SELF_QUALIFIED" if not blocking \
        else "HARNESS_NOT_SELF_QUALIFIED"

    return {
        "gate_version": "1.0",
        "verdict": verdict,
        "conjunctive": True,
        "blocking_legs": blocking,
        "real_engine_campaign_permitted": verdict == "HARNESS_SELF_QUALIFIED",
        "legs": {
            "anchors": {k: v for k, v in anchors.items() if k != "findings"},
            "specificity": {k: v for k, v in specificity.items()
                            if k != "findings"},
            "sensitivity": sensitivity,
            "failure_registry": registry,
        },
        "note": ("A conjunctive gate: no aggregate percentage may conceal a "
                 "single required miss. Passing this gate authorizes only the "
                 "real black-box campaign, never a study execution release."),
    }
