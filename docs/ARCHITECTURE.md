# Architecture

The current runnable path is:

```text
synthetic fixture specifications
            |
            v
independent oracle ---- symbolic anchors
            |
            v
expected values and dispositions
            |
            +--> same checks --> separate reference (clean behavior)
            |
            +--> same checks --> broken target variants (fault detection)
                                  |
                                  v
                         per-row coverage + gate
```

`harness/oracle/` uses exact arithmetic. `harness/reference/` is a separate implementation and must not import oracle, checks, or mutants. `harness/checks/` independently checks values, decisions, archives and anchors. `harness/mutants/` implements deliberate faults. The `targets` adapter makes reference and mutants conform to the same local interface.

`build_fixtures`, `build_archives`, `build_registry`, `runner` and `selfqual` provide the runnable workflow. `simulation` generates a prospective grid and deterministic seeds, not a live campaign. `batching`, `serial`, `inflight` and `sequential` retain reusable engineering helpers; they are not a universal scheduler.

`harness/workspace.py` controls generated-artifact locations. It reads an optional `BLACKBOX_WORKSPACE` path, defaulting to `workspace/` beside the code. The CLI sets it before loading builders. Symbolic anchor inputs remain in the distribution's `fixtures/anchors/`.

## Preserved design assets

`incubator/harness/` contains a sanitized, disabled snapshot of the harness code, including the ordered-evidence campaign, evidence store, resume logic, release hashing and transport. `incubator/operations/` contains selected proxy, supervision, attestation, continuation and launch-safety sources. Source history, target implementations and execution records are absent.

These assets have study-era coupling to contract files, version IDs and earlier report filenames. Their immediate runtime guard prevents accidental execution; their value here is as concrete material for extracting the next reusable components. Active imports never depend on `incubator`.

## Planned boundaries

A future profile supplies scenario generation, anchors, oracle/reference behavior, mutations, schema normalization, decision checks and acceptance rules. The Phase 2 adapters supply bounded execution and declared identity for the JSON profile. The Phase 3 JSON campaign supplies bounded dispatch, evidence retention, resumption and estimated-cost accounting. The ordinal campaign remains in the design archive. The Phase 4 Docker runner adds a local reviewer process boundary; any work outside that process still needs separate controls. See [the plan](GENERALIZATION-PLAN.md) for deliverables and acceptance criteria.

## Phase 1 profile boundary

`harness/profiles/base.py` defines the local profile interface; `harness/profiles/ordinal.py` adapts the extracted harness and `harness/profiles/json_transform/` supplies a second, exact contract. `harness/cli.py` owns selection, workspace identity and report envelopes. The profile modules own their criteria, fixtures and evidence. See [PROFILE-API.md](PROFILE-API.md).

## Phase 2 target boundary

`harness/target_adapters.py` implements bounded process and literal-loopback HTTP transports. `harness/target_probe.py` applies a target-capable profile's cases and checks, returning PASS, FAIL or BLOCKED without fallback. `examples/` contains deliberately small toy targets and custom inputs. The [adapter guide](TARGET-ADAPTERS.md) defines the wire protocol and limits.

## Phase 3 evidence boundary

`harness/campaign.py` freezes a per-run specification and operator budget separately, records a durable dispatch intent before each target call, then commits canonical response evidence with SHA-256 digests and a chain index. Resume verifies the full prefix and identities. `report.json` is rebuilt from the store, while explicit `--execute` is required for each invocation. Research authority is not inferred from a technical pass. See [CAMPAIGNS.md](CAMPAIGNS.md).

## Phase 4 role boundary

`scripts/role_workflow.py` prepares a contract-only handoff, freezes reviewer expectations and lineage disclosure, binds that freeze to a Phase 3 campaign, and publishes a report-only result bundle. `scripts/run_reviewer.py` starts a Docker process with only the handoff and reviewer workspace mounted, no network, no host credentials, a read-only root filesystem and reduced privileges. `scripts/check_isolation.py` validates that boundary with synthetic private files. The templates under `templates/` describe the two roles. See [AGENT-WORKFLOW.md](AGENT-WORKFLOW.md).

## Metamorphic profile preview

`harness/profiles/graph_path/` adds a directed-graph contract, a repeated-relaxation oracle, a separate Dijkstra reference and six mutants. Optional `check_target_relations` lets the probe and campaign evaluate pairs of completed outputs. Derived requests check schema individually; relation findings are computed from the full set of frozen response evidence and remain pending during partial runs. The bundled graph executable is synthetic; this type has not been tested on a live engine.
