"""Deterministic synthetic C2/C4 qualification evidence.

Authority: the approved synthetic-qualification clarification v0.1
(SHA-256 ``774f5076...52e52b``) and its approval record (``51f1984b...bfc79``),
which are bound to the finite method contract, the implementation approval, and
the reviewed engine release manifest.

Two evidence contexts exist and they never mix:

* **Operational ordinal-profile acquisition** -- real append-only attempt archive, through the
  reviewed engine's own normalizer and its 48/16 replacement budget gates, to
  ordered input. This module does not participate in that path at all.
* **Synthetic C2/C4 qualification** -- deterministic synthetic evidence directly
  to ordered input, as method contract section 8.1(1) expressly permits
  ("accept the ordered vectors directly, or a digest-bound archive reference
  resolving to them"). Operational replacement budgets do not apply, because no
  evaluator request, replacement call, or study cost is created.

The identity chain is not weakened by the direct route. Every replication
deterministically materializes a complete canonical synthetic attempt archive,
including every virtual attempt in order, and the SHA-256 of that archive is
what goes into ``attempt_archive_sha256``. The archive is reconstructable from
the stored generator/version/seed bindings alone, and every reconstruction is
reverified against the recorded digest.

Nothing here performs inference. The single scientific function remains
``ordinal_engine.engine.analyze``.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import random
from fractions import Fraction

from ..oracle import core
from .canonical import canonical_sha256
from .grid import (
    MECHANICAL_ENGINE_TO_ROLE,
    SCORE_MODE_ORDER_FIXTURE,
    SCORE_MODE_SAMPLED,
    SEMANTIC_ENGINE_TO_ROLE,
    mechanical_role_for,
    semantic_role_for,
)
from .statuses import (
    CELLS,
    LIGHTS,
    MECHANICAL_SPECIMENS,
    N,
    SEMANTIC_SPECIMENS,
)

# ---------------------------------------------------------------------------
# Registered identity of this evidence context
# ---------------------------------------------------------------------------

EVIDENCE_KIND = "SYNTHETIC_QUALIFICATION_NOT_S1_ACQUISITION"
ACQUISITION_EVIDENCE_KIND = "S1_ACQUISITION"
GENERATOR = "blackbox-ordinal-synthetic-qualification"
GENERATOR_VERSION = "1.0"
SYNTHETIC_ARCHIVE_SCHEMA = "blackbox.ordinal.synthetic-qualification-archive.v0.1"
ORDERED_SCHEMA = "blackbox.ordinal.ordered-analysis-input.v0.1"

# Master seed sealed prospectively by the v1.6.1 correction authority section 3,
# before any successor characterization. Never selected or tuned after
# inspecting successor results.
SYNTHETIC_MASTER_SEED = 20260923

ANALYSIS_ID_PREFIX = "SYNTH"

BUDGET_NOTE = (
    "Operational replacement budgets (48 campaign-wide, 16 per light) are NOT "
    "applicable to this synthetic Monte Carlo stress case. No evaluator request, "
    "replacement call, or study cost is created. They remain fully enforced for "
    "every real ordinal-profile acquisition archive."
)

# Indicator-to-attempt construction, clarification section 4.
CONSTRUCTION = {
    (0, 0): ("ordinary canonical scored response", None),
    (1, 0): ("canonical schema-valid scored refusal", None),
    (0, 1): ("pre-canonical S1_SCHEMA_INVALID then canonical scored response", "S1_SCHEMA_INVALID"),
    (1, 1): ("pre-canonical S2_REFUSAL_WITHOUT_SCORE then canonical scored response",
             "S2_REFUSAL_WITHOUT_SCORE"),
}


class SyntheticEvidenceError(Exception):
    """Raised when synthetic evidence cannot be produced or reverified exactly."""


# ---------------------------------------------------------------------------
# Deterministic seeds
# ---------------------------------------------------------------------------

def _digest_seed(material):
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def configuration_seed(configuration_id, master=SYNTHETIC_MASTER_SEED):
    """Stable per-configuration seed, as a hex string for the evidence record."""
    return _digest_seed("%d|%s|%s|%s" % (master, configuration_id, GENERATOR, GENERATOR_VERSION))


def replication_seed(configuration_id, replication, stream, master=SYNTHETIC_MASTER_SEED):
    """Per-replication seed for one named draw stream."""
    base = configuration_seed(configuration_id, master)
    return _digest_seed("%s|rep=%d|%s" % (base, replication, stream))


def _rng(seed_hex):
    return random.Random(int(seed_hex[:16], 16))


# ---------------------------------------------------------------------------
# Draws
# ---------------------------------------------------------------------------

def sample_scores(distribution, n, rng):
    """Draw ``n`` ordered categories from an exact rational distribution.

    Uses the same threshold walk as the frozen predecessor generator, so the
    marginal law of the draw is unchanged; only the ordered sequence is retained
    rather than collapsed into counts.
    """
    thresholds = []
    total = Fraction(0)
    for index, mass in enumerate(distribution):
        total += Fraction(mass)
        thresholds.append((float(total), index))
    if total != 1:
        raise SyntheticEvidenceError("distribution does not sum to one")
    scores = []
    for _ in range(n):
        draw = rng.random()
        for threshold, index in thresholds:
            if draw < threshold:
                scores.append(index + 1)
                break
        else:
            scores.append(thresholds[-1][1] + 1)
    return scores


def _counts(scores):
    result = [0] * core.K
    for score in scores:
        result[score - 1] += 1
    return result


def _draw_scores(configuration, replication):
    """Ordered score vectors keyed (light, group, engine_position, cell).

    Every corpus samples from a registered population in the digest-verified
    simulation grid. For the seven validity configurations those populations are
    the approved predecessor configurations ``G2-C1-POWER-P0-9_10`` (semantic)
    and ``G4-C2-POWER-IP-1_2`` (mechanical), which hold every score-effect chain
    in its registered alternative region.
    """
    scores = {}
    rng = _rng(replication_seed(configuration["configuration_id"], replication, "scores"))
    for light_index, light in enumerate(LIGHTS):
        for group, roster, by_light, mode_key, fixture_key in (
            ("semantic", SEMANTIC_SPECIMENS, configuration["semantic_by_light"],
             "semantic_score_mode", "semantic_scores"),
            ("mechanical", MECHANICAL_SPECIMENS, configuration["mechanical_by_light"],
             "mechanical_score_mode", "mechanical_scores"),
        ):
            mode = configuration[mode_key]
            if mode == SCORE_MODE_ORDER_FIXTURE:
                fixture = configuration[fixture_key]
                for position in range(len(roster)):
                    for cell in CELLS:
                        vector = list(fixture[position][cell])
                        if len(vector) != N:
                            raise SyntheticEvidenceError(
                                "registered order fixture cell is not length %d" % N)
                        scores[(light, group, position, cell)] = vector
            elif mode == SCORE_MODE_SAMPLED:
                specimens = by_light[light_index]
                for position in range(len(roster)):
                    for cell in CELLS:
                        scores[(light, group, position, cell)] = sample_scores(
                            specimens[position][cell], N, rng)
            else:
                raise SyntheticEvidenceError("unknown score mode %r" % mode)
    return scores


def _draw_indicators(configuration, replication):
    """``R_s``/``I_s`` keyed (light, group, engine_position, cell, t).

    Predecessor configurations carry clean validity throughout, exactly as the
    predecessor payload did. Validity configurations draw independent fixed
    Bernoulli indicators by prospectively indexed slot, which is verbatim the
    ``generation_rule`` the approved fixture states.
    """
    indicators = {}
    population = configuration["validity_population"]
    if population is None:
        for light in LIGHTS:
            for group, roster in (("semantic", SEMANTIC_SPECIMENS),
                                  ("mechanical", MECHANICAL_SPECIMENS)):
                for position in range(len(roster)):
                    for cell in CELLS:
                        for t in range(N):
                            indicators[(light, group, position, cell, t)] = (0, 0)
        return indicators

    rng = _rng(replication_seed(configuration["configuration_id"], replication, "indicators"))
    for light in LIGHTS:
        for group, roster in (("semantic", SEMANTIC_SPECIMENS),
                              ("mechanical", MECHANICAL_SPECIMENS)):
            rates = population[group]
            for position in range(len(roster)):
                for cell in CELLS:
                    refusal_rate = rates["refusal"][cell]
                    invalid_rate = rates["invalid"][cell]
                    for t in range(N):
                        r_value = 1 if rng.random() < refusal_rate else 0
                        i_value = 1 if rng.random() < invalid_rate else 0
                        indicators[(light, group, position, cell, t)] = (r_value, i_value)
    return indicators


# ---------------------------------------------------------------------------
# Canonical synthetic attempt archive
# ---------------------------------------------------------------------------

def slot_id(light, specimen, cell, t):
    return "ordinal-profile|%s|%s|%s|t=%02d" % (light, specimen, cell, t)


def attempt_id(expected_slot_id, attempt_index):
    return "%s|a=%d" % (expected_slot_id, attempt_index)


def _stamps(configuration_id, seed_hex):
    return {
        "lens_id": "SYNTHETIC-QUALIFICATION",
        "provider": "SYNTHETIC-DETERMINISTIC-GENERATOR",
        "requested_model": "%s-%s" % (GENERATOR, GENERATOR_VERSION),
        "served_model": "%s-%s" % (GENERATOR, GENERATOR_VERSION),
        "key_id": "%s|%s" % (configuration_id, seed_hex[:16]),
    }


def _slot_attempts(light, group, specimen, cell, t, score, r_value, i_value, stamps):
    """The virtual attempt sequence realizing (R_s, I_s), clarification section 4."""
    key = (int(r_value), int(i_value))
    if key not in CONSTRUCTION:
        raise SyntheticEvidenceError("indicators must be 0/1, received %r" % (key,))
    _, pre_canonical_outcome = CONSTRUCTION[key]
    sid = slot_id(light, specimen, cell, t)
    attempts = []
    index = 0
    if pre_canonical_outcome is not None:
        attempts.append({
            "attempt_id": attempt_id(sid, index), "slot_id": sid, "light_id": light,
            "specimen_id": specimen, "specimen_group": group, "cell": cell, "t": t,
            "attempt_index": index, "outcome_code": pre_canonical_outcome,
            "refusal": False, "score": None, "rationale": None, "stamps": dict(stamps),
        })
        index += 1
    # The canonical attempt keeps the original preassigned t and is always last;
    # no post-canonical attempt is ever produced.
    attempts.append({
        "attempt_id": attempt_id(sid, index), "slot_id": sid, "light_id": light,
        "specimen_id": specimen, "specimen_group": group, "cell": cell, "t": t,
        "attempt_index": index, "outcome_code": "OK_SCORED",
        "refusal": bool(key == (1, 0)), "score": int(score),
        "rationale": "synthetic qualification slot", "stamps": dict(stamps),
    })
    return attempts


def build_expanded_archive(configuration, replication, master=SYNTHETIC_MASTER_SEED):
    """Materialize the complete canonical synthetic attempt archive."""
    configuration_id = configuration["configuration_id"]
    seed_hex = configuration_seed(configuration_id, master)
    scores = _draw_scores(configuration, replication)
    indicators = _draw_indicators(configuration, replication)
    stamps = _stamps(configuration_id, seed_hex)

    attempts = []
    for light in LIGHTS:
        for group, roster in (("semantic", SEMANTIC_SPECIMENS),
                              ("mechanical", MECHANICAL_SPECIMENS)):
            for position, specimen in enumerate(roster):
                for cell in CELLS:
                    vector = scores[(light, group, position, cell)]
                    for t in range(N):
                        r_value, i_value = indicators[(light, group, position, cell, t)]
                        attempts.extend(_slot_attempts(
                            light, group, specimen, cell, t, vector[t], r_value, i_value, stamps))

    archive = {
        "schema_version": SYNTHETIC_ARCHIVE_SCHEMA,
        "evidence_kind": EVIDENCE_KIND,
        "operational_replacement_budgets_applicable": False,
        "operational_replacement_budget_note": BUDGET_NOTE,
        "bindings": synthetic_bindings(configuration, replication, master),
        "attempts": attempts,
    }
    return archive


def synthetic_bindings(configuration, replication, master=SYNTHETIC_MASTER_SEED):
    """Every binding the clarification requires, as exact strings."""
    from .family import C2_MANIFEST_DIGEST, C4_RECORD_DIGEST
    from .statuses import C1_CONTRACT_DIGEST

    configuration_id = configuration["configuration_id"]
    return {
        "evidence_kind": EVIDENCE_KIND,
        "reviewed_engine_release_manifest_sha256":
            "4a7c42f51071f0d19016e38617ab36a72c3f7a50ccf4841d24184f76103e860a",
        "c1_contract_digest": C1_CONTRACT_DIGEST,
        "c2_manifest_digest": C2_MANIFEST_DIGEST,
        "c4_record_digest": C4_RECORD_DIGEST,
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "configuration_id": configuration_id,
        "configuration_source": configuration["source"],
        "semantic_score_mode": configuration["semantic_score_mode"],
        "mechanical_score_mode": configuration["mechanical_score_mode"],
        # Name the population actually used. GV-ORDER-A is never claimed here.
        "semantic_score_population": configuration.get(
            "semantic_population_configuration", configuration["configuration_id"]),
        "mechanical_score_population": configuration.get(
            "mechanical_population_configuration", configuration["configuration_id"]),
        "score_population_source": configuration.get(
            "score_population_source", "fixtures/simulation-grid-v1.0.json"),
        "score_population_source_sha256": configuration.get(
            "score_population_source_sha256",
            "13ce27cf2e612415ae3ec2331e992834579eefce25cc13ba547fb66231c19f97"),
        "master_seed": str(master),
        "configuration_seed": configuration_seed(configuration_id, master),
        "score_stream_seed": replication_seed(configuration_id, replication, "scores", master),
        "indicator_stream_seed": replication_seed(configuration_id, replication, "indicators", master),
        "replication_index": str(replication),
        "n": str(N),
        "lights": ",".join(LIGHTS),
        "cells": ",".join(CELLS),
        "semantic_specimens": ",".join(SEMANTIC_SPECIMENS),
        "mechanical_specimens": ",".join(MECHANICAL_SPECIMENS),
        "operational_replacement_budgets_applicable": "false",
    }


def archive_digest(expanded_archive):
    """SHA-256 over the canonical expanded synthetic attempt archive."""
    return canonical_sha256(expanded_archive)


# ---------------------------------------------------------------------------
# Ordered input
# ---------------------------------------------------------------------------

def _corpus_payload(light, group, roster, scores, indicators):
    """Build one corpus exactly as the reviewed normalizer's projection does."""
    specimens = []
    r_overall, i_overall = [], []
    r_diff_b, r_diff_a, i_diff_b, i_diff_a = [], [], [], []
    slot_rows = []
    for position, specimen in enumerate(roster):
        cells = {}
        for cell in CELLS:
            vector = list(scores[(light, group, position, cell)])
            cells[cell] = {"scores": vector, "counts": _counts(vector)}
            for t in range(N):
                r_value, i_value = indicators[(light, group, position, cell, t)]
                r_overall.append(r_value)
                i_overall.append(i_value)
                slot_rows.append({
                    "slot_id": slot_id(light, specimen, cell, t),
                    "R": r_value, "I": i_value,
                })
        specimens.append({"id": specimen, "cells": cells})
        for t in range(N):
            r_diff_b.append(indicators[(light, group, position, "00", t)][0]
                            - indicators[(light, group, position, "0B", t)][0])
            r_diff_a.append(indicators[(light, group, position, "A0", t)][0]
                            - indicators[(light, group, position, "AB", t)][0])
            i_diff_b.append(indicators[(light, group, position, "00", t)][1]
                            - indicators[(light, group, position, "0B", t)][1])
            i_diff_a.append(indicators[(light, group, position, "A0", t)][1]
                            - indicators[(light, group, position, "AB", t)][1])

    ordered_projection = [
        {"id": item["id"], "cells": {cell: item["cells"][cell]["scores"] for cell in CELLS}}
        for item in specimens
    ]
    count_projection = [
        {"id": item["id"], "cells": {cell: item["cells"][cell]["counts"] for cell in CELLS}}
        for item in specimens
    ]
    return {
        "structural_state": "ELIGIBLE",
        "structural_reason_codes": [],
        "specimens": specimens,
        "validity_indicators": {
            "R_overall": r_overall, "R_diff_B": r_diff_b, "R_diff_A": r_diff_a,
            "I_overall": i_overall, "I_diff_B": i_diff_b, "I_diff_A": i_diff_a,
        },
        "slot_validity_rows": slot_rows,
        "ordered_observation_sha256": canonical_sha256(ordered_projection),
        "recomputed_count_sha256": canonical_sha256(count_projection),
    }


