---
name: readme-creator
description: |
  Generate or rewrite project READMEs that are instantly clear, trustworthy, and beautiful.
  Use whenever the user asks for a README, project documentation, repo overview, onboarding guide,
  getting-started instructions, or says anything like "make my readme nice", "document this project",
  "write a readme", or "explain what this does". Triggers on README, readme, documentation,
  project summary, onboarding, getting started.
---

## Purpose
A README is a sales pitch for the project. It should answer three questions in seconds:
- What is this?
- Why should I trust it?
- How do I use it?

This skill produces READMEs that walk the reader down the ladder of abstraction: from vision
(why this exists), to practical features (how it solves the problem), to getting started and
installation, to screenshots and how-tos, and finally to contributions. The result should be
crisp enough that no reader ever stops and says "huh?"

## When to use
- The user asks for a README or wants to improve an existing one.
- The user wants project documentation, an onboarding guide, or a repo summary.
- The user mentions "readme", "documentation", "getting started", or "project overview".

## Before you write
Ask (or infer from context):
1. **What is this project?** One sentence.
2. **Who is the reader?** Engineer, end user, contributor, evaluator?
3. **What problem does it solve?** The concrete pain, not the abstract goal.
4. **What are the top 3 features?** The things that make someone say "yes, this solves X."
5. **How do I install and run it?** The shortest credible path.
6. **Are there screenshots, logos, or demo assets?** If yes, use them.
7. **Tone?** Professional, playful, brutalist, luxury, etc. Pick one extreme and commit.

If the user wants a styled or themed README, invoke the `theme-factory` skill to pick a cohesive
palette and font pairing, then apply it consistently. Otherwise, apply the principles from
`bencium-innovative-ux-designer`: strong hierarchy, one clear aesthetic, no generic "AI slop".

## How to use this skill
1. Load `examples/readme.md` for the full template, section-by-section guidance, and UX checklist.
2. Load `examples/minimal.md` if the user only wants a fast, lightweight skeleton.
3. Load `examples/ux-checklist.md` if you need a quick accessibility and hierarchy sanity check.
4. Write or update `README.md` in the project's root.

## Output structure (ladder of abstraction)
Every README must follow this order:

1. **Logo** — centered at the very top. If none exists, ask the user or leave a placeholder.
2. **One-line what-it-is** — a crisp sentence a stranger can understand.
3. **Why it exists** — the problem and the promise.
4. **Features** — 3–7 bullets that map directly to user problems.
5. **Getting started** — the shortest path to first value. **Must come before Installation.**
6. **Installation** — copy-paste commands, prerequisites, platform notes.
7. **Screenshots / how-tos / examples** — show, don't tell.
8. **Contributing** — how to help, where to discuss, license.

## Output rules
- No section should make the reader pause and re-read.
- One idea per paragraph; one purpose per bullet.
- Code blocks must be copy-paste ready.
- Headings must be hierarchical (`#` → `##` → `###`).
- Alt text for every image; meaningful link text.
- Preserve existing user-written content outside managed regions.
- Prefer Markdown. Use HTML only for layout when strictly necessary (e.g., centered logo).
