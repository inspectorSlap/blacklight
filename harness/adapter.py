"""Frozen adapter from a target response to the harness normal form.

`schemas/ordinal-analysis.schema.json` constrains `semantic_lights` and
`mechanical_lights` only as three-item arrays and `cross_light` only as an
object; no per-light field is named (AMB-09). The harness therefore defines its
own normal form from the preregistration and maps a target response into it
through the FROZEN candidate-key table below.

Two rules make this safe against the "use the engine as an answer key" failure:

1. The table is frozen before any real-target call, so it cannot be tuned to
   whatever the engine happens to emit.
2. If a required quantity cannot be located, the adapter raises
   `UndocumentedSchema`. The harness then fails closed with
   `ENGINE_NOT_YET_QUALIFIABLE` -- never a silent pass, and never
   `ENGINE_REJECTED`, because an unmapped key is a harness limitation rather
   than proof of an engine defect.

Disposition strings are likewise not schema-constrained (AMB-11). Section 13.1
of the preregistration is explicitly a *semantic* contract, so the harness maps
recognized spellings to semantic classes and fails closed on anything it does
not recognize.
"""

ADAPTER_VERSION = "1.0"


class UndocumentedSchema(Exception):
    """A required quantity or disposition could not be located or recognized."""

    def __init__(self, path, detail):
        Exception.__init__(self, "%s: %s" % (path, detail))
        self.path = path
        self.detail = detail


# ---------------------------------------------------------------------------
# Frozen candidate key spellings
# ---------------------------------------------------------------------------

KEYS = {
    "semantic_lights": ["semantic_lights"],
    "mechanical_lights": ["mechanical_lights"],
    "cross_light": ["cross_light"],
    "light_id": ["light_id", "id", "light"],
    "specimens": ["specimens", "specimen_results", "units"],
    "specimen_id": ["id", "specimen_id", "specimen"],
    "P0": ["P0", "p0", "P0_hat", "standalone_ps"],
    "PA": ["PA", "pa", "PA_hat", "a_present_ps"],
    "I_P": ["I_P", "i_p", "I_P_hat", "interaction"],
    "W0": ["W0", "w0"], "L0": ["L0", "l0"], "T0": ["T0", "t0"],
    "WA": ["WA", "wa"], "LA": ["LA", "la"], "TA": ["TA", "ta"],
    "delta0": ["delta0", "cliff_delta0", "delta_0"],
    "deltaA": ["deltaA", "cliff_deltaA", "delta_A"],
    "I_delta": ["I_delta", "i_delta", "cliff_interaction"],
    "p_floor_A0": ["p_floor_A0", "p_floor_a0", "floor_mass_A0"],
    "K_A": ["K_A", "k_a", "capacity_K_A"],
    "G": ["G", "g", "range_surplus"],
    "G_interval": ["G_interval", "g_interval", "range_surplus_interval"],
    "range_disposition": ["range_disposition", "range", "capacity_disposition"],
    "collision": ["collision", "collision_probability", "C_hat", "C"],
    "K_Q": ["K_Q", "k_q", "concentration_capacity"],
    "G_Q": ["G_Q", "g_q", "concentration_surplus"],
    "G_Q_interval": ["G_Q_interval", "g_q_interval"],
    "Q": ["Q", "q", "concentration_contrast"],
    "component_q0": ["component_q0", "q0", "q0_component"],
    "component_qB": ["component_qB", "qB", "qB_component"],
    "degeneracy": ["degeneracy", "degeneracy_flags", "empirical_degeneracy"],
    "n": ["n", "counts_total", "valid_response_totals"],
    "P0_bar": ["P0_bar", "p0_bar", "P0_mean", "corpus_P0"],
    "P0_bar_interval": ["P0_bar_interval", "p0_bar_interval", "P0_interval"],
    "I_P_bar": ["I_P_bar", "i_p_bar", "I_P_mean", "corpus_I_P"],
    "I_P_bar_interval": ["I_P_bar_interval", "i_p_bar_interval", "I_P_interval"],
    "c1": ["c1", "C1", "c1_ordinal"],
    "c2": ["c2", "C2", "c2_ordinal"],
    "c4": ["c4", "C4", "c4_resolution"],
    "c5": ["c5", "C5", "c5_control"],
    "range": ["range", "range_gate", "ordinal_range"],
    "validity": ["validity", "instrument_validity"],
    "disposition": ["disposition", "result", "state", "verdict"],
    "A_l": ["A_l", "a_l", "attenuation_claim", "light_claim"],
    "A_all": ["A_all", "a_all", "cross_light_claim"],
    "A_vector": ["A_vector", "a_vector", "light_claims"],
    "c3": ["c3", "C3", "cross_light_stability"],
    "pooled_verdict": ["pooled_verdict", "pooled", "pooled_disposition"],
    "Q_bar": ["Q_bar", "q_bar", "Q_mean"],
    "Q_bar_interval": ["Q_bar_interval", "q_bar_interval"],
    "guards": ["guards", "guard_results"],
    "cleared": ["cleared", "passed", "ok"],
    "inference_engine": ["inference_engine", "engine_status", "inference"],
}


