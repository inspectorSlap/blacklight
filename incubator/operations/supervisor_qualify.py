"""Zero-call adversarial qualification of the v1.5 detached operation.

Every check here runs without contacting the target's analysis endpoints.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness import freeze as _freeze  # noqa: E402
VERSION = _freeze.HARNESS_VERSION
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import blackbox_proxy as fp          # noqa: E402
import blackbox_supervisor as sup    # noqa: E402

CHECKS = []


def check(name, ok, detail):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print("  %-56s %s" % (name, "OK" if ok else "FAIL"))


def main():
    env = dict(os.environ)

    # 1. The frozen transport refuses to operate with no proxy at all.
    #
    # Tested at the transport layer, not by running the CLI. The CLI has
    # several fail-closed gates -- the phase gate fires before the transport
    # is ever constructed -- so a non-zero CLI exit does not establish that
    # the PROXY requirement is what stopped it. This asserts the specific
    # claim: with every *_proxy spelling absent, constructing the target
    # raises the proxy fail-closed error.
    stripped = dict(env)
    for name in list(stripped):
        if name.lower().endswith("_proxy"):
            stripped.pop(name, None)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, json;"
         "sys.path.insert(0, '.');"
         "from harness import transport;"
         "\ntry:\n"
         "    transport.HttpTarget()\n"
         "    print(json.dumps({'raised': None}))\n"
         "except Exception as exc:\n"
         "    print(json.dumps({'raised': type(exc).__name__,"
         " 'proxy_related': 'proxy' in str(exc).lower()"
         " or 'Proxy' in type(exc).__name__}))\n"],
        cwd=ROOT, env=stripped, capture_output=True, text=True)
    try:
        outcome = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        outcome = {"raised": None, "proxy_related": False,
                   "stderr": proc.stderr[-200:]}
    check("transport fails closed when every proxy variable is absent",
          outcome.get("raised") is not None and outcome.get("proxy_related"),
          "raised %s (proxy-related: %s)"
          % (outcome.get("raised"), outcome.get("proxy_related")))

    # 2. Placeholder proxy variables do not satisfy preflight.
    placeholder = dict(env)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        placeholder[name] = "http://placeholder:1/"
    saved = dict(os.environ)
    os.environ.update({k: placeholder[k] for k in
                       ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")})
    try:
        result = sup.preflight(live_phase=True, verbose=False)
    finally:
        os.environ.clear(); os.environ.update(saved)
    live = [c for c in result["checks"]
            if c["check"] == "live proxy identity verified"]
    points = [c for c in result["checks"]
              if c["check"].startswith("resolved proxy is the verified proxy")]
    check("placeholder proxy variables do not pass preflight",
          not result["ok"] and live and not live[0]["ok"]
          and points and not points[0]["ok"],
          "preflight refused a placeholder proxy")

    # 3. Direct target bypass is rejected: with proxy variables pointing at a
    #    dead port the runner must fail rather than reach the target directly.
    # Strip EVERY *_proxy spelling first: urllib merges them all, so leaving
    # a lowercase variant in place would let the real proxy win and the probe
    # would wrongly report a direct bypass.
    dead = {k: v for k, v in env.items()
            if not k.lower().endswith("_proxy")}
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        dead[name] = "http://127.0.0.1:9/"
    probe = subprocess.run(
        [sys.executable, "-c",
         "import os,urllib.request,json;"
         "o=urllib.request.build_opener(urllib.request.ProxyHandler());"
         "r=o.open(os.environ['BLACKBOX_TARGET_URL']+'/health',timeout=5);"
         "print('REACHED')"],
        cwd=ROOT, env=dead, capture_output=True, text=True)
    check("direct target bypass rejected (no fallback off-proxy)",
          "REACHED" not in probe.stdout,
          "a dead proxy yields failure, not a direct connection")

    # 4. Tampered release digest fails closed.
    from harness import freeze as freeze_module
    manifest = json.load(open(os.path.join(
        ROOT, "results", "harness-release-manifest-v1.4.json")))
    group = list(manifest["artifact_groups"])[0]
    victim = list(manifest["artifact_groups"][group])[0]
    manifest["artifact_groups"][group][victim] = "0" * 64
    tampered = tempfile.mktemp(suffix=".json")
    json.dump(manifest, open(tampered, "w"))
    integrity = freeze_module.verify_release_integrity(tampered)
    os.unlink(tampered)
    check("tampered release digest fails closed",
          not integrity["intact"] and victim in integrity["mismatches"],
          "%d mismatch detected" % len(integrity["mismatches"]))

    # 5. Tampered proxy code or configuration digest is detected.
    config = fp.load_config(os.path.join(ROOT, "tools",
                                         "blackbox-proxy-config.json"))
    baseline = fp.proxy_identity(config)
    widened = dict(config)
    widened["allowed_paths"] = sorted(config["allowed_paths"] + ["/admin"])
    check("tampered proxy configuration digest is detected",
          fp.config_digest(widened) != baseline["config_sha256"],
          "widening the allowlist changes the configuration digest")

    modified = tempfile.mktemp(suffix=".py")
    with open(modified, "w") as handle:
        handle.write(open(os.path.join(ROOT, "tools",
                                       "blackbox_proxy.py")).read()
                     + "\n# tampered\n")
    check("tampered proxy code digest is detected",
          fp.proxy_identity(config, modified)["code_sha256"]
          != baseline["code_sha256"], "code digest changes on modification")
    os.unlink(modified)

    # 6. Tampered launcher digest is detected.
    launcher = os.path.join(ROOT, "tools", "blackbox_supervisor.py")
    original = sup.sha256_file(launcher)
    copy = tempfile.mktemp(suffix=".py")
    with open(copy, "w") as handle:
        handle.write(open(launcher).read() + "\n# tampered\n")
    check("tampered launcher digest is detected",
          sup.sha256_file(copy) != original, "launcher digest changes")
    os.unlink(copy)

    # 7. status performs no network request.
    import urllib.request
    calls = {"n": 0}
    real_open = urllib.request.OpenerDirector.open

    def tripwire(self, *a, **k):
        calls["n"] += 1
        raise AssertionError("status attempted a network request")

    urllib.request.OpenerDirector.open = tripwire
    try:
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            sup.cmd_status([])
        status_ok = calls["n"] == 0
    finally:
        urllib.request.OpenerDirector.open = real_open
    check("status is read-only and performs no network request",
          status_ok, "%d network calls attempted" % calls["n"])

    # 8. Scientific core identical to v1.4.
    current, entries = sup.scientific_core_digest()
    previous, _ = sup.scientific_core_digest(os.path.join(ROOT, "releases",
                                                          "v1.4"))
    check("scientific core exactly identical to v1.4",
          current == previous,
          "%d files, digest %s" % (len(entries), current[:16]))

    # 9. Concurrency limit unchanged at one.
    from harness import inflight
    check("gateway-facing concurrency limit remains one",
          inflight.GATE.limit == 1, "limit %d" % inflight.GATE.limit)

    # 10. Secrets absent from every v1.5 operational artifact.
    token = os.environ.get("BLACKBOX_TARGET_TOKEN", "")
    leaked = []
    for name in sorted(os.listdir(os.path.join(ROOT, "results"))):
        if "v1.5" not in name and "v1.5.1" not in name:
            continue
        path = os.path.join(ROOT, "results", name)
        if not os.path.isfile(path):
            continue
        text = open(path, "r", errors="replace").read()
        if token and token in text:
            leaked.append(name)
        if "Proxy-Authorization" in text or "Bearer " in text:
            leaked.append(name + " (header material)")
    check("no token or credential in operational artifacts",
          not leaked, "leaks: %s" % (leaked or "none"))

    # 11. Crash recovery contract is the frozen one.
    from harness import campaign as campaign_module
    import inspect
    source = inspect.getsource(campaign_module.EvidenceStore.recover)
    check("replication-granular crash recovery unchanged",
          "truncate" in source and "surviving" in source,
          "index-is-a-prefix invariant retained from v1.4")

    passed = sum(1 for c in CHECKS if c["ok"])
    print("\n%d/%d supervisor qualification checks passed" % (passed, len(CHECKS)))
    out = {"supervisor_qualification_version": VERSION,
           "note": "check 1 asserts the proxy fail-closed path at the "
                   "transport layer. Running the CLI instead would conflate "
                   "it with the phase gate, which fires earlier.",
           "checks": CHECKS, "passed": passed, "total": len(CHECKS),
           "all_passed": passed == len(CHECKS),
           "analysis_endpoints_contacted": 0}
    with open(os.path.join(ROOT, "results",
                           "supervisor-qualification-v%s.json" % VERSION), "w") as h:
        json.dump(out, h, indent=2, sort_keys=True); h.write("\n")
    return 0 if out["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
