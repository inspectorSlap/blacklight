> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Operational durability correction — v1.5.6

One defect. Operational only. Scientific core
`797b5d6bd3ad2d58fff202519e0994ab08579e5b5f7f81c78322955859d150ff` — 76 files,
zero drift from v1.4 through v1.5.5. v1.5.5 is preserved unchanged as a
frozen, unapproved candidate.

---

## 1. The defect

`_fsync_dir()` suppressed every `OSError`:

```python
try:
    os.fsync(fd)
except OSError:
    pass
```

Fsyncing a file makes its **contents** durable. It says nothing about whether
the **directory entry naming it** survives a crash. With the failure
suppressed, a spent-attestation marker, a run lock, a pre-spawn state file, a
provenance record or an abort record could all vanish on reboot while the code
believed them committed.

A vanished spent marker is the v1.5.3 failure returning by another route: an
attestation that authorized a launch, appearing unused.

## 2. Semantics

`_fsync_dir` raises `DurabilityError` (a subclass of `OSError`, so existing
pre-spawn handlers already catch it, while callers that care can distinguish
it). There is **no fallback treating unsupported directory fsync as success**.
On the APFS study host, inability to establish the promised durability is a
fail-closed condition, not a reason to lower the promise.

### Before any process exists

| Boundary | Behaviour | Exit |
|---|---|---|
| Run-lock creation | fail closed; attestation **not** reserved, stays unspent | 17 |
| After spent-marker creation | fail closed; attestation **permanently spent** | 17 |
| Pre-spawn state write | fail closed; attestation stays spent | 17 |
| Pre-spawn provenance write | fail closed; attestation stays spent | 17 |

No proxy or runner exists at any of these points.

**The spent marker is never rolled back.** If its directory fsync fails, the
marker still exists and the attestation is spent. Removing it to "clean up"
would hand a used attestation back to the next launch — exactly what v1.5.4
was built to prevent. The `O_EXCL` design and the append-only ledgers are
unchanged.

**The run lock is left in place.** Removing it risks a removal that is itself
not durable, and would expose the run identity to a concurrent launch at the
moment the filesystem is misbehaving. Leaving it is still recoverable without
manual intervention: the holder pid is dead, so the stale-lock path adopts it
on the next attempt. The disposition is recorded, not guessed at.

### After a process exists

Final state, final provenance, consumption bookkeeping and abort recording all
route through the existing abort handler: every process started by that launch
is terminated, the attestation remains spent, and the run is **never** reported
as successfully started. Exit 16.

### When the abort record itself cannot be made durable

This is the one place where writing nothing would be worse than writing
something undurable. `write_best_effort` writes the record and **reports** its
durability rather than assuming it:

```json
{"abort_record_written": true,
 "abort_record_durable": false,
 "abort_record_durability_error": "directory fsync failed for ...",
 "abort_record_caveat": "this abort record was written but could NOT be made
   durable. A crash could lose it. Do not treat its absence after a reboot as
   evidence that no launch was attempted."}
```

## 3. Evidence

`results/v1.5.6-integrated-faults.json`. Zero-network fault injection through
the real supervisor orchestration, injected at the lowest level — the real
`_fsync_dir` — so the failure arrives exactly where a filesystem fault would
and every layer above it is shipped code.

| Boundary | Exit | Spawned | Survivors | Spent | Abort record |
|---|---|---|---|---|---|
| run-lock creation | 17 | 0 | 0 | no | n/a |
| after spent-marker creation | 17 | 0 | 0 | **yes** | n/a |
| pre-spawn state | 17 | 0 | 0 | **yes** | durable |
| pre-spawn provenance | 17 | 0 | 0 | **yes** | durable |
| post-spawn final state | 16 | 2 | 0 | **yes** | durable |
| post-spawn final provenance | 16 | 2 | 0 | **yes** | durable |
| abort record write | 16 | 2 | 0 | **yes** | **UNKNOWN, reported** |

Target identity and analysis calls are zero in every case.

**Positive controls**, so the suite cannot pass by refusing everything:
directory fsync succeeds on the supported path; an unfaulted launch still
reaches exit 0 with both processes spawned; and the full integrated suite's
own positive control is retained.

**Suppression audit.** The module is parsed for bare `except: pass` handlers.
Three remain, each documented as not a durability claim: removing a scratch
probe file, appending to the human-readable `VOID.jsonl` (the authoritative
spent marker is already durable), and reaping a process that may not be our
child. A handler without such justification fails the test.

**No injection hook ships.** The seams are monkeypatches applied from the test
process; there is no flag, environment variable or configuration field.

## 4. Also corrected

The credential scan previously reported this test module's own source as a
leak, because it necessarily contains the synthetic placeholders it injects.
The placeholders are now assembled at runtime, so no source line holds the
literal. Live credentials are still scanned across everything **including
immutable snapshots**; historical placeholders inside snapshots published
before this change are excluded, because the alternative is rewriting history
or carrying a permanent false positive. A separate assertion proves no live
credential appears in any snapshot.
