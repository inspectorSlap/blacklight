> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Campaign runner — v1.0

**Status:** implemented and operationally verified against the local sound
reference. **The real engine has not been contacted on any scientific
endpoint.**
**Implementation:** `harness/campaign.py`
**Operational tests:** `harness/dryrun.py` → `results/campaign-dryrun-v1.0.json`

This document describes what `python3 -m harness.cli campaign --confirm` will
do when the operator launches it. It changes no approved element of
`reports/SIMULATION-ACCEPTANCE-PROPOSAL-v1.0.md`; it implements it.

---

## 1. Launch gating

`campaign` is refused unless **all** of the following hold:

1. the release manifest exists (`release_frozen`);
2. `results/self-qualification-v1.0.json` records `HARNESS_SELF_QUALIFIED`;
3. the failure registry records `operator_approval.status == "APPROVED"`.

Even with the gate open, the command exits **3** and does nothing unless
`--confirm` is passed. Launching the real campaign is an explicit operator
action, never a side effect of running a status command.

Exit codes: `0` valid campaign, `2` phase gate closed, `3` confirmation
required, `4` proxy not configured (fail closed), `5` campaign aborted invalid.

---

## 2. Identity binding (amendment §5)

| Step | Behaviour |
|---|---|
| Immediately before | `GET /v0.1/meta`; every field must equal `target-manifest-v0.2.json`'s `target` block exactly |
| During | the pre-campaign metadata digest is stamped into **every** index record |
| Immediately after | `GET /v0.1/meta` again; the after digest must equal the before digest |
| On any mismatch | campaign **aborts**, `status = ABORTED_INVALID`, `campaign_valid = false`, `engine_result_state = NOT_ASSESSED` |

An aborted campaign's report states explicitly that its results are **not
usable**. Evidence already written is retained for audit but may not be cited
as engine evidence. This enforces the requirement that the endpoint build
tested is the build later source-reviewed.

Both directions are covered by the dry run: a pre-campaign mismatch and a
mid-campaign drift each abort and mark the campaign invalid.

---

## 3. Transport

Via `harness/transport.py` only:

- removes **only** `NO_PROXY` and `no_proxy` in the requesting process;
- preserves `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` unchanged;
- **fails closed** (exit 4) if any required proxy variable is absent — it never
  falls back to a direct loopback socket;
- never prints, archives or logs the bearer token; route evidence records the
  token as `<redacted>`;
- no unsandboxed retry, no wider allowlist, no new transport.

---

## 4. Execution plan

- Frozen grid `fixtures/simulation-grid-v1.0.json`: 53 configurations × 6
  candidate `N` = **318 segments**.
- Per-replication seed derived from
  `(master_seed, cell_id, N, replication, generator_version)`, so any single
  replication is regenerable in isolation.
- **Stage 1:** 500 replications. Evaluate. `PASS`/`FAIL` stop here.
- **Stage 2:** only `UNRESOLVED` segments escalate to 2,000 total.
- **Hard stop at 2,000.** No third stage, no outcome-dependent extension.
- Acceptance is asymmetric and stated on exact binomial bounds: `PASS` on the
  unadjusted one-sided 99% upper bound, `FAIL` on the Bonferroni-adjusted
  lower bound across 318 segments, `UNRESOLVED` otherwise.
- Four zero-tolerance events fail on a single occurrence rather than by rate:
  a zero-width decision-bearing interval, a pooled cross-light verdict, an C3
  disposition that is not a withholding, and degeneracy misrouted to
  `INFERENCE_ENGINE_FAILURE`.

---

## 5. Evidence retention (decision D1)

Per `(cell_id, N)` segment:

```
<slug>.requests.gz     concatenated gzip members, one per block
<slug>.responses.gz    same
<slug>.index.jsonl     one JSON line per replication
```

Every index line carries: coordinates, derived seed, timestamp, the campaign
target-identity digest, SHA-256 of the **raw** request and response bytes taken
before compression, raw lengths, the block's byte offset and length, the
record's offset and length within the block, the blocked flag and any error,
and the complete extracted decision record.

Block framing rather than per-record framing is used because responses within
a cell are highly redundant: measured **20.5×** compression as per-cell JSONL
versus 14.3× per record. The byte-offset index keeps any single record
independently retrievable regardless.

