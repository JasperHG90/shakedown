# VHS tape reference

Complete command reference for `.tape` files, verified against VHS v0.11.0. A tape is a
plain-text script: settings first, then commands executed top to bottom.

## Table of contents
- [Output formats](#output-formats)
- [Require](#require)
- [Settings (`Set`)](#settings-set)
- [Typing](#typing)
- [Keys](#keys)
- [Timing: Sleep vs Wait](#timing-sleep-vs-wait)
- [Display control (Hide/Show/Scroll)](#display-control)
- [Screenshots](#screenshots)
- [Clipboard](#clipboard)
- [Environment & shell](#environment--shell)
- [Source (composition)](#source)
- [CLI commands](#cli-commands)
- [Themes](#themes)

## Output formats
List one or more. The extension picks the encoder; multiple `Output` lines emit multiple files.

```tape
Output demo.gif      # animated GIF (default choice; gets large fast)
Output demo.mp4      # H.264 video — smallest for long/motion-heavy clips
Output demo.webm     # WebM video
Output demo.webp     # animated WebP — smaller than GIF, browser-friendly
Output frames/       # directory → one PNG per frame (advanced)
```

Rule of thumb: GIF for short README loops; MP4/WebM for anything over a few seconds.

## Require
Abort before recording if a program isn't installed. Put these right after `Output` so a
missing dependency fails fast instead of producing a GIF of a "command not found" error.

```tape
Require git
Require mytool
```

## Settings (`Set`)
All `Set` lines should come before the commands they affect — put them at the top.

| Setting | Example | Notes |
|---|---|---|
| `Shell` | `Set Shell "bash"` | `bash`, `zsh`, `fish`, `powershell`, etc. |
| `FontSize` | `Set FontSize 22` | Biggest lever on output dimensions/size. |
| `FontFamily` | `Set FontFamily "JetBrains Mono"` | Must be installed on the system. |
| `Width` | `Set Width 1200` | Terminal width in px. |
| `Height` | `Set Height 700` | Terminal height in px. |
| `LetterSpacing` | `Set LetterSpacing 1.0` | Tracking. |
| `LineHeight` | `Set LineHeight 1.2` | |
| `Theme` | `Set Theme "Dracula"` | Name (see themes) or JSON object. |
| `Padding` | `Set Padding 20` | Inner padding in px. |
| `Margin` | `Set Margin 40` | Outer margin; needs `MarginFill` to show. |
| `MarginFill` | `Set MarginFill "#1a1a2e"` | Color or image path behind the margin. |
| `BorderRadius` | `Set BorderRadius 10` | Rounded window corners (px). |
| `WindowBar` | `Set WindowBar Colorful` | `Rings`, `RingsRight`, `Colorful`, `ColorfulRight`. macOS-style title bar. |
| `WindowBarSize` | `Set WindowBarSize 40` | Bar height in px. |
| `TypingSpeed` | `Set TypingSpeed 50ms` | Default delay between typed chars. |
| `Framerate` | `Set Framerate 60` | Frames per second. |
| `PlaybackSpeed` | `Set PlaybackSpeed 1.0` | >1 speeds the whole thing up. |
| `LoopOffset` | `Set LoopOffset 20%` | Frame the GIF loop restarts from. |
| `CursorBlink` | `Set CursorBlink false` | Disable cursor blink for cleaner stills. |

Custom theme via JSON:
```tape
Set Theme { "name": "custom", "background": "#171717", "foreground": "#e5e5e5", "cursor": "#c7c7c7", "black": "#000000", "red": "#ff5555", "green": "#50fa7b", "yellow": "#f1fa8c", "blue": "#bd93f9", "magenta": "#ff79c6", "cyan": "#8be9fd", "white": "#bfbfbf" }
```

## Typing
```tape
Type "echo hello"          # types at TypingSpeed, leaves it on the line
Type "echo hello" Enter    # type then run
Type@30ms "fast text"      # per-command typing speed override
```
Strings can use single or double quotes. To run a command you must add an explicit `Enter`.

## Keys
Every key takes an optional `@<time>` delay and an optional repeat count.

```tape
Enter          Enter 2          # press, or press N times
Tab            Backspace 3
Space          Escape
Up   Down   Left   Right        # arrows — drive menus & TUIs
PageUp   PageDown
Delete   Insert
Ctrl+C   Ctrl+L   Ctrl+R        # control combos
Down@100ms 5                    # 5 down-presses, 100ms apart
```

## Timing: Sleep vs Wait
This is the single most important choice for robust recordings.

```tape
Sleep 2s        Sleep 500ms     # fixed pause — fine for fast, predictable output
```

`Sleep` is fragile for real programs: too short captures a half-rendered screen, too long
makes the GIF drag. Prefer `Wait`, which blocks until the terminal actually shows something:

```tape
Wait                    # wait for the shell prompt to return (command finished)
Wait+Screen /Done/      # wait until "Done" appears anywhere on screen
Wait+Line /\$\s*$/      # wait until the current line matches the regex
Wait@10s+Screen /ready/ # same, but time out after 10s
```

Use `Wait`/`Wait+Screen` after running a real command so the recording adapts to machine
speed instead of guessing. Add a small `Sleep` *after* the wait so the finished state is
readable in the final frames.

## Display control
```tape
Hide                    # subsequent commands run but are NOT recorded
Type "cd /proj" Enter
Type "clear" Enter
Show                    # recording resumes — demo starts clean

ScrollUp 3              # scroll the viewport
ScrollDown 5
```
`Hide`/`Show` is how you do invisible setup (cd, clear, exports, seeding state).

## Screenshots
```tape
Screenshot out.png      # capture the current screen as a PNG at this point
```
Two uses: (1) the deliverable when the user wants a still image; (2) a mid-tape checkpoint
you can Read to visually verify the render is correct before committing to a long GIF.

## Clipboard
```tape
Copy "text to clipboard"
Paste
```

## Environment & shell
```tape
Env FOO "bar"           # set an env var for the recorded shell
Set Shell "zsh"
```

## Source
Compose tapes by including another file (e.g. shared settings). The referenced file must
exist at validate/render time.
```tape
Source common-settings.tape
```

## CLI commands
```bash
vhs file.tape              # render
vhs validate file.tape     # parse-check without rendering (run this first)
vhs new file.tape          # scaffold a documented starter tape
vhs themes                 # list every built-in theme name
vhs -o other.gif file.tape # override the Output path from the CLI
vhs record > out.tape      # record live keystrokes into a tape (manual use)
```

## Themes
Hundreds of built-in themes (Dracula, Catppuccin Mocha, Nord, Gruvbox Dark, Solarized Dark,
TokyoNight, etc.). Run `vhs themes` for the full list. Match the user's terminal or the
repo's existing assets when there's a reason to; otherwise a clean dark theme like Dracula
or Catppuccin Mocha is a safe, attractive default.
