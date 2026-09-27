# Test-type roadmap and validation boundary

The architecture phases established reusable profiles, bounded target adapters, durable evidence and a local reviewer process boundary. The next work tests different **kinds of claims**. This table is the current scope; it is not a claim that Blacklight has been exercised against a live engine.

| Test type | Current status | Evidence and next gate |
|---|---|---|
| Exact-output examples | Implemented for `json-transform-v1`; ordinal profile remains offline | Hand-worked anchors, independent local reference and targeted mutants; bundled toy target only |
| Metamorphic cross-run relations | Implemented as a bounded `graph-path-v1` preview | Three hand-worked bases, independent oracle/reference, six mutants, toy process probe/campaign and resume tests; **no live-engine test** |
| Stateful sequences | Planned; no target session protocol or engine test | Define reset/isolation semantics, ordered action traces, crash ambiguity, clean reference and targeted state defects before claiming support |
| Statistical properties | Planned; no engine test or general threshold | Per-profile estimand, independence assumptions, sample/spend plan, false-positive controls, clean and broken controls, and prospective stopping rule |
| Third-party profile discovery | Planned | Only after several distinct profile shapes show a stable extension contract |

The next implementation candidate is a small stateful service profile, because it will force us to design session/reset boundaries rather than stretching the one-request-per-process API. Statistical claims should follow only when those boundaries and the profile-owned uncertainty rules are explicit. A real-engine evaluation is a **separate prospective milestone**: review target identity and permissions, freeze requirements and expectations, run an authorized bounded campaign, then publish the limits and negative results as well as passes. None of the current synthetic or toy runs is a substitute for that milestone.
