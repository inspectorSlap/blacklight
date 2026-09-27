"""Phase 2 target-boundary tests; live HTTP is also checked in validation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.profiles.json_transform.profile import JsonTransformProfile
from harness.target_adapters import Blocked, LoopbackHttpAdapter, ProcessAdapter, MAX_OUTPUT_BYTES
from harness.target_probe import run

CASE = JsonTransformProfile().target_cases()[0]


def executable(folder, body):
    path = Path(folder) / "target.py"
    path.write_text("#!" + sys.executable + "\n" + body)
    path.chmod(0o755)
    return path


class TargetProbeTests(unittest.TestCase):
    def test_process_pass_and_no_inherited_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            program = executable(directory, '''import json, os, sys
request = json.load(sys.stdin)
rows = [r for r in request["input"]["records"] if r["value"] >= request["input"]["minimum"]]
value = {"ids": [r["id"] for r in rows], "total": sum(r["value"] for r in rows), "count": len(rows)}
if "BLACKBOX_TEST_SECRET" in os.environ: value["secret"] = os.environ["BLACKBOX_TEST_SECRET"]
json.dump({"target_id": "demo", "output": value}, sys.stdout)
''')
            with patch.dict(os.environ, {"BLACKBOX_TEST_SECRET": "never-print-this"}):
                adapter = ProcessAdapter(program, "demo", directory)
                report = run(JsonTransformProfile(), adapter, [CASE])
            self.assertEqual(report["verdict"], "PASS")
            self.assertNotIn("never-print-this", json.dumps(report))
            self.assertEqual(len(report["target"]["program_sha256"]), 64)
            self.assertNotIn(str(program), json.dumps(report))

    def test_process_faults_block_without_echoing_stderr(self):
        faults = [
            ('''import sys; sys.stderr.write("sensitive-error-body"); sys.exit(4)''', "TARGET_EXITED", 0.5),
            ('''print("not json")''', "INVALID_JSON", 0.5),
            ('''import time; time.sleep(2)''', "TARGET_TIMEOUT", 0.1),
            ('''import sys; sys.stdout.write("x" * 70000)''', "OUTPUT_TOO_LARGE", 0.5),
            ('''print('{"target_id":"other","output":{}}')''', "IDENTITY_MISMATCH", 0.5),
        ]
        for body, expected, timeout in faults:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                program = executable(directory, body)
                adapter = ProcessAdapter(program, "demo", directory, timeout=timeout)
                report = run(JsonTransformProfile(), adapter, [CASE])
                self.assertEqual(report["verdict"], "BLOCKED")
                self.assertEqual(report["rows"][0]["reason"], expected)
                self.assertNotIn("sensitive-error-body", json.dumps(report))

    def test_program_change_blocks_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            program = executable(directory, 'print("before")')
            adapter = ProcessAdapter(program, "demo", directory)
            program.write_text("#!" + sys.executable + "\n" + 'print("after")')
            with self.assertRaises(Blocked) as caught:
                adapter.request("json-transform-v1", CASE["input"])
            self.assertEqual(caught.exception.code, "IDENTITY_CHANGED")

    def test_http_url_must_be_literal_loopback(self):
        for url in ("https://127.0.0.1:80/", "http://example.com:80/", "http://10.0.0.1:80/",
                    "http://127.0.0.1:80/?token=x", "http://user:pass@127.0.0.1:80/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LoopbackHttpAdapter(url, "demo")

    def test_http_identity_and_unavailability_block(self):
        class Response:
            status = 200
            def read(self, _size):
                return b'{"target_id":"changed","output":{}}'
        class Connection:
            def __init__(self, *_args, **_kwargs): pass
            def request(self, *_args, **_kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        adapter = LoopbackHttpAdapter("http://127.0.0.1:8777/transform", "demo")
        with patch("harness.target_adapters.http.client.HTTPConnection", Connection):
            report = run(JsonTransformProfile(), adapter, [CASE])
        self.assertEqual(report["rows"][0]["reason"], "IDENTITY_MISMATCH")
        class Down(Connection):
            def request(self, *_args, **_kwargs): raise ConnectionRefusedError("secret diagnostic")
        with patch("harness.target_adapters.http.client.HTTPConnection", Down):
            report = run(JsonTransformProfile(), adapter, [CASE])
        self.assertEqual(report["rows"][0]["reason"], "TARGET_UNAVAILABLE")
        self.assertNotIn("secret diagnostic", json.dumps(report))

    def test_wrong_target_output_is_fail_not_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            program = executable(directory, '''import json, sys
json.load(sys.stdin)
json.dump({"target_id": "demo", "output": {"ids": [], "total": 0, "count": 0}}, sys.stdout)
''')
            report = run(JsonTransformProfile(), ProcessAdapter(program, "demo", directory), [CASE])
            self.assertEqual(report["verdict"], "FAIL")
            self.assertIn("selection", report["rows"][0]["checks"])

    def test_cli_probe_process_custom_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            program = executable(root, '''import json, sys
r = json.load(sys.stdin)["input"]
s = [item for item in r["records"] if item["value"] >= r["minimum"]]
json.dump({"target_id":"demo","output":{"ids":[item["id"] for item in s],"total":sum(item["value"] for item in s),"count":len(s)}},sys.stdout)
''')
            inputs = root / "cases.json"
            inputs.write_text(json.dumps([CASE["input"]]))
            workspace = root / "probe"
            cmd = [sys.executable, "-m", "harness.cli", "probe", "--profile", "json-transform-v1",
                   "--program", str(program), "--target-id", "demo", "--cases", str(inputs),
                   "--workspace", str(workspace)]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((workspace / "results/target-probe.json").read_text())
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(report["rows"][0]["case"], "custom-001")
            self.assertNotIn(str(program), json.dumps(report))


if __name__ == "__main__":
    unittest.main()
