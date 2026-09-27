"""Behavioral checks for the Phase 1 profile boundary."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.profiles import PROFILES
from harness.profiles.json_transform import oracle, reference
from harness.profiles.json_transform.profile import ANCHORS


class ProfileTests(unittest.TestCase):
    def test_registry_exposes_distinct_contracts(self):
        self.assertEqual(set(PROFILES), {"ordinal-v1", "json-transform-v1", "graph-path-v1"})
        self.assertTrue(all(callable(p.build) and callable(p.evaluate) for p in PROFILES.values()))

    def test_json_oracle_and_reference_match_hand_answers(self):
        for case in ANCHORS:
            with self.subTest(case=case["id"]):
                self.assertEqual(oracle.transform(case["input"]), case["expected"])
                self.assertEqual(reference.transform(case["input"]), case["expected"])

    def test_json_reference_has_no_oracle_import(self):
        tree = ast.parse((ROOT / "harness/profiles/json_transform/reference.py").read_text())
        imported = [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
        self.assertFalse(any("oracle" in name or "mutants" in name for name in imported))

    def test_json_input_rejects_bool_as_integer(self):
        payload = {"records": [{"id": "a", "value": True}], "minimum": 0}
        for fn in (oracle.transform, reference.transform):
            with self.subTest(fn=fn.__module__), self.assertRaises(ValueError):
                fn(payload)

    def test_cli_json_profile_and_workspace_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "case"
            cmd = [sys.executable, "-m", "harness.cli"]
            run = subprocess.run(cmd + ["demo", "--profile", "json-transform-v1", "--workspace", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads((path / "results/profile-evaluation.json").read_text())
            self.assertTrue(report["technical_checks_passed"])
            self.assertEqual(report["profile"], "json-transform-v1")
            self.assertEqual(len(report["details"]["mutants"]), 5)
            self.assertTrue(all(m["detected"] and m["attributed"] for m in report["details"]["mutants"]))
            wrong = subprocess.run(cmd + ["selfqual", "--profile", "ordinal-v1", "--workspace", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(wrong.returncode, 0)
            self.assertIn("belongs to json-transform-v1", wrong.stderr)
            tampered = json.loads((path / "fixtures/json-transform-v1.json").read_text())
            tampered["cases"][0]["expected"]["total"] = 99
            (path / "fixtures/json-transform-v1.json").write_text(json.dumps(tampered))
            rerun = subprocess.run(cmd + ["selfqual", "--profile", "json-transform-v1", "--workspace", str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(rerun.returncode, 0)
            self.assertIn("differs from registered synthetic cases", rerun.stderr)


if __name__ == "__main__":
    unittest.main()
