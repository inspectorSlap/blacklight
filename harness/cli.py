"""Offline extraction workspace commands. External campaigns are not implemented."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "build", "selfqual", "status", "campaign", "ordered-dryrun"))
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    if args.workspace:
        import os
        os.environ["BLACKBOX_WORKSPACE"] = str(args.workspace.resolve())
    from .workspace import ROOT
    root = Path(ROOT)
    if args.command in ("campaign", "ordered-dryrun"):
        print("NOT_IMPLEMENTED: external and vendored-engine execution is excluded from this extraction.", file=sys.stderr)
        return 2
    if args.command == "status":
        print(json.dumps({"stage": "EXTRACTED_PROTOTYPE", "profile": "ordinal-v0", "external_target_enabled": False, "operator_approval": "PENDING", "report_exists": (root / "results/self-qualification-v1.0.json").exists()}, indent=2))
        return 0
    if args.command in ("demo", "build"):
        if root.exists():
            parser.error("workspace already exists; choose a new path to preserve earlier evidence")
        for sub in ("fixtures", "results", "reports"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        from . import build_fixtures, build_archives, build_registry, simulation
        written = build_fixtures.write_panel(build_fixtures.build_clean_panel(), "clean")
        written += build_fixtures.write_panel(build_fixtures.build_anchor_panel(), "anchors")
        written += build_archives.write_panel(build_archives.build_archive_panel())
        simulation.write_grid_and_seeds()  # Generates a plan only; no simulated campaign runs.
        print("Built %d synthetic scenario files; building measured failure registry..." % len(written), flush=True)
        registry = build_registry.build()
        build_registry.write(registry)
        build_registry.write_matrix(registry)
        print("Registry rows: %d; operator approval: PENDING" % len(registry["rows"]), flush=True)
    if args.command in ("demo", "selfqual"):
        from . import runner, selfqual
        if any(not rows for rows in runner.load_all().values()):
            parser.error("all three fixture panels are required; run build in a new workspace first")
        result = selfqual.run_gate()
        result["extraction_status"] = "PROTOTYPE_NOT_PUBLIC_RELEASE"
        path = root / "results/self-qualification-v1.0.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        legs = result["legs"]
        technical = all(legs[k]["passed"] for k in ("anchors", "specificity", "sensitivity")) and legs["failure_registry"]["complete"]
        print(json.dumps({"technical_checks_passed": technical, "gate": result["verdict"], "blocking_legs": result["blocking_legs"], "sensitivity": "%s/%s" % (sum(r["row_passed"] for r in legs["sensitivity"]["rows"]), legs["sensitivity"]["mutants_run"]), "specificity_scenarios": legs["specificity"]["scenarios_run"], "anchor_values": legs["anchors"]["numeric_values_checked"], "external_target_enabled": False}, indent=2))
        print(path)
        # Demo reports mechanics success separately from the still-closed research gate.
        if args.command == "demo":
            return 0 if technical else 1
        return 0 if result["verdict"] == "HARNESS_SELF_QUALIFIED" else 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
