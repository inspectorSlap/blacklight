"""Durable, bounded local target campaigns for target-capable profiles.

The SQLite intent is committed before the target call. An intent without a
completed result is deliberately never retried automatically: the call may
have reached a target just before a crash. SQLite commits are the evidence
boundary; report.json is a rebuildable view.
"""
from contextlib import contextmanager, closing
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

from .target_adapters import Blocked, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
from .target_probe import MAX_CASES


class CampaignError(ValueError):
    pass


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _money(value, name):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise CampaignError("%s must be a finite nonnegative decimal" % name) from exc
    if not number.is_finite() or number < 0:
        raise CampaignError("%s must be a finite nonnegative decimal" % name)
    return number


def _profile_fingerprint(profile):
    folder = Path(__import__(profile.__class__.__module__, fromlist=["_"]).__file__).parent
    digest = hashlib.sha256()
    for path in sorted(folder.glob("*.py")):
        digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _connect(path):
    connection = sqlite3.connect(path, timeout=1)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


@contextmanager
def _locked(workspace):
    with (workspace / "campaign.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CampaignError("campaign is already running") from exc
        yield


def _create(connection, spec_raw, policy_raw):
    connection.executescript("""
        CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE evidence (
            position INTEGER PRIMARY KEY,
            case_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('INTENT','COMPLETE')),
            request BLOB NOT NULL,
            request_sha256 TEXT NOT NULL,
            response BLOB,
            response_sha256 TEXT,
            checks_json TEXT,
            chain_sha256 TEXT
        );
    """)
    connection.executemany("INSERT INTO meta VALUES (?, ?)",
                           [("spec_sha256", _sha(spec_raw)), ("policy_sha256", _sha(policy_raw)),
                            ("state", "ACTIVE")])
    connection.commit()


def _load(workspace, connection, profile, adapter):
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise CampaignError("campaign database integrity check failed")
    meta = dict(connection.execute("SELECT name, value FROM meta"))
    try:
        spec_raw = (workspace / "spec.json").read_bytes()
        policy_raw = (workspace / "policy.json").read_bytes()
        spec, policy = json.loads(spec_raw), json.loads(policy_raw)
    except (OSError, ValueError) as exc:
        raise CampaignError("campaign freeze is missing or invalid") from exc
    if _sha(spec_raw) != meta.get("spec_sha256") or _sha(policy_raw) != meta.get("policy_sha256"):
        raise CampaignError("campaign freeze digest changed")
    if spec.get("profile") != profile.profile_id or spec.get("profile_sha256") != _profile_fingerprint(profile):
        raise CampaignError("profile identity changed")
    if adapter is not None and spec.get("target") != adapter.identity():
        raise CampaignError("target identity changed")
    if meta.get("state") not in ("ACTIVE", "ABORTED"):
        raise CampaignError("campaign state is invalid")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise CampaignError("frozen cases are invalid")
    if hasattr(profile, "validate_target_cases"):
        profile.validate_target_cases(cases)
    if policy.get("max_requests") != len(cases):
        raise CampaignError("frozen request budget is invalid")
    unit = _money(policy.get("unit_cost"), "unit cost")
    ceiling = _money(policy.get("max_cost"), "cost ceiling")
    if unit * len(cases) > ceiling:
        raise CampaignError("frozen cost budget is invalid")
    rows = connection.execute("SELECT position,case_id,state,request,request_sha256,response,response_sha256,checks_json,chain_sha256 FROM evidence ORDER BY position").fetchall()
    previous = "0" * 64
    intent = False
    for expected_position, row in enumerate(rows):
        position, case_id, state, request, request_sha, response, response_sha, checks_json, chain_sha = row
        if position != expected_position or position >= len(cases) or case_id != cases[position]["id"]:
            raise CampaignError("evidence index is not a case prefix")
        expected_request = _bytes({"profile": profile.profile_id, "input": cases[position]["input"]})
        if request != expected_request or _sha(request) != request_sha:
            raise CampaignError("request evidence digest changed")
        if state == "INTENT":
            if intent or position != len(rows) - 1 or any(item is not None for item in (response, response_sha, checks_json, chain_sha)):
                raise CampaignError("intent evidence is invalid")
            intent = True
            continue
        if state != "COMPLETE" or not isinstance(response, bytes) or _sha(response) != response_sha:
            raise CampaignError("response evidence digest changed")
        try:
            observed = json.loads(response)
            checks = json.loads(checks_json)
        except (ValueError, TypeError) as exc:
            raise CampaignError("completed evidence is invalid") from exc
        if _bytes(observed) != response or checks != profile.check_target_output(observed, cases[position]["expected"]):
            raise CampaignError("evidence checks no longer reproduce")
        expected_chain = _sha(_bytes({"previous": previous, "position": position, "request": request_sha,
                                      "response": response_sha, "checks": checks}))
        if chain_sha != expected_chain:
            raise CampaignError("evidence chain digest changed")
        previous = expected_chain
    return spec, policy, rows, meta["state"]


def _report(spec, policy, rows, state, profile, blocked_reason=None):
    completed = [r for r in rows if r[2] == "COMPLETE"]
    uncertain = bool(rows and rows[-1][2] == "INTENT")
    failed = sum(bool(json.loads(row[7])) for row in completed)
    relational = hasattr(profile, "check_target_relations")
    relations_status = ("EVALUATED" if len(completed) == len(spec["cases"]) and not uncertain
                        else "PENDING") if relational else "NOT_APPLICABLE"
    relation_failures = (profile.check_target_relations(
        spec["cases"], {row[1]: json.loads(row[5]) for row in completed})
        if relations_status == "EVALUATED" else [])
    if state == "ABORTED":
        verdict = "ABORTED"
    elif uncertain:
        verdict = "INDETERMINATE"
    elif len(completed) < len(spec["cases"]):
        verdict = "INCOMPLETE"
    else:
        verdict = "FAILED" if failed or relation_failures else "PASSED"
    return {"run_id": spec["run_id"], "profile": spec["profile"], "target": spec["target"],
            "verdict": verdict, "research_verdict": None,
            "planned_cases": len(spec["cases"]), "completed_cases": len(completed),
            "passed_cases": len(completed) - failed, "failed_cases": failed,
            "relations_status": relations_status, "failed_relations": len(relation_failures),
            "relation_failures": relation_failures,
            "uncertain_inflight_case": rows[-1][1] if uncertain else None,
            "blocked_reason": blocked_reason,
            "estimated_cost": str(Decimal(policy["unit_cost"]) * len(rows)),
            "max_cost": policy["max_cost"], "max_requests": policy["max_requests"],
            "evidence_chain_sha256": completed[-1][8] if completed else None,
            "rows": [{"case": row[1], "status": "FAIL" if json.loads(row[7]) else "PASS",
                      "checks": json.loads(row[7]), "request_sha256": row[4],
                      "response_sha256": row[6]} for row in completed],
            "scope": "bounded local campaign; technical verdict only"}


def _publish(workspace, report):
    _atomic(workspace / "report.json", json.dumps(report, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return report


def start(workspace, profile, adapter, cases, max_requests, max_cost, unit_cost, execute=False, step_limit=None,
          methodology_freeze_sha256=None):
    """Freeze a new campaign, then optionally dispatch a bounded batch."""
    workspace = Path(workspace)
    if workspace.exists():
        raise CampaignError("workspace already exists; use --resume or a new path")
    if not 1 <= len(cases) <= MAX_CASES:
        raise CampaignError("campaign requires 1–32 cases")
    if hasattr(profile, "validate_target_cases"):
        profile.validate_target_cases(cases)
    if max_requests != len(cases):
        raise CampaignError("max requests must equal planned cases before any target work")
    ceiling, unit = _money(max_cost, "cost ceiling"), _money(unit_cost, "unit cost")
    if unit * len(cases) > ceiling:
        raise CampaignError("projected cost exceeds cost ceiling before any target work")
    if step_limit is not None and not 1 <= step_limit <= MAX_CASES:
        raise CampaignError("step limit must be 1–32")
    with tempfile.TemporaryDirectory(prefix="blacklight-preflight-") as temporary:
        local_workspace = Path(temporary)
        (local_workspace / "fixtures").mkdir()
        profile.build(local_workspace)
        if not profile.evaluate(local_workspace).technical_checks_passed:
            raise CampaignError("profile local checks failed before target work")
    for case in cases:
        raw = _bytes({"profile": profile.profile_id, "input": case["input"]})
        if len(raw) > MAX_INPUT_BYTES:
            raise CampaignError("case input exceeds transport limit")
    if methodology_freeze_sha256 is not None and (type(methodology_freeze_sha256) is not str or len(methodology_freeze_sha256) != 64
                                                   or any(c not in "0123456789abcdef" for c in methodology_freeze_sha256)):
        raise CampaignError("methodology freeze digest is invalid")
    spec = {"run_id": str(uuid.uuid4()), "profile": profile.profile_id,
            "profile_sha256": _profile_fingerprint(profile), "target": adapter.identity(), "cases": cases,
            "methodology_freeze_sha256": methodology_freeze_sha256}
    policy = {"max_requests": max_requests, "max_cost": str(ceiling), "unit_cost": str(unit)}
    spec_raw, policy_raw = _bytes(spec), _bytes(policy)
    workspace.mkdir(parents=True)
    with _locked(workspace):
        _atomic(workspace / "spec.json", spec_raw)
        _atomic(workspace / "policy.json", policy_raw)
        with closing(_connect(workspace / "evidence.sqlite3")) as connection:
            _create(connection, spec_raw, policy_raw)
    return resume(workspace, profile, adapter, execute=execute, step_limit=step_limit)


def resume(workspace, profile, adapter, execute=False, step_limit=None, abort=False):
    workspace = Path(workspace)
    if step_limit is not None and not 1 <= step_limit <= MAX_CASES:
        raise CampaignError("step limit must be 1–32")
    if not (workspace / "evidence.sqlite3").is_file():
        raise CampaignError("campaign evidence store is missing")
    with _locked(workspace), closing(_connect(workspace / "evidence.sqlite3")) as connection:
        spec, policy, rows, state = _load(workspace, connection, profile, adapter)
        if abort and state == "ACTIVE":
            connection.execute("UPDATE meta SET value='ABORTED' WHERE name='state'")
            connection.commit()
            state = "ABORTED"
        if state == "ABORTED" or not execute or (rows and rows[-1][2] == "INTENT"):
            return _publish(workspace, _report(spec, policy, rows, state, profile))
        limit = min(len(spec["cases"]), len(rows) + (step_limit or MAX_CASES))
        for position in range(len(rows), limit):
            case = spec["cases"][position]
            request = _bytes({"profile": profile.profile_id, "input": case["input"]})
            connection.execute("INSERT INTO evidence(position,case_id,state,request,request_sha256) VALUES (?,?,?,?,?)",
                               (position, case["id"], "INTENT", request, _sha(request)))
            connection.commit()  # durable intent precedes the external call
            try:
                observed = adapter.request(profile.profile_id, case["input"])
            except Blocked as exc:
                rows = connection.execute("SELECT position,case_id,state,request,request_sha256,response,response_sha256,checks_json,chain_sha256 FROM evidence ORDER BY position").fetchall()
                return _publish(workspace, _report(spec, policy, rows, state, profile, exc.code))
            try:
                response = _bytes(observed)
                checks = profile.check_target_output(observed, case["expected"])
            except (TypeError, ValueError, UnicodeError) as exc:
                raise CampaignError("target output cannot be archived as JSON") from exc
            if len(response) > MAX_OUTPUT_BYTES:
                raise CampaignError("target output exceeds archive limit")
            previous = rows[-1][8] if rows else "0" * 64
            response_sha = _sha(response)
            chain = _sha(_bytes({"previous": previous, "position": position, "request": _sha(request),
                                 "response": response_sha, "checks": checks}))
            connection.execute("UPDATE evidence SET state='COMPLETE',response=?,response_sha256=?,checks_json=?,chain_sha256=? WHERE position=? AND state='INTENT'",
                               (response, response_sha, json.dumps(checks), chain, position))
            connection.commit()  # completed evidence is now durable
            rows = connection.execute("SELECT position,case_id,state,request,request_sha256,response,response_sha256,checks_json,chain_sha256 FROM evidence ORDER BY position").fetchall()
        return _publish(workspace, _report(spec, policy, rows, state, profile))