# ---------------------------------------------------------------------------
# Frozen disposition synonym table -> semantic class
# ---------------------------------------------------------------------------

DISPOSITION_CLASSES = {
    # C1 / C2 branches
    "SUPPORTED": "SUPPORTED",
    "EQUIVALENTLY_ABSENT": "EQUIVALENTLY_ABSENT",
    "INDETERMINATE": "INDETERMINATE",
    "INDETERMINATE_GUARD_NOT_MET": "GUARD_NOT_MET",
    "HETEROGENEITY_NOT_CLEARED": "HETEROGENEITY_NOT_CLEARED",
    "RANGE_NOT_CLEARED": "RANGE_NOT_CLEARED",
    "RANGE_CLEARED": "RANGE_CLEARED",
    "INSTRUMENT_VALIDITY_NOT_CLEARED": "VALIDITY_NOT_CLEARED",
    "INFERENCE_ENGINE_FAILURE": "INFERENCE_ENGINE_FAILURE",
    "NOT_OPENED_C1_NOT_SUPPORTED": "NOT_OPENED",
    "C2_NOT_OPENED": "NOT_OPENED",
    "NOT_OPENED": "NOT_OPENED",
    # range / capacity
    "RANGE_ADEQUATE": "RANGE_ADEQUATE",
    "FLOOR_LIMITED": "FLOOR_LIMITED",
    "RANGE_INDETERMINATE": "RANGE_INDETERMINATE",
    "CONCENTRATION_RANGE_ADEQUATE": "CONCENTRATION_RANGE_ADEQUATE",
    "CONCENTRATION_RANGE_LIMITED": "CONCENTRATION_RANGE_LIMITED",
    "CONCENTRATION_RANGE_INDETERMINATE": "CONCENTRATION_RANGE_INDETERMINATE",
    # C4
    "GENERAL_RESOLUTION_LOSS_SUPPORTED": "C4_SUPPORTED",
    "GENERAL_RESOLUTION_LOSS_EQUIVALENTLY_ABSENT": "C4_EQUIVALENTLY_ABSENT",
    "GENERAL_RESOLUTION_LOSS_INDETERMINATE": "C4_INDETERMINATE",
    "C4_INDETERMINATE": "C4_INDETERMINATE",
    "C4_INDETERMINATE_GUARD_NOT_MET": "C4_GUARD_NOT_MET",
    "C4_HETEROGENEITY_NOT_CLEARED": "C4_HETEROGENEITY_NOT_CLEARED",
    "C4_CONCENTRATION_CAPACITY_NOT_CLEARED": "C4_CAPACITY_NOT_CLEARED",
    "C4_NOT_OPENED": "C4_NOT_OPENED",
    # C5
    "CONTROL_ATTENUATION_SUPPORTED": "C5_SUPPORTED",
    "CONTROL_ATTENUATION_EQUIVALENTLY_ABSENT": "C5_EQUIVALENTLY_ABSENT",
    "CONTROL_INDETERMINATE": "C5_INDETERMINATE",
    "CONTROL_INDETERMINATE_GUARD_NOT_MET": "C5_GUARD_NOT_MET",
    "CONTROL_HETEROGENEITY_NOT_CLEARED": "C5_HETEROGENEITY_NOT_CLEARED",
    "CONTROL_NOT_ELIGIBLE": "C5_NOT_ELIGIBLE",
    # C3
    "WITHHELD_NOT_IMPLEMENTED": "C3_WITHHELD",
    "WITHHELD": "C3_WITHHELD",
    "NOT_IMPLEMENTED": "C3_WITHHELD",
}

