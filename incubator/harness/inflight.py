"""Measurement of concurrent analysis calls at the gateway-facing boundary.

WHY MEASURE RATHER THAN THROTTLE
--------------------------------
A blocking semaphore would *enforce* one-in-flight but would also *hide* a
violation: inner calls spawned by a batch adapter would simply queue, and the
observed maximum would read 1 no matter how much fan-out occurred. That is
exactly the failure mode the requirement warns about -- "one outer batch that
fans out concurrent inner calls does not satisfy this rule."

So this gate does not throttle. It instruments every actual analysis call,
records the true maximum simultaneous count, and flags any excursion above the
limit. Enforcement comes from the transport being strictly serialized: one
request at a time, no thread pool, no batch fan-out. Measurement and
enforcement are deliberately separated so the measurement can falsify the
enforcement.

WHERE IT WRAPS
--------------
The gate wraps the call that actually reaches the gateway -- `analyze` and
`analyze_batch` on the real target -- not the logical replication loop. A batch
adapter that internally issues N concurrent analyses will therefore register N
simultaneous calls and be caught.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import threading


class InFlightViolation(Exception):
    """Raised when more analysis calls are in flight than the frozen limit."""


class InFlightGate(object):
    def __init__(self, limit=1, raise_on_violation=True):
        self.limit = limit
        self.raise_on_violation = raise_on_violation
        self._lock = threading.Lock()
        self.current = 0
        self.max_observed = 0
        self.total_calls = 0
        self.violations = 0
        self.violation_details = []

    def reset(self):
        with self._lock:
            self.current = 0
            self.max_observed = 0
            self.total_calls = 0
            self.violations = 0
            self.violation_details = []

    def _enter(self, label):
        with self._lock:
            self.current += 1
            self.total_calls += 1
            if self.current > self.max_observed:
                self.max_observed = self.current
            if self.current > self.limit:
                self.violations += 1
                detail = ("%d analysis calls in flight (limit %d) at %s"
                          % (self.current, self.limit, label))
                if len(self.violation_details) < 10:
                    self.violation_details.append(detail)
                return detail
        return None

    def _exit(self):
        with self._lock:
            self.current -= 1

    def call(self, label="analysis"):
        return _GateContext(self, label)

    def report(self):
        return {
            "limit": self.limit,
            "max_observed_in_flight": self.max_observed,
            "total_analysis_calls": self.total_calls,
            "violations": self.violations,
            "violation_details": list(self.violation_details),
            "honors_one_in_flight": self.max_observed <= self.limit,
            "measured_at": "gateway-facing analysis-call boundary, including "
                           "any work created inside a batch adapter",
            "enforcement": "strictly serialized transport; this gate measures "
                           "rather than throttles, so fan-out cannot be hidden",
        }


class _GateContext(object):
    def __init__(self, gate, label):
        self.gate = gate
        self.label = label

    def __enter__(self):
        detail = self.gate._enter(self.label)
        if detail and self.gate.raise_on_violation:
            self.gate._exit()
            raise InFlightViolation(detail)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.gate._exit()
        return False


# Process-wide gate used by the real target wrapper.
GATE = InFlightGate(limit=1)
