# BlackboxHarness

**Test the evaluator before trusting its verdict.**

BlackboxHarness is an extracted Python prototype for testing an implementation against a separately specified contract. It combines an exact oracle, a separate reference implementation, known-broken targets, synthetic scenarios, and explicit review gates.

**Current status: local Phase 2 prototype, not a public release.** The working name is temporary. Two profiles run through a common interface. The JSON profile can now probe a user-selected local executable or loopback HTTP service. The ordinal profile remains an offline demonstration. Enforced agent isolation and durable campaigns are later work.

## Try the local prototype

Python 3.11+; standard library only. No keys, provider accounts, packages, target server, or network connection are required. From this folder:

```sh
python3 -m harness.cli profiles
python3 -m harness.cli demo --profile ordinal-v1 --workspace ./workspace/ordinal-demo
python3 -m harness.cli demo --profile json-transform-v1 --workspace ./workspace/json-demo
python3 -m unittest discover -s tests -v
```

Choose a fresh workspace for each demo. The ordinal command generates synthetic fixtures and a measured failure registry. The JSON command tests five hand-checked cases and five deliberate defects. Both use the same workspace and report flow. The ordinal demo does **not** run the hundreds of thousands of evaluations described by its retained simulation grid.

A successful demo exits zero when its technical checks pass. The ordinal research gate still reports `HARNESS_NOT_SELF_QUALIFIED` because operator approval is pending. Ordinal `selfqual` reports that closed gate with exit code 1. No historic approval applies to this copy. The separate `probe` command can test only the JSON profile through the bounded local transports below.

## Test a local target

```sh
python3 -m harness.cli probe --profile json-transform-v1 \
  --program examples/json_transform_process.py --target-id toy-json-v1 \
  --workspace ./workspace/process-probe
```

This runs the five bundled examples against a toy executable. Use `--cases examples/custom-cases.json` to supply your own input values. The [target adapter guide](docs/TARGET-ADAPTERS.md) includes the loopback HTTP example, target protocol, limits and result meanings. The probe accepts the JSON profile only at this stage.

## What is usable now

| Component | Status |
|---|---|
| Exact rational oracle and symbolic anchors | Runnable for `ordinal-v1` |
| Separate reference implementation | Runnable; no imports from oracle/checks/mutants |
| Known-broken targets and clean scenarios | Runnable; measured sensitivity and specificity |
| Archive/retry/provenance checks | Runnable on synthetic fixtures |
| Deterministic simulation grid and seeds | Generated; full campaign not enabled |
| Dispatch, in-flight and sequential helpers | Extracted; full operational validation pending |
| Durable campaign, resume, freeze and supervisor code | Preserved in disabled `incubator/` design archive |
| Different schemas and criteria | Supported by writing a new profile module; no plug-in loader yet |
| Local process and loopback HTTP target probes | Runnable for `json-transform-v1`; bounded and explicitly incomplete on transport failure |
| JSON transformation example | Runnable as `json-transform-v1` with independent examples and five mutants |
| Two-agent discovery/review process | Documented methodology; not automatically enforced |

The oracle and reference have different implementations but share historical authoring lineage. This export does not claim independent human authorship, a new blinded assessment, or independent agent agreement. See [methodology](docs/METHODOLOGY.md).

## Read next

- [Implementation guide](docs/IMPLEMENTATION.md): commands, artifacts and exit codes.
- [Profile API](docs/PROFILE-API.md): how to write and register another profile.
- [Target adapters](docs/TARGET-ADAPTERS.md): process/HTTP protocol and limits.
- [Ordinal profile](docs/PROFILE.md): supported dimensions and fixed assumptions.
- [JSON example](docs/JSON-TRANSFORM-PROFILE.md): second profile and its exact contract.
- [Architecture](docs/ARCHITECTURE.md): active code and preserved design assets.
- [Generalization plan](docs/GENERALIZATION-PLAN.md): proposed extension points and acceptance gates.
- [Extraction record](docs/EXTRACTION.md): what was retained, changed and excluded.
- [Validation](docs/VALIDATION.md): results from this extracted copy only.
- [Public review](docs/PUBLIC-REVIEW.md): scope of the owner's prepublication sweep.
- [Contribution guide](CONTRIBUTING.md): how future profiles should be demonstrated.

No original study outcomes, original study target implementation, release authority, credentials, or original Git history are included. Do not interpret a synthetic pass as qualification of an external system. The code is [MIT licensed](LICENSE). Public-repository creation and the owner's independent review remain pending; this folder has not been published.
