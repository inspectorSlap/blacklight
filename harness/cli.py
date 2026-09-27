"""Local profile and bounded target-probe commands."""
import argparse
import json
import math
import os
from pathlib import Path
import sys


def main(argv=None):
    from .profiles import PROFILES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("profiles", "demo", "build", "selfqual", "status", "probe", "campaign", "ordered-dryrun"))
    parser.add_argument("--profile", choices=tuple(PROFILES), default="ordinal-v1")
    parser.add_argument("--workspace", type=Path)
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument("--program", type=Path, help="executable for a local process target")
    transport.add_argument("--url", help="literal loopback HTTP URL")
    parser.add_argument("--target-id", help="declared identity returned in every response")
    parser.add_argument("--timeout", type=float, default=3.0, help="seconds per target request, 0.1–30")
    parser.add_argument("--cases", type=Path, help="JSON array of custom input objects; probe only")
    args = parser.parse_args(argv)
    if args.command == "profiles":
        print(json.dumps([{"id": p.profile_id, "description": p.description} for p in PROFILES.values()], indent=2))
        return 0
    if args.command in ("campaign", "ordered-dryrun"):
        print("NOT_IMPLEMENTED: campaign and ordered execution are not available.", file=sys.stderr)
        return 2
    if args.workspace:
        os.environ["BLACKBOX_WORKSPACE"] = str(args.workspace.resolve())
    from .workspace import ROOT
    workspace = Path(ROOT)
    profile = PROFILES[args.profile]
    marker = workspace / "profile.json"
    if args.command == "status":
        recorded = json.loads(marker.read_text())["profile"] if marker.is_file() else None
        print(json.dumps({"stage": "PHASE2_LOCAL_TARGET_PROTOTYPE", "available_profiles": list(PROFILES),
                          "workspace_profile": recorded, "target_adapters": ["local-process", "loopback-http"],
                          "remote_network_enabled": False,
                          "report_exists": (workspace / "results/profile-evaluation.json").is_file(),
                          "target_probe_exists": (workspace / "results/target-probe.json").is_file()}, indent=2))
        return 0
    if args.command == "probe":
        from .target_adapters import Blocked, ProcessAdapter, LoopbackHttpAdapter, validate_target_id
        from . import target_probe
        if not hasattr(profile, "target_cases") or not hasattr(profile, "check_target_output"):
            parser.error("profile does not support target probes yet")
        if (args.program is None) == (args.url is None):
            parser.error("probe requires exactly one of --program or --url")
        if not args.target_id:
            parser.error("probe requires --target-id")
        try:
            validate_target_id(args.target_id)
        except ValueError as exc:
            parser.error(str(exc))
        if not math.isfinite(args.timeout) or not 0.1 <= args.timeout <= 30:
            parser.error("--timeout must be 0.1–30 seconds")
        if workspace.exists():
            parser.error("workspace already exists; choose a new path to preserve earlier evidence")
        custom = None
        if args.cases:
            try:
                if args.cases.stat().st_size > 1048576:
                    parser.error("cases file exceeds 1 MiB")
                custom = json.loads(args.cases.read_text())
            except (OSError, UnicodeError, ValueError):
                parser.error("cases file is unreadable or invalid JSON")
        try:
            cases = profile.target_cases(custom)
        except (ValueError, TypeError, KeyError):
            parser.error("cases do not match the selected profile contract")
        for sub in ("fixtures", "results", "reports"):
            (workspace / sub).mkdir(parents=True, exist_ok=True)
        profile.build(workspace)
        marker.write_text(json.dumps({"profile": profile.profile_id, "description": profile.description,
                                      "target_probe": True}, indent=2) + "\n")
        local = profile.evaluate(workspace)
        if not local.technical_checks_passed:
            parser.error("profile's local checks failed; target probe refused")
        adapter = None
        try:
            adapter = (ProcessAdapter(args.program, args.target_id, workspace, args.timeout)
                       if args.program else LoopbackHttpAdapter(args.url, args.target_id, args.timeout))
        except ValueError as exc:
            parser.error(str(exc))
        except Blocked as exc:
            report = {"profile": profile.profile_id, "target": {"transport": "local-process", "target_id": args.target_id},
                      "verdict": "BLOCKED", "planned_cases": len(cases), "executed_cases": 0,
                      "counts": {"PASS": 0, "FAIL": 0, "BLOCKED": 1},
                      "rows": [{"case": None, "status": "BLOCKED", "reason": exc.code}],
                      "scope": "bounded local target probe; no campaign qualification"}
        else:
            report = target_probe.run(profile, adapter, cases)
        path = workspace / "results/target-probe.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2))
        print(path)
        return 0 if report["verdict"] == "PASS" else 1 if report["verdict"] == "FAIL" else 2
    if args.command in ("demo", "build"):
        if workspace.exists():
            parser.error("workspace already exists; choose a new path to preserve earlier evidence")
        for sub in ("fixtures", "results", "reports"):
            (workspace / sub).mkdir(parents=True, exist_ok=True)
        built = profile.build(workspace)
        marker.write_text(json.dumps({"profile": profile.profile_id, "description": profile.description,
                                      "external_target_enabled": False}, indent=2) + "\n")
        print(json.dumps({"profile": profile.profile_id, "built": built}, indent=2), flush=True)
    if args.command in ("demo", "selfqual"):
        if not marker.is_file():
            parser.error("workspace has no profile marker; run build in a new workspace first")
        recorded = json.loads(marker.read_text()).get("profile")
        if recorded != profile.profile_id:
            parser.error("workspace belongs to %s; select that profile" % recorded)
        try:
            result = profile.evaluate(workspace)
        except (ValueError, KeyError, FileNotFoundError, TypeError) as exc:
            parser.error("profile evaluation failed: %s" % exc)
        report = {"profile": profile.profile_id, "technical_checks_passed": result.technical_checks_passed,
                  "gate": result.gate, "profile_gate_passed": result.profile_gate_passed,
                  "external_target_enabled": False, "details": result.details}
        path = workspace / "results/profile-evaluation.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        print(path)
        if args.command == "selfqual":
            return 0 if result.profile_gate_passed else 1
        return 0 if result.technical_checks_passed else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
