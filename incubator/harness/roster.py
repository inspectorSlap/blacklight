"""Canonical specimen roster and its zero-call preflight (v1.3).

WHY THIS EXISTS
---------------
The v1.2 checkpoint sent 500 real-target requests and every one was rejected
with `INPUT_REJECTED: semantic specimen roster does not match the frozen
six-specimen corpus`. The harness had been emitting placeholder identifiers
`ordinal-profile..S6` and `M1..M4`. The engine requires the frozen ordinal-profile roster.

WHAT CHANGES, AND WHAT MUST NOT
-------------------------------
Only the specimen *identifiers* change. The roles are mapped **bijectively and
positionally** onto the frozen roster, so:

* every synthetic count vector is unchanged;
* every scenario's meaning is unchanged -- position `i` still carries the same
  distribution, so the leave-one-out index order, the "first three versus last
  three" splits, and the floor-limited-specimen constructions all survive
  intact;
* every oracle answer, anchor, critical value and expected disposition is
  unchanged, because none of them is a function of an identifier.

The roster identifiers are public metadata: preregistration section 2 lists
them in the distributed contract. Using them as labels on synthetic count
vectors is not constructing an ordinal-profile artifact fixture and reads no ordinal-profile outcome.

ORDER
-----
The canonical order follows the preregistration's own listing: S-sem first,
then S-mix. If the engine turns out to require a different order, the v1.3
checkpoint now fails closed rather than reporting success -- which is exactly
the property the v1.2 failure showed was missing.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


# Preregistration section 2, verbatim order.
S_SEM = ("sample-01", "sample-02", "sample-03")
S_MIX = ("sample-04", "sample-05", "sample-06")
SEMANTIC_ROSTER = S_SEM + S_MIX                      # the six semantic-bearing
MECHANICAL_ROSTER = ("control-01", "control-02", "control-03", "control-04")   # the four controls

SEMANTIC_ROLES = ("ordinal-profile", "S2", "S3", "S4", "S5", "S6")
MECHANICAL_ROLES = ("M1", "M2", "M3", "M4")

ROLE_TO_SPECIMEN = dict(zip(SEMANTIC_ROLES, SEMANTIC_ROSTER))
ROLE_TO_SPECIMEN.update(zip(MECHANICAL_ROLES, MECHANICAL_ROSTER))
SPECIMEN_TO_ROLE = {v: k for k, v in ROLE_TO_SPECIMEN.items()}

PLACEHOLDER_PREFIXES = ("S", "M")


class RosterViolation(Exception):
    """Raised when a payload's roster is not the canonical frozen roster."""


def semantic_id(index):
    """Canonical semantic identifier for positional index 0..5."""
    return SEMANTIC_ROSTER[index]


def mechanical_id(index):
    return MECHANICAL_ROSTER[index]


def is_placeholder(identifier):
    """True for the v1.2-style placeholder identifiers."""
    return identifier in SEMANTIC_ROLES or identifier in MECHANICAL_ROLES


def _check_group(observed, expected, label, problems):
    """Detect placeholder, missing, duplicated, reordered and extra ids."""
    if observed == list(expected):
        return
    placeholders = [i for i in observed if is_placeholder(i)]
    if placeholders:
        problems.append("%s uses placeholder identifiers %s; the frozen roster "
                        "is required" % (label, placeholders))
    duplicates = sorted({i for i in observed if observed.count(i) > 1})
    if duplicates:
        problems.append("%s contains duplicated identifiers %s"
                        % (label, duplicates))
    missing = [i for i in expected if i not in observed]
    if missing:
        problems.append("%s is missing %s" % (label, missing))
    extra = [i for i in observed if i not in expected and not is_placeholder(i)]
    if extra:
        problems.append("%s contains identifiers outside the frozen roster %s"
                        % (label, extra))
    if (not placeholders and not duplicates and not missing and not extra
            and sorted(observed) == sorted(expected)):
        problems.append("%s is reordered: expected %s, found %s"
                        % (label, list(expected), observed))
    if len(observed) != len(expected):
        problems.append("%s has %d specimens, expected %d"
                        % (label, len(observed), len(expected)))


def check_counts_payload(payload):
    """Zero-call roster validation of an ordinal-counts payload."""
    problems = []
    lights = payload.get("lights")
    if not isinstance(lights, list):
        return ["payload has no lights array"]
    for index, light in enumerate(lights):
        label = "light[%s]" % (light.get("id", index))
        semantic = [s.get("id") for s in light.get("semantic_specimens", [])]
        mechanical = [s.get("id") for s in light.get("mechanical_specimens", [])]
        _check_group(semantic, SEMANTIC_ROSTER, "%s.semantic_specimens" % label,
                     problems)
        _check_group(mechanical, MECHANICAL_ROSTER,
                     "%s.mechanical_specimens" % label, problems)
        crossover = set(semantic) & set(MECHANICAL_ROSTER)
        if crossover:
            problems.append("%s places mechanical controls %s in the primary "
                            "aggregate" % (label, sorted(crossover)))
    return problems


def check_archive_payload(payload):
    """Zero-call roster validation of a canonical attempt archive."""
    problems = []
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        return ["payload has no attempts array"]
    by_group = {"semantic": set(), "mechanical": set()}
    for attempt in attempts:
        group = attempt.get("specimen_group")
        specimen = attempt.get("specimen_id")
        if group in by_group:
            by_group[group].add(specimen)
    for group, expected in (("semantic", SEMANTIC_ROSTER),
                            ("mechanical", MECHANICAL_ROSTER)):
        observed = sorted(by_group[group])
        placeholders = [i for i in observed if is_placeholder(i)]
        if placeholders:
            problems.append("%s attempts use placeholder identifiers %s"
                            % (group, placeholders))
        extra = [i for i in observed
                 if i not in expected and not is_placeholder(i)]
        if extra:
            problems.append("%s attempts reference identifiers outside the "
                            "frozen roster %s" % (group, extra))
    return problems


def assert_payload(payload, kind="counts"):
    """Raise unless the payload carries the canonical frozen roster.

    Called before a payload is handed to any transport, so a roster fault
    costs zero target requests.
    """
    problems = (check_counts_payload(payload) if kind == "counts"
                else check_archive_payload(payload))
    if problems:
        raise RosterViolation(
            "roster preflight rejected the payload before transport: %s"
            % "; ".join(problems[:4]))
    return True


def describe():
    return {
        "semantic_roster": list(SEMANTIC_ROSTER),
        "mechanical_roster": list(MECHANICAL_ROSTER),
        "role_to_specimen": dict(ROLE_TO_SPECIMEN),
        "bijective": (len(set(ROLE_TO_SPECIMEN.values()))
                      == len(ROLE_TO_SPECIMEN) == 10),
        "canonical_order_source": "preregistration section 2: S-sem then S-mix",
        "mapping_is_positional": True,
        "scientific_content_changed": False,
        "rejects": ["placeholder", "missing", "duplicated", "reordered",
                    "extra", "mechanical-in-primary"],
        "zero_call": True,
    }
