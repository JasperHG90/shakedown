---
name: Python Docstrings
description: How to write and keep up-to-date docstrings in Python code (numpy convention). Read before adding or changing Python code.
paths: ["**/*.py"]
---

<constraint name="python-objects-need-docstrings">
Every Python object gets a docstring at minimum one sentence describing what it
achieves. This includes internal functions, private methods, classes, dataclasses,
and Pydantic models — not just public API. When you create or touch an object,
update its docstring to match the new behavior.
</constraint>

## Convention

Use the numpy docstring convention
(see <https://numpydoc.readthedocs.io/en/latest/format.html>).
Keep the one-line summary first, then a blank line, then the extended
description and structured sections. The summary fits on one line and starts
with a capital letter and ends with a period.

Write the docstring for the reader who will call the thing, not the one who
wrote it. Describe what it does and what it returns; omit mechanics that are
already obvious from the signature and types.

## Functions

Document parameters and returns in their own sections. Note raised exceptions
when callers need to handle them.

```python
def reconcile(
    records: Iterable[Record],
    baseline: Iterable[Record],
    *,
    key: str = "id",
    strict: bool = False,
) -> ReconciliationReport:
    """Reconcile two record streams by ``key``.

    The order of each input is ignored. Records present in ``baseline`` but
    missing from ``records`` are reported as removed; the reverse as added.
    Conflicting fields on shared keys are reported only when ``strict`` is set.

    Parameters
    ----------
    records :
        Incoming records to validate.
    baseline :
        Reference records to compare against.
    key :
        Field used to match records across the two streams.
    strict :
        When true, shared records with differing fields are flagged as
        conflicts instead of being accepted.

    Returns
    -------
    ReconciliationReport
        Counts of added, removed, and conflicting records, plus the
        offending items.

    Raises
    ------
    KeyError
        If ``key`` is absent from any input record.
    """
```

For a simple function, the summary plus a return description is enough; drop
sections that would only restate the types.

```python
def normalize_path(value: str) -> str:
    """Collapse redundant separators and strip a trailing slash from ``value``."""
```

## Classes

Give the class a summary docstring, then document `Attributes` for non-obvious
fields. Constructors document their parameters in the class docstring, not a
separate `__init__` docstring, per the numpy convention.

```python
class RetryPolicy:
    """Backoff schedule for retrying a fallible operation.

    Parameters
    ----------
    max_attempts :
        Upper bound on attempts, including the first call.
    base_delay :
        Delay before the second attempt; later delays grow geometrically.
    jitter :
        When true, add bounded randomness to each delay to avoid synchronized
        retry storms.

    Attributes
    ----------
    max_attempts : int
        Configured upper bound on attempts.
    base_delay : float
        Configured initial delay, in seconds.
    """

    def __init__(self, max_attempts: int, base_delay: float, jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.jitter = jitter
```

## Methods

Document public methods like functions: a one-line summary plus
`Parameters`, `Returns`, and `Raises` sections as needed. `self` and `cls`
never appear in the `Parameters` section — the reader knows they're implied.

```python
class RetryPolicy:
    # ... constructor as above ...

    def delay_for(self, attempt: int) -> float:
        """Return the backoff delay, in seconds, before the given attempt.

        ``attempt`` is 1-indexed: the first attempt has no delay, the second
        waits ``base_delay``, and each subsequent attempt waits geometrically
        more. When ``jitter`` is set, the result is randomized within a
        bounded window.

        Parameters
        ----------
        attempt :
            1-indexed attempt number to compute the delay for.

        Returns
        -------
        float
            Delay in seconds, or ``0.0`` for the first attempt.
        """
```

Class methods, static methods, and properties follow the same shape. For a
property, the summary line reads as a noun phrase describing the value, and
there is no `Parameters` or `Returns` section — the getter returns it.

```python
class RetryPolicy:
    @property
    def is_exhausted(self) -> bool:
        """Whether no further attempts remain under this policy."""

    @classmethod
    def from_config(cls, config: Config) -> "RetryPolicy":
        """Build a policy from the retry section of an app ``Config``."""
```

Private methods (leading underscore) still get a one-line summary so a future
reader knows what the helper is for without reading its body.

## Dataclasses and Pydantic models

Document the model with a summary, then use the `Attributes` section for the
fields. For Pydantic models, prefer documenting fields via `Field(description=...)`
so the text surfaces in generated schemas and OpenAPI docs as well as the
docstring.

```python
@dataclass(frozen=True)
class TokenBudget:
    """Capacity budget for a single model request.

    Attributes
    ----------
    prompt : int
        Tokens reserved for the input.
    completion : int
        Tokens reserved for the response.
    """

    prompt: int
    completion: int
```

```python
class CreateUser(BaseModel):
    """Payload for the create-user endpoint."""

    email: str = Field(description="Unique, case-normalized address.")
    display_name: str = Field(description="Human-readable name shown in the UI.")
    role: Role = Field(default=Role.member, description="Authorization role.")
```

## Keeping docstrings honest

<constraint name="docstrings-track-behavior">
A signature change is a docstring change. When you add, remove, or reorder a
parameter, rename a field, or change a return type, update the docstring in the
same change. Do not leave a docstring describing parameters that no longer
exist.
</constraint>

Document the contract, not the implementation. A reader who consults the
docstring should not need to open the function body to know what to pass and
what to expect back. Stating behavior that is obvious from the types (such as
"the string length") adds noise without helping that reader.