def analysis_id(configuration_id, replication):
    return "%s|%s|N=%d|rep=%d" % (ANALYSIS_ID_PREFIX, configuration_id, N, replication)


def build_ordered_input(configuration, replication, master=SYNTHETIC_MASTER_SEED):
    """Build the reviewed engine's ordered input and its synthetic archive.

    Returns ``(ordered_input, expanded_archive)``. The ordered input's
    ``attempt_archive_sha256`` is the canonical digest of the expanded archive.
    """
    configuration_id = configuration["configuration_id"]
    scores = _draw_scores(configuration, replication)
    indicators = _draw_indicators(configuration, replication)
    expanded = build_expanded_archive(configuration, replication, master)
    digest = archive_digest(expanded)

    payload = {
        "schema_version": ORDERED_SCHEMA,
        "analysis_id": analysis_id(configuration_id, replication),
        "campaign_id": "blackbox-ordinal-v1.6.0-synthetic-qualification",
        "roster_seed": configuration_seed(configuration_id, master),
        "bindings": synthetic_bindings(configuration, replication, master),
        "attempt_archive_sha256": digest,
        "lights": [
            {
                "id": light,
                "semantic": _corpus_payload(light, "semantic", SEMANTIC_SPECIMENS, scores, indicators),
                "mechanical": _corpus_payload(light, "mechanical", MECHANICAL_SPECIMENS, scores, indicators),
            }
            for light in LIGHTS
        ],
    }
    payload["ordered_input_sha256"] = canonical_sha256(payload)
    return payload, expanded


