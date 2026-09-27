# Implementation guide

Run commands from the folder root using Python 3.11 or newer. There are no third-party runtime dependencies. A virtual environment is optional; nothing must be installed to run the modules.

## Run a complete offline demonstration

```sh
python3 -m harness.cli demo --workspace workspace/demo-001
```

The destination must not already exist. A workspace contains generated scenario fixtures under `fixtures/`, a failure registry and machine-readable qualification output under `results/`, and a coverage matrix under `reports/`. All generated scenarios are synthetic. No original research results are copied.

The demo has two distinct outcomes: technical checks and research authority. A technical pass returns exit 0, while the JSON gate remains unqualified because the registry approval is pending. A test failure returns 1. No network transport is constructed.

## Run the steps separately

```sh
python3 -m harness.cli build --workspace workspace/demo-002
python3 -m harness.cli selfqual --workspace workspace/demo-002
python3 -m harness.cli status --workspace workspace/demo-002
```

`selfqual` returns 1 for the intentionally pending approval; inspect its JSON rather than treating that as a software crash. `build` creates a new workspace and refuses reuse. `selfqual` recomputes and replaces that workspace's qualification report; preserve/copy a report before editing code if you need comparison history.

`status` reports whether a report file exists, not whether its contents remain valid after code changes. Artifact freezing for public campaigns is planned.

## Standalone reference

```sh
python3 -m harness.reference.sound_reference analyze < your-synthetic-counts.json
python3 -m harness.reference.sound_reference aggregate < your-synthetic-archive.json
```

Use the generated fixture payloads as shape examples. Do not pass an entire scenario envelope where a `payload` object is expected. The reference is profile-specific.

## Disabled paths

`campaign` and `ordered-dryrun` return `NOT_IMPLEMENTED` and exit 2 before constructing a target. Every archived Python module in `incubator/` raises immediately before its imports or actions. It is preserved source for design work, not a runnable second product. Removing those guards is not sufficient to restore compatibility: private contract files, prior authorizations and the vendored target are intentionally absent.

## Validation and release hygiene

```sh
python3 -m unittest discover -s tests -v
python3 scripts/audit_export.py
```

Generated workspaces are ignored by the proposed Git configuration. Inspect candidate files before creating a public repository. No automatic test can certify absence of all sensitive content; the extraction record describes both the automated scan and the material manually excluded.
