> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Campaign runner — v1.2

**Status:** implemented and operationally verified against the local sound
reference. **The real engine has not been contacted on any scientific
endpoint. No storage checkpoint has been run.**
**Supersedes:** `CAMPAIGN-RUNNER-v1.1.md` (preserved; byte-exact v1.1 release
under `releases/v1.1/`).
**Operational tests:** `results/campaign-dryrun-v1.2.json` — **75/75**, zero
real-engine scientific calls.

Statistical justification is in `SIMULATION-ACCEPTANCE-ADDENDUM-v1.2.md`;
operating characteristics in `OPERATING-CHARACTERISTICS-v1.2.md`.

---

## 1. Launch order

```
1. phase gate      (frozen · self-qualified · approved · integrity · D6 valid)
2. --confirm       (explicit operator action; exit 3 otherwise)
3. D6 RESOLUTION   (exit 6 before any client is constructed)
4. transport       (fail closed; exit 4)
5. RELEASE INTEGRITY (recompute all hashes; abort before any request)
6. identity BEFORE (GET /v0.1/meta — identity, not scientific)
7. scientific requests
8. identity AFTER  (must equal the before digest)
```

Steps 3 and 5 both precede any request. D6 now resolves *before the transport
client exists*, so an absent, unknown or topology-inconsistent selection cannot
reach even the proxy layer.

Exit codes: `0` valid, `2` gate closed, `3` confirmation required, `4` proxy
not configured, `5` aborted invalid, `6` D6 not selected or inconsistent.

---

## 2. Inference topology

| Direction | Family | Per unit | Per look (2L) | Per look (FS) |
|---|---:|---|---:|---:|
| PASS | 0.01 | `0.01/6` per candidate `N` | 8.3333e-4 | 1.6667e-3 |
| FAIL | 0.01 | `0.01/318` per segment | 1.5723e-5 | 3.1447e-5 |

PASS divides across the six candidate `N` because qualification is a union of
selection opportunities; it does **not** divide across the 53 conjunctive
segments within an `N`, because qualification there is intersection-union.
FAIL divides across all 318 segments because a false accusation can arise at
any one of them.

Critical values, derived not hard-coded: two-look (10, 49) at 500 and (70, 144)
at 2,000; fixed-stage (72, 142) at 2,000.

---

## 3. D6 binding

Documented enum: **`corrected_two_look`**, **`corrected_fixed_stage`**. v1.1-era
values are deliberately rejected. `resolve_decision_plan` additionally
validates candidate count `== 6`, segment count `== 318`, and every PASS/FAIL
budget against the frozen topology; any mismatch raises and the caller refuses.

Every campaign report stamps twelve provenance fields: D6 plan, candidate
count, segment count, PASS family/per-candidate/per-look budgets, FAIL
family/per-segment/per-look budgets, approval-record digest, release digest,
plus the target identity digest.

---

## 4. Storage checkpoint and the blinding rule

The checkpoint runs exactly the first segment, withholds every disposition, and
leaves `engine_result_state: NOT_ASSESSED`.

**It does not make an early read impossible.** The retained archives contain
complete engine responses and could be decoded by hand. What protects the
campaign is the frozen blinding rule, embedded in every checkpoint report:

> Before the storage-based continuation decision is recorded, neither the
> operator, a coding agent, nor any reviewer may inspect, decode, summarize,
> search, or otherwise access the checkpoint's raw request/response archives.
> Only the checkpoint's storage, completeness, integrity, compression,
> identity, and provenance report may be reviewed. The continuation decision
> must be recorded before those archives may be used by the resumed campaign.

The report also carries an explicit `blinding_attestation` stating that this is
procedural, not technical.

---

## 5. Unchanged from v1.1

Per-`N` result topology; batch contract (32 items, 4 concurrent, identity beats
position); full compressed retention with per-response SHA-256 and byte-offset
index; crash-safe resume with the index-is-a-prefix invariant; pre-flight
integrity; nested-look union-bound validity.

Durability granularity remains one dispatch wave (`batch_size × concurrency`),
re-run on resume.

---

## 6. Operational verification — 75/75

| Area | Checks |
|---|---:|
| Retention and indexing | 4 |
| Resume | 4 |
| Torn writes | 3 |
| Identity | 3 |
| Failure and blocked | 4 |
| Unresolved and hard stop | 2 |
| Per-N topology | 5 |
| Sequential error control | 4 |
| **PASS/FAIL inference families** | **8** |
| **D6 binding** | **5** |
| Batch item identity | 10 |
| Release integrity | 4 |
| Storage checkpoint and blinding | 9 |
| **Operating-characteristic determinism** | **3** |
| **Snapshot verification** | **2** |
| **Zero-real-call proof** | **4** |

### Two test defects found and fixed while building these

1. A blinding-rule assertion searched for `"may not inspect"`; the frozen text
   reads `"neither … nor … may inspect"`. The test was wrong, not the rule.
2. The zero-real-call check grepped its own module for the string
   `"import transport"` — which appears in that very check's source as a
   literal, so it reported a false positive against itself. It now parses the
   module's AST and inspects real import nodes, and additionally asserts that
   `harness.transport` is absent from `sys.modules` during the run.

---

## 7. What this runner still does not do

No code path begins source review; the gate reports
`source_review_permitted: false` unconditionally. The campaign report states
that `ENGINE_CANDIDATE_QUALIFIED`, if ever reached, does not seal the
apparatus, authorize study execution, or authorize source review.

The gate requires operator approval of the v1.2 addendum **and** a valid D6
selection, so no scientific request is possible until both exist.
