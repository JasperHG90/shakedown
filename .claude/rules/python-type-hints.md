---
name: Python Type Hints
description: Mandates type annotations on Python code (mypy-checked, modern syntax) and shows how to type common shapes. Read before adding or changing Python code.
paths: ["**/*.py"]
---

<constraint name="annotate-every-signature">
Every function and method carries type hints for all parameters and its
return value, including `-> None`. Module- and class-level attributes are
annotated when their type is not obvious from the assigned literal. New code is
fully typed; when you touch an untyped function, type it rather than leaving the
gap. The point is a machine-checked contract: the annotations are what let mypy
catch a wrong call before it ships, so an unannotated `def` is an unchecked one.
</constraint>

Type-checking is a gate, not decoration. mypy runs in the project's pre-commit
hooks; a change is not done until it passes (see the prek-code-quality and
python-testing rules). Annotations and docstrings describe the same contract
from two angles — keep them in sync (see the python-docstrings rule); a
signature change is a change to both.

## Prefer precise types over escape hatches

`Any` disables checking wherever it spreads, so reach for it only at genuinely
dynamic boundaries (deserializing unknown JSON, decorator plumbing), and narrow
back to a concrete type as soon as you can. `object` is the honest choice when a
value truly can be anything but callers should not assume operations on it.
Suppressions carry their reason and stay narrow: `cast(T, x)` when you know more
than the checker, `# type: ignore[code]` with the specific error code (never a
bare `# type: ignore`) for a genuine tool or stub gap. A suppression added only
to make the gate go green is hiding a real defect — fix the cause instead.

## Modern syntax

Target the syntax for the project's Python. On 3.10+, write unions and optionals
as `X | None`, not `Optional[X]` or `Union[X, Y]`, and use built-in generics
(`list[str]`, `dict[str, int]`, `tuple[int, ...]`) rather than the `typing`
aliases. Reserve `typing` for what has no builtin form — `Protocol`,
`TypedDict`, `Literal`, `Final`, `TypeVar`, `Callable`, `Iterable`, and friends.

<example name="functions-and-collections">
```python
from collections.abc import Iterable, Callable

def parse_ports(raw: str) -> list[int]:
    """Split a comma-separated string into port numbers."""
    return [int(p) for p in raw.split(",") if p]

def retry(fn: Callable[[], int], *, attempts: int = 3) -> int | None:
    """Call ``fn`` up to ``attempts`` times; return its result or ``None``."""
    ...

def total(values: Iterable[float]) -> float:
    """Sum an iterable of numbers."""
    return sum(values)
```

Accept the widest abstract type you actually use (`Iterable`, `Mapping`,
`Sequence` from `collections.abc`) and return the concrete one you produce
(`list`, `dict`). This lets callers pass a generator or tuple while still
telling them exactly what they get back.
</example>

## Protocols — type by shape, not by base class

Use a `Protocol` for structural ("duck") typing: a parameter that needs *some
methods*, not a *specific superclass*. Callers satisfy it by shape, with no
explicit inheritance, which keeps the dependency one-directional.

<example name="protocol">
```python
from typing import Protocol

class SupportsWrite(Protocol):
    """Anything with a text ``write`` method."""

    def write(self, data: str) -> int: ...

def emit(sink: SupportsWrite, message: str) -> None:
    """Write ``message`` to any object shaped like a writable stream."""
    sink.write(message)
```

Annotate a `@runtime_checkable` protocol only when you actually call
`isinstance` against it. For an invariant/covariant container, introduce a
`TypeVar`; add `Generic[T]` bounds only where the extra machinery earns itself.
</example>

## Pydantic models

Pydantic reads the annotations at runtime to validate and coerce, so the hints
are load-bearing, not advisory. Every field is annotated; `Field` carries
constraints and, per the docstrings rule, the human description.

<example name="pydantic">
```python
from enum import Enum
from pydantic import BaseModel, Field

class Role(str, Enum):
    admin = "admin"
    member = "member"

class CreateUser(BaseModel):
    """Payload for the create-user endpoint."""

    email: str = Field(description="Unique, case-normalized address.")
    display_name: str = Field(min_length=1, description="Name shown in the UI.")
    role: Role = Field(default=Role.member, description="Authorization role.")
    tags: list[str] = Field(default_factory=list, description="Free-form labels.")
```

Use `default_factory` for mutable defaults so instances never share one list.
Enable the mypy plugin (`plugins = ["pydantic.mypy"]`) so the generated
`__init__` is checked against these fields.
</example>

## Dataclasses, TypedDict, and aliases

A `@dataclass` derives its `__init__` from annotated fields — annotate every
one. Use `TypedDict` for a dict with a fixed, known key set (an API's JSON
shape) instead of `dict[str, Any]`, which erases the keys. Name a repeated or
unwieldy type with a `type` alias so the intent reads at each use site.

<example name="dataclass-typeddict-alias">
```python
from dataclasses import dataclass, field
from typing import TypedDict

type Headers = dict[str, str]          # 3.12+; use `Headers: TypeAlias = ...` below

@dataclass(frozen=True)
class Request:
    """An outbound HTTP request."""

    url: str
    headers: Headers = field(default_factory=dict)
    timeout: float = 5.0

class GeoPoint(TypedDict):
    """The shape of a location object in the upstream API."""

    lat: float
    lon: float
```
</example>

## Overloads and literals

When a return type depends on an argument's *value*, use `@overload` so callers
get the precise type per call, and `Literal` to pin an argument to a known set.

<example name="overload-literal">
```python
from typing import Literal, overload

@overload
def load(path: str, *, parsed: Literal[True]) -> dict[str, object]: ...
@overload
def load(path: str, *, parsed: Literal[False]) -> str: ...

def load(path: str, *, parsed: bool = True) -> dict[str, object] | str:
    """Read a file, returning parsed JSON when ``parsed`` is set, else raw text."""
    ...
```
</example>
