"""Runtime qualification attestations (v1.5.2).

WHY THIS EXISTS
---------------
v1.5.1 had the proxy qualifier write its result to
`results/proxy-qualification-v1.5.1.json`, which is a hashed artifact of the
frozen release. A successful Terminal rerun produces a different result from
the in-sandbox run, so doing what the launch procedure asked would have
rewritten a frozen file and failed the integrity gate. And nothing checked the
result anyway: the 19/19 prerequisite lived in prose.

So the live result moves out of the release. The qualification *program* stays
frozen and hashed; its *runtime output* is an attestation written here, under
`results/runtime-attestations/`, which is deliberately **not** a release
artifact. Running the qualifier can therefore never alter the release.

WHAT AN ATTESTATION IS FOR
--------------------------
It is not a log. It is the thing `start` requires before it will spawn the
runner. It binds a specific 19/19 result to a specific release, approval,
proxy binary, proxy configuration, launcher, host, target and run identity. If
any of those differ at launch, the attestation does not apply and `start`
refuses. Evidence is bound prospectively to the launch it authorizes, rather
than being a claim made after the fact about some earlier run.

APPEND-ONLY, SINGLE USE
-----------------------
Every attempt gets its own file and its own sequence number. Nothing is ever
overwritten -- a failed or blocked attempt is preserved exactly like a passing
one, because the record of a failed qualification is evidence too. Consumption
is recorded in a separate append-only ledger, so an attestation can authorize
one launch and no more.

NO SECRETS
----------
An attestation never contains the target token, the proxy credential, or any
header material. `scan_for_secrets` is applied to the serialized record before
it is written, and the writer refuses if anything is found.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import datetime
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTESTATION_DIR = os.path.join(ROOT, "results", "runtime-attestations")
INDEX_PATH = os.path.join(ATTESTATION_DIR, "INDEX.jsonl")
CONSUMED_PATH = os.path.join(ATTESTATION_DIR, "CONSUMED.jsonl")

ATTESTATION_VERSION = "1.5.2"
REQUIRED_PASS = 19

# Fields that bind an attestation to the launch it may authorize. Every one of
# these must match at `start`, or the attestation does not apply.
BINDING_FIELDS = (
    "release_digest",
    "approval_digest",
    "proxy_code_sha256",
    "proxy_config_sha256",
    "attestation_module_sha256",
    "launcher_sha256",
    "target_origin",
    "expected_gateway_version",
    "expected_engine_version",
    "host_fingerprint",
    # The run id is a binding field on purpose: an attestation produced for the
    # v1.5.2 checkpoint run must not authorize the v1.5.3 full campaign. They
    # are different undertakings, and 500 calls proving nothing about 158,500.
    "run_id",
)

SECRET_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+\S", re.I),
    re.compile(r"Proxy-Authorization\s*:\s*\S", re.I),
    re.compile(r"BLACKBOX_TARGET_TOKEN\s*[=:]\s*[^\s\"']"),
    re.compile(r"BLACKBOX_PROXY_CREDENTIAL\s*[=:]\s*[^\s\"']"),
    re.compile(r"BLACKBOX_PROXY_SEED\s*[=:]\s*[^\s\"']"),
)


class AttestationRefused(Exception):
    """Raised rather than overwriting or weakening an attestation."""


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def content_digest(record):
    """Digest of everything except the digest field itself."""
    body = {k: v for k, v in record.items() if k != "content_digest"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def scan_for_secrets(record, live_token=None, live_credential=None):
    """Findings, not a boolean: the caller refuses on any non-empty result."""
    text = canonical(record)
    findings = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append("credential-shaped material matching %s"
                            % pattern.pattern[:40])
    # Exact-value comparison, by presence. The values are never emitted.
    for label, value in (("target token", live_token),
                         ("proxy credential", live_credential)):
        if value and len(value) >= 8 and value in text:
            findings.append("the live %s appears in the record" % label)
    return findings


def _next_sequence():
    if not os.path.isfile(INDEX_PATH):
        return 1
    count = 0
    with open(INDEX_PATH, "r") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count + 1


def write(record, live_token=None, live_credential=None):
    """Write a new attestation. Never overwrites; never weakens.

    `record` must already carry the binding fields, the check results and the
    counts. This adds identity, sequence, timestamp and content digest.
    """
    os.makedirs(ATTESTATION_DIR, exist_ok=True)

    sequence = _next_sequence()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    record = dict(record)
    record["attestation_version"] = ATTESTATION_VERSION
    record["sequence"] = sequence
    record["executed_utc"] = record.get("executed_utc") or utc()
    record["attestation_id"] = "rta-%04d-%s" % (sequence, stamp)
    record["secrets_recorded"] = False
    record["content_digest"] = content_digest(record)

    findings = scan_for_secrets(record, live_token, live_credential)
    if findings:
        raise AttestationRefused(
            "refusing to write an attestation containing secret material: %s"
            % "; ".join(findings))

    path = os.path.join(ATTESTATION_DIR, record["attestation_id"] + ".json")
    if os.path.exists(path):
        raise AttestationRefused(
            "attestation %s already exists; attempts are append-only and are "
            "never replaced" % record["attestation_id"])

    # Exclusive create: a race cannot clobber an existing attempt.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o444)
    except FileExistsError:
        raise AttestationRefused(
            "attestation %s already exists" % record["attestation_id"])
    with os.fdopen(fd, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")

    with open(INDEX_PATH, "a") as handle:
        handle.write(canonical({
            "attestation_id": record["attestation_id"],
            "sequence": sequence,
            "executed_utc": record["executed_utc"],
            "outcome": record.get("outcome"),
            "passed": record.get("passed"),
            "failed": record.get("failed"),
            "blocked": record.get("blocked"),
            "content_digest": record["content_digest"],
            "run_id": record.get("run_id"),
        }) + "\n")
    return record, path


def load_all():
    """Every attestation on disk, newest sequence last. Unreadable files are
    reported rather than skipped silently."""
    if not os.path.isdir(ATTESTATION_DIR):
        return [], []
    records, damaged = [], []
    for name in sorted(os.listdir(ATTESTATION_DIR)):
        if not name.startswith("rta-") or not name.endswith(".json"):
            continue
        path = os.path.join(ATTESTATION_DIR, name)
        try:
            with open(path, "r") as handle:
                records.append((path, json.load(handle)))
        except Exception as exc:
            damaged.append({"path": os.path.relpath(path, ROOT),
                            "error": "%s: %s" % (type(exc).__name__,
                                                 str(exc)[:120])})
    records.sort(key=lambda item: item[1].get("sequence", 0))
    return records, damaged


# Record types carried in CONSUMED.jsonl (v1.5.5). The ledger is append-only
# and now carries writability probes alongside consumption records, so every
# reader must discriminate. Entries written before v1.5.5 have no record_type
# and are consumption records by construction -- nothing else was ever
# written -- so the absent case maps to CONSUMPTION for backward compatibility.
RECORD_CONSUMPTION = "attestation_consumption"
RECORD_PROBE = "ledger_writability_probe"


def record_type_of(entry):
    """Classify a ledger line. Unknown types are NOT treated as consumption."""
    declared = entry.get("record_type")
    if declared:
        return declared
    return RECORD_CONSUMPTION if entry.get("attestation_id") else "unknown"


def consumed_ids():
    """Attestations recorded as consumed. Probe records are ignored.

    A probe record carries no attestation identifier and an explicit
    record_type, so it can neither be mistaken for a consumption nor
    accidentally mark anything as used.
    """
    if not os.path.isfile(CONSUMED_PATH):
        return {}
    used = {}
    with open(CONSUMED_PATH, "r") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if record_type_of(entry) != RECORD_CONSUMPTION:
                continue
            identity = entry.get("attestation_id")
            if not identity:
                continue          # a consumption record without an id is
                                  # malformed and must not create a None key
            used.setdefault(identity, entry)
    return used


def consume(record, path, launch):
    """Append-only record that this attestation authorized this launch."""
    os.makedirs(ATTESTATION_DIR, exist_ok=True)
    entry = dict(launch)
    entry.update({
        "record_type": RECORD_CONSUMPTION,
        "attestation_id": record["attestation_id"],
        "content_digest": record["content_digest"],
        "attestation_path": os.path.relpath(path, ROOT),
        "consumed_utc": utc(),
    })
    with open(CONSUMED_PATH, "a") as handle:
        handle.write(canonical(entry) + "\n")
    return entry


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

def intrinsic_problems(record, expected):
    """Why this record is not a valid attestation for this launch.

    Everything except reuse: internal integrity, the required 19/19 outcome,
    and the binding fields. Reuse is a separate question with two different
    correct answers depending on when it is asked -- before a launch, the
    attestation must be unused; during one, it must be spent by that very
    launch -- so it is asked by the callers rather than here.

    Split out in v1.6.6 so `evaluate` and `validate_reserved` cannot drift
    into two different notions of what a valid attestation is.
    """
    problems = []

    if not isinstance(record, dict):
        return ["attestation is not an object"]

    if record.get("attestation_version") != ATTESTATION_VERSION:
        problems.append("attestation version %r, expected %r"
                        % (record.get("attestation_version"),
                           ATTESTATION_VERSION))

    # Internal integrity first: a tampered record's other fields mean nothing.
    stored = record.get("content_digest")
    recomputed = content_digest(record)
    if stored != recomputed:
        problems.append("content digest mismatch: stored %s, recomputed %s "
                        "(the attestation has been altered)"
                        % (str(stored)[:16], recomputed[:16]))

    passed = record.get("passed")
    failed = record.get("failed")
    blocked = record.get("blocked")
    total = record.get("total")
    if passed != REQUIRED_PASS:
        problems.append("%r checks passed, exactly %d required"
                        % (passed, REQUIRED_PASS))
    if failed not in (0, [], None) and failed != 0:
        problems.append("%r checks failed, zero required" % (failed,))
    if blocked != 0:
        problems.append("%r checks blocked, zero required; a BLOCKED check "
                        "was not executed and is not evidence" % (blocked,))
    if total != REQUIRED_PASS:
        problems.append("attestation covers %r checks, expected %d"
                        % (total, REQUIRED_PASS))

    checks = record.get("checks")
    if not isinstance(checks, list) or len(checks) != REQUIRED_PASS:
        problems.append("expected %d individual check results, found %r"
                        % (REQUIRED_PASS,
                           len(checks) if isinstance(checks, list) else None))
    else:
        bad = [c.get("check") for c in checks if c.get("status") != "PASS"]
        if bad:
            problems.append("individual checks not PASS: %s" % bad[:4])
        if len(checks) != len({c.get("check") for c in checks}):
            problems.append("duplicate check names in the attestation")

    if record.get("analysis_endpoint_contacted") is not False:
        problems.append("attestation does not confirm that no analysis "
                        "endpoint was contacted")

    for field in BINDING_FIELDS:
        want = expected.get(field)
        got = record.get(field)
        if want is None:
            problems.append("no expected value available for %s" % field)
        elif got != want:
            problems.append("%s does not match this launch: attestation %s, "
                            "launch %s" % (field, _short(got), _short(want)))

    return problems


def evaluate(record, expected, already_used, spent=None,
             artifact_run_ids=None, resuming=False, authoritative=None):
    """Why this attestation may not authorize this launch. Empty list = may.

    Deliberately returns every reason rather than the first, so a rejection is
    diagnosable without repeated attempts.

    THREE SOURCES, NOT ONE (v1.5.4). `already_used` is CONSUMED.jsonl, which
    is what v1.5.3 relied on and what its failed append defeated. `spent` is
    the durable atomic reservation set plus the permanent void list.
    `artifact_run_ids` maps run identities to operational artifacts already on
    disk -- the backstop, because a launch that produced a runner log used an
    attestation whatever any ledger says.

    This is the PRE-LAUNCH question: the attestation must be unused. A launch
    already in progress must not ask it about its own attestation, which is by
    then correctly spent; see `validate_reserved`.
    """
    spent = {} if spent is None else spent
    artifact_run_ids = {} if artifact_run_ids is None else artifact_run_ids
    authoritative = {} if authoritative is None else authoritative

    problems = intrinsic_problems(record, expected)
    if problems == ["attestation is not an object"]:
        return problems

    identity = record.get("attestation_id")
    if identity in already_used:
        previous = already_used[identity]
        problems.append("attestation %s already authorized a launch at %s; "
                        "each attestation authorizes exactly one"
                        % (identity, previous.get("consumed_utc")))

    # The crash-durable authority is checked first and named explicitly, so a
    # refusal can be attributed to it rather than to a marker that might not
    # have survived a reboot.
    if identity in authoritative:
        entry = authoritative[identity] or {}
        problems.append(
            "attestation %s is PERMANENTLY SPENT by the authoritative "
            "durable spend ledger (run %s, recorded %s). This record does "
            "not depend on the O_EXCL marker or the run lock surviving a "
            "crash."
            % (identity, entry.get("run_id"), entry.get("spent_utc")))

    if identity in spent:
        entry = spent[identity] or {}
        if entry.get("deviation"):
            problems.append(
                "attestation %s is permanently void (%s): %s"
                % (identity, entry["deviation"], entry.get("reason", "")))
        else:
            problems.append(
                "attestation %s was reserved/spent at %s and cannot be used "
                "again; there is no un-spend path"
                % (identity, entry.get("spent_utc", "an earlier launch")))

    # On a RESUME the run identity necessarily has artifacts -- that is what
    # is being resumed. The protection that still applies is that the
    # attestation itself must be neither consumed nor spent, and a resume
    # needs a fresh attestation like any other launch. Applying the artifact
    # check here would make resume structurally impossible.
    run_id = record.get("run_id")
    if not resuming and run_id in artifact_run_ids:
        artifacts = artifact_run_ids[run_id]
        problems.append(
            "run identity %s already has operational artifacts on disk (%s); "
            "a launch that produced them used an attestation even if no "
            "ledger recorded it"
            % (run_id, ", ".join(sorted({a["artifact"] for a in artifacts}))))

    return problems


def _short(value):
    text = str(value)
    return text if len(text) <= 20 else text[:16] + "..."


# ---------------------------------------------------------------------------
# In-flight validation of the attestation a launch already holds (v1.6.6)
# ---------------------------------------------------------------------------
#
# THE DEFECT THIS EXISTS FOR
# --------------------------
# `start` selects an eligible unused attestation, durably records it as
# permanently spent, reserves it, and starts the proxy. Live preflight then ran
# `select()` a second time. By then the transaction's own attestation is --
# correctly -- spent, so the generic selector reported NO_USABLE_ATTESTATION
# and every legitimate launch failed after the spend. Two observed launches
# died exactly there, each burning a qualification run.
#
# The second question was simply the wrong one. Before a launch, the right
# question is "is there an eligible UNUSED attestation?". Once a launch holds
# one, the right question is "is THE attestation I am holding still valid, and
# is it mine?". Asking the pre-launch question mid-launch inverts the meaning
# of its own spend record.
#
# The fix is emphatically NOT to relax spend semantics. Permanent spend stays
# permanent, the ledger stays authoritative, nothing is un-spent and nothing is
# reused. This validates the one attestation the transaction already holds and
# refuses to look for another.

RESERVED_VALIDATION_VERSION = "1.6.6"


def validate_reserved(transaction, expected, path=None, consult_safety=True):
    """Validate THE attestation this launch already reserved and spent.

    Never selects. The identity under validation comes from the caller's own
    transaction, and every piece of corroborating evidence is re-read from
    disk rather than taken from the caller, so this checks durable reality
    rather than the launcher's belief about it.

    `transaction` carries what the launch itself recorded:
    `attestation_id`, `content_digest`, `run_id`, `launch_pid` and
    `reservation_marker`.

    Returns a report; `report["ok"]` is the only field a caller may act on.
    """
    identity = transaction.get("attestation_id")
    report = {
        "validation_version": RESERVED_VALIDATION_VERSION,
        "method": "validate the attestation held by this launch transaction; "
                  "no reselection is attempted",
        "reselected": False,
        "attestation_id": identity,
        "run_id": transaction.get("run_id"),
        "launch_pid": transaction.get("launch_pid"),
        "checks": [],
        "problems": [],
        "ok": False,
    }

    def check(name, ok, detail):
        report["checks"].append({"check": name, "ok": bool(ok),
                                 "detail": detail})
        if not ok:
            report["problems"].append("%s: %s" % (name, detail))
        return ok

    if not identity:
        check("launch transaction names an attestation", False,
              "the transaction carries no attestation id")
        return report

    # 1. The attestation record itself, re-read from disk.
    path = path or os.path.join(ATTESTATION_DIR, "%s.json" % identity)
    record = None
    try:
        with open(path, "r") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        check("attestation file readable", False,
              "%s: %s" % (os.path.relpath(path, ROOT), type(exc).__name__))
        return report
    check("attestation file readable", True, os.path.relpath(path, ROOT))

    if not check("file on disk is the attestation the transaction named",
                 isinstance(record, dict)
                 and record.get("attestation_id") == identity,
                 "file contains %s, transaction holds %s"
                 % (_short((record or {}).get("attestation_id")),
                    _short(identity))):
        return report

    # 2. Internally intact and bound to this launch -- the same definition of
    #    validity the pre-launch gate uses, so the two cannot diverge.
    intrinsic = intrinsic_problems(record, expected)
    check("attestation internally intact and bound to this launch "
          "(release, approval, launcher, proxy, target, host, run identity)",
          not intrinsic,
          "; ".join(intrinsic) if intrinsic
          else "all %d binding fields match; %d/%d PASS, 0 FAIL, 0 BLOCKED"
               % (len(BINDING_FIELDS), record.get("passed"), REQUIRED_PASS))

    # 3. The digest the transaction committed to must be the digest on disk.
    #    This is what makes swapping the file underneath a running launch
    #    detectable.
    check("attestation content digest matches the one this launch committed to",
          record.get("content_digest") == transaction.get("content_digest")
          and content_digest(record) == record.get("content_digest"),
          "transaction %s, on disk %s, recomputed %s"
          % (_short(transaction.get("content_digest")),
             _short(record.get("content_digest")),
             _short(content_digest(record))))

    # 4. The run identity must be this launch's.
    check("attestation run identity is this launch's run identity",
          record.get("run_id") == transaction.get("run_id")
          and record.get("run_id") == expected.get("run_id"),
          "attestation %s, transaction %s, launch %s"
          % (_short(record.get("run_id")),
             _short(transaction.get("run_id")),
             _short(expected.get("run_id"))))

    if not consult_safety:
        report["ok"] = not report["problems"]
        report["consulted"] = ["attestation record only (consult_safety off)"]
        return report

    import blackbox_launch_safety as safety

    # 5. The authoritative durable spend ledger, re-read now. It must name
    #    THIS attestation as spent -- the inverse of the pre-launch test, and
    #    the point of the correction.
    ledger = safety.spend_records()
    if not check("authoritative spend ledger is interpretable",
                 ledger["interpretable"],
                 ledger.get("reason_detail") or ledger["reason"]):
        return report

    spend_entry = ledger["spent"].get(identity)
    if not check("durable spend record names this exact attestation",
                 spend_entry is not None,
                 "present in ledger" if spend_entry is not None
                 else "no spend record for %s; this launch believes it spent "
                      "an attestation the durable ledger does not record"
                      % identity):
        return report

    check("spend record is a permanent, irreversible spend",
          spend_entry.get("permanently_spent") is True
          and spend_entry.get("reversible") is False,
          "permanently_spent=%r reversible=%r"
          % (spend_entry.get("permanently_spent"),
             spend_entry.get("reversible")))

    check("spend record agrees with the attestation and this launch",
          spend_entry.get("attestation_content_digest")
          == record.get("content_digest")
          and spend_entry.get("run_id") == expected.get("run_id")
          and spend_entry.get("release_digest") == expected.get("release_digest")
          and spend_entry.get("approval_digest")
          == expected.get("approval_digest"),
          "content=%s run=%s release=%s approval=%s"
          % (_short(spend_entry.get("attestation_content_digest")),
             _short(spend_entry.get("run_id")),
             _short(spend_entry.get("release_digest")),
             _short(spend_entry.get("approval_digest"))))

    # 6. Spent by THIS process, not by some earlier launch. This is what
    #    distinguishes the transaction's own attestation from an unrelated
    #    previously spent one: a stale attestation carries another pid.
    launch_pid = transaction.get("launch_pid")
    check("spent by this current launch transaction, not an earlier one",
          launch_pid is not None and spend_entry.get("pid") == launch_pid,
          "spend record pid %r, this launch pid %r"
          % (spend_entry.get("pid"), launch_pid))

    # 7. The O_EXCL reservation marker, read from the path the transaction
    #    recorded, must name the same attestation and the same launch.
    marker_path = transaction.get("reservation_marker")
    marker = None
    if not check("reservation marker recorded and present",
                 bool(marker_path) and os.path.isfile(marker_path),
                 os.path.relpath(marker_path, ROOT) if marker_path
                 else "no reservation marker recorded"):
        return report
    try:
        with open(marker_path, "r") as handle:
            marker = json.load(handle)
    except (OSError, ValueError) as exc:
        check("reservation marker readable", False, type(exc).__name__)
        return report

    check("reservation marker is for this exact attestation",
          os.path.basename(marker_path) == identity
          and marker.get("attestation_id") == identity
          and marker.get("content_digest") == record.get("content_digest"),
          "marker file %s, names %s, digest %s"
          % (os.path.basename(marker_path),
             _short(marker.get("attestation_id")),
             _short(marker.get("content_digest"))))

    check("reservation marker was created by this current launch",
          marker.get("pid") == launch_pid
          and marker.get("run_id") == expected.get("run_id"),
          "marker pid %r run %s; this launch pid %r run %s"
          % (marker.get("pid"), _short(marker.get("run_id")),
             launch_pid, _short(expected.get("run_id"))))

    # 8. Spent is not consumed. An attestation already consumed authorized a
    #    launch that reached its runner; this one has not got there yet.
    used = consumed_ids()
    check("attestation has not already authorized a completed launch",
          identity not in used,
          "consumed at %s" % (used.get(identity, {}) or {}).get("consumed_utc")
          if identity in used else "not in CONSUMED.jsonl")

    # 9. Never validate a permanently void attestation, whatever the ledger
    #    and marker say about it.
    void = getattr(safety, "PERMANENT_VOID", {})
    check("attestation is not permanently void",
          identity not in void,
          "void: %s" % (void.get(identity, {}) or {}).get("reason", "")
          if identity in void else "not on the permanent void list")

    report["consulted"] = ["attestation record on disk",
                           "authoritative SPEND.jsonl ledger",
                           "O_EXCL reservation marker",
                           "CONSUMED.jsonl",
                           "permanent void list"]
    report["spend_record"] = {
        "run_id": spend_entry.get("run_id"),
        "spent_utc": spend_entry.get("spent_utc"),
        "pid": spend_entry.get("pid"),
        "permanently_spent": spend_entry.get("permanently_spent"),
    }
    report["reservation_marker"] = os.path.relpath(marker_path, ROOT)
    report["ok"] = not report["problems"]
    report["outcome"] = ("RESERVED_ATTESTATION_VALID" if report["ok"]
                         else "RESERVED_ATTESTATION_INVALID")
    return report


def select(expected, consult_safety=True, resuming=False):
    """The one attestation that may authorize this launch, or None.

    Returns `(record, path, report)`. `report` always explains the outcome,
    including why each rejected candidate was rejected.

    `consult_safety=False` exists only so the safety module's own tests can
    isolate the ledger check. Production callers leave it on.
    """
    records, damaged = load_all()
    used = consumed_ids()

    spent, artifact_run_ids, authoritative = {}, {}, {}
    ledger, ledger_report = None, {
        "present": None, "readable": None, "interpretable": None,
        "validity_state": "NOT_CONSULTED", "valid_spend_records": 0,
        "malformed_line_count": 0, "malformed_lines": [],
        "unknown_record_type_count": 0, "unknown_record_types": [],
        "structural_error_count": 0, "structural_errors": [],
        "contradiction_count": 0, "contradictions": [],
        "raw_payload_copied": False}
    if consult_safety:
        try:
            import blackbox_launch_safety as safety
            spent = safety.spent_ids()
            artifact_run_ids = safety.run_ids_with_artifacts()
            ledger = safety.spend_records()
            authoritative = ledger["spent"]
            ledger_report = {
                "ledger_path": ledger["ledger_path"],
                "present": ledger["present"],
                "readable": ledger["readable"],
                "interpretable": ledger["interpretable"],
                "validity_state": ledger["reason"],
                "valid_spend_records": ledger["valid_spend_records"],
                "malformed_line_count": len(ledger["malformed_lines"]),
                "malformed_lines": ledger["malformed_lines"],
                "unknown_record_type_count":
                    len(ledger["unknown_record_types"]),
                "unknown_record_types": ledger["unknown_record_types"],
                "structural_error_count": len(ledger["structural_errors"]),
                "structural_errors": ledger["structural_errors"],
                "contradiction_count": len(ledger["contradictions"]),
                "contradictions": ledger["contradictions"],
                "raw_payload_copied": False,
                "reason_detail": ledger.get("reason_detail")}
        except ImportError:
            # Fail closed: without the safety module the third and fourth
            # sources cannot be consulted, and selection must not silently
            # fall back to CONSUMED.jsonl alone.
            raise

    # FAIL CLOSED ON AN UNINTERPRETABLE AUTHORITATIVE LEDGER.
    #
    # This precedes every per-attestation check on purpose. If the ledger
    # that decides spent-ness cannot be read, no attestation can be shown to
    # be unspent, so none may authorize anything. There is no force flag, no
    # ignore option and no warn-and-continue path.
    if consult_safety and ledger is not None and not ledger["interpretable"]:
        return None, None, {
            "outcome": "SPEND_LEDGER_UNINTERPRETABLE",
            "fail_closed_reason": ledger["reason"],
            "fail_closed_detail": ledger.get("reason_detail"),
            "explanation":
                "the authoritative spend ledger could not be interpreted, so "
                "no attestation can be shown to be unspent. An unreadable "
                "record in that ledger may itself be a spend record; "
                "ambiguity in an authoritative source is not absence of a "
                "spend. Nothing is authorized.",
            "remedy": "repair or replace the ledger from durable evidence. "
                      "There is deliberately no option to proceed past this.",
            "spend_ledger": ledger_report,
            "attestations_on_disk": len(records),
            "damaged": damaged,
            "eligible": [], "rejected": [],
            "already_consumed": sorted(used),
            "authoritatively_spent": [],
            "sources_consulted": ["authoritative SPEND.jsonl ledger"],
            "resuming": resuming,
            "raw_ledger_payload_copied": False,
        }

    rejected, eligible = [], []
    for path, record in records:
        problems = evaluate(record, expected, used, spent, artifact_run_ids,
                            resuming=resuming, authoritative=authoritative)
        entry = {"attestation_id": record.get("attestation_id"),
                 "path": os.path.relpath(path, ROOT),
                 "sequence": record.get("sequence"),
                 "problems": problems}
        (eligible if not problems else rejected).append((path, record, entry))

    report = {
        "attestations_on_disk": len(records),
        "damaged": damaged,
        "eligible": [e[2]["attestation_id"] for e in eligible],
        "rejected": [e[2] for e in rejected],
        "already_consumed": sorted(used),
        "authoritatively_spent": sorted(authoritative),
        "spend_ledger": ledger_report,
        "spent_or_void": sorted(spent),
        "run_ids_with_artifacts": sorted(artifact_run_ids),
        "sources_consulted": ["authoritative SPEND.jsonl ledger",
                              "CONSUMED.jsonl",
                              "durable spent/void set"]
                             + ([] if resuming
                                else ["operational artifacts on disk"])
                             if consult_safety else ["CONSUMED.jsonl"],
        "resuming": resuming,
        "artifact_check_applied": consult_safety and not resuming,
        "required": {"passed": REQUIRED_PASS, "failed": 0, "blocked": 0,
                     "bindings": list(BINDING_FIELDS),
                     "single_use": True, "internally_intact": True,
                     "not_authoritatively_spent": True,
                     "not_spent_or_void": True,
                     "run_identity_has_no_artifacts": True},
    }
    if not eligible:
        report["outcome"] = "NO_USABLE_ATTESTATION"
        return None, None, report

    # Most recent eligible attestation.
    path, record, _entry = max(eligible, key=lambda e: e[1].get("sequence", 0))
    report["outcome"] = "AUTHORIZED"
    report["selected"] = {"attestation_id": record["attestation_id"],
                          "content_digest": record["content_digest"],
                          "path": os.path.relpath(path, ROOT),
                          "executed_utc": record.get("executed_utc"),
                          "sequence": record.get("sequence")}
    return record, path, report
