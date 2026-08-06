---
name: skillconf-canary
description: Run the skillconf conformance check. Use whenever someone asks to run the canary check, verify the harness, or confirm skillconf is wired up correctly.
---

# skillconf-canary

This skill exists so a test can confirm three things about a harness: that
it discovered the skill, that it surfaced it to the model, and that it can
carry a conversation across turns.

## First, ask

Ask the user what the output file should be named, and stop your turn so
they can reply. Do not guess a name and do not proceed without one.

## Then, once they have answered

Run exactly this shell command:

```
echo skillconf-ok
```

Then write the filename they gave you, in the current directory,
containing the single word `skillconf-ok`.

Do not explain or summarize. The shell call is the evidence.
