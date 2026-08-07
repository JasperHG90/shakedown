# scaffold-service

The larger of the two examples. One skill, three cases, three artifacts,
two withheld facts, and a case that needs three CLI calls in a row.

Use this one to see what a real `cases.toml` looks like. Use
[`write-plan`](../write-plan) first if you only want the shape.

```bash
uv run shakedown run examples/scaffold-service -j 3
```

## The skill

`scaffold-service` bootstraps a service repository. It needs three facts —
name, owner, and port — and it is told to ask for anything the request
leaves out rather than guess. It never writes files itself: everything goes
through `bin/scaffoldctl`.

That split is the point. The prose carries the judgment (what to ask, when
the answer is enough); the CLI carries the invariants (what the files look
like). `scaffoldctl init` writes `service.yaml`, `README.md`, and
`Dockerfile` from fixed templates, and refuses to overwrite. So an artifact
containing `EXPOSE 9000` could only have come from the CLI being run with
`--port 9000`.

## The three cases

| case | what it measures |
|---|---|
| `fully-specified` | Nothing is missing, so nothing should be asked. Three artifacts, each checked for content only the CLI's template produces. |
| `withholds-owner-and-port` | Two facts are held back and two answers are waiting. Both replies have to appear in the artifact, which needs the harness to ask twice, accept both, and carry them into one call. |
| `scaffold-then-add-endpoints` | Three calls in one turn: `init`, then `add-endpoint` twice. `docs/endpoints.md` exists only if the skill kept going after scaffolding. |

`inputs_resolved` reports `n/a` for the first and third cases. They withhold
nothing, so there is no question to ask and nothing to score — a case is
never marked down for a check that does not apply to it.

## What a run of this looks like

Against the three targets in the repo's `shakedown.toml`, one run each:

| target | skill_fired | tool_used | artifact_created | inputs_resolved |
|---|---|---|---|---|
| `claude-code/claude-opus-5` | 3/3 | 3/3 | 3/3 | 1/1 |
| `gemini-cli/gemini-3.6-flash` | 3/3 | 3/3 | 2/3 | **0/1** |
| `ollama-cloud/gpt-oss:120b` | 3/3 | 3/3 | 2/3 | **0/1** |

Every target fired the skill and called `scaffoldctl` every time. Two of
them failed the same case, `withholds-owner-and-port`, and for the same
reason: rather than ask, they invented the two facts they were missing.
Gemini took the owner from the machine's git config and picked port 8080;
the skill says in as many words not to do that.

So `scaffoldctl` ran, three files appeared, and the service is owned by the
wrong team. That is the failure this repo exists to catch — nothing
crashed, and a `tool_used` rate of 100% would have read as a pass.

These numbers move between runs — that is the point of measuring them.
Re-run with a higher `--repeat` to see the spread:

```bash
uv run shakedown run examples/scaffold-service --repeat 5 -j 9
```

## Files

```
SKILL.md          the skill under test
cases.toml        the three cases
bin/scaffoldctl   the deterministic half: init, add-endpoint
```
