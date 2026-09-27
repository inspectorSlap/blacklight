"""Coverage-campaign runner (harness v1.1).

Implements the campaign approved in the simulation-acceptance proposal. v1.1
corrects five operational defects found in v1.0 and is documented in
`reports/CAMPAIGN-RUNNER-v1.1.md`:

1. **Per-N result topology.** v1.0 collapsed any failing segment into a global
   `ENGINE_REJECTED`. That is wrong: a valid engine may legitimately fail to
   deliver adequate coverage at `N = 8` while being sound at `N = 30`, and
   `N` selection is a study decision. v1.1 reports a state per candidate `N`
   and reserves global rejection for defects that are `N`-independent.
2. **Valid two-look error control.** v1.0 spent the full per-cell level at both
   looks. v1.1 splits the budget prospectively across looks; see
   `harness/sequential.py`.
3. **Frozen batch and concurrency contract.** See `harness/batching.py`.
4. **Storage-only first-segment checkpoint**, which writes and measures
   evidence without computing or exposing any scientific disposition.
5. **Pre-flight release-integrity recomputation** before any scientific
   request.

Retained from v1.0 unchanged: identity binding, full compressed retention with
per-response SHA-256 and a byte-offset index, and crash-safe resume.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import datetime
import gzip
import hashlib
import json
import os

from . import adapter, batching, inflight, roster, sequential, serial
from . import simulation as sim
from .checks import rules

CAMPAIGN_VERSION = "1.4"
ANALYSIS_SCHEMA = "blackbox.ordinal.ordinal-analysis.v0.1"
EVIDENCE_VERSION = "1.1"
DEFAULT_BLOCK_SIZE = 100

CLAIM = rules.CLAIM_CLASSES
C4_CLAIM = rules.C4_CLAIM_CLASSES
C5_CLAIM = rules.C5_CLAIM_CLASSES

# Structural defects that cannot be explained by finite resolution at a small
# replicate count. These are logic errors, so they reject the engine globally
# rather than only at the N where they were observed.
N_INDEPENDENT_EVENTS = (
    "zero_width_interval",
    "pooled_verdict_emitted",
    "c3_not_withheld",
    "degeneracy_routed_to_engine_failure",
)
ZERO_TOLERANCE_EVENTS = N_INDEPENDENT_EVENTS
REPORT_ONLY_EVENTS = ("claim_earned",)

NOMINAL = 0.05
CELL_LEVEL = sim.CELL_LEVEL

MODE_FULL = "full"
MODE_STORAGE_CHECKPOINT = "storage_checkpoint"

# Frozen checkpoint blinding rule (v1.2).
#
# The storage checkpoint does not COMPUTE dispositions, but its retained raw
# archives necessarily contain complete engine output and can be decoded by
# hand. Withholding computation is therefore not the same as making an early
# read impossible, and v1.1 overstated the guarantee. What actually protects
# the campaign is this procedural commitment.
BLINDING_RULE = (
    "Before the storage-based continuation decision is recorded, neither the "
    "operator, a coding agent, nor any reviewer may inspect, decode, "
    "summarize, search, or otherwise access the checkpoint's raw "
    "request/response archives. Only the checkpoint's storage, completeness, "
    "integrity, compression, identity, and provenance report may be reviewed. "
    "The continuation decision must be recorded before those archives may be "
    "used by the resumed campaign.")


def _is_analysis_shaped(body):
    """Structural test only: is this an analysis object at all?

    Deliberately reads NO disposition. It checks the schema version and the
    presence of the required top-level blocks, which is enough to tell an
    analysis from an error envelope without learning anything about engine
    behaviour. This keeps the checkpoint blind while still letting it fail
    closed on a non-analysis response.
    """
    if not isinstance(body, dict):
        return False
    if body.get("schema_version") != ANALYSIS_SCHEMA:
        return False
    for key in ("semantic_lights", "mechanical_lights"):
        block = body.get(key)
        if not isinstance(block, list) or len(block) != 3:
            return False
    return isinstance(body.get("cross_light"), dict)


def _utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class CampaignAborted(Exception):
    """Raised when the campaign must stop and be marked invalid."""


# ---------------------------------------------------------------------------
# Evidence store (unchanged from v1.0 apart from the version stamp)
# ---------------------------------------------------------------------------

class EvidenceStore(object):
    """Per-cell compressed archives with a byte-offset index."""

    def __init__(self, root, block_size=DEFAULT_BLOCK_SIZE):
        self.root = root
        self.block_size = block_size
        if not os.path.isdir(root):
            os.makedirs(root)

    def slug(self, cell_id, n):
        return "%s__N%d" % (cell_id.replace("/", "_"), n)

    def _path(self, slug, suffix):
        return os.path.join(self.root, slug + suffix)

    def recover(self, slug):
        """Durably completed replications, repairing any partial write."""
        index_path = self._path(slug, ".index.jsonl")
        if not os.path.isfile(index_path):
            for suffix in (".requests.gz", ".responses.gz"):
                path = self._path(slug, suffix)
                if os.path.isfile(path):
                    os.remove(path)
            return set(), 0

        sizes = {}
        for kind, suffix in (("requests", ".requests.gz"),
                             ("responses", ".responses.gz")):
            path = self._path(slug, suffix)
            sizes[kind] = os.path.getsize(path) if os.path.isfile(path) else 0

        surviving = []
        with open(index_path, "r") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    break
                ok = True
                for kind in ("requests", "responses"):
                    frame = record.get(kind)
                    if not frame:
                        ok = False
                        break
                    if frame["member_offset"] + frame["member_length"] > sizes[kind]:
                        ok = False
                        break
                if not ok:
                    break
                surviving.append(record)

        with open(index_path, "w") as handle:
            for record in surviving:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

        for kind, suffix in (("requests", ".requests.gz"),
                             ("responses", ".responses.gz")):
            extent = 0
            for record in surviving:
                frame = record[kind]
                extent = max(extent, frame["member_offset"] + frame["member_length"])
            path = self._path(slug, suffix)
            if os.path.isfile(path) and os.path.getsize(path) > extent:
                with open(path, "r+b") as handle:
                    handle.truncate(extent)

        return {record["replication"] for record in surviving}, len(surviving)

    def write_block(self, slug, records):
        """Append a block. Archives are written and fsynced before the index."""
        frames = {}
        for kind, key, suffix in (("requests", "request_raw", ".requests.gz"),
                                  ("responses", "response_raw", ".responses.gz")):
            payload = b""
            offsets = []
            for record in records:
                raw = record[key]
                offsets.append((len(payload), len(raw)))
                payload += raw + b"\n"
            blob = gzip.compress(payload, 9)
            path = self._path(slug, suffix)
            with open(path, "ab") as handle:
                handle.flush()
                member_offset = handle.tell()
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
            frames[kind] = (member_offset, len(blob), offsets)

        with open(self._path(slug, ".index.jsonl"), "a") as handle:
            for position, record in enumerate(records):
                entry = {
                    "evidence_version": EVIDENCE_VERSION,
                    "cell_id": record["cell_id"],
                    "N": record["N"],
                    "replication": record["replication"],
                    "seed": record["seed"],
                    "timestamp_utc": record["timestamp_utc"],
                    "target_identity_digest": record["meta_digest"],
                    "release_integrity_digest": record.get("integrity_digest"),
                    "blocked": record["blocked"],
                    "error": record["error"],
                    "transport": record.get("transport"),
                    "request_sha256": hashlib.sha256(record["request_raw"]).hexdigest(),
                    "response_sha256": hashlib.sha256(record["response_raw"]).hexdigest(),
                    "request_raw_length": len(record["request_raw"]),
                    "response_raw_length": len(record["response_raw"]),
                    "decision_record": record["decision_record"],
                    "dispositions_withheld": record.get("dispositions_withheld", False),
                }
                for kind in ("requests", "responses"):
                    member_offset, member_length, offsets = frames[kind]
                    record_offset, record_length = offsets[position]
                    entry[kind] = {
                        "archive": self.slug_archive_name(slug, kind),
                        "member_offset": member_offset,
                        "member_length": member_length,
                        "record_offset_in_block": record_offset,
                        "record_length": record_length,
                    }
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def slug_archive_name(self, slug, kind):
        return slug + (".requests.gz" if kind == "requests" else ".responses.gz")

    def read_record(self, slug, replication, kind="responses"):
        with open(self._path(slug, ".index.jsonl"), "r") as handle:
            for line in handle:
                entry = json.loads(line)
                if entry["replication"] != replication:
                    continue
                frame = entry[kind]
                suffix = ".requests.gz" if kind == "requests" else ".responses.gz"
                with open(self._path(slug, suffix), "rb") as archive:
                    archive.seek(frame["member_offset"])
                    blob = archive.read(frame["member_length"])
                block = gzip.decompress(blob)
                start = frame["record_offset_in_block"]
                raw = block[start:start + frame["record_length"]]
                digest = hashlib.sha256(raw).hexdigest()
                expected = entry["%s_sha256" % ("request" if kind == "requests"
                                                else "response")]
                return {"raw": raw, "sha256": digest,
                        "sha256_matches": digest == expected, "index_entry": entry}
        raise KeyError("replication %r not indexed in %s" % (replication, slug))


# ---------------------------------------------------------------------------
# Event extraction (unchanged semantics from v1.0)
# ---------------------------------------------------------------------------

def _interval_contains(interval, value, tol=1e-9):
    return interval[0] - tol <= value <= interval[1] + tol


def decision_record(normalized):
    return {
        "semantic_lights": [
            {"light_id": light["light_id"], "c1": light["c1"], "c2": light["c2"],
             "range": light["range"], "c4": light["c4"], "A_l": light["A_l"],
             "P0_bar": light["P0_bar"], "I_P_bar": light["I_P_bar"],
             "P0_bar_interval": light["P0_bar_interval"],
             "I_P_bar_interval": light["I_P_bar_interval"],
             "Q_bar": light.get("Q_bar"),
             "Q_bar_interval": light.get("Q_bar_interval"),
             "range_specimen": light["range_specimen_dispositions"],
             "specimen_G_intervals": [s["G_interval"] for s in light["specimens"]]}
            for light in normalized["semantic_lights"]],
        "mechanical_lights": [{"light_id": light["light_id"], "c5": light["c5"]}
                              for light in normalized["mechanical_lights"]],
        "cross_light": normalized["cross_light"],
    }


def extract_events(cell, normalized, truth):
    events = {}
    lights = normalized["semantic_lights"]
    cell_id = cell["cell_id"]

    zero_width = False
    for light in lights:
        for interval in (light["P0_bar_interval"], light["I_P_bar_interval"]):
            if interval[1] - interval[0] < 1e-9:
                zero_width = True
        for specimen in light["specimens"]:
            if specimen["G_interval"][1] - specimen["G_interval"][0] < 1e-9:
                zero_width = True
    events["zero_width_interval"] = zero_width
    events["pooled_verdict_emitted"] = (
        normalized["cross_light"]["pooled_verdict"] is not None)
    events["c3_not_withheld"] = normalized["cross_light"]["c3"] != "C3_WITHHELD"

    events["p0_noncoverage"] = any(
        not _interval_contains(light["P0_bar_interval"],
                               truth[i]["P0_bar_decimal"])
        for i, light in enumerate(lights))
    events["ip_noncoverage"] = any(
        not _interval_contains(light["I_P_bar_interval"],
                               truth[i]["I_P_bar_decimal"])
        for i, light in enumerate(lights))

    if cell_id.startswith("G1-"):
        events["false_c1_support"] = any(light["c1"] == "SUPPORTED"
                                         for light in lights)
    elif cell_id.startswith("G3-"):
        events["false_attenuation_claim"] = any(light["A_l"] for light in lights)
    elif cell_id.startswith("G5-"):
        if cell["population_targets"].get("outside_equivalence_region"):
            events["false_c1_equivalence"] = any(
                light["c1"] == "EQUIVALENTLY_ABSENT" for light in lights)
    elif cell_id.startswith("G6-"):
        if cell["population_targets"].get("outside_equivalence_region"):
            events["false_c2_equivalence"] = any(
                light["c2"] == "EQUIVALENTLY_ABSENT" for light in lights)
    elif cell_id.startswith("G7-"):
        if cell["population_targets"].get("attenuating_lights", 0) < 3:
            events["false_cross_light_generalization"] = (
                normalized["cross_light"]["A_all"])
    elif cell_id.startswith("G9-"):
        events["claim_despite_guard"] = any(
            light["c1"] in CLAIM or light["c2"] in CLAIM for light in lights)
    elif cell_id.startswith("G10-"):
        events["degeneracy_routed_to_engine_failure"] = any(
            light["c1"] == "INFERENCE_ENGINE_FAILURE"
            or light["c2"] == "INFERENCE_ENGINE_FAILURE" for light in lights)
    elif cell_id.startswith("G11-"):
        if cell_id.endswith(("BELOW", "AT")):
            events["false_range_clearance"] = any(
                light["range"] == "RANGE_CLEARED" for light in lights)
    elif cell_id.startswith("G12-") or cell_id.startswith("G13-"):
        if cell_id.endswith(("BELOW", "AT")) or cell_id.startswith("G13-"):
            events["false_c4_claim_without_capacity"] = any(
                light["c4"] in C4_CLAIM for light in lights)
    elif cell_id.startswith("G14-"):
        if cell_id.endswith(("BELOW", "AT")):
            events["false_c4_support"] = any(light["c4"] == "C4_SUPPORTED"
                                             for light in lights)
    elif cell_id.startswith("G15-"):
        mechanical = normalized["mechanical_lights"]
        if cell["population_targets"].get("control_eligible") is False:
            events["false_control_claim"] = any(light["c5"] in C5_CLAIM
                                                for light in mechanical)
        else:
            events["false_control_support"] = any(
                light["c5"] == "C5_SUPPORTED" for light in mechanical)

    if cell["family"] == "POWER":
        events["claim_earned"] = any(light["A_l"] for light in lights)
    return events


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

# Documented D6 enum values. These are v1.2-specific so that a v1.1-era
# approval cannot satisfy the v1.2 gate by accident.
PLAN_TWO_LOOK = "corrected_two_look"
PLAN_FIXED_STAGE = "corrected_fixed_stage"
PLAN_ENUM = (PLAN_TWO_LOOK, PLAN_FIXED_STAGE)

# Frozen v1.2 topology.
CANDIDATE_COUNT = len(sim.CANDIDATE_N)          # 6
PASS_FAMILY_BUDGET = CELL_LEVEL                 # 0.01 campaign-wide
FAIL_FAMILY_BUDGET = CELL_LEVEL                 # 0.01 campaign-wide


class DecisionPlanNotSelected(Exception):
    """Raised when operator decision D6 is absent, unknown or inconsistent."""


def default_plan(stage_1=None, stage_2=None, fixed_stage=False,
                 segment_count=None, candidate_count=None):
    looks = [stage_2 or sim.STAGE_2_REPLICATIONS] if fixed_stage else [
        stage_1 or sim.STAGE_1_REPLICATIONS, stage_2 or sim.STAGE_2_REPLICATIONS]
    if segment_count is None:
        segment_count = len(sim.build_grid()) * len(sim.CANDIDATE_N)
    if candidate_count is None:
        candidate_count = CANDIDATE_COUNT
    return sequential.Plan(
        looks=looks, nominal=NOMINAL,
        pass_level_family=PASS_FAMILY_BUDGET,
        fail_level_family=FAIL_FAMILY_BUDGET,
        label=PLAN_FIXED_STAGE if fixed_stage else PLAN_TWO_LOOK,
        candidate_count=candidate_count, segment_count=segment_count)


def validate_plan_topology(plan, candidate_count=None, segment_count=None):
    """Fail closed unless the plan matches the frozen v1.2 topology exactly."""
    expected_candidates = candidate_count or CANDIDATE_COUNT
    expected_segments = (segment_count
                         or len(sim.build_grid()) * len(sim.CANDIDATE_N))
    problems = []
    if plan.candidate_count != expected_candidates:
        problems.append("candidate_count is %r, expected %r"
                        % (plan.candidate_count, expected_candidates))
    if plan.segment_count != expected_segments:
        problems.append("segment_count is %r, expected %r"
                        % (plan.segment_count, expected_segments))
    if abs(plan.pass_level_family - PASS_FAMILY_BUDGET) > 1e-15:
        problems.append("PASS family budget is %r, expected %r"
                        % (plan.pass_level_family, PASS_FAMILY_BUDGET))
    if abs(plan.fail_level_family - FAIL_FAMILY_BUDGET) > 1e-15:
        problems.append("FAIL family budget is %r, expected %r"
                        % (plan.fail_level_family, FAIL_FAMILY_BUDGET))
    expected_pass = PASS_FAMILY_BUDGET / float(expected_candidates)
    if abs(plan.pass_level_per_candidate - expected_pass) > 1e-15:
        problems.append("PASS per-candidate budget is %r, expected %r"
                        % (plan.pass_level_per_candidate, expected_pass))
    expected_fail = FAIL_FAMILY_BUDGET / float(expected_segments)
    if abs(plan.fail_level_per_segment - expected_fail) > 1e-18:
        problems.append("FAIL per-segment budget is %r, expected %r"
                        % (plan.fail_level_per_segment, expected_fail))
    if abs(sum(plan.pass_levels) - plan.pass_level_per_candidate) > 1e-15:
        problems.append("PASS per-look budgets do not sum to the per-candidate "
                        "budget")
    if abs(sum(plan.fail_levels) - plan.fail_level_per_segment) > 1e-18:
        problems.append("FAIL per-look budgets do not sum to the per-segment "
                        "budget")
    return problems


def resolve_decision_plan(approval, segment_count=None, candidate_count=None):
    """Build the decision plan selected by operator decision D6.

    D6 is NOT defaulted and is NOT inferred. An absent, unknown or
    topology-inconsistent selection raises, and the caller must refuse before
    any target or identity request. Choosing a plan silently would be making a
    prospective statistical decision on the operator's behalf.
    """
    approval = approval or {}
    if approval.get("status") != "APPROVED":
        raise DecisionPlanNotSelected(
            "operator approval status is %r, not 'APPROVED'"
            % approval.get("status"))
    decisions = approval.get("decisions") or {}
    d6 = decisions.get("D6") or {}
    selected = d6.get("plan")
    if selected not in PLAN_ENUM:
        raise DecisionPlanNotSelected(
            "operator decision D6 must be exactly one of %s; found %r. See "
            "reports/OPERATING-CHARACTERISTICS-v1.2.md for the prospective "
            "comparison." % (list(PLAN_ENUM), selected))
    plan = default_plan(fixed_stage=selected == PLAN_FIXED_STAGE,
                        segment_count=segment_count,
                        candidate_count=candidate_count)
    problems = validate_plan_topology(plan, candidate_count, segment_count)
    if problems:
        raise DecisionPlanNotSelected(
            "the selected plan does not match the frozen v1.2 topology: %s"
            % "; ".join(problems))
    return plan, selected


class Campaign(object):
    def __init__(self, target, identity_provider, store, expected_identity,
                 cells=None, candidate_n=None, plan=None, block_size=None,
                 label="campaign", mode=MODE_FULL, integrity_check=None,
                 dispatcher=None, batch_size=batching.MAX_BATCH_ITEMS,
                 concurrency=batching.MAX_CONCURRENCY,
                 segment_multiplicity=None, d6_plan=None,
                 approval_digest=None):
        self.d6_plan = d6_plan
        self.approval_digest = approval_digest
        self.target = target
        self.identity_provider = identity_provider
        self.store = store
        self.expected_identity = expected_identity
        self.cells = cells if cells is not None else sim.build_grid()
        self.candidate_n = list(candidate_n or sim.CANDIDATE_N)
        self.plan = plan or default_plan()
        self.block_size = block_size or store.block_size
        self.label = label
        self.mode = mode
        self.integrity_check = integrity_check
        # v1.4: serialized single-request transport. Batching is dropped
        # because it cannot be shown to honor one analysis call in flight.
        self.dispatcher = dispatcher or serial.SerialDispatcher(target)
        self.segment_multiplicity = (segment_multiplicity
                                     or len(self.cells) * len(self.candidate_n))
        self.wave_size = max(1, self.dispatcher.batch_size
                             * self.dispatcher.concurrency)
        inflight.GATE.reset()

    # -- pre-flight -------------------------------------------------------

    def preflight_integrity(self):
        """Recompute the complete release integrity BEFORE any scientific call."""
        if self.integrity_check is None:
            return {"performed": False,
                    "reason": "no integrity check supplied (local dry run)"}
        result = self.integrity_check()
        record = {
            "performed": True,
            "timestamp_utc": _utc(),
            "artifacts_checked": result.get("artifacts_checked"),
            "release_digest": result.get("release_digest"),
            "intact": bool(result.get("intact")),
            "mismatches": result.get("mismatches", []),
            "missing": result.get("missing", []),
        }
        if not record["intact"]:
            raise CampaignAborted(
                "release integrity check failed before any scientific request: "
                "%d artifact(s) altered or missing since the freeze (%s). The "
                "campaign must run against the frozen release it was qualified "
                "on." % (len(record["mismatches"]) + len(record["missing"]),
                         ", ".join((record["mismatches"] + record["missing"])[:5])))
        return record

    def check_identity(self, phase):
        meta = self.identity_provider()
        mismatches = [
            {"field": key, "expected": value, "observed": meta.get(key)}
            for key, value in self.expected_identity.items()
            if meta.get(key) != value]
        record = {"phase": phase, "timestamp_utc": _utc(), "metadata": meta,
                  "metadata_digest": canonical_digest(meta),
                  "matches_distributed_manifest": not mismatches,
                  "mismatches": mismatches}
        if mismatches:
            raise CampaignAborted(
                "%s target identity does not match the distributed manifest: %s"
                % (phase, ", ".join(m["field"] for m in mismatches)))
        return record

    # -- execution --------------------------------------------------------

    def _build_outcome(self, cell, n, replication, result, meta_digest,
                       integrity_digest, payload, seed):
        # The stored request must be byte-identical to what was SENT, including
        # the dispatch analysis_id, not a fresh regeneration that omits it.
        request_raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        blocked = False
        error = result.get("error")
        events = {}
        record = None
        withheld = self.mode == MODE_STORAGE_CHECKPOINT

        response = result.get("response")
        if response is None:
            blocked = True
            response_raw = json.dumps({"harness_error": error},
                                      sort_keys=True, default=str).encode("utf-8")
        else:
            response_raw = json.dumps(response, sort_keys=True).encode("utf-8")
            if not withheld:
                try:
                    normalized = adapter.normalize(response)
                    record = decision_record(normalized)
                    events = extract_events(cell, normalized,
                                            sim.population_truth(cell))
                except adapter.UndocumentedSchema as exc:
                    blocked = True
                    error = {"code": "UNDOCUMENTED_SCHEMA", "detail": str(exc)}
                except Exception as exc:
                    blocked = True
                    error = {"code": type(exc).__name__, "detail": str(exc)[:400]}

        return {
            "cell_id": cell["cell_id"], "N": n, "replication": replication,
            "seed": seed, "timestamp_utc": _utc(), "meta_digest": meta_digest,
            "integrity_digest": integrity_digest,
            "request_raw": request_raw, "response_raw": response_raw,
            "decision_record": record, "blocked": blocked, "error": error,
            "events": events, "transport": result.get("via"),
            "dispositions_withheld": withheld,
        }

    def _run_and_tally(self, cell, n, upto, meta_digest, integrity_digest):
        """Ensure replications 0..upto-1 exist; return tallies over them."""
        slug = self.store.slug(cell["cell_id"], n)
        completed, _ = self.store.recover(slug)
        pending = [r for r in range(upto) if r not in completed]

        block = []
        for start in range(0, len(pending), self.wave_size):
            wave = pending[start:start + self.wave_size]
            items = []
            built = {}
            for replication in wave:
                payload, seed = sim.build_payload(cell, n, replication)
                key = "%s|N=%d|rep=%d" % (cell["cell_id"], n, replication)
                payload["analysis_id"] = key
                roster.assert_payload(payload)  # zero-call, pre-transport
                built[replication] = (key, payload, seed)
                items.append((key, payload))
            results = self.dispatcher.dispatch(items)
            for replication in wave:
                key, payload, seed = built[replication]
                outcome = self._build_outcome(
                    cell, n, replication,
                    results.get(key, {"response": None,
                                      "error": {"code": "NO_RESULT"}}),
                    meta_digest, integrity_digest, payload, seed)
                block.append(outcome)
                if len(block) >= self.block_size:
                    self.store.write_block(slug, block)
                    block = []
        if block:
            self.store.write_block(slug, block)

        tallies = {}
        if self.mode != MODE_STORAGE_CHECKPOINT:
            self._tally_from_evidence(slug, cell, tallies, upto)
        final, _ = self.store.recover(slug)
        return tallies, final, slug

    def _tally_from_evidence(self, slug, cell, tallies, upto):
        """Recompute tallies from stored evidence, so resume is exact."""
        index_path = self.store._path(slug, ".index.jsonl")
        if not os.path.isfile(index_path):
            return
        truth = sim.population_truth(cell)
        with open(index_path, "r") as handle:
            for line in handle:
                entry = json.loads(line)
                if entry["replication"] >= upto:
                    continue
                if entry["blocked"]:
                    blocked = tallies.setdefault("_blocked",
                                                 {"events": 0, "trials": 0})
                    blocked["events"] += 1
                    continue
                stored = self.store.read_record(slug, entry["replication"])
                response = json.loads(stored["raw"].decode("utf-8"))
                normalized = adapter.normalize(response)
                for name, fired in extract_events(cell, normalized, truth).items():
                    tally = tallies.setdefault(name, {"events": 0, "trials": 0})
                    tally["trials"] += 1
                    if fired:
                        tally["events"] += 1

    def _duplicates(self, slug):
        index_path = self.store._path(slug, ".index.jsonl")
        seen, duplicates = set(), []
        if not os.path.isfile(index_path):
            return duplicates
        with open(index_path, "r") as handle:
            for line in handle:
                replication = json.loads(line)["replication"]
                if replication in seen:
                    duplicates.append(replication)
                seen.add(replication)
        return duplicates

    def _evaluate(self, tallies, look_index):
        results = {}
        for name, tally in sorted(tallies.items()):
            if name == "_blocked":
                continue
            if name in REPORT_ONLY_EVENTS:
                results[name] = {
                    "events": tally["events"], "trials": tally["trials"],
                    "observed_rate": tally["events"] / float(tally["trials"] or 1),
                    "verdict": "REPORTED_NOT_GATED",
                    "look": look_index + 1}
                continue
            if name in ZERO_TOLERANCE_EVENTS:
                results[name] = {
                    "events": tally["events"], "trials": tally["trials"],
                    "nominal": 0, "zero_tolerance": True,
                    "n_independent": name in N_INDEPENDENT_EVENTS,
                    "look": look_index + 1,
                    "verdict": "FAIL" if tally["events"] > 0 else "PASS"}
                continue
            verdict = self.plan.decide_at(look_index, tally["events"])
            pass_max, fail_min = self.plan.criticals[look_index]
            results[name] = {
                "events": tally["events"], "trials": tally["trials"],
                "observed_rate": tally["events"] / float(tally["trials"] or 1),
                "nominal": NOMINAL, "look": look_index + 1,
                "pass_if_events_at_most": pass_max,
                "fail_if_events_at_least": fail_min,
                "pass_level_this_look": self.plan.pass_levels[look_index],
                "fail_level_this_look": self.plan.fail_levels[look_index],
                "verdict": verdict}
        return results

    @staticmethod
    def _segment_verdict(results, blocked):
        if blocked:
            return "BLOCKED"
        verdicts = {entry["verdict"] for entry in results.values()}
        if "FAIL" in verdicts:
            return "FAIL"
        if "CONTINUE" in verdicts:
            return "CONTINUE"
        if "UNRESOLVED" in verdicts:
            return "UNRESOLVED"
        return "PASS"

    def run(self):
        report = {
            "campaign_version": CAMPAIGN_VERSION,
            "label": self.label,
            "mode": self.mode,
            "started_utc": _utc(),
            "configuration": {
                "configurations": len(self.cells),
                "candidate_N": self.candidate_n,
                "segments": self.segment_multiplicity,
                "decision_plan": self.plan.describe(),
                # NOTE: transport statistics are deliberately NOT captured
                # here. v1.3 snapshotted them at start of run and therefore
                # always reported zeros. They are generated at finalization.
                "transport_contract_placeholder":
                    "populated at report finalization",
                "block_size": self.block_size,
                "evidence_root": self.store.root,
            },
            # Frozen provenance stamp. Every field required by the v1.2 gate is
            # recorded in the report itself, so the report is self-describing
            # about the exact decision topology that produced it.
            "provenance_stamp": {
                "d6_plan": self.d6_plan,
                "candidate_count": self.plan.candidate_count,
                "segment_count": self.plan.segment_count,
                "pass_family_budget": self.plan.pass_level_family,
                "pass_per_candidate_N_budget": self.plan.pass_level_per_candidate,
                "pass_per_look_budget": self.plan.pass_levels[0],
                "fail_family_budget": self.plan.fail_level_family,
                "fail_per_segment_budget": self.plan.fail_level_per_segment,
                "fail_per_look_budget": self.plan.fail_levels[0],
                "approval_record_digest": self.approval_digest,
                "release_digest": None,  # filled after the integrity pre-flight
                "harness_version": CAMPAIGN_VERSION,
            },
            "segments": [],
        }

        # 1. Release integrity, BEFORE any request of any kind.
        try:
            report["release_integrity"] = self.preflight_integrity()
        except CampaignAborted as exc:
            return self._invalid(report, str(exc), phase="pre-flight-integrity",
                                 scientific_calls_made=0)

        # 2. Zero-call preflights: roster and batch capability. Both decide
        #    without sending anything, so a fault here costs zero requests.
        try:
            report["preflight_roster"] = self.preflight_roster()
            report["preflight_batch"] = self.preflight_batch_capability()
        except CampaignAborted as exc:
            return self._invalid(report, str(exc), phase="preflight",
                                 scientific_calls_made=0)

        # 3. Target identity. /v0.1/meta is an identity call, not a scientific one.
        try:
            report["identity_before"] = self.check_identity("pre-campaign")
        except CampaignAborted as exc:
            return self._invalid(report, str(exc), phase="pre-campaign",
                                 scientific_calls_made=0)

        meta_digest = report["identity_before"]["metadata_digest"]
        integrity_digest = report["release_integrity"].get("release_digest")
        report["provenance_stamp"]["release_digest"] = integrity_digest
        report["provenance_stamp"]["target_identity_digest"] = meta_digest

        if self.mode == MODE_STORAGE_CHECKPOINT:
            return self._run_storage_checkpoint(report, meta_digest,
                                                integrity_digest)

        for cell in self.cells:
            for n in self.candidate_n:
                segment = self._run_segment(cell, n, meta_digest, integrity_digest)
                report["segments"].append(segment)

        try:
            report["identity_after"] = self.check_identity("post-campaign")
        except CampaignAborted as exc:
            return self._invalid(report, str(exc), phase="post-campaign")

        before = report["identity_before"]["metadata_digest"]
        after = report["identity_after"]["metadata_digest"]
        if before != after:
            return self._invalid(
                report, "target identity changed during the campaign: before "
                        "%s, after %s" % (before, after), phase="post-campaign")
        report["identity_stable"] = True
        report["finished_utc"] = _utc()
        contract = self.dispatcher.contract()
        report["configuration"]["batch_contract"] = contract
        report["transport_contract"] = contract
        report["in_flight"] = contract["in_flight"]
        return self._finalize(report)

    def _run_segment(self, cell, n, meta_digest, integrity_digest):
        look_index = 0
        tallies, final, slug = self._run_and_tally(
            cell, n, self.plan.looks[0], meta_digest, integrity_digest)
        blocked = tallies.get("_blocked", {}).get("events", 0)
        results = self._evaluate(tallies, look_index)
        verdict = self._segment_verdict(results, blocked)

        while verdict == "CONTINUE" and look_index + 1 < len(self.plan.looks):
            look_index += 1
            tallies, final, slug = self._run_and_tally(
                cell, n, self.plan.looks[look_index], meta_digest,
                integrity_digest)
            blocked = tallies.get("_blocked", {}).get("events", 0)
            results = self._evaluate(tallies, look_index)
            verdict = self._segment_verdict(results, blocked)
        if verdict == "CONTINUE":
            verdict = "UNRESOLVED"

        target_reps = self.plan.looks[look_index]
        missing = sorted(set(range(target_reps)) - final)
        n_independent_failures = sorted(
            name for name, entry in results.items()
            if entry["verdict"] == "FAIL" and name in N_INDEPENDENT_EVENTS)

        return {
            "cell_id": cell["cell_id"], "N": n, "family": cell["family"],
            "population_targets": cell["population_targets"],
            "look_reached": look_index + 1,
            "replications": len(final),
            "blocked_replications": blocked,
            "missing_replications": missing,
            "duplicated_replications": self._duplicates(slug),
            "events": results,
            "verdict": verdict,
            "n_independent_failures": n_independent_failures,
            "evidence_slug": slug,
        }

    # -- storage-only checkpoint ------------------------------------------

    def preflight_roster(self):
        """Zero-call roster validation of every cell's first payload.

        Runs before any transport. The v1.2 checkpoint spent 500 real requests
        discovering a roster fault that is decidable without sending anything.
        """
        problems = []
        checked = 0
        for cell in self.cells:
            for n in self.candidate_n:
                payload, _seed = sim.build_payload(cell, n, 0)
                checked += 1
                found = roster.check_counts_payload(payload)
                if found:
                    problems.append({"cell_id": cell["cell_id"], "N": n,
                                     "problems": found[:3]})
        record = {"performed": True, "target_calls_used": 0,
                  "payloads_checked": checked,
                  "roster": roster.describe(),
                  "violations": problems[:5],
                  "violation_count": len(problems),
                  "ok": not problems}
        if problems:
            raise CampaignAborted(
                "roster preflight rejected %d payload(s) before any target "
                "request: %s" % (len(problems),
                                 problems[0]["problems"][0]))
        return record

    def preflight_batch_capability(self):
        """Zero-call check that the target supplies the assumed batch capability.

        The frozen cost arithmetic assumes batched requests. v1.2 silently fell
        back to single requests while retaining batched projections; that is now
        forbidden. If the capability is absent the campaign stops here, before
        any target call, rather than executing a different cost profile than the
        one that was approved.
        """
        mode = getattr(self.dispatcher, "mode", "unknown")
        record = {
            "performed": True, "target_calls_used": 0,
            "transport_mode": mode,
            "batching_enabled": mode != serial.SerialDispatcher.mode,
            "effective_analysis_calls_in_flight": 1,
            "batch_size": self.dispatcher.batch_size,
            "concurrency": self.dispatcher.concurrency,
            "retries_enabled": False,
            "cost_arithmetic_matches_transport": True,
        }
        if mode != serial.SerialDispatcher.mode:
            raise CampaignAborted(
                "v1.4 requires serialized single-request transport so that "
                "exactly one analysis call is in flight; the configured "
                "dispatcher is %r. Batching cannot be shown to honor the "
                "one-in-flight rule and is not permitted." % mode)
        if self.dispatcher.batch_size != 1 or self.dispatcher.concurrency != 1:
            raise CampaignAborted(
                "serialized transport must use batch_size=1 and concurrency=1; "
                "found %r/%r" % (self.dispatcher.batch_size,
                                 self.dispatcher.concurrency))
        return record

    def _checkpoint_failures(self, slug, target_reps):
        """Fail-closed audit of a checkpoint segment.

        Counts successful analyses by STRUCTURE only -- schema version and the
        presence of the required top-level blocks -- never by reading a
        disposition. A response that is an error envelope, a non-analysis
        object, or a digest mismatch is not a success.
        """
        index_path = self.store._path(slug, ".index.jsonl")
        blocked = non_analysis = digest_failures = successes = records = 0
        error_codes = {}
        if os.path.isfile(index_path):
            with open(index_path, "r") as handle:
                for line in handle:
                    entry = json.loads(line)
                    records += 1
                    if entry["blocked"]:
                        blocked += 1
                        code = (entry.get("error") or {}).get("code")
                        error_codes[code] = error_codes.get(code, 0) + 1
                        continue
                    stored = self.store.read_record(slug, entry["replication"])
                    if not stored["sha256_matches"]:
                        digest_failures += 1
                        continue
                    try:
                        body = json.loads(stored["raw"].decode("utf-8"))
                    except ValueError:
                        non_analysis += 1
                        continue
                    if not _is_analysis_shaped(body):
                        non_analysis += 1
                        continue
                    successes += 1

        missing = max(0, target_reps - records)
        reasons = []
        capacity = error_codes.get("CAPACITY", 0)
        if capacity:
            reasons.append(
                "%d CAPACITY rejection(s) with exactly one analysis call in "
                "flight: this is a TARGET_DEPLOYMENT_CONTRACT_PROBLEM, not a "
                "harness concurrency fault, and is deliberately NOT masked by "
                "retries" % capacity)
        if blocked:
            reasons.append("%d blocked request(s): %s" % (blocked, error_codes))
        if non_analysis:
            reasons.append("%d non-analysis or schema-rejected response(s)"
                           % non_analysis)
        if digest_failures:
            reasons.append("%d digest verification failure(s)" % digest_failures)
        if missing:
            reasons.append("%d missing response(s)" % missing)
        if successes < target_reps:
            reasons.append("only %d successful analyses of %d requested"
                           % (successes, target_reps))
        return {
            "requested": target_reps, "records": records,
            "successful_analyses": successes, "blocked": blocked,
            "non_analysis_responses": non_analysis,
            "digest_failures": digest_failures, "missing_responses": missing,
            "error_codes": error_codes, "failure_reasons": reasons,
            "passed": not reasons,
        }

    def _run_storage_checkpoint(self, report, meta_digest, integrity_digest):
        """Run exactly the FIRST defined segment, storing evidence only.

        No scientific disposition is computed, recorded or reported. The point
        is to measure retention and compression against the real target before
        committing to the full campaign, without producing -- or being able to
        produce -- any early read on engine behaviour.
        """
        cell = self.cells[0]
        n = self.candidate_n[0]
        target_reps = self.plan.looks[0]
        _tallies, final, slug = self._run_and_tally(
            cell, n, target_reps, meta_digest, integrity_digest)

        try:
            report["identity_after"] = self.check_identity("post-checkpoint")
        except CampaignAborted as exc:
            return self._invalid(report, str(exc), phase="post-checkpoint")
        if (report["identity_after"]["metadata_digest"]
                != report["identity_before"]["metadata_digest"]):
            return self._invalid(report, "target identity changed during the "
                                         "checkpoint", phase="post-checkpoint")

        raw_request = raw_response = 0
        digests = 0
        index_path = self.store._path(slug, ".index.jsonl")
        with open(index_path, "r") as handle:
            for line in handle:
                entry = json.loads(line)
                raw_request += entry["request_raw_length"]
                raw_response += entry["response_raw_length"]
                digests += 1

        storage = self.storage_summary()
        ratio = (float(raw_response) / storage["compressed_response_bytes"]
                 if storage["compressed_response_bytes"] else None)

        # Fail closed. A checkpoint in which nothing succeeded must be
        # impossible to report as completion -- the v1.2 defect.
        audit = self._checkpoint_failures(slug, target_reps)
        report["checkpoint_audit"] = audit

        # Report-time transport statistics, reconciled against the audit.
        contract = self.dispatcher.contract()
        report["configuration"]["batch_contract"] = contract
        report["transport_contract"] = contract
        reconciliation = self.dispatcher.reconciles_with(audit)
        report["transport_reconciliation"] = reconciliation
        report["in_flight"] = contract["in_flight"]
        if not reconciliation["reconciled"]:
            audit["failure_reasons"].append(
                "transport statistics do not reconcile with the attempt "
                "audit: %s" % "; ".join(reconciliation["problems"][:2]))
            audit["passed"] = False
        if not contract["in_flight"]["honors_one_in_flight"]:
            audit["failure_reasons"].append(
                "observed %d analysis calls in flight; the frozen limit is 1"
                % contract["in_flight"]["max_observed_in_flight"])
            audit["passed"] = False
        report["campaign_valid"] = audit["passed"]
        report["status"] = ("STORAGE_CHECKPOINT_COMPLETE" if audit["passed"]
                            else "STORAGE_CHECKPOINT_FAILED")
        report["checkpoint_disposition"] = (
            "CHECKPOINT_PASSED" if audit["passed"] else "CHECKPOINT_FAILED")
        if not audit["passed"]:
            report["checkpoint_failure_reasons"] = audit["failure_reasons"]
            report["usability"] = (
                "This checkpoint FAILED. Its storage and compression "
                "measurements are VOID and must not be used for any "
                "projection. %s" % "; ".join(audit["failure_reasons"]))
        report["finished_utc"] = _utc()
        report["checkpoint"] = {
            "segment": {"cell_id": cell["cell_id"], "N": n,
                        "replications_target": target_reps,
                        "replications_stored": len(final),
                        "missing": sorted(set(range(target_reps)) - final),
                        "duplicated": self._duplicates(slug),
                        "evidence_slug": slug},
            "stopped_after_first_segment": True,
            "segments_remaining": self.segment_multiplicity - 1,
            "per_response_digests_recorded": digests,
            "measured_raw_request_bytes": raw_request,
            "measured_raw_response_bytes": raw_response,
            "measured_compression_ratio_responses": ratio,
            "projected_full_campaign_compressed_bytes": (
                int(storage["compressed_total_bytes"]
                    * self.segment_multiplicity) if storage[
                        "compressed_total_bytes"] else None),
        }
        report["storage"] = storage
        report["dispositions_exposed"] = False
        report["engine_result_state"] = "NOT_ASSESSED"
        report["scientific_dispositions_note"] = (
            "This is a storage-only checkpoint. No disposition, event tally or "
            "verdict was computed for any replication; index records carry "
            "decision_record=null with dispositions_withheld=true. Response "
            "bodies are retained in full as decision D1 requires, so the "
            "campaign can later be completed from the same evidence.")
        report["blinding_rule"] = BLINDING_RULE
        report["blinding_attestation"] = {
            "archives_written": True,
            "archives_inspected_by_harness": False,
            "dispositions_computed": False,
            "continuation_decision_recorded": False,
            "honest_limitation": (
                "Withholding dispositions does NOT make an early read "
                "impossible. The retained archives contain complete engine "
                "responses and could be decoded and inspected by hand at any "
                "time. What prevents an early read is the frozen blinding "
                "rule above, which is a procedural commitment binding the "
                "operator, any coding agent and any reviewer -- not a "
                "technical impossibility."),
        }
        report["authorization_note"] = (
            "A storage checkpoint authorizes nothing. It does not qualify the "
            "engine, does not seal the apparatus, does not authorize study "
            "execution and does not authorize source review.")
        return report

    # -- finalization ------------------------------------------------------

    def _invalid(self, report, reason, phase, scientific_calls_made=None):
        report["finished_utc"] = _utc()
        report["campaign_valid"] = False
        report["status"] = "ABORTED_INVALID"
        report["abort_phase"] = phase
        report["abort_reason"] = reason
        report["engine_result_state"] = "NOT_ASSESSED"
        if scientific_calls_made is not None:
            report["scientific_calls_made"] = scientific_calls_made
        report["usability"] = (
            "The results of this campaign are NOT usable. Evidence already "
            "written is retained for audit but must not be used as engine "
            "evidence.")
        return report

    def _finalize(self, report):
        segments = report["segments"]
        counts = {}
        for segment in segments:
            counts[segment["verdict"]] = counts.get(segment["verdict"], 0) + 1
        report["verdict_counts"] = counts
        report["campaign_valid"] = True

        # --- per-N topology ---------------------------------------------
        per_n = {}
        for n in self.candidate_n:
            at_n = [s for s in segments if s["N"] == n]
            if not at_n:
                continue
            failing = [s for s in at_n if s["verdict"] == "FAIL"]
            unresolved = [s for s in at_n if s["verdict"] == "UNRESOLVED"]
            blocked = [s for s in at_n if s["verdict"] == "BLOCKED"]
            incomplete = [s for s in at_n
                          if s["missing_replications"] or s["duplicated_replications"]]
            if incomplete:
                state = "EVIDENCE_INCOMPLETE_AT_N"
            elif failing:
                state = "ENGINE_REJECTED_AT_N"
            elif unresolved or blocked:
                state = "ENGINE_NOT_YET_QUALIFIABLE_AT_N"
            else:
                state = "ENGINE_CANDIDATE_QUALIFIED_AT_N"
            per_n[n] = {
                "N": n, "segments": len(at_n), "state": state,
                "failing": [s["cell_id"] for s in failing],
                "unresolved": [s["cell_id"] for s in unresolved],
                "blocked": [s["cell_id"] for s in blocked],
                "incomplete": [s["cell_id"] for s in incomplete],
            }
        report["per_N"] = [per_n[n] for n in sorted(per_n)]

        qualified = [n for n, entry in per_n.items()
                     if entry["state"] == "ENGINE_CANDIDATE_QUALIFIED_AT_N"]
        rejected = [n for n, entry in per_n.items()
                    if entry["state"] == "ENGINE_REJECTED_AT_N"]
        incomplete_n = [n for n, entry in per_n.items()
                        if entry["state"] == "EVIDENCE_INCOMPLETE_AT_N"]

        # --- N-independent structural defects ---------------------------
        structural = sorted({name for s in segments
                             for name in s["n_independent_failures"]})
        structural_segments = [
            {"cell_id": s["cell_id"], "N": s["N"],
             "failures": s["n_independent_failures"]}
            for s in segments if s["n_independent_failures"]]

        if incomplete_n:
            state = "ENGINE_NOT_YET_QUALIFIABLE"
            reason = ("evidence is incomplete at N=%s; missing or duplicated "
                      "replications block any conclusion"
                      % sorted(incomplete_n))
        elif structural:
            state = "ENGINE_REJECTED"
            reason = ("N-independent structural defect(s) observed: %s. These "
                      "are logic errors rather than resolution limits, so they "
                      "reject the engine at every replicate count."
                      % ", ".join(structural))
        elif qualified:
            state = "ENGINE_CANDIDATE_QUALIFIED"
            reason = ("every frozen requirement passed at N=%s under the "
                      "approved rule. Failure at a smaller N is a resolution "
                      "limit at that N, not a global engine defect."
                      % sorted(qualified))
        elif rejected and len(rejected) == len(per_n):
            state = "ENGINE_REJECTED"
            reason = "rejected at every candidate N"
        else:
            state = "ENGINE_NOT_YET_QUALIFIABLE"
            reason = ("no candidate N cleared every requirement, and no "
                      "N-independent defect was observed")

        report["engine_result_state"] = state
        report["engine_result_reason"] = reason
        report["qualified_N"] = sorted(qualified)
        report["rejected_N"] = sorted(rejected)
        report["n_independent_failures"] = structural
        report["n_independent_failure_segments"] = structural_segments
        report["status"] = "COMPLETE"

        report["per_N_topology_note"] = (
            "Result states are reported per candidate N. A failure confined to "
            "small N is a statement about that N, not about the engine: "
            "selecting N is a study decision under preregistration 12.4. Only "
            "an N-independent structural defect, or rejection at every "
            "candidate N, rejects the engine globally.")
        report["failing_segments"] = [
            {"cell_id": s["cell_id"], "N": s["N"],
             "events": {k: v for k, v in s["events"].items()
                        if v["verdict"] == "FAIL"}}
            for s in segments if s["verdict"] == "FAIL"]
        report["unresolved_segments"] = [
            {"cell_id": s["cell_id"], "N": s["N"]}
            for s in segments if s["verdict"] == "UNRESOLVED"]
        report["blocked_segments"] = [
            {"cell_id": s["cell_id"], "N": s["N"],
             "blocked_replications": s["blocked_replications"]}
            for s in segments if s["verdict"] == "BLOCKED"]
        report["authorization_note"] = (
            "This campaign result authorizes nothing further on its own. "
            "ENGINE_CANDIDATE_QUALIFIED, if reached, does not seal the "
            "apparatus, does not authorize ordinal-profile study execution, and does not "
            "authorize source review. Source review remains a separately "
            "authorized later phase bound to this exact target identity.")
        report["storage"] = self.storage_summary()
        return report

    def storage_summary(self):
        total_requests = total_responses = entries = 0
        if not os.path.isdir(self.store.root):
            return {"indexed_replications": 0, "compressed_request_bytes": 0,
                    "compressed_response_bytes": 0, "compressed_total_bytes": 0}
        for name in sorted(os.listdir(self.store.root)):
            path = os.path.join(self.store.root, name)
            if name.endswith(".requests.gz"):
                total_requests += os.path.getsize(path)
            elif name.endswith(".responses.gz"):
                total_responses += os.path.getsize(path)
            elif name.endswith(".index.jsonl"):
                with open(path, "r") as handle:
                    entries += sum(1 for line in handle if line.strip())
        return {
            "indexed_replications": entries,
            "compressed_request_bytes": total_requests,
            "compressed_response_bytes": total_responses,
            "compressed_total_bytes": total_requests + total_responses,
            "retention_policy": "decision D1: every request and response body "
                                "retained verbatim, losslessly compressed, with "
                                "per-response SHA-256 and a byte-offset index",
        }


def write_report(report, path):
    with open(path, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path
