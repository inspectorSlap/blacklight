# Extraction validation

Extraction validation run on 2026-09-27 using the extracted copy, Python standard library, and freshly generated synthetic fixtures. These results do not describe an external target or a completed research campaign.

| Check | Result |
|---|---|
| Known-broken targets detected and correctly attributed | 28 / 28 |
| Clean synthetic scenarios accepted | 47 / 47 |
| Numeric anchors checked | 57; oracle and reference passed |
| Failure-registry coverage | 80 rows complete |
| Extraction regression suite | 11 tests passed |
| Export heuristic scan | No issues detected |
| Original selected source integrity | Hashes unchanged |

The research gate remains `HARNESS_NOT_SELF_QUALIFIED`, with `failure_registry` blocking because approval is pending. Technical demo success does not approve the registry, validate all statistical operating characteristics, or authorize real-target execution.

## Reproduce

From the repository root, choose a workspace that does not already exist:

```sh
python3 -m harness.cli demo --workspace ./workspace/validation
python3 -m unittest discover -s tests -v
python3 scripts/audit_export.py
```

The demo writes `results/self-qualification-v1.0.json` beneath the selected workspace. Generated workspaces are intentionally excluded from the export scan and Git; review any evidence separately before sharing it. This package includes source and mathematical fixtures, not the generated run archive.

Regression tests cover pending approval, reference import separation, exact anchors, blocked findings, roster enforcement, deterministic scenarios, a valid reference case, disabled external CLI commands, preservation of existing workspaces, disabled archived execution, and a scrub-scan canary.

## Limits

These are bounded synthetic checks of the bundled ordinal profile. They do not establish universal defect detection, calibrated error rates across arbitrary inputs, statistical validity of every retained procedure, operational durability of the disabled campaign code, or enforced isolation between agents. The export scan is heuristic and cannot certify absence of every sensitive detail. Selected source files were checked against a private hash manifest; that manifest is stored outside this package.

## Phase 1 validation

The new JSON profile passed five hand-checked oracle/reference cases and detected five of five deliberate defects through their named checks. The ordinal profile was rerun through the shared CLI: 28/28 deliberate defects detected, 47 clean scenarios accepted, and 57 numeric anchors checked. The expanded suite passed 16 tests, and the heuristic export scan reported no issues. Both profiles remain offline.
