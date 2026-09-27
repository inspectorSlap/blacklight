# Implementation guide

Run commands from the folder root using Python 3.11 or newer. There are no third-party runtime dependencies. A virtual environment is optional; nothing must be installed to run the modules.

## Run a complete offline demonstration

```sh
python3 -m harness.cli profiles
python3 -m harness.cli demo --profile ordinal-v1 --workspace workspace/demo-001
python3 -m harness.cli demo --profile json-transform-v1 --workspace workspace/json-001
```

The destination must not already exist. A workspace contains generated scenario fixtures under `fixtures/`, a failure registry and machine-readable qualification output under `results/`, and a coverage matrix under `reports/`. All generated scenarios are synthetic. No original research results are copied.

All three demos use the same `profile.json` workspace marker and `results/profile-evaluation.json` report. The ordinal profile also writes its detailed legacy report. Its technical pass returns exit 0, while its research gate remains unqualified because registry approval is pending. The JSON and graph profiles report local technical checks only. A test failure returns 1. No network transport is constructed.

## Run the steps separately

```sh
python3 -m harness.cli build --profile ordinal-v1 --workspace workspace/demo-002
python3 -m harness.cli selfqual --profile ordinal-v1 --workspace workspace/demo-002
python3 -m harness.cli status --workspace workspace/demo-002
```

`selfqual` returns 1 for the ordinal profile's intentionally pending approval; inspect its JSON rather than treating that as a software crash. `build` creates a new workspace and refuses reuse. `selfqual` recomputes and replaces that workspace's qualification report; preserve/copy a report before editing code if you need comparison history.

`status` reports whether demo/probe reports or a campaign evidence file exist, not whether their contents remain valid after code changes. Campaigns use a separate frozen workspace and verified resume path.

## Standalone reference

```sh
python3 -m harness.reference.sound_reference analyze < your-synthetic-counts.json
python3 -m harness.reference.sound_reference aggregate < your-synthetic-archive.json
```

Use the generated fixture payloads as shape examples. Do not pass an entire scenario envelope where a `payload` object is expected. The reference is profile-specific.

## Disabled paths

`ordered-dryrun` returns `NOT_IMPLEMENTED` and exit 2 before constructing a target. The bounded JSON `campaign` command is active; see [the campaign guide](CAMPAIGNS.md). Every archived Python module in `incubator/` raises immediately before its imports or actions. It is preserved source for design work, not a runnable second product. Removing those guards is not sufficient to restore compatibility: private contract files, prior authorizations and the vendored target are intentionally absent.

## Validation and release hygiene

```sh
python3 -m unittest discover -s tests -v
python3 scripts/audit_export.py
```

Generated workspaces are ignored by the proposed Git configuration. Inspect candidate files before creating a public repository. No automatic test can certify absence of all sensitive content; the extraction record describes both the automated scan and the material manually excluded.

For another profile, use `--profile json-transform-v1` or `--profile graph-path-v1` with `build` and `selfqual`. A workspace refuses a mismatched profile. See [the profile extension guide](PROFILE-API.md).

## Probe your own target (Phase 2)

For the JSON transformation profile, use `probe` with either `--program` or `--url` and a matching `--target-id`. It creates a fresh workspace and writes `results/target-probe.json`. Exit 0 means all selected cases pass; 1 means a completed response failed a criterion; 2 means the run was blocked. See [target adapters](TARGET-ADAPTERS.md) for the request/response contract, examples, bounds and security limits. The ordinal profile does not yet have a target adapter.

## Run a bounded campaign (Phase 3)

See [bounded campaigns](CAMPAIGNS.md) for a complete start/resume example, costs and request limits, evidence files, result meanings and restart behavior. A campaign uses a fresh workspace, a target-capable profile, an explicit request budget, an estimated cost ceiling and `--execute` on each dispatching invocation. The ordinal target path remains unsupported.

## Run the two-role workflow (Phase 4)

See [the agent workflow guide](AGENT-WORKFLOW.md) for contract preparation, reviewer containment, expectation freezing, campaign evaluation and report-only publication. The Docker containment check is `python3 scripts/check_isolation.py` after pulling its documented public image. It uses disposable synthetic files.

## Try a metamorphic test type (synthetic preview)

```sh
python3 -m harness.cli demo --profile graph-path-v1 --workspace workspace/graph-demo
python3 -m harness.cli probe --profile graph-path-v1 \
  --program examples/graph_path_process.py --target-id toy-graph-v1 \
  --workspace workspace/graph-probe
```

The graph profile checks exact base distances and three relations between each base and transformed request. Its bundled process is a toy target; **no live engine has been tested**. See [the graph profile](GRAPH-PATH-PROFILE.md) and [test-type roadmap](TEST-TYPES-ROADMAP.md).
