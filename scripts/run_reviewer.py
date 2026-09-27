"""Run a local reviewer process with only handoff and reviewer project mounts."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from role_workflow import _verify_handoff, WorkflowError


def command(handoff, workspace, image, reviewer_command, interactive=False):
    handoff = Path(handoff).resolve(strict=True)
    workspace = Path(workspace).resolve(strict=True)
    if not handoff.is_dir() or not workspace.is_dir() or handoff == workspace \
            or handoff in workspace.parents or workspace in handoff.parents:
        raise WorkflowError("handoff and reviewer workspace must be separate directories")
    if "," in str(handoff) or "," in str(workspace):
        raise WorkflowError("mount paths cannot contain commas")
    if any(path.is_symlink() for path in handoff.iterdir()):
        raise WorkflowError("handoff may not contain symlinks")
    _verify_handoff(handoff)
    if not reviewer_command:
        raise WorkflowError("reviewer command is required")
    return ["docker", "run", "--rm", *(["-it"] if interactive else []), "--pull=never", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
            "--memory=256m", "--user=%s:%s" % (os.getuid(), os.getgid()),
            "--mount=type=bind,src=%s,dst=/handoff,readonly" % handoff,
            "--mount=type=bind,src=%s,dst=/reviewer" % workspace,
            "--tmpfs=/tmp:rw,nosuid,noexec,size=16m", "--workdir=/reviewer",
            image, *reviewer_command]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--image", default="debian:bookworm-slim", help="pre-pulled reviewer runtime image")
    parser.add_argument("--interactive", action="store_true", help="allocate an interactive reviewer terminal")
    parser.add_argument("reviewer_command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    reviewer_command = args.reviewer_command
    if reviewer_command and reviewer_command[0] == "--":
        reviewer_command = reviewer_command[1:]
    try:
        invocation = command(args.handoff, args.workspace, args.image, reviewer_command, args.interactive)
    except (OSError, WorkflowError) as exc:
        parser.error(str(exc))
    return subprocess.call(invocation)


if __name__ == "__main__":
    sys.exit(main())
