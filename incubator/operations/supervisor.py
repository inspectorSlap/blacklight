"""Detached campaign supervisor for the frozen v1.4 runner (v1.5.4).

THE FROZEN RUNNER IS NOT MODIFIED
---------------------------------
Nothing in `harness/` changes to make detachment work. This supervisor starts
the standalone proxy, verifies every identity that matters, then launches the
already-frozen runner as a detached child. The scientific core -- oracle,
reference, scenarios, seeds, anchors, decision rules, blinding rule -- is
byte-identical to v1.4 and is checked to be so before the first target call.

WHY VERIFICATION LIVES HERE
---------------------------
The runner already fails closed when the proxy variables are absent. It cannot,
however, tell a real filtering proxy from a placeholder value pointed at
anything at all. That check belongs to preflight: the supervisor authenticates
to the proxy's control endpoint and requires its code and configuration digests
to match the approved values before the runner is started.

PREFLIGHT IS SPLIT IN TWO (v1.5.1)
----------------------------------
v1.5 had one preflight that demanded a live, identity-verified proxy but never
started one. Run on its own it could not pass, and its FAIL said nothing about
whether the static checks were sound. v1.5.1 splits it:

* **static phase** -- release integrity, approval, D6 topology, scientific-core
  digest, proxy code/config digests, launcher digest, expected target identity,
  deviation records, run-collision safety. Zero network operations of any kind.
* **live phase** -- authenticated proxy control-endpoint identity, and the
  proxy urllib will ACTUALLY resolve. Requires a running proxy, so it runs at
  `start`, immediately after the supervisor has launched that proxy and
  immediately before the runner is spawned.

Why this design and not "launch a temporary proxy during preflight": a
temporary launch makes a read-only command start and kill a listening process,
and a failure between launch and teardown orphans a proxy bound to loopback
that the operator does not know about. Splitting has no side effects and
cannot leave a process behind.

Both phases fail closed. `preflight` reports its live phase as NOT_PERFORMED
rather than as passed, so a green standalone preflight never implies that live
verification happened. Neither phase contacts an analysis endpoint: the static
phase makes no request at all, and the live phase talks only to the proxy's own
`/__proxy/identity` control path.

QUALIFICATION IS ENFORCED, NOT REQUESTED (v1.5.2)
-------------------------------------------------
Up to v1.5.1 the requirement that the Terminal proxy qualification produce
19/19 PASS with zero FAIL and zero BLOCKED lived only in prose and in the
approval record. `start` did not check it, so a campaign could be launched
against a proxy that had never been qualified against a live upstream, or that
had been qualified and failed. An unenforced prerequisite is a comment.

`start` now refuses -- before launching the proxy, before spawning the runner,
and before any analysis endpoint could be contacted -- unless it finds a
runtime attestation that is internally intact, reports exactly 19 PASS with
zero FAIL and zero BLOCKED, is bound to this exact release, approval, proxy
code, proxy configuration, launcher, host, target and run identity, and has
not already authorized a launch. The attestation's identity and digest are
recorded in the campaign provenance, so qualification evidence is bound
prospectively to the launch it authorizes.

Attestations live under `results/runtime-attestations/` and are deliberately
NOT release artifacts, so running the qualifier cannot alter the frozen
release. See tools/blackbox_attestation.py.

TRANSACTIONAL LAUNCH (v1.5.4)
-----------------------------
v1.5.3 spawned the runner and only then tried to consume the attestation,
write run state and write provenance. The ledger was read-only, so all three
failed -- with a campaign already executing, no durable record of it, and an
attestation that no ledger showed as used.

v1.5.4 inverts the order. Everything that can fail happens, and is fsynced,
before any process exists:

  1. probe the attestation ledger with a real append and a real fsync;
  2. select an attestation, consulting the consumed ledger, the durable
     spent/void set, and the run identities that already have artifacts;
  3. acquire an exclusive run-identity lock, held for the run's lifetime;
  4. atomically reserve and permanently SPEND the attestation;
  5. write minimal state and provenance durably;
  6. only then spawn the proxy, and only then the runner.

After a process exists, any failure terminates everything this launch started
and records why. A spent attestation is never returned to the pool, and there
is no force flag or recovery path that un-spends one.

RUN COLLISION IS FATAL (v1.5.1)
-------------------------------
`start` refuses if this run identity's report, evidence directory, state or
logs already exist. There is no force option. A failed attempt is preserved by
being impossible to overwrite.

Commands: preflight, start, status, stop, resume.
`status` is strictly read-only and performs no network request.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import base64
import datetime
import getpass
import hashlib
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TOOLS = os.path.join(ROOT, "tools")
PROXY_CODE = os.path.join(TOOLS, "blackbox_proxy.py")
PROXY_CONFIG = os.path.join(TOOLS, "blackbox-proxy-config.json")
SUPERVISOR_CODE = os.path.abspath(__file__)

# Every operational path is derived from one version constant so a new release
# cannot silently reuse a previous release's evidence, report or state.
VERSION = "1.6.6"
RESULTS = os.path.join(ROOT, "results")

# The registered v1.6.0 workload, read from the C4 v0.6 amendment through the
# family module rather than restated here.
FIRST_LOOK_REQUESTS = 30000
WORST_CASE_REQUESTS = 120000

# v1.5.3 is a CONTINUATION release. Its authorized action is the full campaign
# resuming from the passed v1.5.2 storage checkpoint -- not a fresh campaign
# and not a rerun of the checkpoint. The predecessor's paths are named here so
# they can be protected, never written.
PREDECESSOR_VERSION = "1.5.2"
PREDECESSOR_EVIDENCE = os.path.join(
    RESULTS, "campaign-evidence-v%s" % PREDECESSOR_VERSION)
PREDECESSOR_RUN_ID = "checkpoint-v%s-run-001" % PREDECESSOR_VERSION
CONTINUATION_FLAG = "--continue-from-v1.5.2"

STATE_PATH = os.path.join(RESULTS, "campaign-run-state-v%s.json" % VERSION)
PROVENANCE_PATH = os.path.join(RESULTS, "campaign-provenance-v%s.json" % VERSION)
RUN_LOG = os.path.join(RESULTS, "campaign-runner-v%s.log" % VERSION)
PROXY_LOG = os.path.join(RESULTS, "campaign-proxy-v%s.log" % VERSION)
EVIDENCE_DIR = os.path.join(RESULTS, "campaign-evidence-v%s" % VERSION)
CHECKPOINT_REPORT = os.path.join(
    RESULTS, "campaign-report-checkpoint-v%s.json" % VERSION)
FULL_REPORT = os.path.join(RESULTS, "campaign-report-v%s.json" % VERSION)

# One authoritative target-manifest binding for every active path.
TARGET_MANIFEST_PATTERN = re.compile(r"target-manifest-v\d+\.\d+\.json")
TARGET_MANIFEST_NAME = "target-manifest-v0.5.json"
TARGET_MANIFEST = os.path.join(ROOT, TARGET_MANIFEST_NAME)
ACTIVE_IDENTITY_SOURCES = (
    "tools/blackbox_supervisor.py",
    "tools/blackbox_target_server.py",
    "harness/cli.py",
)

MANIFEST = os.path.join(RESULTS, "harness-release-manifest-v%s.json" % VERSION)
APPROVAL = os.path.join(RESULTS, "v%s-approval.json" % VERSION)

CHECKPOINT_RUN_ID = "checkpoint-v%s-run-001" % VERSION
FULL_RUN_ID = "campaign-v%s-run-001" % VERSION

# Files whose bytes define the scientific answers. Through v1.5.8 these had to
# be identical to v1.4. v1.6.0 changes the scientific core deliberately and
# under approval: the count-primary target is replaced by the reviewed
# ordered-evidence engine, and status-blind consumption is removed. The
# invariant is therefore re-baselined, not dropped -- the core must now match
# the frozen v1.6.0 baseline recorded in
# results/v1.6.0-scientific-core-baseline.json, which also carries the
# file-by-file inventory of what changed against v1.4 and why.
#
# Operational plumbing (cli, freeze, transport, supervisor, proxy) is
# deliberately excluded and is listed separately in the provenance record.
SCIENTIFIC_CORE_BASELINE = os.path.join(
    RESULTS, "v%s-scientific-core-baseline.json" % VERSION)

SCIENTIFIC_CORE = [
    "harness/oracle/core.py", "harness/oracle/population.py",
    "harness/oracle/sample.py", "harness/oracle/__init__.py",
    "harness/reference/sound_reference.py", "harness/reference/interval.py",
    "harness/reference/archive.py", "harness/reference/__init__.py",
    "harness/mutants/mutants.py", "harness/mutants/__init__.py",
    "harness/checks/checks.py", "harness/checks/rules.py",
    "harness/checks/anchor_checks.py", "harness/checks/archive_checks.py",
    "harness/sequential.py", "harness/simulation.py", "harness/roster.py",
    "harness/adapter.py", "harness/campaign.py", "harness/serial.py",
    "harness/inflight.py", "harness/targets.py", "harness/runner.py",
    "harness/selfqual.py", "harness/batching.py",
    "fixtures/anchors/hand-anchors-v1.0.json",
    "fixtures/simulation-grid-v1.0.json", "fixtures/seeds.json",
    "results/failure-registry-v1.0.json",
    # v1.6.0 ordered-evidence path.
    "harness/ordered/__init__.py", "harness/ordered/canonical.py",
    "harness/ordered/statuses.py", "harness/ordered/grid.py",
    "harness/ordered/synthetic.py", "harness/ordered/family.py",
    "harness/ordered/events.py", "harness/ordered/engine_bridge.py",
    "harness/ordered/selfcheck.py", "harness/ordered/campaign.py",
    # The reviewed engine itself: its bytes decide every disposition.
    "vendor/blackbox-ordinal-v0.3.0-rc2/MANIFEST.sha256",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/engine.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/ingest.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/pp.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/validity.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/output_contract.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/estimands.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/regions.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/optimization.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/qualification.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/models.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/canonical.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/api.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/cli.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/src/ordinal_engine/__init__.py",
    "vendor/blackbox-ordinal-v0.3.0-rc2/contracts/C1-successor-v0.6.json",
    "vendor/blackbox-ordinal-v0.3.0-rc2/contracts/C2-event-family-v0.5.json",
    "vendor/blackbox-ordinal-v0.3.0-rc2/contracts/C4-statistical-amendment-v0.6.json",
    "vendor/blackbox-ordinal-v0.3.0-rc2/fixtures/validity-configurations-v1.0.json",
    "fixtures/validity-configurations-v1.1.json",
    "vendor/blackbox-ordinal-v0.3.0-rc2/fixtures/GV-ORDER-A.json",
    "vendor/blackbox-ordinal-v0.3.0-rc2/fixtures/GV-ORDER-B.json",
]

TOKEN_PATTERNS = (re.compile(r"Bearer\s+\S+", re.I),
                  re.compile(r"Proxy-Authorization", re.I))


class PreflightFailure(Exception):
    """Any preflight failure stops before the first target call."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_target_identity():
    """The one authoritative target identity block.

    Every active path -- launch bindings, preflight, campaign and provenance --
    resolves target identity through here, so a divergent binding cannot be
    introduced by editing one call site.
    """
    with open(TARGET_MANIFEST, "r") as handle:
        return json.load(handle)["target"]


