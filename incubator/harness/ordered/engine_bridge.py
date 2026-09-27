"""The one place the harness reaches the reviewed engine.

Every caller -- CLI, batch, campaign, qualification, and the standalone endpoint
server -- resolves through this module to the same reviewed function,
``ordinal_engine.engine.analyze``. The module adds no scientific logic of its own and
holds no alternate adjudication path.

The vendored release is byte-verified before it is imported, so the harness
cannot silently run against an edited engine.
"""

from __future__ import annotations

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import os
import sys

from .canonical import sha256_hex

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENDOR = os.path.join(ROOT, "vendor", "blackbox-ordinal-v0.3.0-rc2")
VENDOR_SRC = os.path.join(VENDOR, "src")
MANIFEST_PATH = os.path.join(VENDOR, "MANIFEST.sha256")

RELEASE_MANIFEST_SHA256 = "1e2c7dae8e3d879cc3bf49cacc860a4c61e8868e291a26ccdfbab1b2d60776a4"
ENGINE_VERSION = "0.3.0-rc2"

# The immutable reviewed predecessor this release supersedes and preserves.
PREDECESSOR_RELEASE_MANIFEST_SHA256 = (
    "4a7c42f51071f0d19016e38617ab36a72c3f7a50ccf4841d24184f76103e860a")


class EngineIntegrityError(Exception):
    """Raised when the vendored engine is missing or not byte-identical."""


def _verify_engine_sources():
    """Recompute every manifest entry under ``src/`` before importing."""
    if not os.path.isfile(MANIFEST_PATH):
        raise EngineIntegrityError("vendored engine manifest is missing: %s" % MANIFEST_PATH)
    with open(MANIFEST_PATH, "rb") as handle:
        raw = handle.read()
    observed_manifest = sha256_hex(raw)
    if observed_manifest != RELEASE_MANIFEST_SHA256:
        raise EngineIntegrityError(
            "vendored release manifest digest mismatch: expected %s, observed %s"
            % (RELEASE_MANIFEST_SHA256, observed_manifest))

    mismatched = []
    checked = 0
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if name.startswith("./"):
            name = name[2:]
        if not name.startswith("src/"):
            continue
        full = os.path.join(VENDOR, name)
        if not os.path.isfile(full):
            mismatched.append(name)
            continue
        with open(full, "rb") as source:
            if sha256_hex(source.read()) != digest:
                mismatched.append(name)
        checked += 1
    if mismatched:
        raise EngineIntegrityError(
            "vendored engine sources are not byte-identical: %s" % mismatched[:5])
    if not checked:
        raise EngineIntegrityError("vendored manifest lists no engine sources")
    return checked


ENGINE_SOURCE_FILES_VERIFIED = _verify_engine_sources()

if VENDOR_SRC not in sys.path:
    sys.path.insert(0, VENDOR_SRC)

from ordinal_engine import api as _api  # noqa: E402
from ordinal_engine import cli as _cli  # noqa: E402
from ordinal_engine import engine as _engine  # noqa: E402
from ordinal_engine import ingest as _ingest  # noqa: E402
from ordinal_engine.canonical import canonical_sha256 as engine_canonical_sha256  # noqa: E402
from ordinal_engine.models import InputError  # noqa: E402
from ordinal_engine.output_contract import ContractViolation  # noqa: E402

# The single reviewed scientific function. Nothing else adjudicates.
SCIENTIFIC_FUNCTION = _engine.analyze

analyze = _engine.analyze
analyze_endpoint = _api.analyze_endpoint
analyze_archive_endpoint = _api.analyze_archive_endpoint
analyze_batch = _api.analyze_batch
aggregate_attempt_archive = _ingest.aggregate_attempt_archive
cli_main = _cli.main

ENGINE_MODULE = _engine
API_MODULE = _api
CLI_MODULE = _cli
INGEST_MODULE = _ingest


def wrapper_targets():
    """Every wrapper and the function object it actually reaches.

    Used by the wrapper-termination proof. ``api`` and ``cli`` both import
    ``analyze`` from the engine module, so identity comparison of the bound
    objects is the exact question being asked.
    """
    return {
        "engine.analyze": _engine.analyze,
        "api.analyze_endpoint": _api.analyze,
        "api.analyze_archive_endpoint": _api.analyze,
        "api.analyze_batch": _api.analyze,
        "cli.analyze": _cli.analyze,
    }


def describe():
    return {
        "vendor_path": os.path.relpath(VENDOR, ROOT),
        "engine_version": ENGINE_VERSION,
        "release_manifest_sha256": RELEASE_MANIFEST_SHA256,
        "engine_source_files_verified": ENGINE_SOURCE_FILES_VERIFIED,
        "scientific_function": "ordinal_engine.engine.analyze",
        "second_engine_present": False,
        "alternate_adjudication_path_present": False,
    }
