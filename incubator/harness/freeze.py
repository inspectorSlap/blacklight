"""Release hashing, environment manifest, and the phase gate.

Contract §4 requires "checksums for the released harness, scenarios, expected
answers, and report" and "an environment and dependency manifest". Amendment §6
requires every listed artifact to be frozen and hashed before the real engine
campaign may begin.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import json
import os
import platform
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RELEASE_ID = "blackbox-ordinal-independent-harness-1.6.6"
HARNESS_VERSION = "1.6.6"

# Artifact groups named by amendment §6.
ARTIFACT_GROUPS = {
    "executable_oracle": ["harness/oracle/core.py", "harness/oracle/population.py",
                          "harness/oracle/sample.py", "harness/oracle/__init__.py"],
    "hand_computed_anchors": ["fixtures/anchors/hand-anchors-v1.0.json",
                              "docs/ANCHORS.md"],
    "sound_reference_target": ["harness/reference/sound_reference.py",
                               "harness/reference/interval.py",
                               "harness/reference/archive.py",
                               "harness/reference/__init__.py"],
    "defective_target_panel": ["harness/mutants/mutants.py",
                               "harness/mutants/__init__.py"],
    "harness_implementation": ["harness/__init__.py", "harness/adapter.py",
                               "harness/runner.py", "harness/selfqual.py",
                               "harness/targets.py", "harness/transport.py",
                               "harness/simulation.py", "harness/freeze.py",
                               "harness/cli.py", "harness/build_fixtures.py",
                               "harness/build_archives.py",
                               "harness/build_registry.py",
                               "harness/checks/__init__.py",
                               "harness/checks/checks.py",
                               "harness/checks/rules.py",
                               "harness/checks/archive_checks.py",
                               "harness/checks/anchor_checks.py"],
    "campaign_implementation": ["harness/campaign.py", "harness/dryrun.py",
                                "harness/sequential.py", "harness/batching.py",
                                "harness/roster.py",
                                "harness/inflight.py", "harness/serial.py",
                                "reports/CAMPAIGN-RUNNER-v1.0.md",
                                "reports/CAMPAIGN-RUNNER-v1.1.md",
                                "reports/CAMPAIGN-RUNNER-v1.2.md",
                                "reports/CAMPAIGN-RUNNER-v1.3.md"],
    "operational_records": ["results/campaign-dryrun-v1.0.json",
                            "results/campaign-dryrun-v1.1.json",
                            "results/campaign-dryrun-v1.2.json",
                            "results/campaign-dryrun-v1.3.json",
                            "results/campaign-dryrun-v1.4.json",
                            "results/distribution-verification-v1.0.json"],
    "v1_1_amendment": ["reports/SIMULATION-ACCEPTANCE-ADDENDUM-v1.1.md"],
    "v1_2_amendment": ["reports/SIMULATION-ACCEPTANCE-ADDENDUM-v1.2.md",
                       "results/provenance-deviation-v1.2-001.json"],
    "v1_3_amendment": ["reports/SIMULATION-ACCEPTANCE-ADDENDUM-v1.5.md",
                       "releases/deviations/checkpoint-v1.2-run-001/DEVIATION-RECORD.json"],
    "operating_characteristics": ["harness/oc.py",
                                  "reports/OPERATING-CHARACTERISTICS-v1.1.md",
                                  "results/operating-characteristics-v1.1.json",
                                  "reports/OPERATING-CHARACTERISTICS-v1.2.md",
                                  "results/operating-characteristics-v1.2.json"],
    "operational_v1_5": ["tools/blackbox_proxy.py",
                         "tools/blackbox-proxy-config.json",
                         "tools/blackbox_supervisor.py",
                         "tools/blackbox_proxy_qualify.py",
                         "tools/blackbox_supervisor_qualify.py",
                         "tools/snapshot_release.py",
                         "reports/DETACHED-OPERATION-v1.5.md",
                         "results/proxy-qualification-v1.5.json",
                         "results/supervisor-qualification-v1.5.json"],
    "v1_5_amendment": ["reports/SIMULATION-ACCEPTANCE-ADDENDUM-v1.5.md",
                       "releases/deviations/checkpoint-v1.3-run-001/DEVIATION-RECORD.json"],
    # v1.5.1: operational corrections only. No scientific-core artifact is
    # listed here, and none changed -- see results/scientific-invariance-v1.5.1.json.
    "operational_v1_5_1": ["tools/blackbox_v151_qualify.py",
                           "reports/DETACHED-OPERATION-v1.5.1.md",
                           "results/proxy-qualification-v1.5.1.json",
                           "results/supervisor-qualification-v1.5.1.json",
                           "results/v1.5.1-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.1.json",
                           "results/change-classification-v1.5.1.json"],
    # v1.5.2: operational only. The qualification PROGRAM is a release
    # artifact; its runtime ATTESTATION deliberately is not, because a live
    # result differs from the in-sandbox one and hashing it in would mean a
    # successful Terminal qualification mutated the frozen release.
    "operational_v1_5_2": ["tools/blackbox_attestation.py",
                           "tools/blackbox_v152_qualify.py",
                           "reports/DETACHED-OPERATION-v1.5.2.md",
                           "reports/OPERATIONAL-CORRECTIONS-v1.5.2.md",
                           "results/supervisor-qualification-v1.5.2.json",
                           "results/v1.5.2-corrections-qualification.json",
                           "results/v1.5.2-negative-controls.json",
                           "results/scientific-invariance-v1.5.2.json",
                           "results/change-classification-v1.5.2.json"],
    # v1.5.3: continuation release. The sealed continuation decision, the
    # checkpoint inventory and the checkpoint seal are listed so the release
    # integrity check covers them. The checkpoint's OWN artifacts are not
    # listed: v1.5.2 remains their authoritative provenance source, and
    # nothing here may refreeze them.
    "operational_v1_5_3": ["tools/blackbox_continuation.py",
                           "tools/blackbox_v153_qualify.py",
                           "reports/DETACHED-OPERATION-v1.5.3.md",
                           "reports/OPERATIONAL-CONTINUATION-v1.5.3.md",
                           "results/continuation-decision-v1.5.2-001.json",
                           "results/checkpoint-lineage/checkpoint-v1.5.2-inventory.json",
                           "results/checkpoint-lineage/checkpoint-v1.5.2-seal.json",
                           "results/supervisor-qualification-v1.5.3.json",
                           "results/v1.5.3-corrections-qualification.json",
                           "results/v1.5.3-continuation-controls.json",
                           "results/scientific-invariance-v1.5.3.json",
                           "results/change-classification-v1.5.3.json"],
    # v1.5.4: operational safety only. No scientific-core artifact is listed
    # here and none changed.
    "operational_v1_5_4": ["tools/blackbox_launch_safety.py",
                           "tools/blackbox_v154_qualify.py",
                           "reports/OPERATIONAL-SAFETY-v1.5.4.md",
                           "reports/OPERATOR-REVIEW-v1.5.4.md",
                           "results/v1.5.4-safety-controls.json",
                           "results/supervisor-qualification-v1.5.4.json",
                           "results/v1.5.4-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.4.json",
                           "results/change-classification-v1.5.4.json"],
    # v1.5.5: operational qualification corrections only.
    "operational_v1_5_5": ["tools/blackbox_v155_qualify.py",
                           "reports/OPERATIONAL-QUALIFICATION-v1.5.5.md",
                           "reports/OPERATOR-REVIEW-v1.5.5.md",
                           "results/v1.5.5-integrated-faults.json",
                           "results/v1.5.5-safety-controls.json",
                           "results/supervisor-qualification-v1.5.5.json",
                           "results/v1.5.5-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.5.json",
                           "results/change-classification-v1.5.5.json"],
    # v1.5.6: one durability defect. Operational only.
    "operational_v1_5_6": ["reports/OPERATIONAL-DURABILITY-v1.5.6.md",
                           "reports/OPERATOR-REVIEW-v1.5.6.md",
                           "results/v1.5.6-integrated-faults.json",
                           "results/v1.5.6-safety-controls.json",
                           "results/supervisor-qualification-v1.5.6.json",
                           "results/v1.5.6-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.6.json",
                           "results/change-classification-v1.5.6.json"],
    # v1.5.7: crash-durability spend authority plus two reporting defects.
    # v1.5.8: the authoritative ledger reader fails closed on ambiguity.
    "operational_v1_5_8": ["reports/OPERATIONAL-LEDGER-VALIDATION-v1.5.8.md",
                           "reports/OPERATOR-REVIEW-v1.5.8.md",
                           "results/v1.5.8-integrated-faults.json",
                           "results/v1.5.8-safety-controls.json",
                           "results/supervisor-qualification-v1.5.8.json",
                           "results/v1.5.8-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.8.json",
                           "results/change-classification-v1.5.8.json"],
    "operational_v1_5_7": ["reports/OPERATIONAL-SPEND-AUTHORITY-v1.5.7.md",
                           "reports/OPERATOR-REVIEW-v1.5.7.md",
                           "results/v1.5.7-integrated-faults.json",
                           "results/v1.5.7-safety-controls.json",
                           "results/supervisor-qualification-v1.5.7.json",
                           "results/v1.5.7-corrections-qualification.json",
                           "results/scientific-invariance-v1.5.7.json",
                           "results/change-classification-v1.5.7.json"],
    "v1_5_5_amendment": [
        "releases/deviations/v1.5.4-superseded-candidate-001/"
        "DEVIATION-RECORD.json"],
    "v1_5_4_amendment": [
        "releases/deviations/campaign-v1.5.3-run-001/DEVIATION-RECORD.json",
        "releases/deviations/v1.5.4-superseded-candidate-001/"
        "DEVIATION-RECORD.json",
        "results/audit/operator-decisions-v0.3.json"],
    "v1_5_3_amendment": [
        "releases/deviations/v1.5.2-prospective-001/DEVIATION-RECORD.json"],
    "v1_5_2_amendment": [
        "releases/deviations/v1.5.2-prospective-001/DEVIATION-RECORD.json"],
    "v1_5_1_amendment": [
        "reports/OPERATIONAL-CORRECTIONS-v1.5.1.md",
        "releases/deviations/checkpoint-v1.5-run-001/DEVIATION-RECORD.json",
        "releases/deviations/v1.5.1-superseded-candidate-001/"
        "DEVIATION-RECORD.json"],
    "preserved_snapshots": ["releases/v1.0/SNAPSHOT-MANIFEST.json",
                            "releases/v1.1/SNAPSHOT-MANIFEST.json",
                            "releases/v1.2/SNAPSHOT-MANIFEST.json",
                            "releases/v1.3/SNAPSHOT-MANIFEST.json",
                            "releases/v1.4/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.1/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.2/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.3/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.4/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.5/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.6/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.7/SNAPSHOT-MANIFEST.json",
                            "releases/v1.5.8/SNAPSHOT-MANIFEST.json",
                            "releases/v1.6.0/SNAPSHOT-MANIFEST.json",
                            "releases/v1.6.1/SNAPSHOT-MANIFEST.json",
                            "releases/v1.6.2/SNAPSHOT-MANIFEST.json",
                            "releases/v1.6.3/SNAPSHOT-MANIFEST.json",
                            "releases/v1.6.4/SNAPSHOT-MANIFEST.json"],
    "acceptance_proposal": ["reports/SIMULATION-ACCEPTANCE-PROPOSAL-v1.0.md",
                            "fixtures/simulation-grid-v1.0.json",
                            "fixtures/seeds.json"],
    "failure_registry": ["results/failure-registry-v1.0.json",
                         "reports/FAILURE-TAXONOMY-COVERAGE-MATRIX-v1.0.md"],
    "ambiguity_register": ["reports/AMBIGUITY-REGISTER-v1.0.md"],
    # Contract section 4 requires checksums for the released report as well as
    # the harness, scenarios and expected answers.
    "reports": ["reports/QUALIFICATION-REPORT-v1.0.md",
                "reports/REPRODUCTION-v1.0.md",
                "reports/NO-SOURCE-ATTESTATION-COMPLETED-v1.0.md"],

    # v1.6.0: the reviewed ordered-evidence engine replaces the count-primary
    # target, and the harness consumes enumerated statuses rather than booleans.
    "ordered_evidence_path_v1_6_0": [
        "harness/ordered/__init__.py",
        "harness/ordered/canonical.py",
        "harness/ordered/statuses.py",
        "harness/ordered/grid.py",
        "harness/ordered/synthetic.py",
        "harness/ordered/family.py",
        "harness/ordered/events.py",
        "harness/ordered/engine_bridge.py",
        "harness/ordered/selfcheck.py",
        "harness/ordered/campaign.py",
        "harness/ordered/runner.py",
    ],
    "operational_v1_6_0": [
        "tools/vendor_engine.py",
        "tools/blackbox_target_server.py",
        "tools/build_target_manifest_v04.py",
        "tools/v160_qualify.py",
        "target-manifest-v0.4.json",
        "reports/DETACHED-OPERATION-v1.6.0.md",
        "reports/OPERATOR-REVIEW-v1.6.0.md",
    ],
    "v1_6_0_evidence": [
        "results/vendor-engine-v1.6.0.json",
        "results/v1.6.0-validity-configuration-feasibility.json",
        "results/v1.6.0-mechanical-corpus-probe.json",
        "results/v1.6.0-validity-corpus-probe.json",
        "results/v1.6.0-integration-not-ready-v0.1.json",
        "results/v1.6.0-v160-b-01-resolution-v0.1.json",
        "results/v1.6.0-self-qualification.json",
        "results/v1.6.0-separation-proofs.json",
        "results/v1.6.0-topology.json",
        "results/v1.6.0-scientific-core-baseline.json",
        "results/v1.6.0-ordered-dryrun.json",
        "reports/ordinal-profile-V1.6.0-INTEGRATION-NOT-READY-v0.1.md",
        "reports/ordinal-profile-legacy-review-gate-INDEPENDENT-REVIEW-v0.3.0-rc1.md",
        "results/audit/s1-od-r09-review-v0.1/s1-od-r09-independent-review-v0.1.json",
        "tools/v160_validity_feasibility.py",
        "tools/v160_mechanical_corpus_probe.py",
        "tools/v160_validity_corpus_probe.py",
    ],

    # v1.6.1: the reviewed rc2 engine, the versioned successor validity fixture,
    # and the characterization sealed under master seed 20260923.
    "operational_v1_6_1": [
        "tools/vendor_rc2.py",
        "tools/build_validity_fixture_v11.py",
        "tools/build_target_manifest_v05.py",
        "tools/v161_precharacterization_lock.py",
        "tools/v161_characterize.py",
        "tools/v161_qualify.py",
        "fixtures/validity-configurations-v1.1.json",
        "target-manifest-v0.5.json",
        "reports/DETACHED-OPERATION-v1.6.1.md",
        "reports/OPERATOR-REVIEW-v1.6.1.md",
    ],
    "v1_6_1_evidence": [
        "reports/ordinal-profile-legacy-review-gate-RC2-BOUNDED-DIFF-REVIEW-v0.1.txt",
        "results/vendor-engine-v1.6.1.json",
        "results/v1.6.1-precharacterization-lock.json",
        "results/v1.6.1-characterization.json",
        "results/v1.6.1-self-qualification.json",
        "results/v1.6.1-separation-proofs.json",
        "results/v1.6.1-topology.json",
        "results/v1.6.1-scientific-core-baseline.json",
    ],

    # v1.6.2: bounded corrective successor. Operational corrections only -- the
    # reviewed engine, contracts, thresholds, fixtures, populations and seed are
    # unchanged, and the first-look characterization reproduces exactly.
    "operational_v1_6_2": [
        "tools/v162_launch_sim.py",
        "tools/v162_reproduce_blockers.py",
        "tools/v162_acceptance.py",
        "tools/v162_characterize.py",
        "tools/v162_qualify.py",
        "reports/DETACHED-OPERATION-v1.6.2.md",
        "reports/OPERATOR-REVIEW-v1.6.2.md",
    ],
    "v1_6_2_evidence": [
        "results/v1.6.2-blocker-reproduction-v1.6.1.json",
        "results/v1.6.2-blocker-reproduction-worktree.json",
        "results/v1.6.2-acceptance-proofs.json",
        "results/v1.6.2-characterization.json",
        "results/v1.6.2-self-qualification.json",
        "results/v1.6.2-separation-proofs.json",
        "results/v1.6.2-topology.json",
        "results/v1.6.2-scientific-core-baseline.json",
    ],

    # v1.6.3: minimal corrective successor. Second-look subset validation and
    # cumulative merging only; no scientific change.
    "operational_v1_6_3": [
        "tools/v163_reproduce_blocker.py",
        "tools/v163_bounded_acceptance.py",
        "tools/v163_characterize.py",
        "tools/v163_qualify.py",
        "reports/DETACHED-OPERATION-v1.6.3.md",
        "reports/OPERATOR-REVIEW-v1.6.3.md",
    ],
    "v1_6_3_evidence": [
        "results/v1.6.3-blocker-reproduction-v1.6.2.json",
        "results/v1.6.3-blocker-reproduction-worktree.json",
        "results/v1.6.3-bounded-acceptance.json",
        "results/v1.6.3-characterization-aborted.json",
        "results/v1.6.3-characterization-ABORTED.log",
        "results/v1.6.3-self-qualification.json",
        "results/v1.6.3-separation-proofs.json",
        "results/v1.6.3-topology.json",
        "results/v1.6.3-scientific-core-baseline.json",
    ],

    # v1.6.4: minimal operational correction. D6 argument shape, and execution
    # authorization separated from release approval. No scientific change.
    "operational_v1_6_4": [
        "tools/v164_bounded_acceptance.py",
        "tools/v164_qualify.py",
        "reports/OPERATOR-REVIEW-v1.6.4.md",
    ],
    "v1_6_4_evidence": [
        "results/v1.6.4-bounded-acceptance.json",
        "results/v1.6.4-self-qualification.json",
        "results/v1.6.4-separation-proofs.json",
        "results/v1.6.4-topology.json",
        "results/v1.6.4-scientific-core-baseline.json",
    ],

    # v1.6.5: minimal operational correction. The forwarded-health assertion
    # now validates the frozen /health contract instead of a metadata field.
    "operational_v1_6_5": [
        "tools/v165_bounded_acceptance.py",
        "tools/v165_qualify.py",
        "reports/OPERATOR-REVIEW-v1.6.5.md",
    ],
    "v1_6_5_evidence": [
        "results/v1.6.5-bounded-acceptance.json",
        "results/v1.6.5-self-qualification.json",
        "results/v1.6.5-separation-proofs.json",
        "results/v1.6.5-topology.json",
        "results/v1.6.5-scientific-core-baseline.json",
    ],

    # v1.6.6: minimal operational correction. Live preflight validates the
    # attestation the launch already reserved and spent, instead of asking the
    # pre-launch "is there an unused attestation?" question mid-launch and
    # failing on its own correct spend record.
    "operational_v1_6_6": [
        "tools/v166_sandbox.py",
        "tools/v166_proofs.py",
        "tools/v166_bounded_acceptance.py",
        "tools/v166_qualify.py",
        "reports/OPERATOR-REVIEW-v1.6.6.md",
    ],
    "v1_6_6_evidence": [
        "results/v1.6.6-bounded-acceptance.json",
        "results/v1.6.6-self-qualification.json",
        "results/v1.6.6-separation-proofs.json",
        "results/v1.6.6-topology.json",
        "results/v1.6.6-scientific-core-baseline.json",
    ],
}


def _vendored_engine_paths():
    """Every file of the vendored reviewed engine, from its own manifest.

    Reading the vendored manifest rather than walking the tree means the release
    hashes exactly the files the reviewed release declares, so an extra or
    missing file is caught at freeze time.
    """
    manifest = os.path.join(ROOT, "vendor", "blackbox-ordinal-v0.3.0-rc2", "MANIFEST.sha256")
    if not os.path.isfile(manifest):
        return []
    paths = ["vendor/blackbox-ordinal-v0.3.0-rc2/MANIFEST.sha256"]
    with open(manifest, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            _, _, name = line.rstrip("\n").partition("  ")
            if name.startswith("./"):
                name = name[2:]
            paths.append("vendor/blackbox-ordinal-v0.3.0-rc2/%s" % name)
    return paths


ARTIFACT_GROUPS["vendored_reviewed_engine"] = _vendored_engine_paths()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_canonical(obj):
    """Canonical digest of a JSON-serializable object."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _scenario_paths():
    paths = []
    for family in ("clean", "archive", "anchors"):
        directory = os.path.join(ROOT, "fixtures", "scenarios", family)
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith(".json"):
                paths.append("fixtures/scenarios/%s/%s" % (family, name))
    return paths


