"""Small directed-graph profile combining exact anchors and cross-run relations."""
from copy import deepcopy
import json
from pathlib import Path

from ..base import Evaluation
from . import mutants, oracle, reference
from .schema import validate


# These distances are hand-worked and do not come from either implementation.
HAND_BASES = (
    {"id": "weighted", "input": {"vertices": ["s", "a", "t"],
         "edges": [{"from": "s", "to": "a", "weight": 2},
                   {"from": "a", "to": "t", "weight": 3},
                   {"from": "s", "to": "t", "weight": 10}],
         "source": "s", "target": "t"}, "distance": 5},
    {"id": "directed-unreachable", "input": {"vertices": ["u", "v"],
         "edges": [{"from": "v", "to": "u", "weight": 4},
                   {"from": "v", "to": "v", "weight": 1}],
         "source": "u", "target": "v"}, "distance": None},
    {"id": "zero-weight", "input": {"vertices": ["s", "a", "t"],
         "edges": [{"from": "s", "to": "t", "weight": 0},
                   {"from": "s", "to": "a", "weight": 5},
                   {"from": "a", "to": "t", "weight": 0}],
         "source": "s", "target": "t"}, "distance": 0},
)


def _distance(output):
    if type(output) is not dict or set(output) != {"distance"}:
        return False, None
    value = output["distance"]
    if value is not None and (type(value) is not int or value < 0):
        return False, None
    return True, value


def output_findings(observed, expected):
    valid, value = _distance(observed)
    if not valid:
        return ["schema"]
    if expected["mode"] == "relation":
        return []  # cross-case comparison happens after both responses exist
    if expected["mode"] != "exact":
        raise ValueError("unknown expectation mode")
    wanted = expected["distance"]
    if value == wanted:
        return []
    return ["reachability" if (value is None) != (wanted is None) else "distance"]


def relation_findings(cases, observations):
    findings = []
    for case in cases:
        rule = case["expected"]
        if rule["mode"] != "relation":
            continue
        source_id = rule["source"]
        derived_id = case["id"]
        source_valid, source_value = _distance(observations[source_id])
        derived_valid, derived_value = _distance(observations[derived_id])
        if not source_valid or not derived_valid:
            reason = "invalid-output"
        else:
            wanted = source_value * rule["factor"] if source_value is not None and rule["relation"] == "positive-scaling" else source_value
            reason = "changed" if derived_value != wanted else None
        if reason:
            findings.append({"relation": rule["relation"], "source": source_id,
                             "derived": derived_id, "reason": reason})
    return findings


def _transformed(graph, relation):
    changed = deepcopy(graph)
    if relation == "edge-order":
        changed["edges"].reverse()
    elif relation == "isolated-vertex":
        i = 1
        while "isolated%d" % i in changed["vertices"]:
            i += 1
        changed["vertices"].append("isolated%d" % i)
    elif relation == "positive-scaling":
        for edge in changed["edges"]:
            edge["weight"] *= 2
    else:
        raise ValueError("unknown graph relation")
    return changed


def _expanded(base_id, graph, exact_distance):
    validate(graph)
    if len(graph["vertices"]) > 11 or len(graph["edges"]) < 2 \
            or any(edge["weight"] > 50 for edge in graph["edges"]):
        raise ValueError("metamorphic base needs 2+ edges, at most 11 vertices and weights at most 50")
    cases = [{"id": base_id + "-base", "input": deepcopy(graph),
              "expected": {"mode": "exact", "distance": exact_distance}}]
    for name, factor in (("edge-order", 1), ("isolated-vertex", 1), ("positive-scaling", 2)):
        cases.append({"id": base_id + "-" + name, "input": _transformed(graph, name),
                      "expected": {"mode": "relation", "source": base_id + "-base",
                                   "relation": name, "factor": factor}})
    return cases


