# Contributing

The extension API is still being designed. Open an issue or design note describing your target, input/output shape, criteria, and what counts as a valid result before depending on internal module names.

A new profile needs an explicit contract, a minimal synthetic example, independently derived expectations, valid cases, deliberately faulty cases, a per-check coverage table, tests, and honest limitations. Include an uncertainty/independence argument where stochastic results are involved. Keep a reference implementation separate from the oracle/checker code.

Do not add private datasets, credentials, copied target implementations, or historical approval records. A new target response must not silently become the expected answer. Changes to criteria after inspecting target results need a new version and an explanation.

For now, run the offline demo, unit tests and export scanner described in the implementation guide. Contribution and distribution terms must be selected before this local workspace becomes a public project.
