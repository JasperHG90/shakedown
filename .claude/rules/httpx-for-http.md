---
name: httpx-for-http
description: Make HTTP calls with httpx rather than urllib or requests, on a reused client with an explicit timeout and jittered retries. Read before writing code that talks to an HTTP API.
paths: ["**/*.py"]
---

<constraint name="one-client-explicit-timeout">
HTTP calls go through `httpx`, not `urllib.request`, `http.client`, or
`requests`. Create one `Client` (or `AsyncClient`), reuse it as a context
manager, and set the timeout explicitly rather than inheriting the default.
</constraint>

`urllib` and `http.client` leave you owning JSON encoding, headers,
query-string building, and error classification. `requests` covers those but is
sync-only, so an async fan-out becomes a rewrite; `httpx` is one API for both,
and respx mocks it (see the python-testing rule). Module-level `httpx.get`
builds and tears down a client per call, losing the connection pool along with
your shared headers and base URL.

<example name="client">
```python
import httpx

with httpx.Client(base_url=API, headers=auth, timeout=10.0) as client:
    response = client.get("/releases")
    response.raise_for_status()
```
</example>

The default timeout is 5 seconds on connect, read, write, and pool alike — too
tight for a slow report, too loose for a health check. A bare float sets all
four; use `httpx.Timeout(connect=5.0, read=30.0)` when the phases differ.

Retry with `tenacity`, not `HTTPTransport(retries=...)`, which retries only
connection failures and returns a 500 on the first try. Retry idempotent
requests on explicit 429 and 5xx, never a blind `except`, and use
`wait_exponential_jitter` so a fleet of clients does not resynchronize its
retries. A 429 usually carries `Retry-After`; tenacity has no built-in for it,
so honor it with a custom `wait`.

Parse the body into a Pydantic model (see the pydantic-boundaries rule). For
many concurrent calls, see the async-python rule.