# Dispositions that assert a positive scientific claim. Emitting one of these
# is what the FALSE-SUPPORT and FALSE-EQUIVALENCE campaigns try to provoke.
CLAIM_CLASSES = {"SUPPORTED", "EQUIVALENTLY_ABSENT", "C4_SUPPORTED",
                 "C4_EQUIVALENTLY_ABSENT", "C5_SUPPORTED",
                 "C5_EQUIVALENTLY_ABSENT"}


def pick(obj, logical_key, path, required=True):
    """Locate a logical key in an object using the frozen candidate table."""
    if not isinstance(obj, dict):
        raise UndocumentedSchema(path, "expected an object, found %s"
                                 % type(obj).__name__)
    for candidate in KEYS.get(logical_key, [logical_key]):
        if candidate in obj:
            return obj[candidate]
    if required:
        raise UndocumentedSchema(
            "%s.%s" % (path, logical_key),
            "none of %s present; available keys: %s"
            % (KEYS.get(logical_key, [logical_key]), sorted(obj)))
    return None


def disposition_of(obj, logical_key, path, required=True, allow_unknown=False):
    """Extract a disposition string and map it to its semantic class.

    `allow_unknown` is used only for C3. Everywhere else an unrecognized
    spelling is genuinely ambiguous -- a conforming engine might legitimately
    spell SUPPORTED differently -- so the harness fails closed. For C3 the
    distribution is unambiguous in the other direction: the hypothesis is
    withheld in this engine version, so *any* string that is not a recognized
    withholding is a substantive violation regardless of spelling, and must be
    reportable as a FAIL rather than swallowed as an unmapped schema.
    """
    block = pick(obj, logical_key, path, required=required)
    if block is None:
        return None, None
    if isinstance(block, str):
        raw = block
    else:
        raw = pick(block, "disposition", "%s.%s" % (path, logical_key))
    if not isinstance(raw, str):
        raise UndocumentedSchema("%s.%s.disposition" % (path, logical_key),
                                 "disposition must be a string")
    if raw not in DISPOSITION_CLASSES:
        if allow_unknown:
            return raw, "UNRECOGNIZED"
        raise UndocumentedSchema(
            "%s.%s.disposition" % (path, logical_key),
            "unrecognized disposition %r; the frozen synonym table does not "
            "define its meaning, so the harness fails closed rather than "
            "guessing" % raw)
    return raw, DISPOSITION_CLASSES[raw]


def number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UndocumentedSchema(path, "expected a number, found %r" % (value,))
    return float(value)


def bounds(value, path):
    if isinstance(value, dict):
        lo = value.get("lower", value.get("lo", value.get("low")))
        hi = value.get("upper", value.get("hi", value.get("high")))
        pair = [lo, hi]
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        pair = list(value)
    else:
        raise UndocumentedSchema(path, "expected a two-element interval")
    return [number(pair[0], path + "[0]"), number(pair[1], path + "[1]")]


