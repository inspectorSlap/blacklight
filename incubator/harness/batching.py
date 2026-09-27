"""Frozen batch and concurrency contract (harness v1.1).

`POST /v0.1/analyze-batch` is a transport convenience for 1..32 independent
`analyze` requests. It is NOT a new scientific estimand, so this module must
guarantee one thing above all: **every item's response is attributed to exactly
the item that produced it, or to no item at all.** A silently misattributed
response would corrupt the campaign in a way no downstream check could detect,
because the payload and the response would each be individually well formed.

The frozen contract:

* at most `MAX_BATCH_ITEMS` (32) items per request, per `openapi.json`;
* at most `MAX_CONCURRENCY` (4) requests in flight, per the target manifest's
  `maximum_concurrent_requests`;
* every item carries a unique `analysis_id`, which the dispatcher uses to
  re-attribute results;
* **identity beats position.** If a result carries an `analysis_id`, it is
  matched by that id and the position is ignored. A result whose id was not
  requested, or was already matched, is discarded and its item is blocked.
* **positional fallback is used only when the response is complete and
  id-free.** If the item count differs from the request count and ids are
  absent, positional alignment is refused outright rather than guessed, because
  a shifted alignment is exactly the silent corruption above.
* a malformed item blocks only that item;
* an interrupted or envelope-rejected batch falls back to per-item singles, so
  a transport fault never costs more than it must.

Every failure mode yields an explicit per-item error record. No item is ever
dropped silently.
"""

raise RuntimeError("Design archive only: this module is not an enabled public runtime.")


import copy
import json

try:
    from concurrent.futures import ThreadPoolExecutor
except ImportError:  # pragma: no cover
    ThreadPoolExecutor = None

MAX_BATCH_ITEMS = 32
MAX_CONCURRENCY = 4

ERROR_ENVELOPE_REJECTED = "BATCH_ENVELOPE_REJECTED"
ERROR_INTERRUPTED = "BATCH_INTERRUPTED"
ERROR_ITEM_MISSING = "BATCH_ITEM_MISSING"
ERROR_ITEM_MALFORMED = "BATCH_ITEM_MALFORMED"
ERROR_IDENTITY_MISMATCH = "BATCH_ITEM_IDENTITY_MISMATCH"
ERROR_UNREQUESTED_ID = "BATCH_UNREQUESTED_ID"
ERROR_AMBIGUOUS_ALIGNMENT = "BATCH_AMBIGUOUS_ALIGNMENT"
ERROR_SINGLE_FAILED = "SINGLE_REQUEST_FAILED"


def chunk(items, size=MAX_BATCH_ITEMS):
    size = max(1, min(int(size), MAX_BATCH_ITEMS))
    return [items[i:i + size] for i in range(0, len(items), size)]


