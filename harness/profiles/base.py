"""The public extension boundary for local, offline test profiles.

A profile owns its criteria, oracle, reference, fixtures and mutations. The
orchestrator owns workspace lifecycle, command routing and result envelopes.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Evaluation:
    technical_checks_passed: bool
    gate: str
    profile_gate_passed: bool
    details: dict[str, Any]


class Profile(Protocol):
    profile_id: str
    description: str

    def build(self, workspace: Path) -> dict[str, Any]:
        """Write synthetic fixtures to a fresh workspace."""
        ...

    def evaluate(self, workspace: Path) -> Evaluation:
        """Evaluate the profile without external target access."""
        ...


class TargetProfile(Profile, Protocol):
    def target_cases(self, custom_inputs: list[Any] | None = None) -> list[dict[str, Any]]:
        """Return bounded cases with id, input and expected fields."""
        ...

    def check_target_output(self, observed: Any, expected: Any) -> list[str]:
        """Return named failed criteria; never substitute a reference result."""
        ...


class RelationalTargetProfile(TargetProfile, Protocol):
    def check_target_relations(self, cases: list[dict[str, Any]], observations: dict[str, Any]) -> list[dict[str, str]]:
        """Return named cross-case failures after every selected response exists."""
        ...
