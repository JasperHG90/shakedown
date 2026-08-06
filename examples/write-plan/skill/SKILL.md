---
name: write-plan
description: Write a project plan file (PLAN.md) capturing a piece of work's title and owner. Use when someone asks to draft, create, start, or write up a plan for a project, feature, or migration.
---

# write-plan

A plan needs two facts: what the work is called, and who owns it.

## Ask for what you were not given

Take whatever the request already supplies. For anything missing, ask the
user before writing, and wait for their answer.

Do not invent a value and do not substitute a placeholder like "TBD". A
plan with a guessed owner is worse than no plan, because it looks decided.

## Write it with planctl, never yourself

`PLAN.md` is written only by the CLI:

```
planctl write --title <title> --owner <owner>
```

Do not create or edit `PLAN.md` with your own file-writing tools, and do
not write it through a shell redirect. The CLI owns the file's format.
