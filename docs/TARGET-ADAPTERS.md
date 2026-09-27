# Phase 2 target adapters

`probe` sends a bounded set of cases to a user-selected target and compares its output with the profile's independent expectation. The initial target-capable profile is `json-transform-v1`. The ordinal profile retains local qualification only; its external schema and campaign protocol have not been adapted.

## Target protocol

Both transports receive one JSON request per case:

```json
{"profile":"json-transform-v1","input":{"records":[{"id":"a","value":2}],"minimum":2}}
```

Each response must be a JSON object with exactly these two fields:

```json
{"target_id":"toy-json-v1","output":{"ids":["a"],"total":2,"count":1}}
```

The declared `target_id` must match `--target-id` on every response. A mismatch or missing envelope blocks the run. The process adapter also records the executable's SHA-256 digest and checks it before and after every case. This pins that file, not its interpreter, imported modules, external files, or dependencies. The HTTP ID is a declaration from the service, not a cryptographic identity claim.

## Local executable

The program must be an executable file. It receives one request on standard input, writes one response on standard output, and exits. The adapter invokes it once per case without a shell. It passes a minimal environment with a system Python path and no inherited application secrets; it discards standard error and never puts raw target responses in the report.

```sh
python3 -m harness.cli probe --profile json-transform-v1 \
  --program examples/json_transform_process.py --target-id toy-json-v1 \
  --cases examples/custom-cases.json --workspace workspace/process-probe
```

Only run programs you trust. The process is time and I/O bounded but is **not sandboxed** from local files or the network. Use a separate operating-system sandbox if the target itself is untrusted.

## Loopback HTTP

Start the toy service in one terminal:

```sh
python3 examples/json_transform_http.py --port 8765
```

In another terminal:

```sh
python3 -m harness.cli probe --profile json-transform-v1 \
  --url http://127.0.0.1:8765/transform --target-id toy-json-v1 \
  --cases examples/custom-cases.json --workspace workspace/http-probe
```

The adapter accepts plain HTTP at a **literal loopback IP** only. It does not use a proxy, resolve hostnames, follow redirects, or send requests to public or private network addresses. A non-200 status blocks the run without recording the response body. The toy service binds to `127.0.0.1` only. A real loopback service may still have side effects; point the probe at a service intended for testing.

## Cases, bounds and results

Without `--cases`, the probe uses the profile's five bundled examples. `--cases` accepts a JSON array of up to 32 profile input objects. The JSON profile computes the expected answers with its exact oracle, which is checked separately against hand-worked examples. Custom inputs are not copied into the report. They receive anonymous IDs such as `custom-001`.

| Bound | Current limit |
|---|---:|
| Cases per probe | 32 |
| Cases file | 1 MiB |
| Request JSON | 32 KiB |
| Response JSON | 64 KiB |
| Per-case timeout | 0.1–30 seconds; default 3 |

`results/target-probe.json` contains the target identity, case IDs, named failed checks and blocked reason codes. `PASS` means every selected case matched. `FAIL` means at least one completed response violated a criterion. `BLOCKED` means execution stopped without a complete verdict; the report shows how many cases ran. Exit codes are 0, 1 and 2 respectively. There is no fallback to a reference output when a target cannot respond.

Blocked codes include `TARGET_UNAVAILABLE`, `TARGET_TIMEOUT`, `TARGET_EXITED`, `TARGET_IO_ERROR`, `INVALID_JSON`, `BAD_ENVELOPE`, `IDENTITY_MISMATCH`, `IDENTITY_CHANGED`, `HTTP_STATUS`, `INPUT_TOO_LARGE` and `OUTPUT_TOO_LARGE`. Raw standard error, HTTP error bodies and exception strings are excluded. The report is a bounded probe, not durable campaign evidence or qualification of a production system.

The Phase 3 `campaign` command uses these same adapters and limits, with durable intent/result storage and verified resume. See [bounded campaigns](CAMPAIGNS.md).
