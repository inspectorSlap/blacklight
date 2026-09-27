# Bundled ordinal profile: current scope

The first extraction preserves a concrete statistical test profile so there is runnable substance to inspect. Changing its labels does not make its mathematics universal.

## 1. Inputs

- Ten ordered categories, scores 1 through 10; larger scores mean larger measured values.
- Four cells named `00`, `A0`, `0B`, and `AB`, representing a two-factor arrangement.
- Three evaluation conditions (legacy code calls them `lights`).
- Six primary specimens and four controls, now labelled `sample-01` through `sample-06` and `control-01` through `control-04`.
- Count-vector evidence and synthetic attempt archives. The later ordered-evidence implementation is preserved only in the disabled archive.

The primary/control group fields still use the historical generic labels `semantic` and `mechanical`. They describe this profile, not an assertion that every evaluation domain has these groups.

## 2. Quantities

The exact oracle computes win/loss/tie probabilities, probability of superiority, a linear transform to Cliff's delta, factor contrasts/interactions, concentration/collision quantities and floor/capacity constraints. The separate reference computes its own quantities without importing the oracle. The symbolic derivations and examples are in [ANCHORS.md](ANCHORS.md).

The reference uses a conservative uncertainty construction. It is a reference choice, not an assertion that this is the right statistical method for every study.

## 3. Fixed decision assumptions

The source hypothesis labels have become generic criteria C1–C5. This is a namespace change, not mathematical generalization. Important constants are still duplicated across the independently written implementations:

| Assumption | Current value/behavior |
|---|---|
| C1 superiority boundary | 0.70 |
| Equivalence interval for probability of superiority | 0.45–0.55 |
| Interaction magnitude / equivalence | 0.15 / 0.05 |
| Concentration magnitude / equivalence | 0.10 / 0.05 |
| C3 cross-condition equivalence | Withheld; not implemented |
| Candidate replicate counts in the retained grid | 8, 10, 12, 16, 20, 30 |
| Additional synthetic branch-coverage sizes | Not valid study-size recommendations |

Validity/provenance, recurrence, leave-one-out, heterogeneity, range and capacity gates have profile-specific logic. The namespace `blackbox.ordinal.*` deliberately does not advertise compatibility with another engine's schema.

## 4. What cannot be customized yet

There is no supported configuration switch for different category counts, arbitrary metric functions, specimen counts, evaluation-condition counts, missingness rules, target schemas, or decision topologies. Editing only one copy of a threshold would break agreement between implementations. These changes require a profile design and new anchors, reference behavior and mutations.

## 5. Claims you may make today

You can inspect and reproduce how this extracted profile checks its reference and known broken variants. You cannot conclude from that result that a new model, benchmark, classifier, instrument, API or production service is valid. Those require explicit adapters and domain-specific expectations, followed by new qualification.
