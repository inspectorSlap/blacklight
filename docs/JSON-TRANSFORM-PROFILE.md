# JSON transformation example

This small profile demonstrates a different schema and decision rule through the common harness interface. It is a local example, not a statistical profile.

Input:

```json
{"records": [{"id": "a", "value": 2}, {"id": "b", "value": 1}], "minimum": 2}
```

Output:

```json
{"ids": ["a"], "total": 2, "count": 1}
```

Records whose integer `value` is greater than or equal to integer `minimum` are selected. `ids` preserve input order and duplicates. `total` sums only selected values; `count` counts selected records. Empty selections yield an empty list and zero totals. Booleans are not accepted as integers. Input has exactly `records` and `minimum`; each record has exactly `id` and `value`.

Five hand-checked cases cover the inclusive boundary, stable order, empty selection, duplicate IDs and a negative boundary. The oracle and separately written reference must match them. Five deliberate defects—exclusive boundary, sorted IDs, unfiltered total, incorrect count and an unexpected output field—must be caught by their named checks.

```sh
python3 -m harness.cli demo --profile json-transform-v1 --workspace workspace/json-demo
```

The report is `workspace/json-demo/results/profile-evaluation.json`. Its local pass means these synthetic checks behaved as specified. It does not test an external transformation service or authorize a campaign.