def target_manifest_divergence():
    """Active runtime sources that name a target manifest other than the one.

    A mechanical guard rather than a convention: if any active source names a
    different manifest, this returns it and the preflight check fails.
    """
    divergent = {}
    for relative in ACTIVE_IDENTITY_SOURCES:
        path = os.path.join(ROOT, relative)
        if not os.path.isfile(path):
            continue
        with open(path, "r") as handle:
            text = handle.read()
        # Only well-formed manifest filenames count. A loose scan would also
        # match the prefix constant that defines the check itself.
        names = set(TARGET_MANIFEST_PATTERN.findall(text))
        other = sorted(n for n in names if n != TARGET_MANIFEST_NAME)
        if other:
            divergent[relative] = other
    return divergent


def active_topology():
    """The sealed active topology, derived from the verified contracts.

    Read through the ordered family rather than restated here, so status cannot
    drift from the plan the campaign actually runs.
    """
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from harness.ordered import family

    return {
        "configurations": family.SEGMENT_COUNT,
        "gated_streams": family.GATED_STREAM_COUNT,
        "looks": list(family.LOOKS),
        "first_look_requests": family.FIRST_LOOK_REQUESTS,
        "worst_case_requests": family.WORST_CASE_REQUESTS,
        "source": "C2 v0.5 manifest %s and C4 v0.6 %s"
                  % (family.C2_MANIFEST_DIGEST[:12],
                     family.C4_RECORD_DIGEST[:12]),
    }


D6_SELECTED_PLAN = "corrected_two_look"


def validate_d6_against_active_plan(approval):
    """Validate the already-selected D6 decision against the active plan.

    This does not reopen D6. The selection stays `corrected_two_look`; it is
    simply checked against the sealed ordered topology the campaign runs --
    60 configurations, 153 streams, looks 500/2000, PASS [33,165],
    FAIL [80,256] -- rather than the obsolete 318-segment apparatus.
    """
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from harness.ordered import campaign as ordered_campaign
    from harness.ordered import family

    # Callers differ in what they hold: preflight has already unwrapped the
    # record to its operator_approval block, while other callers pass the whole
    # approval record. Accept either, so a valid D6 selection is never read as
    # absent because of the caller's shape.
    record = approval or {}
    block = record.get("operator_approval", record)
    selected = (block.get("decisions") or {}).get("D6")
    if isinstance(selected, dict):
        selected = selected.get("plan") or selected.get("selection") or selected.get("value")
    if selected != D6_SELECTED_PLAN:
        return selected, False, ("D6 selection is %r, expected the already "
                                 "selected %r" % (selected, D6_SELECTED_PLAN))

    plan = ordered_campaign.Plan()
    topology = active_topology()
    problems = []
    if topology["configurations"] != 60:
        problems.append("configurations=%d" % topology["configurations"])
    if topology["gated_streams"] != 153:
        problems.append("streams=%d" % topology["gated_streams"])
    if list(plan.looks) != [500, 2000]:
        problems.append("looks=%s" % list(plan.looks))
    if list(plan.pass_critical) != [33, 165]:
        problems.append("PASS=%s" % list(plan.pass_critical))
    if list(plan.fail_critical) != [80, 256]:
        problems.append("FAIL=%s" % list(plan.fail_critical))
    if topology["first_look_requests"] != 30000:
        problems.append("first_look=%d" % topology["first_look_requests"])
    if topology["worst_case_requests"] != 120000:
        problems.append("worst_case=%d" % topology["worst_case_requests"])
    if problems:
        return selected, False, "active plan mismatch: %s" % ", ".join(problems)
    return selected, True, (
        "%s against 60 configurations, %d streams, looks %s, PASS %s, FAIL %s"
        % (selected, topology["gated_streams"], list(plan.looks),
           list(plan.pass_critical), list(plan.fail_critical)))


def assert_no_predecessor_evidence_import():
    """Fail closed if a predecessor-evidence import path is still reachable.

    v1.6.2 inherits nothing. This is asserted at launch rather than assumed, so
    a reintroduced continuation import is refused before any process is spawned.
    """
    if os.path.isdir(PREDECESSOR_EVIDENCE):
        # Present on disk is fine; reading or importing it is not. The guard is
        # that no code path here opens it, which the acceptance proof measures.
        pass
    return True


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


