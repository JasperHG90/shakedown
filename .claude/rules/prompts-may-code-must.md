---
name: prompts-may-code-must
description: When authoring skills, agents, or hooks, express anything that must happen every time as code, and reserve prose for judgment. Read before writing a SKILL.md step, a hook, or a checklist an agent is meant to follow.
paths: ["**/skills/**", "**/agents/**", "**/.claude/**", "**/SKILL.md", "**/AGENTS.md", "**/CLAUDE.md"]
---

<constraint name="deterministic-over-probabilistic">
Never write a probabilistic rule where a deterministic one will do. Instructions
steer a model; they do not bind it. A fully specified step that has to work
every time goes in a script the skill runs, not in a sentence the skill hopes is
followed.
</constraint>

Split the work along that seam. Prose carries judgment — what to name a thing,
whether a change is worth making, which of three designs fits. Code carries the
invariants: validation, formatting, ordering, file placement, and the fact that
a command actually ran. The test is whether a step has any judgment left in it;
forcing a judgment call into a script makes it wrong deterministically instead
of occasionally.

## Hooks gate; reminders do not

When a step's effect has to hold, add a hook rather than a firmer sentence. Get
the mechanics right or you build a gate that does not gate:

- **Exit 2 blocks; exit 1 does not.** Claude Code treats 1 as a non-blocking
  error and proceeds anyway. A hook that `sys.exit(1)`s, or that propagates a
  failing subprocess status, enforces nothing.
- **`PreToolUse` can block, `PostToolUse` cannot** — the tool has already run,
  so exit 2 there only feeds stderr back to the model.

Assert the outcome, not the intention: check that the tree is formatted, not
that a "run the formatter" instruction was present. Then name what broke and how
to fix it, since that message is what the agent acts on.
