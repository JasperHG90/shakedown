# /remove-image-background

A Claude Code skill that removes a solid background from an image and writes a
transparent PNG, using a bundled self-contained script
(`scripts/remove_background.py`). The skill body is the recipe around it. Build-
time tooling only: it post-processes PNGs checked into the repo, never running
inside an application's runtime. It pairs with `generate-art`: generate a flat
asset, then key its background here.

## Prerequisites

- `uv` available. The script is a PEP 723 file; `uv run` installs `pillow` into
  an ephemeral env, so no project install is needed.

## Usage

```
/remove-image-background
```

Or run the engine directly from the repo root:

```
uv run scripts/remove_background.py --in logo.png --out logo.png --pad 0.12
```

Key flags: `--mode flood|key` (flood is border-connected and interior-safe; key
clears every matching pixel), `--bg auto|R,G,B`, `--tolerance/-t`, `--pad`,
`--trim/--no-trim`, `--defringe/--no-defringe`. Run with `--help` for the full
list.

## Workflow

1. **Check the source.** Keying is clean only when the source is clean. A flat,
   solid-color asset on a uniform background keys with no artifacts.
2. **Run** the script, starting from defaults.
3. **Verify the alpha** by compositing over light, dark, and a saturated color,
   then view the results. A white-on-white view hides every artifact.
4. **Iterate** on `--tolerance`, `--mode`, or `--bg`. If holes or fringing
   persist, fix the source rather than the flags.

## Notes

- Alpha edges are binary. This suits flat assets that get downscaled for
  display. It is not a photo-grade matting tool.