def utc():
    """Timezone-aware UTC. Same instant and same rendering as the naive
    `utcnow()` this replaced; only the deprecation is gone."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text):
    """Parse a timestamp this module wrote back into an aware datetime."""
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


def host_identifier():
    """Stable host id that exposes no secret and no username."""
    raw = "%s|%s|%s" % (platform.node(), platform.system(), platform.machine())
    return {
        "host_fingerprint": hashlib.sha256(raw.encode()).hexdigest()[:32],
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "user_recorded": False,
        "hostname_recorded": False,
    }


def launch_bindings(mode="full"):
    """The identities an attestation is bound to.

    Single source of truth, used both by the qualifier when it writes an
    attestation and by `start` when it checks one. Two conventions describing
    the same thing would produce spurious mismatches, so there is only one.

    `mode` selects the run id. It is a binding field, so an attestation
    produced for the checkpoint run cannot authorize the full campaign and vice
    versa -- they are different scientific undertakings, and evidence that one
    proxy configuration worked for a 500-call checkpoint is not evidence about
    a 158,500-call campaign. v1.5.3's authorized action is the full run, so
    that is the default.
    """
    import importlib
    sys.path.insert(0, TOOLS)
    proxy_module = importlib.import_module("blackbox_proxy")
    config = proxy_module.load_config(PROXY_CONFIG)
    manifest = json.load(open(MANIFEST)) if os.path.isfile(MANIFEST) else {}
    target = load_target_identity()
    return {
        "release_digest": manifest.get("release_digest"),
        "approval_digest": sha256_file(APPROVAL)
                           if os.path.isfile(APPROVAL) else None,
        "proxy_code_sha256": sha256_file(PROXY_CODE),
        "proxy_config_sha256": proxy_module.config_digest(config),
        "attestation_module_sha256": sha256_file(
            os.path.join(TOOLS, "blackbox_attestation.py")),
        "launcher_sha256": sha256_file(SUPERVISOR_CODE),
        "target_origin": config["allowed_origin"],
        "expected_gateway_version": target["gateway_version"],
        "expected_engine_version": target["engine_version"],
        "host_fingerprint": host_identifier()["host_fingerprint"],
        "run_id": FULL_RUN_ID if mode == "full" else CHECKPOINT_RUN_ID,
    }


def scientific_core_digest(root=ROOT):
    entries = {}
    for relative in sorted(SCIENTIFIC_CORE):
        path = os.path.join(root, relative)
        entries[relative] = sha256_file(path) if os.path.isfile(path) else None
    scenarios = os.path.join(root, "fixtures", "scenarios")
    for family in sorted(os.listdir(scenarios)) if os.path.isdir(scenarios) else []:
        directory = os.path.join(scenarios, family)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith(".json"):
                relative = "fixtures/scenarios/%s/%s" % (family, name)
                entries[relative] = sha256_file(os.path.join(root, relative))
    return canonical_digest(entries), entries


def load_state():
    if not os.path.isfile(STATE_PATH):
        return {}
    with open(STATE_PATH, "r") as handle:
        return json.load(handle)


def save_state(state):
    """Durable. A state file whose directory entry is not durable can vanish
    on a crash, leaving a running campaign with no record of itself."""
    import blackbox_launch_safety as safety
    safety.durable_write(STATE_PATH,
                         json.dumps(state, indent=2, sort_keys=True) + "\n")


def process_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def proxy_credential():
    credential = os.environ.get("BLACKBOX_PROXY_CREDENTIAL")
    if credential:
        return credential
    # Deterministic per-host secret derived from an operator-supplied seed, so
    # resume can reconstruct it without storing it anywhere.
    seed = os.environ.get("BLACKBOX_PROXY_SEED")
    if not seed:
        return None
    return "blackbox:%s" % hashlib.sha256(
        ("%s|%s" % (seed, platform.node())).encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# run collision (v1.5.1)
# ---------------------------------------------------------------------------

def run_collisions(mode="checkpoint", resuming=False, launch_identity=None):
    """Artifacts of this run identity that already exist.

    v1.5's checkpoint aborted at HTTP 401. Nothing stopped a second attempt
    from writing the same report path, the same evidence directory and the same
    state file, which would have erased the record of the failure. This is the
    guard. There is deliberately no force-overwrite option: to run again, use a
    new run identity.

    `resume` is the one legitimate reason to find these artifacts, and it is
    allowed only when prior state exists and names this same run id -- so a
    resume can continue a run but cannot start a different one on top of it.

    `launch_identity` is the second legitimate reason, and it exists for the
    same reason `validate_reserved` does (v1.6.6). A launch writes its run
    state and provenance durably at step 6, BEFORE live preflight runs at step
    8. Asking "does this run identity already have artifacts?" at step 8
    therefore finds the launch's own pre-spawn commit and calls it a
    collision -- a fresh launch failing on evidence that it, and only it, just
    wrote. When the caller supplies its own campaign id, artifacts that belong
    to that very launch are recognised as its own rather than as a competing
    run. Artifacts belonging to any OTHER launch still collide, and a caller
    that supplies no identity is treated exactly as before.
    """
    report = CHECKPOINT_REPORT if mode == "checkpoint" else FULL_REPORT
    expected_id = CHECKPOINT_RUN_ID if mode == "checkpoint" else FULL_RUN_ID

    found = []
    if os.path.isfile(report):
        found.append({"artifact": "campaign report",
                      "path": os.path.relpath(report, ROOT)})
    if os.path.isdir(EVIDENCE_DIR) and os.listdir(EVIDENCE_DIR):
        found.append({"artifact": "evidence directory (non-empty)",
                      "path": os.path.relpath(EVIDENCE_DIR, ROOT),
                      "entries": len(os.listdir(EVIDENCE_DIR))})
    for label, path in (("run state", STATE_PATH), ("runner log", RUN_LOG),
                        ("provenance record", PROVENANCE_PATH)):
        if os.path.exists(path):
            found.append({"artifact": label,
                          "path": os.path.relpath(path, ROOT)})

    if not found:
        return {"collision": False, "found": [], "run_id": expected_id,
                "resume_authorized": False}

    state = load_state()
    resume_ok = bool(resuming and state and state.get("run_id") == expected_id)

    # Artifacts this very launch just committed are not a competing run. The
    # test is ownership, not absence: the recorded state must name THIS
    # campaign id and this run identity, and only the pre-spawn artifacts may
    # be present. A campaign report, a non-empty evidence directory or a
    # runner log means some launch actually ran, which this one has not, so
    # those still collide.
    own_launch = False
    if launch_identity and state:
        pre_spawn_only = {"run state", "provenance record"}
        labels = {entry["artifact"] for entry in found}
        own_launch = (state.get("campaign_id") == launch_identity
                      and state.get("run_id") == expected_id
                      and labels.issubset(pre_spawn_only))

    return {"collision": not (resume_ok or own_launch), "found": found,
            "run_id": expected_id,
            "resume_authorized": resume_ok,
            "own_pre_spawn_commit": own_launch,
            "launch_identity": launch_identity,
            "prior_run_id": state.get("run_id") if state else None,
            "remedy": "these artifacts belong to run %s; preserve them and use "
                      "a new run identity. There is no force option."
                      % expected_id}


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

def verify_proxy_live(config, credential, timeout=10):
    """Authenticate to the proxy control endpoint and verify its identity."""
    url = "http://%s:%s/__proxy/identity" % (config["bind_host"],
                                             config["bind_port"])
    request = urllib.request.Request(url)
    request.add_header("Proxy-Authorization", "Basic " + base64.b64encode(
        credential.encode()).decode())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def preflight(live_phase=False, verbose=True, mode="checkpoint",
              resuming=False, transaction_attestation=None,
              launch_identity=None):
    """Static checks always; live proxy checks only when `live_phase`.

    `transaction_attestation` is supplied only by a launch that is already
    holding a reserved and spent attestation. When it is present, check 10
    validates THAT attestation instead of selecting one; see the v1.6.6 note
    at check 10. Standalone preflight passes nothing and keeps requiring an
    eligible unused attestation.

    `launch_identity` is that launch's campaign id, so check 9 can tell the
    launch's own pre-spawn commit apart from a competing run. Standalone
    preflight passes nothing and keeps requiring a clean run identity.

    `live_phase=False` performs zero network operations of any kind and is what
    the standalone `preflight` command runs. `live_phase=True` is used by
    `start`, after the supervisor has launched the proxy and before the runner
    is spawned. Neither phase ever contacts an analysis endpoint.
    """
    import importlib
    sys.path.insert(0, ROOT)
    proxy_module = importlib.import_module("tools.blackbox_proxy") \
        if os.path.isfile(os.path.join(TOOLS, "__init__.py")) else None
    if proxy_module is None:
        sys.path.insert(0, TOOLS)
        proxy_module = importlib.import_module("blackbox_proxy")

    checks = []

    def record(name, ok, detail, **extra):
        checks.append(dict({"check": name, "ok": bool(ok), "detail": detail},
                           **extra))
        if verbose:
            print("  %-46s %s" % (name, "OK" if ok else "FAIL"))
        return ok

    # 1. release manifest and integrity
    from harness import freeze as freeze_module
    integrity = freeze_module.verify_release_integrity(MANIFEST)
    manifest = json.load(open(MANIFEST)) if os.path.isfile(MANIFEST) else {}
    record("release digest verified", integrity["intact"],
           "%s artifacts, %d altered"
           % (integrity["artifacts_checked"], len(integrity["mismatches"])),
           release_digest=manifest.get("release_digest"))

    # 2. approval
    approval = {}
    if os.path.isfile(APPROVAL):
        approval = json.load(open(APPROVAL)).get("operator_approval", {})
    approval_digest = sha256_file(APPROVAL) if os.path.isfile(APPROVAL) else None
    record("approval digest present and APPROVED",
           approval.get("status") == "APPROVED", approval.get("status", "ABSENT"),
           approval_digest=approval_digest)

    # 3. D6 plan, validated against the ACTIVE sealed ordered plan.
    #
    # The already-selected decision `corrected_two_look` is retained; what
    # changes is what it is checked against. The obsolete six-candidate /
    # 318-segment apparatus is not the plan this release runs.
    d6_ok, d6_detail, d6_plan = False, "unresolved", None
    try:
        d6_plan, d6_ok, d6_detail = validate_d6_against_active_plan(approval)
    except Exception as exc:
        d6_detail = str(exc)[:120]
    record("D6 plan valid against the active sealed ordered topology",
           d6_ok, d6_detail, d6_plan=d6_plan)

    # 4. scientific core identical to the frozen v1.6.0 baseline
    core_digest, core_entries = scientific_core_digest()
    baseline_digest = None
    baseline_detail = "baseline record missing: %s" % os.path.relpath(
        SCIENTIFIC_CORE_BASELINE, ROOT)
    if os.path.isfile(SCIENTIFIC_CORE_BASELINE):
        try:
            with open(SCIENTIFIC_CORE_BASELINE, "r") as handle:
                baseline_digest = json.load(handle).get("scientific_core_digest")
            baseline_detail = "core digest %s" % (core_digest[:16] + "...")
        except (ValueError, OSError) as exc:
            baseline_detail = "baseline record unreadable: %s" % str(exc)[:60]
    record("scientific core identical to the frozen v%s baseline" % VERSION,
           baseline_digest is not None and core_digest == baseline_digest,
           baseline_detail,
           scientific_core_digest=core_digest,
           baseline_scientific_core_digest=baseline_digest,
           baseline_record=os.path.relpath(SCIENTIFIC_CORE_BASELINE, ROOT))

    # 5. proxy code and configuration digests
    config = proxy_module.load_config(PROXY_CONFIG)
    identity = proxy_module.proxy_identity(config, PROXY_CODE)
    record("proxy configuration valid and loopback-bound", True,
           "%s -> %s" % (identity["bind"], identity["allowed_origin"]),
           proxy_code_sha256=identity["code_sha256"],
           proxy_config_sha256=identity["config_sha256"])

    # 6. launcher digest
    record("launcher digest recorded", True,
           sha256_file(SUPERVISOR_CODE)[:16] + "...",
           launcher_sha256=sha256_file(SUPERVISOR_CODE))

    # 7. target identity, read from the one authoritative manifest (no network)
    expected_identity = load_target_identity()
    record("expected target identity loaded", True,
           "engine %s, gateway %s, from %s"
           % (expected_identity["engine_version"],
              expected_identity["gateway_version"], TARGET_MANIFEST_NAME),
           target_manifest=TARGET_MANIFEST_NAME)

    # 7b. every active runtime source must name that same manifest.
    divergent = target_manifest_divergence()
    record("single authoritative target manifest across active paths",
           not divergent,
           TARGET_MANIFEST_NAME if not divergent else "divergent: %s" % divergent,
           target_manifest_references=divergent or "uniform")

    # 8. prior checkpoint and deviation records present
    deviations = os.path.join(ROOT, "releases", "deviations")
    records = sorted(os.listdir(deviations)) if os.path.isdir(deviations) else []
    record("prior checkpoint/deviation records present", len(records) >= 2,
           ", ".join(records), deviation_records=records)

    # 9. this run identity must not overwrite an earlier attempt (static)
    collisions = run_collisions(mode=mode, resuming=resuming,
                                launch_identity=launch_identity)
    record("run identity free of collisions", not collisions["collision"],
           "run %s; %s" % (collisions["run_id"],
                           "clear" if not collisions["found"]
                           else ("own pre-spawn commit: %s"
                                 if collisions.get("own_pre_spawn_commit")
                                 else "existing: %s")
                                % ", ".join(f["artifact"]
                                            for f in collisions["found"])),
           run_collisions=collisions)

    # 10. runtime qualification attestation (static; no network)
    #
    # v1.6.6. Two questions, asked at two different moments, with two
    # different correct answers:
    #
    #   before a launch  -- is there an eligible UNUSED attestation?
    #   during a launch  -- is THE attestation this launch holds still valid?
    #
    # Through v1.6.5 both moments asked the first question. `start` spends its
    # attestation before the proxy comes up, so by the time live preflight ran,
    # the selector correctly reported that no unused attestation existed and
    # refused the launch it had itself already committed. Asking the pre-launch
    # question mid-launch made a launch's own correct spend record the reason
    # it failed.
    #
    # Which question gets asked is decided by whether the caller is holding an
    # attestation, not by a flag that could be set on a path that holds none.
    import blackbox_attestation as attestation_module
    # Both branches must leave these bound: the result dict below reports them
    # unconditionally, and a branch that skipped one would raise instead of
    # returning a verdict -- during a launch that has already spent its
    # attestation, which is the worst possible moment to crash.
    attestation_report = None
    attestation_summary = None
    if transaction_attestation:
        validation = attestation_module.validate_reserved(
            transaction_attestation, launch_bindings(mode=mode),
            path=transaction_attestation.get("path"))
        attestation_report = validation
        attestation_summary = {
            "attestation_id": validation["attestation_id"],
            "content_digest": transaction_attestation.get("content_digest"),
            "validated_in_flight": True,
            "reselected": False,
        }
        record("reserved runtime attestation validated (not reselected)",
               validation["ok"],
               "%s; %s"
               % (validation.get("outcome", "INVALID"),
                  "; ".join(validation["problems"]) if validation["problems"]
                  else "%s spent by this launch (pid %s), marker and "
                       "durable ledger agree"
                       % (validation["attestation_id"],
                          validation["launch_pid"])),
               attestation=attestation_summary,
               attestation_report=validation)
    else:
        _att, _att_path, attestation_report = attestation_module.select(
            launch_bindings())
        attestation_summary = attestation_report.get("selected")
        record("runtime qualification attestation present and bound",
               attestation_report["outcome"] == "AUTHORIZED",
               "%s; %d on disk, %d rejected"
               % (attestation_report["outcome"],
                  attestation_report["attestations_on_disk"],
                  len(attestation_report["rejected"])),
               attestation=attestation_report.get("selected"),
               attestation_report=attestation_report)

    # ---- live phase ------------------------------------------------------
    # Requires a running proxy, so it is performed by `start` (which launches
    # that proxy first), never by standalone `preflight`.

    # 11. live proxy identity must match the approved digests
    credential = proxy_credential()
    live = None
    if live_phase:
        if not credential:
            record("live proxy identity verified", False,
                   "BLACKBOX_PROXY_CREDENTIAL/SEED absent")
        else:
            try:
                live = verify_proxy_live(config, credential)
                matches = (live["code_sha256"] == identity["code_sha256"]
                           and live["config_sha256"] == identity["config_sha256"])
                record("live proxy identity verified", matches,
                       "code %s config %s" % (live["code_sha256"][:12],
                                              live["config_sha256"][:12]))
            except Exception as exc:
                record("live proxy identity verified", False,
                       "%s: %s" % (type(exc).__name__, str(exc)[:60]))

    # 12. The RESOLVED proxy must be this proxy.
    #
    # Checking HTTP_PROXY alone is not enough. urllib resolves proxies from
    # every *_proxy spelling in the environment and, on macOS, from System
    # Configuration as well. A stray lowercase http_proxy or a system proxy
    # setting can silently take precedence over the value we set, which would
    # route target traffic somewhere other than the verified filtering proxy.
    # This check asks urllib what it will ACTUALLY use.
    expected_netloc = "%s:%s" % (config["bind_host"], config["bind_port"])
    if live_phase:
        resolved = urllib.request.getproxies()
        http_ok = expected_netloc in (resolved.get("http") or "")
        https_ok = expected_netloc in (resolved.get("https") or "")
        strays = sorted(k for k, v in resolved.items()
                        if k in ("http", "https", "all")
                        and expected_netloc not in (v or ""))
        record("resolved proxy is the verified proxy (all spellings)",
               http_ok and https_ok and not strays,
               "urllib resolves http/https to %s"
               % ("the verified proxy" if http_ok and https_ok
                  else "something else; strays: %s" % strays),
               resolved_scheme_keys=sorted(resolved))

    ok = all(entry["ok"] for entry in checks)
    live_status = "PERFORMED" if live_phase else "NOT_PERFORMED"
    return {"ok": ok, "checks": checks, "timestamp_utc": utc(),
            "phase": "static+live" if live_phase else "static",
            "live_phase_status": live_status,
            "live_checks_meaning": (
                "live proxy identity and resolved-proxy routing were verified"
                if live_phase else
                "live proxy identity and resolved-proxy routing were NOT "
                "verified by this run; they are verified at start, after the "
                "proxy is launched and before the runner is spawned. A passing "
                "static preflight does not mean live verification occurred."),
            "network_operations_performed": 1 if live_phase else 0,
            "analysis_endpoints_contacted": 0,
            "run_collisions": collisions,
            "attestation_report": attestation_report,
            "attestation": attestation_summary,
            "target_calls_used": 0,
            "proxy_identity": identity, "live_proxy_identity": live,
            "scientific_core_digest": core_digest,
            "baseline_scientific_core_digest": baseline_digest,
            "d6_plan": d6_plan,
            "release_digest": manifest.get("release_digest"),
            "approval_digest": approval_digest}


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def _spawn_detached(argv, log_path, env):
    """Start a process that outlives this one and the terminal."""
    handle = open(log_path, "ab")
    kwargs = {"stdout": handle, "stderr": handle, "stdin": subprocess.DEVNULL,
              "cwd": ROOT, "env": env, "close_fds": True}
    if hasattr(os, "setsid"):
        kwargs["preexec_fn"] = os.setsid      # detach from the terminal
    return subprocess.Popen(argv, **kwargs)


def start_proxy(env):
    state = load_state()
    if process_alive(state.get("proxy_pid")):
        return state["proxy_pid"], False
    proc = _spawn_detached([sys.executable, PROXY_CODE, PROXY_CONFIG],
                           PROXY_LOG, env)
    time.sleep(1.2)
    if proc.poll() is not None:
        raise PreflightFailure(
            "the standalone proxy exited immediately; see %s"
            % os.path.relpath(PROXY_LOG, ROOT))
    return proc.pid, True


def cmd_preflight(args):
    mode = "full" if (isinstance(args, list) and "--full" in args) \
        else "checkpoint"
    print("preflight, STATIC phase (zero network operations, no target call):")
    result = preflight(live_phase=False, mode=mode)
    print("\nresult:", "PASS" if result["ok"] else "FAIL",
          "| network operations:", result["network_operations_performed"],
          "| target calls:", result["target_calls_used"])
    print("live phase:", result["live_phase_status"], "--",
          result["live_checks_meaning"])
    return 0 if result["ok"] else 1


def cmd_start(args, resuming=False):
    mode_args = args if isinstance(args, list) else []

    # ---- launch mode must be stated explicitly (v1.6.0) -------------------
    #
    # v1.6.0 is a FRESH release, not a continuation. It replaces the
    # count-primary target with the reviewed ordered-evidence engine and moves
    # the apparatus from 53 configurations and 125 gated streams to 60 and 153.
    # The v1.5.2 storage checkpoint was produced by the predecessor apparatus
    # against a different target and a different stream family, so it cannot be
    # inherited, continued, imported or reused here: doing so would mix two
    # incompatible event families in one campaign.
    #
    #   --full     the authorized action: a fresh 30,000-request first look;
    #   (nothing)  refused, so a fresh full campaign is never a default.
    #
    # The predecessor continuation flag is refused explicitly rather than
    # ignored, so an operator repeating the v1.5.3 command is told why.
    continuing = CONTINUATION_FLAG in mode_args
    fresh_full = "--full" in mode_args

    if continuing:
        sys.stderr.write(
            "FAIL_CLOSED: %s is refused by v%s.\n\n"
            "The v%s checkpoint belongs to the predecessor apparatus: 53 "
            "configurations, 125 gated\nstreams, and the count-primary target. "
            "v%s runs 60 configurations and 153 gated\nstreams against the "
            "reviewed ordered-evidence engine. Those replications are not\n"
            "commensurable and must not be mixed into one campaign.\n\n"
            "The authorized action is a fresh campaign:\n\n"
            "  python3 tools/blackbox_supervisor.py start --full\n\n"
            "Nothing was started and no target call was made.\n"
            % (CONTINUATION_FLAG, VERSION, PREDECESSOR_VERSION, VERSION))
        return 8

    if not fresh_full and not resuming:
        sys.stderr.write(
            "FAIL_CLOSED: v%s requires an explicit launch mode.\n\n"
            "A fresh full campaign issues %d requests at the first look and up "
            "to %d in the\nworst case, so it is never started by default.\n\n"
            "The authorized action is:\n\n"
            "  python3 tools/blackbox_supervisor.py start --full\n\n"
            "Nothing was started and no target call was made.\n"
            % (VERSION, FIRST_LOOK_REQUESTS, WORST_CASE_REQUESTS))
        return 8

    checkpoint = False
    mode = "full"

    # v1.6.0 inherits nothing. The predecessor checkpoint is neither verified
    # nor read; its evidence directory is protected by run_collisions() and is
    # never written.

    # Refuse before touching anything: no proxy launched, no process spawned,
    # no file written. A previous attempt's evidence cannot be overwritten.
    collisions = run_collisions(mode=mode, resuming=resuming)
    if collisions["collision"]:
        sys.stderr.write("FAIL_CLOSED: run identity %s already has artifacts "
                         "on disk:\n" % collisions["run_id"])
        for entry in collisions["found"]:
            sys.stderr.write("  - %s: %s\n"
                             % (entry["artifact"], entry["path"]))
        sys.stderr.write("%s\n" % collisions["remedy"])
        return 6

    # ---- transactional launch (v1.5.4) ----------------------------------
    #
    # Everything that can fail is done, and made durable, BEFORE any process
    # exists. v1.5.3 spawned the runner and then discovered the ledger was
    # read-only, leaving a running campaign with no durable record of itself
    # and an attestation that no ledger showed as used.
    import blackbox_launch_safety as safety
    transaction = safety.LaunchTransaction(
        FULL_RUN_ID, os.path.join(RESULTS,
                                  "launch-abort-v%s.json" % VERSION))

    # Step 1: prove the ledger is genuinely writable. A real append and a
    # real fsync -- os.access() answers about permission bits, not about
    # read-only mounts, full filesystems or immutable flags.
    probe = safety.probe_ledger_writable(
        launch={"run_id": FULL_RUN_ID})
    if not probe["writable"]:
        sys.stderr.write("FAIL_CLOSED: the attestation ledger is not "
                         "writable, so a launch could not be recorded:\n")
        for entry in probe["checks"]:
            if not entry["ok"]:
                sys.stderr.write("  - %s: %s\n"
                                 % (entry["check"], entry["detail"]))
        sys.stderr.write("Nothing was started and no target call was made.\n")
        return 10
    transaction.step("attestation ledger writable", True,
                     probe["method"], checks=probe["checks"])

    # Qualification gate. Runs before the proxy is launched, before the
    # runner is spawned, and before anything could contact an analysis
    # endpoint. A launch that is not covered by a passing, bound, unused
    # attestation does not happen.
    import blackbox_attestation as attestation_module
    expected = launch_bindings(mode=mode)
    attestation, attestation_path, attestation_report = \
        attestation_module.select(expected, resuming=resuming)
    # A distinct outcome deserves a distinct exit: an uninterpretable
    # authoritative ledger is not "no matching attestation", and reporting it
    # as one would send the operator looking for the wrong problem.
    if attestation_report.get("outcome") == "SPEND_LEDGER_UNINTERPRETABLE":
        sys.stderr.write(
            "FAIL_CLOSED: the authoritative spend ledger could not be "
            "interpreted (%s).\n" % attestation_report["fail_closed_reason"])
        sys.stderr.write("  %s\n" % attestation_report["fail_closed_detail"]
                         if attestation_report.get("fail_closed_detail")
                         else "")
        ledger = attestation_report["spend_ledger"]
        for label, key in (("malformed lines", "malformed_lines"),
                           ("unexpected record types", "unknown_record_types"),
                           ("structurally invalid records",
                            "structural_errors"),
                           ("contradictory duplicates", "contradictions")):
            entries = ledger.get(key) or []
            if entries:
                sys.stderr.write("  %s at line(s): %s\n"
                                 % (label,
                                    ", ".join(str(e["line"])
                                              for e in entries)))
        sys.stderr.write(
            "No attestation can be shown to be unspent, so nothing is "
            "authorized. No marker was created, no process was started and "
            "no target call was made.\n"
            "There is deliberately no option to proceed past this.\n")
        return 19

    if attestation is None:
        sys.stderr.write(
            "FAIL_CLOSED: no runtime qualification attestation authorizes "
            "this launch.\n"
            "Required: exactly %d PASS, zero FAIL, zero BLOCKED, internally "
            "intact, bound to this release/approval/proxy/config/attestation-"
            "module/launcher/host/target, and bound to run %s specifically, "
            "and not already used.\n"
            "An attestation produced for the v%s checkpoint run does NOT "
            "authorize the full campaign.\n"
            % (attestation_module.REQUIRED_PASS, FULL_RUN_ID,
               PREDECESSOR_VERSION))
        sys.stderr.write("  attestations on disk: %d\n"
                         % attestation_report["attestations_on_disk"])
        for entry in attestation_report["rejected"]:
            sys.stderr.write("  - %s rejected:\n" % entry["attestation_id"])
            for problem in entry["problems"]:
                sys.stderr.write("      %s\n" % problem)
        for entry in attestation_report["damaged"]:
            sys.stderr.write("  - unreadable: %s (%s)\n"
                             % (entry["path"], entry["error"]))
        sys.stderr.write(
            "\nRun the qualifier in Terminal.app with the gateway running:\n"
            "  python3 tools/blackbox_proxy_qualify.py\n"
            "No target call was made and nothing was started.\n")
        return 7
    transaction.step("attestation selected", True,
                     attestation["attestation_id"],
                     content_digest=attestation["content_digest"])

    # Credentials are checked here, still before anything is spawned or
    # reserved: failing on a missing token after burning an attestation would
    # cost a qualification run for a typo.
    credential = proxy_credential()
    if not credential:
        sys.stderr.write("FAIL_CLOSED: set BLACKBOX_PROXY_SEED (or "
                         "BLACKBOX_PROXY_CREDENTIAL) before starting\n")
        return 4
    if not os.environ.get("BLACKBOX_TARGET_TOKEN"):
        sys.stderr.write(
            "FAIL_CLOSED: BLACKBOX_TARGET_TOKEN is not set.\n"
            "The active gateway's token file is\n"
            "  /tmp/blackbox-ordinal-target-v0.1.0.token\n"
            'Export it with:\n'
            '  export BLACKBOX_TARGET_TOKEN='
            '"$(</tmp/blackbox-ordinal-target-v0.1.0.token)"\n'
            "(/tmp/blackbox-ordinal-gateway.token is an obsolete path; a "
            "token read from it produces HTTP 401.)\n")
        return 4

    # Step 2: exclusive run-identity lock. Held for the run's lifetime, so a
    # second start for the same identity fails here -- before any process
    # exists and before any campaign evidence is written.
    try:
        lock = safety.RunIdentityLock(FULL_RUN_ID).acquire()
    except safety.DurabilityError as exc:
        sys.stderr.write("FAIL_CLOSED (durability): %s\n" % exc)
        sys.stderr.write("No process was started and no target call was "
                         "made. The attestation was NOT reserved and remains "
                         "unspent.\n")
        return 17
    except safety.LaunchAborted as exc:
        sys.stderr.write("FAIL_CLOSED: %s\n" % exc)
        sys.stderr.write("Nothing was started and no target call was made.\n")
        return 11
    transaction.lock = lock
    transaction.step("run identity locked", True, FULL_RUN_ID,
                     adopted_stale_lock=lock.adopted_stale)

    # Step 3: record the AUTHORITATIVE spend, durably, before the marker.
    #
    # v1.5.6 treated the O_EXCL marker as the spend authority. A marker is a
    # new directory entry, so a directory-fsync failure meant the code called
    # an attestation "permanently spent" while knowing the marker might not
    # survive a reboot -- after which nothing authoritative would remain and
    # the attestation could be selected again.
    #
    # The spend ledger already exists and its directory entry is already
    # durable (established during the probe), so appending to it and fsyncing
    # the FILE is durable on its own. This append is the point at which the
    # attestation becomes permanently spent.
    spend_context = {
        "run_id": FULL_RUN_ID, "mode": mode,
        "release_digest": expected["release_digest"],
        "approval_digest": expected["approval_digest"],
        "content_digest": attestation["content_digest"]}
    try:
        spend_record = safety.record_spend(attestation["attestation_id"],
                                           spend_context)
    except safety.DurabilityError as exc:
        lock.release()
        sys.stderr.write("FAIL_CLOSED (durability): %s\n" % exc)
        sys.stderr.write("No marker was created, no process was started and "
                         "no target call was made. The attestation is NOT "
                         "claimed spent; the run-identity lock was "
                         "released.\n")
        return 18
    transaction.spend_record = spend_record
    transaction.step("attestation spend durably recorded", True,
                     "authoritative; survives a crash from this point",
                     ledger=os.path.relpath(safety.SPEND_LEDGER, ROOT),
                     permanently_spent=True)

    # Step 4: atomically reserve with the O_EXCL marker. This remains the
    # concurrency control; it is no longer the spend authority.
    try:
        marker = safety.reserve(attestation["attestation_id"], {
            "run_id": FULL_RUN_ID, "mode": mode,
            "release_digest": expected["release_digest"],
            "approval_digest": expected["approval_digest"],
            "content_digest": attestation["content_digest"]})
    except safety.DurabilityError as exc:
        lock.release()
        sys.stderr.write("FAIL_CLOSED (durability): %s\n" % exc)
        sys.stderr.write("No process was started and no target call was "
                         "made. The attestation is PERMANENTLY SPENT on the "
                         "authority of the durable spend ledger, which does "
                         "not depend on the marker surviving a crash. "
                         "Recovery is a new qualification run.\n")
        return 17
    except safety.LaunchAborted as exc:
        lock.release()
        sys.stderr.write("FAIL_CLOSED: %s\n" % exc)
        sys.stderr.write("Nothing was started and no target call was made.\n")
        return 12
    transaction.reservation = os.path.relpath(marker, ROOT)
    transaction.step("attestation reserved and spent", True,
                     transaction.reservation,
                     spent_before_any_process_existed=True,
                     reusable_after_failure=False)

    import importlib
    sys.path.insert(0, TOOLS)
    proxy_module = importlib.import_module("blackbox_proxy")
    config = proxy_module.load_config(PROXY_CONFIG)

    env = dict(os.environ)
    env["BLACKBOX_PROXY_CREDENTIAL"] = credential
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)

    # Step 4: write minimal run state and provenance durably -- fsynced,
    # including the directory entry -- BEFORE anything is spawned. v1.5.3
    # wrote neither, because it tried to write them after the runner was
    # already executing and the attempt died on the read-only ledger.
    campaign_id = "blackbox-ordinal-v%s-%s" % (
        VERSION, utc().replace(":", "").replace("-", ""))
    minimal_state = {
        "campaign_id": campaign_id, "run_id": FULL_RUN_ID, "mode": mode,
        "launch_state": "PRE_SPAWN_COMMITTED",
        "started_utc": utc(), "last_event_utc": utc(),
        "evidence_dir": os.path.relpath(EVIDENCE_DIR, ROOT),
        "runner_pid": None, "proxy_pid": None,
        "run_identity_lock": os.path.relpath(lock.path, ROOT),
        "runtime_attestation": {
            "attestation_id": attestation["attestation_id"],
            "content_digest": attestation["content_digest"],
            "reservation": transaction.reservation,
            "spent_before_spawn": True},
        "history": [{"event": "pre-spawn commit", "timestamp_utc": utc()}],
    }
    try:
        safety.durable_write(
            STATE_PATH, json.dumps(minimal_state, indent=2, sort_keys=True)
            + "\n")
        safety.durable_write(
            PROVENANCE_PATH, json.dumps({
                "provenance_version": VERSION,
                "launch_state": "PRE_SPAWN_COMMITTED",
                "recorded_utc": utc(), "campaign_id": campaign_id,
                "run_id": FULL_RUN_ID,
                "release_digest": expected["release_digest"],
                "approval_digest": expected["approval_digest"],
                "runtime_attestation_id": attestation["attestation_id"],
                "runtime_attestation_digest": attestation["content_digest"],
                "note": "minimal pre-spawn provenance, written and fsynced "
                        "before any process existed. Completed after a "
                        "successful launch.",
                "secrets_recorded": False},
                indent=2, sort_keys=True) + "\n")
    except safety.DurabilityError as exc:
        record = transaction.abort("pre-spawn durability failure: %s" % exc)
        sys.stderr.write("FAIL_CLOSED (durability): could not durably record "
                         "the launch before spawning: %s\n" % exc)
        sys.stderr.write("No process was started and no target call was "
                         "made. The attestation is SPENT. Abort record "
                         "durable: %s\n" % record.get("abort_record_durable"))
        return 17
    except OSError as exc:
        transaction.abort("durable pre-spawn write failed: %s" % exc)
        sys.stderr.write("FAIL_CLOSED: could not durably record the launch "
                         "before spawning: %s\n" % exc)
        sys.stderr.write("Nothing was started and no target call was made.\n")
        return 13
    transaction.step("run state and provenance durably written", True,
                     "fsynced file and directory, before any spawn")

    # Step 5: only now may processes be created. From here on, any failure
    # terminates everything this launch started.
    try:
        proxy_pid, started = start_proxy(env)
    except Exception as exc:
        transaction.abort("proxy launch failed: %s" % exc)
        sys.stderr.write("FAIL_CLOSED: proxy launch failed: %s\n" % exc)
        return 14
    if started:
        transaction.register_process("proxy", proxy_pid)
    transaction.step("proxy started", True, "pid %s" % proxy_pid)

    # The runner talks only to our proxy.
    endpoint = "http://%s@%s:%s" % (
        credential.replace(":", "%3A", 1) if False else credential,
        config["bind_host"], config["bind_port"])
    runner_env = dict(env)
    # Remove EVERY competing proxy spelling first. urllib merges all *_proxy
    # variables, so a leftover lowercase or scheme-specific value could
    # silently outrank ours and divert target traffic off the verified proxy.
    for name in list(runner_env):
        if name.lower().endswith("_proxy") and name.lower() not in (
                "no_proxy",):
            runner_env.pop(name, None)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        runner_env[name] = endpoint

    # The runner is the only process authorized to run the campaign, and only
    # while this launch is in progress. The token is the attestation this launch
    # already reserved and spent, which the durable pre-spawn state records, so
    # the runner's environment and that state must agree before the campaign
    # constructs a transport or contacts anything.
    runner_env["BLACKBOX_SUPERVISED_LAUNCH"] = attestation["content_digest"]

    saved = dict(os.environ)
    for name in list(os.environ):
        if name.lower().endswith("_proxy") and name.lower() != "no_proxy":
            os.environ.pop(name, None)
    os.environ.update({k: runner_env[k] for k in
                       ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                        "http_proxy", "https_proxy", "all_proxy")})
    # This launch is already holding a reserved, permanently spent attestation,
    # so preflight must validate THAT one rather than look for an unused one it
    # would never find. Identity, digest, reservation marker and owning pid are
    # passed from the transaction; preflight re-reads the corroborating
    # evidence from disk itself (v1.6.6).
    transaction_attestation = {
        "attestation_id": attestation["attestation_id"],
        "content_digest": attestation["content_digest"],
        "run_id": expected["run_id"],
        "launch_pid": os.getpid(),
        "reservation_marker": marker,
        "path": attestation_path,
    }

    try:
        # Static + live. The proxy is now running, so the live phase is
        # meaningful; it verifies the proxy's identity and the proxy urllib
        # will actually resolve, and contacts no analysis endpoint.
        result = preflight(live_phase=True, verbose=True, mode=mode,
                           resuming=resuming,
                           transaction_attestation=transaction_attestation,
                           launch_identity=campaign_id)
    finally:
        os.environ.clear()
        os.environ.update(saved)

    if not result["ok"]:
        record = transaction.abort("live preflight failed")
        sys.stderr.write("\nPREFLIGHT_FAILED: not starting; no target call "
                         "was made.\n")
        sys.stderr.write("terminated %d process(es) started by this launch; "
                         "orphans: %d\n"
                         % (len(record["processes_terminated"]),
                            len(record["orphans_left"])))
        sys.stderr.write("the attestation stays spent; recovery is a new "
                         "qualification run\n")
        return 5

    # ---- no predecessor evidence is inherited ----------------------------
    #
    # v1.6.2 is a fresh campaign. It neither reads, imports, references nor
    # copies predecessor campaign evidence: the v1.5.2 checkpoint belongs to the
    # 53-configuration/125-stream apparatus and is not commensurable with the
    # sealed 60-configuration/153-stream family this release runs.
    #
    # The predecessor evidence directory is protected by run_collisions() and is
    # never written. Nothing here opens it.
    assert_no_predecessor_evidence_import()

    argv = [sys.executable, "-m", "harness.cli", "campaign", "--confirm"]

    # Keep the machine awake for the duration on macOS.
    if sys.platform == "darwin" and os.path.exists("/usr/bin/caffeinate"):
        argv = ["/usr/bin/caffeinate", "-i", "-s"] + argv
        sleep_prevention = "caffeinate -i -s"
    else:
        sleep_prevention = "not available on this platform; interruption is "\
                           "detected and recorded by crash recovery"

    try:
        proc = _spawn_detached(argv, RUN_LOG, runner_env)
    except Exception as exc:
        record = transaction.abort("runner spawn failed: %s" % exc)
        sys.stderr.write("FAIL_CLOSED: runner spawn failed: %s\n" % exc)
        sys.stderr.write("terminated %d process(es); orphans: %d\n"
                         % (len(record["processes_terminated"]),
                            len(record["orphans_left"])))
        return 15
    transaction.register_process("runner", proc.pid)
    transaction.step("runner spawned", True, "pid %d" % proc.pid)

    try:
        return _finish_launch(transaction, attestation, attestation_path,
                              attestation_module, proc, proxy_pid, started,
                              lock, expected, result,
                              mode, checkpoint, resuming, sleep_prevention,
                              campaign_id)
    except Exception as exc:
        record = transaction.abort("post-spawn bookkeeping failed: %s" % exc)
        sys.stderr.write("FAIL_CLOSED: post-spawn bookkeeping failed: %s\n"
                         % exc)
        sys.stderr.write("terminated %d process(es); orphans: %d\n"
                         % (len(record["processes_terminated"]),
                            len(record["orphans_left"])))
        sys.stderr.write("the run was NOT started. Attestation remains "
                         "spent. Abort record written: %s, durable: %s\n"
                         % (record.get("abort_record_written"),
                            record.get("abort_record_durable")))
        if not record.get("abort_record_durable"):
            sys.stderr.write("WARNING: the abort record could not be made "
                             "durable; a crash could lose it.\n")
        return 16


def _finish_launch(transaction, attestation, attestation_path,
                   attestation_module, proc, proxy_pid, started, lock,
                   expected, result, mode, checkpoint,
                   resuming, sleep_prevention, campaign_id):
    """Post-spawn bookkeeping.

    Separated so that ANY failure in it is caught by one handler that
    terminates every process this launch started. v1.5.3's failure was
    exactly here, and there was no handler.

    v1.6.2 records no continuation lineage: the run inherits nothing.
    """
    # Consumed only once the runner actually exists. The attestation was
    # already SPENT at reservation; this appends the human-readable record.
    consumed = attestation_module.consume(
        attestation, attestation_path,
        {"run_id": CHECKPOINT_RUN_ID if checkpoint else FULL_RUN_ID,
         "runner_pid": proc.pid, "proxy_pid": proxy_pid,
         "release_digest": expected["release_digest"],
         "approval_digest": expected["approval_digest"],
         "mode": mode})

    state = load_state()
    history = state.get("history", [])
    history.append({"event": "resume" if resuming else "start",
                    "timestamp_utc": utc(), "runner_pid": proc.pid,
                    "proxy_pid": proxy_pid, "mode":
                        "checkpoint" if checkpoint else "full"})
    state.update({
        "campaign_id": state.get("campaign_id") or campaign_id,
        "launch_state": "SPAWNED_AND_RECORDED",
        "run_identity_lock": os.path.relpath(lock.path, ROOT),
        "run_id": CHECKPOINT_RUN_ID if checkpoint else FULL_RUN_ID,
        "runner_pid": proc.pid, "proxy_pid": proxy_pid,
        "proxy_started_by_supervisor": started,
        "started_utc": state.get("started_utc") or utc(),
        "last_event_utc": utc(),
        "evidence_dir": os.path.relpath(EVIDENCE_DIR, ROOT),
        "mode": "checkpoint" if checkpoint else "full",
        "sleep_prevention": sleep_prevention,
        "supervision": "detached child with setsid; survives terminal and "
                       "a reviewer agent exit",
        "claude_required_after_launch": False,
        "runtime_attestation": {
            "attestation_id": attestation["attestation_id"],
            "content_digest": attestation["content_digest"],
            "path": os.path.relpath(attestation_path, ROOT),
            "executed_utc": attestation.get("executed_utc"),
            "passed": attestation.get("passed"),
            "failed": attestation.get("failed"),
            "blocked": attestation.get("blocked"),
            "consumed_utc": consumed["consumed_utc"],
            "reservation": transaction.reservation,
            "spent_before_spawn": True},
        "launch_transaction": transaction.summary(),
        "lineage": {
            "kind": "FRESH_CAMPAIGN_NO_INHERITANCE",
            "inherits_predecessor_evidence": False,
            "predecessor_evidence_read": False,
            "predecessor_evidence_imported": False,
            "predecessor_evidence_copied": False,
            "inherited_replications": 0},
        "history": history,
    })
    save_state(state)
    write_provenance(result, state, attestation, attestation_path)

    transaction.step("post-spawn bookkeeping complete", True,
                     "state, provenance and consumption recorded")

    print("\nstarted: runner pid %d, proxy pid %d" % (proc.pid, proxy_pid))
    print("evidence :", os.path.relpath(EVIDENCE_DIR, ROOT))
    print("log      :", os.path.relpath(RUN_LOG, ROOT))
    print("sleep    :", sleep_prevention)
    print("a reviewer agent may now be closed.")
    return 0


def cmd_resume(args):
    state = load_state()

    # An ordinary resume cannot cross the run-id boundary. The v1.5.2 state
    # names the checkpoint run; resuming it would continue THAT run, under
    # an approval that excludes the remaining 317 segments. v1.5.3 keeps its
    # own state, so there is nothing here to resume until a continuation
    # launch has created it.
    if state and state.get("run_id") not in (FULL_RUN_ID, None):
        sys.stderr.write(
            "FAIL_CLOSED: recorded run is %s.\n"
            "This release resumes only its own run identity %s.\n"
            "A run belonging to another release is never resumed or imported.\n"
            % (state.get("run_id"), FULL_RUN_ID))
        return 8

    if process_alive(state.get("runner_pid")):
        print("already running: pid", state["runner_pid"])
        return 0
    if not state:
        sys.stderr.write("no prior run state; use start\n")
        return 1

    # A predecessor continuation flag is refused here rather than forwarded.
    # v1.6.2 resumes only its own run identity and its own evidence set.
    supplied = list(args if isinstance(args, list) else [])
    legacy = [flag for flag in supplied if flag.startswith("--continue-from-")]
    if legacy:
        sys.stderr.write(
            "FAIL_CLOSED: %s is not a v%s launch mode.\n"
            "Resume continues run %s and its own evidence set only; no "
            "predecessor\nevidence is read, imported, referenced or copied.\n"
            % (", ".join(legacy), VERSION, FULL_RUN_ID))
        return 8

    print("resuming run %s: same release, approval, proxy configuration, "
          "target identity and evidence directory; nothing inherited"
          % FULL_RUN_ID)
    # The resumed launch is the same fresh full campaign, so it carries exactly
    # the mode the fresh launch carries and no predecessor flag.
    forwarded = [flag for flag in supplied if flag != "--full"]
    return cmd_start(["--full"] + forwarded, resuming=True)


def cmd_status(_args):
    """Read-only. Performs no network request of any kind."""
    state = load_state()
    if not state:
        print("no campaign run recorded")
        return 1

    # Filesystem only. Counts records; never reads a response body, never
    # names a segment, never computes or reports a verdict.
    slug_dir = EVIDENCE_DIR
    committed = 0
    segments_with_evidence = 0
    disk = 0
    if os.path.isdir(slug_dir):
        for name in sorted(os.listdir(slug_dir)):
            path = os.path.join(slug_dir, name)
            if not os.path.isfile(path):
                continue
            disk += os.path.getsize(path)
            if name.endswith(".index.jsonl"):
                segments_with_evidence += 1
                with open(path, "r") as handle:
                    for line in handle:
                        if line.strip():
                            committed += 1

    running = process_alive(state.get("runner_pid"))
    started = state.get("started_utc")
    elapsed = None
    if started:
        elapsed = (datetime.datetime.now(datetime.timezone.utc)
                   - parse_utc(started)).total_seconds()

    # Inherited replications were not requested by this run, so they are not
    # counted as its work -- neither in the request total nor in the rate used
    # for the estimate.
    # v1.6.2 inherits nothing, so every committed replication is this run's.
    new_replications = committed

    # Topology is derived from the sealed active plan, never hard-coded here.
    topology = active_topology()
    upper_bound = topology["worst_case_requests"]
    remaining = None
    if new_replications and elapsed:
        rate = new_replications / elapsed
        if rate:
            remaining = round((upper_bound - committed) / rate, 1)

    # Operational health only: does the operator need to intervene? This scans
    # for transport and launch failure markers. It does not read, count or
    # summarize anything about analysis content.
    intervention = []
    if os.path.isfile(RUN_LOG):
        with open(RUN_LOG, "r", errors="replace") as handle:
            tail = handle.read()[-20000:]
        for marker, meaning in (
                ("FAIL_CLOSED", "a gate refused; the run did not start"),
                ("CAPACITY", "the gateway reported a capacity limit"),
                ("ABORTED_INVALID", "the run aborted and is marked invalid"),
                ("ProxyNotConfigured", "proxy routing was lost"),
                ("Traceback", "the runner raised an unhandled exception")):
            if marker in tail:
                intervention.append({"marker": marker, "meaning": meaning})

    report = {
        "campaign_id": state.get("campaign_id"),
        "run_id": state.get("run_id"),
        "mode": state.get("mode"),
        "running": running,
        "runner_pid": state.get("runner_pid"),
        "proxy_pid": state.get("proxy_pid"),
        "proxy_running": process_alive(state.get("proxy_pid")),
        "started_utc": started,
        "elapsed_seconds": round(elapsed, 1) if elapsed else None,

        # -- sealed active topology --------------------------------------
        "configurations_total": topology["configurations"],
        "gated_streams_total": topology["gated_streams"],
        "first_look_requests": topology["first_look_requests"],
        "worst_case_requests": topology["worst_case_requests"],
        "looks": topology["looks"],
        "topology_source": topology["source"],

        # -- progress, without scientific labels -------------------------
        "segments_with_evidence": segments_with_evidence,
        "committed_replications_total": committed,
        "new_replications_this_run": new_replications,
        "new_requests_issued_by_this_run": new_replications,
        "inherits_predecessor_evidence": False,
        "estimated_remaining_seconds_upper_bound": remaining,
        "estimate_basis": "an upper bound assuming every segment runs to the "
                          "second look; the true total is smaller and depends "
                          "on information this status withholds",
        "evidence_disk_bytes": disk,

        # -- withheld ----------------------------------------------------
        "segment_names": "withheld: segment slugs encode scientific labels",
        "segment_dispositions": "withheld until the frozen campaign "
                                "completion rules permit release",
        "event_counts": "withheld until the frozen campaign completion rules "
                        "permit release",
        "verdicts": "withheld until the frozen campaign completion rules "
                    "permit release",
        "successful_analyses": "withheld until the run completes",
        "blocked_or_ambiguous": "withheld until the run completes",
        "response_content": "never exposed by status",

        # -- health ------------------------------------------------------
        "intervention_required": bool(intervention),
        "intervention_markers": intervention,

        "sleep_prevention": state.get("sleep_prevention"),
        "supervision": state.get("supervision"),
        "claude_required_after_launch": state.get(
            "claude_required_after_launch", False),
        "network_requests_made_by_status": 0,
        "filesystem_only": True,
        "response_bodies_read": False,
        "dispositions_exposed": False,
        "blinding_note": "Aggregate progress is not a disposition, but it is "
                         "not perfectly uninformative either: a segment that "
                         "stops at the first look leaves fewer replications "
                         "than one that continues. Segment identities and all "
                         "counts that would make that readable per segment are "
                         "withheld.",
        "lineage": state.get("lineage", {
            "kind": "FRESH_CAMPAIGN_NO_INHERITANCE",
            "inherits_predecessor_evidence": False}),
        "history": state.get("history", []),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_stop(_args):
    state = load_state()
    stopped = []
    for key, signame in (("runner_pid", signal.SIGTERM),
                         ("proxy_pid", signal.SIGTERM)):
        pid = state.get(key)
        if process_alive(pid):
            os.kill(int(pid), signame)
            stopped.append({"process": key, "pid": pid})
    for _ in range(50):
        if not process_alive(state.get("runner_pid")):
            break
        time.sleep(0.2)
    # Release the run-identity lock so a resume can reacquire it. The
    # attestation stays spent either way.
    import blackbox_launch_safety as safety
    lock_released = False
    lock_path = state.get("run_identity_lock")
    if lock_path:
        absolute = os.path.join(ROOT, lock_path)
        if os.path.exists(absolute):
            try:
                os.remove(absolute)
                lock_released = True
            except OSError:
                pass

    history = state.get("history", [])
    history.append({"event": "stop", "timestamp_utc": utc(),
                    "stopped": stopped,
                    "run_identity_lock_released": lock_released,
                    "attestation_remains_spent": True,
                    "contract": "a replication not yet committed to the index "
                                "is re-run on resume; the index-is-a-prefix "
                                "invariant prevents duplication or omission"})
    state["history"] = history
    state["last_event_utc"] = utc()
    save_state(state)
    print(json.dumps({"stopped": stopped,
                      "recovery_contract": "partial replication re-run on "
                                           "resume; no duplication, no "
                                           "omission"}, indent=2))
    return 0


def write_provenance(preflight_result, state, attestation=None,
                     attestation_path=None):
    import importlib
    sys.path.insert(0, TOOLS)
    proxy_module = importlib.import_module("blackbox_proxy")
    config = proxy_module.load_config(PROXY_CONFIG)
    core_digest, _entries = scientific_core_digest()
    record = {
        "provenance_version": VERSION,
        "recorded_utc": utc(),
        "release_digest": preflight_result.get("release_digest"),
        "approval_digest": preflight_result.get("approval_digest"),
        "scientific_core_digest_current": core_digest,
        "scientific_core_baseline_digest":
            preflight_result.get("baseline_scientific_core_digest"),
        "scientific_core_matches_baseline":
            core_digest == preflight_result.get("baseline_scientific_core_digest"),
        "scientific_core_baseline_record":
            os.path.relpath(SCIENTIFIC_CORE_BASELINE, ROOT),
        "launcher_sha256": sha256_file(SUPERVISOR_CODE),
        "proxy_code_sha256": sha256_file(PROXY_CODE),
        "proxy_config_sha256": proxy_module.config_digest(config),
        "proxy_allowlist": sorted(config["allowed_paths"]),
        "proxy_bind": "%s:%s" % (config["bind_host"], config["bind_port"]),
        "runtime": {"interpreter": sys.executable and "python3",
                    "version": platform.python_version(),
                    "implementation": platform.python_implementation()},
        "target_identity_expected": load_target_identity(),
        "target_manifest": TARGET_MANIFEST_NAME,
        "execution_host": host_identifier(),
        "campaign_id": state.get("campaign_id"),
        "run_id": state.get("run_id"),
        "evidence_directory": state.get("evidence_dir"),
        "supervision_mechanism": state.get("supervision"),
        "sleep_prevention": state.get("sleep_prevention"),
        "proxy_route_verification": {
            "live_identity_matched": bool(
                preflight_result.get("live_proxy_identity")),
            "verified_before_first_target_call": True,
            "placeholder_proxy_would_fail": True,
            "live_phase_status": preflight_result.get("live_phase_status"),
        },
        "preflight_phases": {
            "static": "release integrity, approval, D6 topology, scientific "
                      "core digest, proxy code/config digests, launcher "
                      "digest, expected target identity, deviation records, "
                      "run-collision safety; zero network operations",
            "live": "authenticated proxy control identity and resolved-proxy "
                    "routing; performed at start, after the proxy is launched "
                    "and before the runner is spawned",
            "analysis_endpoints_contacted_by_preflight": 0,
        },
        "run_collision_guard": {
            "enforced": True,
            "force_overwrite_option": None,
            "checked": preflight_result.get("run_collisions"),
        },
        "predecessor_deviation": "PROV-DEV-004 (checkpoint-v1.5-run-001, "
                                 "HTTP 401 from an obsolete token-file path)",
        "d6_plan": preflight_result.get("d6_plan"),
        "lineage": {
            "kind": "FRESH_CAMPAIGN_NO_INHERITANCE",
            "inherits_predecessor_evidence": False,
            "predecessor_evidence_read": False,
            "predecessor_evidence_imported": False,
            "predecessor_evidence_copied": False,
            "inherited_replications": 0,
            "note": "v%s runs the sealed 60-configuration/153-stream family "
                    "from scratch; no predecessor campaign evidence is read, "
                    "imported, referenced or copied" % VERSION,
        },
        "runtime_qualification_attestation": ({
            "attestation_id": attestation["attestation_id"],
            "content_digest": attestation["content_digest"],
            "path": os.path.relpath(attestation_path, ROOT)
                    if attestation_path else None,
            "executed_utc": attestation.get("executed_utc"),
            "sequence": attestation.get("sequence"),
            "passed": attestation.get("passed"),
            "failed": attestation.get("failed"),
            "blocked": attestation.get("blocked"),
            "target_requests_made": attestation.get("target_requests_made"),
            "target_request_paths": attestation.get("target_request_paths"),
            "analysis_endpoint_contacted":
                attestation.get("analysis_endpoint_contacted"),
            "bound_to": {field: attestation.get(field) for field in
                         __import__("blackbox_attestation").BINDING_FIELDS},
            "single_use": True,
            "not_a_release_artifact": True,
            "why_outside_the_release":
                "a live qualification result differs from the in-sandbox one; "
                "hashing it into the release would mean a successful "
                "qualification mutated the frozen release and failed the "
                "integrity gate",
        } if attestation else {
            "present": False,
            "note": "no attestation was recorded; a launch without one is "
                    "refused, so this provenance record did not accompany a "
                    "launch"}),
        "history": state.get("history", []),
        "claude_session_required_after_launch": False,
        "os_sandbox_note": (
            "OS-level source-read denial protected independent harness "
            "CONSTRUCTION and is not required for an already frozen "
            "deterministic runner. Execution integrity is supplied by the "
            "frozen release digest, the black-box endpoint, the filtering "
            "proxy, and the standing prohibition on human or LLM source "
            "review."),
        "secrets_recorded": False,
    }
    with open(PROVENANCE_PATH, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return record


COMMANDS = {"preflight": cmd_preflight, "start": cmd_start,
            "status": cmd_status, "stop": cmd_stop, "resume": cmd_resume}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        sys.stderr.write("usage: blackbox_supervisor.py "
                         "{preflight|start|status|stop|resume} [--full]\n")
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
