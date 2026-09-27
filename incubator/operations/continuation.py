"""Checkpoint-to-full-campaign continuation (v1.5.3).

WHAT THIS IS FOR
----------------
The v1.5.2 storage checkpoint committed 500 replications of the first segment
and passed. The full campaign must use those 500 as the first look of that
segment **exactly once**: no new target calls for replications 0-499, no double
counting, no mutation of the retained archive, no silent regeneration, and no
starting over.

WHY A COPY RATHER THAN A REFERENCE
----------------------------------
The frozen runner's `EvidenceStore.recover()` rewrites the index file it reads
-- that is how it repairs a partial write after a crash. Pointing the runner at
the retained v1.5.2 directory would therefore mutate the authoritative archive
on the first call, even in the ordinary case where nothing needs repairing.

So the continuation imports a byte-identical copy into the v1.5.3 evidence
directory and verifies it afterwards. v1.5.2 is opened read-only, never
written, and its digests are re-checked after the copy to prove it.

HOW EXACT-ONCE FALLS OUT
------------------------
No change to the frozen core is needed. `_run_and_tally` calls `recover(slug)`,
computes `pending = [r for r in range(upto) if r not in completed]`, and issues
calls only for `pending`. With 0-499 already committed and a 500-replication
first look, `pending` is empty: zero new calls, and the look is scored from the
stored raw responses by the campaign's normal decision process.

That last point matters. The checkpoint withheld the computed *disposition*
(every index record carries `decision_record: null`), but it retained every raw
response verbatim under decision D1. `_tally_from_evidence` re-reads those raw
responses rather than trusting any stored verdict, so the inherited replications
are scored at the same time, by the same code, as everything else.

WHAT THIS MODULE MUST NOT DO
----------------------------
Decode an archive, read a response body, or compute a disposition. It verifies
structure, digests and identity only. Scoring belongs to the campaign.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import gzip
import hashlib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREDECESSOR_VERSION = "1.5.2"
PREDECESSOR_RELEASE_DIGEST = \
    "59412577ecbc99db5a2a7bf3d260b4d3a00d101a0fb0c2935157abf74b5b23fa"
PREDECESSOR_APPROVAL_DIGEST = \
    "f70107cf5505e64ee8c75d819d42ca67d97e1e20479d79a59fb183451856022a"

CHECKPOINT_REPORT = os.path.join(
    ROOT, "results", "campaign-report-checkpoint-v1.5.2.json")
CHECKPOINT_EVIDENCE = os.path.join(ROOT, "results", "campaign-evidence-v1.5.2")
DECISION_RECORD = os.path.join(
    ROOT, "results", "continuation-decision-v1.5.2-001.json")
INVENTORY = os.path.join(ROOT, "results", "checkpoint-lineage",
                         "checkpoint-v1.5.2-inventory.json")
SEAL = os.path.join(ROOT, "results", "checkpoint-lineage",
                    "checkpoint-v1.5.2-seal.json")

EXPECTED_SLUG = "G1-C1-NULL-P0-1_2__N8"
EXPECTED_CELL = "G1-C1-NULL-P0-1_2"
EXPECTED_N = 8
EXPECTED_REPLICATIONS = 500
REQUIRED_DECISION = "CONTINUE_AFTER_PASSED_STORAGE_CHECKPOINT"


class ContinuationRefused(Exception):
    """Raised rather than proceeding on anything that does not verify."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load(path):
    with open(path, "r") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

