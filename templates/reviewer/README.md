# Independent reviewer workspace template

Work from the handoff contract only. Define expected behavior and cases without opening target source, private results or target responses. Record limitations. Complete `expectations.example.json` and `lineage.example.json`, then freeze them before any target evaluation. The lineage disclosure is self-reported; a shared model family must be marked `yes` or `unknown` when appropriate.

The Docker recipe in `docs/AGENT-WORKFLOW.md` mounts only the reviewed handoff and this workspace. Two chat windows, separate prompts and these template files do not enforce isolation by themselves.
