# Language-Specific Review Checklist

This is a reference document — don't dump the entire thing into a review. Pick items that are relevant to the code at hand.

## Table of Contents

1. [Python: Type System](#python-type-system)
2. [Python: OOP and Abstractions](#python-oop-and-abstractions)
3. [Python: Error Handling](#python-error-handling)
4. [Python: Async](#python-async)
5. [Python: Testing](#python-testing)
6. [Python: Logging](#python-logging)
7. [Python: Configuration](#python-configuration)
8. [Python: Performance and Resources](#python-performance-and-resources)
9. [Python: Common Anti-Patterns](#python-common-anti-patterns)
10. [General: Concurrency](#general-concurrency)
11. [General: Resource Management](#general-resource-management)

---

## Python: Type System

**Why it matters:** Python's dynamic typing is powerful but dangerous at scale. Type hints are the bridge between flexibility and maintainability — they're documentation that the toolchain can verify.

### What to look for

- **Public APIs missing type hints.** Every function/method that's part of a public interface should have parameter and return type annotations. Internal helpers can be more relaxed, but public contracts need to be explicit.

- **`Any` used as an escape hatch.** Sometimes necessary, but often a sign that the author couldn't figure out the right type. Check if a TypeVar, Protocol, or Union would be more precise.

- **TypeVars without bounds.** Unbounded `TypeVar('T')` accepts anything, including unhashable types passed to dicts. Use `bound=` or Protocol constraints when the generic needs specific capabilities.

  ```python
  # Weak: accepts list[str] which isn't hashable
  T = TypeVar('T')

  # Better: constrains to types that support hashing
  class Hashable(Protocol):
      def __hash__(self) -> int: ...
  T = TypeVar('T', bound=Hashable)
  ```

- **Protocols vs ABCs.** Protocols define structural types ("does it quack?"); ABCs define nominal types ("is it a Duck?"). Prefer protocols when you just need a few methods. Use ABCs when you need to enforce implementation and provide shared logic.

- **Overly complex type signatures.** If a type annotation is harder to read than the code, it's not helping. Consider type aliases or simplifying the design.

---

## Python: OOP and Abstractions

**Why it matters:** Python makes it easy to create classes. Too easy. The result is often deep inheritance hierarchies, god classes, and objects that mix data with behavior inappropriately.

### What to look for

- **Deep inheritance chains.** If a class inherits from more than 2 levels deep, the MRO becomes hard to reason about. Favor composition: pass collaborators in, don't inherit from them.

  ```python
  # Fragile: 4 levels deep, tightly coupled
  class SpecializedProcessor(EnhancedProcessor(BaseProcessor(AbstractProcessor))):
      ...

  # Better: compose behaviors
  class Processor:
      def __init__(self, parser: Parser, validator: Validator, output: OutputWriter):
          ...
  ```

- **Mixins that carry state.** Mixins should add behavior, not data. A mixin with `__init__` or instance attributes is a class in disguise and will cause MRO headaches.

- **ABCs with too many abstract methods.** If implementers need to provide 10+ methods, the interface is too fat. Split it. ISP exists for a reason.

- **Properties hiding expensive operations.** A `@property` should feel like attribute access. If it makes a network call or does heavy computation, make it an explicit method. Use `@functools.cached_property` if the result is stable and worth caching.

- **Dataclasses vs regular classes.** If a class is mostly data with minimal behavior, it should probably be a `dataclass` or Pydantic model. Boilerplate `__init__` methods that just assign `self.x = x` are a smell.

- **Enums for fixed sets of values.** Magic strings and integer constants scattered through code should be enums. They're self-documenting, IDE-friendly, and prevent typos.

- **Dunder method misuse.** Operator overloading (`__add__`, `__mul__`, etc.) should only be used when the operation is intuitive for the type. Don't make `+` do something surprising just because you can.

---

## Python: Error Handling

**Why it matters:** Exception handling is where "happy path" code meets reality. Done poorly, it either swallows errors (hiding bugs) or leaks implementation details (breaking abstractions).

### What to look for

- **Bare `except:` or `except Exception:` as a blanket catch.** Catch specific exceptions. Broad catches swallow `KeyboardInterrupt`, `SystemExit`, and bugs you need to see.

- **Missing exception chaining.** When re-raising a different exception type, always use `raise NewError(...) from original`. Without it, the traceback loses the root cause.

  ```python
  # Bad: original traceback is lost
  except ConnectionError:
      raise ServiceUnavailable("db is down")

  # Good: chains the cause
  except ConnectionError as e:
      raise ServiceUnavailable("db is down") from e
  ```

- **Catching exceptions too far from the source.** Handle exceptions where you have enough context to do something meaningful. A generic catch at the top-level that logs and continues is often hiding problems.

- **Missing error handling at system boundaries.** User input, network calls, file I/O, and external APIs are where errors *will* happen. These boundaries need explicit handling. Internal code can trust its own contracts more.

- **Exception classes without useful context.** Custom exceptions should carry the data needed to diagnose the problem — not just a string message.

- **Retrying without backoff.** For transient errors (network, rate limits), use exponential backoff with jitter. Libraries like `tenacity` handle this well. Naive retry loops amplify thundering herds.

---

## Python: Async

**Why it matters:** Async Python gives you concurrency for I/O-bound work, but it's cooperative — one blocking call stalls the entire event loop.

### What to look for

- **Blocking calls inside async functions.** `time.sleep()`, synchronous file I/O, synchronous HTTP calls, and CPU-heavy computation in async code will block the event loop. Use `asyncio.sleep()`, `aiofiles`, `httpx`, and `asyncio.to_thread()` respectively.

- **Missing `await` on coroutines.** A coroutine that isn't awaited never executes. Python 3.12+ warns about this, but it's still a common bug.

- **Synchronous logging in hot async paths.** `logging` is synchronous and blocking. In high-throughput async code, excessive logging can become a bottleneck. Consider log levels carefully.

- **Not using async context managers.** If a resource has an async lifecycle (connection pools, sessions), use `async with`. Mixing sync and async resource management leads to leaks.

- **`asyncio.gather()` without error handling.** By default, `gather()` lets one failure cancel the rest. Make sure `return_exceptions=True` is used when partial results are acceptable, or that failures are handled explicitly.

- **Creating too many concurrent tasks.** Unlimited concurrency means unlimited connections, file handles, and memory. Use semaphores or task groups to bound concurrency.

---

## Python: Testing

**Why it matters:** Tests are a contract, documentation, and safety net. Bad tests are worse than no tests — they give false confidence and resist refactoring.

### What to look for

- **Testing implementation, not behavior.** Tests that break when you refactor internals (without changing behavior) are too tightly coupled. Test the *what*, not the *how*.

- **Over-mocking.** If a test mocks 5+ things, it's probably not testing anything real. Prefer composition and dependency injection — pass real (or simple fake) collaborators instead of mocking everything away.

  ```python
  # Over-mocked: what is this even testing?
  @mock.patch("app.db.connect")
  @mock.patch("app.cache.get")
  @mock.patch("app.queue.publish")
  @mock.patch("app.metrics.emit")
  def test_process(mock_metrics, mock_queue, mock_cache, mock_db):
      ...

  # Better: inject dependencies
  def test_process():
      processor = Processor(db=FakeDB(), cache=FakeCache())
      result = processor.process(input_data)
      assert result.status == "ok"
  ```

- **Missing edge case tests.** Happy path is tested; error paths, empty inputs, boundary conditions, and concurrent access are not. The bugs live in the edges.

- **No fixture organization.** Related fixtures should live in `conftest.py` at the appropriate scope. Test files importing fixtures from other test files is a smell.

- **Missing test markers.** Slow tests, integration tests, and tests requiring external services should be marked (`@pytest.mark.integration`, `@pytest.mark.slow`) so they can be skipped in fast feedback loops.

- **Non-deterministic tests.** Tests that use `random`, `datetime.now()`, or depend on network calls without mocking are time bombs. Use seeds, frozen time, and recorded responses.

- **Mutable default arguments in test fixtures.** Same issue as production code: `def fixture(items=[])` shares state across tests.

---

## Python: Logging

**Why it matters:** Logging is how you debug production. Bad logging either drowns you in noise or leaves you blind when something breaks.

### What to look for

- **Using `print()` instead of `logging`.** Print statements can't be filtered, leveled, routed, or structured. Use loggers.

- **Flat logger hierarchy.** `logging.getLogger(__name__)` is fine, but hierarchical names (`logging.getLogger("package.module.Class")`) let you control verbosity precisely. You can silence noisy sub-loggers without losing logs from their parent.

- **Wrong log levels.** DEBUG for developer-only details, INFO for operational events, WARNING for recoverable issues, ERROR for failures that need attention. If everything is INFO, nothing is.

- **Sensitive data in logs.** Passwords, tokens, PII in log messages. Check that Pydantic `SecretStr` or equivalent is used for sensitive config values.

- **Missing structured context.** Log messages like `"Error processing request"` are useless. Include the request ID, user context, and the actual error.

---

## Python: Configuration

**Why it matters:** Configuration is the interface between your code and its environment. Done well, it makes deployment flexible. Done poorly, it makes every environment a special snowflake.

### What to look for

- **Config scattered across the codebase.** Environment variables read directly in business logic, magic strings everywhere. Centralize config into typed models (Pydantic `BaseSettings` is ideal for this).

- **Missing validation.** Config values parsed from YAML/env vars without type checking or constraint validation. Pydantic validators catch bad config at startup instead of at 3am in production.

- **Secrets in config files.** Passwords, API keys, or tokens in committed YAML/JSON. Use `SecretStr`, environment variables, or a secrets manager.

- **No environment separation.** Dev, staging, and production using the same config with no clear override mechanism.

---

## Python: Performance and Resources

**Why it matters:** Python isn't fast, so you need to be smart about where you spend cycles and how you manage resources.

### What to look for

- **Resources not using context managers.** Files, database connections, HTTP sessions, locks — anything that needs cleanup should use `with`. Manual `.close()` calls are easy to skip on exception paths.

- **Missing caching for expensive operations.** Repeated computation or I/O that could use `@functools.lru_cache` or `@functools.cached_property`. But check that the cached function is actually pure and that cache invalidation is considered.

- **Generators not used for large sequences.** Building a full list in memory when a generator would stream results. Especially important when processing large datasets.

- **Mutable default arguments.** `def f(items=[])` — the list is shared across all calls. Use `None` as sentinel:

  ```python
  def f(items: list[str] | None = None):
      items = items or []
  ```

---

## Python: Common Anti-Patterns

Quick-reference list of smells specific to Python:

| Anti-pattern | Why it's bad | Better approach |
|---|---|---|
| `isinstance()` checks everywhere | Breaks duck typing, creates rigid coupling | Use protocols or method dispatch |
| God class with 20+ methods | Violates SRP, impossible to test in isolation | Split by responsibility, compose |
| 6+ parameters on a function | Hard to call correctly, usually a design smell | Group into dataclass/config object |
| `import *` | Pollutes namespace, hides dependencies | Import explicitly |
| Nested try/except 3+ levels deep | Unreadable, usually means error handling is in the wrong place | Restructure, handle at the right level |
| Long `if/elif/elif/...` chains | Hard to extend, violates OCP | Use dispatch dict, strategy pattern, or `functools.singledispatch` |
| String concatenation in loops | O(n^2) string building | Use `"".join()` or f-strings |
| Catching and logging, then re-raising | Double-logs the same error | Catch at the boundary, or re-raise without logging |

---

## General: Concurrency

Applies across languages:

- **Shared mutable state without synchronization.** Race conditions are the most common concurrency bug. If two threads/tasks can touch the same data, there must be a lock, queue, or immutable design.
- **Thread safety assumptions.** "It works on my machine" is not thread-safety evidence. Review for actual guarantees.
- **Missing cancellation/timeout handling.** Long-running operations without timeouts will eventually hang. Network calls, subprocess execution, and lock acquisition all need deadlines.

---

## General: Resource Management

Applies across languages:

- **Acquired resources not released on all paths.** Files, connections, locks must be released even when exceptions occur. Use language-specific RAII patterns (context managers in Python, try-with-resources in Java, defer in Go, RAII in C++/Rust).
- **Connection pool exhaustion.** Creating new connections per request instead of pooling. Or pooling but never returning connections on error paths.
- **Unbounded growth.** Caches, queues, or buffers that grow without limit. Always set max sizes and eviction policies.

---

## Calibration Examples

These examples anchor severity judgments. Use them as reference points to keep your reviews calibrated — not too harsh, not too lenient.

### Example 1: Major — Abstraction leak across layers

```python
# In a FastAPI route handler:
@router.post('/notes')
async def create_note(request: NoteCreate, db: AsyncSession = Depends(get_db)):
    stmt = insert(NoteModel).values(**request.dict())
    result = await db.execute(stmt)
    await db.commit()
    return {'id': result.inserted_primary_key[0]}
```

**Expected review:**
> **Abstraction leak — major**
> **Level:** Architecture
> **Issue:** The route handler directly constructs and executes SQL statements. This couples the HTTP layer to the database schema — any schema change requires modifying route handlers. The service layer is bypassed entirely.
> **Suggestion:** Route handlers should call a service method (`note_service.create(request)`) that owns the database interaction. The handler's job is HTTP concerns (validation, response formatting), not data persistence.

Why major, not critical: The code works and there's no data loss risk, but this pattern makes the codebase progressively harder to maintain as it grows. Every new endpoint that follows this pattern deepens the coupling.

### Example 2: Critical — Silent error swallowing

```python
async def process_batch(items: list[Item]) -> list[Result]:
    results = []
    for item in items:
        try:
            result = await transform(item)
            results.append(result)
        except Exception:
            continue  # skip failed items
    return results
```

**Expected review:**
> **Silent error swallowing in batch processing — critical**
> **Level:** Implementation
> **Issue:** Failed items are silently skipped with no logging, no error collection, and no indication to the caller that some items failed. A batch of 100 items could silently drop 99 and return 1 result, which the caller would treat as success. The bare `except Exception` also catches programming errors (KeyError, TypeError) that indicate bugs, not transient failures.
> **Suggestion:** At minimum: log the error, collect failures separately, and return them alongside successes so the caller can decide what to do. Catch specific expected exceptions, not `Exception`.

Why critical, not major: Data is silently lost with no way to detect or recover. In production, this creates ghost failures that are extremely hard to diagnose.

### Example 3: Minor — Overly complex type signature

```python
def get_handlers(
    config: dict[str, dict[str, list[tuple[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]]]]]
) -> dict[str, Callable]:
    ...
```

**Expected review:**
> **Unreadable type signature — minor**
> **Level:** Quality
> **Issue:** This nested type annotation is harder to read than the code it documents. Four levels of nesting make it nearly impossible to understand what the function expects at a glance.
> **Suggestion:** Define a type alias: `HandlerMap = dict[str, list[tuple[str, AsyncHandler]]]` where `AsyncHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]`. Or better yet, consider whether a dataclass or TypedDict would be clearer than nested dicts.

Why minor, not major: The code works correctly and the type is technically accurate. It's a readability issue, not a design problem. A type alias fixes it in one line.