def verify(expected_release_digest=None, expected_approval_digest=None,
           report_path=None, evidence_dir=None, decision_path=None,
           inventory_path=None):
    """Every reason the checkpoint may not be inherited. Empty list = it may.

    Returns every problem rather than the first, so a refusal is diagnosable
    without repeated attempts. Paths are parameters purely so the negative
    controls can point them at crafted fixtures.
    """
    report_path = report_path or CHECKPOINT_REPORT
    evidence_dir = evidence_dir or CHECKPOINT_EVIDENCE
    decision_path = decision_path or DECISION_RECORD
    inventory_path = inventory_path or INVENTORY

    problems = []
    facts = {}

    # -- 1. the continuation decision must exist and be the right one --------
    if not os.path.isfile(decision_path):
        problems.append("no continuation-decision record at %s; the frozen "
                        "blinding rule requires the decision to be recorded "
                        "before the archives may be used"
                        % os.path.relpath(decision_path, ROOT))
        decision = {}
    else:
        try:
            decision = _load(decision_path)
        except ValueError as exc:
            problems.append("continuation-decision record is not valid JSON: %s"
                            % str(exc)[:80])
            decision = {}

    if decision:
        stored = decision.get("decision_digest")
        recomputed = canonical_digest(
            {k: v for k, v in decision.items() if k != "decision_digest"})
        if stored != recomputed:
            problems.append("continuation-decision record has been altered: "
                            "stored digest %s, recomputed %s"
                            % (str(stored)[:16], recomputed[:16]))
        if decision.get("decision") != REQUIRED_DECISION:
            problems.append("continuation decision is %r, required %r"
                            % (decision.get("decision"), REQUIRED_DECISION))
        basis = decision.get("authorization_basis") or {}
        for field in ("raw_archives_inspected", "raw_archives_decoded",
                      "scientific_disposition_inspected",
                      "scientific_disposition_computed"):
            if basis.get(field) is not False:
                problems.append("decision record does not attest %s is False"
                                % field)
        facts["decision_digest"] = recomputed

    # -- 2. the checkpoint report -------------------------------------------
    if not os.path.isfile(report_path):
        problems.append("no checkpoint report at %s"
                        % os.path.relpath(report_path, ROOT))
        report = {}
    else:
        report_digest = sha256_file(report_path)
        facts["checkpoint_report_digest"] = report_digest
        expected_report_digest = (decision.get("predecessor") or {}).get(
            "checkpoint_report_digest")
        if expected_report_digest and report_digest != expected_report_digest:
            problems.append("checkpoint report has been altered since the "
                            "decision was recorded: %s, expected %s"
                            % (report_digest[:16], expected_report_digest[:16]))
        try:
            report = _load(report_path)
        except ValueError as exc:
            problems.append("checkpoint report is not valid JSON: %s"
                            % str(exc)[:80])
            report = {}

    if report:
        if report.get("checkpoint_disposition") != "CHECKPOINT_PASSED":
            problems.append("checkpoint disposition is %r, required "
                            "CHECKPOINT_PASSED"
                            % report.get("checkpoint_disposition"))
        if report.get("campaign_valid") is not True:
            problems.append("checkpoint campaign_valid is %r, required True"
                            % report.get("campaign_valid"))
        audit = report.get("checkpoint_audit") or {}
        for field, want in (("requested", EXPECTED_REPLICATIONS),
                            ("successful_analyses", EXPECTED_REPLICATIONS),
                            ("records", EXPECTED_REPLICATIONS),
                            ("blocked", 0), ("digest_failures", 0),
                            ("missing_responses", 0),
                            ("non_analysis_responses", 0)):
            if audit.get(field) != want:
                problems.append("checkpoint audit %s is %r, required %r"
                                % (field, audit.get(field), want))
        if audit.get("passed") is not True:
            problems.append("checkpoint audit did not pass")

        segment = (report.get("checkpoint") or {}).get("segment") or {}
        if segment.get("evidence_slug") != EXPECTED_SLUG:
            problems.append("first segment is %r, expected %r"
                            % (segment.get("evidence_slug"), EXPECTED_SLUG))
        if segment.get("cell_id") != EXPECTED_CELL or segment.get("N") != EXPECTED_N:
            problems.append("first segment identity is %r/N=%r, expected %r/N=%r"
                            % (segment.get("cell_id"), segment.get("N"),
                               EXPECTED_CELL, EXPECTED_N))
        if segment.get("replications_stored") != EXPECTED_REPLICATIONS:
            problems.append("segment stored %r replications, expected %d"
                            % (segment.get("replications_stored"),
                               EXPECTED_REPLICATIONS))
        if segment.get("missing") or segment.get("duplicated"):
            problems.append("segment reports missing=%r duplicated=%r"
                            % (segment.get("missing"), segment.get("duplicated")))

        transport = report.get("transport_reconciliation") or {}
        stats = transport.get("dispatcher_stats") or {}
        if transport.get("reconciled") is not True:
            problems.append("checkpoint transport did not reconcile")
        if stats.get("retries_performed") not in (0, None) and \
                stats.get("retries_performed") != 0:
            problems.append("checkpoint performed %r retries, required 0"
                            % stats.get("retries_performed"))
        flight = report.get("in_flight") or {}
        if flight.get("max_observed_in_flight") not in (0, 1):
            problems.append("checkpoint observed %r analysis calls in flight, "
                            "required at most 1"
                            % flight.get("max_observed_in_flight"))
        if flight.get("violations"):
            problems.append("checkpoint recorded %r in-flight violations"
                            % flight.get("violations"))

        if (report.get("identity_before") or {}).get("metadata") != \
                (report.get("identity_after") or {}).get("metadata"):
            problems.append("target identity changed during the checkpoint")

        if report.get("dispositions_exposed") is not False:
            problems.append("checkpoint report exposes dispositions")

        stamp = report.get("provenance_stamp") or {}
        facts["checkpoint_release_digest"] = stamp.get("release_digest")
        facts["checkpoint_approval_digest"] = stamp.get("approval_record_digest")
        facts["target_identity_digest"] = stamp.get("target_identity_digest")
        if expected_release_digest and \
                stamp.get("release_digest") != expected_release_digest:
            problems.append("checkpoint was produced under release %s, "
                            "expected %s"
                            % (str(stamp.get("release_digest"))[:16],
                               expected_release_digest[:16]))
        if expected_approval_digest and \
                stamp.get("approval_record_digest") != expected_approval_digest:
            problems.append("checkpoint was produced under approval %s, "
                            "expected %s"
                            % (str(stamp.get("approval_record_digest"))[:16],
                               expected_approval_digest[:16]))

    # -- 3. run and campaign identity ---------------------------------------
    predecessor = decision.get("predecessor") or {}
    if report:
        for label, want in (("run_id", predecessor.get("run_id")),
                            ("campaign_id", predecessor.get("campaign_id"))):
            facts[label] = want
        want_target = predecessor.get("target_identity_digest")
        got_target = (report.get("provenance_stamp") or {}).get(
            "target_identity_digest")
        if want_target and got_target != want_target:
            problems.append("target identity digest does not match the "
                            "decision record: %s vs %s"
                            % (str(got_target)[:16], str(want_target)[:16]))

    # -- 4. evidence structure, digests and index prefix --------------------
    inventory = _load(inventory_path) if os.path.isfile(inventory_path) else {}
    if not inventory:
        problems.append("no evidence inventory at %s"
                        % os.path.relpath(inventory_path, ROOT))
    else:
        stored = inventory.get("inventory_digest")
        recomputed = canonical_digest(
            {k: v for k, v in inventory.items() if k != "inventory_digest"})
        if stored != recomputed:
            problems.append("evidence inventory has been altered")
        expected_inventory = predecessor.get("evidence_inventory_digest")
        if expected_inventory and stored != expected_inventory:
            problems.append("evidence inventory digest does not match the "
                            "decision record")
        facts["evidence_inventory_digest"] = stored

        for name, meta in sorted((inventory.get("files") or {}).items()):
            path = os.path.join(evidence_dir, name)
            if not os.path.isfile(path):
                problems.append("evidence file missing: %s" % name)
                continue
            if sha256_file(path) != meta["sha256"]:
                problems.append("evidence file altered: %s" % name)

    index_path = os.path.join(evidence_dir, EXPECTED_SLUG + ".index.jsonl")
    if not os.path.isfile(index_path):
        problems.append("no index at %s" % os.path.relpath(index_path, ROOT))
    else:
        seen, order, malformed = set(), [], 0
        missing_digest = 0
        with open(index_path, "r") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    malformed += 1
                    continue
                replication = entry.get("replication")
                order.append(replication)
                seen.add(replication)
                if not entry.get("response_sha256") or \
                        not entry.get("request_sha256"):
                    missing_digest += 1
                if entry.get("blocked"):
                    problems.append("index records a blocked replication (%r)"
                                    % replication)
        if malformed:
            problems.append("%d malformed index records" % malformed)
        if missing_digest:
            problems.append("%d index records lack a request/response digest"
                            % missing_digest)
        duplicates = sorted({r for r in order if order.count(r) > 1})
        if duplicates:
            problems.append("duplicate replication indexes: %s"
                            % duplicates[:6])
        expected = set(range(EXPECTED_REPLICATIONS))
        if seen != expected:
            extra = sorted(seen - expected)[:6]
            absent = sorted(expected - seen)[:6]
            problems.append("index is not exactly 0-%d: %d present, missing "
                            "%s, unexpected %s"
                            % (EXPECTED_REPLICATIONS - 1, len(seen),
                               absent or "none", extra or "none"))
        if order != sorted(order):
            problems.append("index is not a contiguous ascending prefix")
        facts["committed_replications"] = len(seen)

    return {"ok": not problems, "problems": problems, "facts": facts,
            "checked": {
                "decision_record": os.path.relpath(decision_path, ROOT),
                "checkpoint_report": os.path.relpath(report_path, ROOT),
                "evidence_directory": os.path.relpath(evidence_dir, ROOT),
                "inventory": os.path.relpath(inventory_path, ROOT)},
            "archives_decoded": False,
            "response_bodies_read": False,
            "dispositions_computed": False}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def already_imported(destination):
    """Whether this destination already holds the inherited segment."""
    marker = os.path.join(destination, ".inherited-from-v1.5.2.json")
    return os.path.isfile(marker)


