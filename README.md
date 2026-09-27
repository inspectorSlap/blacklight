# Blacklight

**Test the evaluator before trusting its verdict.**

Blacklight is an extracted Python prototype for testing an implementation against a separately specified contract. It combines an exact oracle, a separate reference implementation, known-broken targets, synthetic scenarios, and explicit review gates.

**Current status: metamorphic preview after Phase 4.** Three profiles share the interface. `json-transform-v1` checks exact outputs; `graph-path-v1` adds cross-run relations; `ordinal-v1` remains an offline demonstration. Target-capable profiles can use bounded local probes and durable campaigns. The two-role Docker workflow is available. **The new graph profile has not been tested on a live engine.**

## Try Blacklight locally

Python 3.11+; standard library only. No keys, provider accounts, packages, target server, or network connection are required. From this folder:

```sh
python3 -m harness.cli profiles
python3 -m harness.cli demo --profile ordinal-v1 --workspace ./workspace/ordinal-demo
python3 -m harness.cli demo --profile json-transform-v1 --workspace ./workspace/json-demo
python3 -m harness.cli demo --profile graph-path-v1 --workspace ./workspace/graph-demo
python3 -m unittest discover -s tests -v
```

Choose a fresh workspace for each demo. The ordinal command generates synthetic fixtures and a measured failure registry. The JSON command tests five hand-checked cases and five deliberate defects. The graph command checks three hand-worked bases, three cross-run relations per base and six deliberate defects. All use the same workspace and report flow. The ordinal demo does **not** run the hundreds of thousands of evaluations described by its retained simulation grid.

A successful demo exits zero when its technical checks pass. The ordinal research gate still reports `HARNESS_NOT_SELF_QUALIFIED` because operator approval is pending. Ordinal `selfqual` reports that closed gate with exit code 1. No historic approval applies to this copy. The separate `probe` and `campaign` commands support the JSON and graph profiles through the bounded local transports below.

## Test a local target

```sh
python3 -m harness.cli probe --profile json-transform-v1 \
  --program examples/json_transform_process.py --target-id toy-json-v1 \
  --workspace ./workspace/process-probe
```

This runs the five bundled examples against a toy executable. Use `--cases examples/custom-cases.json` to supply your own input values. The [target adapter guide](docs/TARGET-ADAPTERS.md) includes the loopback HTTP example, target protocol, limits and result meanings. The probe and durable campaign also accept the synthetic graph profile. See [bounded campaigns](docs/CAMPAIGNS.md) for freeze, budgets, resume, and result meanings.

## What is usable now

| Component | Status |
|---|---|
| Exact rational oracle and symbolic anchors | Runnable for `ordinal-v1` |
| Separate reference implementation | Runnable; no imports from oracle/checks/mutants |
| Known-broken targets and clean scenarios | Runnable; measured sensitivity and specificity |
| Archive/retry/provenance checks | Runnable on synthetic fixtures |
| Deterministic ordinal simulation grid and seeds | Generated; full ordinal campaign not enabled |
| Dispatch, in-flight and sequential helpers | Extracted; full operational validation pending |
| Bounded JSON campaign, durable evidence and resume | Runnable; uncertain dispatched requests stop automatic continuation |
| Full ordinal campaign and supervisor | Preserved in disabled `incubator/` design archive |
| Different schemas and criteria | Supported by writing a new profile module; no plug-in loader yet |
| Local process and loopback HTTP target probes | Runnable for `json-transform-v1`; bounded and explicitly incomplete on transport failure |
| JSON transformation example | Runnable as `json-transform-v1` with independent examples and five mutants |
| Metamorphic graph path example | Synthetic/toy runs for `graph-path-v1`; no live-engine validation |
| Two-role discovery/review process | Handoff, expectation freeze, report-only release and tested Docker process boundary |

The oracle and reference have different implementations but share historical authoring lineage. This export does not claim independent human authorship, a new blinded assessment, or independent agent agreement. See [methodology](docs/METHODOLOGY.md).

## Read next

- [Implementation guide](docs/IMPLEMENTATION.md): commands, artifacts and exit codes.
- [Profile API](docs/PROFILE-API.md): how to write and register another profile.
- [Target adapters](docs/TARGET-ADAPTERS.md): process/HTTP protocol and limits.
- [Bounded campaigns](docs/CAMPAIGNS.md): freeze, budgets, evidence and restart behavior.
- [Two-role workflow](docs/AGENT-WORKFLOW.md): independent expectations, narrow handoff and Docker containment.
- [Graph path profile](docs/GRAPH-PATH-PROFILE.md): exact anchors, cross-run relations and toy demo.
- [Test-type roadmap](docs/TEST-TYPES-ROADMAP.md): implemented, planned and live-engine validation boundaries.
- [Ordinal profile](docs/PROFILE.md): supported dimensions and fixed assumptions.
- [JSON example](docs/JSON-TRANSFORM-PROFILE.md): second profile and its exact contract.
- [Architecture](docs/ARCHITECTURE.md): active code and preserved design assets.
- [Generalization plan](docs/GENERALIZATION-PLAN.md): proposed extension points and acceptance gates.
- [Extraction record](docs/EXTRACTION.md): what was retained, changed and excluded.
- [Validation](docs/VALIDATION.md): results from this extracted copy only.
- [Public review](docs/PUBLIC-REVIEW.md): scope of the history and sensitive-content review.
- [Contribution guide](CONTRIBUTING.md): how future profiles should be demonstrated.

No original study outcomes, original study target implementation, release authority, credentials, or original Git history are included. Do not interpret a synthetic pass as qualification of an external system. The code is [MIT licensed](LICENSE). The [release review](docs/PUBLIC-REVIEW.md) describes the automated checks and the scope of independent review.
