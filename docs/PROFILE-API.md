# Profile extension guide

Phase 1 provides a small Python interface for local profiles. A profile owns its input contract, independent expected behavior, synthetic fixtures, deliberate defects and checks. The common CLI owns profile selection, fresh workspaces and a consistent `results/profile-evaluation.json` envelope. The interface does not yet load arbitrary installed plugins. A profile may opt into bounded target probes by implementing `TargetProfile`.

## Interface

`harness/profiles/base.py` defines `Profile`: `profile_id`, `description`, `build(workspace)` and `evaluate(workspace)`. `build` writes synthetic fixtures and returns a short inventory. `evaluate` returns `Evaluation(technical_checks_passed, gate, profile_gate_passed, details)`. It may write additional profile-owned evidence beneath `results/`. Keep output JSON-serializable.

The built-in registry now names `ordinal-v1`, `json-transform-v1` and `graph-path-v1`. The first wraps the extracted statistical harness; the second checks an exact JSON transformation; the third checks exact path distances and cross-run relations. All use the same workspace and report flow in `harness/cli.py`.

## Authoring a profile

1. Specify exact input and output schemas and decide which cases must be refused or marked indeterminate.
2. Write independently checked examples before using either implementation as an answer key. For a domain without a complete oracle, state the exact subset that can be checked and which properties remain unproved.
3. Build the oracle and sound reference separately. Do not import oracle, checks or mutants into the reference. Different implementations reduce shared mistakes; they do not prove independent authorship.
4. Add clean fixtures and targeted broken variants. For each claimed criterion, show a defect that violates it and name the check that should fire.
5. Implement `build` and `evaluate`, then register the profile. Add an end-to-end CLI test and run the export scan.

The caller selects a profile with `--profile`. A workspace records its profile ID; `selfqual` refuses a different profile. `demo` returns success for technical profile checks; `selfqual` uses the profile-owned `profile_gate_passed` value. The ordinal research gate stays closed pending its registry approval. The JSON example has a local technical gate only. Reports never authorize external execution.

## Criteria and ownership

Each profile decides what its criteria mean. `json-transform-v1` checks selection at an inclusive boundary, original order, total, count and output shape. The ordinal profile owns its own statistical decisions and fixed thresholds. There is no shared global threshold file, because applying one numeric rule to every domain would be unsound. A contributor who needs different inputs or values can add a profile module and tests today; configurable profile discovery and third-party loading are future work.

## Target-capable profiles

`TargetProfile` adds `target_cases(custom_inputs)` and `check_target_output(observed, expected)`. The first returns 1–32 cases with `id`, `input` and independently derived `expected` fields. The second returns named failed criteria. The shared `probe` runner calls the selected process or loopback adapter and never substitutes a reference result after a transport failure. The JSON and graph profiles demonstrate this extension. The ordinal profile does not yet implement it. `RelationalTargetProfile` additionally defines `check_target_relations(cases, observations)`. The probe and campaign call it only when all selected responses exist, and report `PENDING` for an incomplete set. A relation failure contributes to the technical verdict even when every individual response passes its shape check. `graph-path-v1` shows exact base expectations beside relation-only derived expectations. Its optional `validate_target_cases` preflight verifies oracle agreement, complete relation groups and the declared input transformations before any target request; see [its profile guide](GRAPH-PATH-PROFILE.md).

## Remaining boundary

A bounded durable campaign supports the JSON and graph profiles, and the Docker reviewer boundary can freeze either profile’s cases. Broader adapters, ordinal target support and qualification policy remain future work. The graph profile has only synthetic and bundled-toy validation, not a live-engine test. A new profile cannot claim that passing a bounded probe validates a production system.
