---
name: remove-image-background
description: |
  Remove a solid background from an image and write a transparent PNG, using the
  bundled remove_background.py. Use this whenever the user wants to knock out,
  drop, or make transparent the background of a logo, banner, icon, or other
  static image asset in a repo, or to trim an asset to its content and pad it.
  Pairs with generate-art: generate a flat asset, then key its background here.
  Do NOT trigger for photo cutouts needing subject segmentation, for runtime
  image processing, or for editing source code rather than an image file.
---

# Remove background

Build-time asset tooling. The engine is `scripts/remove_background.py`; the
skill body is the recipe around it. It turns a solid background into alpha,
trims to the content, and de-fringes the edges so no halo survives on a new
backdrop.

## Boundary: build-time only

This post-processes static PNGs checked into a repo. It never runs inside a
shipped application or its request path. It has one dependency (`pillow`)
pulled into an ephemeral `uv` env, so it needs no project install.

## Prerequisites

- `uv` available. The script is a self-contained PEP 723 script: `uv run`
  installs `pillow` into an ephemeral env.

## Run

```
uv run scripts/remove_background.py --in <input> --out <output.png> [flags]
```

- `--in` / `--out`: required. Writing back to the same path is fine.
- `--mode`: `flood` (default) or `key`. See "Which mode" below.
- `--bg`: background color. `auto` (default, averages the four corners) or an
  explicit `R,G,B` when the corners are not representative.
- `--tolerance` / `-t`: color distance still counted as background (default
  `60`). Raise it when a tint survives; lower it when real art gets eaten.
- `--trim` / `--no-trim`: crop to the content bounding box (default on).
- `--pad`: transparent padding as a fraction of content height (default `0`).
  A banner reads better with `0.10` to `0.15`.
- `--defringe` / `--no-defringe`: clear anti-aliased edge pixels still tinted
  by the old background (default on). This is what kills the halo.

## Which mode

The default `flood` fill clears only background that touches the border, so a
gap INSIDE the artwork that happens to match the background color stays intact.
Reach for `key` only when the subject contains no such interior region, because
`key` clears every matching pixel wherever it sits and will punch holes through
an interior that shares the background color.

## The input matters more than the flags

Keying is clean only when the source is clean. A flat, solid-color asset on a
uniform background keys with no artifacts. A textured or painterly render
leaves a mottled fill, and any spot inside the art that shares the background
color becomes a hole. When a result looks grubby, fix the SOURCE (regenerate it
flat via generate-art) rather than fighting the key with tolerance.

## Workflow

1. **Check the source.** Confirm the background is roughly uniform and the
   subject does not share that exact color internally. If it is textured,
   prefer regenerating a flat version first.
2. **Run** the script, starting from defaults.
3. **Verify the alpha.** Composite the output over both a light and a dark
   background (and a saturated color like magenta to expose fringing), then
   view the results. Do not claim success without looking, since a
   white-on-white view hides every artifact.
4. **Iterate.** Adjust `--tolerance`, switch `--mode`, or set `--bg`
   explicitly. If holes or fringing persist, the source is the problem.
5. Show the user the result and the final path.

## Notes

- Alpha edges are binary (no soft feather). This suits flat assets that get
  downscaled for display, which anti-aliases the edge naturally. It is not a
  photo-grade matting tool.
