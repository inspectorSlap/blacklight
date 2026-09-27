"""Sound reference implementation of canonical attempt-archive aggregation.

Derived from `docs/PROFILE.md` section 11.2 (retry
and replacement policy), section 11.3 (deviation rule) and the locked contract
section 10 adversary list. Imports only the standard library.

Governing rules implemented here, with their sources:

* "Every attempt, including invalid and failed attempts, is retained in order."
  -- nothing is ever dropped; the union of `selected_responses` and
  `technical_or_unselected_attempts` is exactly the input attempt set.
* "The first valid response in attempt order is retained as the requested
  replicate." -- selection is by smallest `attempt_index` among valid attempts,
  never by score favourability (anchor A16).
* "A schema-valid refusal that supplies the required integer score and rationale
  remains in the cell distribution with its supplied score" -- refusals with a
  valid score are selectable and their scores enter `count_payload`.
* "A refusal without a valid required score is a structurally invalid response"
  -- unselectable.
* "After the prospectively fixed maximum R_MAX is exhausted, the replicate is
  recorded missing under its terminal failure code."
* "A nonzero cache read or write ... pauses the affected instrument for
  deviation review" -- a cache hit is recorded as a deviation and is not
  silently replaced.

Two reading choices are forced by gaps in the distribution and are declared
rather than hidden (see `reports/AMBIGUITY-REGISTER-v1.0.md`):

* AMB-06: `r_max` is read as a count of *replacement* attempts, so permitted
  `attempt_index` values are `0..r_max`.
* AMB-07: a cache-hit attempt is treated as unselectable and deviation-flagged.

The harness does not assert either choice against the real engine; it asserts
only the reading-independent invariants documented in the register.
"""

CELLS = ("00", "A0", "0B", "AB")
GROUPS = ("semantic", "mechanical")
K = 10

ARCHIVE_SCHEMA = "blackbox.ordinal.attempt-archive.v0.1"
AGGREGATE_SCHEMA = "blackbox.ordinal.aggregate-result.v0.1"
COUNTS_SCHEMA = "blackbox.ordinal.ordinal-counts.v0.1"

REQUIRED_ATTEMPT_FIELDS = (
    "attempt_id", "light_id", "specimen_id", "specimen_group", "cell",
    "replicate_index", "attempt_index", "transport_status", "schema_valid",
    "stamp_valid", "cache_hit", "route_match", "lens_valid", "refusal", "score",
)