def normalize_specimen(raw, path):
    out = {"id": pick(raw, "specimen_id", path)}
    for key in ("P0", "PA", "I_P", "W0", "L0", "T0", "WA", "LA", "TA",
                "delta0", "deltaA", "I_delta", "p_floor_A0", "K_A", "G"):
        out[key] = number(pick(raw, key, path), "%s.%s" % (path, key))
    for key in ("K_Q", "G_Q", "Q", "component_q0", "component_qB"):
        value = pick(raw, key, path, required=False)
        out[key] = None if value is None else number(value, "%s.%s" % (path, key))
    out["G_interval"] = bounds(pick(raw, "G_interval", path),
                               "%s.G_interval" % path)
    gq = pick(raw, "G_Q_interval", path, required=False)
    out["G_Q_interval"] = None if gq is None else bounds(gq, "%s.G_Q_interval" % path)
    raw_range, class_range = disposition_of(raw, "range_disposition", path)
    out["range_disposition"] = raw_range
    out["range_class"] = class_range
    collision = pick(raw, "collision", path)
    if not isinstance(collision, dict):
        raise UndocumentedSchema("%s.collision" % path, "expected a cell mapping")
    out["collision"] = {
        cell: (None if collision.get(cell) is None
               else number(collision[cell], "%s.collision.%s" % (path, cell)))
        for cell in ("00", "A0", "0B", "AB")}
    out["n"] = pick(raw, "n", path)
    out["degeneracy"] = pick(raw, "degeneracy", path, required=False)
    return out


def normalize_semantic_light(raw, index):
    path = "semantic_lights[%d]" % index
    out = {"light_id": pick(raw, "light_id", path)}
    out["P0_bar"] = number(pick(raw, "P0_bar", path), "%s.P0_bar" % path)
    out["I_P_bar"] = number(pick(raw, "I_P_bar", path), "%s.I_P_bar" % path)
    out["P0_bar_interval"] = bounds(pick(raw, "P0_bar_interval", path),
                                    "%s.P0_bar_interval" % path)
    out["I_P_bar_interval"] = bounds(pick(raw, "I_P_bar_interval", path),
                                     "%s.I_P_bar_interval" % path)
    out["c1_raw"], out["c1"] = disposition_of(raw, "c1", path)
    out["c2_raw"], out["c2"] = disposition_of(raw, "c2", path)
    out["range_raw"], out["range"] = disposition_of(raw, "range", path)
    out["c4_raw"], out["c4"] = disposition_of(raw, "c4", path)

    c1_block = pick(raw, "c1", path)
    out["c1_guards"] = (pick(c1_block, "guards", "%s.c1" % path, required=False)
                        if isinstance(c1_block, dict) else None)
    c2_block = pick(raw, "c2", path)
    out["c2_guards"] = (pick(c2_block, "guards", "%s.c2" % path, required=False)
                        if isinstance(c2_block, dict) else None)
    c4_block = pick(raw, "c4", path)
    if isinstance(c4_block, dict):
        q_bar = pick(c4_block, "Q_bar", "%s.c4" % path, required=False)
        out["Q_bar"] = None if q_bar is None else number(q_bar, "%s.c4.Q_bar" % path)
        q_int = pick(c4_block, "Q_bar_interval", "%s.c4" % path, required=False)
        out["Q_bar_interval"] = (None if q_int is None
                                 else bounds(q_int, "%s.c4.Q_bar_interval" % path))
        out["c4_guards"] = pick(c4_block, "guards", "%s.c4" % path, required=False)
    else:
        out["Q_bar"] = out["Q_bar_interval"] = out["c4_guards"] = None

    validity = pick(raw, "validity", path)
    if isinstance(validity, dict):
        cleared = pick(validity, "cleared", "%s.validity" % path, required=False)
        # C1 v0.6 forbids status-blind consumption. A structured validity
        # disposition must never collapse through bool(): a non-empty status
        # string such as "NOT_CLEARED" is truthy and would have been read as a
        # clearance. Only a genuine JSON boolean is accepted here; anything else
        # fails closed rather than being coerced.
        if cleared is None:
            out["validity_cleared"] = None
        elif isinstance(cleared, bool):
            out["validity_cleared"] = cleared
        else:
            raise UndocumentedSchema(
                "%s.validity.cleared" % path,
                "validity clearance must be a JSON boolean; a status-bearing value "
                "must be consumed status-exactly, never coerced")
        out["validity_flags"] = validity.get("flags", validity)
    else:
        out["validity_cleared"] = None
        out["validity_flags"] = None

    engine = pick(raw, "inference_engine", path, required=False)
    out["inference_engine_status"] = (
        engine.get("status") if isinstance(engine, dict) else engine)

    a_l = pick(raw, "A_l", path)
    if not isinstance(a_l, bool):
        raise UndocumentedSchema("%s.A_l" % path, "A_l must be a boolean")
    out["A_l"] = a_l

    specimens = pick(raw, "specimens", path)
    if not isinstance(specimens, list):
        raise UndocumentedSchema("%s.specimens" % path, "expected an array")
    out["specimens"] = [normalize_specimen(s, "%s.specimens[%d]" % (path, i))
                        for i, s in enumerate(specimens)]
    out["range_specimen_dispositions"] = [s["range_class"] for s in out["specimens"]]
    return out