class GraphPathProfile:
    profile_id = "graph-path-v1"
    description = "Directed nonnegative shortest paths with exact anchors and cross-run relations"

    def target_cases(self, custom_inputs=None):
        if custom_inputs is None:
            return [case for base in HAND_BASES for case in _expanded(base["id"], base["input"], base["distance"])]
        if type(custom_inputs) is not list or not 1 <= len(custom_inputs) <= 8:
            raise ValueError("custom graph bases must be a list of 1–8 objects")
        cases = []
        for i, graph in enumerate(custom_inputs, 1):
            validate(graph)
            cases.extend(_expanded("custom-%03d" % i, graph, oracle.solve(graph)["distance"]))
        return cases

    def validate_target_cases(self, cases):
        if type(cases) is not list or not 4 <= len(cases) <= 32 or len(cases) % 4:
            raise ValueError("graph target cases must be complete groups of four")
        by_id = {}
        exact = {}
        for case in cases:
            if type(case) is not dict or set(case) != {"id", "input", "expected"} \
                    or type(case["id"]) is not str or not case["id"] or case["id"] in by_id:
                raise ValueError("graph case IDs must be unique and cases must have exact fields")
            validate(case["input"])
            if type(case["expected"]) is not dict:
                raise ValueError("graph expectation must be an object")
            by_id[case["id"]] = case
            expected = case["expected"]
            if expected.get("mode") == "exact":
                if set(expected) != {"mode", "distance"} or (expected["distance"] is not None and
                        (type(expected["distance"]) is not int or expected["distance"] < 0)):
                    raise ValueError("exact graph expectation is invalid")
                if len(case["input"]["vertices"]) > 11 or len(case["input"]["edges"]) < 2 \
                        or any(edge["weight"] > 50 for edge in case["input"]["edges"]):
                    raise ValueError("graph base is outside metamorphic bounds")
                if oracle.solve(case["input"])["distance"] != expected["distance"]:
                    raise ValueError("exact graph expectation disagrees with independent oracle")
                exact[case["id"]] = case
            elif expected.get("mode") != "relation":
                raise ValueError("unknown graph expectation mode")
        seen = set()
        for case in cases:
            expected = case["expected"]
            if expected["mode"] != "relation":
                continue
            if set(expected) != {"mode", "source", "relation", "factor"} or \
                    type(expected["source"]) is not str or expected["source"] not in exact \
                    or expected["relation"] not in ("edge-order", "isolated-vertex", "positive-scaling"):
                raise ValueError("graph relation metadata is invalid")
            relation = expected["relation"]
            factor = 2 if relation == "positive-scaling" else 1
            if type(expected["factor"]) is not int or expected["factor"] != factor \
                    or case["input"] != _transformed(exact[expected["source"]]["input"], relation):
                raise ValueError("derived graph does not match its declared relation")
            pair = (expected["source"], relation)
            if pair in seen:
                raise ValueError("duplicate graph relation")
            seen.add(pair)
        if len(exact) * 4 != len(cases) or len(seen) != len(exact) * 3:
            raise ValueError("every graph base needs all three derived relations")

    def check_target_output(self, observed, expected):
        return output_findings(observed, expected)

    def check_target_relations(self, cases, observations):
        return relation_findings(cases, observations)

    def build(self, workspace: Path):
        cases = self.target_cases()
        self.validate_target_cases(cases)
        path = workspace / "fixtures/graph-path-v1.json"
        path.write_text(json.dumps({"profile": self.profile_id, "bases": HAND_BASES,
                                    "cases": cases}, indent=2) + "\n")
        return {"synthetic_scenario_files": 1, "hand_checked_bases": len(HAND_BASES),
                "target_cases": len(cases), "registered_mutants": len(mutants.REGISTRY)}

    def evaluate(self, workspace: Path):
        data = json.loads((workspace / "fixtures/graph-path-v1.json").read_text())
        cases = self.target_cases()
        if data != {"profile": self.profile_id, "bases": list(HAND_BASES), "cases": cases}:
            raise ValueError("fixture differs from registered synthetic graph cases")
        anchor_failures = []
        for base in HAND_BASES:
            expected = {"distance": base["distance"]}
            if oracle.solve(base["input"]) != expected or reference.solve(base["input"]) != expected:
                anchor_failures.append(base["id"])
        clean_observed = {case["id"]: reference.solve(case["input"]) for case in cases}
        clean_case_failures = [{"case": case["id"], "checks": self.check_target_output(clean_observed[case["id"]], case["expected"])}
                               for case in cases if self.check_target_output(clean_observed[case["id"]], case["expected"])]
        clean_relation_failures = self.check_target_relations(cases, clean_observed)
        oracle_relation_failures = self.check_target_relations(
            cases, {case["id"]: oracle.solve(case["input"]) for case in cases})
        sensitivity = []
        for name, owner, target in mutants.REGISTRY:
            observed = {case["id"]: target(case["input"]) for case in cases}
            case_checks = [{"case": case["id"], "checks": self.check_target_output(observed[case["id"]], case["expected"])}
                           for case in cases if self.check_target_output(observed[case["id"]], case["expected"])]
            relation_checks = self.check_target_relations(cases, observed)
            names = {check for row in case_checks for check in row["checks"]} | {row["relation"] for row in relation_checks}
            sensitivity.append({"mutant": name, "expected_check": owner, "detected": bool(names),
                                "attributed": owner in names, "case_failures": case_checks,
                                "relation_failures": relation_checks})
        technical = (not anchor_failures and not clean_case_failures and not clean_relation_failures
                     and not oracle_relation_failures and all(row["detected"] and row["attributed"] for row in sensitivity))
        return Evaluation(technical, "LOCAL_PROFILE_CHECKS_PASSED" if technical else "LOCAL_PROFILE_CHECKS_FAILED", technical,
                          {"hand_checked_bases": len(HAND_BASES), "cases": len(cases),
                           "anchor_failures": anchor_failures, "clean_case_failures": clean_case_failures,
                           "clean_relation_failures": clean_relation_failures,
                           "oracle_relation_failures": oracle_relation_failures,
                           "mutants": sensitivity,
                           "scope": "synthetic profile and bundled toy target only; not tested on a live engine"})
