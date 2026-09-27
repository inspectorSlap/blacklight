"""Command-line entry point.

    python3 -m harness.cli build        # regenerate every frozen fixture
    python3 -m harness.cli selfqual     # run the two-sided gate
    python3 -m harness.cli freeze       # hash the release
    python3 -m harness.cli status       # phase-gate status
    python3 -m harness.cli campaign     # real black-box campaign (gated)

`campaign` refuses to run until the release is frozen, the two-sided gate has
passed, and the operator has approved the failure registry and the
simulation-acceptance proposal. That refusal is the locked phase gate, not a
convenience check.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os
import sys

from . import build_archives, build_fixtures, build_registry, freeze, runner
from . import selfqual, simulation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write(relative, payload):
    path = os.path.join(ROOT, relative)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def cmd_build(_args):
    written = build_fixtures.write_panel(build_fixtures.build_clean_panel(),
                                         "clean")
    written += build_fixtures.write_panel(build_fixtures.build_anchor_panel(),
                                          "anchors")
    written += build_archives.write_panel(build_archives.build_archive_panel())
    grid_path, seeds_path, grid = simulation.write_grid_and_seeds()
    registry = build_registry.build()
    build_registry.write(registry)
    build_registry.write_matrix(registry)
    print("scenario fixtures: %d" % len(written))
    print("simulation grid  : %d configurations, %d cells"
          % (grid["configuration_count"], grid["cell_count"]))
    print("registry rows    : %d" % len(registry["rows"]))
    return 0


def cmd_selfqual(_args):
    result = selfqual.run_gate()
    path = _write("results/self-qualification-v1.0.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "legs"}, indent=2))
    print("sensitivity: %d/%d mutants detected by their named check"
          % (sum(1 for r in result["legs"]["sensitivity"]["rows"]
                 if r["row_passed"]),
             result["legs"]["sensitivity"]["mutants_run"]))
    print("specificity: %s (%d scenarios)"
          % (result["legs"]["specificity"]["passed"],
             result["legs"]["specificity"]["scenarios_run"]))
    print("anchors    : %s (%d exact values)"
          % (result["legs"]["anchors"]["passed"],
             result["legs"]["anchors"]["numeric_values_checked"]))
    print(path)
    return 0 if result["verdict"] == "HARNESS_SELF_QUALIFIED" else 1


def cmd_freeze(_args):
    manifest = freeze.release_manifest()
    path = _write("results/harness-release-manifest-v%s.json" % freeze.HARNESS_VERSION, manifest)
    print("artifacts hashed: %d" % manifest["artifact_count"])
    print("release digest  : %s" % manifest["release_digest"])
    print(path)
    return 0


def cmd_status(_args):
    status = freeze.phase_gate_status()
    print(json.dumps(status, indent=2))
    return 0


SUPERVISED_LAUNCH_ENV = "BLACKBOX_SUPERVISED_LAUNCH"


def _supervised_launch_authorization():
    """Is this process the runner of an in-progress supervised launch?

    Two independent facts must agree, so neither a stale state file nor a
    hand-set environment variable is sufficient on its own:

    * the supervisor placed a launch token in the runner's environment, and
    * the durable pre-spawn run state names this release's run identity and
      carries the same token as the attestation it already reserved and spent.

    Returns ``(authorized, detail)`` and makes no network or target call.
    """
    token = os.environ.get(SUPERVISED_LAUNCH_ENV)
    if not token:
        return False, ("%s is not set: this invocation is not a supervised "
                       "launch runner" % SUPERVISED_LAUNCH_ENV)

    state_path = os.path.join(
        ROOT, "results", "campaign-run-state-v%s.json" % freeze.HARNESS_VERSION)
    if not os.path.isfile(state_path):
        return False, ("no supervised launch state at %s"
                       % os.path.relpath(state_path, ROOT))
    try:
        with open(state_path, "r") as handle:
            state = json.load(handle)
    except ValueError as exc:
        return False, "supervised launch state is unreadable: %s" % exc

    expected_run = "campaign-v%s-run-001" % freeze.HARNESS_VERSION
    if state.get("run_id") != expected_run:
        return False, ("launch state names run %r, not this release's %r"
                       % (state.get("run_id"), expected_run))

    attestation = state.get("runtime_attestation") or {}
    recorded = attestation.get("content_digest")
    if not recorded:
        return False, "launch state records no runtime attestation"
    if recorded != token:
        return False, ("%s does not match the attestation recorded for this "
                       "launch" % SUPERVISED_LAUNCH_ENV)
    if not attestation.get("spent_before_spawn"):
        return False, "the launch attestation was not spent before the spawn"
    return True, "supervised launch %s" % expected_run


def cmd_campaign(args):
    """Run the real black-box coverage campaign. Gated and explicit."""
    status = freeze.phase_gate_status()
    if not status["real_engine_campaign_permitted"]:
        sys.stderr.write(
            "PHASE_GATE_CLOSED: the real black-box campaign may not begin.\n")
        for blocker in status["blockers"]:
            sys.stderr.write("  - %s\n" % blocker)
        sys.stderr.write(
            "\nAmendment section 6 requires the oracle, anchors, scenarios, "
            "sound reference, clean panel, failure registry, defective-target "
            "panel, acceptance proposal, harness and expected-answer manifest "
            "to be frozen and hashed, the two-sided gate to pass, and the "
            "operator to approve the registry and the acceptance proposal.\n")
        return 2

    if "--confirm" not in args:
        sys.stderr.write(
            "The phase gate is open, but launching the real campaign is an "
            "explicit operator action.\n"
            "It will contact the scientific endpoints of the real engine.\n\n"
            "Re-run with --confirm to start:\n"
            "    python3 -m harness.cli campaign --confirm\n")
        return 3

    # Release approval alone does not authorize execution. The phase gate
    # answers "is this release approved", not "is a supervised launch under
    # way", so on its own it would let a direct invocation contact the target
    # with no supervisor, no runtime attestation and no execution authorization.
    #
    # The campaign therefore runs only as the runner of an in-progress
    # supervised launch. This is checked BEFORE any transport is constructed,
    # any identity request is made, or any target is contacted.
    supervised, detail = _supervised_launch_authorization()
    if not supervised:
        sys.stderr.write(
            "FAIL_CLOSED: the campaign runs only as the runner of a supervised "
            "launch.\n  %s\n\n"
            "Release approval authorizes the release; it does not authorize "
            "execution.\nA supervised launch additionally requires the runtime "
            "attestation, the\nlaunch transaction and the live preflight, none "
            "of which this invocation has.\n\n"
            "The authorized action is:\n"
            "    python3 tools/blackbox_supervisor.py start --full\n\n"
            "No transport was constructed, no identity request was made and no "
            "target call\nwas made.\n" % detail)
        return 7

    from . import campaign as campaign_module
    from . import transport
    from .targets import BlackBoxTarget

    from .ordered import campaign as ordered_campaign
    from .ordered import runner as ordered_runner

    if "--checkpoint-first-segment" in args:
        sys.stderr.write(
            "FAIL_CLOSED: v1.6.0 has no storage-checkpoint mode.\n"
            "The checkpoint belonged to the predecessor 53-configuration "
            "apparatus and is not\ncommensurable with the 60-configuration, "
            "153-stream family this release runs.\n")
        return 6

    # Topology is proved against the verified contracts before any target call.
    topology = ordered_campaign.validate_topology()
    sys.stderr.write(
        "configurations: %d  gated streams: %d  first look: %d requests\n"
        % (topology["configurations"], topology["gated_streams"],
           topology["workload"]["first_look_requests"]))

    approval_digest = freeze.approval_record_digest()
    sys.stderr.write("approval record digest: %s\n" % approval_digest)

    try:
        client = transport.HttpTarget()
    except transport.ProxyNotConfigured as exc:
        sys.stderr.write("FAIL_CLOSED: %s\n" % exc)
        return 4

    with open(os.path.join(ROOT, "target-manifest-v0.5.json"), "r") as handle:
        expected_identity = json.load(handle)["target"]
    identity = transport.verify_identity(client, expected_identity)
    if not identity["identity_matches"]:
        sys.stderr.write("FAIL_CLOSED: target identity does not match the manifest:\n")
        for mismatch in identity["mismatches"]:
            sys.stderr.write("  - %s\n" % json.dumps(mismatch, sort_keys=True))
        return 4
    meta_digest = freeze.sha256_canonical(identity["meta"])

    store = campaign_module.EvidenceStore(
        os.path.join(ROOT, "results", "campaign-evidence-v%s" % freeze.HARNESS_VERSION))

    # The sealed C4 two-look procedure: look one always, look two only for
    # streams that return CONTINUE, cumulative over the first look.
    report = ordered_runner.run_two_look(
        target=BlackBoxTarget(client),
        store=store,
        meta_digest=meta_digest,
        integrity_digest=freeze.sha256_canonical(freeze.verify_release_integrity()),
    )
    report["target_identity"] = identity["meta"]
    report["approval_digest"] = approval_digest
    report["route_evidence"] = client.route_evidence()

    path = os.path.join(ROOT, "results",
                        "campaign-report-v%s.json" % freeze.HARNESS_VERSION)
    with open(path, "w") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print("configurations       :", report["configurations"])
    print("gated streams        :", report["gated_streams"])
    print("verdicts             :", json.dumps(report["verdict_counts"], sort_keys=True))
    print("zero-tolerance failed:", report["zero_tolerance_failed"])
    print("looks executed       :", report["looks_executed"])
    print("second look          :", json.dumps(report["second_look"], sort_keys=True))
    print("total requests       :", report["total_requests_issued"])
    print("campaign valid       :", report["campaign_valid"])
    print("route evidence       :", json.dumps(client.route_evidence()))
    print(path)
    return 0 if report.get("campaign_valid") else 5


def cmd_ordered_dryrun(args):
    """Zero-contact local run of the ordered campaign against the engine itself.

    Drives the in-process reviewed engine rather than the HTTP target, so it
    binds no socket and makes no network call. It exercises the campaign driver
    and the family-exactness guard deterministically, before the standalone
    campaign is ever launched.
    """
    from .ordered import runner as ordered_runner

    replications = 1
    for arg in args:
        if arg.startswith("--replications="):
            replications = int(arg.split("=", 1)[1])

    report = ordered_runner.run_campaign(
        target=ordered_runner.LocalEngineTarget(),
        look_index=0,
        replications=replications)
    report["note"] = ("in-process reviewed engine; zero network operations, "
                      "zero socket binds, zero target calls")
    path = _write("results/v%s-ordered-dryrun.json" % freeze.HARNESS_VERSION, report)
    print("configurations       :", report["configurations"])
    print("gated streams        :", report["gated_streams"])
    print("replications each    :", replications)
    print("identity checks      :", report["evidence_identity_verifications"])
    print("verdicts             :", json.dumps(report["verdict_counts"], sort_keys=True))
    print("zero-tolerance failed:", report["zero_tolerance_failed"])
    print(path)
    return 0 if not report["zero_tolerance_failed"] and not report["blocked"] else 5


def cmd_dryrun(_args):
    """Operational dry run against the local sound reference only."""
    from . import dryrun
    result = dryrun.run_all()
    path = _write("results/campaign-dryrun-v%s.json" % freeze.HARNESS_VERSION, result)
    for check in result["checks"]:
        print("%-42s %s" % (check["name"], check["status"]))
    print("\n%d/%d operational checks passed"
          % (result["passed"], result["total"]))
    print("real-engine scientific calls:",
          result["real_engine_scientific_calls"])
    print(path)
    return 0 if result["all_passed"] else 1


def cmd_scenarios(_args):
    scenarios = runner.load_all()
    for family in sorted(scenarios):
        print("%s (%d)" % (family, len(scenarios[family])))
        for scenario in scenarios[family]:
            print("  %-40s %-14s %s"
                  % (scenario["scenario_id"], scenario["assertion_strength"],
                     scenario["description"].split(".")[0][:90]))
    return 0


COMMANDS = {
    "build": cmd_build,
    "selfqual": cmd_selfqual,
    "freeze": cmd_freeze,
    "status": cmd_status,
    "campaign": cmd_campaign,
    "dryrun": cmd_dryrun,
    "ordered-dryrun": cmd_ordered_dryrun,
    "scenarios": cmd_scenarios,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        sys.stderr.write("usage: python3 -m harness.cli {%s}\n"
                         % "|".join(sorted(COMMANDS)))
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
