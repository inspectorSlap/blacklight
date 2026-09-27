"""Profile-owned cases through one target adapter, with explicit blocked rows."""
from .target_adapters import Blocked

MAX_CASES = 32


def run(profile, adapter, cases):
    if not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("target probe requires 1–32 cases")
    if hasattr(profile, "validate_target_cases"):
        profile.validate_target_cases(cases)
    rows = []
    observations = {}
    for case in cases:
        try:
            observed = adapter.request(profile.profile_id, case["input"])
        except Blocked as exc:
            rows.append({"case": case["id"], "status": "BLOCKED", "reason": exc.code})
            break
        observations[case["id"]] = observed
        checks = profile.check_target_output(observed, case["expected"])
        rows.append({"case": case["id"], "status": "FAIL" if checks else "PASS", "checks": checks})
    counts = {state: sum(row["status"] == state for row in rows) for state in ("PASS", "FAIL", "BLOCKED")}
    relational = hasattr(profile, "check_target_relations")
    relations_status = "PENDING" if relational and counts["BLOCKED"] else "EVALUATED" if relational else "NOT_APPLICABLE"
    relation_failures = profile.check_target_relations(cases, observations) if relational and not counts["BLOCKED"] else []
    verdict = "BLOCKED" if counts["BLOCKED"] else "FAIL" if counts["FAIL"] or relation_failures else "PASS"
    return {"profile": profile.profile_id, "target": adapter.identity(), "verdict": verdict,
            "relations_status": relations_status, "relation_failures": relation_failures,
            "planned_cases": len(cases), "executed_cases": len(rows), "counts": counts,
            "rows": rows, "scope": "bounded local target probe; no campaign qualification"}
