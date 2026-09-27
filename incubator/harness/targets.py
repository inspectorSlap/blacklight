"""Uniform target interface.

Every target exposes `analyze(payload)` and `aggregate(payload)`, returning a
parsed response body or raising `Rejection` for a documented input rejection.
The harness treats the sound reference, each registered mutant, and the real
black-box endpoint through exactly this interface, so the same check suite runs
unchanged against all three. That is what makes the self-qualification evidence
transferable to the real campaign.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


from .mutants import mutants as mutant_module
from .reference import archive as archive_mod
from .reference import sound_reference as sr


class Rejection(Exception):
    """A documented input rejection (HTTP 422 or the local equivalent)."""

    def __init__(self, code, message, status=422, body=None):
        Exception.__init__(self, "%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.status = status
        self.body = body or {"error": {"code": code, "message": message}}


class SoundReferenceTarget(object):
    target_id = "sound-reference-1.0"
    kind = "sound_reference"

    def analyze(self, payload):
        try:
            return sr.analyze(payload)
        except sr.Rejected as exc:
            raise Rejection(exc.code, exc.message)

    def aggregate(self, payload):
        try:
            return archive_mod.aggregate(payload)
        except archive_mod.Rejected as exc:
            raise Rejection(exc.code, exc.message)

    def analyze_batch(self, payloads):
        """Batch convenience: each item is evaluated as though sent separately.

        The batch endpoint is transport only and is not a new scientific
        estimand, so this simply maps analyze over the items and tags each
        result with its requesting analysis_id for attribution.
        """
        results = []
        for payload in payloads:
            try:
                body = self.analyze(payload)
                if isinstance(body, dict):
                    body = dict(body)
                    body["analysis_id"] = payload.get("analysis_id")
                results.append(body)
            except Rejection as exc:
                results.append({"analysis_id": payload.get("analysis_id"),
                                "error": {"code": exc.code,
                                          "message": exc.message}})
        return {"results": results}


class MutantTarget(object):
    kind = "mutant"

    def __init__(self, mutant_id):
        cls = mutant_module.BY_ID.get(mutant_id)
        if cls is None:
            raise KeyError("unknown mutant %r" % mutant_id)
        self.target_id = mutant_id
        self.mutant = cls()
        self.defect_class = cls.defect_class
        self.dangerous_direction = cls.dangerous_direction
        self.expected_check = cls.expected_check
        self.mutated_target = cls.target

    def analyze(self, payload):
        try:
            return self.mutant.analyze(payload)
        except sr.Rejected as exc:
            raise Rejection(exc.code, exc.message)

    def aggregate(self, payload):
        try:
            return self.mutant.aggregate(payload)
        except archive_mod.Rejected as exc:
            raise Rejection(exc.code, exc.message)

    def analyze_batch(self, payloads):
        """Batch convenience: each item is evaluated as though sent separately.

        The batch endpoint is transport only and is not a new scientific
        estimand, so this simply maps analyze over the items and tags each
        result with its requesting analysis_id for attribution.
        """
        results = []
        for payload in payloads:
            try:
                body = self.analyze(payload)
                if isinstance(body, dict):
                    body = dict(body)
                    body["analysis_id"] = payload.get("analysis_id")
                results.append(body)
            except Rejection as exc:
                results.append({"analysis_id": payload.get("analysis_id"),
                                "error": {"code": exc.code,
                                          "message": exc.message}})
        return {"results": results}



class BlackBoxTarget(object):
    """The real HTTP endpoint. Constructing this opens the proxy route.

    Not instantiated anywhere in the pre-approval phase: the phase gate in
    `harness/cli.py` refuses to build it until the freeze manifest exists and
    the operator approval record is present.
    """

    kind = "black_box"

    def __init__(self, client):
        self.client = client
        self.target_id = "black-box-http"

    def analyze(self, payload):
        from .transport import TargetRejected
        from . import inflight
        try:
            with inflight.GATE.call("blackbox.analyze"):
                return self.client.analyze(payload)
        except TargetRejected as exc:
            code = "UNKNOWN"
            message = ""
            if isinstance(exc.body, dict):
                error = exc.body.get("error") or {}
                code = error.get("code", code)
                message = error.get("message", "")
            raise Rejection(code, message, status=exc.status, body=exc.body)

    def aggregate(self, payload):
        from .transport import TargetRejected
        try:
            return self.client.aggregate(payload)
        except TargetRejected as exc:
            code = "UNKNOWN"
            message = ""
            if isinstance(exc.body, dict):
                error = exc.body.get("error") or {}
                code = error.get("code", code)
                message = error.get("message", "")
            raise Rejection(code, message, status=exc.status, body=exc.body)

    def analyze_batch(self, payloads):
        """Expose the transport's batch capability to the dispatcher.

        v1.2 omitted this. The dispatcher checks `hasattr(target,
        "analyze_batch")` on the wrapper, so its absence silently demoted the
        campaign to single requests while the frozen cost arithmetic still
        assumed batching -- 500 requests where 16 were projected. The batch
        endpoint is a transport convenience only: each item is evaluated as
        though sent separately and is not a new scientific estimand.
        """
        from .transport import TargetRejected
        from . import inflight
        # Measured as N simultaneous analyses: a batch asks the gateway for N
        # analyses, so it cannot satisfy the one-in-flight rule. v1.4 does not
        # use this path; it remains instrumented so any use is caught.
        try:
            with inflight.GATE.call("blackbox.analyze_batch[%d]" % len(payloads)):
                return self.client.analyze_batch(payloads)
        except TargetRejected as exc:
            code = "UNKNOWN"
            message = ""
            if isinstance(exc.body, dict):
                error = exc.body.get("error") or {}
                code = error.get("code", code)
                message = error.get("message", "")
            raise Rejection(code, message, status=exc.status, body=exc.body)
