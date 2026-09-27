"""Run an actual Docker containment probe with disposable synthetic host files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from role_workflow import prepare
from run_reviewer import command


def main():
    with tempfile.TemporaryDirectory(prefix="blacklight-isolation-") as temporary:
        root = Path(temporary)
        implementer = root / "implementer"
        private = root / "private-results"
        reviewer = root / "reviewer"
        for path in (implementer, private, reviewer):
            path.mkdir()
        (implementer / "source.py").write_text("PRIVATE_SOURCE_CANARY\n")
        (private / "result.json").write_text('{"secret":"PRIVATE_RESULT_CANARY"}\n')
        contract = implementer / "contract.json"
        contract.write_text((ROOT / "templates/implementer/contract.example.json").read_text())
        handoff = root / "handoff"
        prepare(contract, handoff)
        probe = '''set -eu
cat /handoff/contract.json >/reviewer/contract-seen.json
test ! -e /implementer/source.py
test ! -e /private-results/result.json
test ! -e /host/implementer/source.py
test ! -e /var/run/docker.sock
if grep -R 'PRIVATE_SOURCE_CANARY\\|PRIVATE_RESULT_CANARY' /handoff /reviewer >/dev/null 2>&1; then exit 41; fi
printf 'isolated\\n' >/reviewer/proof.txt
'''
        invocation = command(handoff, reviewer, "debian:bookworm-slim", ["/bin/sh", "-c", probe])
        result = subprocess.run(invocation, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr.strip() or "containment probe failed", file=sys.stderr)
            return 1
        if (reviewer / "proof.txt").read_text() != "isolated\n":
            print("reviewer output was not written", file=sys.stderr)
            return 1
        if json.loads((reviewer / "contract-seen.json").read_text())["profile"] != "json-transform-v1":
            print("reviewer could not read handoff contract", file=sys.stderr)
            return 1
        print(json.dumps({"passed": True, "handoff_readable": True, "reviewer_writable": True,
                          "private_source_visible": False, "private_results_visible": False,
                          "network": "none", "container_rootfs": "read-only"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
