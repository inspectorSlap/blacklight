> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Campaign runner — v1.3

**Status:** corrected after the v1.2 checkpoint failure. **The v1.3 checkpoint
has not yet run.**
**Supersedes:** `CAMPAIGN-RUNNER-v1.2.md` (preserved; byte-exact v1.2 release
under `releases/v1.2/` and `releases/by-digest/7040aed3…`).
**Deviation record:** `releases/deviations/checkpoint-v1.2-run-001/`

## 1. What v1.2 got wrong

500 real-target requests, zero successful analyses, reported as
`STORAGE_CHECKPOINT_COMPLETE` with `campaign_valid: true`.

| Defect | Correction |
|---|---|
| Placeholder specimen identifiers `ordinal-profile..S6`/`M1..M4` | canonical frozen roster + zero-call preflight |
| Checkpoint failed open | fail-closed audit; 500/500 rejection is now impossible to report as completion |
| `BlackBoxTarget` lacked `analyze_batch` | capability supplied and preflight-verified; no silent fallback |

## 2. Canonical roster (`harness/roster.py`)

Semantic: `sample-01, sample-02, sample-03, sample-04, sample-05, sample-06`
Mechanical: `control-01, control-02, control-03, control-04`

The mapping from role index to identifier is **positional and bijective**, so
position `i` still carries the same distribution. Leave-one-out order,
first-three/last-three splits and floor-limited constructions are untouched.
The identifiers are public metadata in preregistration §2; labelling synthetic
counts with them constructs no ordinal-profile artifact and reads no ordinal-profile outcome.

The preflight rejects placeholder, missing, duplicated, reordered, extra and
mechanical-in-primary rosters, at **zero target calls**, and every payload is
re-checked immediately before dispatch.

## 3. Fail-closed checkpoint

`campaign_valid: false`, `status: STORAGE_CHECKPOINT_FAILED`,
`checkpoint_disposition: CHECKPOINT_FAILED` and a nonzero exit whenever there
is any blocked request, non-analysis response, schema rejection, missing
response, digest failure, or successful-analysis count below the requested
count. A failed checkpoint marks its own storage measurement **VOID**.

Success is counted by **structure only** — schema version plus required
top-level blocks — never by reading a disposition, so the checkpoint stays
blind while still failing closed.

## 4. Batch capability

Preflight verifies the capability exists before any target call. If absent the
campaign stops rather than executing single requests while retaining batched
cost projections. One evidence record and digest per replication is preserved
on both paths. Interruption fallback to singles remains, and is recorded.

## 5. Launch order

```
1. phase gate       2. --confirm       3. D6 resolution
4. ROSTER PREFLIGHT (zero calls)       5. BATCH PREFLIGHT (zero calls)
6. release integrity                   7. identity before
8. scientific requests                 9. identity after
```

Steps 3–6 all precede any request.

## 6. Verification

Dry run **81/81**, zero real-engine calls. Five negative controls prove:
placeholder rosters rejected before transport; a single blocked request fails
the checkpoint; zero successful analyses cannot pass; missing batch capability
fails preflight; batch and single representations are semantically equivalent.

Scientific invariance: **0 of 47** scenario files differ beyond identifiers;
all count vectors byte-identical; 57 hand anchors reproduced; oracle, sound
reference and anchor file unchanged; critical values `(10,49) (70,144) (72,142)`
unchanged; D6 `corrected_two_look` unchanged.
