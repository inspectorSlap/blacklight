"""Transactional launch ordering and attestation-reuse controls (v1.5.4).

WHY THIS EXISTS
---------------
The v1.5.3 launch spawned the runner and only afterwards tried to consume the
attestation, write run state, and write provenance. The ledger was read-only,
so the append raised -- and by then the runner was already executing. The run
left no durable record of itself, and the attestation it had used stayed absent
from the ledger, which means the gate would happily hand it to a second launch.

Two defects, one fix each:

* **ordering** -- everything that can fail is done, and made durable, before
  any process exists. Nothing is spawned until the transaction has committed.
* **reuse** -- an attestation is spent by an atomic filesystem operation at
  reservation time, not by an append after the fact. A launch that fails later
  does not give it back. That is deliberate: an attestation records that a
  proxy was qualified for a specific run, and a failed launch has already
  consumed that evidence's usefulness.

WHAT SPENDING MEANS
-------------------
`spent/<attestation_id>` created with `O_EXCL`. On POSIX that is atomic: two
concurrent launches cannot both succeed, and the winner is unambiguous. The
human-readable `VOID.jsonl` is written alongside for the record, but the
directory entry is the authority -- a JSONL append is not atomic and must not
be load-bearing for a safety property.

THREE SOURCES ARE CONSULTED, NOT ONE
------------------------------------
`CONSUMED.jsonl` alone is what failed in v1.5.3. Selection now also consults
the durable spent/void set, and the set of run identities that already have
operational artifacts on disk. The third is the backstop: a launch that
produced a runner log used an attestation, whatever any ledger says.

NO FORCE PATH
-------------
There is deliberately no flag, environment variable or recovery path that
un-spends an attestation. Recovery from a failed launch is a new attestation,
which costs one qualification run and is the correct price.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import datetime
import errno
import hashlib
import json
import os
import re
import signal
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
ATTESTATION_DIR = os.path.join(RESULTS, "runtime-attestations")
SPENT_DIR = os.path.join(ATTESTATION_DIR, "spent")
VOID_LEDGER = os.path.join(ATTESTATION_DIR, "VOID.jsonl")

# The authoritative, crash-durable record that an attestation is spent.
#
# v1.5.6 treated the O_EXCL marker as the spend authority. A marker is a NEW
# directory entry, so its durability depends on a directory fsync -- and when
# that fsync failed, v1.5.6 still called the attestation "permanently spent"
# while explicitly knowing the marker might not survive a reboot. After a
# crash the marker and the released lock could both be gone, and nothing
# authoritative would remain to stop the attestation being selected again.
#
# This ledger closes that hole. It is created and its directory entry made
# durable BEFORE any launch appends to it, so an append to an already-existing
# file plus fsync(file) is durable on its own -- no directory fsync is needed
# at spend time, because no new directory entry is created. That is the whole
# reason the ordering works.
SPEND_LEDGER = os.path.join(ATTESTATION_DIR, "SPEND.jsonl")

RECORD_SPEND = "attestation_spend"
LOCK_DIR = os.path.join(RESULTS, "run-locks")

# Permanently void, tied to a deviation record. These are refused regardless
# of host, ledger state, or anything else.
PERMANENT_VOID = {
    "rta-0027-20260921T113621Z": {
        "reason": "authorized the failed campaign-v1.5.3-run-001 launch. The "
                  "runner was spawned and ran; the ledger append failed, so "
                  "it never reached CONSUMED.jsonl.",
        "deviation": "PROV-DEV-007",
        "record": "releases/deviations/campaign-v1.5.3-run-001/"
                  "DEVIATION-RECORD.json",
        "must_be_refused_on_original_host": True,
    },
}


class LaunchAborted(Exception):
    """Raised instead of proceeding past a failed transactional step."""


class DurabilityError(OSError):
    """The promised durability could not be established.

    Raised when a directory fsync fails. Subclasses OSError so existing
    pre-spawn write handlers already catch it, while callers that care can
    distinguish it and report honestly.

    WHY THIS IS NOT BEST-EFFORT
    ---------------------------
    Up to v1.5.5 `_fsync_dir` swallowed every OSError. fsyncing a file makes
    its CONTENTS durable; it says nothing about whether the directory entry
    naming it survives a crash. A spent-attestation marker, a run lock, a
    pre-spawn state file, a provenance record or an abort record could all
    vanish on reboot while the code believed them committed -- and a vanished
    spent marker is precisely the v1.5.3 failure mode returning by another
    route.

    Directory fsync is supported on the APFS study host. There is deliberately
    no fallback that treats "unsupported" as success: on this host, inability
    to establish the promised durability is a fail-closed condition, not a
    reason to lower the promise.
    """


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _fsync_dir(path):
    """Make a directory ENTRY durable, not just the named file's contents.

    Raises DurabilityError on any failure. Never suppresses.
    """
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise DurabilityError(
            "could not open directory %s to fsync it: %s" % (path, exc))
    try:
        os.fsync(fd)
    except OSError as exc:
        raise DurabilityError(
            "directory fsync failed for %s: %s. The file's contents may be "
            "durable while the directory entry naming it is not, so a crash "
            "could lose the record entirely. This is a fail-closed condition "
            "on the study host." % (path, exc))
    finally:
        os.close(fd)


def durable_write(path, payload):
    """Write, flush, fsync the file, then fsync its directory.

    Raises DurabilityError if either fsync fails. The file may exist on disk
    when this raises -- that is the honest situation, and callers report it as
    "written, durability unknown" rather than deleting evidence of what
    happened.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w") as handle:
        handle.write(payload)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError as exc:
            raise DurabilityError("file fsync failed for %s: %s"
                                  % (path, exc))
    if directory:
        _fsync_dir(directory)


