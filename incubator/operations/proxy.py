"""Standalone filtering proxy for the ordinal-profile black-box target (v1.5).

PURPOSE
-------
The development sandbox supplied a filtering proxy through reviewer agent-Code-injected
environment variables. A detached campaign cannot rely on that. This proxy is a
standalone stdlib process that reproduces the *routing* guarantee the frozen
runner depends on, with no reviewer agent-provided environment or process.

WHAT IT GUARANTEES
------------------
* Only the exact approved target origin is reachable. Any other host, port or
  scheme is refused.
* Only the approved paths are reachable: health, metadata, analysis and the
  batch contract. Any other path is refused, including path traversal and
  query-string smuggling.
* `CONNECT` is refused outright. The target is plain HTTP on loopback, so
  tunnelling has no legitimate use here and would defeat path filtering.
* It binds to loopback only and refuses unauthenticated use.
* It never logs, echoes or stores the target bearer token, nor its own proxy
  credential.
* It writes an append-only audit line for every request it handles, sufficient
  to prove that a given target request traversed the proxy.
* It fails closed on an invalid configuration, an absent token, an empty
  allowlist, or a non-loopback bind.

WHAT IT DOES NOT CLAIM
----------------------
This is a routing control, not an OS sandbox. It constrains what the *runner*
can reach through it; it does not prevent some other process on the host from
opening its own socket. That distinction is recorded in the v1.5 release notes
rather than papered over: OS-level containment protected independent harness
*construction*, and is not what supplies execution integrity for an already
frozen deterministic runner.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import base64
import datetime
import hashlib
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ROOT, "tools", "blackbox-proxy-config.json")

PROXY_VERSION = "1.5"
AUDIT_VERSION = "1.5"

# Headers that must never be written to the audit or any report.
REDACTED_HEADERS = ("authorization", "proxy-authorization", "cookie",
                    "x-api-key")


class ConfigurationError(Exception):
    """Raised when the proxy cannot start safely. Always fails closed."""


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


def load_config(path=DEFAULT_CONFIG):
    if not os.path.isfile(path):
        raise ConfigurationError("proxy configuration not found: %s" % path)
    with open(path, "r") as handle:
        config = json.load(handle)

    for key in ("allowed_origin", "allowed_paths", "bind_host", "bind_port",
                "audit_path"):
        if key not in config:
            raise ConfigurationError("configuration is missing %r" % key)

    origin = urllib.parse.urlsplit(config["allowed_origin"])
    if origin.scheme != "http" or not origin.hostname:
        raise ConfigurationError("allowed_origin must be an http:// origin")
    if origin.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ConfigurationError(
            "allowed_origin must be loopback; refusing %r" % origin.hostname)
    if not config["allowed_paths"]:
        raise ConfigurationError("allowlist is empty; refusing to start")
    if config["bind_host"] not in ("127.0.0.1", "localhost", "::1"):
        raise ConfigurationError(
            "bind_host must be loopback; refusing %r" % config["bind_host"])
    return config


def config_digest(config):
    """Digest of the security-relevant configuration only."""
    return canonical_digest({
        "allowed_origin": config["allowed_origin"],
        "allowed_paths": sorted(config["allowed_paths"]),
        "bind_host": config["bind_host"],
        "bind_port": config["bind_port"],
    })


def proxy_identity(config, code_path=None):
    code_path = code_path or os.path.abspath(__file__)
    return {
        "proxy_version": PROXY_VERSION,
        "code_sha256": sha256_file(code_path),
        "config_sha256": config_digest(config),
        "allowed_origin": config["allowed_origin"],
        "allowed_paths": sorted(config["allowed_paths"]),
        "bind": "%s:%s" % (config["bind_host"], config["bind_port"]),
        "connect_permitted": False,
        "token_logged": False,
        "upstream_chained": None,
        "upstream_digest": None,
    }


class Audit(object):
    """Append-only operational audit. Bodies and credentials never enter it."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)

    def write(self, record):
        record = dict(record)
        record["audit_version"] = AUDIT_VERSION
        # Timezone-aware UTC. Identical instant and identical rendering to
        # the naive utcnow() this replaced, including microseconds.
        record["timestamp_utc"] = datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._lock:
            with open(self.path, "a") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


class FilteringProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BLACKBOXFilteringProxy/1.5.1"
    sys_version = ""

    # -- helpers -----------------------------------------------------------

    def log_message(self, fmt, *args):
        """Silence the default stderr log; the audit is the record."""

    def _audit(self, decision, status, **extra):
        record = {
            "decision": decision,
            "method": self.command,
            "status": status,
            "client": self.client_address[0],
            "proxy_pid": os.getpid(),
        }
        record.update(extra)
        self.server.audit.write(record)

    def _refuse(self, status, code, detail, **extra):
        body = json.dumps({"error": {"code": code, "message": detail}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self._audit("DENY", status, denial_code=code, detail=detail, **extra)

    def _authenticated(self):
        header = self.headers.get("Proxy-Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except Exception:
            return False
        # Constant-time-ish comparison; the credential is never logged.
        expected = self.server.credential
        if len(decoded) != len(expected):
            return False
        mismatch = 0
        for a, b in zip(decoded, expected):
            mismatch |= ord(a) ^ ord(b)
        return mismatch == 0

    def _check_target(self, raw_path):
        """Return (origin, path) if permitted, else raise ValueError."""
        parts = urllib.parse.urlsplit(raw_path)
        if not parts.scheme:
            raise ValueError("relative request; an absolute proxy URI is required")
        origin = "%s://%s" % (parts.scheme, parts.netloc)
        allowed_origin = self.server.config["allowed_origin"].rstrip("/")
        if origin.rstrip("/") != allowed_origin:
            raise ValueError("origin %r is not the approved target" % origin)
        path = parts.path or "/"
        if ".." in path or "//" in path:
            raise ValueError("path traversal is refused")
        if path not in self.server.config["allowed_paths"]:
            raise ValueError("path %r is not on the allowlist" % path)
        if parts.query:
            raise ValueError("query strings are refused on this allowlist")
        return origin, path

    # -- verbs -------------------------------------------------------------

    def do_CONNECT(self):
        self._refuse(405, "CONNECT_REFUSED",
                     "CONNECT tunnelling is refused; it would defeat path "
                     "filtering", path="<connect>")

    def _handle(self):
        # Local control endpoint: identity, for preflight verification.
        if self.path in ("/__proxy/identity", "/__proxy/health"):
            if not self._authenticated():
                return self._refuse(407, "PROXY_AUTH_REQUIRED",
                                    "unauthenticated proxy use is refused",
                                    path=self.path)
            body = json.dumps(self.server.identity).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return self._audit("ALLOW_CONTROL", 200, path=self.path)

        if not self._authenticated():
            return self._refuse(407, "PROXY_AUTH_REQUIRED",
                                "unauthenticated proxy use is refused",
                                path="<redacted>")

        try:
            origin, path = self._check_target(self.path)
        except ValueError as exc:
            return self._refuse(403, "DESTINATION_REFUSED", str(exc),
                                requested=self.path[:200])

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        request_digest = hashlib.sha256(body or b"").hexdigest()

        # Forward. The target token rides in the Authorization header and is
        # passed through untouched and unlogged.
        forward = urllib.request.Request(origin + path, data=body,
                                         method=self.command)
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in REDACTED_HEADERS and lowered != "authorization":
                continue
            if lowered in ("proxy-authorization", "proxy-connection",
                           "connection", "host", "content-length"):
                continue
            forward.add_header(name, value)
        if body is not None:
            forward.add_header("Content-Length", str(len(body)))

        try:
            with self.server.opener.open(
                    forward, timeout=self.server.timeout_seconds) as up:
                status = up.status
                payload = up.read()
                headers = [(k, v) for k, v in up.headers.items()
                           if k.lower() not in ("transfer-encoding",
                                                "connection",
                                                "content-length")]
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            headers = [(k, v) for k, v in exc.headers.items()
                       if k.lower() not in ("transfer-encoding", "connection",
                                            "content-length")]
        except Exception as exc:
            return self._refuse(502, "UPSTREAM_ERROR",
                                "%s" % type(exc).__name__, path=path)

        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

        self._audit("ALLOW", status, path=path, origin=origin,
                    request_bytes=len(body or b""),
                    response_bytes=len(payload),
                    request_sha256=request_digest,
                    response_sha256=hashlib.sha256(payload).hexdigest())

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle
    do_HEAD = _handle


class ThreadedProxy(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(config, credential, code_path=None):
    if not credential:
        raise ConfigurationError("proxy credential is absent; refusing to start")
    address = (config["bind_host"], int(config["bind_port"]))
    server = ThreadedProxy(address, FilteringProxyHandler)
    server.config = config
    server.credential = credential
    server.audit = Audit(config["audit_path"])
    server.identity = proxy_identity(config, code_path)
    server.timeout_seconds = int(config.get("upstream_timeout_seconds", 120))

    # Upstream route. On an independent host the proxy connects directly to
    # the loopback target. Inside the development sandbox a direct loopback
    # socket is blocked, so an upstream proxy may be chained. Its VALUE is
    # never recorded -- only whether chaining is in use, and a digest.
    upstream = os.environ.get("BLACKBOX_UPSTREAM_PROXY")
    if upstream:
        server.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": upstream, "https": upstream}))
        server.identity["upstream_chained"] = True
        server.identity["upstream_digest"] = hashlib.sha256(
            upstream.encode()).hexdigest()[:16]
    else:
        server.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))
        server.identity["upstream_chained"] = False
        server.identity["upstream_digest"] = None
    return server


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    config_path = argv[0] if argv else DEFAULT_CONFIG
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        sys.stderr.write("PROXY_FAIL_CLOSED: %s\n" % exc)
        return 2

    credential = os.environ.get("BLACKBOX_PROXY_CREDENTIAL")
    if not credential:
        sys.stderr.write("PROXY_FAIL_CLOSED: BLACKBOX_PROXY_CREDENTIAL is not "
                         "set; unauthenticated proxies are refused\n")
        return 2
    if not os.environ.get("BLACKBOX_TARGET_TOKEN"):
        sys.stderr.write("PROXY_FAIL_CLOSED: BLACKBOX_TARGET_TOKEN is absent; "
                         "refusing to start a route to an unauthenticated "
                         "target\n")
        return 2

    try:
        server = build_server(config, credential)
    except (ConfigurationError, socket.error) as exc:
        sys.stderr.write("PROXY_FAIL_CLOSED: %s\n" % exc)
        return 2

    server.audit.write({"decision": "START", "status": 0,
                        "identity": server.identity, "proxy_pid": os.getpid()})
    sys.stderr.write("proxy listening on %s:%s (identity %s)\n"
                     % (config["bind_host"], config["bind_port"],
                        server.identity["code_sha256"][:12]))
    sys.stderr.flush()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.audit.write({"decision": "STOP", "status": 0,
                            "proxy_pid": os.getpid()})
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
