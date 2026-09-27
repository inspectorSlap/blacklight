# Bounded campaigns (Phase 3)

A campaign runs 1–32 cases from `json-transform-v1` against a local executable or literal-loopback HTTP service. It uses the same target protocol and transport limits as [`probe`](TARGET-ADAPTERS.md). The ordinal profile remains an offline demonstration. A campaign's result is a **technical comparison of the selected cases**, not a research qualification or a general claim about the target.

## Run and resume

From the repository root, using the bundled executable:

```sh
python3 -m harness.cli campaign --profile json-transform-v1 \
  --program examples/json_transform_process.py --target-id toy-json-v1 \
  --workspace workspace/campaign-001 \
  --max-requests 5 --max-cost 0 --unit-cost 0 --execute --step-limit 2

python3 -m harness.cli campaign --profile json-transform-v1 \
  --program examples/json_transform_process.py --target-id toy-json-v1 \
  --workspace workspace/campaign-001 --resume --execute
```

The first invocation reports `INCOMPLETE` after two cases; the second completes the other three and reports `PASSED`. Omit `--execute` on the first invocation to freeze a plan without sending requests. Each invocation that should send requests needs its own `--execute`. `--cases examples/custom-cases.json` supplies input objects for a new run; the profile computes and freezes expected values. Resume uses the frozen cases and budget, so omit `--cases` and all budget flags. Use a new workspace for a new campaign.

`--max-requests` must equal the selected case count. `--unit-cost` is your nonnegative estimate per attempted request, and `--max-cost` must cover every planned request. These are conservative planning numbers, **not actual billing data**. The command checks both limits before sending any request. The current bounded run cannot add cases later or increase a budget on resume. The `--step-limit` flag limits only the current invocation. A refusal before workspace creation has sent no request.

To stop a frozen run permanently:

```sh
python3 -m harness.cli campaign --profile json-transform-v1 \
  --workspace workspace/campaign-001 --resume --abort
```

An aborted run cannot be resumed. `--abort` does not contact the target.

## Evidence and restart behavior

A campaign workspace contains:

| File | Purpose |
|---|---|
| `spec.json` | Frozen run ID, profile ID and source fingerprint, target identity, selected inputs and expected values |
| `policy.json` | Frozen request and estimated-cost ceilings |
| `evidence.sqlite3` | Durable dispatch intents, canonical request/response JSON bytes, SHA-256 digests, checks and a chained digest index |
| `report.json` | Rebuildable summary of completed evidence and current state |

The SQLite store commits a request intent before the target call and commits its result after receiving and checking the response. A restart verifies the database, freeze digests, full evidence prefix, checks, target identity and profile source fingerprint before any further call. Completed cases are not repeated. A completed row remains available even if a crash prevents the report file from being updated; resume rebuilds the report. A single-process lock prevents simultaneous dispatchers in one workspace.

A crash, timeout or lost response after dispatch leaves an intent without a completed result. It is `INDETERMINATE`: the target might have acted, so Blacklight will not retry it automatically. The operator must investigate or start a new campaign with full awareness of possible side effects. This design does **not** promise exactly-once effects at the target. Tampering with the database and recomputing every digest is outside this accidental-corruption check; the evidence is not a signed audit log.

The process identity pins the executable file digest, but not imported code, interpreter or external dependencies. The HTTP identity is the endpoint plus a target-declared ID, not a cryptographic attestation of the service. A changed program digest, changed endpoint or ID, changed profile source, modified freeze, broken evidence digest, or missing evidence row stops resumption.

## Result meanings

| Verdict | Meaning |
|---|---|
| `PASSED` | All frozen cases completed and met the profile checks |
| `FAILED` | All frozen cases completed, with at least one failed check |
| `INCOMPLETE` | No uncertain request, but some cases remain undispatched |
| `INDETERMINATE` | A dispatched request has no durable completed result |
| `ABORTED` | Operator permanently closed this campaign |

Exit codes are 0 for `PASSED`, 1 for `FAILED`, and 2 for the other states or a refusal. `research_verdict` remains null in every report. The report omits raw inputs and responses but the **workspace stores them** for verification. Treat workspaces as potentially sensitive, protect them with filesystem permissions, and inspect them before sharing. Git ignores the conventional `workspace/` path; another path may need its own ignore rule.

A local two-role workflow and Docker reviewer boundary are now available; see [the workflow guide](AGENT-WORKFLOW.md). An ordinal external target adapter remains planned work.
