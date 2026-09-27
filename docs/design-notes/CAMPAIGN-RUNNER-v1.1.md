> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Campaign runner — v1.1

**Status:** implemented and operationally verified against the local sound
reference. **The real engine has not been contacted on any scientific
endpoint.**
**Supersedes:** `reports/CAMPAIGN-RUNNER-v1.0.md` (preserved, and the byte-exact
v1.0 release is preserved under `releases/v1.0/`).
**Implementation:** `harness/campaign.py`, `harness/sequential.py`,
`harness/batching.py`
**Operational tests:** `harness/dryrun.py` → `results/campaign-dryrun-v1.1.json`
— **49/49 checks pass**, zero real-engine scientific calls.

The five corrections and their statistical justification are in
`reports/SIMULATION-ACCEPTANCE-ADDENDUM-v1.1.md`. This document describes the
implementation.

---

## 1. Launch sequence

Order matters, and it is enforced:

```
1. phase gate          (frozen · self-qualified · approved · integrity · v1.1 approved)
2. --confirm required  (explicit operator action; exit 3 otherwise)
3. proxy construction  (fail closed; exit 4 if proxy variables absent)
4. RELEASE INTEGRITY   (recompute every artifact hash; abort before any request)
5. identity BEFORE     (GET /v0.1/meta; not a scientific call)
6. scientific requests (POST /v0.1/analyze-batch)
7. identity AFTER      (must equal the before digest)
```

Steps 4 and 5 both precede step 6, so an aborted launch makes **zero**
scientific calls. Exit codes: `0` valid, `2` gate closed, `3` confirmation
required, `4` proxy not configured, `5` aborted invalid.

---

## 2. Per-N result topology

States are reported per candidate `N`, and global rejection is reserved for
`N`-independent structural defects or rejection at every `N`. Full rule in the
addendum §2.

The report exposes `per_N`, `qualified_N`, `rejected_N`,
`n_independent_failures` and a plain-language `engine_result_reason`.

---

## 3. Decision rule

`harness/sequential.py`. The per-cell error budget is split across looks before
any data are seen; validity is by union bound over nested looks, with exactly
valid Clopper-Pearson bounds at each look. Decisions reduce to integer critical
values computed once per look, which is what makes the 150,000-replication
error-control demonstration tractable.

Both a two-look and a fixed-stage plan are implemented; the campaign records
which it used in `configuration.decision_plan`.

---

## 4. Batch and concurrency

`harness/batching.py`. 32 items per batch, 4 concurrent requests, both clamped.
Identity beats position; positional alignment is refused unless the response is
complete and id-free. Partial, malformed, misidentified, interrupted and
envelope-rejected batches each have a defined, tested behaviour that never
misattributes a response and never loses an item.

---

## 5. Retention, indexing and resume

Unchanged from v1.0 except that the stored request is now byte-identical to
what was **sent**, including the dispatch `analysis_id` — v1.0 regenerated the
payload for storage, which would have omitted it.

**Durability granularity, stated honestly:** results are written only once a
dispatch *wave* returns, and a wave is `batch_size × concurrency` items. An
interruption therefore loses at most one wave, which resume re-runs. This is
the one place where batching and durability trade against each other: larger
waves mean better throughput and coarser checkpoints. With the frozen limits a
wave is at most 128 replications out of 500 or 2,000.

The index-is-a-prefix-of-durable-archive invariant is unchanged, so resume
still cannot duplicate or omit.

---

## 6. Storage-only checkpoint

`--checkpoint-first-segment`. Runs exactly the first segment, withholds every
disposition, reports only storage and integrity facts, and leaves
`engine_result_state = NOT_ASSESSED`.

---

## 7. Operational verification — 49/49

| Area | Checks |
|---|---:|
| Retention and indexing | 4 |
| Resume | 4 |
| Torn writes | 3 |
| Identity | 3 |
| Failure and blocked | 4 |
| Unresolved and hard stop | 2 |
| **Per-N topology** | **5** |
| **Sequential error control** | **4** |
| **Batch item identity** | **10** |
| **Release integrity** | **4** |
| **Storage checkpoint** | **6** |

### Findings from building these tests

Four test designs were initially wrong in ways that would have produced false
confidence. All were fixed by correcting the test, never by weakening an
assertion:

1. **The per-N test used a cell that cannot vary.** `G1-C1-NULL-P0-1_2` places
   both compared cells at the same point mass, so its estimate is exactly 0.5
   on every replication and a deliberately narrowed interval never misses
   coverage. The test passed vacuously against a target it was supposed to
   catch. It now uses `G1-C1-NULL-P0-13_20`, whose estimate is genuinely
   stochastic — verified to produce non-coverage on 20/20 replications before
   the assertion was wired.
2. **A `PASS` was unreachable at the dry-run replication count.** At level 0.01
   against a 0.05 nominal, zero events only clear the bound at roughly 104
   replications; below that `pass_max = -1` and every segment is `UNRESOLVED`
   by construction, making the per-N distinction untestable. The per-N check
   now uses a single look at 110.
3. **The interruption test could not interrupt.** With the batch dispatcher, a
   whole wave is dispatched before anything is written, so a wave larger than
   the segment left nothing durable. The test now uses a small wave so several
   durable checkpoints precede the interruption — which also surfaced the
   durability-granularity property documented in §5.
4. **The blocked-evidence assertion looked for the wrong artifact.** An
   unmappable response is still a real response: v1.1 retains the body verbatim
   and records the failure alongside it, rather than replacing the body with an
   error stub. The assertion now checks for the body *and* the recorded error,
   which is the stronger property.

---

## 8. What this runner does not do

No code path begins source review; `phase_gate_status()` reports
`source_review_permitted: false` unconditionally. The campaign report carries
an explicit note that `ENGINE_CANDIDATE_QUALIFIED`, if reached, does not seal
the apparatus, authorize study execution, or authorize source review.

The gate additionally requires operator approval of the v1.1 addendum, so no
scientific request is possible until v1.1 has been reviewed and approved.
