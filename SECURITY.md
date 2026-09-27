# Security and scope

This is a local prototype, not a hardened service. Campaign execution and archived operational launchers are disabled. The target probe can run a selected executable or call a loopback service. A token or a prompt does not isolate a process from readable files.

Generated artifacts may contain complete user-supplied test inputs and outputs. Keep real workspaces private by default. Do not log credentials, import private research corpora, or publish session traces automatically.

Before public release, the maintainer should establish a private vulnerability reporting route. None is claimed here.

## Phase 2 target execution

The process adapter executes the program selected by the operator. It limits runtime and I/O and passes a minimal environment, but it does not confine file access or network access. Run only trusted programs or place them in an operating-system sandbox. The HTTP adapter accepts literal loopback IPs only and never follows redirects. Target output and error bodies are omitted from reports; custom case inputs are sent to the selected target and may be sensitive to that service.

## Phase 3 campaign evidence

Campaign workspaces retain input and output JSON in the local SQLite evidence store. Protect those files and inspect them before sharing. Dispatch intent is committed before target execution; after a crash or transport uncertainty, the campaign stops as `INDETERMINATE` rather than automatically retrying a possible side effect. Evidence digests detect accidental corruption, not an attacker able to rewrite the whole workspace and recompute hashes. Process targets are not sandboxed.
