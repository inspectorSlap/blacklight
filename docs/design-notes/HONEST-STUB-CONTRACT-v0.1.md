> DESIGN ARCHIVE: sanitized historical engineering notes, not a current capability, approval, result, or execution instruction. Referenced legacy artifacts are intentionally absent.

# Proposed honest-stub output contract — v0.2 shape

**PROPOSAL ONLY. Not implemented. No executable code was modified.**

Machine-readable authority: `results/audit/honest-stub-contract-v0.1.json`.

---

## Core principle

> an unresolved or ineligible state must never be encoded as an ordinary Boolean false. False is a scientific claim -- 'the procedure ran and the effect was not earned'. Absence of a procedure is not that claim.

## Terminal statuses

| Status | Boolean value | Scientifically defined | Meaning |
|---|---|---|---|
| `EQUIVALENTLY_ABSENT` | `false` | yes | the equivalence region cleared; the effect is practically absent. NOT the same as NOT_EARNED |
| `FAILED_INFERENCE` | `null` | **no** | the inference engine could not produce a boundary-valid region for this claim |
| `FAILED_VALIDITY` | `null` | **no** | instrument-validity requirements did not clear -- refusal rates, differential refusal, stochastic validity |
| `INDETERMINATE` | `null` | **no** | the procedure ran and cleared neither region |
| `INELIGIBLE` | `null` | **no** | a structural eligibility gate failed -- provenance, cache, schema, local-lens or inference-engine. Per preregistration s12.3 the claim cannot be declared regardless of numerical results |
| `NOT_EARNED` | `false` | yes | the procedure ran and the meaningful-effect region did not clear; this is a substantive negative result |
| `SUPPORTED` | `true` | yes | the claim's meaningful-effect region cleared under the sealed procedure |
| `WITHHELD_UNSEALED` | `null` | **no** | the procedure this claim requires is not yet sealed in the preregistration, so no honest disposition exists |

`INELIGIBLE` is not invented here: preregistration §12.3 already uses exactly that word for a claim whose structural eligibility gate has failed, and states it 'cannot be declared regardless of numerical results'.

## Claim object shape
```json
{
  "$comment": "PROPOSED SHAPE -- NOT IMPLEMENTED. Every claim-bearing field becomes an object of this shape.",
  "estimate": {
    "$comment": "null whenever the interval construction is unsealed",
    "alpha": "number or null",
    "interval": "[lo, hi] or null",
    "point": "number or null"
  },
  "prerequisites": [
    {
      "claim_ref": "pointer to another claim object, e.g. semantic_lights[0].c1",
      "status": "its status"
    }
  ],
  "procedure": {
    "id": "identifier of the sealed procedure used",
    "sealed": "boolean: whether the procedure is sealed",
    "version": "version of that procedure"
  },
  "reason_codes": [
    "machine-readable codes, e.g. UNSEALED_ALPHA_P, UNSEALED_CR_PROVIDER, UNSEALED_D_NEAR, STRUCTURAL_GATE_CACHE, REFUSAL_LIMIT_UNSEALED"
  ],
  "status": "one of the eight terminal statuses",
  "value": "boolean ONLY when status.scientifically_defined is true; otherwise null. Never false as a stand-in for unknown."
}
```

## Per-light primary claim `A_l`

**Meaning.** A_l = C1_l AND RANGE_l AND VALIDITY_l AND C2_l

**Rule.** status is SUPPORTED with value true only when all four prerequisites are SUPPORTED (range: RANGE_ADEQUATE / cleared). If any prerequisite is WITHHELD_UNSEALED, INELIGIBLE, FAILED_VALIDITY or FAILED_INFERENCE, A_l inherits that status with value null and cites the failing prerequisite. Only when every prerequisite is scientifically defined and at least one is NOT_EARNED may A_l be NOT_EARNED with value false.

**Today.** `WITHHELD_UNSEALED, value null, because c1/c2/range/validity all depend on unsealed constructions`

## Derived cross-light claim `A_all`

**Meaning.** A_all = A_L1 AND A_L2 AND A_L3, a DERIVED conjunction

**Rule.** identical conjunction discipline one level up. A_all is never a bare boolean and never the sole primary result.

**Must not:**
- be conflated with C3 stability
- replace the three-light vector as the reported object
- be emitted as false when any A_l is undefined

**Today.** `WITHHELD_UNSEALED, value null, prerequisites all WITHHELD_UNSEALED`

## C3 stability — a separate object and family

**Meaning.** cross-light STABILITY: pairwise equivalence procedures on the three interaction effects I_P_bar_L1, I_P_bar_L2, I_P_bar_L3

