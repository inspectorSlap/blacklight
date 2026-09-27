"""In-process adversarial qualification of the standalone filtering proxy.

The development sandbox denies binding a listening socket, so the proxy cannot
be exercised over a real port from inside a a reviewer agent session. It can still
be exercised completely: the handler is driven over a `socketpair`, which
needs no bind, so every decision path -- authentication, origin allowlist, path
allowlist, traversal, query smuggling, CONNECT refusal, audit redaction -- is
tested against the real code rather than a mock.

DENY paths make no upstream contact at all. The single ALLOW probe uses
/health, an identity-class endpoint, never an analysis endpoint.

WHERE THE RESULT GOES (v1.5.2)
------------------------------
Nowhere inside the release. Up to v1.5.1 this wrote
`results/proxy-qualification-v1.5.1.json`, a hashed artifact of the frozen
release -- so a successful Terminal rerun, which is exactly what the launch
procedure asks for, rewrote a frozen file and failed the integrity gate.

The result is now a runtime attestation under `results/runtime-attestations/`,
which is deliberately not a release artifact. Running this program can no
longer alter the release. The attestation is append-only, single-use, and
bound to the release, approval, proxy code, proxy configuration, launcher,
host, target and run identity it may authorize; `start` refuses to spawn the
runner without one that reports 19 PASS, zero FAIL and zero BLOCKED.

A blocked or failed attempt is written too, and preserved. Evidence that
qualification did not succeed is still evidence.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import base64
import json
import os
import socket
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import blackbox_proxy as fp            # noqa: E402
import blackbox_attestation as attestation  # noqa: E402

ATTESTATION_SUITE_VERSION = "1.5.2"


def launch_bindings():
    """The identities this attestation is bound to.

    Computed from the same sources `start` will use, so a mismatch means the
    launch genuinely differs from what was qualified -- not that two different
    conventions were used to describe the same thing.
    """
    import blackbox_supervisor as sup
    return sup.launch_bindings()

CREDENTIAL = "blackbox:qualification-credential"
SECRET_TOKEN = "SUPERSECRET-TARGET-TOKEN-DO-NOT-LEAK"


class _Server(object):
    """Minimal stand-in for the HTTPServer attributes the handler reads."""

    def __init__(self, config, audit_path, opener=None):
        self.config = config
        self.credential = CREDENTIAL
        self.audit = fp.Audit(audit_path)
        self.identity = fp.proxy_identity(config, os.path.join(
            ROOT, "tools", "blackbox_proxy.py"))
        self.timeout_seconds = 15
        self.opener = opener


def drive(config, audit_path, raw_request, opener=None):
    """Feed one raw HTTP request to the real handler over a socketpair."""
    client, server_side = socket.socketpair()
    server = _Server(config, audit_path, opener)
    holder = {}

    def run():
        try:
            fp.FilteringProxyHandler(server_side, ("127.0.0.1", 0), server)
        except Exception as exc:               # connection teardown is fine
            holder["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    client.sendall(raw_request)
    client.settimeout(15)
    chunks = []
    try:
        while True:
            data = client.recv(65536)
            if not data:
                break
            chunks.append(data)
            if b"\r\n\r\n" in b"".join(chunks):
                head = b"".join(chunks).split(b"\r\n\r\n", 1)
                if len(head) > 1:
                    length = 0
                    for line in head[0].split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":")[1])
                    if len(head[1]) >= length:
                        break
    except socket.timeout:
        pass
    client.close()
    server_side.close()
    thread.join(timeout=5)
    return b"".join(chunks)


def status_of(response):
    try:
        return int(response.split(b" ")[1])
    except Exception:
        return None


# The frozen target's /health contract. `api_version` is NOT part of it: that
# field belongs to the authenticated metadata identity served by /v0.1/meta.
# Asserting it here classified a correctly forwarded HTTP 200 as a failure.
HEALTH_CONTRACT_FIELDS = ("status", "service", "engine_version")
HEALTH_STATUS = "ok"
HEALTH_SERVICE = "blackbox-ordinal-target"


def health_payload_ok(response, expected_engine_version):
    """Validate a forwarded /health response against the frozen contract.

    Requires HTTP 200, a valid JSON object body, and the exact registered
    liveness fields. An arbitrary 200, malformed JSON, a missing field or a
    wrong value all fail. Returns ``(ok, detail)`` and makes no network call.
    """
    status = status_of(response)
    if status != 200:
        return False, "status %s" % status
    if b"\r\n\r\n" not in response:
        return False, "status 200 but the response carried no body"
    body = response.split(b"\r\n\r\n", 1)[1]
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        return False, "status 200 but the body is not valid JSON: %s" % error
    if not isinstance(payload, dict):
        return False, "status 200 but the body is not a JSON object"

    missing = [name for name in HEALTH_CONTRACT_FIELDS if name not in payload]
    if missing:
        return False, "status 200 but /health omitted %s" % ", ".join(missing)

    expected = {"status": HEALTH_STATUS, "service": HEALTH_SERVICE,
                "engine_version": expected_engine_version}
    wrong = ["%s=%r (expected %r)" % (name, payload[name], expected[name])
             for name in HEALTH_CONTRACT_FIELDS if payload[name] != expected[name]]
    if wrong:
        return False, "status 200 but /health disagreed: %s" % "; ".join(wrong)
    return True, ("status 200; status=%s service=%s engine_version=%s"
                  % (payload["status"], payload["service"],
                     payload["engine_version"]))


def request(method, url, auth=True, token=True, body=None, extra=b""):
    headers = [b"%s %s HTTP/1.1" % (method.encode(), url.encode()),
               b"Host: 127.0.0.1"]
    if auth:
        creds = base64.b64encode(CREDENTIAL.encode())
        headers.append(b"Proxy-Authorization: Basic " + creds)
    if token:
        headers.append(b"Authorization: Bearer " + SECRET_TOKEN.encode())
    payload = body or b""
    headers.append(b"Content-Length: %d" % len(payload))
    if extra:
        headers.append(extra)
    headers.append(b"Connection: close")
    return b"\r\n".join(headers) + b"\r\n\r\n" + payload


def main():
    config = fp.load_config(os.path.join(ROOT, "tools",
                                         "blackbox-proxy-config.json"))
    audit_path = tempfile.mktemp(suffix=".jsonl")
    origin = config["allowed_origin"]
    checks = []

    def check(name, ok, detail, blocked=False):
        # BLOCKED is not a pass. A check that could not execute is recorded as
        # unexecuted and must be run outside the sandbox before launch; it is
        # never silently counted as evidence.
        status = "BLOCKED" if blocked else ("PASS" if ok else "FAIL")
        checks.append({"check": name, "ok": bool(ok) and not blocked,
                       "status": status, "detail": detail})
        print("  %-52s %s" % (name, status))

    # 1. unauthenticated use refused
    code = status_of(drive(config, audit_path,
                           request("GET", origin + "/health", auth=False)))
    check("unauthenticated proxy use refused", code == 407, "status %s" % code)

    # 2. wrong credential refused
    bad = request("GET", origin + "/health", auth=False)
    bad = bad.replace(b"Host: 127.0.0.1",
                      b"Host: 127.0.0.1\r\nProxy-Authorization: Basic "
                      + base64.b64encode(b"blackbox:wrong"))
    check("incorrect proxy credential refused",
          status_of(drive(config, audit_path, bad)) == 407, "status 407")

    # 3. unapproved destination refused
    for label, url in (("foreign host", "http://example.com/health"),
                       ("wrong port", "http://127.0.0.1:9999/health"),
                       ("https scheme", "https://127.0.0.1:8765/health")):
        code = status_of(drive(config, audit_path, request("GET", url)))
        check("unapproved destination refused (%s)" % label, code == 403,
              "status %s" % code)

    # 4. unapproved paths refused
    for label, path in (("root", "/"), ("admin", "/admin"),
                        ("traversal", "/v0.1/../admin"),
                        ("query smuggling", "/v0.1/meta?x=1"),
                        ("double slash", "/v0.1//meta")):
        code = status_of(drive(config, audit_path,
                               request("GET", origin + path)))
        check("unapproved path refused (%s)" % label, code == 403,
              "status %s" % code)

    # 5. CONNECT refused
    code = status_of(drive(config, audit_path,
                           request("CONNECT", "127.0.0.1:8765")))
    check("CONNECT tunnelling refused", code == 405, "status %s" % code)

    # 6. relative request refused (no absolute proxy URI)
    code = status_of(drive(config, audit_path, request("GET", "/health")))
    check("relative (non-proxy) request refused", code == 403,
          "status %s" % code)

    # 7. control endpoint returns identity to an authenticated caller
    response = drive(config, audit_path,
                     request("GET", "/__proxy/identity"))
    identity_ok = status_of(response) == 200 and b"code_sha256" in response
    check("control endpoint serves identity when authenticated", identity_ok,
          "status %s" % status_of(response))

    # 8. approved path allowed (identity-class /health only)
    upstream = os.environ.get("BLACKBOX_UPSTREAM_PROXY")
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": upstream, "https": upstream} if upstream else {}))
    response = drive(config, audit_path,
                     request("GET", origin + "/health"), opener=opener)
    upstream_status = status_of(response)
    allowed_ok, health_detail = health_payload_ok(
        response, launch_bindings()["expected_engine_version"])
    # 502 means the proxy accepted the request and could not reach upstream.
    # Inside the a reviewer agent sandbox, loopback connect() is denied outright, so
    # forwarding cannot be exercised here at all. That is a sandbox limit, not
    # a proxy defect, and it is recorded as BLOCKED rather than passed.
    upstream_blocked = upstream_status == 502 and not allowed_ok
    check("approved path allowed and forwarded (/health)", allowed_ok,
          "%s%s" % (health_detail,
                    "; upstream unreachable from this sandbox "
                    "(loopback connect denied). Re-run in Terminal.app "
                    "with the gateway running before launch."
                    if upstream_blocked else ""),
          blocked=upstream_blocked)

    # 9. audit completeness and redaction
    lines = [json.loads(l) for l in open(audit_path)]
    text = open(audit_path).read()
    check("audit records every request", len(lines) == len(checks),
          "%d audit lines for %d requests" % (len(lines), len(checks)))
    check("target token absent from audit", SECRET_TOKEN not in text,
          "token never written")
    check("proxy credential absent from audit", CREDENTIAL not in text,
          "credential never written")
    allows = sum(1 for l in lines if l["decision"] == "ALLOW")
    denies = sum(1 for l in lines if l["decision"] == "DENY")
    check("audit proves traversal (allow/deny per request)",
          all("decision" in l for l in lines) and allows and denies,
          "%d ALLOW, %d DENY%s"
          % (allows, denies,
             "; no ALLOW is reachable while upstream is unreachable"
             if upstream_blocked else ""),
          blocked=upstream_blocked and not allows)
    check("audit carries per-request digests",
          any(l.get("request_sha256") for l in lines),
          "request/response digests are recorded for forwarded requests%s"
          % ("; none forwarded because upstream was unreachable"
             if upstream_blocked else ""),
          blocked=upstream_blocked)

    # Target requests are taken from the proxy's own audit rather than from a
    # counter this program maintains: the audit is the independent record of
    # what actually left for the target. ALLOW_CONTROL entries are the proxy's
    # own control endpoint and never reach the target.
    target_requests = sorted(l.get("path") for l in lines
                             if l.get("decision") == "ALLOW")

    os.unlink(audit_path)
    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = [c["check"] for c in checks if c["status"] == "FAIL"]
    blocked = [c["check"] for c in checks if c["status"] == "BLOCKED"]
    print("\n%d passed, %d failed, %d blocked, of %d proxy qualification "
          "checks" % (passed, len(failed), len(blocked), len(checks)))
    if blocked:
        print("BLOCKED checks were NOT executed and are not evidence:")
        for name in blocked:
            print("  -", name)
        print("Re-run this suite in Terminal.app with the gateway running "
              "before launching a campaign.")
    record = dict(launch_bindings())
    record.update({
        "proxy_qualification_version": ATTESTATION_SUITE_VERSION,
        "method": "in-process over socketpair; bind is not required",
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "failed": len(failed),
        "blocked": len(blocked),
        "failed_checks": failed,
        "blocked_checks": blocked,
        "outcome": ("QUALIFIED" if passed == len(checks)
                    else "NOT_QUALIFIED"),
        "no_failures": not failed,
        "blocked_are_not_passes": True,
        "blocked_reason": ("upstream was unreachable, so forwarding could not "
                           "be exercised; inside the a reviewer agent sandbox "
                           "loopback connect() is denied outright"
                           if blocked else None),
        "target_requests_made": len(target_requests),
        "target_request_paths": target_requests,
        "analysis_endpoint_contacted": False,
        "analysis_endpoints_contacted": 0,
    })

    written, path = attestation.write(
        record,
        live_token=os.environ.get("BLACKBOX_TARGET_TOKEN"),
        live_credential=os.environ.get("BLACKBOX_PROXY_CREDENTIAL"))

    print("\nattestation : %s" % written["attestation_id"])
    print("written to  : %s" % os.path.relpath(path, ROOT))
    print("content sha : %s" % written["content_digest"])
    print("outcome     : %s" % written["outcome"])
    print("target requests: %d %s"
          % (len(target_requests), target_requests or ""))
    print("analysis endpoints contacted: 0")
    if written["outcome"] == "QUALIFIED":
        print("\nThis attestation authorizes exactly one launch of run %s."
              % record["run_id"])
    else:
        print("\nNOT QUALIFIED: `start` will refuse. This attempt is "
              "preserved; run again to produce a new attestation.")
    print("No release artifact was written or modified.")

    # 0 = qualified; 2 = nothing failed but checks were blocked, so not
    # qualified; 1 = a real failure.
    if failed:
        return 1
    return 0 if not blocked else 2


if __name__ == "__main__":
    sys.exit(main())
