"""Deterministic construction of the attempt-archive adversary fixtures.

Covers every challenge enumerated in locked contract section 10. Expectations
are expressed as *named invariants* rather than exact error strings wherever
the distribution leaves the disposition open (see AMB-06, AMB-07, AMB-08,
AMB-14); the invariants are the properties contract section 10 actually
demands, namely that "invalid attempts, missingness, refusals, and deviations
remain observable and cannot disappear through denominator changes or
favorable replacement selection".
"""

import copy
import json
import os

from . import roster

from .workspace import ROOT
FIXTURE_ROOT = os.path.join(ROOT, "fixtures")

CELLS = ("00", "A0", "0B", "AB")
SEMANTIC = list(roster.SEMANTIC_ROSTER)
MECHANICAL = list(roster.MECHANICAL_ROSTER)
LIGHTS = ["L1", "L2", "L3"]

ANALYSIS_CONFIG = {"alpha": {"primary": 0.05, "c4": 0.05, "c5": 0.05},
                   "d_near": 0.9}

BASE_CONFIG = {"expected_n": 3, "r_max": 2,
               "refusal_overall_limit": 0.20,
               "refusal_differential_limit": 0.20}

# Scores chosen so the assembled count payload shows a clean attenuation
# pattern: 00 at the ceiling, 0B at the floor, A0 and AB tied mid-scale.
CELL_SCORE = {"00": 10, "A0": 6, "0B": 1, "AB": 6}


def attempt(attempt_id, light, specimen, group, cell, replicate, index=0,
            score=None, **overrides):
    record = {
        "attempt_id": attempt_id,
        "light_id": light,
        "specimen_id": specimen,
        "specimen_group": group,
        "cell": cell,
        "replicate_index": replicate,
        "attempt_index": index,
        "transport_status": "OK",
        "schema_valid": True,
        "stamp_valid": True,
        "cache_hit": False,
        "route_match": True,
        "lens_valid": True,
        "refusal": False,
        "score": CELL_SCORE[cell] if score is None else score,
    }
    record.update(overrides)
    return record


def base_attempts(expected_n=3):
    """A complete, fully valid archive over the registered design."""
    records = []
    for light in LIGHTS:
        for group, specimens in (("semantic", SEMANTIC), ("mechanical", MECHANICAL)):
            for specimen in specimens:
                for cell in CELLS:
                    for replicate in range(1, expected_n + 1):
                        records.append(attempt(
                            "%s-%s-%s-r%d" % (light, specimen, cell, replicate),
                            light, specimen, group, cell, replicate))
    return records


def archive(archive_id, attempts, config=None):
    return {
        "schema_version": "blackbox.ordinal.attempt-archive.v0.1",
        "archive_id": archive_id,
        "config": copy.deepcopy(config or BASE_CONFIG),
        "analysis_config": copy.deepcopy(ANALYSIS_CONFIG),
        "attempts": attempts,
    }


def scenario(scenario_id, description, payload, invariants, strength,
             contract_refs, notes=""):
    return {
        "scenario_id": scenario_id,
        "family": "archive",
        "target": "aggregate",
        "description": description,
        "contract_refs": contract_refs,
        "assertion_strength": strength,
        "notes": notes,
        "payload": payload,
        "expected": {"invariants": invariants},
        "replicate_classification": {
            "n_class": "ARCHIVE_STRUCTURAL_FIXTURE",
            "expected_n": payload["config"]["expected_n"],
            "study_candidate_N": [8, 10, 12, 16, 20, 30],
            "usable_as_study_evidence": False,
            "rationale": (
                "Archive fixtures test attempt accounting, selection, "
                "missingness, refusal and deviation handling. Their "
                "expected_n is a structural parameter of the archive, not a "
                "study replicate count, and these fixtures are not evidence "
                "about behaviour at any candidate N (operator decision D5 "
                "labelling discipline)."),
        },
    }


def find(records, light, specimen, cell, replicate):
    for index, record in enumerate(records):
        if (record["light_id"] == light and record["specimen_id"] == specimen
                and record["cell"] == cell
                and record["replicate_index"] == replicate):
            return index
    raise KeyError((light, specimen, cell, replicate))


