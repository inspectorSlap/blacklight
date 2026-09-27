"""Phase 3 durability and boundary tests; no paid or remote target calls."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import campaign
from harness.profiles.json_transform.profile import JsonTransformProfile
from harness.profiles.json_transform import oracle
from harness.target_adapters import Blocked


class FakeAdapter:
    def __init__(self, target_id="fake", fault=None):
        self.target_id = target_id
        self.calls = 0
        self.fault = fault

    def identity(self):
        return {"transport": "test-local", "target_id": self.target_id}

    def request(self, _profile_id, payload):
        self.calls += 1
        if self.fault:
            raise self.fault
        return oracle.transform(payload)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "run"
        self.profile = JsonTransformProfile()
        self.cases = self.profile.target_cases()[:3]

    def start(self, adapter=None, **kwargs):
        adapter = adapter or FakeAdapter()
        return campaign.start(self.workspace, self.profile, adapter, self.cases, 3, "0.3", "0.1", **kwargs)

    def test_plan_batch_resume_no_repetition_and_verdicts(self):
        target = FakeAdapter()
        plan = self.start(target)
        self.assertEqual(plan["verdict"], "INCOMPLETE")
        self.assertEqual(target.calls, 0)
        partial = campaign.resume(self.workspace, self.profile, target, execute=True, step_limit=2)
        self.assertEqual(partial["verdict"], "INCOMPLETE")
        self.assertEqual(partial["completed_cases"], 2)
        done = campaign.resume(self.workspace, self.profile, target, execute=True)
        self.assertEqual(done["verdict"], "PASSED")
        self.assertEqual(done["completed_cases"], 3)
        self.assertEqual(done["estimated_cost"], "0.3")
        self.assertEqual(target.calls, 3)
        self.assertEqual(campaign.resume(self.workspace, self.profile, target, execute=True)["verdict"], "PASSED")
        self.assertEqual(target.calls, 3)
        self.assertEqual(json.loads((self.workspace / "report.json").read_text())["verdict"], "PASSED")

    def test_crash_after_dispatch_is_indeterminate_and_never_reissued(self):
        target = FakeAdapter(fault=RuntimeError("simulated crash after target received call"))
        with self.assertRaisesRegex(RuntimeError, "simulated crash"):
            self.start(target, execute=True)
        target.fault = None
        report = campaign.resume(self.workspace, self.profile, target, execute=True)
        self.assertEqual(report["verdict"], "INDETERMINATE")
        self.assertEqual(report["uncertain_inflight_case"], self.cases[0]["id"])
        self.assertEqual(target.calls, 1)
        self.assertEqual(report["completed_cases"], 0)

    def test_crash_after_completed_commit_rebuilds_report_without_reissue(self):
        target = FakeAdapter()
        with patch.object(campaign, "_publish", side_effect=RuntimeError("report write fault")):
            with self.assertRaisesRegex(RuntimeError, "report write fault"):
                self.start(target, execute=True, step_limit=1)
        self.assertEqual(target.calls, 1)
        report = campaign.resume(self.workspace, self.profile, target, execute=True, step_limit=2)
        self.assertEqual(report["verdict"], "PASSED")
        self.assertEqual(target.calls, 3)

    def test_blocked_target_is_indeterminate(self):
        target = FakeAdapter(fault=Blocked("TARGET_TIMEOUT"))
        report = self.start(target, execute=True)
        self.assertEqual(report["verdict"], "INDETERMINATE")
        self.assertEqual(report["blocked_reason"], "TARGET_TIMEOUT")
        self.assertEqual(target.calls, 1)

    def test_changed_target_profile_and_corrupt_evidence_refuse_resume(self):
        target = FakeAdapter()
        self.start(target, execute=True, step_limit=1)
        with self.assertRaisesRegex(campaign.CampaignError, "target identity"):
            campaign.resume(self.workspace, self.profile, FakeAdapter("other"), execute=True)
        original = (self.workspace / "spec.json").read_bytes()
        (self.workspace / "spec.json").write_bytes(original + b" ")
        with self.assertRaisesRegex(campaign.CampaignError, "freeze digest"):
            campaign.resume(self.workspace, self.profile, target, execute=True)
        (self.workspace / "spec.json").write_bytes(original)
        with patch.object(campaign, "_profile_fingerprint", return_value="changed"):
            with self.assertRaisesRegex(campaign.CampaignError, "profile identity"):
                campaign.resume(self.workspace, self.profile, target, execute=True)
        with sqlite3.connect(self.workspace / "evidence.sqlite3") as db:
            db.execute("UPDATE evidence SET response=? WHERE position=0", (b'{}',))
        with self.assertRaisesRegex(campaign.CampaignError, "response evidence digest"):
            campaign.resume(self.workspace, self.profile, target, execute=True)
        self.assertEqual(target.calls, 1)

    def test_budgets_refuse_before_workspace_or_target_call(self):
        target = FakeAdapter()
        with self.assertRaisesRegex(campaign.CampaignError, "max requests"):
            campaign.start(self.workspace, self.profile, target, self.cases, 2, "99", "0", execute=True)
        self.assertFalse(self.workspace.exists())
        with self.assertRaisesRegex(campaign.CampaignError, "projected cost"):
            campaign.start(self.workspace, self.profile, target, self.cases, 3, "0.29", "0.1", execute=True)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(target.calls, 0)

    def test_abort_is_distinct_and_terminal(self):
        target = FakeAdapter()
        self.start(target)
        report = campaign.resume(self.workspace, self.profile, None, abort=True)
        self.assertEqual(report["verdict"], "ABORTED")
        self.assertEqual(campaign.resume(self.workspace, self.profile, target, execute=True)["verdict"], "ABORTED")
        self.assertEqual(target.calls, 0)

    def test_failed_checks_are_not_a_pass(self):
        class Wrong(FakeAdapter):
            def request(self, _profile_id, _payload):
                self.calls += 1
                return {"ids": [], "total": 0, "count": 0}
        target = Wrong()
        report = self.start(target, execute=True)
        self.assertEqual(report["verdict"], "FAILED")
        self.assertGreater(report["failed_cases"], 0)


if __name__ == "__main__":
    unittest.main()
