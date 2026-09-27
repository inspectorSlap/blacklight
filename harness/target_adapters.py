"""Bounded local-process and loopback-HTTP target transports.

Only response envelopes are accepted: {"target_id": str, "output": JSON}.
Transport exceptions are normalized to codes; target stderr and HTTP bodies are
never placed in reports.
"""
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

MAX_INPUT_BYTES = 32768
MAX_OUTPUT_BYTES = 65536


class Blocked(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_target_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("target ID must be 1–128 letters, digits, dots, underscores or hyphens")
    return value


def _json_bytes(obj):
    try:
        raw = json.dumps(obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Blocked("INVALID_REQUEST") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise Blocked("INPUT_TOO_LARGE")
    return raw


def _reject_constant(_):
    raise ValueError("nonfinite number")


def _decode(raw, expected_id):
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise Blocked("INVALID_JSON") from exc
    if type(value) is not dict or set(value) != {"target_id", "output"} or type(value["target_id"]) is not str:
        raise Blocked("BAD_ENVELOPE")
    if value["target_id"] != expected_id:
        raise Blocked("IDENTITY_MISMATCH")
    return value["output"]


def _digest(path):
    h = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                h.update(chunk)
    except OSError as exc:
        raise Blocked("TARGET_UNAVAILABLE") from exc
    return h.hexdigest()


def _stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _run_bounded(program, body, timeout, cwd):
    env = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath, "LANG": "C.UTF-8"}
    try:
        proc = subprocess.Popen([str(program)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd=cwd, env=env,
                                close_fds=True, start_new_session=True)
    except OSError as exc:
        raise Blocked("TARGET_UNAVAILABLE") from exc
    assert proc.stdin is not None and proc.stdout is not None
    sel = selectors.DefaultSelector()
    written = 0
    output = bytearray()
    deadline = time.monotonic() + timeout
    stdout_open = True
    stdin_open = True
    os.set_blocking(proc.stdin.fileno(), False)
    os.set_blocking(proc.stdout.fileno(), False)
    sel.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
    sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
    try:
        while stdout_open or stdin_open or proc.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Blocked("TARGET_TIMEOUT")
            events = sel.select(min(remaining, 0.1)) if sel.get_map() else []
            for key, _ in events:
                if key.data == "stdin":
                    try:
                        written += os.write(proc.stdin.fileno(), body[written:])
                    except BrokenPipeError:
                        written = len(body)
                    if written == len(body):
                        sel.unregister(proc.stdin)
                        proc.stdin.close()
                        stdin_open = False
                else:
                    chunk = os.read(proc.stdout.fileno(), min(65536, MAX_OUTPUT_BYTES + 1 - len(output)))
                    if chunk:
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT_BYTES:
                            raise Blocked("OUTPUT_TOO_LARGE")
                    else:
                        sel.unregister(proc.stdout)
                        proc.stdout.close()
                        stdout_open = False
        if proc.returncode != 0:
            raise Blocked("TARGET_EXITED")
        return bytes(output)
    except Blocked:
        _stop(proc)
        raise
    except OSError as exc:
        _stop(proc)
        raise Blocked("TARGET_IO_ERROR") from exc
    finally:
        sel.close()
        if proc.poll() is None:
            _stop(proc)
        if not proc.stdin.closed:
            proc.stdin.close()
        if not proc.stdout.closed:
            proc.stdout.close()


class ProcessAdapter:
    kind = "local-process"

    def __init__(self, program, target_id, workspace, timeout=3.0):
        self.target_id = validate_target_id(target_id)
        path = Path(program).expanduser()
        try:
            path = path.resolve(strict=True)
            mode = path.stat().st_mode
        except OSError as exc:
            raise Blocked("TARGET_UNAVAILABLE") from exc
        if not stat.S_ISREG(mode) or not os.access(path, os.X_OK):
            raise Blocked("TARGET_UNAVAILABLE")
        self.program = path
        self.sha256 = _digest(path)
        self.timeout = timeout
        self.cwd = Path(workspace) / "target-workdir"

    def identity(self):
        return {"transport": self.kind, "target_id": self.target_id, "program_sha256": self.sha256}

    def request(self, profile_id, payload):
        if _digest(self.program) != self.sha256:
            raise Blocked("IDENTITY_CHANGED")
        body = _json_bytes({"profile": profile_id, "input": payload})
        self.cwd.mkdir(parents=True, exist_ok=True)
        raw = _run_bounded(self.program, body, self.timeout, self.cwd)
        if _digest(self.program) != self.sha256:
            raise Blocked("IDENTITY_CHANGED")
        return _decode(raw, self.target_id)


class LoopbackHttpAdapter:
    kind = "loopback-http"

    def __init__(self, url, target_id, timeout=3.0):
        self.target_id = validate_target_id(target_id)
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            address = ipaddress.ip_address(host) if host else None
            port = parsed.port
        except ValueError as exc:
            raise ValueError("HTTP endpoint must use a literal loopback IP and valid port") from exc
        if parsed.scheme != "http" or not address or not address.is_loopback or not port \
                or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("HTTP endpoint must be a plain loopback URL without credentials, query or fragment")
        self.host = str(address)
        self.port = port
        self.path = parsed.path or "/"
        self.timeout = timeout

    def identity(self):
        return {"transport": self.kind, "target_id": self.target_id,
                "endpoint": "http://%s:%s%s" % (self.host, self.port, self.path)}

    def request(self, profile_id, payload):
        body = _json_bytes({"profile": profile_id, "input": payload})
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request("POST", self.path, body=body,
                               headers={"Content-Type": "application/json", "Accept": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise Blocked("HTTP_STATUS")
            raw = response.read(MAX_OUTPUT_BYTES + 1)
            if len(raw) > MAX_OUTPUT_BYTES:
                raise Blocked("OUTPUT_TOO_LARGE")
            return _decode(raw, self.target_id)
        except (socket.timeout, TimeoutError) as exc:
            raise Blocked("TARGET_TIMEOUT") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise Blocked("TARGET_UNAVAILABLE") from exc
        finally:
            connection.close()
