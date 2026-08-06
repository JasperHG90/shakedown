---
name: pydantic-boundaries
description: Parse external input and emit structured output through Pydantic models instead of raw dicts. Read before reading an HTTP response, a YAML/JSON/TOML config, or env vars, and before emitting structured output a caller depends on.
paths: ["**/*.py"]
---

<constraint name="model-at-the-boundary">
Data arriving from outside the program — an HTTP response body, a YAML or JSON
config, environment variables, a subprocess's output — is parsed into a Pydantic
model at the point it arrives, not carried around as `dict[str, Any]`. Data
leaving in a shape a caller depends on is built as a model and serialized with
`model_dump_json()`, not assembled as a dict by hand.
</constraint>

A raw dict defers every failure to the first place someone indexes into it, far
from the source. A model collapses that into one `ValidationError` at the
boundary and gives mypy a real type downstream, so a renamed field breaks at the
type gate. Annotate the fields per the python-type-hints rule.

<example name="http-response">
```python
from pydantic import BaseModel, ConfigDict, Field

class Release(BaseModel):
    """A release entry from the upstream API."""

    model_config = ConfigDict(populate_by_name=True)

    tag: str = Field(alias="tag_name", description="Version tag, e.g. v1.2.0.")
    draft: bool = Field(description="True while the release is unpublished.")

response = client.get(url)
response.raise_for_status()
release = Release.model_validate(response.json())
```

An alias renames a field on *input only*. Without `populate_by_name=True`,
`Release(tag="v1.2.0", ...)` raises and the model cannot even re-validate its
own `model_dump()`; dump with `by_alias=True` when the upstream shape has to go
back out.

Prefer `model_validate_json(response.text)` to `json.loads` plus
`model_validate`: a malformed body raises `ValidationError` rather than
`JSONDecodeError`, so one `except` covers the boundary. For a list, build
`RELEASES = TypeAdapter(list[Release])` once at module scope and call
`RELEASES.validate_json(...)`; constructing one per call costs more than the
validation does.
</example>

## Settings and config files

For app configuration, use `pydantic-settings`: it merges env vars, dotenv, and
defaults into one validated object. Construct it at startup — validation runs on
construction, so a lazily built `Settings` defers the failure you added it to
prevent.

Know which `extra` default you get: `BaseModel` ignores unknown keys,
`BaseSettings` rejects them. Both are usually right. Override in two cases: a
plain `BaseModel` used as a config schema (`extra="forbid"`, so a typo'd key
fails loudly), and a `BaseSettings` reading a `.env` shared with other tools
(`extra="ignore"`, or it rejects their keys).

## Where a model is not the answer

Data that never crosses a boundary — an internal value object, a small return
tuple — does not need runtime validation; a `@dataclass` or `NamedTuple` is
lighter and says the same thing. And when the input has no schema at all
(free-form text, an opaque blob), a model invents a contract that isn't there.