def import_checkpoint(destination, verification, source=None, dry_run=False):
    """Copy the checkpoint evidence into `destination`, verified both sides.

    Refuses if the destination already holds the segment, so the inherited
    replications cannot be imported twice.
    """
    source = source or CHECKPOINT_EVIDENCE
    if not verification["ok"]:
        raise ContinuationRefused(
            "refusing to import an unverified checkpoint: %s"
            % "; ".join(verification["problems"][:3]))

    marker = os.path.join(destination, ".inherited-from-v1.5.2.json")
    if os.path.isfile(marker):
        raise ContinuationRefused(
            "the first segment has already been inherited into %s; importing "
            "again would count the checkpoint replications twice"
            % os.path.relpath(destination, ROOT))

    inventory = _load(INVENTORY)
    names = sorted(inventory["files"])
    existing = [n for n in names
                if os.path.exists(os.path.join(destination, n))]
    if existing:
        raise ContinuationRefused(
            "destination already contains evidence for this segment: %s"
            % existing)

    if dry_run:
        return {"imported": False, "dry_run": True, "files": names}

    os.makedirs(destination, exist_ok=True)
    source_before = {n: sha256_file(os.path.join(source, n)) for n in names}

    copied = []
    for name in names:
        src = os.path.join(source, name)
        dst = os.path.join(destination, name)
        shutil.copyfile(src, dst)          # never copies permissions
        os.chmod(dst, 0o644)               # the runner must be able to append
        digest = sha256_file(dst)
        if digest != inventory["files"][name]["sha256"]:
            raise ContinuationRefused(
                "imported copy of %s does not match the sealed digest" % name)
        copied.append({"file": name, "sha256": digest,
                       "bytes": os.path.getsize(dst)})

    # The source must be exactly as it was. This is the whole point.
    source_after = {n: sha256_file(os.path.join(source, n)) for n in names}
    if source_after != source_before:
        raise ContinuationRefused(
            "the retained v1.5.2 archive changed during import")

    lineage = {
        "inherited_from": "v1.5.2 storage checkpoint",
        "predecessor_run_id": verification["facts"].get("run_id"),
        "predecessor_campaign_id": verification["facts"].get("campaign_id"),
        "checkpoint_report_digest":
            verification["facts"].get("checkpoint_report_digest"),
        "evidence_inventory_digest":
            verification["facts"].get("evidence_inventory_digest"),
        "continuation_decision_digest":
            verification["facts"].get("decision_digest"),
        "segment_slug": EXPECTED_SLUG,
        "cell_id": EXPECTED_CELL,
        "N": EXPECTED_N,
        "inherited_replications": EXPECTED_REPLICATIONS,
        "inherited_replication_range": [0, EXPECTED_REPLICATIONS - 1],
        "files": copied,
        "source_unchanged_by_import": True,
        "source_digests_before": source_before,
        "source_digests_after": source_after,
        "new_target_calls_for_inherited_replications": 0,
        "counted_once": True,
        "archives_decoded_during_import": False,
        "dispositions_computed_during_import": False,
        "note": "these replications were produced by the v1.5.2 checkpoint and "
                "are reused as the first look of the first segment. The full "
                "campaign scores them from the stored raw responses by its "
                "normal decision process; no verdict is inherited.",
    }
    with open(marker, "w") as handle:
        json.dump(lineage, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"imported": True, "dry_run": False, "lineage": lineage,
            "files": [c["file"] for c in copied]}


def lineage_of(destination):
    marker = os.path.join(destination, ".inherited-from-v1.5.2.json")
    return _load(marker) if os.path.isfile(marker) else None


def reconcile_requests(destination, total_physical_requests):
    """Split a campaign's request count into inherited and new.

    Without this the full campaign's totals would silently absorb the 500
    checkpoint calls, and there would be no way to tell an inherited
    replication from one this run paid for.
    """
    lineage = lineage_of(destination)
    inherited = lineage["inherited_replications"] if lineage else 0
    return {
        "inherited_replications_from_v1_5_2": inherited,
        "new_requests_issued_by_this_run": total_physical_requests,
        "total_scientific_replications": inherited + total_physical_requests,
        "inherited_replications_recalled": 0,
        "note": "inherited replications were not requested again; "
                "new_requests_issued_by_this_run counts only calls this run "
                "actually made",
    }
