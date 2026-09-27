# BlackboxHarness

**Test the evaluator before trusting its verdict.**

BlackboxHarness is an extracted Python prototype for testing an implementation against a separately specified contract. It combines an exact oracle, a separate reference implementation, known-broken targets, synthetic scenarios, and explicit review gates.

**Current status: local extraction, not a public release.** The working name is temporary. The runnable component supports one bounded ordinal-scoring profile. General-purpose profiles, external target integrations, enforced agent isolation, and supported campaign execution are planned. A broad methodology is not the same thing as broad implementation support.

## Try the local prototype

Python 3.11+; standard library only. No keys, provider accounts, packages, target server, or network connection are required. From this folder:

```sh
python3 -m harness.cli demo --workspace ./workspace/first-demo
python3 -m harness.cli status --workspace ./workspace/first-demo
python3 -m unittest discover -s tests -v
```

Choose a fresh workspace for each demo. The command generates synthetic fixtures and a measured failure registry, runs the oracle/reference/mutant checks, and writes local evidence. It does **not** run the hundreds of thousands of evaluations described by the retained simulation grid.

A successful demo exits zero when its technical checks pass. The research gate still reports `HARNESS_NOT_SELF_QUALIFIED` because operator approval is pending. `selfqual` reports that closed gate with exit code 1. No historic approval applies to this copy, and no CLI command enables external execution.

## What is usable now

| Component | Status |
|---|---|
| Exact rational oracle and symbolic anchors | Runnable for the bundled profile |
| Separate reference implementation | Runnable; no imports from oracle/checks/mutants |
| Known-broken targets and clean scenarios | Runnable; measured sensitivity and specificity |
| Archive/retry/provenance checks | Runnable on synthetic fixtures |
| Deterministic simulation grid and seeds | Generated; full campaign not enabled |
| Dispatch, in-flight and sequential helpers | Extracted; full operational validation pending |
| Durable campaign, resume, freeze and supervisor code | Preserved in disabled `incubator/` design archive |
| Different scales, schemas, domains and user-defined criteria | Planned; not a config-file feature today |
| Two-agent discovery/review process | Documented methodology; not automatically enforced |

The oracle and reference have different implementations but share historical authoring lineage. This export does not claim independent human authorship, a new blinded assessment, or independent agent agreement. See [methodology](docs/METHODOLOGY.md).

## Read next

- [Implementation guide](docs/IMPLEMENTATION.md): commands, artifacts and exit codes.
- [Current profile](docs/PROFILE.md): supported dimensions and fixed assumptions.
- [Architecture](docs/ARCHITECTURE.md): active code and preserved design assets.
- [Generalization plan](docs/GENERALIZATION-PLAN.md): proposed extension points and acceptance gates.
- [Extraction record](docs/EXTRACTION.md): what was retained, changed and excluded.
- [Validation](docs/VALIDATION.md): results from this extracted copy only.
- [Contribution guide](CONTRIBUTING.md): how future profiles should be demonstrated.

No source-study outcomes, target implementation, original release authority, credentials, or Git history are included. Do not interpret a synthetic pass as qualification of an external system. Licensing and public-repository creation remain decisions for the owner; this folder has not been published.