class Rejected(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def _require(condition, code, message):
    if not condition:
        raise Rejected(code, message)


def validate_archive(payload):
    _require(isinstance(payload, dict), "NOT_AN_OBJECT", "payload must be an object")
    _require(payload.get("schema_version") == ARCHIVE_SCHEMA,
             "BAD_SCHEMA_VERSION", "schema_version must be %s" % ARCHIVE_SCHEMA)
    _require(isinstance(payload.get("archive_id"), str),
             "BAD_ARCHIVE_ID", "archive_id must be a string")

    config = payload.get("config")
    _require(isinstance(config, dict), "BAD_CONFIG", "config must be an object")
    expected_n = config.get("expected_n")
    _require(isinstance(expected_n, int) and not isinstance(expected_n, bool)
             and expected_n >= 2, "BAD_EXPECTED_N",
             "config.expected_n must be an integer >= 2")
    r_max = config.get("r_max")
    _require(isinstance(r_max, int) and not isinstance(r_max, bool) and r_max >= 0,
             "BAD_R_MAX", "config.r_max must be an integer >= 0")
    for key in ("refusal_overall_limit", "refusal_differential_limit"):
        value = config.get(key)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool),
                 "BAD_REFUSAL_LIMIT", "config.%s must be a number" % key)
        _require(0.0 <= float(value) <= 1.0, "BAD_REFUSAL_LIMIT",
                 "config.%s must lie in [0,1]" % key)

    _require(isinstance(payload.get("analysis_config"), dict),
             "BAD_ANALYSIS_CONFIG", "analysis_config must be an object")

    attempts = payload.get("attempts")
    _require(isinstance(attempts, list), "BAD_ATTEMPTS",
             "attempts must be an array")

    seen_ids = set()
    seen_coords = set()
    group_of_specimen = {}
    for attempt in attempts:
        _require(isinstance(attempt, dict), "BAD_ATTEMPT",
                 "attempt must be an object")
        for field in REQUIRED_ATTEMPT_FIELDS:
            _require(field in attempt, "MISSING_FIELD",
                     "attempt is missing %r" % field)
        _require(isinstance(attempt["attempt_id"], str),
                 "BAD_ATTEMPT_ID", "attempt_id must be a string")
        _require(attempt["attempt_id"] not in seen_ids, "DUPLICATE_ATTEMPT_ID",
                 "duplicate attempt_id %r" % attempt["attempt_id"])
        seen_ids.add(attempt["attempt_id"])

        _require(attempt["specimen_group"] in GROUPS, "BAD_SPECIMEN_GROUP",
                 "specimen_group must be one of %s" % (GROUPS,))
        _require(attempt["cell"] in CELLS, "BAD_CELL",
                 "cell must be one of %s" % (CELLS,))
        for field in ("light_id", "specimen_id"):
            _require(isinstance(attempt[field], str) and attempt[field],
                     "BAD_IDENTIFIER", "%s must be a non-empty string" % field)
        for field in ("replicate_index", "attempt_index"):
            value = attempt[field]
            _require(isinstance(value, int) and not isinstance(value, bool),
                     "BAD_INDEX", "%s must be an integer" % field)
        _require(attempt["replicate_index"] >= 1, "BAD_INDEX",
                 "replicate_index must be >= 1")
        _require(attempt["attempt_index"] >= 0, "BAD_INDEX",
                 "attempt_index must be >= 0")
        _require(attempt["transport_status"] in ("OK", "TECHNICAL_FAILURE"),
                 "BAD_TRANSPORT_STATUS", "transport_status is not a registered value")
        for field in ("schema_valid", "stamp_valid", "cache_hit", "route_match",
                      "lens_valid", "refusal"):
            _require(isinstance(attempt[field], bool), "BAD_FLAG",
                     "%s must be a boolean" % field)
        score = attempt["score"]
        if score is not None:
            _require(isinstance(score, int) and not isinstance(score, bool),
                     "BAD_SCORE", "score must be an integer or null")
            _require(1 <= score <= K, "BAD_SCORE",
                     "score must lie in 1..%d" % K)

        key = (attempt["light_id"], attempt["specimen_id"], attempt["cell"],
               attempt["replicate_index"], attempt["attempt_index"])
        _require(key not in seen_coords, "DUPLICATE_ATTEMPT_COORDINATE",
                 "duplicate attempt coordinate %r" % (key,))
        seen_coords.add(key)

        prior = group_of_specimen.setdefault(attempt["specimen_id"],
                                             attempt["specimen_group"])
        _require(prior == attempt["specimen_group"], "SPECIMEN_GROUP_CONFLICT",
                 "specimen %r appears in two specimen groups"
                 % attempt["specimen_id"])
        _require(attempt["replicate_index"] <= expected_n, "REPLICATE_OUT_OF_RANGE",
                 "replicate_index exceeds expected_n")
    return payload


def classify(attempt, r_max):
    """Return (selectable, reasons) for one attempt."""
    reasons = []
    if attempt["transport_status"] != "OK":
        reasons.append("TRANSPORT_FAILURE")
    if not attempt["schema_valid"]:
        reasons.append("SCHEMA_INVALID")
    if not attempt["stamp_valid"]:
        reasons.append("STAMP_INVALID")
    if not attempt["route_match"]:
        reasons.append("ROUTE_MISMATCH")
    if not attempt["lens_valid"]:
        reasons.append("LENS_INVALID")
    if attempt["score"] is None:
        reasons.append("NO_VALID_SCORE")
    if attempt["cache_hit"]:
        reasons.append("CACHE_HIT_DEVIATION")
    if attempt["attempt_index"] > r_max:
        reasons.append("BEYOND_R_MAX")
    return (not reasons), reasons


