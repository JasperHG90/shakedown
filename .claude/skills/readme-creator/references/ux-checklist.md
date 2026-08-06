# README UX checklist

A quick sanity check for every README produced by `readme-creator`.

## First impression
- [ ] Logo is centered at the top.
- [ ] One-line description is clear enough for a stranger.
- [ ] The "why" appears before the "how."

## Clarity
- [ ] No jargon or acronyms without explanation.
- [ ] Each feature bullet states a user outcome.
- [ ] No section makes the reader re-read to understand it.
- [ ] Code blocks are copy-paste ready.

## Hierarchy
- [ ] Headings follow `#` → `##` → `###` order; no skipped levels.
- [ ] Sections follow the ladder of abstraction: vision → features → getting started → install → how-tos → contributing.
- [ ] Visual spacing groups related ideas.

## Accessibility
- [ ] Images have descriptive alt text.
- [ ] Link text is meaningful (not "click here").
- [ ] Color contrast meets WCAG 2.1 AA (4.5:1 normal, 3:1 large).
- [ ] No information relies on color alone.

## Tone and polish
- [ ] A single tone is used throughout.
- [ ] Generic "AI slop" aesthetics are avoided.
- [ ] If a theme is used, it is applied consistently.

## Common anti-patterns that make readers say "huh"
| Anti-pattern | Fix |
|---|---|
| "Seamlessly integrates with..." | Say the concrete outcome. |
| Acronym on first use with no definition | Spell it out, then abbreviate. |
| Feature list without outcomes | Rewrite each bullet as "helps you X". |
| Install steps buried after deep docs | Put install right after quick start. |
| Screenshot with no caption | Add one sentence saying what it proves. |
| Heading jumps from `##` to `####` | Fill in or reorder the hierarchy. |
| Link text like "here" or "this" | Use descriptive text. |
