"""Panel execution.

The same code path runs the sound reference, every registered mutant, and (once
the phase gate opens) the real black-box endpoint. Nothing in this module knows
which kind of target it is holding.
"""

import copy
import glob
import json
import os

from . import adapter
from .checks import anchor_checks, archive_checks, checks
from .targets import Rejection

from .workspace import ROOT
SCENARIO_ROOT = os.path.join(ROOT, "fixtures", "scenarios")


def load_family(family):
    paths = sorted(glob.glob(os.path.join(SCENARIO_ROOT, family, "*.json")))
    scenarios = []
    for path in paths:
        with open(path, "r") as handle:
            scenarios.append(json.load(handle))
    return scenarios


def load_all():
    return {family: load_family(family)
            for family in ("clean", "anchors", "archive")}


# ---------------------------------------------------------------------------
# Analysis panel
# ---------------------------------------------------------------------------

def run_analysis_scenario(target, scenario, strict, deep=True):
    """Run every analysis check against one scenario."""
    findings = []
    scenario_id = scenario["scenario_id"]
    try:
        raw = target.analyze(copy.deepcopy(scenario["payload"]))
    except Rejection as exc:
        return [checks.finding(
            "schema_conformance", scenario_id, "FAIL",
            "target rejected a well-formed clean-panel payload with %s: %s"
            % (exc.code, exc.message),
            {"error": exc.body})]
    except Exception as exc:
        return [checks.finding("schema_conformance", scenario_id, "BLOCKED",
                               "target raised %s: %s"
                               % (type(exc).__name__, exc))]

    try:
        normalized = adapter.normalize(raw)
    except adapter.UndocumentedSchema as exc:
        return [checks.finding(
            "schema_conformance", scenario_id, "BLOCKED",
            "the response could not be mapped into the harness normal form "
            "using the frozen adapter table: %s. The harness fails closed on "
            "an undocumented schema rather than guessing (contract section 3)."
            % exc, {"path": exc.path, "detail": exc.detail})]

    findings += checks.check_point_estimates(scenario, normalized)
    findings += checks.check_interval_validity(scenario, normalized)
    findings += checks.check_decision_consistency(scenario, normalized)
    findings += checks.check_cross_light(scenario, normalized)
    if scenario["family"] != "anchors":
        findings += checks.check_expected_dispositions(scenario, normalized, strict)
    if deep:
        findings += checks.check_invariance(target, scenario)
        findings += checks.check_alpha_nesting(target, scenario)
        findings += checks.check_interval_scaling(target, scenario)
    return findings


def run_analysis_panel(target, scenarios, strict, deep_scenarios=None):
    """Run the analysis panel. `deep_scenarios` limits the multi-call checks."""
    findings = []
    deep_set = set(deep_scenarios) if deep_scenarios is not None else None
    for scenario in scenarios:
        deep = deep_set is None or scenario["scenario_id"] in deep_set
        findings += run_analysis_scenario(target, scenario, strict, deep=deep)

    pair = {s["scenario_id"]: s for s in scenarios}
    left = pair.get("CL-12-C4-NONINTERFERENCE-A")
    right = pair.get("CL-12-C4-NONINTERFERENCE-B")
    if left and right:
        findings += checks.check_c4_noninterference(target, left, right)
    return findings


# ---------------------------------------------------------------------------
# Archive panel
# ---------------------------------------------------------------------------

def run_archive_scenario(target, scenario):
    try:
        result = target.aggregate(copy.deepcopy(scenario["payload"]))
        outcome = {"rejected": False, "result": result}
    except Rejection as exc:
        outcome = {"rejected": True, "result": None, "error": exc.body}
    except Exception as exc:
        return [checks.finding("archive_invariants", scenario["scenario_id"],
                               "BLOCKED", "target raised %s: %s"
                               % (type(exc).__name__, exc))], None
    return archive_checks.run_archive_invariants(scenario, outcome, target), outcome


def run_archive_panel(target, scenarios):
    findings = []
    for scenario in scenarios:
        scenario_findings, _outcome = run_archive_scenario(target, scenario)
        findings += scenario_findings
    return findings


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

def run_anchor_panel(target, scenarios):
    findings = []
    for scenario in scenarios:
        if scenario["family"] != "anchors":
            continue
        findings += anchor_checks.verify_target(target, scenario)
    return findings


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def summarize(findings):
    counts = {"FAIL": 0, "OBSERVATION": 0, "BLOCKED": 0}
    by_check = {}
    for entry in findings:
        counts[entry["severity"]] = counts.get(entry["severity"], 0) + 1
        bucket = by_check.setdefault(entry["check"], {"FAIL": 0, "OBSERVATION": 0,
                                                      "BLOCKED": 0})
        bucket[entry["severity"]] = bucket.get(entry["severity"], 0) + 1
    return {"totals": counts, "by_check": by_check,
            "failing_checks": sorted({e["check"] for e in findings
                                      if e["severity"] == "FAIL"})}
