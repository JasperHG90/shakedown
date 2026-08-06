# README writing guide

Use this guide whenever you are producing a project README with the `readme-creator` skill.

## Golden rule
The reader should know in 10 seconds whether this project solves their problem and in 60 seconds
how to start using it. If anything forces the reader to stop and re-read, delete or rewrite it.

## Structure template

```markdown
<p align="center">
  <img src="assets/logo.png" alt="Project logo" width="320">
</p>

# Project Name

One-line description that a stranger immediately understands.

## Why this exists

The concrete problem this project solves. Write it for the reader, not for yourself.

## Features

- Solves X without Y.
- Works with Z out of the box.
- Fast / small / safe / observable because ...

## Quick start

The shortest path from zero to first value:

```bash
command here
```

## Installation

Prerequisites, then copy-paste commands per platform.

## How to use

Screenshots, GIFs, or code snippets that show real usage.

## Contributing

How to open an issue, submit a PR, or ask a question. Link to the license.
```

## Logo rules
- Place the logo at the very top, centered, with a short, descriptive `alt`.
- If no logo exists, ask the user. Do not invent one.
- A centered title directly under the logo is fine; the logo is the visual anchor.

## Section guidance

### One-line what-it-is
- Maximum 25 words.
- Avoid jargon, acronyms, and internal codenames.
- Good: "A CLI that installs Claude skills from git repos."
- Bad: "A next-generation agent experience orchestration layer."

### Why it exists
- State the reader's pain point first, then the project's promise.
- One or two short paragraphs.
- Avoid origin stories unless they directly increase trust.

### Features
- 3–7 bullets. Each bullet starts with a user outcome.
- Good: "Rollback to any previous version with one command."
- Bad: "Implements rollback."
- If there are more than 7 features, group them under subheadings.

### Quick start
- Show the fastest path to value, not every option.
- Include prerequisites inline if they are short.
- Every command should be copy-paste ready.

### Installation
- Cover the common platforms. Flag experimental ones.
- If multiple install methods exist, put the recommended one first.

### Screenshots / how-tos
- Use images or GIFs for anything visual. Describe them with alt text.
- Pair each screenshot with a one-sentence explanation of what it proves.
- Keep code examples minimal and runnable.

### Contributing
- One paragraph plus links to `CONTRIBUTING.md`, issues, and discussions.
- State the license in plain language.

## UX and accessibility checklist

Apply these to every README:

- Contrast: normal text 4.5:1, large text 3:1.
- Heading hierarchy: never skip levels.
- Alt text: every image, every time.
- Link text: meaningful (no "click here").
- Code blocks: fenced and labeled where possible.
- Line length: keep prose lines readable (45–75 characters is ideal; Markdown will reflow).
- One idea per paragraph; one purpose per bullet.

## Tone

Pick one tone and use it consistently. Examples:

- **Professional / neutral**: most infrastructure and tools.
- **Playful**: developer tools with strong UX, demos, side projects.
- **Brutalist / raw**: experimental or opinionated tools.
- **Luxury / refined**: design-focused or premium products.

Avoid generic "AI slop": do not default to Inter/Roboto/Space Grotesk, SaaS blue (#3B82F6),
cookie-cutter layouts, or Apple mimicry. If you use a theme, apply it fully.

## Before / after example

**Before:**
> aim is a tool for managing agent-related files and configurations in software projects.

**After:**
> `aim` installs Claude skills, rules, and agent instructions from git repos into your
> project, so your AI assistant has the right context from day one.
