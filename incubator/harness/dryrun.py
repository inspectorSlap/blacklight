"""Operational dry run for the campaign runner (harness v1.1).

Exercises every campaign guarantee against the LOCAL sound reference and local
mutants, with a deliberately small configuration. **No scientific endpoint of
the real target is contacted.** This module never constructs a
`BlackBoxTarget` and never imports `harness.transport`, so the real engine's
zero scientific-call count is preserved by construction rather than by
discipline.

v1.0 areas retained: retention, indexing, resume, torn writes, identity
mismatch, failure, blocked, unresolved, stage bounds.

v1.1 areas added, one per corrected defect:

* per-N topology -- small N failing with larger N passing must NOT produce a
  global engine rejection;
* sequential error control -- the two-look rule must respect its stated bound
  across both looks, and the v1.0 rule must be shown to breach it;
* batch identity -- exact item attribution through partial, malformed,
  interrupted, misidentified and envelope-rejected batches;
* frozen-artifact drift -- altering a frozen artifact after freeze must abort
  before scientific call one;
* storage checkpoint -- stops after exactly the first defined segment and
  exposes no scientific disposition.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import copy
import json
import os
import shutil
import tempfile

from . import batching
from . import campaign as campaign_module
from . import sequential
from . import simulation as sim
from .targets import MutantTarget, SoundReferenceTarget

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DRY_CELL_IDS = ("G1-C1-NULL-P0-1_2", "G10-DEGENERACY-SAME-POINT-MASS",
                "G3-C2-NULL-IP-0")
DRY_N = (8,)
DRY_LOOK_1 = 6
DRY_LOOK_2 = 12
DRY_BLOCK = 4

FAKE_IDENTITY = {
    "api_version": "blackbox.ordinal.blackbox-http.v0.1",
    "engine_version": "0.1.0",
    "gateway_version": "0.1.0",
}


def dry_cells():
    by_id = {c["cell_id"]: c for c in sim.build_grid()}
    return [by_id[cid] for cid in DRY_CELL_IDS if cid in by_id]


def dry_plan(look_1=DRY_LOOK_1, look_2=DRY_LOOK_2, candidate_count=1,
             segment_count=1):
    looks = [look_1] if look_2 is None or look_2 == look_1 else [look_1, look_2]
    return sequential.Plan(looks=looks, nominal=campaign_module.NOMINAL,
                           pass_level_family=sim.CELL_LEVEL,
                           fail_level_family=sim.CELL_LEVEL, label="dryrun",
                           candidate_count=candidate_count,
                           segment_count=segment_count)


def make_campaign(target, store, identity_provider=None, expected=None,
                  plan=None, cells=None, label="dryrun", mode=None,
                  integrity_check=None, candidate_n=None, dispatcher=None,
                  batch_size=batching.MAX_BATCH_ITEMS,
                  concurrency=batching.MAX_CONCURRENCY):
    expected = expected if expected is not None else dict(FAKE_IDENTITY)
    provider = identity_provider or (lambda: dict(FAKE_IDENTITY))
    return campaign_module.Campaign(
        target=target, identity_provider=provider, store=store,
        expected_identity=expected, cells=cells or dry_cells(),
        candidate_n=candidate_n or DRY_N, plan=plan or dry_plan(),
        block_size=DRY_BLOCK, label=label,
        mode=mode or campaign_module.MODE_FULL,
        integrity_check=integrity_check, dispatcher=dispatcher,
        batch_size=batch_size, concurrency=concurrency)


class InterruptingTarget(object):
    """Sound reference that kills the run after a fixed number of analyses.

    Raises `KeyboardInterrupt`, which derives from `BaseException` and is
    therefore NOT caught by the campaign's `except Exception` handler. A target
    error is a *blocked replication* and must be recorded as evidence; a
    process death must leave the store partially written so resume has
    something real to repair. Using an ordinary exception would test the wrong
    thing.
    """

    def __init__(self, limit):
        self.inner = SoundReferenceTarget()
        self.limit = limit
        self.calls = 0

    def analyze(self, payload):
        if self.calls >= self.limit:
            raise KeyboardInterrupt("simulated process interruption")
        self.calls += 1
        return self.inner.analyze(payload)


class UnmappableTarget(object):
    def analyze(self, _payload):
        return {"schema_version": "blackbox.ordinal.ordinal-analysis.v0.1",
                "engine_version": "weird-1.0",
                "apparatus_status": "DEVELOPMENT_ONLY_NOT_EXECUTION_ELIGIBLE",
                "confirmatory_ready": False,
                "blocking_conditions": ["development target"],
                "semantic_lights": [{"unexpected": True} for _ in range(3)],
                "mechanical_lights": [{"unexpected": True} for _ in range(3)],
                "cross_light": {"A_all": False, "A_vector": [False] * 3,
                                "c3": {"disposition": "WITHHELD_NOT_IMPLEMENTED"},
                                "pooled_verdict": None}}


class NDependentTarget(object):
    """Sound at large N, structurally fine but mis-covering at small N.

    Emulates an engine whose interval construction is too narrow only when the
    replicate count is small: it shrinks the reported aggregate intervals to a
    point at N below the threshold, which destroys coverage there while leaving
    every disposition rule and every structural property intact. This is
    exactly the shape of failure that must NOT reject the engine globally.
    """

    def __init__(self, bad_below_n=10):
        self.inner = SoundReferenceTarget()
        self.bad_below_n = bad_below_n

    def analyze(self, payload):
        result = self.inner.analyze(payload)
        smallest = min(
            sum(cell["counts"])
            for light in payload["lights"]
            for key in ("semantic_specimens", "mechanical_specimens")
            for specimen in light[key]
            for cell in specimen["cells"].values())
        if smallest >= self.bad_below_n:
            return result
        for light in result["semantic_lights"]:
            for field, point in (("P0_bar_interval", light["P0_bar"]),
                                 ("I_P_bar_interval", light["I_P_bar"])):
                light[field] = [point - 5e-9, point + 5e-9]
        return result


class BatchTarget(object):
    """Batch-capable local target with injectable batch pathologies."""

    def __init__(self, mode="clean"):
        self.inner = SoundReferenceTarget()
        self.mode = mode
        self.batch_calls = 0

    def analyze(self, payload):
        return self.inner.analyze(payload)

    def analyze_batch(self, payloads):
        self.batch_calls += 1
        results = []
        for index, payload in enumerate(payloads):
            body = self.inner.analyze(payload)
            body["analysis_id"] = payload.get("analysis_id")
            results.append(body)

        if self.mode == "partial" and len(results) > 1:
            results = results[:-1]                       # drop the last item
        elif self.mode == "malformed" and results:
            results[0] = {"analysis_id": payloads[0].get("analysis_id"),
                          "error": {"code": "ITEM_FAILED"}}
        elif self.mode == "misidentified" and len(results) > 1:
            results[0]["analysis_id"] = results[1]["analysis_id"]
        elif self.mode == "shuffled" and len(results) > 1:
            results = list(reversed(results))
        elif self.mode == "interrupted":
            raise RuntimeError("simulated batch interruption")
        elif self.mode == "envelope_rejected":
            error = RuntimeError("batch envelope rejected")
            error.status = 422
            raise error
        elif self.mode == "idfree":
            for entry in results:
                entry.pop("analysis_id", None)
        elif self.mode == "idfree_partial":
            for entry in results:
                entry.pop("analysis_id", None)
            results = results[:-1]
        return {"results": results}


def _batch_via_analyze(self, payloads):
    """Batch shim for dry-run doubles: analyze each item independently."""
    results = []
    for payload in payloads:
        try:
            body = self.analyze(payload)
            if isinstance(body, dict):
                body = dict(body)
                body["analysis_id"] = payload.get("analysis_id")
            results.append(body)
        except Exception as exc:
            results.append({"analysis_id": payload.get("analysis_id"),
                            "error": {"code": type(exc).__name__,
                                      "message": str(exc)[:120]}})
    return {"results": results}


InterruptingTarget.analyze_batch = _batch_via_analyze
UnmappableTarget.analyze_batch = _batch_via_analyze
NDependentTarget.analyze_batch = _batch_via_analyze


def _check(name, passed, detail, evidence=None):
    return {"name": name, "status": "PASS" if passed else "FAIL",
            "passed": bool(passed), "detail": detail, "evidence": evidence or {}}


# ---------------------------------------------------------------------------
# v1.0 areas (retained)
# ---------------------------------------------------------------------------

def check_retention_and_indexing(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "retention"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(SoundReferenceTarget(), store).run()
    checks = []
    indexed = report["storage"]["indexed_replications"]
    enough = all(s["replications"] >= DRY_LOOK_1 for s in report["segments"])
    checks.append(_check(
        "retention: every replication stored",
        indexed >= len(dry_cells()) * DRY_LOOK_1 and enough,
        "indexed %d replications across %d segments"
        % (indexed, len(report["segments"])), {"storage": report["storage"]}))

    slug = report["segments"][0]["evidence_slug"]
    ok, details = True, []
    for kind in ("responses", "requests"):
        record = store.read_record(slug, 3, kind=kind)
        ok = ok and record["sha256_matches"]
        ok = ok and isinstance(json.loads(record["raw"].decode("utf-8")), dict)
        details.append({"kind": kind, "sha256_matches": record["sha256_matches"]})
    checks.append(_check(
        "indexing: byte-offset retrieval verifies SHA-256", ok,
        "retrieved replication 3 from both archives by byte offset",
        {"records": details}))

    cell = dry_cells()[0]
    payload, _seed = sim.build_payload(cell, DRY_N[0], 3)
    payload["analysis_id"] = "%s|N=%d|rep=%d" % (cell["cell_id"], DRY_N[0], 3)
    regenerated = json.dumps(payload, sort_keys=True).encode("utf-8")
    stored = store.read_record(store.slug(cell["cell_id"], DRY_N[0]), 3,
                               kind="requests")["raw"]
    checks.append(_check(
        "retention: stored request is exactly what was sent",
        stored == regenerated,
        "stored request bytes match the dispatched payload, analysis_id included",
        {"bytes": len(stored)}))
    checks.append(_check(
        "accounting: storage summary reported",
        report["storage"]["compressed_total_bytes"] > 0,
        "compressed evidence totals %d bytes"
        % report["storage"]["compressed_total_bytes"]))
    return checks, report


def check_resume(workdir):
    root = os.path.join(workdir, "resume")
    store = campaign_module.EvidenceStore(root, block_size=DRY_BLOCK)
    cells = dry_cells()[:1]
    plan = dry_plan(DRY_LOOK_1, DRY_LOOK_1)

    # A dispatch wave is the atomic unit of durability: results are written
    # only once the whole wave returns. Wave size is batch_size x concurrency,
    # so this test deliberately uses a small wave to produce several durable
    # checkpoints before the interruption, mirroring a real campaign where the
    # wave is far smaller than the segment.
    propagated = False
    try:
        make_campaign(InterruptingTarget(limit=5), store, cells=cells,
                      plan=plan, label="interrupted",
                      batch_size=2, concurrency=1).run()
    except KeyboardInterrupt:
        propagated = True
    slug = store.slug(cells[0]["cell_id"], DRY_N[0])
    after, _ = store.recover(slug)

    second = make_campaign(SoundReferenceTarget(), store, cells=cells,
                           plan=plan, label="resumed",
                           batch_size=2, concurrency=1).run()
    final, _ = store.recover(slug)
    segment = second["segments"][0]

    return [
        _check("resume: interruption leaves a partial but valid segment",
               propagated and 0 < len(after) < DRY_LOOK_1,
               "%d of %d replications durable after interruption; the unflushed "
               "block was correctly lost" % (len(after), DRY_LOOK_1),
               {"durable_after_interrupt": sorted(after)}),
        _check("resume: no duplicated replications",
               not segment["duplicated_replications"],
               "duplicates: %s" % (segment["duplicated_replications"] or "none")),
        _check("resume: no omitted replications",
               not segment["missing_replications"]
               and final == set(range(DRY_LOOK_1)),
               "final set is exactly 0..%d" % (DRY_LOOK_1 - 1)),
        _check("resume: all resumed evidence verifies by digest",
               all(store.read_record(slug, r)["sha256_matches"]
                   for r in sorted(final)),
               "all %d stored responses verify" % len(final)),
    ]


def check_torn_write(workdir):
    root = os.path.join(workdir, "torn")
    store = campaign_module.EvidenceStore(root, block_size=DRY_BLOCK)
    cells = dry_cells()[:1]
    plan = dry_plan(DRY_LOOK_1, DRY_LOOK_1)
    make_campaign(SoundReferenceTarget(), store, cells=cells, plan=plan).run()
    slug = store.slug(cells[0]["cell_id"], DRY_N[0])

    index_path = store._path(slug, ".index.jsonl")
    with open(index_path, "r") as handle:
        lines = handle.readlines()
    with open(index_path, "w") as handle:
        handle.writelines(lines[:-1])
        handle.write(lines[-1][:len(lines[-1]) // 2])
    archive_path = store._path(slug, ".responses.gz")
    before_size = os.path.getsize(archive_path)
    with open(archive_path, "ab") as handle:
        handle.write(b"\x00" * 512)

    recovered, _ = store.recover(slug)
    truncated = os.path.getsize(archive_path) <= before_size

    report = make_campaign(SoundReferenceTarget(), store, cells=cells,
                           plan=plan).run()
    final, _ = store.recover(slug)
    return [
        _check("torn write: malformed trailing index line discarded",
               len(recovered) == len(lines) - 1,
               "recovered %d of %d index entries" % (len(recovered), len(lines))),
        _check("torn write: orphaned archive tail truncated", truncated,
               "archive truncated back to the last indexed extent"),
        _check("torn write: resume restores the full replication set",
               final == set(range(DRY_LOOK_1))
               and not report["segments"][0]["duplicated_replications"],
               "final set is exactly 0..%d with no duplicates" % (DRY_LOOK_1 - 1)),
    ]


def check_identity_mismatch(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "identity-pre"),
                                          block_size=DRY_BLOCK)
    wrong = dict(FAKE_IDENTITY)
    wrong["engine_version"] = "9.9.9-not-the-distributed-build"
    report = make_campaign(SoundReferenceTarget(), store, expected=wrong,
                           cells=dry_cells()[:1], label="identity-pre").run()
    pre_ok = (report["status"] == "ABORTED_INVALID"
              and report["campaign_valid"] is False
              and report["abort_phase"] == "pre-campaign"
              and report.get("scientific_calls_made") == 0)

    store2 = campaign_module.EvidenceStore(
        os.path.join(workdir, "identity-drift"), block_size=DRY_BLOCK)
    state = {"calls": 0}

    def drifting():
        state["calls"] += 1
        meta = dict(FAKE_IDENTITY)
        if state["calls"] > 1:
            meta["engine_version"] = "0.1.1"
        return meta

    report2 = make_campaign(SoundReferenceTarget(), store2,
                            identity_provider=drifting, cells=dry_cells()[:1],
                            label="identity-drift").run()
    drift_ok = (report2["status"] == "ABORTED_INVALID"
                and report2["campaign_valid"] is False
                and report2["abort_phase"] == "post-campaign")
    return [
        _check("identity: pre-campaign mismatch aborts before any scientific call",
               pre_ok, "status=%s phase=%s scientific_calls=%s"
               % (report["status"], report.get("abort_phase"),
                  report.get("scientific_calls_made"))),
        _check("identity: mid-campaign drift aborts and marks invalid", drift_ok,
               "status=%s phase=%s" % (report2["status"],
                                       report2.get("abort_phase"))),
        _check("identity: aborted campaign results are marked unusable",
               "NOT usable" in report.get("usability", ""),
               "the report states explicitly that results are not usable"),
    ]


def check_failure_handling(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "failure"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(MutantTarget("MUT-25-DEGENERACY-IS-ENGINE-FAILURE"),
                           store, label="mutant-degeneracy").run()
    degeneracy = [s for s in report["segments"] if s["cell_id"].startswith("G10-")]
    fired = bool(degeneracy) and degeneracy[0]["events"].get(
        "degeneracy_routed_to_engine_failure", {}).get("verdict") == "FAIL"
    fail_ok = (report["engine_result_state"] == "ENGINE_REJECTED"
               and report["campaign_valid"] is True and fired
               and "degeneracy_routed_to_engine_failure"
               in report["n_independent_failures"])

    store2 = campaign_module.EvidenceStore(os.path.join(workdir, "blocked"),
                                           block_size=DRY_BLOCK)
    report2 = make_campaign(UnmappableTarget(), store2, cells=dry_cells()[:1],
                            label="unmappable").run()
    blocked_ok = (report2["segments"][0]["verdict"] == "BLOCKED"
                  and report2["engine_result_state"] == "ENGINE_NOT_YET_QUALIFIABLE"
                  and report2["segments"][0]["blocked_replications"] > 0)
    # A response the adapter cannot map is still a real response: the body is
    # retained verbatim (not replaced by an error stub) and the failure is
    # recorded alongside it in the index. That is strictly better evidence than
    # discarding the body, so the assertion checks for the body AND the error.
    slug = report2["segments"][0]["evidence_slug"]
    stored = store2.read_record(slug, 0, kind="responses")
    entry = stored["index_entry"]
    retained = (stored["sha256_matches"]
                and entry["blocked"] is True
                and entry["error"] is not None
                and entry["error"].get("code") == "UNDOCUMENTED_SCHEMA"
                and b"semantic_lights" in stored["raw"])

    store3 = campaign_module.EvidenceStore(os.path.join(workdir, "pooled"),
                                           block_size=DRY_BLOCK)
    report3 = make_campaign(MutantTarget("MUT-17-POOLED-CROSS-LIGHT-VERDICT"),
                            store3, cells=dry_cells()[:1],
                            label="mutant-pooled").run()
    pooled_ok = (report3["segments"][0]["verdict"] == "FAIL"
                 and report3["engine_result_state"] == "ENGINE_REJECTED")
    return [
        _check("failure: defective target yields FAIL and ENGINE_REJECTED",
               fail_ok, "engine=%s; classified as an N-independent defect"
               % report["engine_result_state"]),
        _check("failure: zero-tolerance pooled verdict fails immediately",
               pooled_ok, "a single occurrence is enough to FAIL"),
        _check("blocked: unmappable response yields BLOCKED, not a pass",
               blocked_ok, "verdict=%s engine=%s"
               % (report2["segments"][0]["verdict"],
                  report2["engine_result_state"])),
        _check("blocked: blocked replications still retained as evidence",
               retained, "stored body records the harness error and digest-verifies"),
    ]


def check_unresolved(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "unresolved"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(SoundReferenceTarget(), store, cells=dry_cells()[:1],
                           plan=dry_plan(4, 4), label="unresolved").run()
    segment = report["segments"][0]
    unresolved_events = [name for name, entry in segment["events"].items()
                         if entry["verdict"] == "UNRESOLVED"]
    return [
        _check("unresolved: an under-powered segment is reported honestly",
               segment["verdict"] == "UNRESOLVED"
               and report["engine_result_state"] == "ENGINE_NOT_YET_QUALIFIABLE"
               and bool(unresolved_events),
               "verdict=%s engine=%s with %d unresolved rates"
               % (segment["verdict"], report["engine_result_state"],
                  len(unresolved_events))),
        _check("unresolved: hard stop respected",
               segment["replications"] == 4,
               "ran exactly the configured budget without escalating past it"),
    ]


# ---------------------------------------------------------------------------
# v1.1 area 1: per-N topology
# ---------------------------------------------------------------------------

def check_per_n_topology(workdir):
    """Small N failing and larger N passing must not reject the engine."""
    # A PASS is only reachable once the replication count is large enough for
    # zero events to clear the bound: at level 0.01 against a 0.05 nominal that
    # needs about 104 replications, so this check uses a single look at 110.
    # Below that, pass_max is -1 and every segment is UNRESOLVED by
    # construction, which would make the per-N distinction untestable.
    # The cell must actually VARY under sampling for a coverage defect to be
    # observable. G1-C1-NULL-P0-1_2 places both compared cells at the same
    # point mass, so its estimate is exactly 0.5 on every replication and a
    # narrowed interval never misses -- it would silently test nothing.
    # G1-C1-NULL-P0-13_20 has a genuinely stochastic estimate.
    by_id = {c["cell_id"]: c for c in sim.build_grid()}
    varying = [by_id["G1-C1-NULL-P0-13_20"]]

    store = campaign_module.EvidenceStore(os.path.join(workdir, "pern"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(
        NDependentTarget(bad_below_n=10), store, cells=varying,
        candidate_n=(8, 30), plan=dry_plan(110, None),
        label="per-N").run()

    by_n = {entry["N"]: entry for entry in report["per_N"]}
    small_bad = by_n.get(8, {}).get("state") == "ENGINE_REJECTED_AT_N"
    large_good = by_n.get(30, {}).get("state") == "ENGINE_CANDIDATE_QUALIFIED_AT_N"
    not_global = report["engine_result_state"] != "ENGINE_REJECTED"
    qualified = report.get("qualified_N") == [30]
    rejected = report.get("rejected_N") == [8]
    no_structural = not report["n_independent_failures"]

    return [
        _check("per-N: coverage failure confined to the small N is seen there",
               small_bad, "N=8 state=%s" % by_n.get(8, {}).get("state")),
        _check("per-N: the larger N still qualifies", large_good,
               "N=30 state=%s" % by_n.get(30, {}).get("state")),
        _check("per-N: small-N failure does NOT reject the engine globally",
               not_global and qualified and rejected,
               "engine=%s qualified_N=%s rejected_N=%s"
               % (report["engine_result_state"], report.get("qualified_N"),
                  report.get("rejected_N")),
               {"reason": report.get("engine_result_reason")}),
        _check("per-N: no N-independent defect is falsely alleged",
               no_structural,
               "n_independent_failures=%s" % report["n_independent_failures"]),
        _check("per-N: a genuine N-independent defect still rejects globally",
               _structural_still_global(workdir),
               "a structural mutant is rejected at every N, as it must be"),
    ]


def _structural_still_global(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "pern-struct"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(
        MutantTarget("MUT-17-POOLED-CROSS-LIGHT-VERDICT"), store,
        cells=dry_cells()[:1], candidate_n=(8, 30),
        plan=dry_plan(DRY_LOOK_1, None), label="per-N-structural").run()
    return (report["engine_result_state"] == "ENGINE_REJECTED"
            and "pooled_verdict_emitted" in report["n_independent_failures"])


# ---------------------------------------------------------------------------
# v1.1 area 2: sequential error control
# ---------------------------------------------------------------------------

def check_sequential_error_control(_workdir, replications=100000):
    """The two-look rule must respect its stated bound across BOTH looks."""
    # segment_count=1 and candidate_count=1 isolate the per-segment rule,
    # which is the level a single-segment simulation can actually test. The
    # familywise guarantees follow from it by union bounds and are verified
    # exactly in _check_familywise rather than by simulation.
    two = sequential.Plan(looks=[500, 2000], nominal=0.05,
                          pass_level_family=0.01, fail_level_family=0.01,
                          label="two-look")
    fixed = sequential.Plan(looks=[2000], nominal=0.05, pass_level_family=0.01,
                            fail_level_family=0.01, label="fixed-stage")

    two_result = sequential.verify_error_control(two, 0.05, replications)
    fixed_result = sequential.verify_error_control(fixed, 0.05, replications)

    # The v1.0 rule: the FULL level spent at each of two looks.
    naive = sequential.Plan(looks=[500, 2000], nominal=0.05,
                            pass_level_family=0.01, fail_level_family=0.01,
                            label="v1.0-style")
    naive.pass_levels = [0.01, 0.01]
    naive.fail_levels = [0.01, 0.01]
    naive.criticals = [sequential.critical_values(n, 0.01, 0.01, 0.05)
                       for n in naive.looks]
    naive_result = sequential.verify_error_control(naive, 0.05, replications)

    return [
        _check("sequential: two-look rule respects its stated bound",
               two_result["strictly_within_bound"],
               "false-FAIL %.5f, exact 99.9%% upper %.5f, bound %.4f, over "
               "%d replications with nested looks"
               % (two_result["observed_error_rate"],
                  two_result["observed_error_upper_999"],
                  two_result["stated_bound"], replications),
               {"decisions_by_look": two_result["decisions_by_look"]}),
        _check("sequential: fixed-stage alternative respects its bound",
               fixed_result["strictly_within_bound"],
               "false-FAIL %.5f, upper %.5f, bound %.4f"
               % (fixed_result["observed_error_rate"],
                  fixed_result["observed_error_upper_999"],
                  fixed_result["stated_bound"])),
        _check("sequential: the v1.0 rule is shown to breach its stated bound",
               naive_result["observed_error_rate"] > naive_result["stated_bound"],
               "spending the full level at both looks realises %.5f against a "
               "stated %.4f -- the defect this correction removes"
               % (naive_result["observed_error_rate"],
                  naive_result["stated_bound"])),
        _check("sequential: error is spent across looks, not per look",
               abs(sum(two.fail_levels) - two.fail_level_per_segment) < 1e-15
               and len(two.fail_levels) == 2,
               "per-look levels %s sum to the per-segment budget %.4g"
               % (two.fail_levels, two.fail_level_per_segment)),
    ] + _check_familywise() + _check_d6_gating()


def _check_familywise():
    """The v1.2 PASS and FAIL inference families (operator requirements 1-6)."""
    from . import oc as oc_module

    configurations = len(sim.build_grid())
    candidates = len(sim.CANDIDATE_N)
    segments = configurations * candidates
    family = sim.CELL_LEVEL

    two = campaign_module.default_plan(segment_count=segments,
                                       candidate_count=candidates)
    fixed = campaign_module.default_plan(fixed_stage=True,
                                         segment_count=segments,
                                         candidate_count=candidates)

    per_candidate = family / float(candidates)
    per_segment = family / float(segments)

    # (1) PASS budget is 0.01/6 per candidate N.
    pass_per_candidate_ok = (
        abs(two.pass_level_per_candidate - per_candidate) < 1e-15
        and abs(fixed.pass_level_per_candidate - per_candidate) < 1e-15)

    # (2) Two-look PASS budgets sum to 0.01/6 across looks.
    pass_looks_ok = (abs(sum(two.pass_levels) - per_candidate) < 1e-15
                     and len(two.pass_levels) == 2)

    # (3) PASS is NOT divided across the 53 conjunctive segments within an N.
    would_be_if_divided = per_candidate / float(configurations)
    not_divided = abs(two.pass_levels[0] - would_be_if_divided) > 1e-12

    # (4) For any invalid N, P(false qualification) <= 0.01/6. Qualifying an N
    # requires every one of its segments to PASS, so the probability is bounded
    # by the PASS probability of the single segment that makes the N invalid.
    # Least-favourable invalid rate is just above the nominal.
    worst_pass_two = max(oc_module.plan_oc(two, p)["P_PASS"]
                         for p in (0.05 + 1e-9, 0.0501, 0.051, 0.06))
    worst_pass_fixed = max(oc_module.plan_oc(fixed, p)["P_PASS"]
                           for p in (0.05 + 1e-9, 0.0501, 0.051, 0.06))
    invalid_n_ok = (worst_pass_two <= per_candidate + 1e-12
                    and worst_pass_fixed <= per_candidate + 1e-12)

    # (5) Union bound across six invalid candidate N.
    union_two = worst_pass_two * candidates
    union_fixed = worst_pass_fixed * candidates
    union_ok = (union_two <= family + 1e-12 and union_fixed <= family + 1e-12)

    # (6) FAIL remains 0.01/318 per segment and splits across looks.
    fail_segment_ok = (abs(two.fail_level_per_segment - per_segment) < 1e-18
                       and abs(fixed.fail_level_per_segment - per_segment) < 1e-18)
    fail_looks_ok = abs(sum(two.fail_levels) - per_segment) < 1e-18
    exact_fail = oc_module.plan_oc(two, 0.05)["P_FAIL"]
    fail_family_ok = exact_fail * segments <= family + 1e-12

    return [
        _check("PASS family: budget is 0.01/6 per candidate N",
               pass_per_candidate_ok,
               "per-candidate PASS budget %.6g = %.4g / %d"
               % (two.pass_level_per_candidate, family, candidates)),
        _check("PASS family: two-look budgets sum to 0.01/6 across looks",
               pass_looks_ok,
               "per-look budgets %s sum to %.6g"
               % ([round(v, 12) for v in two.pass_levels], per_candidate)),
        _check("PASS family: NOT divided across the 53 conjunctive segments",
               not_divided,
               "per-look PASS is %.6g; dividing across %d segments would give "
               "%.6g. Within an N qualification is intersection-union, so no "
               "segment-level division applies"
               % (two.pass_levels[0], configurations, would_be_if_divided)),
        _check("PASS family: false qualification of an invalid N <= 0.01/6",
               invalid_n_ok,
               "worst-case P(PASS) just above nominal is %.3g (two-look) and "
               "%.3g (fixed), against a per-candidate budget of %.6g"
               % (worst_pass_two, worst_pass_fixed, per_candidate)),
        _check("PASS family: union across six invalid N stays within 0.01",
               union_ok,
               "%.3g x %d = %.3g (two-look) and %.3g (fixed), within %.4g"
               % (worst_pass_two, candidates, union_two, union_fixed, family)),
        _check("FAIL family: 0.01/318 per segment, split across looks",
               fail_segment_ok and fail_looks_ok,
               "per-segment %.6g, per-look %s"
               % (two.fail_level_per_segment,
                  [round(v, 12) for v in two.fail_levels])),
        _check("FAIL family: exact campaign-wide false-FAIL respects 0.01",
               fail_family_ok,
               "exact P(false FAIL | p = nominal) = %.3g x %d segments = %.3g"
               % (exact_fail, segments, exact_fail * segments)),
        _check("critical values: derived from the frozen budgets",
               (two.criticals[0] == (10, 49) and two.criticals[1] == (70, 144)
                and fixed.criticals[0] == (72, 142)),
               "two-look %s and %s; fixed-stage %s"
               % (two.criticals[0], two.criticals[1], fixed.criticals[0])),
    ]


def _check_d6_gating():
    """D6 must be bound to the frozen topology and never defaulted (7, 8)."""
    checks = []

    refusals = []
    for label, approval in (
            ("absent approval", None),
            ("approved but no D6", {"status": "APPROVED"}),
            ("approved, D6 empty", {"status": "APPROVED",
                                    "decisions": {"D6": {}}}),
            ("unknown enum value", {"status": "APPROVED",
                                    "decisions": {"D6": {"plan": "two_look"}}}),
            ("v1.1-era enum value", {"status": "APPROVED",
                                     "decisions": {"D6": {"plan": "fixed_stage"}}}),
            ("not approved", {"status": "PENDING",
                              "decisions": {"D6": {"plan":
                                                   campaign_module.PLAN_TWO_LOOK}}}),
    ):
        try:
            campaign_module.resolve_decision_plan(approval)
            refusals.append((label, False))
        except campaign_module.DecisionPlanNotSelected:
            refusals.append((label, True))
    all_refused = all(refused for _label, refused in refusals)
    checks.append(_check(
        "D6: absent, unknown or inconsistent selections all refuse",
        all_refused,
        "refused: %s" % ", ".join(l for l, r in refusals if r)))

    resolved = {}
    for selected in campaign_module.PLAN_ENUM:
        approval = {"status": "APPROVED",
                    "decisions": {"D6": {"plan": selected}}}
        plan, name = campaign_module.resolve_decision_plan(approval)
        resolved[selected] = plan
    checks.append(_check(
        "D6: each documented enum value produces its plan",
        len(resolved[campaign_module.PLAN_TWO_LOOK].looks) == 2
        and len(resolved[campaign_module.PLAN_FIXED_STAGE].looks) == 1,
        "%s -> 2 looks, %s -> 1 look"
        % (campaign_module.PLAN_TWO_LOOK, campaign_module.PLAN_FIXED_STAGE)))
    checks.append(_check(
        "D6: both plans carry candidate count 6 and segment count 318",
        all(p.candidate_count == 6 and p.segment_count == 318
            for p in resolved.values()),
        "candidate counts %s, segment counts %s"
        % (sorted({p.candidate_count for p in resolved.values()}),
           sorted({p.segment_count for p in resolved.values()}))))

    # A topology-inconsistent plan must be rejected by validation.
    bad = sequential.Plan(looks=[500, 2000], nominal=0.05,
                          pass_level_family=sim.CELL_LEVEL,
                          fail_level_family=sim.CELL_LEVEL, label="bad",
                          candidate_count=3, segment_count=100)
    problems = campaign_module.validate_plan_topology(bad)
    checks.append(_check(
        "D6: a topology-inconsistent plan is rejected",
        len(problems) >= 2,
        "validation reported %d problems: %s" % (len(problems), problems[:2])))

    from . import freeze as freeze_module
    status = freeze_module.phase_gate_status()
    # The blocking behaviour is proved above against synthetic approval
    # records, which is the right way to test it. What the LIVE gate must show
    # is that whatever selection exists is valid against the frozen topology --
    # asserting "unselected" here would encode a transient state and go stale
    # the moment the operator decides.
    live_ok = (status["d6_decision_plan"] in campaign_module.PLAN_ENUM
               and status["d6_valid"] is True
               and (status["d6_budgets"] or {}).get("candidate_count") == 6
               and (status["d6_budgets"] or {}).get("segment_count") == 318
               ) or (status["d6_decision_plan"] == "NOT_SELECTED"
                     and not status["real_engine_campaign_permitted"])
    checks.append(_check(
        "D6: the live gate reports a topology-consistent selection or blocks",
        live_ok,
        "gate reports d6_decision_plan=%s, d6_valid=%s"
        % (status["d6_decision_plan"], status["d6_valid"])))
    checks.append(_check(
        "D6: the documented enum is exactly the two corrected plans",
        tuple(status["d6_documented_enum"]) == campaign_module.PLAN_ENUM,
        "enum = %s" % (status["d6_documented_enum"],)))
    return checks


def check_v13_negative_controls(workdir):
    """Requirement 4: five negative controls for the v1.3 corrections."""
    from . import roster
    checks = []

    # (a) Placeholder rosters are rejected before transport, at zero cost.
    placeholder = copy.deepcopy(sim.build_payload(dry_cells()[0], 8, 0)[0])
    for light in placeholder["lights"]:
        for index, specimen in enumerate(light["semantic_specimens"]):
            specimen["id"] = "S%d" % (index + 1)
        for index, specimen in enumerate(light["mechanical_specimens"]):
            specimen["id"] = "M%d" % (index + 1)
    placeholder_problems = roster.check_counts_payload(placeholder)
    raised = False
    try:
        roster.assert_payload(placeholder)
    except roster.RosterViolation:
        raised = True
    checks.append(_check(
        "negative control: placeholder roster rejected before transport",
        raised and bool(placeholder_problems)
        and "placeholder" in placeholder_problems[0],
        "zero target calls used; first problem: %s"
        % placeholder_problems[0][:90]))

    # Missing, duplicated, reordered and extra are each detected.
    variants = {}
    base = sim.build_payload(dry_cells()[0], 8, 0)[0]
    for label, mutate in (
            ("missing", lambda ids: ids[:-1]),
            ("duplicated", lambda ids: ids[:-1] + [ids[0]]),
            ("reordered", lambda ids: list(reversed(ids))),
            ("extra", lambda ids: ids + ["unknown-sample-99"])):
        payload = copy.deepcopy(base)
        for light in payload["lights"]:
            ids = [s["id"] for s in light["semantic_specimens"]]
            new_ids = mutate(list(ids))
            specimens = []
            for i, ident in enumerate(new_ids):
                entry = copy.deepcopy(light["semantic_specimens"][
                    min(i, len(light["semantic_specimens"]) - 1)])
                entry["id"] = ident
                specimens.append(entry)
            light["semantic_specimens"] = specimens
        variants[label] = roster.check_counts_payload(payload)
    checks.append(_check(
        "negative control: missing/duplicated/reordered/extra all detected",
        all(variants[k] for k in ("missing", "duplicated", "reordered", "extra")),
        "; ".join("%s=%d problem(s)" % (k, len(v))
                  for k, v in sorted(variants.items()))))

    # (b) One or more blocked requests fails the checkpoint.
    class OneBlockedTarget(object):
        """Blocks exactly one replication, chosen by analysis_id.

        Keying off the identifier rather than a call counter makes the control
        deterministic: the batch-to-single fallback re-issues requests, so a
        counter would block a different replication depending on the path
        taken, and could block none at all.
        """

        def __init__(self):
            self.inner = SoundReferenceTarget()

        def analyze(self, payload):
            if str(payload.get("analysis_id", "")).endswith("rep=2"):
                raise RuntimeError("simulated single blocked request")
            return self.inner.analyze(payload)

        analyze_batch = _batch_via_analyze

    store = campaign_module.EvidenceStore(
        os.path.join(workdir, "one-blocked"), block_size=DRY_BLOCK)
    report = make_campaign(OneBlockedTarget(), store, cells=dry_cells()[:1],
                           mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                           plan=dry_plan(DRY_LOOK_1, None),
                           label="one-blocked").run()
    checks.append(_check(
        "negative control: a single blocked request fails the checkpoint",
        report["campaign_valid"] is False
        and report["status"] == "STORAGE_CHECKPOINT_FAILED"
        and report["checkpoint_disposition"] == "CHECKPOINT_FAILED"
        and report["checkpoint_audit"]["blocked"] >= 1,
        "status=%s valid=%s blocked=%d"
        % (report["status"], report["campaign_valid"],
           report["checkpoint_audit"]["blocked"])))

    # (c) Zero successful analyses cannot pass -- the exact v1.2 failure.
    class AllRejectedTarget(object):
        def analyze(self, _payload):
            from .targets import Rejection
            raise Rejection("INPUT_REJECTED", "roster mismatch", status=422)

        def analyze_batch(self, payloads):
            return {"results": [{"error": {"code": "INPUT_REJECTED"}}
                                for _ in payloads]}

    store2 = campaign_module.EvidenceStore(
        os.path.join(workdir, "all-rejected"), block_size=DRY_BLOCK)
    report2 = make_campaign(AllRejectedTarget(), store2, cells=dry_cells()[:1],
                            mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                            plan=dry_plan(DRY_LOOK_1, None),
                            label="all-rejected").run()
    audit = report2["checkpoint_audit"]
    checks.append(_check(
        "negative control: zero successful analyses cannot pass",
        report2["campaign_valid"] is False
        and audit["successful_analyses"] == 0
        and report2["status"] == "STORAGE_CHECKPOINT_FAILED"
        and "VOID" in report2.get("usability", ""),
        "the v1.2 500/500 scenario now reports %s with %d successes and a VOID "
        "storage measurement" % (report2["status"],
                                 audit["successful_analyses"])))

    # (d) v1.4: a BATCHING dispatcher is refused at preflight, before any
    #     target call. Batching cannot be shown to honor one-in-flight.
    class CountingTarget2(object):
        def __init__(self):
            self.calls = 0

        def analyze(self, payload):
            self.calls += 1
            return SoundReferenceTarget().analyze(payload)

        analyze_batch = _batch_via_analyze

    counting = CountingTarget2()
    store3 = campaign_module.EvidenceStore(
        os.path.join(workdir, "batching-refused"), block_size=DRY_BLOCK)
    campaign = make_campaign(counting, store3, cells=dry_cells()[:1],
                             mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                             plan=dry_plan(DRY_LOOK_1, None),
                             dispatcher=batching.BatchDispatcher(
                                 counting, batch_size=32, concurrency=4),
                             label="batching-refused")
    report3 = campaign.run()
    checks.append(_check(
        "negative control: a batching dispatcher is refused at preflight",
        report3["status"] == "ABORTED_INVALID"
        and report3["abort_phase"] == "preflight"
        and counting.calls == 0
        and report3.get("scientific_calls_made") == 0,
        "batching refused before any target call (%d made); v1.4 requires "
        "serialized single-request transport" % counting.calls))

    # (e) Batch and single-request representations are semantically equivalent.
    items = []
    for replication in range(5):
        payload, _seed = sim.build_payload(dry_cells()[0], 8, replication)
        key = "eq|rep=%d" % replication
        payload["analysis_id"] = key
        items.append((key, payload))

    batch_target = BatchTarget("clean")
    batched = batching.BatchDispatcher(batch_target, batch_size=3,
                                       concurrency=2).dispatch(items)
    singles = {}
    reference = SoundReferenceTarget()
    for key, payload in items:
        singles[key] = reference.analyze(copy.deepcopy(payload))

    def comparable(body):
        body = copy.deepcopy(body)
        body.pop("analysis_id", None)
        return json.dumps(body, sort_keys=True)

    equivalent = all(
        batched[key]["response"] is not None
        and comparable(batched[key]["response"]) == comparable(singles[key])
        for key, _payload in items)
    checks.append(_check(
        "negative control: batch and single representations are equivalent",
        equivalent,
        "all %d items produced byte-identical scientific bodies through the "
        "batch and single paths, with identity preserved per item" % len(items)))
    return checks


def check_v14_concurrency_controls(workdir):
    """Requirement 5: six adversarial controls for the v1.4 corrections."""
    import threading
    from . import inflight, serial
    checks = []

    # (1) Outer concurrency of one cannot conceal inner fan-out.
    gate = inflight.InFlightGate(limit=1, raise_on_violation=False)

    class FanOutTarget(object):
        """One outer call that spawns concurrent inner analysis calls."""

        def analyze(self, payload):
            barrier = threading.Barrier(4, timeout=5)
            errors = []

            def inner():
                try:
                    with gate.call("inner"):
                        barrier.wait()      # force genuine overlap
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=inner) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            return {"ok": True, "errors": len(errors)}

    FanOutTarget().analyze({})
    checks.append(_check(
        "concurrency: outer concurrency one cannot conceal inner fan-out",
        gate.max_observed > 1 and gate.violations > 0,
        "a single outer call that fanned out 4 inner analyses registered "
        "max_observed=%d with %d violation(s); a throttling semaphore would "
        "have serialized them and reported 1"
        % (gate.max_observed, gate.violations),
        {"violation_details": gate.violation_details[:2]}))

    # (2) Under the serialized dispatcher the maximum in flight is exactly one.
    measured = inflight.InFlightGate(limit=1)

    class CountingSerialTarget(object):
        def __init__(self):
            self.inner = SoundReferenceTarget()
            self.calls = 0

        def analyze(self, payload):
            self.calls += 1
            with measured.call("serial"):
                return self.inner.analyze(payload)

    target = CountingSerialTarget()   # wraps the gate at its own boundary
    dispatcher = serial.SerialDispatcher(target, gate=measured)
    items = []
    for replication in range(12):
        payload, _seed = sim.build_payload(dry_cells()[0], 8, replication)
        key = "inflight|rep=%d" % replication
        payload["analysis_id"] = key
        items.append((key, payload))
    dispatcher.dispatch(items)
    contract = dispatcher.contract()
    checks.append(_check(
        "concurrency: maximum observed in-flight analysis count is one",
        contract["in_flight"]["max_observed_in_flight"] == 1
        and contract["in_flight"]["violations"] == 0
        and contract["in_flight"]["honors_one_in_flight"],
        "%d analysis calls, max in flight %d, %d violations"
        % (contract["in_flight"]["total_analysis_calls"],
           contract["in_flight"]["max_observed_in_flight"],
           contract["in_flight"]["violations"])))

    # (3) CAPACITY still fails closed, and is not retried.
    class CapacityTarget(object):
        def __init__(self):
            self.inner = SoundReferenceTarget()
            self.attempts = {}

        def analyze(self, payload):
            key = payload.get("analysis_id")
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if not str(key).endswith(("rep=0", "rep=1")):
                from .targets import Rejection
                raise Rejection("CAPACITY", "gateway concurrency limit reached")
            return self.inner.analyze(payload)

    capacity_target = CapacityTarget()
    store = campaign_module.EvidenceStore(os.path.join(workdir, "capacity"),
                                          block_size=DRY_BLOCK)
    report = make_campaign(capacity_target, store, cells=dry_cells()[:1],
                           mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                           plan=dry_plan(DRY_LOOK_1, None),
                           label="capacity").run()
    audit = report["checkpoint_audit"]
    capacity_reason = any("TARGET_DEPLOYMENT_CONTRACT_PROBLEM" in reason
                          for reason in audit["failure_reasons"])
    checks.append(_check(
        "concurrency: CAPACITY still fails closed and is classified",
        report["campaign_valid"] is False
        and report["status"] == "STORAGE_CHECKPOINT_FAILED"
        and audit["error_codes"].get("CAPACITY", 0) > 0
        and capacity_reason,
        "%d CAPACITY rejection(s) classified as a target/deployment contract "
        "problem, checkpoint failed"
        % audit["error_codes"].get("CAPACITY", 0)))

    # (6) No failed or ambiguous attempt is silently retried.
    repeated = {k: v for k, v in capacity_target.attempts.items() if v > 1}
    checks.append(_check(
        "concurrency: no failed or ambiguous attempt is silently retried",
        not repeated
        and report["transport_contract"]["stats"]["retries_performed"] == 0
        and report["transport_contract"]["retries_enabled"] is False,
        "every replication was attempted exactly once; %d repeated"
        % len(repeated)))

    # (4) Final statistics reconcile with the audit, and cannot be all-zero.
    reconciliation = report["transport_reconciliation"]
    stats = report["transport_contract"]["stats"]
    nonzero = (stats["physical_http_requests"] > 0
               and stats["logical_replications"] > 0)
    checks.append(_check(
        "statistics: report-time stats reconcile with the attempt audit",
        reconciliation["reconciled"] and nonzero
        and report["transport_contract"]["stats_generated_at"]
        == "report finalization",
        "successes %d/%d, blocked %d/%d, physical requests %d, batches %d"
        % (stats["successful_analyses"], audit["successful_analyses"],
           stats["blocked_attempts"], audit["blocked"],
           stats["physical_http_requests"], stats["logical_batches"]),
        {"problems": reconciliation["problems"]}))
    checks.append(_check(
        "statistics: nonzero live activity cannot yield all-zero statistics",
        nonzero and stats["physical_http_requests"]
        == stats["successful_analyses"] + stats["blocked_attempts"],
        "%d physical requests recorded for %d successes + %d blocked; the "
        "v1.3 start-of-run snapshot would have reported zeros"
        % (stats["physical_http_requests"], stats["successful_analyses"],
           stats["blocked_attempts"])))

    # (5) Six successes plus 494 failures cannot satisfy completion.
    class MostlyCapacityTarget(object):
        def __init__(self):
            self.inner = SoundReferenceTarget()

        def analyze(self, payload):
            key = str(payload.get("analysis_id"))
            if key.endswith("rep=0"):
                return self.inner.analyze(payload)
            from .targets import Rejection
            raise Rejection("CAPACITY", "gateway concurrency limit reached")

    store2 = campaign_module.EvidenceStore(os.path.join(workdir, "mostly"),
                                           block_size=DRY_BLOCK)
    report2 = make_campaign(MostlyCapacityTarget(), store2,
                            cells=dry_cells()[:1],
                            mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                            plan=dry_plan(DRY_LOOK_1, None),
                            label="mostly-capacity").run()
    audit2 = report2["checkpoint_audit"]
    checks.append(_check(
        "statistics: partial success cannot satisfy checkpoint completion",
        report2["campaign_valid"] is False
        and audit2["successful_analyses"] < audit2["requested"]
        and "VOID" in report2.get("usability", ""),
        "the v1.3 shape (a few successes, the rest CAPACITY) reports %s with "
        "%d of %d successes and a VOID storage measurement"
        % (report2["status"], audit2["successful_analyses"],
           audit2["requested"])))
    return checks


def check_oc_determinism(_workdir):
    """The corrected operating-characteristics artifact must be deterministic."""
    from . import oc as oc_module
    first = json.dumps(oc_module.build_report(), sort_keys=True)
    second = json.dumps(oc_module.build_report(), sort_keys=True)
    report = oc_module.build_report()
    topology = report["inference_topology"]
    return [
        _check("OC: the exact artifact is deterministic", first == second,
               "two independent builds are byte-identical (%d bytes)"
               % len(first)),
        _check("OC: computed by exact binomial summation, not simulation",
               report["computation"] == "exact binomial summation; no simulation"
               and report["real_target_calls"] == 0,
               "no Monte Carlo and no real-target call"),
        _check("OC: reports the corrected PASS topology",
               abs(topology["pass_per_candidate_N_budget"]
                   - sim.CELL_LEVEL / 6.0) < 1e-15,
               "per-candidate PASS budget %.6g"
               % topology["pass_per_candidate_N_budget"]),
    ]


def check_snapshots(_workdir):
    """v1.0 and v1.1 snapshots must verify byte-exactly (requirement 11)."""
    import hashlib
    results = []
    for version, manifest_path in (
            ("v1.0", "results/harness-release-manifest-v1.0.json"),
            ("v1.1", "results/harness-release-manifest-v1.1.json")):
        root = os.path.join(ROOT, "releases", version)
        manifest_full = os.path.join(ROOT, manifest_path)
        if not (os.path.isdir(root) and os.path.isfile(manifest_full)):
            results.append(_check("snapshot: %s verifies byte-exactly" % version,
                                  False, "snapshot or manifest missing"))
            continue
        with open(manifest_full, "r") as handle:
            manifest = json.load(handle)
        bad, count = [], 0
        for entries in manifest["artifact_groups"].values():
            for path, digest in entries.items():
                if digest is None:
                    continue
                target = os.path.join(root, path)
                if not os.path.isfile(target):
                    bad.append(path)
                    continue
                count += 1
                if hashlib.sha256(open(target, "rb").read()).hexdigest() != digest:
                    bad.append(path)
        results.append(_check(
            "snapshot: %s verifies byte-exactly" % version,
            not bad and count == manifest["artifact_count"],
            "%d/%d artifacts match the %s manifest (digest %s)"
            % (count, manifest["artifact_count"], version,
               manifest["release_digest"][:12]),
            {"mismatches": bad[:5]}))
    return results


def check_zero_real_calls(_workdir):
    """No real campaign evidence or result may exist (requirement 12)."""
    import ast
    import sys as _sys

    # Completed checkpoints are preserved as permanent records, so "no
    # evidence anywhere" stopped being the invariant after v1.2. What must
    # hold is that no artifact exists for the version CURRENTLY being
    # prepared. The version is derived rather than hardcoded: hardcoding it
    # made this check go stale at every release, which it did three times.
    from . import freeze as freeze_module
    version = "v%s" % freeze_module.HARNESS_VERSION
    results_dir = os.path.join(ROOT, "results")
    evidence = os.path.join(results_dir, "campaign-evidence-%s" % version)
    reports = [name for name in os.listdir(results_dir)
               if name.startswith("campaign-report") and version in name]
    historical = [name for name in os.listdir(results_dir)
                  if name.startswith("campaign-report") and version not in name]

    # Parse the module's real import statements rather than grepping its text:
    # this function's own source contains the word "transport" in string
    # literals, so a substring search would report a false positive against
    # itself.
    tree = ast.parse(open(os.path.join(ROOT, "harness", "dryrun.py")).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.add(base)
            imported.update("%s.%s" % (base, a.name) if base else a.name
                            for a in node.names)
    touches_transport = any("transport" in name for name in imported)
    loaded = [name for name in _sys.modules
              if name.endswith("harness.transport")]

    return [
        _check("zero calls: no campaign evidence directory for the version in preparation",
               not os.path.isdir(evidence),
               "evidence directory for %s absent; preserved earlier "
               "checkpoints are records, not artifacts of this version" % version if False else
               "evidence directory for the version in preparation is absent; "
               "preserved earlier checkpoints are records, not artifacts of it"),
        _check("zero calls: no campaign result artifact for the version in preparation",
               not reports,
               "reports for this version: %s (earlier artifacts retained: "
               "%s)" % (reports or "none", historical or "none")),
        _check("zero calls: the dry run never imports the transport layer",
               not touches_transport,
               "AST of harness/dryrun.py shows %d imports, none referencing "
               "transport" % len(imported)),
        _check("zero calls: the transport module is not even loaded",
               not loaded,
               "harness.transport absent from sys.modules during the dry run"),
    ]


# ---------------------------------------------------------------------------
# v1.1 area 3: batch item identity
# ---------------------------------------------------------------------------

def check_batch_identity(_workdir):
    cell = dry_cells()[0]
    items = []
    for replication in range(6):
        payload, _seed = sim.build_payload(cell, DRY_N[0], replication)
        key = "%s|N=%d|rep=%d" % (cell["cell_id"], DRY_N[0], replication)
        payload["analysis_id"] = key
        items.append((key, payload))
    keys = [key for key, _ in items]

    def dispatch(mode, batch_size=3, concurrency=2):
        target = BatchTarget(mode)
        dispatcher = batching.BatchDispatcher(target, batch_size=batch_size,
                                              concurrency=concurrency)
        return dispatcher.dispatch(items), dispatcher, target

    checks = []

    results, dispatcher, target = dispatch("clean")
    correct = all(
        results[key]["response"] is not None
        and results[key]["response"].get("analysis_id") == key for key in keys)
    checks.append(_check(
        "batch: clean batches attribute every item to its own id",
        correct and set(results) == set(keys) and target.batch_calls == 2,
        "%d items over %d batches, every response carries its requesting id"
        % (len(keys), target.batch_calls)))

    results, _dispatcher, _target = dispatch("shuffled")
    correct = all(
        results[key]["response"] is not None
        and results[key]["response"].get("analysis_id") == key for key in keys)
    checks.append(_check(
        "batch: reordered results are re-attributed by id, not position",
        correct,
        "a fully reversed batch response still maps each result to its own item"))

    results, _dispatcher, _target = dispatch("partial")
    delivered = [k for k in keys if results[k]["response"] is not None]
    missing = [k for k in keys if results[k]["response"] is None]
    codes = {results[k]["error"]["code"] for k in missing}
    checks.append(_check(
        "batch: partial response blocks only the absent items",
        len(missing) == 2 and codes == {batching.ERROR_ITEM_MISSING}
        and all(results[k]["response"].get("analysis_id") == k
                for k in delivered),
        "%d delivered, %d explicitly blocked as missing" % (len(delivered),
                                                            len(missing))))

    results, _dispatcher, _target = dispatch("malformed")
    bad = [k for k in keys if results[k]["response"] is None]
    checks.append(_check(
        "batch: a malformed item blocks only that item",
        len(bad) == 2
        and all(results[k]["error"]["code"] == batching.ERROR_ITEM_MALFORMED
                for k in bad),
        "%d malformed items blocked; the rest delivered" % len(bad)))

    results, _dispatcher, _target = dispatch("misidentified")
    mismatched = [k for k in keys
                  if results[k]["response"] is None
                  and results[k]["error"]["code"] in
                  (batching.ERROR_ITEM_MISSING, batching.ERROR_IDENTITY_MISMATCH)]
    no_crosstalk = all(
        results[key]["response"] is None
        or results[key]["response"].get("analysis_id") == key for key in keys)
    checks.append(_check(
        "batch: a duplicated/foreign id never contaminates another item",
        no_crosstalk and bool(mismatched),
        "%d item(s) refused rather than misattributed; no response is "
        "attributed to an item that did not produce it" % len(mismatched)))

    results, dispatcher, target = dispatch("interrupted")
    recovered = all(results[key]["response"] is not None for key in keys)
    via = {results[key]["via"] for key in keys}
    checks.append(_check(
        "batch: an interrupted batch falls back to singles with no loss",
        recovered and via == {"single"}
        and dispatcher.stats["single_fallbacks"] == 2,
        "all %d items recovered individually after the batch was interrupted"
        % len(keys)))

    results, dispatcher, _target = dispatch("envelope_rejected")
    recovered = all(results[key]["response"] is not None for key in keys)
    checks.append(_check(
        "batch: a rejected envelope falls back to singles with no loss",
        recovered, "all %d items recovered after a 422 envelope rejection"
        % len(keys)))

    results, _dispatcher, _target = dispatch("idfree")
    correct = all(results[key]["response"] is not None for key in keys)
    checks.append(_check(
        "batch: complete id-free responses align positionally",
        correct, "positional alignment permitted only when the count matches"))

    results, _dispatcher, _target = dispatch("idfree_partial")
    refused = [k for k in keys if results[k]["response"] is None]
    codes = {results[k]["error"]["code"] for k in refused}
    checks.append(_check(
        "batch: short id-free responses refuse positional alignment entirely",
        len(refused) == len(keys)
        and codes == {batching.ERROR_AMBIGUOUS_ALIGNMENT},
        "a short id-free response cannot be aligned safely, so every item in "
        "that batch is blocked rather than shifted"))

    contract = batching.BatchDispatcher(BatchTarget("clean"), batch_size=64,
                                        concurrency=16).contract()
    checks.append(_check(
        "batch: frozen limits are enforced",
        contract["max_batch_items"] == batching.MAX_BATCH_ITEMS
        and contract["max_concurrency"] == batching.MAX_CONCURRENCY,
        "requested 64 items / 16 concurrent, clamped to %d / %d"
        % (contract["max_batch_items"], contract["max_concurrency"])))
    return checks


# ---------------------------------------------------------------------------
# v1.1 area 4: frozen-artifact drift
# ---------------------------------------------------------------------------

def check_integrity_gate(workdir):
    """Altering a frozen artifact after freeze must abort before call one."""
    store = campaign_module.EvidenceStore(os.path.join(workdir, "integrity"),
                                          block_size=DRY_BLOCK)
    counting = {"calls": 0}

    class CountingTarget(object):
        def analyze(self, payload):
            counting["calls"] += 1
            return SoundReferenceTarget().analyze(payload)

        analyze_batch = _batch_via_analyze

    def drifted_integrity():
        return {"intact": False, "artifacts_checked": 90,
                "release_digest": "deadbeef",
                "mismatches": ["harness/oracle/core.py"], "missing": []}

    report = make_campaign(CountingTarget(), store, cells=dry_cells()[:1],
                           integrity_check=drifted_integrity,
                           label="integrity-drift").run()
    aborted = (report["status"] == "ABORTED_INVALID"
               and report["abort_phase"] == "pre-flight-integrity"
               and report["campaign_valid"] is False)
    no_calls = counting["calls"] == 0
    identity_not_reached = "identity_before" not in report

    def intact_integrity():
        return {"intact": True, "artifacts_checked": 90,
                "release_digest": "abc123", "mismatches": [], "missing": []}

    store2 = campaign_module.EvidenceStore(os.path.join(workdir, "integrity-ok"),
                                           block_size=DRY_BLOCK)
    report2 = make_campaign(SoundReferenceTarget(), store2,
                            cells=dry_cells()[:1],
                            integrity_check=intact_integrity,
                            label="integrity-ok").run()
    stamped = False
    slug = report2["segments"][0]["evidence_slug"]
    entry = store2.read_record(slug, 0)["index_entry"]
    stamped = entry.get("release_integrity_digest") == "abc123"

    # NOTE: whether the *live* tree currently matches its manifest is
    # deliberately NOT asserted here. The dry run executes before the v1.1
    # freeze, so the working tree legitimately differs from the v1.0 manifest
    # and such an assertion would either fail spuriously or force the dry run
    # to run after freezing, which would let unverified code be frozen. The
    # live check belongs in the post-freeze verification sequence; what is
    # asserted here is that the mechanism detects drift and blocks on it.
    return [
        _check("integrity: a drifted frozen artifact aborts the campaign",
               aborted, "status=%s phase=%s"
               % (report["status"], report.get("abort_phase")),
               {"reason": report.get("abort_reason")}),
        _check("integrity: abort happens before scientific call one",
               no_calls and report.get("scientific_calls_made") == 0,
               "target analyze calls made: %d" % counting["calls"]),
        _check("integrity: abort happens before the identity call too",
               identity_not_reached,
               "integrity is checked first, so no request of any kind is made"),
        _check("integrity: the release digest is stamped into every record",
               stamped,
               "index records carry release_integrity_digest for provenance"),
    ]


# ---------------------------------------------------------------------------
# v1.1 area 5: storage-only checkpoint
# ---------------------------------------------------------------------------

def check_storage_checkpoint(workdir):
    store = campaign_module.EvidenceStore(os.path.join(workdir, "checkpoint"),
                                          block_size=DRY_BLOCK)
    cells = dry_cells()
    report = make_campaign(SoundReferenceTarget(), store, cells=cells,
                           candidate_n=(8, 30),
                           mode=campaign_module.MODE_STORAGE_CHECKPOINT,
                           label="checkpoint").run()

    checkpoint = report.get("checkpoint", {})
    expected_slug = store.slug(cells[0]["cell_id"], 8)
    stopped_correctly = (checkpoint.get("segment", {}).get("evidence_slug")
                         == expected_slug
                         and checkpoint.get("stopped_after_first_segment") is True
                         and not report["segments"])

    archives = sorted(name for name in os.listdir(store.root)
                      if name.endswith(".index.jsonl"))
    only_one_segment = archives == [expected_slug + ".index.jsonl"]

    serialized = json.dumps(report)
    disposition_tokens = ("SUPPORTED", "EQUIVALENTLY_ABSENT", "INDETERMINATE",
                          "RANGE_CLEARED", "A_l", "verdict_counts",
                          "engine_result_reason")
    leaked = [token for token in disposition_tokens if token in serialized]

    entries = []
    with open(store._path(expected_slug, ".index.jsonl"), "r") as handle:
        for line in handle:
            entries.append(json.loads(line))
    withheld = all(entry["decision_record"] is None
                   and entry["dispositions_withheld"] is True
                   for entry in entries)
    digests = all(entry["response_sha256"] and entry["request_sha256"]
                  for entry in entries)
    bodies_retained = all(
        store.read_record(expected_slug, entry["replication"])["sha256_matches"]
        for entry in entries)

    return [
        _check("checkpoint: stops after exactly the first defined segment",
               stopped_correctly and only_one_segment,
               "wrote only %s of %d segments"
               % (expected_slug, checkpoint.get("segments_remaining", 0) + 1),
               {"segments_remaining": checkpoint.get("segments_remaining")}),
        _check("checkpoint: no scientific disposition is exposed in the report",
               not leaked and report["dispositions_exposed"] is False,
               "no disposition token appears in the checkpoint report",
               {"tokens_found": leaked}),
        _check("checkpoint: index records withhold decision records",
               withheld and bool(entries),
               "all %d index records carry decision_record=null with "
               "dispositions_withheld=true" % len(entries)),
        _check("checkpoint: evidence is still fully retained and verifiable",
               digests and bodies_retained,
               "every response body retained with a verifying SHA-256"),
        _check("checkpoint: reports the measured compression ratio",
               (checkpoint.get("measured_compression_ratio_responses") or 0) > 1,
               "measured response compression ratio %.1fx on real evidence"
               % (checkpoint.get("measured_compression_ratio_responses") or 0)),
        _check("checkpoint: engine state remains NOT_ASSESSED",
               report["engine_result_state"] == "NOT_ASSESSED",
               "a storage checkpoint computes no engine disposition"),
        _check("checkpoint: the blinding rule is frozen into the report",
               report.get("blinding_rule") == campaign_module.BLINDING_RULE
               and "may inspect, decode, summarize, search"
               in report["blinding_rule"]
               and "continuation decision must be recorded"
               in report["blinding_rule"],
               "the non-inspection rule travels with the checkpoint report"),
        _check("checkpoint: the report states the honest limitation",
               ("does NOT make an early read impossible"
                in report["blinding_attestation"]["honest_limitation"]
                and report["blinding_attestation"]["dispositions_computed"]
                is False),
               "the report says plainly that blinding is procedural, not "
               "technical: the archives could be decoded by hand"),
        _check("checkpoint: no event-tally material in the report",
               not any(token in json.dumps(report)
                       for token in ("P_PASS", "P_FAIL", "events\":",
                                     "event_tally", "observed_rate")),
               "no event tally or rate appears in the checkpoint report"),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all(sequential_replications=150000):
    workdir = tempfile.mkdtemp(prefix="blackbox-dryrun-")
    checks = []
    sample = None
    try:
        retention, sample = check_retention_and_indexing(workdir)
        checks += retention
        checks += check_resume(workdir)
        checks += check_torn_write(workdir)
        checks += check_identity_mismatch(workdir)
        checks += check_failure_handling(workdir)
        checks += check_unresolved(workdir)
        checks += check_per_n_topology(workdir)
        checks += check_sequential_error_control(workdir, sequential_replications)
        checks += check_batch_identity(workdir)
        checks += check_integrity_gate(workdir)
        checks += check_storage_checkpoint(workdir)
        checks += check_v13_negative_controls(workdir)
        checks += check_v14_concurrency_controls(workdir)
        checks += check_oc_determinism(workdir)
        checks += check_snapshots(workdir)
        checks += check_zero_real_calls(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    passed = sum(1 for check in checks if check["passed"])
    return {
        "dryrun_version": "1.1",
        "purpose": ("Operational verification of the v1.1 campaign runner "
                    "against the local sound reference and local mutants."),
        "configuration": {
            "cells": list(DRY_CELL_IDS), "N": list(DRY_N),
            "look_1": DRY_LOOK_1, "look_2": DRY_LOOK_2,
            "block_size": DRY_BLOCK,
            "sequential_replications": sequential_replications,
        },
        "real_engine_scientific_calls": 0,
        "real_engine_contacted": False,
        "isolation_note": ("This module never constructs a BlackBoxTarget and "
                           "never imports harness.transport, so the real "
                           "engine's zero scientific-call count is preserved "
                           "by construction."),
        "checks": checks,
        "failed_checks": [c["name"] for c in checks if not c["passed"]],
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "sample_report_excerpt": ({
            "status": sample["status"],
            "campaign_valid": sample["campaign_valid"],
            "engine_result_state": sample["engine_result_state"],
            "per_N": sample.get("per_N"),
            "storage": sample["storage"],
        } if sample else None),
    }
