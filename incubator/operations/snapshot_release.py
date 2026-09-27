"""Immutable, separately addressable release snapshots.

DELIBERATELY OUTSIDE THE HASHED RELEASE
---------------------------------------
This tool lives under `tools/` and is NOT listed in `ARTIFACT_GROUPS`, so it is
not one of the artifacts the release manifest hashes. That is not an oversight:
if the snapshot mechanism were part of the release it hashes, adding or editing
it would change the very digest it is meant to preserve. Keeping it outside
breaks that circularity, at the cost that the tool itself is not covered by the
release digest -- a trade recorded here rather than hidden.

GUARANTEES
----------
* **Refuses to overwrite.** A snapshot aborts if either the version directory
  or the content-addressed directory already exists and is non-empty. There is
  no force flag.
* **Two addresses, one content.** Each release is written to
  `releases/<version>/` and to `releases/by-digest/<release_digest>/`. Both are
  full copies, not links: a link would make the "immutable" copy mutate
  whenever its target did.
* **Byte-for-byte verification.** Every artifact is checked against its
  per-artifact digest from the manifest, and the release digest is recomputed
  from the copied files and compared against the expected value.
* **Advisory immutability.** Snapshot files are set read-only (0444) and their
  directories to 0555. This is a guard against accident, not a security
  control: anyone with ownership can chmod it back. Stated plainly rather than
  overclaimed.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import json
import os
import shutil
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASES = os.path.join(ROOT, "releases")
BY_DIGEST = os.path.join(RELEASES, "by-digest")


class SnapshotRefused(Exception):
    """Raised when a snapshot would overwrite an existing release."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _artifact_map(manifest):
    flat = {}
    for entries in manifest["artifact_groups"].values():
        for path, digest in entries.items():
            if digest:
                flat[path] = digest
    return flat


def _occupied(path):
    return os.path.isdir(path) and any(os.scandir(path))


def _make_read_only(root):
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            target = os.path.join(dirpath, name)
            os.chmod(target, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        for name in dirnames:
            target = os.path.join(dirpath, name)
            os.chmod(target, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP
                     | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    os.chmod(root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
             | stat.S_IROTH | stat.S_IXOTH)


def _copy_into(artifact_map, destination, manifest_path):
    for relative in sorted(artifact_map):
        source = os.path.join(ROOT, relative)
        target = os.path.join(destination, relative)
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copy2(source, target)
    shutil.copy2(manifest_path,
                 os.path.join(destination, os.path.basename(manifest_path)))


def verify_snapshot(destination, manifest, expected_digest):
    """Byte-for-byte verification of a snapshot against its manifest."""
    artifact_map = _artifact_map(manifest)
    mismatched, missing = [], []
    recomputed = {}
    for relative, digest in sorted(artifact_map.items()):
        target = os.path.join(destination, relative)
        if not os.path.isfile(target):
            missing.append(relative)
            continue
        actual = sha256_file(target)
        recomputed[relative] = actual
        if actual != digest:
            mismatched.append(relative)
    recomputed_release = canonical_digest(recomputed)
    return {
        "artifacts_expected": len(artifact_map),
        "artifacts_verified": len(recomputed) - len(mismatched),
        "missing": missing,
        "mismatched": mismatched,
        "recomputed_release_digest": recomputed_release,
        "expected_release_digest": expected_digest,
        "release_digest_matches": recomputed_release == expected_digest,
        "byte_for_byte_ok": (not missing and not mismatched
                             and recomputed_release == expected_digest),
    }


def snapshot(manifest_path, version_label, expected_digest=None):
    with open(manifest_path, "r") as handle:
        manifest = json.load(handle)
    release_digest = manifest["release_digest"]
    if expected_digest and release_digest != expected_digest:
        raise SnapshotRefused(
            "manifest release digest %s does not match the expected %s"
            % (release_digest, expected_digest))

    version_dir = os.path.join(RELEASES, version_label)
    digest_dir = os.path.join(BY_DIGEST, release_digest)

    # Refuse to overwrite. No force flag exists.
    for label, path in (("version", version_dir),
                        ("content-addressed", digest_dir)):
        if _occupied(path):
            raise SnapshotRefused(
                "refusing to overwrite the existing %s release directory %s. "
                "A release snapshot is immutable; publish a new version "
                "instead." % (label, os.path.relpath(path, ROOT)))

    artifact_map = _artifact_map(manifest)
    results = {}
    for label, destination in (("version", version_dir),
                               ("content_addressed", digest_dir)):
        if not os.path.isdir(destination):
            os.makedirs(destination)
        _copy_into(artifact_map, destination, manifest_path)
        results[label] = verify_snapshot(destination, manifest, release_digest)

    record = {
        "snapshot_version": version_label,
        "release_id": manifest["release_id"],
        "harness_version": manifest["harness_version"],
        "release_digest": release_digest,
        "artifact_count": manifest["artifact_count"],
        "addresses": {
            "version_path": os.path.relpath(version_dir, ROOT),
            "content_addressed_path": os.path.relpath(digest_dir, ROOT),
        },
        "verification": results,
        "immutability": {
            "mode": "read-only (0444 files, 0555 directories)",
            "enforced_by": "filesystem permissions",
            "honest_limitation": (
                "advisory only: an owner can restore write permission. This "
                "guards against accident, not against a determined change, and "
                "is not a security control."),
        },
        "overwrite_policy": "refuses to overwrite an existing version or "
                            "content-addressed release directory; no force flag",
    }

    for destination in (version_dir, digest_dir):
        with open(os.path.join(destination, "SNAPSHOT-MANIFEST.json"), "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        _make_read_only(destination)
    return record


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        sys.stderr.write("usage: snapshot_release.py <manifest> <version> "
                         "[expected-digest]\n")
        return 2
    manifest_path = os.path.join(ROOT, argv[0])
    expected = argv[2] if len(argv) > 2 else None
    try:
        record = snapshot(manifest_path, argv[1], expected)
    except SnapshotRefused as exc:
        sys.stderr.write("SNAPSHOT_REFUSED: %s\n" % exc)
        return 3
    print(json.dumps(record, indent=2, sort_keys=True))
    ok = all(entry["byte_for_byte_ok"] for entry in record["verification"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