def environment_manifest():
    """Environment and dependency manifest (contract §4)."""
    return {
        "manifest_version": "1.0",
        "python": {
            "version": sys.version.split()[0],
            "full_version": sys.version,
            "implementation": platform.python_implementation(),
            "executable_class": "system python3 (absolute path not recorded)",
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "third_party_dependencies": [],
        "dependency_policy": (
            "The harness, the exact oracle and the sound reference use the "
            "Python standard library ONLY. numpy, scipy and jsonschema are not "
            "installed in this environment and are not required. Exact "
            "arithmetic uses fractions.Fraction; binomial inversion and "
            "incomplete-beta-free Clopper-Pearson bounds are implemented "
            "directly from math.lgamma. This removes third-party numerical "
            "behaviour as a source of disagreement with the hand anchors."),
        "stdlib_modules_used": sorted([
            "contextlib", "copy", "fractions", "glob", "hashlib", "json",
            "math", "os", "platform", "random", "sys", "urllib"]),
        "randomness": {
            "generator": "random.Random (Mersenne Twister)",
            "deterministic_panels": "no sampling; frozen count vectors",
            "coverage_campaign": "seeded per replication, see fixtures/seeds.json",
        },
        "network": {
            "target_transport": "sandbox-filtering-proxy-to-loopback-http",
            "direct_loopback_socket_permitted": False,
            "bypass_variables_removed_in_requesting_child": ["NO_PROXY", "no_proxy"],
            "required_proxy_variables": ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"],
            "fails_closed_if_proxy_absent": True,
            "credentials_recorded": False,
        },
    }


def release_manifest(extra=None):
    """Hash every released artifact, grouped as amendment §6 requires."""
    groups = {}
    for group, paths in ARTIFACT_GROUPS.items():
        entries = {}
        for relative in paths:
            absolute = os.path.join(ROOT, relative)
            entries[relative] = (sha256_file(absolute)
                                 if os.path.isfile(absolute) else None)
        groups[group] = entries

    scenarios = {}
    for relative in _scenario_paths():
        scenarios[relative] = sha256_file(os.path.join(ROOT, relative))
    groups["named_scenarios_and_expected_answers"] = scenarios

    flat = {}
    for entries in groups.values():
        flat.update({k: v for k, v in entries.items() if v})

    manifest = {
        "release_id": RELEASE_ID,
        "harness_version": HARNESS_VERSION,
        "adapter_version": "1.0",
        "oracle_arithmetic": "exact rational (fractions.Fraction)",
        "artifact_groups": groups,
        "artifact_count": len(flat),
        "release_digest": sha256_canonical(flat),
        "environment": environment_manifest(),
    }
    if extra:
        manifest.update(extra)
    return manifest


# ---------------------------------------------------------------------------
# Phase gate
# ---------------------------------------------------------------------------

def _current_manifest_path():
    """The newest release manifest present, most recent version first."""
    for version in ("v1.6.6", "v1.6.5", "v1.6.4", "v1.6.3", "v1.6.2", "v1.6.1",
                    "v1.6.0",
                    "v1.5.8", "v1.5.7", "v1.5.6",
                    "v1.5.5", "v1.5.4",
                    "v1.5.3", "v1.5.2", "v1.5.1", "v1.5", "v1.4", "v1.3",
                    "v1.2", "v1.1", "v1.0"):
        path = os.path.join(ROOT, "results",
                            "harness-release-manifest-%s.json" % version)
        if os.path.isfile(path):
            return path
    return os.path.join(ROOT, "results", "harness-release-manifest-v1.2.json")


def verify_release_integrity(manifest_path=None):
    """Recompute every hashed artifact and compare against the manifest.

    Called by the campaign before any request of any kind. Its purpose is to
    make it impossible to run the real campaign against a tree that has drifted
    from the release the harness was qualified on -- a silent edit to an
    oracle, a scenario, or a decision rule between freeze and launch would
    otherwise be invisible in the campaign record.
    """
    path = manifest_path or _current_manifest_path()
    if not os.path.isfile(path):
        return {"intact": False, "artifacts_checked": 0,
                "mismatches": [], "missing": ["release manifest"],
                "release_digest": None}

    with open(path, "r") as handle:
        manifest = json.load(handle)

    mismatches, missing = [], []
    checked = 0
    for entries in manifest["artifact_groups"].values():
        for relative, digest in entries.items():
            if digest is None:
                continue
            absolute = os.path.join(ROOT, relative)
            if not os.path.isfile(absolute):
                missing.append(relative)
                continue
            checked += 1
            if sha256_file(absolute) != digest:
                mismatches.append(relative)

    return {
        "intact": not mismatches and not missing,
        "manifest": os.path.relpath(path, ROOT),
        "artifacts_checked": checked,
        "artifact_count": manifest.get("artifact_count"),
        "release_digest": manifest.get("release_digest"),
        "mismatches": sorted(mismatches),
        "missing": sorted(missing),
    }


APPROVAL_PATH = os.path.join(ROOT, "results",
                             "v%s-approval.json" % HARNESS_VERSION)


def v11_approval_record():
    """Operator approval of the campaign-runner corrections.

    v1.2 corrects the PASS-side inference family, so it requires its own
    explicit approval rather than inheriting v1.0's or v1.1's. A v1.1-era
    approval cannot satisfy this gate: the D6 enum values are v1.2-specific
    and the plan topology is validated. Absent the record, the gate blocks.
    """
    if not os.path.isfile(APPROVAL_PATH):
        return {"status": "PENDING",
                "detail": "v%s has not been reviewed or approved; see "
                          "reports/OPERATOR-REVIEW-v1.5.8.md"
                          % HARNESS_VERSION}
    with open(APPROVAL_PATH, "r") as handle:
        record = json.load(handle)
    return record.get("operator_approval", {"status": "PENDING"})


def approval_record_digest():
    """Canonical digest of the approval record, for the campaign stamp."""
    if not os.path.isfile(APPROVAL_PATH):
        return None
    return sha256_file(APPROVAL_PATH)


D6_SELECTED_PLAN = "corrected_two_look"


def d6_gate_status():
    """Validate decision D6 against the ACTIVE sealed ordered topology.

    The already-selected decision `corrected_two_look` is retained; this does
    not reopen D6. What changed in v1.6.2 is what it is validated against: the
    active 60-configuration / 153-stream plan with looks 500/2000 and critical
    values PASS [33,165] / FAIL [80,256], not the obsolete six-candidate /
    318-segment apparatus. Fails closed.
    """
    from . import campaign as campaign_module
    from .ordered import campaign as ordered_campaign
    from .ordered import family

    approval = v11_approval_record()
    raw = (approval.get("decisions") or {}).get("D6")
    selected = raw.get("plan") if isinstance(raw, dict) else raw
    if selected != D6_SELECTED_PLAN:
        return {"selected": selected or "NOT_SELECTED", "valid": False,
                "reason": "D6 selection is %r, expected the already selected %r"
                          % (selected, D6_SELECTED_PLAN),
                "budgets": None,
                "documented_enum": list(campaign_module.PLAN_ENUM)}

    plan = ordered_campaign.Plan()
    problems = []
    if family.SEGMENT_COUNT != 60:
        problems.append("configurations=%d" % family.SEGMENT_COUNT)
    if family.GATED_STREAM_COUNT != 153:
        problems.append("streams=%d" % family.GATED_STREAM_COUNT)
    if list(plan.looks) != [500, 2000]:
        problems.append("looks=%s" % list(plan.looks))
    if list(plan.pass_critical) != [33, 165]:
        problems.append("PASS=%s" % list(plan.pass_critical))
    if list(plan.fail_critical) != [80, 256]:
        problems.append("FAIL=%s" % list(plan.fail_critical))
    if problems:
        return {"selected": selected, "valid": False,
                "reason": "active plan mismatch: %s" % ", ".join(problems),
                "budgets": None,
                "documented_enum": list(campaign_module.PLAN_ENUM)}

    return {"selected": selected, "valid": True, "reason": None,
            "budgets": {
                "configurations": family.SEGMENT_COUNT,
                "gated_streams": family.GATED_STREAM_COUNT,
                "looks": list(plan.looks),
                "pass_critical_values": list(plan.pass_critical),
                "fail_critical_values": list(plan.fail_critical),
                "first_look_requests": family.FIRST_LOOK_REQUESTS,
                "worst_case_requests": family.WORST_CASE_REQUESTS},
            "validated_against": "active sealed ordered plan",
            "documented_enum": list(campaign_module.PLAN_ENUM)}


def approval_record():
    path = os.path.join(ROOT, "results", "failure-registry-v1.0.json")
    if not os.path.isfile(path):
        return {"status": "ABSENT"}
    with open(path, "r") as handle:
        registry = json.load(handle)
    return registry.get("operator_approval", {"status": "ABSENT"})


def phase_gate_status():
    """May the real black-box campaign begin?

    Amendment §6's conditions, plus two added in v1.1: the on-disk release must
    still match its manifest, and the v1.1 campaign-runner corrections must
    have been reviewed and explicitly approved.
    """
    release_path = _current_manifest_path()
    frozen = os.path.isfile(release_path)
    approval = approval_record()
    approved = approval.get("status") == "APPROVED"

    qualification_path = os.path.join(ROOT, "results",
                                      "self-qualification-v1.0.json")
    qualified = False
    if os.path.isfile(qualification_path):
        with open(qualification_path, "r") as handle:
            qualified = json.load(handle).get("verdict") == "HARNESS_SELF_QUALIFIED"

    integrity = verify_release_integrity()
    v11 = v11_approval_record()
    v11_approved = v11.get("status") == "APPROVED"

    blockers = []
    if not frozen:
        blockers.append("harness release manifest has not been written")
    if not qualified:
        blockers.append("two-sided self-qualification gate has not passed")
    if not approved:
        blockers.append(
            "operator has not approved the failure-taxonomy registry and the "
            "prospective simulation-acceptance proposal")
    if not integrity["intact"]:
        blockers.append(
            "on-disk release does not match its manifest (%d altered, %d "
            "missing)" % (len(integrity["mismatches"]),
                          len(integrity["missing"])))
    if not v11_approved:
        blockers.append(
            "release v%s has not been reviewed and explicitly approved by the "
            "operator (expected %s)"
            % (HARNESS_VERSION, os.path.relpath(APPROVAL_PATH, ROOT)))
    d6 = d6_gate_status()
    if not d6["valid"]:
        blockers.append(
            "operator decision D6 is not a valid selection against the frozen "
            "v1.2 topology: %s" % d6["reason"])

    return {
        "release_frozen": frozen,
        "self_qualified": qualified,
        # Two DIFFERENT approvals, historically conflated by these names:
        #   operator_approved  -- the original v1.0 approval of the failure
        #                         taxonomy and the acceptance proposal;
        #   current_release_approved -- the per-release approval record for
        #                         THIS release, which is what gates a launch.
        # Reporting only the first invites reading a frozen-but-unapproved
        # release as approved.
        "operator_approved": approved,
        "baseline_v1_0_approved": approved,
        "current_release_approved": v11_approved,
        "current_release_approval_path": os.path.relpath(APPROVAL_PATH, ROOT),
        "current_release_approval_exists": os.path.isfile(APPROVAL_PATH),
        "operator_approval_status": approval.get("status", "ABSENT"),
        "release_integrity_intact": integrity["intact"],
        "release_integrity": {key: integrity[key] for key in
                              ("artifacts_checked", "mismatches", "missing",
                               "release_digest")},
        "approval_status": v11.get("status", "PENDING"),
        "approval_record_digest": approval_record_digest(),
        "d6_decision_plan": d6["selected"],
        "d6_valid": d6["valid"],
        "d6_documented_enum": d6["documented_enum"],
        "d6_budgets": d6["budgets"],
        "real_engine_campaign_permitted": not blockers,
        "source_review_permitted": False,
        "source_review_note": (
            "Source review remains last and may not begin until the black-box "
            "campaign is complete and its exact target identity is preserved "
            "(contract §13, amendment §5)."),
        "blockers": blockers,
    }
