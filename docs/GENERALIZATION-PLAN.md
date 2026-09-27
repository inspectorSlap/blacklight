# Generalization plan

## Product direction

A contract-driven black-box evaluation framework: define what should hold, build an independent challenge harness, demonstrate that it catches known failures without rejecting valid behavior, then preserve an inspectable evidence trail.

The intended extension surface should support different input schemas, values, scales and decision rules. The framework should not pretend that every domain admits the same oracle or statistical test. Domain plugins must state their assumptions, limitations and unsupported cases.

## Phase 0 — extracted workspace (complete)

Retain reusable code and mathematical documentation; replace private identifiers; remove study data, historical approvals and target dependencies; provide a local synthetic demonstration; inventory disabled assets. Record fresh validation and a public-readiness boundary. No claim of universal support.

## Phase 1 — profile boundary (local prototype implemented; release work remains)

Extract a small documented profile protocol from the active ordinal implementation. Let each profile own scenario generation, schema normalization, expected quantities, decision checks and mutations while the common command layer owns workspaces and report envelopes. Keep the oracle and reference independently implemented even when they share declarative configuration. A profile's author must not use the target's implementation as the answer key.

Deliver a versioned `ordinal-v1` profile plus a deliberately different small profile, such as deterministic JSON transformation with exact invariants. The second profile should prove the extension boundary without requiring LLM calls or uncertain statistical claims.

**Acceptance:** both profiles run through the same harness; different input shapes and criteria work without editing core orchestration; each has clean cases, targeted mutations, anchors or explicit oracle limits; registry gaps and unsupported claims remain visible. Do not call numeric thresholds universally valid.

## Phase 2 — real target adapters (bounded local prototype implemented)

Local-process JSON and literal-loopback HTTP adapters now use a target identity envelope, bounded payloads/timeouts and sanitized blocked codes. No provider-specific LLM SDK is required. The JSON profile can test a user-provided executable or local service without importing it into the harness process; the ordinal target boundary remains unsupported.

**Acceptance:** a user-provided executable and a toy HTTP service can be tested; timeouts, invalid JSON, identity changes and unavailable endpoints become explicit blocked results; transport logs omit credentials; no implicit fallback to the reference occurs.

## Phase 3 — campaign evidence and restart safety (bounded JSON prototype implemented)

Extract the retained evidence store, byte/digest indexes, continuation logic and bounded dispatcher. Replace release-number globals and private-contract lookups with a per-run specification. Separate freeze identity, operator policy, live execution authorization and research verdict.

**Acceptance:** crash/restart does not silently lose or duplicate completed evidence; corrupt archives and changed target/profile identities stop resumption; cost and request bounds are enforced before work; reports distinguish aborted, incomplete, indeterminate and passed runs. Local fault tests cover these paths. The active prototype now supports JSON and synthetic graph profiles through two local transports; ordinal campaign support and a general supervisor remain future work.

## Phase 4 — independent agent workflow (local Docker prototype implemented)

Provide two workspace templates, narrow handoff bundles and a tested container/process isolation recipe. Treat the implementer and harness reviewer as separate roles; do not require a particular model vendor. Freeze the independent expectations before releasing target source for later review.

**Acceptance:** an actual Docker containment test confirms that a reviewer process reads only the handoff project input, writes its own workspace, and cannot see synthetic target source or private results. The handoff requires lineage disclosure and freezes expectations before workflow evaluation. This is a local process boundary, not proof of independent reasoning or a general remote-agent sandbox. Never equate different chat windows or prompt instructions with enforced isolation.

## Phase 5 — distinct test types (metamorphic preview implemented)

Add cross-run relations as an optional profile capability, with exact anchors, a separate reference and relation-specific mutants. `graph-path-v1` is the first synthetic slice: edge reordering and an isolated vertex preserve distance, while doubling nonnegative weights doubles a reachable distance. The probe and durable campaign keep relation findings separate from per-case findings, and mark them pending until all paired responses exist. Validation has used local fixtures and a bundled toy executable only; **no live engine has been tested**.

Next candidates are stateful sequences with explicit session/reset semantics, then statistical properties with profile-owned error controls and prospective stopping rules. Neither is implemented or live-engine tested. A real-engine campaign requires separately authorized scope, frozen expectations and an explicit report of limits. See [test-type roadmap](TEST-TYPES-ROADMAP.md).

## Contributions we can welcome

- New profiles with real requirements, independent expected behavior and demonstrable faults.
- Adapters for existing tools and services.
- Alternative uncertainty procedures with explicit assumptions and validation.
- Evidence viewers, fault injection and durable-resume tests.
- Reproducible case studies that report limits and failures, not only favorable outcomes.

A useful profile contribution must include a minimal synthetic example, supported input/output contract, known valid behavior, at least one targeted defect per claimed check, and explicit limitations. No leaderboard number alone establishes readiness.

## Release bar and positioning

Tag the first release once a fresh clone can run the advertised demo, the supported profile/adapters are accurately documented, the MIT license is present, export review is complete and CI passes. A useful early release may support only one substantive profile while honestly exposing the intended extension design; it must not advertise planned adapters or universal criteria as implemented.

Use completed acceptance gates to track progress. No calendar estimate is required to decide the next step. The `ordinal-v1` and `json-transform-v1` modules now exercise the shared local interface. Remaining release work includes profile discovery beyond the built-in registry, independent review of the API, broader domain tests and public export review. The local transports, bounded JSON/graph campaign and Docker reviewer recipe are implemented. The graph profile remains a synthetic/toy preview. A tagged release remains gated on the owner's independent PII review and review of the complete Git history.
