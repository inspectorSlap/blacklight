"""Phase 4 handoff, freeze and report-only release tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from role_workflow import WorkflowError, prepare, freeze, verify, evaluate, publish
from run_reviewer import command


class RoleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "implementer"
        self.private.mkdir()
        self.reviewer = self.root / "reviewer"
        self.reviewer.mkdir()
        self.contract = self.private / "contract.json"
        self.contract.write_bytes((ROOT / "templates/implementer/contract.example.json").read_bytes())
        (self.private / "target_source.py").write_text("PRIVATE_SOURCE_CANARY")
        self.bundle = self.root / "handoff"
        self.expectations = self.reviewer / "expectations.json"
        self.expectations.write_bytes((ROOT / "templates/reviewer/expectations.example.json").read_bytes())
        self.lineage = self.reviewer / "lineage.json"
        self.lineage.write_bytes((ROOT / "templates/reviewer/lineage.example.json").read_bytes())
        self.frozen = self.reviewer / "freeze.json"

    def test_narrow_handoff_freeze_evaluate_resume_and_report_bundle(self):
        prepare(self.contract, self.bundle)
        self.assertEqual({p.name for p in self.bundle.iterdir()}, {"contract.json", "manifest.json"})
        self.assertNotIn("PRIVATE_SOURCE_CANARY", "".join(p.read_text() for p in self.bundle.iterdir()))
        freeze(self.bundle, self.expectations, self.lineage, self.frozen)
        _, expected, _, digest = verify(self.bundle, self.expectations, self.lineage, self.frozen)
        self.assertEqual(len(expected["cases"]), 1)
        self.assertEqual(len(digest), 64)
        workspace = self.root / "campaign"
        program = ROOT / "examples/json_transform_process.py"
        plan = evaluate(self.bundle, self.expectations, self.lineage, self.frozen, workspace, program, None,
                        1, "0", "0", 10.0, False, None, False)
        self.assertEqual(plan["verdict"], "INCOMPLETE")
        result = evaluate(self.bundle, self.expectations, self.lineage, self.frozen, workspace, program, None,
                          None, None, None, 10.0, True, None, True)
        self.assertEqual(result["verdict"], "PASSED")
        self.assertEqual(json.loads((workspace / "spec.json").read_text())["methodology_freeze_sha256"], digest)
        out = self.root / "result-bundle"
        published = publish(self.bundle, self.expectations, self.lineage, self.frozen, workspace, out)
        self.assertEqual(published["verdict"], "PASSED")
        self.assertEqual({p.name for p in out.iterdir()}, {"report.json", "manifest.json"})
        self.assertNotIn("records", "".join(p.read_text() for p in out.iterdir()))
        self.assertNotIn("PRIVATE_SOURCE_CANARY", "".join(p.read_text() for p in out.iterdir()))

    def test_evaluation_refuses_missing_freeze_before_target_work(self):
        prepare(self.contract, self.bundle)
        workspace = self.root / "campaign"
        with self.assertRaises(WorkflowError):
            evaluate(self.bundle, self.expectations, self.lineage, self.frozen, workspace,
                     ROOT / "examples/json_transform_process.py", None,
                     1, "0", "0", 3.0, True, None, False)
        self.assertFalse(workspace.exists())

    def test_contract_allowlist_and_handoff_integrity(self):
        contract = json.loads(self.contract.read_text())
        contract["private_results"] = "should never be bundled"
        self.contract.write_text(json.dumps(contract))
        with self.assertRaisesRegex(WorkflowError, "exactly"):
            prepare(self.contract, self.bundle)
        contract.pop("private_results")
        self.contract.write_text(json.dumps(contract))
        prepare(self.contract, self.bundle)
        (self.bundle / "extra.py").write_text("unexpected")
        with self.assertRaisesRegex(WorkflowError, "unexpected files"):
            freeze(self.bundle, self.expectations, self.lineage, self.frozen)
        (self.bundle / "extra.py").unlink()
        (self.bundle / "contract.json").write_text(self.contract.read_text() + " ")
        with self.assertRaisesRegex(WorkflowError, "digest changed"):
            freeze(self.bundle, self.expectations, self.lineage, self.frozen)

    def test_changed_expectations_or_lineage_invalidate_freeze(self):
        prepare(self.contract, self.bundle)
        freeze(self.bundle, self.expectations, self.lineage, self.frozen)
        self.expectations.write_text(self.expectations.read_text() + " ")
        with self.assertRaisesRegex(WorkflowError, "freeze binding changed"):
            verify(self.bundle, self.expectations, self.lineage, self.frozen)
        self.expectations.write_bytes((ROOT / "templates/reviewer/expectations.example.json").read_bytes())
        self.lineage.write_text(self.lineage.read_text() + " ")
        with self.assertRaisesRegex(WorkflowError, "freeze binding changed"):
            verify(self.bundle, self.expectations, self.lineage, self.frozen)

    def test_containment_command_mounts_only_handoff_and_reviewer(self):
        prepare(self.contract, self.bundle)
        invocation = command(self.bundle, self.reviewer, "debian:bookworm-slim", ["/bin/sh", "-c", "true"])
        joined = " ".join(invocation)
        self.assertIn("--network=none", invocation)
        self.assertIn("--read-only", invocation)
        self.assertIn("--cap-drop=ALL", invocation)
        self.assertIn("--security-opt=no-new-privileges", invocation)
        self.assertIn("dst=/handoff,readonly", joined)
        self.assertIn("dst=/reviewer", joined)
        self.assertNotIn(str(self.private), joined)
        self.assertNotIn("/var/run/docker.sock", joined)


if __name__ == "__main__":
    unittest.main()
