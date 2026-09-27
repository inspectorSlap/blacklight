"""A second profile proving the extension boundary with exact JSON criteria."""
import json
from pathlib import Path

from ..base import Evaluation
from . import mutants, oracle, reference


# Hand-checked answers are independent of both implementations.
ANCHORS = (
    {"id": "inclusive-boundary", "input": {"records": [{"id": "a", "value": 2}, {"id": "b", "value": 3}, {"id": "c", "value": 1}], "minimum": 2}, "expected": {"ids": ["a", "b"], "total": 5, "count": 2}},
    {"id": "stable-order", "input": {"records": [{"id": "z", "value": 4}, {"id": "a", "value": 3}], "minimum": 2}, "expected": {"ids": ["z", "a"], "total": 7, "count": 2}},
    {"id": "empty-selection", "input": {"records": [{"id": "x", "value": -2}, {"id": "y", "value": 0}], "minimum": 1}, "expected": {"ids": [], "total": 0, "count": 0}},
    {"id": "duplicate-ids-preserved", "input": {"records": [{"id": "q", "value": 1}, {"id": "q", "value": 2}], "minimum": 1}, "expected": {"ids": ["q", "q"], "total": 3, "count": 2}},
    {"id": "negative-boundary", "input": {"records": [{"id": "n", "value": -1}, {"id": "m", "value": -2}], "minimum": -1}, "expected": {"ids": ["n"], "total": -1, "count": 1}},
)


def findings(observed, expected):
    if type(observed) is not dict or set(observed) != {"ids", "total", "count"}:
        return ["schema"]
    problems = []
    actual_ids, desired_ids = observed["ids"], expected["ids"]
    if type(actual_ids) is not list or any(type(v) is not str for v in actual_ids):
        problems.append("schema")
    elif actual_ids != desired_ids:
        if sorted(actual_ids) == sorted(desired_ids):
            problems.append("order")
        else:
            problems.append("selection")
    if type(observed["total"]) is not int or observed["total"] != expected["total"]:
        problems.append("total")
    if type(observed["count"]) is not int or observed["count"] != expected["count"]:
        problems.append("count")
    return problems


class JsonTransformProfile:
    profile_id = "json-transform-v1"
    description = "Select integer records at an inclusive boundary; preserve order and report total/count"

    def build(self, workspace: Path):
        path = workspace / "fixtures/json-transform-v1.json"
        path.write_text(json.dumps({"profile": self.profile_id, "cases": ANCHORS}, indent=2) + "\n")
        return {"synthetic_scenario_files": 1, "hand_checked_cases": len(ANCHORS), "registered_mutants": len(mutants.REGISTRY)}

    def evaluate(self, workspace: Path):
        path = workspace / "fixtures/json-transform-v1.json"
        data = json.loads(path.read_text())
        if data.get("profile") != self.profile_id or not isinstance(data.get("cases"), list) or not data["cases"]:
            raise ValueError("fixture profile or cases missing")
        cases = data["cases"]
        if cases != list(ANCHORS):
            raise ValueError("fixture differs from registered synthetic cases")
        anchors = []
        clean = []
        for case in cases:
            oracle_problems = findings(oracle.transform(case["input"]), case["expected"])
            reference_problems = findings(reference.transform(case["input"]), case["expected"])
            anchors.append({"case": case["id"], "checks": oracle_problems})
            clean.append({"case": case["id"], "checks": reference_problems})
        sensitivity = []
        for name, owner, target in mutants.REGISTRY:
            caught = []
            for case in cases:
                check_names = findings(target(case["input"]), case["expected"])
                if check_names:
                    caught.append({"case": case["id"], "checks": check_names})
            sensitivity.append({"mutant": name, "expected_check": owner, "detected": bool(caught),
                                "attributed": any(owner in row["checks"] for row in caught), "evidence": caught})
        technical = (all(not r["checks"] for r in anchors + clean)
                     and all(r["detected"] and r["attributed"] for r in sensitivity))
        return Evaluation(technical, "LOCAL_PROFILE_CHECKS_PASSED" if technical else "LOCAL_PROFILE_CHECKS_FAILED", technical,
                          {"anchor_cases": len(anchors), "oracle_failures": [r for r in anchors if r["checks"]],
                           "clean_cases": len(clean), "reference_failures": [r for r in clean if r["checks"]],
                           "mutants": sensitivity, "scope": "synthetic local profile only"})

    def target_cases(self, custom_inputs=None):
        if custom_inputs is None:
            return list(ANCHORS)
        if type(custom_inputs) is not list or not 1 <= len(custom_inputs) <= 32:
            raise ValueError("custom cases must be a list of 1–32 input objects")
        return [{"id": "custom-%03d" % (i + 1), "input": payload,
                 "expected": oracle.transform(payload)}
                for i, payload in enumerate(custom_inputs)]

    def check_target_output(self, observed, expected):
        return findings(observed, expected)
