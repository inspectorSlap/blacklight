"""Attempt-archive invariants (locked contract section 10).

The governing requirement is that "invalid attempts, missingness, refusals, and
deviations remain observable and cannot disappear through denominator changes
or favorable replacement selection". Each invariant below is a reading of that
sentence that holds under every disposition the distribution leaves open, so
none of them depends on resolving AMB-06, AMB-07, AMB-08 or AMB-14.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import copy
import json
import random

from .checks import finding

CELLS = ("00", "A0", "0B", "AB")
K = 10


def _attempts(scenario):
    return scenario["payload"]["attempts"]


def _group_key(record):
    return (record["light_id"], record["specimen_id"], record["cell"],
            record["replicate_index"])


def _unambiguously_valid(record, r_max):
    """Valid under EVERY reading recorded in the ambiguity register."""
    return (record["transport_status"] == "OK"
            and record["schema_valid"] and record["stamp_valid"]
            and record["route_match"] and record["lens_valid"]
            and not record["cache_hit"]
            and isinstance(record["score"], int)
            and not isinstance(record["score"], bool)
            and 1 <= record["score"] <= K
            and record["attempt_index"] <= r_max)


def _output_ids(result):
    ids = []
    for key in ("selected_responses", "technical_or_unselected_attempts"):
        for row in result.get(key, []):
            if isinstance(row, dict) and "attempt_id" in row:
                ids.append(row["attempt_id"])
    return ids


def _all_text(result):
    return json.dumps(result, sort_keys=True, default=str)


def _counts_from_selected(result):
    buckets = {}
    for row in result.get("selected_responses", []):
        key = (row["light_id"], row["specimen_id"], row["cell"])
        counts = buckets.setdefault(key, [0] * K)
        counts[row["score"] - 1] += 1
    return buckets


def _counts_from_payload(result):
    buckets = {}
    payload = result.get("count_payload") or {}
    for light in payload.get("lights", []):
        for key in ("semantic_specimens", "mechanical_specimens"):
            for specimen in light.get(key, []):
                for cell in CELLS:
                    entry = specimen["cells"][cell]["counts"]
                    buckets[(light["id"], specimen["id"], cell)] = list(entry)
    return buckets


# ---------------------------------------------------------------------------
# Individual invariants
# ---------------------------------------------------------------------------

def inv_no_attempt_lost(scenario, outcome, findings):
    result = outcome["result"]
    expected = len(_attempts(scenario))
    if result.get("attempt_count") != expected:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "attempt_count is %r but the archive contained %d attempts; every "
            "attempt, including invalid and failed attempts, is retained"
            % (result.get("attempt_count"), expected)))


def inv_partition_is_exact(scenario, outcome, findings):
    result = outcome["result"]
    reported = _output_ids(result)
    expected = [record["attempt_id"] for record in _attempts(scenario)]
    if sorted(reported) != sorted(expected):
        missing = sorted(set(expected) - set(reported))
        extra = sorted(set(reported) - set(expected))
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "the selected/unselected partition does not reproduce the input "
            "attempt set: %d attempt(s) vanished, %d appeared"
            % (len(missing), len(extra)),
            {"vanished": missing[:10], "unexpected": extra[:10]}))


def inv_first_valid_selected(scenario, outcome, findings):
    result = outcome["result"]
    r_max = scenario["payload"]["config"]["r_max"]
    groups = {}
    for record in _attempts(scenario):
        groups.setdefault(_group_key(record), []).append(record)
    selected = {}
    for row in result.get("selected_responses", []):
        selected[(row["light_id"], row["specimen_id"], row["cell"],
                  row["replicate_index"])] = row
    for key, records in sorted(groups.items()):
        valid = sorted((r for r in records if _unambiguously_valid(r, r_max)),
                       key=lambda r: r["attempt_index"])
        if not valid:
            continue
        expected = valid[0]
        row = selected.get(key)
        if row is None:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "replicate %r had a valid attempt at index %d but no response "
                "was selected" % (key, expected["attempt_index"])))
            continue
        if row.get("attempt_id") != expected["attempt_id"]:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "replicate %r selected attempt %r (index %r, score %r) although "
                "attempt %r at index %d was already valid and scored %r; "
                "section 11.2 retains the FIRST valid response and this is the "
                "registered favorable-replacement defect (anchor A16)"
                % (key, row.get("attempt_id"), row.get("attempt_index"),
                   row.get("score"), expected["attempt_id"],
                   expected["attempt_index"], expected["score"]),
                {"expected_attempt": expected["attempt_id"],
                 "selected_attempt": row.get("attempt_id")}))


def inv_selected_score_is(scenario, outcome, findings):
    """Uses the `notes` field, e.g. 'selected_score_is: (L1,ordinal-profile,AB,1) -> 4'."""
    result = outcome["result"]
    for line in scenario.get("notes", "").splitlines():
        if "selected_score_is:" not in line:
            continue
        spec, _, score = line.split("selected_score_is:")[1].partition("->")
        light, specimen, cell, replicate = [
            part.strip() for part in spec.strip().strip("()").split(",")]
        want = int(score.strip())
        for row in result.get("selected_responses", []):
            if (row["light_id"] == light and row["specimen_id"] == specimen
                    and row["cell"] == cell
                    and row["replicate_index"] == int(replicate)):
                if row["score"] != want:
                    findings.append(finding(
                        "archive_invariants", scenario["scenario_id"], "FAIL",
                        "selected score for (%s,%s,%s,%s) is %r but the "
                        "first-valid rule requires %r"
                        % (light, specimen, cell, replicate, row["score"], want)))
                return
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "no selected response for (%s,%s,%s,%s)"
            % (light, specimen, cell, replicate)))


def inv_counts_match_selected(scenario, outcome, findings):
    result = outcome["result"]
    from_selected = _counts_from_selected(result)
    from_payload = _counts_from_payload(result)
    if not from_payload:
        return
    for key, counts in sorted(from_payload.items()):
        expected = from_selected.get(key)
        if expected is None:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "count payload contains %r with no corresponding selected "
                "responses" % (key,)))
        elif counts != expected:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "count payload for %r is %r but the selected responses give "
                "%r; the count payload must be exactly reconstructible from "
                "the selected responses, with no imputation" % (key, counts,
                                                                expected),
                {"payload_counts": counts, "selected_counts": expected}))


def inv_no_missing_replicates(scenario, outcome, findings):
    result = outcome["result"]
    if result.get("missing_replicates"):
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "missing replicates reported for a complete archive: %r"
            % (result["missing_replicates"][:3],)))


def inv_missing_replicate_reported(scenario, outcome, findings):
    result = outcome["result"]
    reported = result.get("missing_replicates") or []
    if not reported:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "no missing replicate was reported although this archive has one; "
            "missingness may not disappear through a denominator change"))
        return
    for line in scenario.get("notes", "").splitlines():
        if "missing_replicate_reported:" not in line:
            continue
        spec = line.split("missing_replicate_reported:")[1].strip().strip("()")
        light, specimen, cell, replicate = [p.strip() for p in spec.split(",")]
        for entry in reported:
            if (entry.get("light_id") == light
                    and entry.get("specimen_id") == specimen
                    and entry.get("cell") == cell
                    and entry.get("replicate_index") == int(replicate)):
                return
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "expected missing replicate (%s,%s,%s,%s) was not reported"
            % (light, specimen, cell, replicate),
            {"reported": reported[:5]}))


def inv_analysis_eligible_true(scenario, outcome, findings):
    if outcome["result"].get("analysis_eligible") is not True:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "a clean, complete archive was marked analysis-ineligible"))


def inv_analysis_eligible_false(scenario, outcome, findings):
    if outcome["result"].get("analysis_eligible") is not False:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "analysis_eligible is %r although this archive carries an "
            "unresolved missingness, deviation or validity condition"
            % outcome["result"].get("analysis_eligible")))


def inv_beyond_rmax_not_selected(scenario, outcome, findings):
    result = outcome["result"]
    r_max = scenario["payload"]["config"]["r_max"]
    for row in result.get("selected_responses", []):
        if row.get("attempt_index", 0) > r_max + 1:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "attempt at index %r was selected although r_max is %d; the "
                "index lies outside the cap under every reading in AMB-06"
                % (row.get("attempt_index"), r_max)))


def inv_order_invariance(scenario, outcome, findings, target=None):
    if target is None:
        return
    shuffled = copy.deepcopy(scenario["payload"])
    generator = random.Random(20260920)
    generator.shuffle(shuffled["attempts"])
    try:
        other = target.aggregate(shuffled)
    except Exception as exc:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "BLOCKED",
            "row-permuted archive call failed: %s" % exc))
        return
    if _comparable(other) != _comparable(outcome["result"]):
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "permuting the rows of the attempts array changed the scientific "
            "result; attempt order is carried by attempt_index, not row "
            "position (anchor A16)"))


def _comparable(result):
    stripped = copy.deepcopy(result)
    for key in ("selected_responses", "technical_or_unselected_attempts",
                "missing_replicates", "global_deviations"):
        if isinstance(stripped.get(key), list):
            stripped[key] = sorted(
                (json.dumps(row, sort_keys=True, default=str)
                 for row in stripped[key]))
    return json.dumps(stripped, sort_keys=True, default=str)


def inv_rejected_or_explicitly_flagged(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    result = outcome["result"]
    flagged = (bool(result.get("global_deviations"))
               or result.get("analysis_eligible") is False)
    if not flagged:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "a structurally malformed archive was accepted without rejection "
            "and without any explicit deviation or ineligibility flag; input "
            "rejection is part of the observable target behaviour"))


def inv_no_silent_coercion(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    result = outcome["result"]
    offending = []
    for record in _attempts(scenario):
        score = record["score"]
        if score is None:
            continue
        if isinstance(score, bool) or not isinstance(score, int) \
                or not (1 <= score <= K):
            offending.append(record["attempt_id"])
    selected = {row.get("attempt_id"): row
                for row in result.get("selected_responses", [])}
    for attempt_id in offending:
        row = selected.get(attempt_id)
        if row is not None:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "attempt %r carried an out-of-range or non-integer score but "
                "was selected with score %r; the value was silently coerced "
                "rather than rejected" % (attempt_id, row.get("score"))))


def inv_cache_event_observable(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    text = _all_text(outcome["result"])
    for record in _attempts(scenario):
        if record["cache_hit"]:
            if record["attempt_id"] not in text:
                findings.append(finding(
                    "archive_invariants", scenario["scenario_id"], "FAIL",
                    "cache-hit attempt %r does not appear anywhere in the "
                    "output; an unexpected cache event must remain observable"
                    % record["attempt_id"]))


def inv_deviation_observable(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    text = _all_text(outcome["result"])
    for record in _attempts(scenario):
        if not (record["route_match"] and record["stamp_valid"]
                and record["lens_valid"]):
            if record["attempt_id"] not in text:
                findings.append(finding(
                    "archive_invariants", scenario["scenario_id"], "FAIL",
                    "attempt %r carries a route, stamp or lens problem but does "
                    "not appear in the output" % record["attempt_id"]))


def inv_failed_attempts_reported(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    reported = set(_output_ids(outcome["result"]))
    r_max = scenario["payload"]["config"]["r_max"]
    for record in _attempts(scenario):
        if not _unambiguously_valid(record, r_max):
            if record["attempt_id"] not in reported:
                findings.append(finding(
                    "archive_invariants", scenario["scenario_id"], "FAIL",
                    "invalid attempt %r was dropped from the output"
                    % record["attempt_id"]))


def inv_refusal_scores_retained(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    result = outcome["result"]
    r_max = scenario["payload"]["config"]["r_max"]
    selected = {row.get("attempt_id"): row
                for row in result.get("selected_responses", [])}
    groups = {}
    for record in _attempts(scenario):
        groups.setdefault(_group_key(record), []).append(record)
    for key, records in sorted(groups.items()):
        valid = sorted((r for r in records if _unambiguously_valid(r, r_max)),
                       key=lambda r: r["attempt_index"])
        if not valid or not valid[0]["refusal"]:
            continue
        first = valid[0]
        row = selected.get(first["attempt_id"])
        if row is None:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "schema-valid refusal %r supplying score %r was not retained; "
                "section 11.2 keeps it in the cell distribution with its "
                "supplied score and an immutable refusal flag"
                % (first["attempt_id"], first["score"])))
        elif row.get("score") != first["score"]:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "FAIL",
                "refusal %r was retained with score %r instead of its supplied "
                "score %r; no score may be imputed or replaced"
                % (first["attempt_id"], row.get("score"), first["score"])))


def inv_refusal_rate_reported(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    text = _all_text(outcome["result"])
    if "refusal" not in text:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "the output reports nothing about refusals although the archive "
            "contains them; refusal rates are reported measurement outcomes"))


def inv_differential_refusal_flagged(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    result = outcome["result"]
    summary = result.get("refusal_summary") or {}
    crossed = bool(summary.get("limit_crossings"))
    deviated = any(d.get("class") == "REFUSAL_LIMIT_CROSSED"
                   for d in result.get("global_deviations", [])
                   if isinstance(d, dict))
    if not (crossed or deviated) or result.get("analysis_eligible") is not False:
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "a maximal differential refusal across both registered cell "
            "comparisons was not flagged and did not withhold the affected "
            "confirmatory inference (analysis_eligible=%r)"
            % result.get("analysis_eligible")))


def inv_unequal_totals_reported(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    result = outcome["result"]
    if not (result.get("unequal_valid_response_totals")
            or result.get("missing_replicates")):
        findings.append(finding(
            "archive_invariants", scenario["scenario_id"], "FAIL",
            "unequal valid-response totals were neither reported nor reflected "
            "in missing replicates; the imbalance may not be equalised away"))


def inv_controls_not_pooled_into_primary(scenario, outcome, findings):
    if outcome["rejected"]:
        return
    payload = outcome["result"].get("count_payload") or {}
    mechanical_ids = {record["specimen_id"] for record in _attempts(scenario)
                      if record["specimen_group"] == "mechanical"}
    for light in payload.get("lights", []):
        for specimen in light.get("semantic_specimens", []):
            if specimen["id"] in mechanical_ids:
                findings.append(finding(
                    "archive_invariants", scenario["scenario_id"], "FAIL",
                    "mechanical control %r entered the six-specimen primary "
                    "aggregate for light %r; C5 uses exactly four separate "
                    "controls" % (specimen["id"], light.get("id"))))


INVARIANTS = {
    "no_attempt_lost": inv_no_attempt_lost,
    "partition_is_exact": inv_partition_is_exact,
    "first_valid_selected": inv_first_valid_selected,
    "selected_score_is": inv_selected_score_is,
    "counts_match_selected": inv_counts_match_selected,
    "no_missing_replicates": inv_no_missing_replicates,
    "missing_replicate_reported": inv_missing_replicate_reported,
    "analysis_eligible_true": inv_analysis_eligible_true,
    "analysis_eligible_false": inv_analysis_eligible_false,
    "beyond_rmax_not_selected": inv_beyond_rmax_not_selected,
    "rejected_or_explicitly_flagged": inv_rejected_or_explicitly_flagged,
    "no_silent_coercion": inv_no_silent_coercion,
    "cache_event_observable": inv_cache_event_observable,
    "deviation_observable": inv_deviation_observable,
    "failed_attempts_reported": inv_failed_attempts_reported,
    "refusal_scores_retained": inv_refusal_scores_retained,
    "refusal_rate_reported": inv_refusal_rate_reported,
    "differential_refusal_flagged": inv_differential_refusal_flagged,
    "unequal_totals_reported": inv_unequal_totals_reported,
    "controls_not_pooled_into_primary": inv_controls_not_pooled_into_primary,
    "later_attempt_still_reported": inv_partition_is_exact,
    "order_invariance": inv_order_invariance,
}

# Invariants that are vacuous when the archive was rejected outright: a
# rejection is itself a valid disposition for a malformed archive, so only the
# invariants that reason about a rejection remain live.
REQUIRES_RESULT = set(INVARIANTS) - {"rejected_or_explicitly_flagged",
                                     "no_silent_coercion",
                                     "controls_not_pooled_into_primary"}


def run_archive_invariants(scenario, outcome, target=None):
    findings = []
    for name in scenario["expected"]["invariants"]:
        function = INVARIANTS.get(name)
        if function is None:
            findings.append(finding(
                "archive_invariants", scenario["scenario_id"], "BLOCKED",
                "unknown invariant %r in the frozen scenario" % name))
            continue
        if outcome["rejected"] and name in REQUIRES_RESULT:
            continue
        if name == "order_invariance":
            inv_order_invariance(scenario, outcome, findings, target)
        else:
            function(scenario, outcome, findings)
    return findings
