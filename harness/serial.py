"""Serialized single-request transport (v1.4).

WHY BATCHING IS DROPPED
-----------------------
Requirement: effective concurrency must be exactly one *actual analysis call*
in flight, measured at the gateway-facing boundary, including any work created
inside a batch adapter.

A batch request carrying 32 items asks the gateway to perform 32 analyses. From
outside we cannot observe whether the gateway evaluates them serially or fans
them out, and the v1.3 run produced `CAPACITY: gateway concurrency limit
reached` even at an outer concurrency of 4. Batching therefore **cannot be
shown** to honor the one-analysis-in-flight rule, and the rule says to preserve
batching only if it can be.

So v1.4 uses strictly serialized single-request transport: one logical
replication, one physical HTTP request, one at a time, no thread pool, no
fan-out. This is slower and costs far more physical requests, and those costs
are recomputed prospectively rather than carried over from the batched
arithmetic.

NO RETRIES
----------
v1.4 adds none. An explicit `CAPACITY`, an ambiguous timeout, or any incomplete
call is recorded as a blocked attempt and fails the checkpoint. If `CAPACITY`
occurs with exactly one analysis call in flight, that is a target or deployment
contract problem and must surface as one -- masking it with retries would
convert a contract violation into silent latency.

COUNTING VOCABULARY
-------------------
Kept strictly distinct throughout:

* **logical replication** -- one seeded scenario instance;
* **logical batch** -- a grouping of replications; zero in serialized mode;
* **physical HTTP request** -- one call to the gateway;
* **successful analysis** -- a response that is structurally an analysis;
* **blocked attempt** -- rejection, timeout, or incomplete call.

In serialized mode: physical requests == logical replications attempted, and
logical batches == 0.
"""

import time

from . import inflight

CAPACITY_CODES = ("CAPACITY",)
AMBIGUOUS_KINDS = ("timeout", "TimeoutError", "socket.timeout", "URLError")


