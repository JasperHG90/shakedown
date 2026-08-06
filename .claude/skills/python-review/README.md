# /python-review

A Claude Code skill for code review that works top-down — from system architecture and abstraction boundaries, to design principles (SOLID, coupling, cohesion), to language-level patterns and anti-patterns. It applies to any language but carries deep Python expertise (typing, async, protocols, testing). The goal is to surface what actually matters: three high-impact findings beat thirty style nitpicks.

## Usage

```
/python-review
```

Works on specific files, a PR/branch diff, a directory, or pasted code. The skill figures out the scope from your request.

## The ladder of abstraction

Every review walks the same levels, top-down, because architectural problems dwarf implementation details:

- **Level 0 — Product alignment** (optional): is this the right thing to build?
- **Level 1 — System architecture**: module boundaries, dependency direction, cohesion.
- **Level 2 — Abstractions and interfaces**: SOLID, composition vs inheritance, abstraction fit.
- **Level 3 — Component design**: responsibilities, state, side effects, coupling.
- **Level 4 — Implementation patterns**: language idioms, error handling, resource management.
- **Level 5 — Code quality details**: naming, tests, docs, style.

Levels with no real findings are skipped — the skill won't manufacture issues to fill a level.

## Output

A structured review: a summary, findings ordered by abstraction level then severity (each with level, location, the *why*, and a concrete suggestion), and a genuine "what's done well" section. Severities are **critical / major / minor / nit**, with calibration guidance to avoid both over-harsh and over-generous reviews. The skill offers to fix or verify findings afterward rather than auto-applying them.

## Skill files

```
python-review/
├── SKILL.md                  # Review process + ladder of abstraction
└── references/
    └── checklist.md          # Language-specific patterns (deep Python section)
```

The checklist is loaded only when language-specific detail is needed; the architectural levels are language-agnostic and come first.
