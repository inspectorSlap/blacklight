"""The v1.6.0 sixty-configuration roster at N=40.

Two sources, combined without editing either:

* the 53 preserved predecessor configurations, taken from
  ``harness.simulation.build_grid`` unchanged. Their population definitions are
  the ones bound into the C2 v0.5 manifest through
  ``fixtures/simulation-grid-v1.0.json``, whose digest is verified on load.
* the seven approved validity configurations, read from the reviewed release's
  ``fixtures/validity-configurations-v1.0.json`` and verified against the record
  digest the C2 manifest binds.

The predecessor generator numbers specimens in *preregistration role order*
(ordinal-profile..S6 -> sample-01, sample-02, sample-03, sample-04, sample-05, sample-06), while the reviewed
engine requires specimens in its own frozen roster order. This module keeps the
two explicitly separate and maps between them, so a distribution is never
silently attached to the wrong specimen.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os
from fractions import Fraction

from .. import roster as harness_roster
from .. import simulation as sim
from ..oracle import core, population as pop
from .canonical import canonical_sha256, sha256_hex
from .statuses import (
    CELLS,
    MECHANICAL_SPECIMENS,
    N,
    SEMANTIC_SPECIMENS,
    StatusContractViolation,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = os.path.join(ROOT, "vendor", "blackbox-ordinal-v0.3.0-rc2")

# v1.6.1 reads the versioned successor fixture. v1.0 is preserved unedited in
# the vendored engine release; GV-ORDER-A remains an immutable order-sensitivity
# anchor and is no longer claimed as a data-generating source.
VALIDITY_FIXTURE_PATH = os.path.join(ROOT, "fixtures", "validity-configurations-v1.1.json")
PREDECESSOR_VALIDITY_FIXTURE_PATH = os.path.join(
    VENDOR, "fixtures", "validity-configurations-v1.0.json")
ORDER_FIXTURE_PATH = os.path.join(VENDOR, "fixtures", "GV-ORDER-A.json")
PREDECESSOR_GRID_PATH = os.path.join(ROOT, "fixtures", "simulation-grid-v1.0.json")

# Digests bound by the C2 v0.5 manifest's derivation_inputs block.
PREDECESSOR_GRID_SHA256 = "13ce27cf2e612415ae3ec2331e992834579eefce25cc13ba547fb66231c19f97"
VALIDITY_FIXTURE_SHA256 = "33e4986972e8713703d49823559719e8dbb87826cc36ea0a6a36e3463bd81c7b"
VALIDITY_FIXTURE_RECORD_DIGEST = "c91154b8f382f048dec6f8b5479edba2ad1e29d5ca84eb9ca1b3d1a3846d1e73"
PREDECESSOR_VALIDITY_FIXTURE_SHA256 = (
    "cb4d86a511b1b7293eacc6187adbf416467bb42bb07459fcbdf83e842e2e1000")

# The approved score populations, named by predecessor configuration rather than
# inlined, so the runtime reads the same artifact the fixture declares.
SEMANTIC_POPULATION_CONFIGURATION = "G2-C1-POWER-P0-9_10"
MECHANICAL_POPULATION_CONFIGURATION = "G4-C2-POWER-IP-1_2"

EXPECTED_PREDECESSOR_COUNT = 53
EXPECTED_VALIDITY_COUNT = 7
EXPECTED_TOTAL = 60

PREDECESSOR_SOURCE = "PREDECESSOR_GRID_V1_0"
VALIDITY_SOURCE = "VALIDITY_FIXTURE_V1_1"

SCORE_MODE_SAMPLED = "POPULATION_SAMPLED"
SCORE_MODE_ORDER_FIXTURE = "REGISTERED_ORDER_FIXTURE"


class GridViolation(Exception):
    """Raised when the sixty-configuration roster cannot be built exactly."""


# ---------------------------------------------------------------------------
# Roster order mapping
# ---------------------------------------------------------------------------

def _role_index_map(engine_roster, harness_order):
    """Map engine roster position -> generator (role) index.

    Both rosters must contain exactly the same specimens; only the order
    differs. Any set difference is a contract violation, not a reordering.
    """
    if sorted(engine_roster) != sorted(harness_order):
        raise GridViolation(
            "engine roster %s and harness roster %s are not the same specimen set"
            % (list(engine_roster), list(harness_order)))
    position = {specimen: index for index, specimen in enumerate(harness_order)}
    return tuple(position[specimen] for specimen in engine_roster)


SEMANTIC_ENGINE_TO_ROLE = _role_index_map(SEMANTIC_SPECIMENS, harness_roster.SEMANTIC_ROSTER)
MECHANICAL_ENGINE_TO_ROLE = _role_index_map(MECHANICAL_SPECIMENS, harness_roster.MECHANICAL_ROSTER)


def semantic_role_for(engine_position):
    """Preregistration role id for an engine-order semantic position."""
    return harness_roster.SEMANTIC_ROLES[SEMANTIC_ENGINE_TO_ROLE[engine_position]]


def mechanical_role_for(engine_position):
    return harness_roster.MECHANICAL_ROLES[MECHANICAL_ENGINE_TO_ROLE[engine_position]]


# ---------------------------------------------------------------------------
# Fixture loading with digest verification
# ---------------------------------------------------------------------------

def _load_verified(path, expected_sha256, label):
    with open(path, "rb") as handle:
        raw = handle.read()
    observed = sha256_hex(raw)
    if observed != expected_sha256:
        raise GridViolation(
            "%s digest mismatch: expected %s, observed %s" % (label, expected_sha256, observed))
    return json.loads(raw.decode("utf-8"))


def load_validity_fixture():
    fixture = _load_verified(VALIDITY_FIXTURE_PATH, VALIDITY_FIXTURE_SHA256,
                             "validity configuration fixture")
    material = {k: v for k, v in fixture.items() if k != "record_digest"}
    observed = canonical_sha256(material)
    if observed != VALIDITY_FIXTURE_RECORD_DIGEST:
        raise GridViolation(
            "validity fixture record digest mismatch: expected %s, observed %s"
            % (VALIDITY_FIXTURE_RECORD_DIGEST, observed))
    return fixture


def load_order_fixture():
    with open(ORDER_FIXTURE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def verify_predecessor_grid_digest():
    """The predecessor grid fixture is a C2 v0.5 derivation input; pin it."""
    with open(PREDECESSOR_GRID_PATH, "rb") as handle:
        observed = sha256_hex(handle.read())
    if observed != PREDECESSOR_GRID_SHA256:
        raise GridViolation(
            "predecessor simulation grid digest mismatch: expected %s, observed %s"
            % (PREDECESSOR_GRID_SHA256, observed))
    return observed


# ---------------------------------------------------------------------------
# Configuration records
# ---------------------------------------------------------------------------

def _cells_by_name(distribution_map):
    """Normalize a generator specimen into engine cell order."""
    missing = [cell for cell in CELLS if cell not in distribution_map]
    if missing:
        raise GridViolation("specimen is missing cells %s" % missing)
    return {cell: list(distribution_map[cell]) for cell in CELLS}


def _predecessor_configuration(cell):
    """Convert one predecessor grid cell into a v1.6.0 configuration record."""
    semantic_by_light = []
    for light_index in range(3):
        if cell.get("per_light"):
            generator_specimens = cell["per_light"][light_index]
        else:
            generator_specimens = cell["semantic"]
        if len(generator_specimens) != len(SEMANTIC_SPECIMENS):
            raise GridViolation(
                "%s light %d declares %d semantic specimens, expected %d"
                % (cell["cell_id"], light_index, len(generator_specimens), len(SEMANTIC_SPECIMENS)))
        semantic_by_light.append([
            _cells_by_name(generator_specimens[SEMANTIC_ENGINE_TO_ROLE[position]])
            for position in range(len(SEMANTIC_SPECIMENS))
        ])
    if len(cell["mechanical"]) != len(MECHANICAL_SPECIMENS):
        raise GridViolation(
            "%s declares %d mechanical specimens, expected %d"
            % (cell["cell_id"], len(cell["mechanical"]), len(MECHANICAL_SPECIMENS)))
    mechanical = [
        _cells_by_name(cell["mechanical"][MECHANICAL_ENGINE_TO_ROLE[position]])
        for position in range(len(MECHANICAL_SPECIMENS))
    ]
    return {
        "configuration_id": cell["cell_id"],
        "source": PREDECESSOR_SOURCE,
        "family": cell["family"],
        "description": cell["description"],
        "primary": cell["primary"],
        "n": N,
        "score_mode": SCORE_MODE_SAMPLED,
        "semantic_score_mode": SCORE_MODE_SAMPLED,
        "mechanical_score_mode": SCORE_MODE_SAMPLED,
        "semantic_by_light": semantic_by_light,
        "mechanical_by_light": [mechanical, mechanical, mechanical],
        "validity_population": None,
        "population_targets": cell["population_targets"],
    }


def _population_from_configuration(predecessor_index, configuration_id, corpus):
    """Resolve an approved score population from a named predecessor configuration.

    The successor fixture names the population by predecessor configuration id
    rather than inlining distributions, so the runtime reads exactly the artifact
    the fixture declares, out of the digest-verified simulation grid.
    """
    cell = predecessor_index.get(configuration_id)
    if cell is None:
        raise GridViolation(
            "score population names configuration %r, which is not in the verified grid"
            % configuration_id)
    if corpus == "semantic":
        specimens, roster, mapping = cell["semantic"], SEMANTIC_SPECIMENS, SEMANTIC_ENGINE_TO_ROLE
    elif corpus == "mechanical":
        specimens, roster, mapping = cell["mechanical"], MECHANICAL_SPECIMENS, MECHANICAL_ENGINE_TO_ROLE
    else:
        raise GridViolation("unknown corpus %r" % corpus)
    if len(specimens) != len(roster):
        raise GridViolation(
            "%s %s corpus declares %d specimens, expected %d"
            % (configuration_id, corpus, len(specimens), len(roster)))
    return [_cells_by_name(specimens[mapping[position]]) for position in range(len(roster))]


def _empirical_distribution(scores):
    """Exact rational distribution implied by a registered ordered fixture cell."""
    counts = [0] * core.K
    for score in scores:
        counts[score - 1] += 1
    total = len(scores)
    return [Fraction(count, total) for count in counts]


def _validity_configuration(spec, predecessor_index):
    """Convert one approved validity configuration into a configuration record.

    Ordered score samples are drawn from the two approved predecessor score
    populations, which hold every score-effect chain in its registered
    alternative region so that validity remains the sole adverse component. The
    ``R_s``/``I_s`` indicators are generated independently by the already
    approved configuration-specific Bernoulli rules, unchanged from v1.0.
    """
    if spec.get("N") != N:
        raise GridViolation("%s declares N=%r, expected %d" % (spec["configuration_id"], spec.get("N"), N))

    # v1.6.1 score populations, read from the successor fixture's honest
    # declaration and resolved against the named predecessor configurations in
    # the digest-verified simulation grid. Nothing is inlined here, and
    # GV-ORDER-A is no longer claimed as a data-generating source; it remains an
    # immutable order-sensitivity anchor.
    declared = spec.get("score_population")
    if not isinstance(declared, dict):
        raise GridViolation("%s carries no score_population" % spec["configuration_id"])
    if declared.get("source", {}).get("sha256") != PREDECESSOR_GRID_SHA256:
        raise GridViolation(
            "%s does not name the verified simulation grid as its score source"
            % spec["configuration_id"])
    if declared.get("semantic", {}).get("predecessor_configuration") != SEMANTIC_POPULATION_CONFIGURATION:
        raise GridViolation(
            "%s does not name the approved semantic score population" % spec["configuration_id"])
    if declared.get("mechanical", {}).get("predecessor_configuration") != MECHANICAL_POPULATION_CONFIGURATION:
        raise GridViolation(
            "%s does not name the approved mechanical score population" % spec["configuration_id"])

    semantic_population = _population_from_configuration(
        predecessor_index, SEMANTIC_POPULATION_CONFIGURATION, "semantic")
    mechanical_population = _population_from_configuration(
        predecessor_index, MECHANICAL_POPULATION_CONFIGURATION, "mechanical")

    return {
        "configuration_id": spec["configuration_id"],
        "source": VALIDITY_SOURCE,
        "family": "VALIDITY",
        "description": spec["target"],
        "primary": True,
        "n": N,
        "score_mode": SCORE_MODE_SAMPLED,
        "semantic_score_mode": SCORE_MODE_SAMPLED,
        "mechanical_score_mode": SCORE_MODE_SAMPLED,
        "semantic_population_configuration": SEMANTIC_POPULATION_CONFIGURATION,
        "mechanical_population_configuration": MECHANICAL_POPULATION_CONFIGURATION,
        "score_population_source": declared["source"]["path"],
        "score_population_source_sha256": declared["source"]["sha256"],
        "semantic_by_light": [semantic_population] * 3,
        "mechanical_by_light": [mechanical_population] * 3,
        "validity_population": {
            "semantic": spec["semantic_population"],
            "mechanical": spec["mechanical_population"],
        },
        "generation_rule": spec["generation_rule"],
        "population_targets": {"validity_target": spec["target"]},
    }


def build_configurations():
    """The complete sixty-configuration roster, in a fixed deterministic order."""
    verify_predecessor_grid_digest()
    predecessor = sim.build_grid()
    if len(predecessor) != EXPECTED_PREDECESSOR_COUNT:
        raise GridViolation(
            "predecessor grid has %d configurations, expected %d"
            % (len(predecessor), EXPECTED_PREDECESSOR_COUNT))

    fixture = load_validity_fixture()
    order_fixture = load_order_fixture()
    validity = fixture["configurations"]
    if len(validity) != EXPECTED_VALIDITY_COUNT:
        raise GridViolation(
            "validity fixture has %d configurations, expected %d"
            % (len(validity), EXPECTED_VALIDITY_COUNT))

    predecessor_index = {cell["cell_id"]: cell for cell in predecessor}
    configurations = [_predecessor_configuration(cell) for cell in predecessor]
    configurations.extend(
        _validity_configuration(spec, predecessor_index) for spec in validity)

    if len(configurations) != EXPECTED_TOTAL:
        raise GridViolation("roster has %d configurations, expected %d"
                            % (len(configurations), EXPECTED_TOTAL))
    identifiers = [item["configuration_id"] for item in configurations]
    if len(set(identifiers)) != len(identifiers):
        duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
        raise GridViolation("duplicate configuration identifiers: %s" % duplicates)
    return configurations


def configuration_index():
    return {item["configuration_id"]: item for item in build_configurations()}


# ---------------------------------------------------------------------------
# Independent population truth
# ---------------------------------------------------------------------------

def population_truth(configuration):
    """Exact population P0_bar, I_P_bar and Q_bar per light.

    Computed by the harness's own exact-rational oracle from the configuration's
    declared populations. The engine is never consulted.
    """
    truths = []
    for light_index in range(3):
        specimens = configuration["semantic_by_light"][light_index]
        generator_order = [
            specimens[position]
            for position in sorted(range(len(specimens)),
                                   key=lambda p: SEMANTIC_ENGINE_TO_ROLE[p])
        ]
        truth = pop.light_truth(generator_order)
        truths.append({
            "P0_bar": truth["P0_bar"],
            "I_P_bar": truth["I_P_bar"],
            "Q_bar": truth["Q_bar"],
        })
    return truths


def mechanical_population_truth(configuration):
    """Exact population I_P_bar per light for the mechanical corpus."""
    truths = []
    for light_index in range(3):
        specimens = configuration["mechanical_by_light"][light_index]
        generator_order = [
            specimens[position]
            for position in sorted(range(len(specimens)),
                                   key=lambda p: MECHANICAL_ENGINE_TO_ROLE[p])
        ]
        truth = pop.light_truth(generator_order)
        truths.append({"I_P_bar": truth["I_P_bar"]})
    return truths


def describe():
    """A digest-stable description of the roster, for release evidence."""
    configurations = build_configurations()
    rows = []
    for item in configurations:
        rows.append({
            "configuration_id": item["configuration_id"],
            "source": item["source"],
            "family": item["family"],
            "n": item["n"],
            "score_mode": item["score_mode"],
            "has_validity_population": item["validity_population"] is not None,
        })
    return {
        "configuration_count": len(rows),
        "predecessor_count": sum(1 for r in rows if r["source"] == PREDECESSOR_SOURCE),
        "validity_count": sum(1 for r in rows if r["source"] == VALIDITY_SOURCE),
        "n": N,
        "predecessor_grid_sha256": PREDECESSOR_GRID_SHA256,
        "validity_fixture_sha256": VALIDITY_FIXTURE_SHA256,
        "semantic_engine_to_role_index": list(SEMANTIC_ENGINE_TO_ROLE),
        "mechanical_engine_to_role_index": list(MECHANICAL_ENGINE_TO_ROLE),
        "configurations": rows,
    }
