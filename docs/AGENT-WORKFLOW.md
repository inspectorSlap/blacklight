# Two-role workflow and containment (Phase 4)

Blacklight separates an **implementer** who can see target source and private results from a **reviewer** who develops independent expectations from a reviewed public contract. The reviewer must freeze those expectations before target execution. This workflow works with humans, local agents or other tools; no model vendor is required. See the [implementer](../templates/implementer/README.md) and [reviewer](../templates/reviewer/README.md) workspace templates.

The workflow has two independent protections. The handoff tool copies only the approved contract fields and checks its digest. The Docker runner mounts only that handoff and the reviewer workspace, disables networking and starts a process with a read-only root filesystem, dropped capabilities and no inherited host secrets. The latter is the access boundary; role instructions and separate chat windows alone are not.

## A complete local example

Run from the repository root. The generated `workspace/` tree is ignored by Git. Review the example contract before substituting your own requirements.

```sh
mkdir -p workspace/roles/reviewer
cp templates/reviewer/expectations.example.json workspace/roles/reviewer/expectations.json
cp templates/reviewer/lineage.example.json workspace/roles/reviewer/lineage.json
python3 scripts/role_workflow.py prepare \
  --contract templates/implementer/contract.example.json \
  --out workspace/roles/handoff
```

Only `contract.json` and `manifest.json` appear in the handoff. The tool accepts an explicit contract schema: version, profile, target ID, requirements and request/response schemas. It rejects extra top-level fields and unexpected files. Human review is still required because a string inside an allowed field could itself disclose private material.

Run the reviewer inside a pre-pulled runtime image. The default Debian image offers a shell; use an image with the tools your reviewer actually needs. An interactive session can write only under `/reviewer` and read the contract under `/handoff`:

```sh
docker pull debian:bookworm-slim
python3 scripts/run_reviewer.py \
  --handoff workspace/roles/handoff \
  --workspace workspace/roles/reviewer \
  --interactive -- /bin/sh
```

The two example JSON files above illustrate the required shapes. In a real study, the reviewer should author cases and expected results **inside the isolated process**, using only the contract. If a human or external agent writes those files outside this container, do not claim the container enforced that author's information boundary. A custom local-agent image can be passed with `--image`; it is started without network access or host credentials. External model API calls need a separately reviewed, scoped egress design and are not covered by this recipe.

Once the reviewer has authored `expectations.json` and `lineage.json`, freeze them:

```sh
python3 scripts/role_workflow.py freeze \
  --bundle workspace/roles/handoff \
  --expectations workspace/roles/reviewer/expectations.json \
  --lineage workspace/roles/reviewer/lineage.json \
  --out workspace/roles/reviewer/freeze.json
```

The lineage disclosure names the implementer and reviewer systems and records `shared_lineage` as `yes`, `no`, `unknown` or `not-applicable`, with notes about known prior exposure. This is a disclosure, not a proof of independence. The freeze binds the exact contract, expectation and lineage bytes by SHA-256. It does not provide a trusted timestamp or prevent someone with write access from replacing the whole record; keep the original freeze in an independently controlled record if that matters.

The workflow evaluation refuses to call a target without a valid freeze. This example uses the bundled toy executable and one reviewer case:

```sh
python3 scripts/role_workflow.py evaluate \
  --bundle workspace/roles/handoff \
  --expectations workspace/roles/reviewer/expectations.json \
  --lineage workspace/roles/reviewer/lineage.json \
  --freeze workspace/roles/reviewer/freeze.json \
  --program examples/json_transform_process.py \
  --workspace workspace/roles/campaign \
  --max-requests 1 --max-cost 0 --unit-cost 0 --execute
```

For a paused campaign, repeat `evaluate` with the same bundle, expectations, lineage, freeze, target and workspace, replacing the budget flags with `--resume --execute`. The target identity and case list must still match the frozen run. The [campaign guide](CAMPAIGNS.md) explains bounded dispatch, uncertainty and verdicts.

Publish only the report for the reviewer to inspect:

```sh
python3 scripts/role_workflow.py publish \
  --bundle workspace/roles/handoff \
  --expectations workspace/roles/reviewer/expectations.json \
  --lineage workspace/roles/reviewer/lineage.json \
  --freeze workspace/roles/reviewer/freeze.json \
  --workspace workspace/roles/campaign \
  --out workspace/roles/result-bundle
```

`result-bundle/` contains only `report.json` and a digest manifest binding it to the expectation freeze. The underlying campaign workspace still contains raw case inputs and target outputs; do not give it to the reviewer if those observations are meant to remain private. A post-result source review is a separate, explicitly recorded step.

## Test the actual boundary

```sh
python3 scripts/check_isolation.py
```

This creates disposable synthetic implementer source and private results on the host, launches a reviewer container with the same mount restrictions, checks that it can read the handoff and write its workspace, and checks that the private files and Docker socket are absent. The test uses the pre-pulled `debian:bookworm-slim` image and makes no target or model API calls. CI pulls that public image before running the test. The check demonstrates the local Docker recipe; it does not prove an agent was authored independently, that a handoff was free of sensitive text, or that an operator kept later source access separate.

The Docker daemon and host operator remain trusted. Do not mount the Docker socket, target directory, home directory or private result directory into the reviewer process. Keep reviewer and implementer workspaces separate, and review any custom image or network policy before use.
