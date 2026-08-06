#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=10.0.0",
# ]
# ///
"""Remove a solid background from an image, producing a transparent PNG.

Build-time asset tooling. It post-processes static image files (PNGs) checked
into a repo; it is not meant to run inside an application's runtime.

Run:
    uv run remove_background.py --in logo.png --out logo.png
    uv run remove_background.py --in banner.png --out banner.png --pad 0.12
    uv run remove_background.py --in art.png --out art.png --mode key --tolerance 40

Two removal modes:
  flood (default) — flood-fill from the border, so only background CONNECTED to
      the edge is cleared. Same-colored gaps INSIDE the artwork are preserved.
      This is the safe default for logos/art whose fill matches the backdrop.
  key            — clear EVERY pixel within tolerance of the background color,
      wherever it sits. Simpler, but punches holes through interior regions that
      share the background color. Use only when the subject has no such regions.

Both modes de-fringe by default: anti-aliased edge pixels left carrying the old
background tint are cleared, so no halo survives on a new backdrop.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

from PIL import Image


def parse_bg(spec: str, img: Image.Image) -> tuple[int, int, int]:
    """Resolve the background color: 'auto' averages the four corners."""
    if spec == "auto":
        w, h = img.size
        px = img.load()
        corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        return (
            sum(c[0] for c in corners) // 4,
            sum(c[1] for c in corners) // 4,
            sum(c[2] for c in corners) // 4,
        )
    try:
        r, g, b = (int(v) for v in spec.split(","))
    except ValueError:
        sys.exit(f"error: --bg must be 'auto' or 'R,G,B', got {spec!r}")
    return (r, g, b)


def dist(p: tuple[int, ...], bg: tuple[int, int, int]) -> float:
    return ((p[0] - bg[0]) ** 2 + (p[1] - bg[1]) ** 2 + (p[2] - bg[2]) ** 2) ** 0.5


def clear_flood(img: Image.Image, bg, tol: float) -> None:
    """Clear background connected to the border via a BFS flood fill."""
    w, h = img.size
    px = img.load()
    seen = bytearray(w * h)
    dq: deque[tuple[int, int]] = deque()
    for x in range(w):
        dq.append((x, 0))
        dq.append((x, h - 1))
    for y in range(h):
        dq.append((0, y))
        dq.append((w - 1, y))
    while dq:
        x, y = dq.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        p = px[x, y]
        if dist(p, bg) > tol:
            continue
        px[x, y] = (p[0], p[1], p[2], 0)
        if x > 0:
            dq.append((x - 1, y))
        if x < w - 1:
            dq.append((x + 1, y))
        if y > 0:
            dq.append((x, y - 1))
        if y < h - 1:
            dq.append((x, y + 1))


def clear_key(img: Image.Image, bg, tol: float) -> None:
    """Clear every pixel within tolerance of the background color."""
    w, h = img.size
    px = img.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if dist(p, bg) <= tol:
                px[x, y] = (p[0], p[1], p[2], 0)


def defringe(img: Image.Image, bg, tol: float) -> None:
    """Clear the anti-aliased edge halo: kept pixels that are still near the
    background color AND border an already-cleared pixel.

    Edge-adjacency is judged against a snapshot of the alpha taken before any
    clearing, so the pass removes one ring of tinted fringe without cascading
    inward. Interior background-colored regions (which have no transparent
    neighbor) are left intact, so flood mode stays interior-safe.
    """
    w, h = img.size
    px = img.load()
    transparent = [px[x, y][3] == 0 for y in range(h) for x in range(w)]

    def edge(x: int, y: int) -> bool:
        return (
            (x > 0 and transparent[y * w + x - 1])
            or (x < w - 1 and transparent[y * w + x + 1])
            or (y > 0 and transparent[(y - 1) * w + x])
            or (y < h - 1 and transparent[(y + 1) * w + x])
        )

    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[3] != 0 and dist(p, bg) <= tol and edge(x, y):
                px[x, y] = (p[0], p[1], p[2], 0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove a solid background to alpha.")
    ap.add_argument("--in", dest="src", required=True, help="input image path")
    ap.add_argument("--out", dest="out", required=True, help="output PNG path")
    ap.add_argument(
        "--mode",
        choices=("flood", "key"),
        default="flood",
        help="flood: border-connected only (interior-safe); key: all matches",
    )
    ap.add_argument(
        "--bg",
        default="auto",
        help="background color: 'auto' (corner average) or 'R,G,B'",
    )
    ap.add_argument(
        "--tolerance",
        "-t",
        type=float,
        default=60.0,
        help="color distance still counted as background (default 60)",
    )
    ap.add_argument(
        "--defringe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="clear anti-aliased edge pixels tinted by the old background",
    )
    ap.add_argument(
        "--trim",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="crop to the content bounding box",
    )
    ap.add_argument(
        "--pad",
        type=float,
        default=0.0,
        help="transparent padding as a fraction of content height (default 0)",
    )
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        sys.exit(f"error: input not found: {src}")

    img = Image.open(src).convert("RGBA")
    bg = parse_bg(args.bg, img)

    if args.mode == "flood":
        clear_flood(img, bg, args.tolerance)
    else:
        clear_key(img, bg, args.tolerance)

    if args.defringe:
        defringe(img, bg, args.tolerance)

    if args.trim:
        bbox = img.getbbox()
        if bbox is None:
            sys.exit("error: nothing left after removal — lower --tolerance")
        img = img.crop(bbox)

    if args.pad > 0:
        cw, ch = img.size
        pad = int(round(ch * args.pad))
        canvas = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
        canvas.paste(img, (pad, pad))
        img = canvas

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"saved {out} ({img.size[0]}x{img.size[1]}) mode={args.mode} bg={bg}")


if __name__ == "__main__":
    main()