def aggregate(payload):
    validate_archive(payload)
    config = payload["config"]
    expected_n = config["expected_n"]
    r_max = config["r_max"]
    attempts = payload["attempts"]

    groups = {}
    for position, attempt in enumerate(attempts):
        key = (attempt["light_id"], attempt["specimen_id"], attempt["cell"],
               attempt["replicate_index"])
        groups.setdefault(key, []).append((position, attempt))

    selected = []
    unselected = []
    deviations = []
    selected_by_key = {}

    for key in sorted(groups):
        # Attempt order is carried by attempt_index, never by row position
        # (anchor A16), so the physical ordering of the input array is
        # irrelevant to the result.
        ordered = sorted(groups[key], key=lambda item: item[1]["attempt_index"])
        chosen = None
        for _position, attempt in ordered:
            selectable, reasons = classify(attempt, r_max)
            if attempt["cache_hit"]:
                deviations.append({
                    "class": "CACHE_HIT",
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "specimen_id": attempt["specimen_id"],
                    "cell": attempt["cell"],
                    "replicate_index": attempt["replicate_index"],
                    "disposition": "PAUSE_FOR_DEVIATION_REVIEW",
                })
            if not attempt["route_match"] or not attempt["stamp_valid"]:
                deviations.append({
                    "class": "ROUTE_OR_STAMP_MISMATCH",
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "disposition": "PAUSE_INSTRUMENT",
                })
            if not attempt["lens_valid"]:
                deviations.append({
                    "class": "LENS_INVALID",
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "disposition": "APPARATUS_CHANGE_REVIEW",
                })
            if attempt["attempt_index"] > r_max:
                deviations.append({
                    "class": "BEYOND_R_MAX",
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "specimen_id": attempt["specimen_id"],
                    "cell": attempt["cell"],
                    "replicate_index": attempt["replicate_index"],
                    "disposition": "NOT_ELIGIBLE_FOR_SELECTION",
                })
            if selectable and chosen is None:
                chosen = attempt
                selected.append({
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "specimen_id": attempt["specimen_id"],
                    "specimen_group": attempt["specimen_group"],
                    "cell": attempt["cell"],
                    "replicate_index": attempt["replicate_index"],
                    "attempt_index": attempt["attempt_index"],
                    "score": attempt["score"],
                    "refusal": attempt["refusal"],
                })
                selected_by_key[key] = attempt
            else:
                unselected.append({
                    "attempt_id": attempt["attempt_id"],
                    "light_id": attempt["light_id"],
                    "specimen_id": attempt["specimen_id"],
                    "specimen_group": attempt["specimen_group"],
                    "cell": attempt["cell"],
                    "replicate_index": attempt["replicate_index"],
                    "attempt_index": attempt["attempt_index"],
                    "score": attempt["score"],
                    "refusal": attempt["refusal"],
                    "reasons": reasons if reasons else ["LATER_THAN_FIRST_VALID"],
                })

    # Missing replicates: every scheduled (light, specimen, cell, replicate)
    # coordinate that never produced a selectable attempt.
    coordinates = {}
    for attempt in attempts:
        coordinates.setdefault(
            (attempt["light_id"], attempt["specimen_id"],
             attempt["specimen_group"], attempt["cell"]), set()).add(
                attempt["replicate_index"])

    missing = []
    for (light_id, specimen_id, group, cell) in sorted(coordinates):
        for replicate in range(1, expected_n + 1):
            key = (light_id, specimen_id, cell, replicate)
            if key in selected_by_key:
                continue
            present = [a for _p, a in groups.get(key, [])]
            if not present:
                code = "NO_ATTEMPT_RECORDED"
            else:
                code = "R_MAX_EXHAUSTED_WITHOUT_VALID_RESPONSE"
            missing.append({
                "light_id": light_id,
                "specimen_id": specimen_id,
                "specimen_group": group,
                "cell": cell,
                "replicate_index": replicate,
                "terminal_failure_code": code,
                "attempts_recorded": len(present),
            })

    count_payload, cell_totals = _build_count_payload(
        selected, payload.get("analysis_config", {}))

    refusal = _refusal_summary(selected, config)
    for entry in refusal["limit_crossings"]:
        deviations.append({
            "class": "REFUSAL_LIMIT_CROSSED",
            "detail": entry,
            "disposition": "INSTRUMENT_VALIDITY_NOT_CLEARED",
        })

    unequal = _unequal_totals(cell_totals)

    analysis_eligible = (
        not missing
        and not deviations
        and not unequal
        and count_payload is not None
    )

    return {
        "schema_version": AGGREGATE_SCHEMA,
        "archive_id": payload["archive_id"],
        "apparatus_status": "DEVELOPMENT_ONLY_NOT_EXECUTION_ELIGIBLE",
        "analysis_eligible": analysis_eligible,
        "attempt_count": len(attempts),
        "selected_response_count": len(selected),
        "selected_responses": selected,
        "technical_or_unselected_attempts": unselected,
        "missing_replicates": missing,
        "global_deviations": deviations,
        "refusal_summary": refusal,
        "unequal_valid_response_totals": unequal,
        "count_payload": count_payload if count_payload is not None else {},
        "count_payload_complete": count_payload is not None,
    }