**Must not:**
- be merged into cross_light.A_all or its prerequisites
- be read as implying meaningful attenuation
- be implied by A_all being SUPPORTED

**Preregistered asymmetry.** all-three attenuation support does not imply stability, and stability does not imply meaningful attenuation (s4 C3-light). Two independent claims.

**Today.** `WITHHELD_UNSEALED, value null, reason codes UNSEALED_ALPHA_C3 and UNSEALED_C3_MARGIN and UNSEALED_C3_PROCEDURE`

*C3 is the ONE field the current harness already handles correctly: disposition_of(allow_unknown=True) plus WITHHELD synonyms. The proposal generalizes that treatment to every claim.*

## `A_vector`: booleans, dispositions, or claim objects?

**Answer: structured claim objects -- the same objects referenced by A_all's prerequisites, not copies.**

the preregistration makes the three-light vector THE primary reported object (s4 C3-light), and each entry must carry its C1, range, C2, C4, C5, validity and uncertainty dispositions. A boolean vector cannot carry that. A vector of bare disposition strings is better but still loses the reason codes, prerequisite references and procedure identifiers needed to tell WITHHELD_UNSEALED from INDETERMINATE.

### FLAGGED: current harness behaviour (CRITICAL)

`harness/adapter.py:343` — `normalized_cross["A_vector"] = [bool(v) for v in vector]`

bool(v) maps any nonempty string to true. A vector member of "INDETERMINATE", "INELIGIBLE" or "WITHHELD_UNSEALED" would become true -- silently converting an absence of evidence into a positive primary claim for that light.

**Why this one matters most.** this is the one defect in the audit that fails UNSAFE. Everywhere else the harness fails closed and refuses; here it would proceed and be wrong, in the direction of over-claiming. An adversarial harness that silently upgrades INDETERMINATE to a supported primary claim cannot falsify the thing it exists to test.

*not reached in the v1.5.3 launch only because the A_all check three lines earlier raised first. Fixing A_all without fixing this would expose it.*

## Which stubs are acceptable for development transport

- WITHHELD_UNSEALED on c1, c2, range, validity, c4, c5, A_l, A_all and C3
- null estimates and null intervals wherever the construction is unsealed
- descriptive counts (W/L/T, delta, P0, PA, I_P, collision cells) populated with real numbers -- these are arithmetic on observed categories and do not depend on any unsealed inference
- structural envelope fields: schema_version, engine_version, apparatus_status, confirmatory_ready, blocking_conditions

## Which stubs make full qualification impossible

- any WITHHELD_UNSEALED on c1, c2, range or validity -- these are the A_l chain, so no primary claim can be qualified
- WITHHELD_UNSEALED on A_l and A_all, which are what the campaign's FALSE-SUPPORT and FALSE-EQUIVALENCE scenarios are built to provoke
- null intervals, which make every interval-scaling and coverage scenario in the harness's clean panel untestable

## What could still be tested without overstating qualification

**Testable now:**
- the descriptive arithmetic layer: W/L/T tallies, P0, PA, I_P, Cliff delta and the delta contrast
- range-gate ARITHMETIC: p_floor_A0, K_A = 1 - 0.5*p_floor_A0, G = K_A - (P0 - M_I) as point quantities
- concentration ARITHMETIC: per-cell collision probability, K_Q, G_Q, Q
- the structural envelope and blocking-conditions discipline
- transport, identity, provenance, retention and blinding behaviour (already demonstrated by the v1.5.2 checkpoint)

**Not testable now:** every disposition, every interval, every gate clearance, A_l, A_all, C3, simultaneous inference, candidate-N selection

**Honest label for such a run:** `STRUCTURAL_AND_ARITHMETIC_CONFORMANCE ONLY. It would not be engine qualification and must not be reported as such.`

## What must be sealed before candidate-N selection

- alpha_P
- the three-light simultaneous construction
- the boundary-valid multinomial confidence-region provider
- the constrained-propagation algorithm
- the dependence/blocking unit
- D_NEAR
- refusal-rate and differential-refusal limits
- R_MAX and the retry taxonomy
> s12.4 requires the synthetic-coverage program to exercise the COMPLETE decision procedure including simultaneous inference. Selecting N against a procedure that does not exist would fix the study's precision parameter against nothing.

candidate-N selection cannot be scientifically valid until alpha_P, the simultaneous construction, the boundary-valid CR provider, the dependence unit and D_NEAR are sealed. Selecting N before then would fix the study's precision parameter against a decision procedure that does not yet exist.
