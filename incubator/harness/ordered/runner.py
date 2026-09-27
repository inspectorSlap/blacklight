"""The v1.6.0 campaign driver.

Target-agnostic: it drives any object exposing ``analyze(payload)``. In the
standalone campaign that object is the HTTP client talking to the reviewed
engine behind the four documented routes; in local qualification it is the same
reviewed engine invoked in process. Both reach
``ordinal_engine.engine.analyze`` and nothing else.

The driver is resumable. Completed replications are recovered from the evidence
index, so a stopped campaign continues rather than reissuing work, and exact
request and response bytes are preserved for every replication.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import datetime
import json

from .. import campaign as predecessor_evidence
from . import campaign as ordered_campaign
from . import events, family, grid, synthetic
from .canonical import canonical_sha256
from .statuses import assert_consumable

EVIDENCE_VERSION = predecessor_evidence.EVIDENCE_VERSION


class CampaignAborted(Exception):
    """Raised when the campaign cannot continue safely."""


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_two_look(target, store=None, configurations=None, meta_digest=None,
                 integrity_digest=None, progress=None, first_look_stop_after=None):
    """Execute the sealed C4 two-look procedure exactly.

    Look one runs every configuration at the registered first-look size. If no
    stream returns CONTINUE the campaign stops there. If any stream continues,
    only the configurations carrying those streams are escalated to the
    second-look size; because completed replications are replayed from evidence
    rather than reissued, the second look is cumulative over the first, and the
    registered second-look critical values apply to the cumulative count.

    Stream decisions that were already terminal at look one are preserved, not
    re-decided.

    ``first_look_stop_after`` bounds the first look for local qualification
    only, exactly as ``run_campaign``'s ``stop_after`` does. The standalone
    campaign never passes it, so the sealed first-look size always applies in
    production.
    """
    plan = ordered_campaign.Plan()
    if configurations is None:
        configurations = grid.build_configurations()

    first = run_campaign(target, look_index=0, replications=plan.looks[0],
                         configurations=configurations, store=store,
                         meta_digest=meta_digest, integrity_digest=integrity_digest,
                         progress=progress, stop_after=first_look_stop_after)

    continuing = [flat for flat, entry in first["gated"].items()
                  if entry["verdict"] == ordered_campaign.VERDICT_CONTINUE]

    report = dict(first)
    report["looks_executed"] = 1
    report["streams_continuing_after_look_one"] = len(continuing)
    report["first_look"] = {
        "replications_per_configuration": plan.looks[0],
        "requests_issued": first["evidence_identity_verifications"],
        "verdict_counts": dict(first["verdict_counts"]),
    }
    report["second_look"] = {"executed": False, "escalated_streams": 0,
                             "escalated_configurations": [],
                             "replications_per_configuration": 0,
                             "requests_issued": 0}

    if not continuing:
        report["total_requests_issued"] = first["evidence_identity_verifications"]
        return report

    # Configuration identity comes from the registered manifest, not from
    # splitting the reporting key: a stream_id contains the same delimiter, so
    # positional parsing is not a safe identity.
    escalated_ids = sorted({family.configuration_of(flat) for flat in continuing})
    escalated = [c for c in configurations
                 if c["configuration_id"] in escalated_ids]

    # The second look legitimately tallies only the escalated configurations, so
    # it states that exact registered subset and is held to it exactly.
    second = run_campaign(target, look_index=1, replications=plan.looks[1],
                          configurations=escalated, store=store,
                          meta_digest=meta_digest,
                          integrity_digest=integrity_digest, progress=progress,
                          expected_configurations=escalated_ids)

    return merge_looks(report, first, second, continuing, escalated_ids, plan)


def merge_looks(report, first, second, continuing, escalated_ids, plan):
    """Combine a first and second look into one cumulative whole-family result.

    Separated so it can be exercised directly with deterministic look results,
    without standing up a campaign. ``run_two_look`` calls this and nothing
    else does the merging, so what a test drives here is what production runs.
    """
    # Terminal look-one decisions stand; only continuing streams are re-decided,
    # and they are re-decided on the cumulative count at the second look. Each
    # continuing stream is updated exactly once.
    continuing = set(continuing)
    merged = dict(first["gated"])
    updated = set()
    for flat, entry in second["gated"].items():
        if flat not in continuing:
            # A stream in an escalated configuration that was already terminal
            # at look one keeps its look-one decision untouched.
            continue
        if flat in updated:
            raise CampaignAborted(
                "continuing stream %s was updated more than once" % flat)
        merged[flat] = dict(entry)
        merged[flat]["resolved_at_look"] = 2
        updated.add(flat)
    if updated != continuing:
        raise CampaignAborted(
            "second look did not return every continuing stream: %d of %d updated"
            % (len(updated), len(continuing)))

    # The final cumulative result is a whole-family object and is validated as
    # one, whatever subset the second look ran over.
    family.assert_exact_set_equality(
        family.stream_tuple(family.stream_for_flat_key(flat)) for flat in merged)
    family.verify_per_event_cardinality(
        family.stream_tuple(family.stream_for_flat_key(flat)) for flat in merged)

    verdict_counts = {}
    for entry in merged.values():
        verdict_counts[entry["verdict"]] = verdict_counts.get(entry["verdict"], 0) + 1

    # Zero-tolerance, blocking conditions and report-only counts are cumulative
    # across both looks: a failure that arises only at look two must reach the
    # final result and invalidate the campaign.
    zero_tolerance = {}
    for name in set(first["zero_tolerance"]) | set(second["zero_tolerance"]):
        events = (first["zero_tolerance"].get(name, {}).get("events", 0)
                  + second["zero_tolerance"].get(name, {}).get("events", 0))
        zero_tolerance[name] = {
            "events": events,
            "verdict": ordered_campaign.VERDICT_FAIL if events else
                       ordered_campaign.VERDICT_PASS}
    zero_tolerance_failed = sorted(
        name for name, entry in zero_tolerance.items()
        if entry["verdict"] == ordered_campaign.VERDICT_FAIL)

    report_only = {}
    for name in set(first["report_only"]) | set(second["report_only"]):
        report_only[name] = {
            "events": (first["report_only"].get(name, {}).get("events", 0)
                       + second["report_only"].get(name, {}).get("events", 0)),
            "verdict": ordered_campaign.VERDICT_REPORTED}

    blocked = list(first["blocked"]) + list(second["blocked"])

    report["gated"] = merged
    report["verdict_counts"] = verdict_counts
    report["zero_tolerance"] = zero_tolerance
    report["zero_tolerance_failed"] = zero_tolerance_failed
    report["report_only"] = report_only
    report["blocked"] = blocked
    report["gated_streams"] = len(merged)
    report["looks_executed"] = 2
    report["evidence_identity_verifications"] = (
        first["evidence_identity_verifications"]
        + second["evidence_identity_verifications"])
    report["replications_replayed_from_evidence"] = (
        first["replications_replayed_from_evidence"]
        + second["replications_replayed_from_evidence"])
    report["replications_issued_this_run"] = (
        first["replications_issued_this_run"]
        + second["replications_issued_this_run"])
    report["second_look"] = {
        "executed": True,
        "escalated_streams": len(continuing),
        "escalated_configurations": list(escalated_ids),
        "replications_per_configuration": plan.looks[1],
        "requests_issued": second["evidence_identity_verifications"],
        "replications_replayed_from_first_look":
            second["replications_replayed_from_evidence"],
        "streams_updated": len(updated),
        "critical_values": {"PASS": plan.pass_critical[1],
                            "FAIL": plan.fail_critical[1]},
    }
    report["total_requests_issued"] = (first["evidence_identity_verifications"]
                                       + second["evidence_identity_verifications"])
    report["tally_digest"] = canonical_sha256(merged)
    report["campaign_valid"] = (not blocked and not zero_tolerance_failed)
    return report


def _replay_committed(store, slug, replication, configuration, truth, streams):
    """Score an already-committed replication from its stored response.

    Replay reads the preserved response bytes; it issues no request and cannot
    duplicate one. Scoring uses the same evaluator as a live replication, so an
    interrupted-then-resumed run produces the identical cumulative tally.
    """
    if store is None:
        raise CampaignAborted(
            "cannot replay replication %d without an evidence store" % replication)
    try:
        record = store.read_record(slug, replication, kind="responses")
    except KeyError as error:
        raise CampaignAborted(
            "committed replication %d of %s has no stored response to replay: %s"
            % (replication, configuration["configuration_id"], error))
    if not record.get("sha256_matches"):
        raise CampaignAborted(
            "stored response for replication %d of %s does not match its "
            "recorded digest; refusing to replay tampered evidence"
            % (replication, configuration["configuration_id"]))
    result = json.loads(record["raw"].decode("utf-8"))
    assert_consumable(result)
    return events.evaluate(result, configuration, truth, streams)


class LocalEngineTarget(object):
    """In-process target for zero-contact qualification.

    It reaches the identical reviewed function the HTTP target reaches; the only
    difference is that no socket is involved.
    """

    transport = "in-process"

    def __init__(self):
        from . import engine_bridge

        self._analyze = engine_bridge.analyze_endpoint

    def analyze(self, payload):
        return self._analyze(payload)


def run_campaign(target, look_index=0, replications=None, configurations=None,
                 store=None, meta_digest=None, integrity_digest=None,
                 progress=None, stop_after=None, expected_configurations=None):
    """Run one look of the qualification campaign.

    ``replications`` defaults to the registered look size. ``stop_after`` bounds
    the number of replications per configuration for local qualification only;
    it is never used by the standalone campaign.
    """
    plan = ordered_campaign.Plan()
    if replications is None:
        replications = plan.looks[look_index]
    if configurations is None:
        configurations = grid.build_configurations()

    tally = ordered_campaign.Tally()
    identity_checks = 0
    replayed_count = 0
    blocked = []
    per_configuration = []

    for configuration in configurations:
        configuration_id = configuration["configuration_id"]
        streams = family.streams_for(configuration_id)
        if not streams:
            raise CampaignAborted(
                "configuration %s has no registered gated stream" % configuration_id)
        truth = grid.population_truth(configuration)

        slug = store.slug(configuration_id, family.CANDIDATE_N[0]) if store else None
        completed = set()
        if store is not None:
            completed, _ = store.recover(slug)

        limit = replications if stop_after is None else min(replications, stop_after)
        pending = []
        fired_here = 0

        for replication in range(limit):
            if replication in completed:
                # Already committed by an earlier, interrupted run. It is not
                # reissued -- no duplicate request -- but it MUST still enter
                # the cumulative tally, or a resumed run would silently score
                # fewer trials than an uninterrupted one. The stored response
                # is replayed from evidence and scored by the same evaluator.
                replayed = _replay_committed(store, slug, replication,
                                             configuration, truth, streams)
                tally.add(replayed)
                replayed_count += 1
                fired_here += sum(1 for fired in replayed["gated"].values() if fired)
                continue

            ordered_input, expanded_archive = synthetic.build_ordered_input(
                configuration, replication)
            synthetic.verify_replication(
                configuration, replication, ordered_input, expanded_archive)

            try:
                result = target.analyze(ordered_input)
            except Exception as error:  # noqa: BLE001 - recorded, never masked
                blocked.append({"configuration_id": configuration_id,
                                "replication": replication,
                                "error": "%s: %s" % (type(error).__name__, error)})
                continue

            assert_consumable(result)
            identity = ordered_campaign.verify_evidence_identity(
                result, ordered_input, expanded_archive)
            identity_checks += 1

            observed = events.evaluate(result, configuration, truth, streams)
            tally.add(observed)
            fired_here += sum(1 for fired in observed["gated"].values() if fired)

            if store is not None:
                request_raw = json.dumps(ordered_input, sort_keys=True).encode("utf-8")
                response_raw = json.dumps(result, sort_keys=True).encode("utf-8")
                pending.append({
                    "cell_id": configuration_id,
                    "N": family.CANDIDATE_N[0],
                    "replication": replication,
                    "seed": ordered_input["bindings"]["score_stream_seed"],
                    "timestamp_utc": _utc_now(),
                    "meta_digest": meta_digest,
                    "integrity_digest": integrity_digest,
                    "blocked": False,
                    "error": None,
                    "transport": getattr(target, "transport", "http"),
                    "request_raw": request_raw,
                    "response_raw": response_raw,
                    "decision_record": {
                        "analysis_id": ordered_input["analysis_id"],
                        "evidence_identity": identity,
                        "gated_events_fired": sorted(
                            key[3] for key, fired in observed["gated"].items() if fired),
                        "zero_tolerance_fired": sorted(
                            name for name, fired in observed["zero_tolerance"].items() if fired),
                    },
                })
                if len(pending) >= predecessor_evidence.DEFAULT_BLOCK_SIZE:
                    store.write_block(slug, pending)
                    pending = []

            if progress is not None:
                progress(configuration_id, replication, limit)

        if store is not None and pending:
            store.write_block(slug, pending)

        per_configuration.append({
            "configuration_id": configuration_id,
            "replications": limit,
            "streams": len(streams),
            "gated_events_fired": fired_here,
        })

    adjudication = tally.adjudicate(plan, look_index, expected_configurations)

    gated = adjudication["gated"]
    verdict_counts = {}
    for entry in gated.values():
        verdict_counts[entry["verdict"]] = verdict_counts.get(entry["verdict"], 0) + 1
    zero_tolerance_failed = sorted(
        name for name, entry in adjudication["zero_tolerance"].items()
        if entry["verdict"] == ordered_campaign.VERDICT_FAIL)

    campaign_valid = not blocked and not zero_tolerance_failed
    return {
        "record_type": "BLACKBOX_ORDINAL_V1_6_0_CAMPAIGN_REPORT",
        "harness_version": "1.6.0",
        "generated_utc": _utc_now(),
        "look_index": look_index,
        "replications_per_configuration": replications,
        "configurations": len(configurations),
        "gated_streams": len(gated),
        "gated_stream_family_exact": True,
        "evidence_identity_verifications": identity_checks,
        "replications_replayed_from_evidence": replayed_count,
        "replications_issued_this_run": identity_checks,
        "verdict_counts": verdict_counts,
        "zero_tolerance": adjudication["zero_tolerance"],
        "zero_tolerance_failed": zero_tolerance_failed,
        "report_only": adjudication["report_only"],
        "per_configuration": per_configuration,
        "blocked": blocked,
        "campaign_valid": campaign_valid,
        "critical_values": {
            "PASS": plan.pass_critical[look_index],
            "FAIL": plan.fail_critical[look_index],
        },
        "gated": {"|".join(str(part) for part in key): value
                  for key, value in sorted(gated.items())},
        "tally_digest": canonical_sha256(
            {"|".join(str(part) for part in key): value
             for key, value in sorted(gated.items())}),
    }