def _item_results(body, expected):
    """Extract the per-item result list from an unknown envelope shape."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("results", "responses", "items", "analyses"):
            if isinstance(body.get(key), list):
                return body[key]
    return None


def _result_identity(entry):
    """The analysis_id a result claims, if any."""
    if not isinstance(entry, dict):
        return None
    for key in ("analysis_id", "id", "request_id"):
        value = entry.get(key)
        if isinstance(value, str):
            return value
    inner = entry.get("result")
    if isinstance(inner, dict):
        for key in ("analysis_id", "id"):
            value = inner.get(key)
            if isinstance(value, str):
                return value
    return None


def _result_payload(entry):
    """The analysis object inside a result entry, or None if malformed."""
    if not isinstance(entry, dict):
        return None
    if entry.get("error") is not None and "schema_version" not in entry:
        return None
    inner = entry.get("result")
    if isinstance(inner, dict) and "schema_version" in inner:
        return inner
    if "schema_version" in entry:
        return entry
    return None


class BatchDispatcher(object):
    def __init__(self, target, batch_size=MAX_BATCH_ITEMS,
                 concurrency=MAX_CONCURRENCY, allow_single_fallback=True):
        self.target = target
        self.batch_size = max(1, min(int(batch_size), MAX_BATCH_ITEMS))
        self.concurrency = max(1, min(int(concurrency), MAX_CONCURRENCY))
        self.allow_single_fallback = allow_single_fallback
        self.stats = {"batches": 0, "single_fallbacks": 0, "items": 0,
                      "identity_mismatches": 0, "missing_items": 0,
                      "malformed_items": 0, "unrequested_ids": 0}

    # -- single-item path --------------------------------------------------

    def _single(self, key, payload):
        try:
            response = self.target.analyze(payload)
            return {"response": response, "error": None, "via": "single"}
        except Exception as exc:
            return {"response": None, "via": "single",
                    "error": {"code": ERROR_SINGLE_FAILED,
                              "kind": type(exc).__name__,
                              "detail": str(exc)[:400],
                              "body": getattr(exc, "body", None)}}

    def _all_single(self, batch, reason):
        out = {}
        self.stats["single_fallbacks"] += 1
        for key, payload in batch:
            result = self._single(key, payload)
            result["fallback_reason"] = reason
            out[key] = result
        return out

    # -- batch path --------------------------------------------------------

    def _dispatch_batch(self, batch):
        keys = [key for key, _payload in batch]
        payloads = [payload for _key, payload in batch]

        if not hasattr(self.target, "analyze_batch"):
            return self._all_single(batch, "target exposes no batch endpoint")

        self.stats["batches"] += 1
        try:
            body = self.target.analyze_batch(payloads)
        except Exception as exc:
            if not self.allow_single_fallback:
                return {key: {"response": None, "via": "batch",
                              "error": {"code": ERROR_INTERRUPTED,
                                        "kind": type(exc).__name__,
                                        "detail": str(exc)[:400]}}
                        for key in keys}
            code = (ERROR_ENVELOPE_REJECTED
                    if getattr(exc, "status", None) == 422 else ERROR_INTERRUPTED)
            return self._all_single(batch, code)

        entries = _item_results(body, len(batch))
        if entries is None:
            return self._all_single(batch, "unrecognized batch envelope")

        out = {}
        remaining = list(keys)
        used = set()

        # Pass 1: identity-based attribution. Identity beats position.
        identified = [(index, _result_identity(entry))
                      for index, entry in enumerate(entries)]
        any_identity = any(name is not None for _index, name in identified)
        if any_identity:
            wanted = set(keys)
            for index, name in identified:
                if name is None:
                    continue
                if name not in wanted:
                    self.stats["unrequested_ids"] += 1
                    continue
                if name in used:
                    self.stats["identity_mismatches"] += 1
                    continue
                used.add(name)
                payload = _result_payload(entries[index])
                if payload is None:
                    self.stats["malformed_items"] += 1
                    out[name] = {"response": None, "via": "batch",
                                 "error": {"code": ERROR_ITEM_MALFORMED,
                                           "detail": "item result is not a "
                                                     "well-formed analysis object",
                                           "raw": _truncate(entries[index])}}
                else:
                    claimed = payload.get("analysis_id")
                    if isinstance(claimed, str) and claimed != name:
                        self.stats["identity_mismatches"] += 1
                        out[name] = {"response": None, "via": "batch",
                                     "error": {"code": ERROR_IDENTITY_MISMATCH,
                                               "requested": name,
                                               "returned": claimed}}
                    else:
                        out[name] = {"response": payload, "error": None,
                                     "via": "batch"}
            remaining = [key for key in keys if key not in used]
            for key in remaining:
                self.stats["missing_items"] += 1
                out[key] = {"response": None, "via": "batch",
                            "error": {"code": ERROR_ITEM_MISSING,
                                      "detail": "no batch result carried this "
                                                "analysis_id"}}
            return out

        # Pass 2: positional attribution, permitted only when the response is
        # complete. A short or long id-free response cannot be aligned safely.
        if len(entries) != len(batch):
            for key in keys:
                self.stats["missing_items"] += 1
                out[key] = {"response": None, "via": "batch",
                            "error": {"code": ERROR_AMBIGUOUS_ALIGNMENT,
                                      "detail": "id-free batch response had %d "
                                                "results for %d requested items; "
                                                "positional alignment refused"
                                                % (len(entries), len(batch))}}
            return out

        for index, key in enumerate(keys):
            payload = _result_payload(entries[index])
            if payload is None:
                self.stats["malformed_items"] += 1
                out[key] = {"response": None, "via": "batch",
                            "error": {"code": ERROR_ITEM_MALFORMED,
                                      "raw": _truncate(entries[index])}}
                continue
            claimed = payload.get("analysis_id")
            if isinstance(claimed, str) and claimed != key:
                self.stats["identity_mismatches"] += 1
                out[key] = {"response": None, "via": "batch",
                            "error": {"code": ERROR_IDENTITY_MISMATCH,
                                      "requested": key, "returned": claimed}}
                continue
            out[key] = {"response": payload, "error": None, "via": "batch"}
        return out

    # -- public ------------------------------------------------------------

    def dispatch(self, items):
        """Dispatch `[(key, payload), ...]`, returning `{key: result}`."""
        self.stats["items"] += len(items)
        batches = chunk(items, self.batch_size)
        results = {}

        if ThreadPoolExecutor is None or self.concurrency == 1:
            for batch in batches:
                results.update(self._dispatch_batch(batch))
        else:
            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                for partial in pool.map(self._dispatch_batch, batches):
                    results.update(partial)

        # Nothing may be dropped: every requested key must appear.
        for key, _payload in items:
            if key not in results:
                results[key] = {
                    "response": None, "via": "batch",
                    "error": {"code": ERROR_ITEM_MISSING,
                              "detail": "dispatcher produced no entry"}}
        return results

    def contract(self):
        return {
            "max_batch_items": self.batch_size,
            "max_concurrency": self.concurrency,
            "openapi_limit": MAX_BATCH_ITEMS,
            "manifest_concurrency_limit": MAX_CONCURRENCY,
            "attribution": "analysis_id first; positional only when the "
                           "response is complete and id-free",
            "batch_is_transport_only": True,
            "stats": dict(self.stats),
        }


def _truncate(value, limit=300):
    try:
        text = json.dumps(value, sort_keys=True, default=str)
    except Exception:
        text = repr(value)
    return text[:limit]