class SerialDispatcher(object):
    """One analysis per physical request, strictly one at a time."""

    mode = "serialized_single_request"

    def __init__(self, target, gate=None, batch_size=1, concurrency=1,
                 **_ignored):
        self.target = target
        self.gate = gate or inflight.GATE
        # Frozen at one. Present only so the campaign's interface is unchanged.
        self.batch_size = 1
        self.concurrency = 1
        self.stats = {
            "logical_replications": 0,
            "logical_batches": 0,
            "physical_http_requests": 0,
            "successful_analyses": 0,
            "blocked_attempts": 0,
            "capacity_rejections": 0,
            "ambiguous_or_timeout": 0,
            "other_rejections": 0,
            "retries_performed": 0,
            "single_fallbacks": 0,
            "identity_mismatches": 0,
            "max_observed_in_flight": 0,
            "elapsed_seconds": 0.0,
        }

    # -- single call -------------------------------------------------------

    def _one(self, key, payload):
        self.stats["physical_http_requests"] += 1
        started = time.time()
        try:
            # NOTE: the in-flight gate is NOT applied here. It wraps the
            # gateway-facing call inside the target itself, which is where the
            # boundary actually is. Wrapping in both places would nest and
            # report a spurious violation on every call.
            response = self.target.analyze(payload)
        except Exception as exc:
            self.stats["blocked_attempts"] += 1
            code = getattr(exc, "code", None) or type(exc).__name__
            kind = type(exc).__name__
            if code in CAPACITY_CODES:
                self.stats["capacity_rejections"] += 1
                classification = "TARGET_DEPLOYMENT_CONTRACT_PROBLEM"
            elif any(token.lower() in (str(exc) + kind).lower()
                     for token in AMBIGUOUS_KINDS):
                self.stats["ambiguous_or_timeout"] += 1
                classification = "AMBIGUOUS_INCOMPLETE_CALL"
            else:
                self.stats["other_rejections"] += 1
                classification = "REJECTED"
            return {"response": None, "via": "serial",
                    "error": {"code": code, "kind": kind,
                              "detail": str(exc)[:400],
                              "classification": classification,
                              "retried": False,
                              "body": getattr(exc, "body", None)},
                    "elapsed": time.time() - started}
        finally:
            self.stats["elapsed_seconds"] += time.time() - started

        self.stats["successful_analyses"] += 1
        return {"response": response, "error": None, "via": "serial",
                "elapsed": time.time() - started}

    # -- public ------------------------------------------------------------

    def dispatch(self, items):
        """Dispatch `[(key, payload), ...]` strictly one at a time."""
        results = {}
        for key, payload in items:
            self.stats["logical_replications"] += 1
            results[key] = self._one(key, payload)
        self.stats["max_observed_in_flight"] = self.gate.max_observed
        return results

    def contract(self):
        """Report-time statistics. Never a start-of-run snapshot."""
        self.stats["max_observed_in_flight"] = self.gate.max_observed
        stats = dict(self.stats)
        return {
            "mode": self.mode,
            "batching_enabled": False,
            "batching_dropped_because": (
                "a batch asks the gateway for N analyses and we cannot observe "
                "whether it fans them out, so batching cannot be shown to "
                "honor the one-analysis-in-flight rule"),
            "max_batch_items": self.batch_size,
            "max_concurrency": self.concurrency,
            "effective_analysis_calls_in_flight": 1,
            "retries_enabled": False,
            "stats": stats,
            "in_flight": self.gate.report(),
            "counting_vocabulary": {
                "logical_replications": "one seeded scenario instance",
                "logical_batches": "zero in serialized mode",
                "physical_http_requests": "one per attempted replication",
                "successful_analyses": "structurally valid analysis responses",
                "blocked_attempts": "rejection, timeout or incomplete call",
            },
            "stats_generated_at": "report finalization",
        }

    def reconciles_with(self, audit):
        """Check final statistics against the independent attempt audit."""
        stats = self.stats
        problems = []
        if stats["successful_analyses"] != audit["successful_analyses"]:
            problems.append("successful analyses: dispatcher %d vs audit %d"
                            % (stats["successful_analyses"],
                               audit["successful_analyses"]))
        if stats["blocked_attempts"] != audit["blocked"]:
            problems.append("blocked: dispatcher %d vs audit %d"
                            % (stats["blocked_attempts"], audit["blocked"]))
        attempted = stats["successful_analyses"] + stats["blocked_attempts"]
        if stats["physical_http_requests"] != attempted:
            problems.append("physical requests %d != successes+blocked %d"
                            % (stats["physical_http_requests"], attempted))
        if stats["logical_batches"] != 0:
            problems.append("serialized mode reported %d logical batches"
                            % stats["logical_batches"])
        if attempted and all(value == 0 for key, value in stats.items()
                             if key in ("logical_replications",
                                        "physical_http_requests")):
            problems.append("live activity reported as all-zero statistics")
        return {"reconciled": not problems, "problems": problems,
                "dispatcher_stats": dict(stats), "audit": dict(audit)}


def projected_cost(replications_per_segment, segments,
                   seconds_per_request, bytes_per_replication):
    """Prospective cost under serialized single-request transport."""
    total_reps = replications_per_segment * segments
    return {
        "transport": "serialized single request",
        "logical_replications": int(round(total_reps)),
        "logical_batches": 0,
        "physical_http_requests": int(round(total_reps)),
        "requests_per_replication": 1,
        "seconds_per_request_measured": seconds_per_request,
        "projected_seconds": total_reps * seconds_per_request,
        "projected_hours": round(total_reps * seconds_per_request / 3600.0, 2),
        "projected_storage_bytes": int(total_reps * bytes_per_replication),
        "projected_storage_gb": round(
            total_reps * bytes_per_replication / 1e9, 3),
    }
