"""Proxy-routed transport for the black-box HTTP target.

Implements the required sandbox-proxy route from `BLACK-BOX-HANDOFF-v0.2.md`
and containment amendment v0.2 section 3, exactly and without extension:

* begin with the launcher-provided target URL and bearer token;
* remove ONLY `NO_PROXY` and `no_proxy` from this requesting process;
* preserve `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` unchanged;
* fail closed if any required filtering-proxy variable is absent;
* use the existing domain-and-port allowlist; and
* never print, archive or otherwise disclose the bearer token or proxy values.

Direct loopback sockets are not permitted, no unsandboxed retry is attempted,
and no wider allowlist is requested. The token is held only in memory and is
redacted from every record this module produces.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import json
import os
import urllib.error
import urllib.request

REQUIRED_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
BYPASS_VARS = ("NO_PROXY", "no_proxy")

REDACTED = "<redacted>"


class TransportError(Exception):
    pass


class ProxyNotConfigured(TransportError):
    """Raised when the filtering proxy is absent. The harness fails closed."""


def prepare_environment():
    """Remove only the loopback bypass variables; verify the proxy is present.

    Returns a record of what happened that is safe to archive: it names the
    variables but never their values.
    """
    present = {}
    for name in REQUIRED_PROXY_VARS:
        present[name] = bool(os.environ.get(name) or os.environ.get(name.lower()))
    missing = [name for name, ok in present.items() if not ok]
    if missing:
        raise ProxyNotConfigured(
            "required filtering-proxy variables absent: %s; the harness fails "
            "closed rather than attempting a direct loopback socket"
            % ", ".join(missing))

    removed = []
    for name in BYPASS_VARS:
        if name in os.environ:
            del os.environ[name]
            removed.append(name)

    for name in REQUIRED_PROXY_VARS:
        if not (os.environ.get(name) or os.environ.get(name.lower())):
            raise ProxyNotConfigured(
                "filtering-proxy variable %s was lost while removing the "
                "loopback bypass" % name)

    return {
        "proxy_variables_present": present,
        "bypass_variables_removed": removed,
        "bypass_variables_still_set": [n for n in BYPASS_VARS if n in os.environ],
        "direct_loopback_socket_used": False,
        "values_disclosed": False,
    }


class HttpTarget(object):
    """Authenticated client for the documented black-box endpoints."""

    def __init__(self, base_url=None, token=None, timeout=120):
        self.route_record = prepare_environment()
        self.base_url = (base_url or os.environ.get("BLACKBOX_TARGET_URL") or "").rstrip("/")
        self._token = token or os.environ.get("BLACKBOX_TARGET_TOKEN")
        if not self.base_url:
            raise TransportError("BLACKBOX_TARGET_URL is not set")
        if not self._token:
            raise TransportError("BLACKBOX_TARGET_TOKEN is not set")
        self.timeout = timeout
        # Built after the bypass variables are removed, so the request is
        # routed through the sandbox filtering proxy.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler())
        self.call_count = 0

    # -- low level ---------------------------------------------------------

    def _request(self, method, path, body=None, authenticated=True):
        url = self.base_url + path
        data = None
        request = urllib.request.Request(url, method=method)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request.data = data
            request.add_header("Content-Type", "application/json")
        if authenticated:
            request.add_header("Authorization", "Bearer " + self._token)
        self.call_count += 1
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(payload)
            except ValueError:
                parsed = {"error": {"code": "NON_JSON_ERROR_BODY",
                                    "message": payload[:500]}}
            return exc.code, parsed

    # -- documented endpoints ---------------------------------------------

    def health(self):
        return self._request("GET", "/health", authenticated=False)

    def meta(self):
        return self._request("GET", "/v0.1/meta")

    def analyze(self, payload):
        status, body = self._request("POST", "/v0.1/analyze", payload)
        if status == 200:
            return body
        raise TargetRejected(status, body)

    def aggregate(self, payload):
        status, body = self._request("POST", "/v0.1/aggregate", payload)
        if status == 200:
            return body
        raise TargetRejected(status, body)

    def analyze_batch(self, payloads):
        """Transport convenience only; each item is an independent analyze."""
        if not 1 <= len(payloads) <= 32:
            raise TransportError("batch size must be 1..32")
        status, body = self._request("POST", "/v0.1/analyze-batch",
                                     {"requests": list(payloads)})
        if status == 200:
            return body
        raise TargetRejected(status, body)

    def route_evidence(self):
        record = dict(self.route_record)
        record.update({"base_url": self.base_url, "token": REDACTED,
                       "calls_made": self.call_count})
        return record


class TargetRejected(Exception):
    """A non-200 response. Input rejection is observable target behaviour."""

    def __init__(self, status, body):
        Exception.__init__(self, "target returned HTTP %s" % status)
        self.status = status
        self.body = body


def verify_identity(target, manifest_target_block):
    """Amendment section 5: exact agreement with the distributed manifest."""
    status, meta = target.meta()
    if status != 200:
        raise TransportError("meta retrieval failed with HTTP %s" % status)
    mismatches = []
    for key, expected in manifest_target_block.items():
        if meta.get(key) != expected:
            mismatches.append({"field": key, "expected": expected,
                               "observed": meta.get(key)})
    return {"meta": meta, "mismatches": mismatches,
            "identity_matches": not mismatches}