def write_best_effort(path, payload):
    """Write and report durability honestly instead of raising.

    Used only where the alternative to an undurable record is NO record --
    the abort path. Returns a dict stating exactly what was achieved.
    """
    try:
        durable_write(path, payload)
        return {"written": True, "durable": True, "durability_error": None}
    except DurabilityError as exc:
        return {"written": os.path.isfile(path), "durable": False,
                "durability_error": str(exc)[:300]}
    except OSError as exc:
        return {"written": os.path.isfile(path), "durable": False,
                "durability_error": "%s: %s" % (type(exc).__name__,
                                                str(exc)[:200])}


# ---------------------------------------------------------------------------
# 1. ledger writability -- an actual probe, not a permission inspection
# ---------------------------------------------------------------------------

def probe_ledger_writable(ledger_path=None, attestation_dir=None,
                          launch=None):
    """Append a real, typed provenance record to the real ledger and fsync it.

    v1.5.4 opened the ledger, flushed and fsynced without writing bytes. That
    proves the file can be OPENED; it does not prove an append can succeed. A
    filesystem that is full, a quota that is exhausted, or an append-blocking
    ACL all pass the open and fail the write -- which is the operation that
    actually matters, because consumption is an append.

    So the probe appends. The record it appends:

      * declares record_type = ledger_writability_probe, so consumption
        readers skip it;
      * carries NO attestation identifier, so it cannot be read as marking
        anything consumed even by a reader that ignores record_type;
      * carries no credential or secret;
      * is retained. The ledger is append-only; removing the probe would mean
        rewriting history to prove that history can be written.

    This is ADDITIONAL evidence. The atomic spent-marker remains the control
    that prevents reuse; a probe record is not a reservation and grants
    nothing.
    """
    ledger_path = ledger_path or os.path.join(ATTESTATION_DIR,
                                              "CONSUMED.jsonl")
    attestation_dir = attestation_dir or os.path.dirname(ledger_path)
    findings = []
    probe_record = None

    if not os.path.isdir(attestation_dir):
        return {"writable": False, "probe_record": None, "checks": [
            {"check": "attestation directory exists", "ok": False,
             "detail": attestation_dir}]}

    # (a) a REAL append of a REAL record, fsynced.
    # The authoritative spend ledger must exist durably before any launch
    # appends to it. Established here, in the step that already fails closed.
    try:
        spend_ledger = ensure_spend_ledger()
        findings.append({"check": "spend ledger exists and is durable",
                         "ok": True, "detail": spend_ledger["path"]})
    except (DurabilityError, OSError) as exc:
        findings.append({"check": "spend ledger exists and is durable",
                         "ok": False,
                         "detail": "%s: %s" % (type(exc).__name__, exc)})
        return {"writable": False, "probe_record": None, "checks": findings,
                "ledger": os.path.relpath(ledger_path, ROOT)}

    probe_record = {
        "record_type": "ledger_writability_probe",
        "probe_utc": utc(),
        "probe_id": "probe-%s-%d" % (
            datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ"), os.getpid()),
        "pid": os.getpid(),
        "purpose": "prove the consumption ledger accepts a durable append "
                   "before any process is spawned",
        "grants_nothing": True,
        "is_consumption_record": False,
        "attestation_id": None,
        "secrets_recorded": False,
    }
    if launch:
        probe_record["run_id"] = launch.get("run_id")
        probe_record["release_digest"] = launch.get("release_digest")
    try:
        with open(ledger_path, "a") as handle:
            handle.write(_canon(probe_record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(attestation_dir)
        findings.append({"check": "ledger accepts a durable append",
                         "ok": True,
                         "detail": "typed probe record appended and fsynced"})
    except OSError as exc:
        findings.append({"check": "ledger accepts a durable append",
                         "ok": False,
                         "detail": "%s: %s" % (type(exc).__name__, exc)})
        probe_record = None

    # (b) read it back, to prove the bytes landed and parse.
    if probe_record is not None:
        try:
            found = False
            with open(ledger_path, "r") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if entry.get("probe_id") == probe_record["probe_id"]:
                        found = True
            findings.append({"check": "the appended record reads back",
                             "ok": found,
                             "detail": "probe located by probe_id" if found
                                       else "probe not found after append"})
        except OSError as exc:
            findings.append({"check": "the appended record reads back",
                             "ok": False,
                             "detail": "%s: %s" % (type(exc).__name__, exc)})

    # (c) the directory must accept a new durable file, which is what
    #     reservation needs. Written, fsynced, read back, removed.
    probe = os.path.join(attestation_dir, ".writability-probe")
    token = "probe-%s" % time.time()
    try:
        durable_write(probe, token)
        with open(probe, "r") as handle:
            observed = handle.read()
        os.remove(probe)
        ok = observed == token
        findings.append({"check": "directory accepts a durable new file",
                         "ok": ok,
                         "detail": "written, fsynced, read back, removed"
                                   if ok else "read-back mismatch"})
    except OSError as exc:
        findings.append({"check": "directory accepts a durable new file",
                         "ok": False,
                         "detail": "%s: %s" % (type(exc).__name__, exc)})
        # Removing a scratch probe file. Failing to delete a temporary file
        # is not a durability claim about any record, so it is suppressed.
        if os.path.exists(probe):
            try:
                os.remove(probe)
            except OSError:
                pass

    return {"writable": all(f["ok"] for f in findings), "checks": findings,
            "ledger": os.path.relpath(ledger_path, ROOT),
            "probe_record": probe_record,
            "probe_retained": probe_record is not None,
            "method": "real typed append and real fsync against the exact "
                      "consumption ledger; not os.access(), not a zero-byte "
                      "open"}


# ---------------------------------------------------------------------------
# 2. atomic reservation / spending
# ---------------------------------------------------------------------------

def ensure_spend_ledger(path=None):
    """Create the spend ledger and make its directory entry durable.

    Called during the pre-launch probe, which already fails closed. Once this
    returns, the file exists durably and every later append is durable by
    fsyncing the file alone.
    """
    path = path or SPEND_LEDGER
    directory = os.path.dirname(path)
    created = False
    if not os.path.isfile(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        created = True
    # Durable either way: on first creation this commits the new entry, and
    # afterwards it is a cheap no-op that still proves the directory is sound.
    _fsync_dir(directory)
    return {"path": os.path.relpath(path, ROOT), "created": created,
            "exists": os.path.isfile(path), "directory_entry_durable": True}


def record_spend(attestation_id, launch, path=None):
    """Durably record that an attestation is spent. THE authority.

    Appends to an already-durable file and fsyncs it. No directory entry is
    created, so no directory fsync is required and the record survives a crash
    the moment this returns.

    Raises DurabilityError if the append or fsync fails, in which case the
    caller must NOT create a marker, must NOT spawn anything, and must NOT
    claim the attestation was spent.
    """
    path = path or SPEND_LEDGER
    if not os.path.isfile(path):
        raise DurabilityError(
            "the spend ledger %s does not exist; it must be created and made "
            "durable before any launch appends to it" % path)

    record = {
        "record_type": RECORD_SPEND,
        "attestation_id": attestation_id,
        "run_id": launch.get("run_id"),
        "release_digest": launch.get("release_digest"),
        "approval_digest": launch.get("approval_digest"),
        "attestation_content_digest": launch.get("content_digest"),
        "spent_utc": utc(),
        "pid": os.getpid(),
        "permanently_spent": True,
        "authority": "this record is the authoritative point at which the "
                     "attestation becomes permanently spent. It remains spent "
                     "even if marker creation, or any later launch step, "
                     "fails.",
        "reversible": False,
        "secrets_recorded": False,
    }
    # Never append a record this ledger's own reader would reject. An
    # authoritative ledger that contains an invalid record becomes
    # uninterpretable, which would lock out every future launch -- a
    # self-inflicted denial of service written by the very code that depends
    # on the ledger being readable.
    errors = validate_spend_record(record)
    if errors:
        raise DurabilityError(
            "refusing to append an invalid spend record for %s (%s). Writing "
            "it would make the authoritative ledger uninterpretable and block "
            "every future launch." % (attestation_id, ", ".join(errors)))

    try:
        with open(path, "a") as handle:
            handle.write(_canon(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise DurabilityError(
            "could not durably append the authoritative spend record for %s: "
            "%s. The attestation is NOT claimed spent, no marker was created "
            "and nothing was started." % (attestation_id, exc))
    return record


# Required fields on a valid attestation_spend record, with the constant each
# must equal where one is required. A record that merely carries an
# attestation identifier is NOT valid.
SPEND_REQUIRED_NONEMPTY = ("attestation_id", "run_id", "release_digest",
                           "approval_digest", "attestation_content_digest",
                           "spent_utc")
SPEND_REQUIRED_EXACT = {"record_type": RECORD_SPEND,
                        "permanently_spent": True,
                        "reversible": False,
                        "secrets_recorded": False}
# Fields that must agree across duplicate records for the same attestation.
SPEND_CONSISTENCY_FIELDS = ("run_id", "release_digest", "approval_digest",
                            "attestation_content_digest")


def _safe_type_name(value, limit=48):
    """A record-type name reduced to identifier characters and capped.

    Reports must name the unexpected type, but a type name is attacker-
    adjacent text. Restricting it to an identifier shape and a fixed length
    means naming it cannot become a channel for copying ledger payload.
    """
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", value)[:limit]
    return cleaned or "<unnameable>"


def validate_spend_record(entry):
    """Structural error codes for one record. Empty list means valid.

    Deliberately returns CODES, never the record's contents: this feeds a
    report that must not echo ledger payloads.
    """
    errors = []
    if not isinstance(entry, dict):
        return ["NOT_AN_OBJECT"]
    for field, expected in sorted(SPEND_REQUIRED_EXACT.items()):
        if field not in entry:
            errors.append("MISSING_%s" % field.upper())
        elif entry[field] != expected:
            errors.append("BAD_%s" % field.upper())
    for field in SPEND_REQUIRED_NONEMPTY:
        value = entry.get(field)
        if field not in entry:
            errors.append("MISSING_%s" % field.upper())
        elif not isinstance(value, str) or not value.strip():
            errors.append("EMPTY_%s" % field.upper())
    return sorted(set(errors))


def spend_records(path=None):
    """Read the authoritative ledger, FAILING CLOSED on any ambiguity.

    v1.5.7 made this ledger authoritative but only *reported* malformed lines
    and unknown record types, so an unreadable spend record read as "not
    spent" -- exactly the inversion an authoritative source must never make.
    Once a source decides whether an attestation may be reused, ambiguity in
    it is not absence of a spend; it is inability to tell, and inability to
    tell must block.

    Returns a verdict. `interpretable` is the only field a caller may act on
    to authorize anything. Diagnostics carry line numbers and error codes and
    never the offending text.
    """
    path = path or SPEND_LEDGER
    verdict = {
        "ledger_path": os.path.relpath(path, ROOT),
        "present": False,
        "readable": False,
        "interpretable": False,
        "valid_spend_records": 0,
        "spent": {},
        "malformed_lines": [],
        "unknown_record_types": [],
        "structural_errors": [],
        "contradictions": [],
        "reason": None,
        "raw_payload_copied": False,
    }

    if not os.path.isfile(path):
        verdict["reason"] = "SPEND_LEDGER_MISSING"
        return verdict
    verdict["present"] = True

    try:
        with open(path, "r") as handle:
            lines = handle.readlines()
    except OSError as exc:
        verdict["reason"] = "SPEND_LEDGER_UNREADABLE"
        verdict["read_error"] = type(exc).__name__
        return verdict
    verdict["readable"] = True

    first_seen = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            verdict["malformed_lines"].append({"line": number,
                                               "error": "INVALID_JSON"})
            continue
        if not isinstance(entry, dict):
            verdict["malformed_lines"].append({"line": number,
                                               "error": "NOT_AN_OBJECT"})
            continue

        kind = entry.get("record_type")
        if kind != RECORD_SPEND:
            # A probe or legacy consumption record is valid in ITS ledger.
            # Here it is an unexpected type, and an unexpected type in an
            # authoritative ledger cannot be assumed harmless.
            # The type NAME is reported because a reader needs to know what
            # turned up. It is sanitized first: a record type is an
            # identifier, so anything outside that shape is not a name and
            # must not be copied through into a report verbatim.
            verdict["unknown_record_types"].append(
                {"line": number,
                 "record_type": _safe_type_name(kind),
                 "error": "UNEXPECTED_RECORD_TYPE"})
            continue

        errors = validate_spend_record(entry)
        if errors:
            verdict["structural_errors"].append({"line": number,
                                                 "errors": errors})
            continue

        identity = entry["attestation_id"]
        if identity in first_seen:
            previous = first_seen[identity]
            differing = [f for f in SPEND_CONSISTENCY_FIELDS
                         if entry.get(f) != previous["entry"].get(f)]
            if differing:
                verdict["contradictions"].append(
                    {"line": number, "first_seen_line": previous["line"],
                     "differing_fields": sorted(differing),
                     "error": "CONTRADICTORY_DUPLICATE"})
                continue
            # Consistent duplicate: append-only, collapses to one identity.
            continue
        first_seen[identity] = {"line": number, "entry": entry}
        verdict["spent"][identity] = entry

    verdict["valid_spend_records"] = len(verdict["spent"])

    problems = []
    if verdict["malformed_lines"]:
        problems.append("%d malformed line(s)" % len(verdict["malformed_lines"]))
    if verdict["unknown_record_types"]:
        problems.append("%d unexpected record type(s)"
                        % len(verdict["unknown_record_types"]))
    if verdict["structural_errors"]:
        problems.append("%d structurally invalid spend record(s)"
                        % len(verdict["structural_errors"]))
    if verdict["contradictions"]:
        problems.append("%d contradictory duplicate(s)"
                        % len(verdict["contradictions"]))

    if problems:
        verdict["reason"] = "SPEND_LEDGER_UNINTERPRETABLE"
        verdict["reason_detail"] = ("; ".join(problems) +
                                    ". An unreadable record in the "
                                    "authoritative ledger may be a spend "
                                    "record, so it cannot be treated as "
                                    "absence of a spend.")
        return verdict

    # An existing, readable, well-formed ledger is interpretable even when it
    # is empty -- an empty ledger says "nothing is spent", which is a fact,
    # not an ambiguity.
    verdict["interpretable"] = True
    verdict["reason"] = "OK"
    return verdict


def spent_ids():
    """Every attestation that may never be used again.

    Union of the permanent void list, the authoritative spend ledger, and the
    O_EXCL markers. The ledger is the crash-durable authority; the markers
    remain the atomic concurrency control.
    """
    spent = dict(PERMANENT_VOID)
    verdict = spend_records()
    # Only an interpretable ledger contributes. An uninterpretable one is
    # handled by the caller as a refusal to authorize anything at all -- it
    # must never silently contribute an empty set, which would read as
    # "nothing is spent".
    if verdict["interpretable"]:
        for identity, entry in verdict["spent"].items():
            spent.setdefault(identity, dict(entry,
                                            source="authoritative spend "
                                                   "ledger (crash-durable)"))
    if os.path.isdir(SPENT_DIR):
        for name in sorted(os.listdir(SPENT_DIR)):
            if name.startswith("."):
                continue
            path = os.path.join(SPENT_DIR, name)
            try:
                with open(path, "r") as handle:
                    entry = json.load(handle)
            except (OSError, ValueError):
                entry = {"reason": "spent marker present but unreadable; "
                                   "treated as spent"}
            spent.setdefault(name, entry)
    return spent


def reserve(attestation_id, launch):
    """Atomically and permanently spend an attestation. No un-spend exists.

    Returns the marker path. Raises LaunchAborted if it is already spent,
    which includes losing a race with a concurrent launch.
    """
    if attestation_id in PERMANENT_VOID:
        raise LaunchAborted(
            "attestation %s is permanently void (%s): %s"
            % (attestation_id, PERMANENT_VOID[attestation_id]["deviation"],
               PERMANENT_VOID[attestation_id]["reason"]))

    if not os.path.isdir(SPENT_DIR):
        os.makedirs(SPENT_DIR)

    marker = os.path.join(SPENT_DIR, attestation_id)
    entry = dict(launch)
    entry.update({"attestation_id": attestation_id, "spent_utc": utc(),
                  "pid": os.getpid(),
                  "note": "spent at reservation, before any process was "
                          "spawned. A failed launch does not return it."})
    payload = json.dumps(entry, indent=2, sort_keys=True) + "\n"

    # O_EXCL is the atomic primitive. Two launches cannot both create it.
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        try:
            with open(marker, "r") as handle:
                previous = json.load(handle)
        except (OSError, ValueError):
            previous = {}
        raise LaunchAborted(
            "attestation %s is already spent (at %s by pid %s); each "
            "attestation authorizes exactly one launch and there is no way "
            "to un-spend it"
            % (attestation_id, previous.get("spent_utc", "unknown"),
               previous.get("pid", "unknown")))
    except OSError as exc:
        raise LaunchAborted("could not reserve attestation %s: %s"
                            % (attestation_id, exc))

    with os.fdopen(fd, "w") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

    # The marker now EXISTS. If the directory fsync fails, the attestation is
    # spent regardless: the marker is not removed, not rolled back and not
    # reusable. Removing it to "clean up" would hand a used attestation back
    # to the next launch, which is the exact failure v1.5.4 was built to
    # prevent. The launch fails closed; the attestation stays spent.
    try:
        _fsync_dir(SPENT_DIR)
    except DurabilityError as exc:
        raise DurabilityError(
            "attestation %s is SPENT -- the marker was created and is not "
            "rolled back -- but its directory entry could not be made "
            "durable: %s" % (attestation_id, exc))

    # Human-readable record. Deliberately NOT the authority: a JSONL append
    # is not atomic, so a safety property must not rest on it. The spent
    # marker above is the authority and has already been made durable, so a
    # failure here loses readability, not safety -- it is not a durability
    # claim about whether the attestation is spent.
    try:
        with open(VOID_LEDGER, "a") as handle:
            handle.write(_canon(entry) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        pass

    return marker


# ---------------------------------------------------------------------------
# 3. run identities implied by artifacts on disk
# ---------------------------------------------------------------------------

ARTIFACT_PATTERNS = (
    ("runner log", re.compile(r"^campaign-runner-v(?P<v>[\d.]+)\.log$")),
    ("proxy log", re.compile(r"^campaign-proxy-v(?P<v>[\d.]+)\.log$")),
    ("proxy audit", re.compile(r"^proxy-audit-v(?P<v>[\d.]+)\.jsonl$")),
    ("run state", re.compile(r"^campaign-run-state-v(?P<v>[\d.]+)\.json$")),
    ("provenance", re.compile(r"^campaign-provenance-v(?P<v>[\d.]+)\.json$")),
    ("evidence directory",
     re.compile(r"^campaign-evidence-v(?P<v>[\d.]+)$")),
    ("campaign report",
     re.compile(r"^campaign-report(?:-checkpoint)?-v(?P<v>[\d.]+)\.json$")),
)


def artifact_associated_versions(results=None):
    """Release versions that already have operational artifacts on disk.

    The backstop for the v1.5.3 failure mode: a launch that produced a runner
    log used an attestation, whatever the ledgers say.
    """
    results = results or RESULTS
    found = {}
    if not os.path.isdir(results):
        return found
    for name in sorted(os.listdir(results)):
        path = os.path.join(results, name)
        for label, pattern in ARTIFACT_PATTERNS:
            match = pattern.match(name)
            if not match:
                continue
            if label == "evidence directory":
                if not os.path.isdir(path) or not os.listdir(path):
                    continue
            elif not os.path.isfile(path) or os.path.getsize(path) == 0:
                continue
            found.setdefault(match.group("v"), []).append(
                {"artifact": label, "path": os.path.relpath(path, ROOT)})
    return found


def run_ids_with_artifacts(results=None):
    """Map run identities to the artifacts implying they were launched."""
    out = {}
    for version, artifacts in artifact_associated_versions(results).items():
        for run_id in ("campaign-v%s-run-001" % version,
                       "checkpoint-v%s-run-001" % version):
            out[run_id] = artifacts
    return out


# ---------------------------------------------------------------------------
# 4. exclusive run-identity lock
# ---------------------------------------------------------------------------

def _reap(pid):
    """Reap `pid` if it is our child. Harmless if it is not.

    Without this, a child we have just terminated stays a zombie and
    `kill(pid, 0)` keeps succeeding -- so a correctly terminated process reads
    as a live orphan. That would make the abort path report failure on every
    successful cleanup.
    """
    # Reaping a process that is not our child, or is already reaped, is
    # expected and harmless. This is not a durability claim about any record.
    try:
        os.waitpid(int(pid), os.WNOHANG)
    except (ChildProcessError, OSError):
        pass


def _alive(pid):
    """Whether `pid` is a live process, not a zombie awaiting reaping."""
    if not pid:
        return False
    _reap(pid)
    try:
        os.kill(int(pid), 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


class RunIdentityLock(object):
    """Exclusive for the run's lifetime. Acquired before anything is spawned.

    A stale lock -- one whose holder is gone -- is adopted rather than
    refused, with the adoption recorded. Refusing it would make a machine
    reboot require manual intervention; adopting it silently would hide a
    crash.
    """

    def __init__(self, run_id, lock_dir=None):
        self.run_id = run_id
        self.lock_dir = lock_dir or LOCK_DIR
        self.path = os.path.join(self.lock_dir, run_id + ".lock")
        self.acquired = False
        self.adopted_stale = None
        self.durability_error = None
        self.disposition = "not acquired"

    def acquire(self):
        if not os.path.isdir(self.lock_dir):
            os.makedirs(self.lock_dir)
        payload = json.dumps({"run_id": self.run_id, "pid": os.getpid(),
                              "acquired_utc": utc()},
                             indent=2, sort_keys=True) + "\n"
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            try:
                with open(self.path, "r") as handle:
                    holder = json.load(handle)
            except (OSError, ValueError):
                holder = {}
            if _alive(holder.get("pid")):
                raise LaunchAborted(
                    "run identity %s is locked by live pid %s since %s; a "
                    "concurrent launch is already in progress"
                    % (self.run_id, holder.get("pid"),
                       holder.get("acquired_utc")))
            self.adopted_stale = holder
            os.remove(self.path)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # Safest recoverable state on a durability failure: LEAVE the lock.
        #
        # Removing it risks a removal that is itself not durable, and would
        # open the identity to a concurrent launch at the very moment the
        # filesystem is misbehaving. Leaving it blocks further launches, and
        # is still recoverable without manual intervention: the holder pid is
        # dead, so the stale-lock path adopts it on the next attempt. The
        # disposition is recorded rather than guessed at.
        try:
            _fsync_dir(self.lock_dir)
        except DurabilityError as exc:
            self.acquired = True          # it exists; we own it
            self.durability_error = str(exc)[:300]
            self.disposition = ("lock file created and LEFT IN PLACE; its "
                                "directory entry could not be made durable. "
                                "Not removed: a non-durable removal during a "
                                "filesystem fault would expose the run "
                                "identity to a concurrent launch. The holder "
                                "pid is dead after this failure, so the "
                                "stale-lock path can adopt it.")
            raise DurabilityError("%s (%s)" % (exc, self.disposition))

        self.acquired = True
        self.disposition = "held"
        return self

    def release(self):
        if self.acquired and os.path.exists(self.path):
            os.remove(self.path)
            self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        return False       # held for the run's lifetime; not auto-released


# ---------------------------------------------------------------------------
# 5. the transaction
# ---------------------------------------------------------------------------

class LaunchTransaction(object):
    """Ordered, durable, and self-cleaning.

    Every step that can fail happens before any process exists. Once
    processes do exist, any later failure terminates all of them and records
    why -- a half-started launch is worse than no launch.
    """

    def __init__(self, run_id, record_path):
        self.run_id = run_id
        self.record_path = record_path
        self.steps = []
        self.processes = []
        self.lock = None
        self.reservation = None
        self.aborted = False
        self.abort_record = None
        self.spend_record = None

    def step(self, name, ok, detail, **extra):
        entry = dict({"step": len(self.steps) + 1, "name": name,
                      "ok": bool(ok), "detail": detail, "utc": utc()}, **extra)
        self.steps.append(entry)
        if not ok:
            raise LaunchAborted("%s: %s" % (name, detail))
        return entry

    def register_process(self, label, pid):
        self.processes.append({"label": label, "pid": pid})

    def terminate_all(self):
        """Terminate every process this launch started."""
        stopped = []
        for entry in self.processes:
            pid = entry["pid"]
            if not _alive(pid):
                stopped.append(dict(entry, outcome="already exited"))
                continue
            try:
                os.kill(int(pid), signal.SIGTERM)
            except OSError as exc:
                stopped.append(dict(entry, outcome="SIGTERM failed: %s" % exc))
                continue
            for _ in range(50):
                _reap(pid)
                if not _alive(pid):
                    break
                time.sleep(0.1)
            if _alive(pid):
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    outcome = "SIGKILL"
                except OSError as exc:
                    outcome = "SIGKILL failed: %s" % exc
                for _ in range(20):
                    _reap(pid)
                    if not _alive(pid):
                        break
                    time.sleep(0.1)
            else:
                outcome = "SIGTERM"
            stopped.append(dict(entry, outcome=outcome))
        return stopped

    def abort(self, reason):
        """Terminate everything started, release the lock, record durably.

        The attestation reservation is NOT released. That is the point.
        """
        self.aborted = True
        stopped = self.terminate_all()
        lock_released, lock_disposition = False, "no lock held"
        if self.lock is not None:
            lock_disposition = getattr(self.lock, "disposition", "held")
            if getattr(self.lock, "durability_error", None):
                # A lock whose creation was not durable is deliberately left
                # in place; see RunIdentityLock.acquire.
                lock_disposition = self.lock.disposition
            else:
                try:
                    self.lock.release()
                    lock_released = True
                    lock_disposition = "released"
                except OSError as exc:
                    lock_disposition = "release failed: %s" % exc
        record = {
            "run_id": self.run_id, "outcome": "LAUNCH_ABORTED",
            "reason": str(reason), "aborted_utc": utc(),
            "steps": self.steps, "processes_terminated": stopped,
            "orphans_left": [p for p in stopped
                             if _alive(p["pid"])],
            "attestation_reservation": self.reservation,
            "attestation_returned_to_pool": False,
            "attestation_note": "an attestation spent at reservation stays "
                                "spent. Recovery is a new qualification run.",
            "run_identity_lock_released": lock_released,
            "run_identity_lock_disposition": lock_disposition,
        }
        # The abort record is the one place where refusing to write anything
        # would be worse than writing something undurable. So it is written
        # best-effort and its durability is REPORTED, never assumed.
        outcome = write_best_effort(
            self.record_path,
            json.dumps(record, indent=2, sort_keys=True) + "\n")
        record["abort_record_written"] = outcome["written"]
        record["abort_record_durable"] = outcome["durable"]
        record["abort_record_durability_error"] = outcome["durability_error"]
        if not outcome["durable"]:
            record["abort_record_caveat"] = (
                "this abort record was written but could NOT be made "
                "durable. A crash could lose it. Do not treat its absence "
                "after a reboot as evidence that no launch was attempted.")
            # Rewrite once with the caveat embedded, again best-effort.
            write_best_effort(
                self.record_path,
                json.dumps(record, indent=2, sort_keys=True) + "\n")
        self.abort_record = record
        return record

    def summary(self):
        return {"run_id": self.run_id, "steps": self.steps,
                "processes": self.processes, "aborted": self.aborted,
                "attestation_reservation": self.reservation}
