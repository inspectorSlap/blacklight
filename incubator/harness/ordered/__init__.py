"""v1.6.0 ordered-evidence harness path.

This package carries the parts of the harness that changed when the count-primary
target was replaced by the reviewed legacy-review-gate ordered-evidence engine:

* :mod:`harness.ordered.canonical` -- the registered canonical JSON digest
  convention, implemented independently of the engine and proven equal to it.
* :mod:`harness.ordered.statuses` -- the C1 v0.6 status vocabulary and the
  strict, coercion-free readers the harness uses to consume dispositions.
* :mod:`harness.ordered.grid` -- the 60-configuration roster: the 53 preserved
  predecessor configurations plus the seven approved validity configurations.
* :mod:`harness.ordered.synthetic` -- deterministic synthetic qualification
  evidence, materialized per the approved synthetic-qualification clarification.
* :mod:`harness.ordered.family` -- the C2 v0.5 gated-stream family, read from
  the verified manifest and required to match by exact set equality.
* :mod:`harness.ordered.events` -- event extraction from reviewed-engine output
  using the manifest's own event definitions.

Nothing in this package performs inference. Every scientific disposition is
produced by the single reviewed function ``ordinal_engine.engine.analyze``.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


ORDERED_PATH_VERSION = "1.6.0"