# ---------------------------------------------------------------------------
# Independent reverification -- fails closed
# ---------------------------------------------------------------------------

def verify_replication(configuration, replication, ordered_input, expanded_archive,
                       master=SYNTHETIC_MASTER_SEED):
    """Reconstruct from seeds alone and reverify every binding and digest.

    Fails closed on any reconstruction, score, indicator, paired-difference,
    count, or digest mismatch. Returns the verification record.
    """
    problems = []

    rebuilt_input, rebuilt_archive = build_ordered_input(configuration, replication, master)

    if canonical_sha256(rebuilt_archive) != canonical_sha256(expanded_archive):
        problems.append("expanded synthetic archive is not deterministically reconstructable")
    if canonical_sha256(rebuilt_input) != canonical_sha256(ordered_input):
        problems.append("ordered input is not deterministically reconstructable")

    recorded_digest = ordered_input.get("attempt_archive_sha256")
    recomputed_digest = archive_digest(expanded_archive)
    if recorded_digest != recomputed_digest:
        problems.append("attempt_archive_sha256 %r does not match the expanded archive digest %r"
                        % (recorded_digest, recomputed_digest))

    material = {k: v for k, v in ordered_input.items() if k != "ordered_input_sha256"}
    if ordered_input.get("ordered_input_sha256") != canonical_sha256(material):
        problems.append("ordered_input_sha256 does not match the payload it labels")

    bindings = ordered_input.get("bindings")
    if not isinstance(bindings, dict) or bindings.get("evidence_kind") != EVIDENCE_KIND:
        problems.append("ordered input is not bound to the synthetic evidence kind")
    if expanded_archive.get("evidence_kind") != EVIDENCE_KIND:
        problems.append("expanded archive is not bound to the synthetic evidence kind")
    if expanded_archive.get("operational_replacement_budgets_applicable") is not False:
        problems.append("expanded archive does not record budget non-applicability")

    # Recompute the indicators and scores directly from the archive's attempts and
    # require them to agree with the ordered input the engine will consume.
    derived_scores, derived_indicators = project_archive(expanded_archive)
    for light in LIGHTS:
        payload_light = next((item for item in ordered_input["lights"] if item["id"] == light), None)
        if payload_light is None:
            problems.append("ordered input is missing light %s" % light)
            continue
        for group, roster in (("semantic", SEMANTIC_SPECIMENS),
                              ("mechanical", MECHANICAL_SPECIMENS)):
            corpus = payload_light[group]
            expected = _corpus_payload(light, group, roster, derived_scores, derived_indicators)
            for field in ("validity_indicators", "slot_validity_rows",
                          "ordered_observation_sha256", "recomputed_count_sha256", "specimens"):
                if corpus[field] != expected[field]:
                    problems.append("%s.%s %s disagrees with the synthetic archive projection"
                                    % (light, group, field))
            for specimen in corpus["specimens"]:
                for cell in CELLS:
                    record = specimen["cells"][cell]
                    if record["counts"] != _counts(record["scores"]):
                        problems.append("%s.%s.%s.%s redundant counts disagree with ordered scores"
                                        % (light, group, specimen["id"], cell))

    if problems:
        raise SyntheticEvidenceError("; ".join(problems))
    return {
        "verified": True,
        "analysis_id": ordered_input["analysis_id"],
        "attempt_archive_sha256": recomputed_digest,
        "ordered_input_sha256": ordered_input["ordered_input_sha256"],
        "reconstructable_from_seeds": True,
        "checks": [
            "expanded archive deterministically reconstructed from seeds",
            "ordered input deterministically reconstructed from seeds",
            "attempt_archive_sha256 recomputed over the expanded archive",
            "ordered_input_sha256 recomputed over its own payload",
            "ordered scores, R/I vectors, paired differences and redundant counts "
            "reprojected from the archive attempts and compared",
        ],
    }