def normalize_mechanical_light(raw, index):
    path = "mechanical_lights[%d]" % index
    out = {"light_id": pick(raw, "light_id", path)}
    out["c5_raw"], out["c5"] = disposition_of(raw, "c5", path)
    specimens = pick(raw, "specimens", path)
    out["specimens"] = [normalize_specimen(s, "%s.specimens[%d]" % (path, i))
                        for i, s in enumerate(specimens)]
    return out


def normalize(result):
    """Map a raw target response into the harness normal form."""
    if not isinstance(result, dict):
        raise UndocumentedSchema("$", "response must be a JSON object")
    for key, expected in (("schema_version", "blackbox.ordinal.ordinal-analysis.v0.1"),
                          ("apparatus_status",
                           "DEVELOPMENT_ONLY_NOT_EXECUTION_ELIGIBLE")):
        if result.get(key) != expected:
            raise UndocumentedSchema(key, "expected %r, found %r"
                                     % (expected, result.get(key)))
    if result.get("confirmatory_ready") is not False:
        raise UndocumentedSchema("confirmatory_ready",
                                 "must be exactly false in a development target")
    blocking = result.get("blocking_conditions")
    if not isinstance(blocking, list) or not blocking:
        raise UndocumentedSchema("blocking_conditions",
                                 "must be a non-empty array")

    semantic = pick(result, "semantic_lights", "$")
    mechanical = pick(result, "mechanical_lights", "$")
    cross = pick(result, "cross_light", "$")
    for name, block in (("semantic_lights", semantic),
                        ("mechanical_lights", mechanical)):
        if not isinstance(block, list) or len(block) != 3:
            raise UndocumentedSchema(name, "expected exactly three lights")

    normalized_cross = {}
    a_all = pick(cross, "A_all", "cross_light")
    if not isinstance(a_all, bool):
        raise UndocumentedSchema("cross_light.A_all", "must be a boolean")
    normalized_cross["A_all"] = a_all
    vector = pick(cross, "A_vector", "cross_light")
    if not isinstance(vector, list) or len(vector) != 3:
        raise UndocumentedSchema("cross_light.A_vector",
                                 "expected three light claims")
    # Status-exact consumption: each per-light attenuation claim must already be
    # a JSON boolean under the predecessor schema. Coercing with bool() would
    # have turned any status string, including a non-clearing one, into True.
    for index, value in enumerate(vector):
        if not isinstance(value, bool):
            raise UndocumentedSchema(
                "cross_light.A_vector[%d]" % index,
                "each attenuation claim must be a JSON boolean; a status-bearing "
                "value must be consumed status-exactly, never coerced")
    normalized_cross["A_vector"] = list(vector)
    normalized_cross["c3_raw"], normalized_cross["c3"] = disposition_of(
        cross, "c3", "cross_light", allow_unknown=True)
    normalized_cross["pooled_verdict"] = pick(cross, "pooled_verdict",
                                              "cross_light", required=False)

    return {
        "adapter_version": ADAPTER_VERSION,
        "engine_version": result.get("engine_version"),
        "blocking_conditions": blocking,
        "semantic_lights": [normalize_semantic_light(l, i)
                            for i, l in enumerate(semantic)],
        "mechanical_lights": [normalize_mechanical_light(l, i)
                              for i, l in enumerate(mechanical)],
        "cross_light": normalized_cross,
    }
