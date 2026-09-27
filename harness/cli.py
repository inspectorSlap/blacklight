"""Local profile commands. External campaigns are not implemented."""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    from .profiles import PROFILES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("profiles", "demo", "build", "selfqual", "status", "campaign", "ordered-dryrun"))
    parser.add_argument("--profile", choices=tuple(PROFILES), default="ordinal-v1")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    if args.command == "profiles":
        print(json.dumps([{"id": p.profile_id, "description": p.description} for p in PROFILES.values()], indent=2))
        return 0
    if args.command in ("campaign", "ordered-dryrun"):
        print("NOT_IMPLEMENTED: external target execution is not available.", file=sys.stderr)
        return 2
    if args.workspace:
        os.environ["BLACKBOX_WORKSPACE"] = str(args.workspace.resolve())
    from .workspace import ROOT
    workspace = Path(ROOT)
    profile = PROFILES[args.profile]
    marker = workspace / "profile.json"
    if args.command == "status":
        recorded = json.loads(marker.read_text())["profile"] if marker.is_file() else None
        print(json.dumps({"stage": "PHASE1_LOCAL_PROFILES", "available_profiles": list(PROFILES),
                          "workspace_profile": recorded, "external_target_enabled": False,
                          "report_exists": (workspace / "results/profile-evaluation.json").is_file()}, indent=2))
        return 0
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