def project_archive(expanded_archive):
    """Recompute ordered scores and R/I indicators from the archive's attempts.

    This applies the approved method's section 4 indicator definitions directly
    to the virtual attempt sequence, independently of how the archive was built.
    """
    grouped = {}
    for attempt in expanded_archive["attempts"]:
        key = (attempt["light_id"], attempt["specimen_group"], attempt["specimen_id"],
               attempt["cell"], attempt["t"])
        grouped.setdefault(key, []).append(attempt)

    scores, indicators = {}, {}
    for light in LIGHTS:
        for group, roster in (("semantic", SEMANTIC_SPECIMENS),
                              ("mechanical", MECHANICAL_SPECIMENS)):
            for position, specimen in enumerate(roster):
                for cell in CELLS:
                    vector = []
                    for t in range(N):
                        ordered = sorted(grouped.get((light, group, specimen, cell, t), []),
                                         key=lambda item: item["attempt_index"])
                        if not ordered:
                            raise SyntheticEvidenceError(
                                "synthetic archive is missing slot %s"
                                % slot_id(light, specimen, cell, t))
                        canonical_position = None
                        for index, attempt in enumerate(ordered):
                            if attempt["outcome_code"] == "OK_SCORED" and canonical_position is None:
                                canonical_position = index
                        if canonical_position is None:
                            raise SyntheticEvidenceError(
                                "synthetic archive slot %s has no canonical scored attempt"
                                % slot_id(light, specimen, cell, t))
                        if canonical_position != len(ordered) - 1:
                            raise SyntheticEvidenceError(
                                "synthetic archive slot %s carries a post-canonical attempt"
                                % slot_id(light, specimen, cell, t))
                        prefix = ordered[:canonical_position]
                        r_value = int(any(item["refusal"]
                                          or item["outcome_code"] == "S2_REFUSAL_WITHOUT_SCORE"
                                          for item in ordered))
                        i_value = int(any(item["outcome_code"] in
                                          {"S1_SCHEMA_INVALID", "S2_REFUSAL_WITHOUT_SCORE"}
                                          for item in prefix))
                        indicators[(light, group, position, cell, t)] = (r_value, i_value)
                        vector.append(ordered[canonical_position]["score"])
                    scores[(light, group, position, cell)] = vector
    return scores, indicators


