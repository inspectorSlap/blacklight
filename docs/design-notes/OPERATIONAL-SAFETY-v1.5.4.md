> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Operational safety — v1.5.4

Operational only. v1.5.4 implements the transactional-launch and
attestation-reuse corrections from audit §§6.3–6.4. It changes nothing that
determines a scientific answer.

Scientific core `797b5d6bd3ad2d58fff202519e0994ab08579e5b5f7f81c78322955859d150ff`
— 76 files, byte-identical to v1.4, v1.5, v1.5.1, v1.5.2 and v1.5.3.

Machine-readable records: `results/v1.5.4-safety-controls.json`,
`results/scientific-invariance-v1.5.4.json`,
`results/change-classification-v1.5.4.json`. Counts are not restated in prose
here, so this document cannot drift out of step with them.

---

## 1. What v1.5.3 did

It spawned the runner, and *then* tried to consume the attestation, write run
state, and write provenance. The ledger was read-only, so the append raised —
with a campaign already executing.

The result: no state file, no provenance file, no durable record that the
launch had happened at all, and an attestation that had authorized a real
launch but appeared unused to every subsequent check. Recorded as
`PROV-DEV-007`.

## 2. Ordering

Everything that can fail now happens, and is fsynced, before any process
exists:

| | Step | Fails with |
|---|---|---|
| 1 | probe the ledger with a real append and a real fsync | exit 10 |
| 2 | select an attestation from three sources | exit 7 |
| 3 | acquire an exclusive run-identity lock | exit 11 |
| 4 | atomically reserve and **spend** the attestation | exit 12 |
| 5 | write minimal state and provenance durably | exit 13 |
| 6 | spawn the proxy | exit 14 |
| 7 | spawn the runner | exit 15 |
| 8 | post-spawn bookkeeping | exit 16 |

Steps 1–5 create no process. From step 6 onward, any failure terminates
everything that launch started and records why — steps 6–8 all route through
one abort handler, which is what v1.5.3 lacked.

The probe is a real append and a real fsync, not `os.access`. Permission bits
do not know about read-only mounts, full filesystems, immutable flags or ACLs.
A test parses the module and asserts no `os.access` or `os.stat` call exists.

## 3. Spending

An attestation is spent at **reservation**, by creating
`runtime-attestations/spent/<id>` with `O_EXCL` — atomic on POSIX, so two
concurrent launches cannot both win and the winner is unambiguous. The
human-readable `VOID.jsonl` is written alongside but is deliberately *not* the
authority: a JSONL append is not atomic and must not be load-bearing for a
safety property. That is exactly the mistake v1.5.3 made.

**A failed launch does not give the attestation back.** That is deliberate. An
attestation records that a proxy was qualified for one specific run; a launch
that got far enough to fail has already consumed that. Recovery is a new
qualification run, which costs one Terminal command and is the correct price.

There is no force flag, no environment escape, and no recovery path that
un-spends one. A test greps for them.

## 4. Three sources, not one

`CONSUMED.jsonl` alone is what v1.5.3 relied on, and a failed append defeated
it. Selection now consults:

1. the consumed ledger;
2. the durable spent/void set, including the permanent void list;
3. the run identities that already have operational artifacts on disk.

The third is the backstop and needs no ledger at all: a launch that produced a
runner log used an attestation, whatever any ledger says.

If the safety module cannot be imported, selection raises rather than falling
back to the ledger alone.

**Resume is exempted from the third check only.** A resumed run necessarily
has artifacts — that is what is being resumed. It still needs its own
unspent attestation.

## 5. `rta-0027-20260921T113621Z`

Permanently void, tied to `PROV-DEV-007`. It authorized the failed v1.5.3
launch; the runner was spawned and ran; the ledger append failed, so it never
reached `CONSUMED.jsonl`.

It is refused **with every binding field deliberately matched, including the
host fingerprint**. This matters: in the development sandbox it was previously
refused only because the host fingerprint differed there, which is an
environmental accident and not a control. On the operator's own host it would
have authorized a second launch. It is now refused three times over — the void
list, the artifact backstop on `campaign-v1.5.3-run-001`, and the reservation
primitive.

Neither the attestation file nor the read-only ledger was rewritten.

## 6. A defect this work found

`_alive()` used `kill(pid, 0)`, which **succeeds on a zombie**. A child that
had been terminated but not reaped therefore read as a live orphan, so the
abort path would have reported failure on every successful cleanup — and, worse,
would have escalated to `SIGKILL` against a process that was already dead while
believing it had failed.

Found by the fault-injection tests, which reported orphans after every
injected failure. `terminate_all` now reaps.

## 7. What was deliberately not done

`harness/adapter.py` is untouched, and a test asserts it is byte-identical to
the v1.5.3 snapshot. The approved `bool(v)` correction at line 343 is folded
into the combined versioned output-contract release as a deliberate
scientific-core change, per decision record v0.3. It remains
**campaign-blocking** until that release passes the complete structural
compatibility gate.

Also unchanged: the scientific decision logic, the oracle, expected answers,
scenarios, candidate-N materials, D6, statistical thresholds and critical
values, the target engine, and the output-contract implementation.

## 8. Evidence

`results/v1.5.4-safety-controls.json` — eleven adversarial tests by fault
injection.

Refusals: read-only ledger, unwritable directory, duplicate reservation, the
permanently void attestation, a lock held by a live process, a run identity
with existing artifacts, a foreign run-id resume.

Positive counterparts, because a gate that refuses everything passes every
refusal test: a writable ledger probes clean, a free identity locks, a clean
attestation reserves, a stale lock is adopted with the adoption recorded, and
resume is *not* blocked by its own artifacts.

Fault injection at four stages, each asserting no orphan process, a durable
abort record, a released lock, and an attestation that stays spent.

No proxy was started against the gateway, no identity call, no analysis call,
no campaign, no checkpoint. Helper processes are local `sleep` invocations that
cannot reach the target and are reaped before the suite returns.