Projected: **≈0.55 GB** at stage 1, **≈2.19 GB** worst case at stage 2, with
every body retained verbatim. To be re-measured against the first completed
real cell, since the current figure comes from the sound reference as a size
proxy.

---

## 6. Checkpoint and resume

The invariant is that **the index is always a prefix of durable archive
content**, because archive blocks are written and `fsync`ed before their index
lines.

On resume, per segment:

1. parse index lines, stopping at the first malformed one (a torn trailing
   write);
2. drop any line whose archive extent exceeds the archive's real size;
3. truncate each archive back to the furthest extent still referenced;
4. treat the surviving replication set as complete; everything else is re-run.

A crash between an archive block write and its index lines therefore orphans
the block, which is discarded and re-run — **no duplication** (the reps were
never indexed) and **no omission** (they are re-executed). Completion is
asserted at the end against the full expected set, and a duplicate scan runs
over the index. On resume, event tallies are **recomputed from stored
evidence** rather than carried in memory, so a resumed segment produces the
same counts as an uninterrupted one.

---

## 7. Verdicts

| Verdict | Meaning | Engine result state |
|---|---|---|
| `PASS` | every gated event rate cleared its bound | contributes to `ENGINE_CANDIDATE_QUALIFIED` |
| `FAIL` | a gated rate exceeded its adjusted bound, or a zero-tolerance event fired | `ENGINE_REJECTED` |
| `UNRESOLVED` | still inconclusive at the hard stop | `ENGINE_NOT_YET_QUALIFIABLE` |
| `BLOCKED` | rejected input, unmappable schema, or transport error | `ENGINE_NOT_YET_QUALIFIABLE` |

A `BLOCKED` replication is still retained as evidence, with the harness error
recorded in place of the body and digest-verified like any other record. An
`UNRESOLVED` or `BLOCKED` segment is **never** silently treated as a pass, and
missing or duplicated replications force `EVIDENCE_INCOMPLETE`.

---

## 8. What the final report does not do

`results/campaign-report-v1.0.json` carries an explicit authorization note:

> This campaign result authorizes nothing further on its own.
> `ENGINE_CANDIDATE_QUALIFIED`, if reached, does not seal the apparatus, does
> not authorize ordinal-profile study execution, and does not authorize source review.
> Source review remains a separately authorized later phase bound to this exact
> target identity.

The runner has no code path that begins source review, and
`phase_gate_status()` reports `source_review_permitted: false`
unconditionally.

---

## 9. Operational verification

`python3 -m harness.cli dryrun` — **23/23 checks pass**, against the local
sound reference and local mutants, with **zero** real-engine scientific calls.
`harness/dryrun.py` never imports `harness.transport` and never constructs a
`BlackBoxTarget`, so that isolation holds by construction rather than by
discipline.

| Area | Checks |
|---|---|
| Retention | every replication stored; stored request is lossless and seed-reproducible; storage accounting reported |
| Indexing | byte-offset retrieval from both archives verifies against the recorded SHA-256 |
| Resume | a `KeyboardInterrupt` mid-block leaves a genuine partial segment; resume yields no duplication and no omission; all resumed evidence digest-verifies |
| Torn write | malformed trailing index line discarded; orphaned archive tail truncated; resume restores the full set |
| Identity | pre-campaign mismatch aborts; mid-campaign drift aborts; results marked unusable |
| Failure | a defective target yields `FAIL` and `ENGINE_REJECTED`; a zero-tolerance pooled verdict fails on one occurrence |
| Blocked | unmappable response yields `BLOCKED`, not a pass; blocked replications still retained |
| Unresolved | an under-powered segment reports `UNRESOLVED` honestly; the hard stop binds |

Two findings from building these tests, both fixed rather than worked around:

1. My first "interruption" test raised an ordinary `Exception`, which the
   campaign correctly classified as a *blocked replication* rather than a
   crash — so it never exercised resume at all. A target error and a process
   death are different events and must be tested differently; the test now
   raises `KeyboardInterrupt`.
2. My first failure test used a guard-promotion mutant whose defect is simply
   not observable at `N = 8` on the dry cells, so it produced no `FAIL` and
   tested nothing. It now uses mutants whose defect provably fires on the cells
   under test, confirmed by direct inspection before wiring the assertion.
