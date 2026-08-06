---
name: async-python
description: Use asyncio when the work is many independent I/O waits, and bound every fan-out explicitly. Read before writing concurrent Python.
paths: ["**/*.py"]
---

Async earns its complexity only when the program waits on many independent I/O
operations: dozens of HTTP requests, a directory of files, many subprocesses —
the shape of CI/CD steps, scrapers, and bulk API work. Stay synchronous
otherwise; a handful of sequential calls gets no faster, and async spreads
through every caller once it starts.

CPU-bound work does not belong here at all. The event loop is one thread, so
hashing or parsing inside a coroutine starves every other task. Hand it to a
`ProcessPoolExecutor` with `await loop.run_in_executor(pool, fn, ...)` —
`pool.submit(fn).result()` blocks the loop, which is the failure you were
avoiding. For a single blocking call, `asyncio.to_thread` is enough, though it
shares one default pool of `min(32, cpu_count + 4)` threads that nobody chose.

<constraint name="bound-every-fan-out">
Every fan-out carries an explicit concurrency bound — an `asyncio.Semaphore`
around the unit of work, or a bounded worker pool. An unbounded `gather` over a
list whose length you do not control starts every task at once: it exhausts file
descriptors, trips the remote's rate limit, and turns a fast job into a ban. The
bound is a named constant so it can be read and tuned.
</constraint>

<example name="bounded-fetch">
```python
import asyncio
import httpx

MAX_CONCURRENT_REQUESTS = 10

async def fetch_all(urls: list[str]) -> list[httpx.Response]:
    """Fetch every URL, at most ``MAX_CONCURRENT_REQUESTS`` in flight."""
    limit = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def fetch(url: str) -> httpx.Response:
            async with limit:
                return await client.get(url)

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(fetch(url)) for url in urls]

    return [task.result() for task in tasks]
```

`TaskGroup` (3.11+) cancels siblings and re-raises as an `ExceptionGroup` when a
task fails. Reach for `gather(..., return_exceptions=True)` instead when partial
results are the point and you want to report failures per item.
</example>

Know what your bound is actually for. `httpx.AsyncClient` already caps its pool
at 100 connections (`httpx.Limits(max_connections=...)` moves it), so here the
semaphore paces you against the remote rather than saving local file
descriptors. Where nothing pools for you — `asyncio.open_connection`, subprocess
fan-out, `to_thread` — the semaphore is the only bound there is.
