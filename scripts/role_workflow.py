"""Prepare, freeze, evaluate and publish a narrow two-role handoff."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import campaign
from harness.profiles import PROFILES
from harness.target_adapters import Blocked, LoopbackHttpAdapter, ProcessAdapter, validate_target_id

MAX_FILE = 1048576


class WorkflowError(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _no_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise WorkflowError("duplicate JSON key")
        result[name] = value
    return result


def _read_json_and_bytes(path):
    try:
        if path.stat().st_size > MAX_FILE:
            raise WorkflowError("file exceeds 1 MiB: %s" % path.name)
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(WorkflowError("nonfinite JSON number")))
        _json_bytes(value)  # also rejects exponent overflow to infinity
        return value, raw
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("unreadable or invalid JSON: %s" % path.name) from exc


def _read_json(path):
    return _read_json_and_bytes(path)[0]


def _require_keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise WorkflowError("%s must contain exactly %s" % (label, ", ".join(keys)))


def _contract(value):
    _require_keys(value, ("schema_version", "profile", "target_id", "requirements", "request_schema", "response_schema"), "contract")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["profile"]) is not str or value["profile"] not in PROFILES):
        raise WorkflowError("unsupported contract version or profile")
    try:
        validate_target_id(value["target_id"])
    except ValueError as exc:
        raise WorkflowError("contract target ID is invalid") from exc
    if type(value["requirements"]) is not list or not value["requirements"] or any(type(x) is not str or not x for x in value["requirements"]):
        raise WorkflowError("contract needs nonempty requirement strings")
    if type(value["request_schema"]) is not dict or type(value["response_schema"]) is not dict:
        raise WorkflowError("contract schemas must be JSON objects")
    return value


def _expectations(value, profile):
    _require_keys(value, ("profile", "cases", "limitations"), "expectations")
    cases = value["cases"]
    if value["profile"] != profile or type(cases) is not list or not 1 <= len(cases) <= 32:
        raise WorkflowError("expectations profile or case count is invalid")
    ids = set()
    for case in cases:
        _require_keys(case, ("id", "input", "expected"), "case")
        if type(case["id"]) is not str or not case["id"] or case["id"] in ids:
            raise WorkflowError("case IDs must be nonempty and unique")
        ids.add(case["id"])
        if type(case["input"]) is not dict:
            raise WorkflowError("case input must be a JSON object")
    if type(value["limitations"]) is not list or any(type(x) is not str for x in value["limitations"]):
        raise WorkflowError("limitations must be a list of strings")
    return value


def _lineage(value):
    _require_keys(value, ("implementer", "reviewer", "shared_lineage", "notes"), "lineage disclosure")
    if any(type(value[k]) is not str or not value[k] for k in ("implementer", "reviewer")):
        raise WorkflowError("implementer and reviewer lineage labels are required")
    if value["shared_lineage"] not in ("yes", "no", "unknown", "not-applicable") or type(value["notes"]) is not str:
        raise WorkflowError("shared lineage must be yes, no, unknown or not-applicable")
    return value


def _new_dir(path):
    if path.exists():
        raise WorkflowError("output already exists: %s" % path)
    path.mkdir(parents=True)


def _write_new(path, value):
    data = _json_bytes(value) + b"\n"
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(data)


def prepare(contract_path, out):
    contract = _contract(_read_json(contract_path))
    _new_dir(out)
    digest = _write_new(out / "contract.json", contract)
    _write_new(out / "manifest.json", {"schema_version": 1, "contract_sha256": digest,
                                      "contents": ["contract.json"]})
    return {"handoff": str(out), "contract_sha256": digest}


def _verify_handoff(bundle):
    manifest = _read_json(bundle / "manifest.json")
    _require_keys(manifest, ("schema_version", "contract_sha256", "contents"), "handoff manifest")
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["contents"] != ["contract.json"]):
        raise WorkflowError("handoff manifest is invalid")
    if {p.name for p in bundle.iterdir()} != {"manifest.json", "contract.json"}:
        raise WorkflowError("handoff contains unexpected files")
    contract_path = bundle / "contract.json"
    if contract_path.is_symlink() or (bundle / "manifest.json").is_symlink():
        raise WorkflowError("handoff may not contain symlinks")
    contract_value, contract_raw = _read_json_and_bytes(contract_path)
    contract = _contract(contract_value)
    digest = _digest(contract_raw)
    if manifest["contract_sha256"] != digest:
        raise WorkflowError("handoff contract digest changed")
    return contract, digest


def freeze(bundle, expectations_path, lineage_path, out):
    contract, contract_sha = _verify_handoff(bundle)
    expectation_value, expectation_raw = _read_json_and_bytes(expectations_path)
    lineage_value, lineage_raw = _read_json_and_bytes(lineage_path)
    expectations = _expectations(expectation_value, contract["profile"])
    lineage = _lineage(lineage_value)
    record = {"schema_version": 1, "contract_sha256": contract_sha,
              "expectations_sha256": _digest(expectation_raw),
              "lineage_sha256": _digest(lineage_raw),
              "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
              "case_count": len(expectations["cases"]),
              "shared_lineage": lineage["shared_lineage"]}
    _write_new(out, record)
    return record


def verify(bundle, expectations_path, lineage_path, freeze_path):
    contract, contract_sha = _verify_handoff(bundle)
    expectation_value, expectation_raw = _read_json_and_bytes(expectations_path)
    lineage_value, lineage_raw = _read_json_and_bytes(lineage_path)
    expectations = _expectations(expectation_value, contract["profile"])
    lineage = _lineage(lineage_value)
    record, freeze_raw = _read_json_and_bytes(freeze_path)
    _require_keys(record, ("schema_version", "contract_sha256", "expectations_sha256", "lineage_sha256",
                           "frozen_at_utc", "case_count", "shared_lineage"), "freeze")
    if (type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["contract_sha256"] != contract_sha \
            or record["expectations_sha256"] != _digest(expectation_raw) \
            or record["lineage_sha256"] != _digest(lineage_raw) \
            or record["case_count"] != len(expectations["cases"]) \
            or record["shared_lineage"] != lineage["shared_lineage"]):
        raise WorkflowError("freeze binding changed")
    return contract, expectations, record, _digest(freeze_raw)


def evaluate(bundle, expectations_path, lineage_path, freeze_path, workspace, program, url,
             max_requests, max_cost, unit_cost, timeout, execute, step_limit, resume):
    contract, expectations, _, freeze_sha = verify(bundle, expectations_path, lineage_path, freeze_path)
    profile = PROFILES[contract["profile"]]
    if not hasattr(profile, "target_cases") or not hasattr(profile, "check_target_output"):
        raise WorkflowError("profile has no target campaign boundary")
    if (program is None) == (url is None):
        raise WorkflowError("choose exactly one target transport")
    if not math.isfinite(timeout) or not 0.1 <= timeout <= 30:
        raise WorkflowError("timeout must be 0.1–30 seconds")
    adapter = (ProcessAdapter(program, contract["target_id"], workspace, timeout)
               if program else LoopbackHttpAdapter(url, contract["target_id"], timeout))
    if resume:
        if any(x is not None for x in (max_requests, max_cost, unit_cost)):
            raise WorkflowError("resume uses frozen budget")
        spec = _read_json(workspace / "spec.json")
        if spec.get("methodology_freeze_sha256") != freeze_sha or spec.get("cases") != expectations["cases"]:
            raise WorkflowError("campaign does not bind to this expectation freeze")
        return campaign.resume(workspace, profile, adapter, execute=execute, step_limit=step_limit)
    if any(x is None for x in (max_requests, max_cost, unit_cost)):
        raise WorkflowError("new evaluation requires max requests, max cost and unit cost")
    return campaign.start(workspace, profile, adapter, expectations["cases"], max_requests,
                          max_cost, unit_cost, execute=execute, step_limit=step_limit,
                          methodology_freeze_sha256=freeze_sha)


def publish(bundle, expectations_path, lineage_path, freeze_path, workspace, out):
    contract, expectations, _, freeze_sha = verify(bundle, expectations_path, lineage_path, freeze_path)
    spec = _read_json(workspace / "spec.json")
    if spec.get("methodology_freeze_sha256") != freeze_sha or spec.get("cases") != expectations["cases"]:
        raise WorkflowError("campaign does not bind to this expectation freeze")
    report = campaign.resume(workspace, PROFILES[contract["profile"]], None, execute=False)
    _new_dir(out)
    report_sha = _write_new(out / "report.json", report)
    _write_new(out / "manifest.json", {"schema_version": 1, "freeze_sha256": freeze_sha,
                                      "report_sha256": report_sha, "contents": ["report.json"]})
    return {"result_bundle": str(out), "verdict": report["verdict"], "report_sha256": report_sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--contract", type=Path, required=True)
    prep.add_argument("--out", type=Path, required=True)
    for name in ("freeze", "verify", "evaluate", "publish"):
        p = sub.add_parser(name)
        p.add_argument("--bundle", type=Path, required=True)
        p.add_argument("--expectations", type=Path, required=True)
        p.add_argument("--lineage", type=Path, required=True)
        p.add_argument("--freeze", type=Path, required=name != "freeze")
        if name == "freeze":
            p.add_argument("--out", type=Path, required=True)
        if name in ("evaluate", "publish"):
            p.add_argument("--workspace", type=Path, required=True)
        if name == "publish":
            p.add_argument("--out", type=Path, required=True)
        if name == "evaluate":
            transport = p.add_mutually_exclusive_group(required=True)
            transport.add_argument("--program", type=Path)
            transport.add_argument("--url")
            p.add_argument("--max-requests", type=int)
            p.add_argument("--max-cost")
            p.add_argument("--unit-cost")
            p.add_argument("--timeout", type=float, default=3.0)
            p.add_argument("--execute", action="store_true")
            p.add_argument("--step-limit", type=int)
            p.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.contract, args.out)
        elif args.command == "freeze":
            result = freeze(args.bundle, args.expectations, args.lineage, args.out)
        elif args.command == "verify":
            contract, expectations, record, digest = verify(args.bundle, args.expectations, args.lineage, args.freeze)
            result = {"profile": contract["profile"], "cases": len(expectations["cases"]),
                      "freeze_sha256": digest, "shared_lineage": record["shared_lineage"]}
        elif args.command == "evaluate":
            result = evaluate(args.bundle, args.expectations, args.lineage, args.freeze,
                              args.workspace, args.program, args.url, args.max_requests, args.max_cost,
                              args.unit_cost, args.timeout, args.execute, args.step_limit, args.resume)
        else:
            result = publish(args.bundle, args.expectations, args.lineage, args.freeze, args.workspace, args.out)
    except (WorkflowError, campaign.CampaignError, Blocked, OSError, ValueError, KeyError) as exc:
        parser.error("workflow refused: %s" % (exc.code if isinstance(exc, Blocked) else exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
