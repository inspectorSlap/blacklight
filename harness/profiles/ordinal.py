"""Adapter for the extracted ordinal harness; its math remains profile owned."""
import json
from pathlib import Path
from typing import Any

from .base import Evaluation


class OrdinalProfile:
    profile_id = "ordinal-v1"
    description = "Bounded ordinal scoring with four cells and fixed criteria C1–C5"

    def build(self, workspace: Path) -> dict[str, Any]:
        from .. import build_fixtures, build_archives, build_registry, simulation
        written = build_fixtures.write_panel(build_fixtures.build_clean_panel(), "clean")
        written += build_fixtures.write_panel(build_fixtures.build_anchor_panel(), "anchors")
        written += build_archives.write_panel(build_archives.build_archive_panel())
        simulation.write_grid_and_seeds()  # A plan; no campaign is run.
        registry = build_registry.build()
        build_registry.write(registry)
        build_registry.write_matrix(registry)
        return {"synthetic_scenario_files": len(written), "failure_registry_rows": len(registry["rows"]),
                "operator_approval": "PENDING"}

    def evaluate(self, workspace: Path) -> Evaluation:
        from .. import runner, selfqual
        if any(not rows for rows in runner.load_all().values()):
            raise ValueError("all three fixture panels are required")
        result = selfqual.run_gate()
        result["extraction_status"] = "PROFILE_PROTOTYPE"
        report = workspace / "results/self-qualification-v1.0.json"
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        legs = result["legs"]
        technical = all(legs[k]["passed"] for k in ("anchors", "specificity", "sensitivity")) and legs["failure_registry"]["complete"]
        summary: dict[str, Any] = {
            "blocking_legs": result["blocking_legs"],
            "sensitivity": "%s/%s" % (sum(r["row_passed"] for r in legs["sensitivity"]["rows"]), legs["sensitivity"]["mutants_run"]),
            "specificity_scenarios": legs["specificity"]["scenarios_run"],
            "anchor_values": legs["anchors"]["numeric_values_checked"],
            "legacy_report": str(report.relative_to(workspace)),
        }
        return Evaluation(technical, result["verdict"], result["verdict"] == "HARNESS_SELF_QUALIFIED", summary)