def build_archive_panel():
    panel = []

    # --- AR-00: clean baseline -------------------------------------------------
    panel.append(scenario(
        "AR-00-CLEAN-COMPLETE",
        "A complete, fully valid archive over the registered design: three "
        "lights, six semantic and four mechanical specimens, four cells, three "
        "replicates, one valid attempt each. Nothing may be dropped, nothing "
        "may be missing, and the count payload must reproduce the selected "
        "scores exactly.",
        archive("AR-00", base_attempts()),
        ["no_attempt_lost", "partition_is_exact", "first_valid_selected",
         "counts_match_selected", "no_missing_replicates",
         "analysis_eligible_true", "order_invariance"],
        "ABSOLUTE", ["contract 10"],
        "This is the specificity baseline for the aggregate target: a clean "
        "archive must not be flagged."))

    # --- AR-01: favourable later attempt --------------------------------------
    records = base_attempts()
    index = find(records, "L1", "sample-01", "AB", 1)
    records[index]["score"] = 4
    records.insert(index + 1, attempt(
        "L1-sample-01-AB-r1-late", "L1", "sample-01", "semantic", "AB", 1, index=1, score=9))
    panel.append(scenario(
        "AR-01-FAVOURABLE-LATER-ATTEMPT",
        "A valid attempt at index 0 scoring 4 is followed by a valid attempt at "
        "index 1 scoring 9. Section 11.2 retains the FIRST valid response, so "
        "the selected score must be 4 (anchor A16). Selecting 9 is the "
        "registered 'favorable attempt replacement' defect.",
        archive("AR-01", records),
        ["no_attempt_lost", "partition_is_exact", "first_valid_selected",
         "counts_match_selected", "selected_score_is",
         "later_attempt_still_reported"],
        "ABSOLUTE", ["contract 10", "contract 11", "prereg 11.2", "anchor A16"],
        "selected_score_is: (L1,sample-01,AB,1) -> 4"))

    # --- AR-02: technical failure then valid replacement -----------------------
    records = base_attempts()
    index = find(records, "L1", "sample-02", "00", 1)
    records[index].update({"transport_status": "TECHNICAL_FAILURE", "score": None})
    records.insert(index + 1, attempt(
        "L1-sample-02-00-r1-retry", "L1", "sample-02", "semantic", "00", 1, index=1))
    index = find(records, "L1", "sample-02", "0B", 2)
    records[index].update({"schema_valid": False, "score": None})
    records.insert(index + 1, attempt(
        "L1-sample-02-0B-r2-retry", "L1", "sample-02", "semantic", "0B", 2, index=1))
    panel.append(scenario(
        "AR-02-TECHNICAL-THEN-VALID",
        "A transport failure and a schema failure each followed by a valid "
        "replacement inside R_MAX. Replacement is permitted for exactly these "
        "enumerated technical categories, the replacement score is selected, "
        "and both failed attempts remain visible in the output.",
        archive("AR-02", records),
        ["no_attempt_lost", "partition_is_exact", "first_valid_selected",
         "counts_match_selected", "no_missing_replicates",
         "failed_attempts_reported"],
        "ABSOLUTE", ["contract 10", "prereg 11.2"]))

    # --- AR-03: attempt beyond R_MAX ------------------------------------------
    records = base_attempts()
    index = find(records, "L1", "sample-03", "AB", 1)
    records[index].update({"transport_status": "TECHNICAL_FAILURE", "score": None})
    records.insert(index + 1, attempt(
        "L1-sample-03-AB-r1-a1", "L1", "sample-03", "semantic", "AB", 1, index=1,
        transport_status="TECHNICAL_FAILURE", score=None))
    records.insert(index + 2, attempt(
        "L1-sample-03-AB-r1-a2", "L1", "sample-03", "semantic", "AB", 1, index=2,
        transport_status="TECHNICAL_FAILURE", score=None))
    records.insert(index + 3, attempt(
        "L1-sample-03-AB-r1-a3", "L1", "sample-03", "semantic", "AB", 1, index=3, score=9))
    panel.append(scenario(
        "AR-03-BEYOND-R-MAX",
        "Three consecutive technical failures exhaust r_max = 2, then a fourth "
        "attempt at index 3 returns a valid score. Index 3 lies outside the cap "
        "under BOTH readings of r_max recorded in AMB-06, so it must not be "
        "selected; the replicate is missing under a terminal failure code.",
        archive("AR-03", records),
        ["no_attempt_lost", "partition_is_exact", "beyond_rmax_not_selected",
         "missing_replicate_reported", "analysis_eligible_false"],
        "ABSOLUTE", ["contract 10", "prereg 11.2"],
        "missing_replicate_reported: (L1,sample-03,AB,1)"))

    # --- AR-04: missing scheduled replicate -----------------------------------
    records = [r for r in base_attempts()
               if not (r["light_id"] == "L2" and r["specimen_id"] == "sample-04"
                       and r["cell"] == "A0" and r["replicate_index"] == 3)]
    panel.append(scenario(
        "AR-04-MISSING-REPLICATE",
        "One scheduled replicate has no attempt at all. It must appear in "
        "missing_replicates rather than silently shrinking the denominator, "
        "and the surviving cell total must not be padded or imputed.",
        archive("AR-04", records),
        ["no_attempt_lost", "partition_is_exact", "missing_replicate_reported",
         "analysis_eligible_false", "unequal_totals_reported"],
        "ABSOLUTE", ["contract 10"],
        "missing_replicate_reported: (L2,sample-04,A0,3)"))

    # --- AR-05: duplicate attempt id ------------------------------------------
    records = base_attempts()
    clone = copy.deepcopy(records[0])
    clone["replicate_index"] = 2
    records.append(clone)
    panel.append(scenario(
        "AR-05-DUPLICATE-ATTEMPT-ID",
        "Two records share one attempt_id. An attempt identifier is the "
        "primary key of an immutable measurement record, so the archive must "
        "be rejected or the collision explicitly reported; it must never be "
        "silently collapsed.",
        archive("AR-05", records),
        ["rejected_or_explicitly_flagged"],
        "ABSOLUTE", ["contract 10"]))

    # --- AR-06: duplicate attempt coordinate ----------------------------------
    records = base_attempts()
    clone = copy.deepcopy(records[0])
    clone["attempt_id"] = clone["attempt_id"] + "-dup"
    clone["score"] = 3
    records.append(clone)
    panel.append(scenario(
        "AR-06-DUPLICATE-COORDINATE",
        "Two distinct attempts claim the same (light, specimen, cell, "
        "replicate, attempt_index) coordinate with different scores. The "
        "collision must be rejected or explicitly reported; choosing one "
        "silently would make the selection rule non-deterministic.",
        archive("AR-06", records),
        ["rejected_or_explicitly_flagged"],
        "ABSOLUTE", ["contract 10"]))

    # --- AR-07: cache hit then valid ------------------------------------------
    records = base_attempts()
    index = find(records, "L1", "sample-05", "00", 1)
    records[index].update({"cache_hit": True})
    records.insert(index + 1, attempt(
        "L1-sample-05-00-r1-post-cache", "L1", "sample-05", "semantic", "00", 1, index=1))
    panel.append(scenario(
        "AR-07-CACHE-HIT-THEN-VALID",
        "A cache hit is followed by an otherwise valid response. Prompt-cache "
        "hits are not part of the planned apparatus; the event must remain "
        "visible and must trigger deviation handling rather than being quietly "
        "replaced. AMB-07 records that the exact disposition is unsealed, so "
        "only observability is asserted.",
        archive("AR-07", records),
        ["no_attempt_lost", "partition_is_exact", "cache_event_observable"],
        "ABSOLUTE", ["contract 10", "prereg 7", "prereg 11.1"],
        "Reading-independent: whichever disposition is correct, the cache "
        "event may not disappear."))

    # --- AR-08: route, stamp and lens mismatch --------------------------------
    records = base_attempts()
    records[find(records, "L2", "sample-01", "00", 1)].update({"route_match": False})
    records[find(records, "L2", "sample-01", "A0", 1)].update({"stamp_valid": False})
    records[find(records, "L2", "sample-01", "0B", 1)].update({"lens_valid": False})
    panel.append(scenario(
        "AR-08-ROUTE-STAMP-LENS-MISMATCH",
        "One route mismatch, one invalid stamp and one invalid lens record. "
        "Section 11.1 makes a missing or invalid required stamp invalidate the "
        "attempt, and section 11.3 routes an unexpected route or a lens change "
        "to deviation handling rather than automatic retry.",
        archive("AR-08", records),
        ["no_attempt_lost", "partition_is_exact", "deviation_observable",
         "missing_replicate_reported", "analysis_eligible_false"],
        "ABSOLUTE", ["contract 10", "prereg 11.1", "prereg 11.3"],
        "missing_replicate_reported: (L2,sample-01,00,1)"))

    # --- AR-09: schema-valid refusals carrying valid scores -------------------
    records = base_attempts()
    for specimen in ("sample-01", "sample-02"):
        for replicate in (1, 2):
            records[find(records, "L3", specimen, "AB", replicate)].update(
                {"refusal": True, "score": 6})
    panel.append(scenario(
        "AR-09-REFUSAL-WITH-VALID-SCORE",
        "Schema-valid refusals that supply the required integer score. Section "
        "11.2 is explicit that such a response REMAINS in the cell "
        "distribution with its supplied score and an immutable refusal flag; "
        "no score may be imputed, replaced or dropped.",
        archive("AR-09", records),
        ["no_attempt_lost", "partition_is_exact", "refusal_scores_retained",
         "counts_match_selected", "no_missing_replicates",
         "refusal_rate_reported"],
        "ABSOLUTE", ["contract 10", "prereg 11.2"]))

    # --- AR-10: refusal without a valid score ---------------------------------
    records = base_attempts()
    index = find(records, "L3", "sample-03", "AB", 1)
    records[index].update({"refusal": True, "score": None})
    records.insert(index + 1, attempt(
        "L3-sample-03-AB-r1-retry", "L3", "sample-03", "semantic", "AB", 1, index=1))
    panel.append(scenario(
        "AR-10-REFUSAL-WITHOUT-SCORE",
        "A refusal with no valid score is a structurally invalid response and "
        "falls under the ordinary retry cap. The replacement is selected, the "
        "invalid refusal remains reported, and it must not be counted as a "
        "scored response.",
        archive("AR-10", records),
        ["no_attempt_lost", "partition_is_exact", "first_valid_selected",
         "counts_match_selected", "no_missing_replicates",
         "failed_attempts_reported"],
        "ABSOLUTE", ["contract 10", "prereg 11.2"]))

    # --- AR-11: differential refusal across both registered comparisons -------
    records = base_attempts()
    for specimen in SEMANTIC:
        for replicate in (1, 2, 3):
            records[find(records, "L1", specimen, "0B", replicate)].update(
                {"refusal": True, "score": 1})
            records[find(records, "L1", specimen, "AB", replicate)].update(
                {"refusal": True, "score": 6})
    panel.append(scenario(
        "AR-11-DIFFERENTIAL-REFUSAL",
        "Every 0B and AB response on light L1 is a refusal while 00 and A0 "
        "carry none. Both registered comparisons, 00-versus-0B and "
        "A0-versus-AB, therefore show the maximum possible differential. This "
        "is unambiguous under every candidate denominator in AMB-08, so the "
        "limit must be crossed and the affected confirmatory inference "
        "withheld.",
        archive("AR-11", records),
        ["no_attempt_lost", "partition_is_exact", "refusal_rate_reported",
         "differential_refusal_flagged", "analysis_eligible_false",
         "refusal_scores_retained"],
        "ABSOLUTE", ["contract 10", "contract 9", "prereg 11.2"]))

    # --- AR-12: out-of-range score --------------------------------------------
    records = base_attempts()
    records[find(records, "L1", "sample-01", "00", 1)]["score"] = 11
    panel.append(scenario(
        "AR-12-OUT-OF-RANGE-SCORE",
        "A score of 11 lies outside the registered 1-10 ordinal scale. Input "
        "rejection is part of the observable target behaviour; the value must "
        "never be clipped, rounded or accepted.",
        archive("AR-12", records),
        ["rejected_or_explicitly_flagged", "no_silent_coercion"],
        "ABSOLUTE", ["contract 3", "contract 10"]))

    # --- AR-13: non-integer score ---------------------------------------------
    records = base_attempts()
    records[find(records, "L1", "sample-01", "00", 1)]["score"] = 7.5
    panel.append(scenario(
        "AR-13-NON-INTEGER-SCORE",
        "A non-integer score contradicts the ordered-categorical measurement "
        "model. It must be rejected, not rounded into a neighbouring category.",
        archive("AR-13", records),
        ["rejected_or_explicitly_flagged", "no_silent_coercion"],
        "ABSOLUTE", ["contract 3", "contract 10", "prereg 3"]))

    # --- AR-14: wrong specimen group ------------------------------------------
    records = base_attempts()
    for record in records:
        if record["specimen_id"] == "control-01" and record["light_id"] == "L1":
            record["specimen_group"] = "semantic"
    panel.append(scenario(
        "AR-14-WRONG-SPECIMEN-GROUP",
        "Mechanical control M1 is relabelled as a semantic specimen on light "
        "L1. C5 uses exactly four separate controls and they may never enter "
        "the six-specimen primary aggregate, so the group conflict must be "
        "rejected or explicitly reported.",
        archive("AR-14", records),
        ["rejected_or_explicitly_flagged", "controls_not_pooled_into_primary"],
        "ABSOLUTE", ["contract 6", "contract 10", "prereg 3.2"]))

    # --- AR-15: unregistered cell ---------------------------------------------
    records = base_attempts()
    records[find(records, "L1", "sample-01", "00", 1)]["cell"] = "0A"
    panel.append(scenario(
        "AR-15-UNREGISTERED-CELL",
        "An attempt claims a cell label outside the registered four artifact "
        "states. The archive must be rejected.",
        archive("AR-15", records),
        ["rejected_or_explicitly_flagged"],
        "ABSOLUTE", ["contract 10"]))

    # --- AR-16: out-of-order records ------------------------------------------
    records = base_attempts()
    index = find(records, "L1", "sample-06", "00", 1)
    records[index].update({"transport_status": "TECHNICAL_FAILURE", "score": None})
    late = attempt("L1-sample-06-00-r1-retry", "L1", "sample-06", "semantic", "00", 1,
                   index=1, score=10)
    records.insert(0, late)  # physically first, logically second
    reversed_records = list(reversed(records))
    panel.append(scenario(
        "AR-16-OUT-OF-ORDER-RECORDS",
        "The replacement attempt appears physically before the attempt it "
        "replaces, and the whole array is then reversed. Attempt order is "
        "carried by attempt_index, not by row position, so the scientific "
        "result must be identical to the ordered archive (anchor A16).",
        archive("AR-16", reversed_records),
        ["no_attempt_lost", "partition_is_exact", "first_valid_selected",
         "order_invariance", "counts_match_selected"],
        "ABSOLUTE", ["contract 10", "amendment 5", "anchor A16"]))

    # --- AR-17: unequal valid-response totals ---------------------------------
    records = [r for r in base_attempts()
               if not (r["light_id"] == "L1" and r["specimen_id"] == "sample-02"
                       and r["cell"] == "AB" and r["replicate_index"] in (2, 3))]
    panel.append(scenario(
        "AR-17-UNEQUAL-VALID-TOTALS",
        "One cell ends with one valid response while its three siblings have "
        "three. The imbalance must be reported rather than equalised by "
        "dropping responses elsewhere or by imputing the missing ones.",
        archive("AR-17", records),
        ["no_attempt_lost", "partition_is_exact", "unequal_totals_reported",
         "missing_replicate_reported", "analysis_eligible_false"],
        "ABSOLUTE", ["contract 10"],
        "missing_replicate_reported: (L1,sample-02,AB,2)"))

    return panel


def write_panel(panel, subdirectory="archive"):
    directory = os.path.join(FIXTURE_ROOT, "scenarios", subdirectory)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    written = []
    for entry in panel:
        path = os.path.join(directory, entry["scenario_id"] + ".json")
        with open(path, "w") as handle:
            json.dump(entry, handle, indent=2, sort_keys=True)
            handle.write("\n")
        written.append(path)
    return written


def main():
    written = write_panel(build_archive_panel())
    for path in written:
        print(os.path.relpath(path, FIXTURE_ROOT))
    print("archive scenarios written: %d" % len(written))


if __name__ == "__main__":
    main()
