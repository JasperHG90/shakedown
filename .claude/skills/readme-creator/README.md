# /readme-creator

A Claude Code skill that generates or rewrites project READMEs that are instantly clear, trustworthy, and well-structured. A README is a sales pitch — it should answer three questions in seconds: *What is this? Why should I trust it? How do I use it?*

## Usage

```
/readme-creator
```

Triggers on "write a readme", "make my readme nice", "document this project", "repo overview", "getting-started guide", and similar.

## What it produces

A README that walks the reader down the ladder of abstraction — from vision, to features, to getting started, to installation, to screenshots, to contributing. Before writing, the skill establishes (or infers): what the project is, who the reader is, the concrete problem it solves, the top features, the shortest install path, available assets, and the tone.

## Output structure

Every README follows this order:

1. **Logo** — centered at the top.
2. **One-line what-it-is** — a sentence a stranger understands.
3. **Why it exists** — the problem and the promise.
4. **Features** — 3–7 bullets mapped to user problems.
5. **Getting started** — shortest path to first value (before Installation).
6. **Installation** — copy-paste commands, prerequisites, platform notes.
7. **Screenshots / how-tos / examples** — show, don't tell.
8. **Contributing** — how to help, where to discuss, license.

## Skill files

```
readme-creator/
├── SKILL.md                            # Purpose, intake questions, structure
├── examples/
│   ├── readme.md                       # Full template + section guidance
│   └── minimal.md                      # Lightweight skeleton
├── references/
│   ├── ladder-of-abstraction.md
│   ├── theme-fallback.md
│   └── ux-checklist.md                 # Accessibility + hierarchy sanity check
└── scripts/
    └── check_readme.py                 # README linter
```
