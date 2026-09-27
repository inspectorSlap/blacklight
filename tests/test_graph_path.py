"""Exact and cross-case graph checks, with only synthetic/toy targets."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from harness import campaign, target_probe
from harness.profiles.graph_path import mutants, oracle, reference
from harness.profiles.graph_path.profile import GraphPathProfile, HAND_BASES
from role_workflow import prepare, freeze, evaluate, publish


class FakeAdapter:
    def __init__(self, solve):
        self.solve = solve
        self.calls = 0

    def identity(self):
        return {"transport": "test-local", "target_id": "synthetic"}

    def request(self, _profile, payload):
        self.calls += 1
        return self.solve(payload)


class GraphPathTests(unittest.TestCase):
    def setUp(self):
        self.profile = GraphPathProfile()

    def test_hand_anchors_and_independent_reference(self):
        for base in HAND_BASES:
            with self.subTest(base=base["id"]):
                expected = {"distance": base["distance"]}
                self.assertEqual(oracle.solve(base["input"]), expected)
                self.assertEqual(reference.solve(base["input"]), expected)
        tree = ast.parse((ROOT / "harness/profiles/graph_path/reference.py").read_text())
        imported = [alias.name for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
        self.assertFalse(any("oracle" in name or "mutants" in name for name in imported))

    def test_local_qualification_and_named_mutants(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "fixtures").mkdir()
            built = self.profile.build(workspace)
            result = self.profile.evaluate(workspace)
        self.assertTrue(result.technical_checks_passed, result.details)
        self.assertEqual(built["hand_checked_bases"], 3)
        self.assertEqual(built["target_cases"], 12)
        self.assertEqual(len(result.details["mutants"]), 6)
        self.assertTrue(all(row["detected"] and row["attributed"] for row in result.details["mutants"]))
        self.assertIn("not tested on a live engine", result.details["scope"])

    def test_relation_fails_even_when_derived_case_schema_passes(self):
        cases = self.profile.target_cases()[:4]
        target = FakeAdapter(mutants.one_pass)
        report = target_probe.run(self.profile, target, cases)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["counts"]["FAIL"], 0)
        self.assertEqual(report["relations_status"], "EVALUATED")
        self.assertTrue(any(item["relation"] == "edge-order" for item in report["relation_failures"]))
        self.assertEqual(target.calls, 4)

    def test_relation_failure_is_rebuilt_from_durable_evidence(self):
        cases = self.profile.target_cases()[:4]
        target = FakeAdapter(mutants.one_pass)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "campaign"
            partial = campaign.start(workspace, self.profile, target, cases, 4, "0", "0",
                                     execute=True, step_limit=2)
            self.assertEqual(partial["verdict"], "INCOMPLETE")
            self.assertEqual(partial["relations_status"], "PENDING")
            done = campaign.resume(workspace, self.profile, target, execute=True)
            self.assertEqual(done["verdict"], "FAILED")
            self.assertEqual(done["failed_cases"], 0)
            self.assertGreater(done["failed_relations"], 0)
            self.assertEqual(target.calls, 4)
            rebuilt = campaign.resume(workspace, self.profile, target, execute=False)
            self.assertEqual(rebuilt["relation_failures"], done["relation_failures"])
            self.assertEqual(target.calls, 4)

    def test_custom_bases_expand_and_invalid_inputs_refuse(self):
        cases = self.profile.target_cases([HAND_BASES[0]["input"]])
        self.assertEqual(len(cases), 4)
        self.assertEqual({c["expected"]["mode"] for c in cases}, {"exact", "relation"})
        invalid = json.loads(json.dumps(HAND_BASES[0]["input"]))
        invalid["edges"][0]["weight"] = True
        with self.assertRaises(ValueError):
            self.profile.target_cases([invalid])
        invalid = json.loads(json.dumps(HAND_BASES[0]["input"]))
        invalid["edges"][0]["to"] = "missing"
        with self.assertRaises(ValueError):
            self.profile.target_cases([invalid])

    def test_malformed_reviewer_relation_refuses_before_dispatch(self):
        cases = self.profile.target_cases()[:4]
        for change in ("wrong-exact", "wrong-transform"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                altered = json.loads(json.dumps(cases))
                if change == "wrong-exact":
                    altered[0]["expected"]["distance"] = 99
                else:
                    altered[1]["input"]["edges"][0]["weight"] += 1
                target = FakeAdapter(reference.solve)
                workspace = Path(directory) / "campaign"
                with self.assertRaises(ValueError):
                    campaign.start(workspace, self.profile, target, altered, 4, "0", "0", execute=True)
                self.assertFalse(workspace.exists())
                self.assertEqual(target.calls, 0)

    def test_toy_executable_and_cli_campaign(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "campaign"
            command = [sys.executable, "-m", "harness.cli", "campaign", "--profile", "graph-path-v1",
                       "--program", str(ROOT / "examples/graph_path_process.py"), "--target-id", "toy-graph-v1",
                       "--cases", str(ROOT / "examples/graph_path_custom.json"), "--workspace", str(workspace)]
            first = subprocess.run(command + ["--max-requests", "4", "--max-cost", "0", "--unit-cost", "0",
                                              "--execute", "--step-limit", "2"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 2, first.stderr)
            self.assertEqual(json.loads((workspace / "report.json").read_text())["relations_status"], "PENDING")
            second = subprocess.run(command[:-4] + ["--workspace", str(workspace), "--resume", "--execute"],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            report = json.loads((workspace / "report.json").read_text())
            self.assertEqual(report["verdict"], "PASSED")
            self.assertEqual(report["relations_status"], "EVALUATED")
            self.assertEqual(report["completed_cases"], 4)

    def test_role_handoff_accepts_relational_expectations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.json"
            contract.write_text(json.dumps({"schema_version": 1, "profile": "graph-path-v1", "target_id": "toy-graph-v1",
                                            "requirements": ["Return the shortest directed nonnegative path distance or null."],
                                            "request_schema": {"input": "directed graph"},
                                            "response_schema": {"output": {"distance": "integer or null"}}}))
            bundle = root / "handoff"
            prepare(contract, bundle)
            expectations = root / "expectations.json"
            expectations.write_text(json.dumps({"profile": "graph-path-v1", "cases": self.profile.target_cases()[:4],
                                                "limitations": ["Synthetic graph only; no live engine test."]}))
            lineage = root / "lineage.json"
            lineage.write_text(json.dumps({"implementer": "toy script", "reviewer": "test fixture",
                                           "shared_lineage": "unknown", "notes": "Synthetic workflow demonstration."}))
            frozen = root / "freeze.json"
            freeze(bundle, expectations, lineage, frozen)
            workspace = root / "run"
            report = evaluate(bundle, expectations, lineage, frozen, workspace,
                              ROOT / "examples/graph_path_process.py", None, 4, "0", "0", 10, True, None, False)
            self.assertEqual(report["verdict"], "PASSED")
            result = publish(bundle, expectations, lineage, frozen, workspace, root / "result")
            self.assertEqual(result["verdict"], "PASSED")


if __name__ == "__main__":
    unittest.main()