# ---------------------------------------------------------------------------
# Separation: presenting synthetic evidence as if it were real acquisition
# ---------------------------------------------------------------------------

def as_acquisition_archive(expanded_archive):
    """Wrap the virtual attempts as a real ordinal-profile acquisition archive.

    Used only by the mandatory separation proof, which demonstrates that the
    very same high-invalidity virtual archive is refused by the unchanged
    operational replacement-budget gate when it is offered as acquisition
    evidence. Nothing in the qualification path calls this.
    """
    bindings = expanded_archive["bindings"]
    return {
        "schema_version": "blackbox.ordinal.attempt-archive.v0.2",
        "archive_id": "ACQUISITION-SEPARATION-PROOF|%s|rep=%s" % (
            bindings["configuration_id"], bindings["replication_index"]),
        "config": {
            "expected_n": N, "r_max": 4, "timeout_seconds": 120,
            "backoff_seconds": [1, 2, 4, 8],
            "campaign_replacement_budget": 48,
            "per_light_replacement_budget": 16,
            "campaign_id": "separation-proof",
            "roster_seed": bindings["configuration_seed"],
            "bindings": {"separation_proof": "true"},
        },
        "attempts": [dict(attempt) for attempt in expanded_archive["attempts"]],
    }


def is_synthetic_analysis_id(identifier):
    """True only for identifiers this module mints."""
    return isinstance(identifier, str) and identifier.startswith(ANALYSIS_ID_PREFIX + "|")


def assert_not_synthetic(payload, context):
    """Refuse synthetic evidence wherever real acquisition is required.

    Called by the real acquisition path so that no real ordinal-profile launcher can mark
    evidence as synthetic and no synthetic payload can enter acquisition.
    """
    if not isinstance(payload, dict):
        return
    bindings = payload.get("bindings")
    if isinstance(bindings, dict) and bindings.get("evidence_kind") == EVIDENCE_KIND:
        raise SyntheticEvidenceError(
            "%s received synthetic qualification evidence; the real acquisition path "
            "does not accept it" % context)
    if is_synthetic_analysis_id(payload.get("analysis_id")):
        raise SyntheticEvidenceError(
            "%s received a synthetic analysis identifier" % context)
    if payload.get("evidence_kind") == EVIDENCE_KIND:
        raise SyntheticEvidenceError("%s received a synthetic evidence kind" % context)
