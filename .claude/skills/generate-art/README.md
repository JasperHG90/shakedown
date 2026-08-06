# /generate-art

A Claude Code skill that generates static artwork and illustrations for a repo using Nano Banana Pro (Gemini 3 Pro Image). It bundles a self-contained generator script (`scripts/generate_art.py`); the skill body is the prompt-craft and iterate loop around it. Build-time tooling only — it produces PNGs checked into the repo, never running inside an application's runtime.

This is a **general** generator: it knows *how* to generate, apply a style, and cast a character, but ships with no project-specific art. House styles and portrait pools live in the *project*, not the skill — so the same skill works in any repo.

## Prerequisites

- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in the environment — the script reads it; never hardcode keys.
- `uv` available — the script is a PEP 723 file; `uv run` installs `google-genai` + `pillow` into an ephemeral env.

## Usage

```
/generate-art
```

Or run the engine directly from the repo root:

```
uv run scripts/generate_art.py --prompt "<prompt>" --out docs/assets/diagram.png --aspect 16:9 --size 2K
```

Key flags: `--banana pro|flash`, `--aspect`, `--size 1K|2K|4K`, `--ref` (style/edit continuity), `--style` (named preset), `--cast` (feature a real person's portrait). Run with `--help` for the full list.

## Style presets

Presets are **project content**, not part of the skill. A preset is a markdown file of distilled, look-only style guidance that `--style <name>` appends to the prompt — keeping a house look consistent across calls without cloning a specific person via `--ref`. Projects keep their presets in `docs/styles/` (override with `--styles-dir`).

## Workflow

1. **Clarify** the asset — what it depicts, where it lands, aspect, whether it must match a style.
2. **Craft the prompt** yourself, grounded in the project's design docs; end with negatives (no logos, no text).
3. **Run** the script.
4. **View** the output PNG with the Read tool — never claim success without looking.
5. **Iterate** on the prompt (or add `--ref`) until it's right.

## Notes

- Output is non-deterministic; the same prompt varies run to run.
- Save to a tracked directory — confirm the destination is not `.gitignore`d.