def _build_count_payload(selected, analysis_config):
    """Assemble an ordinal-counts payload from the selected responses.

    Returns None when the selection does not cover the complete registered
    design (three lights, six semantic and four mechanical specimens), which is
    reported rather than padded or imputed.
    """
    buckets = {}
    totals = {}
    for row in selected:
        key = (row["light_id"], row["specimen_group"], row["specimen_id"],
               row["cell"])
        counts = buckets.setdefault(key, [0] * K)
        counts[row["score"] - 1] += 1
        totals[key] = totals.get(key, 0) + 1

    light_ids = sorted({row["light_id"] for row in selected})
    if len(light_ids) != 3:
        return None, totals

    lights = []
    for light_id in light_ids:
        light = {"id": light_id,
                 "validity": {"provenance": True, "cache": True, "schema": True,
                              "local_lens": True, "refusal": True},
                 "semantic_specimens": [], "mechanical_specimens": []}
        for group, target_key, expected in (("semantic", "semantic_specimens", 6),
                                            ("mechanical", "mechanical_specimens", 4)):
            specimen_ids = sorted({
                row["specimen_id"] for row in selected
                if row["light_id"] == light_id and row["specimen_group"] == group})
            if len(specimen_ids) != expected:
                return None, totals
            for specimen_id in specimen_ids:
                cells = {}
                for cell in CELLS:
                    counts = buckets.get((light_id, group, specimen_id, cell))
                    if counts is None or sum(counts) == 0:
                        return None, totals
                    cells[cell] = {"counts": counts}
                light[target_key].append({"id": specimen_id, "cells": cells})
        lights.append(light)

    payload = {
        "schema_version": COUNTS_SCHEMA,
        "analysis_id": None,
        "config": analysis_config,
        "lights": lights,
    }
    return payload, totals


def _refusal_summary(selected, config):
    """Refusal rates and the two registered differential comparisons."""
    by_cell = {}
    for row in selected:
        key = (row["light_id"], row["specimen_id"], row["cell"])
        entry = by_cell.setdefault(key, {"n": 0, "refusals": 0})
        entry["n"] += 1
        if row["refusal"]:
            entry["refusals"] += 1

    total = len(selected)
    refusals = sum(1 for row in selected if row["refusal"])
    overall_rate = (refusals / float(total)) if total else 0.0

    light_cell = {}
    for (light_id, _specimen_id, cell), entry in by_cell.items():
        agg = light_cell.setdefault((light_id, cell), {"n": 0, "refusals": 0})
        agg["n"] += entry["n"]
        agg["refusals"] += entry["refusals"]

    def rate(light_id, cell):
        agg = light_cell.get((light_id, cell))
        if not agg or agg["n"] == 0:
            return None
        return agg["refusals"] / float(agg["n"])

    crossings = []
    differentials = []
    light_ids = sorted({light_id for light_id, _cell in light_cell})
    for light_id in light_ids:
        for left, right in (("00", "0B"), ("A0", "AB")):
            left_rate = rate(light_id, left)
            right_rate = rate(light_id, right)
            if left_rate is None or right_rate is None:
                continue
            diff = abs(left_rate - right_rate)
            record = {"light_id": light_id, "comparison": "%s_vs_%s" % (left, right),
                      "left_rate": left_rate, "right_rate": right_rate,
                      "absolute_difference": diff}
            differentials.append(record)
            if diff > float(config["refusal_differential_limit"]):
                crossings.append(dict(record, limit_type="differential",
                                      limit=float(config["refusal_differential_limit"])))

    if overall_rate > float(config["refusal_overall_limit"]):
        crossings.append({"limit_type": "overall", "rate": overall_rate,
                          "limit": float(config["refusal_overall_limit"])})

    return {
        "overall_rate": overall_rate,
        "overall_refusals": refusals,
        "selected_total": total,
        "by_light_cell": {"%s|%s" % (light_id, cell): dict(agg)
                          for (light_id, cell), agg in sorted(light_cell.items())},
        "differentials": differentials,
        "limit_crossings": crossings,
    }


def _unequal_totals(cell_totals):
    """Report cells whose valid-response totals differ within a specimen."""
    by_specimen = {}
    for (light_id, group, specimen_id, cell), total in cell_totals.items():
        by_specimen.setdefault((light_id, group, specimen_id), {})[cell] = total
    out = []
    for key in sorted(by_specimen):
        per_cell = by_specimen[key]
        values = set(per_cell.values())
        if len(values) > 1:
            out.append({
                "light_id": key[0], "specimen_group": key[1], "specimen_id": key[2],
                "cell_totals": per_cell,
            })
    return out
