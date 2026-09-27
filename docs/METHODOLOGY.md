# Methodology

The reusable idea is adversarial qualification against a contract: a harness must detect relevant known failures without accusing a valid implementation of those failures.

## Separate the responsibilities

1. An operator defines the target contract, allowed inputs, intended claims, evidence policy, and acceptance thresholds before seeing target results.
2. A target implementation agent builds the system in its own workspace.
3. A separate harness agent receives only the public contract, permitted schemas, and a behavioral endpoint. It develops its expected answers without borrowing the target implementation or using responses as an answer key.
4. The harness freezes its oracle, scenarios, checks, failure registry and acceptance plan before the target campaign.
5. A reviewer assesses disagreements and gaps. Source review, if needed, starts after the black-box artifacts are frozen. Findings require concrete inputs, expected behavior, observed behavior and consequences.

This is a recommended two-agent workflow, not something this extracted Python prototype enforces. Two agents can make correlated errors. Shared model families, prompts, source material and authorship should be disclosed. Strong isolation needs filesystem/network/process controls outside a chat instruction.

## Qualify both sides

**Sensitivity:** every registered broken target must trigger the check intended to detect its defect. An unrelated failure is not enough.

**Specificity:** the reference must clear the applicable clean panel and produce the declared expected dispositions. A harness that rejects everything is not useful.

**Anchors:** simple symbolic examples must agree with the exact oracle and the separately implemented reference. The retained anchors have a historical manual-derivation claim; this extraction has not independently established that chronology. They remain reviewable mathematical artifacts.

**Coverage:** every required result or dangerous error direction needs a named clean scenario, broken target, check, and observable evidence. Explicitly explain genuinely unreachable paths. Do not manufacture a scenario to make a table look complete.

## Preserve disagreements

Do not adjust the expected answer to match the target after observing a mismatch. Version a corrected contract/oracle and explain the change. Missing or unmappable evidence is blocked or indeterminate, not a pass. A finite mutation panel does not establish universal correctness or a calibrated detection rate against unseen faults.

## Freeze claims before spending evaluations

Define the random seed derivation, unit of independence, multiplicity, sample counts, stopping rule and precision requirements prospectively. Repeated looks at the same evidence require an appropriate sequential procedure. Thresholds and category semantics belong to the profile, not a universal harness default.

The extracted profile includes specific binomial-bound and two-look helpers, but they are not validated for arbitrary outcomes, dependence structures or adaptive workflows. The broader campaign and approval machinery is archived and disabled.

## Keep operational evidence honest

The original engineering design includes exact request/response retention, digest indexing, crash-safe resumption, target identity checks and explicit spending authorization. Those designs are preserved for adaptation; they are not promised capabilities of the local demo. Hashes detect changed bytes, not scientific correctness or an independently enforced information boundary.

Human review and execution authority remain distinct from a technical test pass. No historical approvals, attestations or release verdicts travel into this workspace.
