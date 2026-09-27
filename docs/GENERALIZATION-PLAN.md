# Generalization plan

## Product direction

A contract-driven black-box evaluation framework: define what should hold, build an independent challenge harness, demonstrate that it catches known failures without rejecting valid behavior, then preserve an inspectable evidence trail.

The intended extension surface should support different input schemas, values, scales and decision rules. The framework should not pretend that every domain admits the same oracle or statistical test. Domain plugins must state their assumptions, limitations and unsupported cases.

## Phase 0 — extracted workspace (this delivery)

Retain reusable code and mathematical documentation; replace private identifiers; remove study data, historical approvals and target dependencies; provide a local synthetic demonstration; inventory disabled assets. Record fresh validation and a public-readiness boundary. No claim of universal support.

## Phase 1 — profile boundary, first credible release

Extract a small documented profile protocol from the active ordinal implementation. Start with methods for scenario generation, schema normalization, expected quantities, decision checks, mutations and report rendering. Keep the oracle and reference independently implemented even when they share declarative configuration. A profile's author must not use the target's implementation as the answer key.

Deliver a versioned `ordinal-v1` profile plus a deliberately different small profile, such as deterministic JSON transformation with exact invariants. The second profile should prove the extension boundary without requiring LLM calls or uncertain statistical claims.

**Acceptance:** both profiles run through the same harness; different input shapes and criteria work without editing core orchestration; each has clean cases, targeted mutations, anchors or explicit oracle limits; registry gaps and unsupported claims remain visible. Do not call numeric thresholds universally valid.

## Phase 2 — real target adapters

Add explicit local-process JSON and loopback HTTP adapters, with a new target identity contract, bounded payloads/timeouts and sanitized errors. No provider-specific LLM SDK is required for the first release. Operators should be able to test their own implementation without importing it into the harness process.

**Acceptance:** a user-provided executable and a toy HTTP service can be tested; timeouts, invalid JSON, identity changes and unavailable endpoints become explicit blocked results; transport logs omit credentials; no implicit fallback to the reference occurs.

## Phase 3 — campaign evidence and restart safety

Extract the retained evidence store, byte/digest indexes, continuation logic and bounded dispatcher. Replace release-number globals and private-contract lookups with a per-run specification. Separate freeze identity, operator policy, live execution authorization and research verdict.

**Acceptance:** crash/restart does not silently lose or duplicate completed evidence; corrupt archives and changed target/profile identities stop resumption; cost and request bounds are enforced before work; reports distinguish aborted, incomplete, indeterminate and passed runs. Demonstrate this with local faults, not a large paid campaign.

## Phase 4 — independent agent workflow

Provide two workspace templates, narrow handoff bundles and a tested container/process isolation recipe. Treat the implementer and harness reviewer as separate roles; do not require a particular model vendor. Freeze the independent expectations before releasing target source for later review.

**Acceptance:** containment tests demonstrate that the harness role cannot read target code or private results and can access only permitted interfaces. Disclose shared model lineage. Never equate different chat windows or prompt instructions with enforced isolation.

## Contributions we can welcome

- New profiles with real requirements, independent expected behavior and demonstrable faults.
- Adapters for existing tools and services.
- Alternative uncertainty procedures with explicit assumptions and validation.
- Evidence viewers, fault injection and durable-resume tests.
- Reproducible case studies that report limits and failures, not only favorable outcomes.

A useful profile contribution must include a minimal synthetic example, supported input/output contract, known valid behavior, at least one targeted defect per claimed check, and explicit limitations. No leaderboard number alone establishes readiness.

## Release bar and positioning

Publish once a fresh clone can run the advertised demo, the supported profile/adapters are accurately documented, the license is selected, export review is complete and CI passes. A useful early release may support only one substantive profile while honestly exposing the intended extension design; it must not advertise planned adapters or universal criteria as implemented.

Use completed acceptance gates to track progress. No calendar estimate is required to decide the next step. Start by reviewing this extraction and choosing the first public profile/API boundary.
