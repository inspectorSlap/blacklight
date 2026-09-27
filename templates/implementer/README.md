# Implementer workspace template

Keep target source, internal tests and private results here. Share only a reviewed public contract through `scripts/role_workflow.py prepare`. Do not mount this directory into the reviewer container. Use a target identity that the Phase 2 adapter can verify, and record unsupported behavior in the public contract.

Copy `contract.example.json` to a working location, edit its requirements and schemas, then review every field before preparing the handoff. This template contains no target implementation.
