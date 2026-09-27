# Graph path profile: exact answers and metamorphic relations

`graph-path-v1` is a **synthetic preview** of a second test type. It has been checked against hand-worked graphs, two separate local algorithms, six deliberately broken variants and the bundled toy executable. **It has not been tested on a live engine or production target.** A local pass does not qualify another implementation.

## Contract

A request contains a directed graph with 2–12 uniquely named vertices, 1–40 edges, a source and a target. Each edge has `from`, `to` and a nonnegative integer `weight` from 0 to 100. Parallel and zero-weight edges are allowed. A response has exactly `{"distance": integer-or-null}`: the minimum sum of weights along a directed path, or `null` if unreachable. Booleans, negative distances and extra fields fail the output-shape check.

The bundled cases start from three independently hand-worked answers: a weighted path of length 5, an unreachable directed pair, and a zero-weight path of length 0. The exact oracle uses repeated edge relaxation; the separate clean reference uses a priority queue. Both are checked against those hand answers. The toy executable is a separate example target, not an independent research implementation.

Each base graph generates four target requests:

| Request | Check |
|---|---|
| Base | Exact shortest distance from a hand anchor or the profile oracle |
| Edges reversed in the input list | Same output as the base; edge order is not semantic |
| Fresh isolated vertex added | Same output as the base |
| Every weight doubled | Double the base distance if reachable; remain `null` if unreachable |

The three derived requests check output shape individually, then compare their answers with the base response. Their exact distances are intentionally withheld from the target verdict to exercise a cross-run relation. This means a wrong base and a matching wrong derived answer can satisfy a relation; the base's exact anchor remains essential. The profile's local self-check also confirms that both independent algorithms obey the relations. Before an external call, the graph profile validates every frozen group: exact base answers must agree with its independent oracle, and derived inputs must actually implement their declared transformations. A malformed reviewer-authored plan is refused before dispatch. Named mutants demonstrate that each advertised relation and the exact distance/reachability checks can detect a targeted defect.

## Run the synthetic example

```sh
python3 -m harness.cli demo --profile graph-path-v1 \
  --workspace workspace/graph-demo

python3 -m harness.cli probe --profile graph-path-v1 \
  --program examples/graph_path_process.py --target-id toy-graph-v1 \
  --workspace workspace/graph-probe
```

For a durable campaign against that same toy executable:

```sh
python3 -m harness.cli campaign --profile graph-path-v1 \
  --program examples/graph_path_process.py --target-id toy-graph-v1 \
  --workspace workspace/graph-campaign \
  --max-requests 12 --max-cost 0 --unit-cost 0 --execute
```

Use a fresh workspace for each command. `--cases examples/graph_path_custom.json` supplies **base graphs**, not pre-expanded cases; each base expands to four target requests. A custom file accepts 1–8 base graphs, each with at least two edges, at most 11 vertices and weights at most 50 so the isolated and doubled variants stay within bounds. Set `--max-requests` to four times the base-graph count. Custom exact base answers come from the profile oracle; they are not additional hand-checked anchors.

A completed probe or campaign reports `relation_failures` separately from per-case failures. A partial or blocked run says `relations_status: PENDING`; it cannot pass a relation whose responses are missing. The campaign recomputes relations from its frozen, digest-checked response evidence after resume. A `PASSED` technical verdict means only that the selected exact and relational checks passed. Research authority stays unset.
