---
name: terminal-gif
description: |
  Record polished GIFs (and MP4/WebM/PNG) of terminal programs — CLIs, TUIs, REPLs, dotfiles, your own tools — by scripting them with VHS. Use this whenever the user wants to "make a gif", "record a terminal", "capture a CLI/TUI demo", "show this command running", "create a demo for the README", "animate my tool", "screen-record the terminal", or asks for an asciinema-style recording, a terminal screenshot, or a demo of how a command-line program behaves. Trigger even when the user only describes the behavior they want to capture (e.g. "show what happens when I run `mytool init`") without naming GIF or VHS explicitly.
---

## What this skill does

Turns a description of a terminal interaction into a rendered GIF (or MP4/WebM/PNG)
using [VHS](https://github.com/charmbracelet/vhs). The user tells you what they want
to capture; you write a declarative `.tape` script and render it.

**Why VHS over alternatives** (asciinema, terminalizer, ttygif, t-rec): VHS is the
only one that is *fully scriptable and deterministic*. You write a tape file that says
"type this, wait for that, press Enter, sleep, screenshot" and it renders identically
every time — no live recording session to drive, no manual timing. It also produces
GIF, MP4, WebM, animated WebP, and PNG screenshots from the same script, with control
over font, theme, window chrome, and dimensions. That makes it the right tool for an
agent: you can author, render, inspect, and refine without a human at the keyboard.

## The workflow

```
1. Check dependencies      → verify: vhs/ttyd/ffmpeg present (ask before installing)
2. Understand the capture   → verify: you know the commands, timing, and output format
3. Write the .tape file     → verify: `vhs validate file.tape` passes
4. Render                    → verify: `vhs file.tape` exits 0 and the output file exists & is non-empty
5. Inspect & refine          → verify: the GIF actually shows what the user asked for
```

### 1. Check dependencies (always, first)

VHS needs three things on PATH: `vhs`, `ttyd`, and `ffmpeg`. Run the bundled check:

```bash
bash scripts/check_deps.sh
```

It reports what's present and prints the correct install command for the detected OS
(macOS via Homebrew, Linux via Charm's apt repo or Homebrew). **If anything is missing,
ask the user for permission before installing it** — do not silently install. Installing
developer tooling changes their machine, so it's their call. Once they say yes, run the
command the script printed.

### 2. Understand what to capture

Before writing a tape, get clear on these. Infer what you can from the repo and context;
ask only about what you genuinely can't determine:

- **The exact commands / keystrokes** in order. For a real program, what's actually typed?
- **What signals "done"** for each step — a prompt returning, a specific line of output,
  a TUI finishing its render. This determines whether you use `Sleep` or `Wait` (see below).
- **Output format**: GIF is the default. Offer MP4/WebM for smoother/longer demos (much
  smaller files), or PNG via `Screenshot` for a still.
- **Where the file should go** (e.g. `assets/demo.gif`, repo root, `docs/`).
- **Look & feel**: theme, font size, dimensions, window bar. Sensible defaults are fine;
  match the repo's existing demo assets if any exist.

### 3. Write the `.tape` file

A tape is a sequence of settings then commands. Skeleton:

```tape
# what this demo shows
Output assets/demo.gif

Require mytool          # abort early if the program under test isn't installed

Set Shell "bash"
Set FontSize 22
Set Width 1200
Set Height 700
Set Theme "Dracula"
Set Padding 20

# --- silent setup: runs but isn't shown in the GIF ---
Hide
Type "cd /path/to/project && clear" Enter
Show

# --- the actual demo ---
Type "mytool init" Sleep 500ms Enter
Wait                    # wait for the shell prompt to return
Sleep 1s
```

The full command reference — every setting, key, and timing modifier — is in
`references/vhs-tape.md`. Read it when you need anything beyond the basics below.

**The patterns that matter most:**

- **`Type "..."`** types a string at the configured typing speed. Follow with `Enter` to run.
  Per-command speed override: `Type@30ms "fast typing"`.
- **Timing — prefer `Wait` over guessing `Sleep`.** `Sleep 2s` pauses a fixed time and is
  fine for short, predictable output. But for *real programs* whose timing varies, fixed
  sleeps are fragile — too short and you capture a half-finished screen, too long and the
  GIF drags. Use `Wait+Screen /regex/` to block until matching text appears on screen, or
  `Wait+Line /regex/` for the current line. Plain `Wait` waits for the shell prompt. This
  makes recordings robust regardless of how fast the machine is.
- **`Hide` / `Show`** run commands without recording them — use for `cd`, `clear`, exports,
  and any setup the viewer shouldn't see. The demo starts clean.
- **Keys**: `Enter`, `Tab`, `Space`, `Backspace`, `Up`/`Down`/`Left`/`Right`, `Ctrl+C`,
  `Ctrl+L`, `Escape`. Repeat with a count: `Down 3`, `Enter 2`.
- **`Screenshot path.png`** grabs a still at that point — great for a quick visual sanity
  check mid-development, or as the deliverable when the user wants a static image.

### 4. Render

```bash
vhs file.tape
```

VHS exits non-zero on a bad tape. Always confirm the output file exists and is non-empty
afterward (`ls -lh <output>`). A 0-byte or missing file means the render failed even if the
command looked like it ran.

For a fast iteration loop while dialing in timing, render to a single screenshot or a short
clip first rather than re-rendering a long GIF every time.

### 5. Inspect and refine

You can't "see" a GIF directly, but you can verify it meaningfully:

- Add a `Screenshot frames/check.png` at a key moment and **Read the PNG** to confirm the
  screen shows what you expect (the right output, no error, correct theme).
- Check file size is reasonable — a multi-MB GIF for a 5-second clip usually means the
  dimensions/font are too large; offer MP4 instead.
- Re-read the tape against the user's request: are all the steps there, in order, with
  enough pause to be readable?

Then show the user the path and a one-line summary of what it captures. If the user is in
a UI that can render it, the GIF will display.

## Scenario playbook

**Real program runs** (their own CLI/TUI, `htop`, `vim`, etc.): use `Require` to assert
the binary exists, `Hide`/`Show` for setup, and `Wait+Screen`/`Wait+Line` for timing so the
capture survives machine-speed differences. Don't fake output — drive the actual program.

**Scripted demos for docs/READMEs**: clarity beats realism. Slightly slower `TypingSpeed`,
deliberate `Sleep`s between steps so each is readable, a clean theme, and a window bar
(`Set WindowBar Colorful`) look professional embedded in a README.

**Interactive TUIs** (menus, `fzf`, full-screen apps): drive navigation with arrow keys,
`Tab`, `Enter`. Give the app a `Sleep` to finish its initial render before interacting, and
use `Wait+Screen /…/` keyed to text the TUI draws when ready. End with the key that exits
cleanly (often `q`, `Ctrl+C`, or `Escape`) so the final frame isn't a stuck screen.

**Multi-format output**: one tape can emit several files — list multiple `Output` lines with
different extensions (`.gif`, `.mp4`, `.webp`, `.ascii`). Recommend MP4/WebM for anything
longer than a few seconds or with lots of motion; GIFs balloon in size fast.

## Gotchas

- `vhs validate file.tape` checks syntax without rendering — run it before the full render to
  catch typos cheaply.
- `vhs new demo.tape` scaffolds a starter tape if you want a quick template.
- Long GIFs get huge. Keep demos tight, or switch format. Dimensions and font size drive size
  more than duration.
- `Set` commands must come before the commands they affect (ideally all at the top).
- If a real program needs a TTY or specific env, set it with `Env KEY value` and `Set Shell`.
