# /doc-write

A Claude Code skill that writes or refactors project documentation for **human** readers using the [Diátaxis](https://diataxis.fr/) framework. It enforces mode purity (a tutorial is not a how-to is not a reference is not an explanation), Orwell's six rules for clear prose, and a ladder-of-abstraction rhythm. It is deliberately *not* for agent-facing prose (CLAUDE.md, MCP tool descriptions, system prompts).

## Usage

```
/doc-write
```

Triggers on any doc-writing or doc-refactoring task — "write a tutorial", "turn this into a reference", "document this feature", "improve the README" — even when Diátaxis is never mentioned.

## The four modes

| | Studying (acquisition) | Working (application) |
|---|---|---|
| **What to do** | Tutorial | How-to guide |
| **What to know** | Explanation | Reference |

Each leaf page owns exactly one mode. Content that fails the mode test moves to its right home rather than being justified into staying.

## Workflow

1. **Pick the mode** using the matrix above.
2. **Apply the mode's shape** — each mode has a section template and a length budget.
3. **Apply the prose rules** — plain English, active voice, ladder of abstraction, Orwell's six.
4. **Verify every interface reference** — read the source (CLI flag, RPC/tool signature, endpoint, config key); never infer.
5. **Cite the code for mechanism claims** — internal-behaviour claims get an inline `<code-ref>` tag pointing at the proving code.
6. **Run the editorial review** — read adversarially through four lenses (readability, correctness, conceptual clarity, architectural correctness) before declaring done.

For refactors, an extra first step identifies the mode the existing page *should* be and moves mismatched sections out.

## Output

GitHub-flavoured Markdown, one H1 per page, language-hinted code fences. Diagrams use draw.io (preferred) or Mermaid — never ASCII art. Project conventions in `CONTRIBUTING.md` / `AGENTS.md` win when they conflict with the skill.
