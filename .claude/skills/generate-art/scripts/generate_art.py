#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai>=1.0.0",
#     "pillow>=10.0.0",
# ]
# ///
"""Generate artwork with Nano Banana Pro (Gemini 3 Pro Image).

Build-time asset tooling. It produces static image files (PNGs) to be checked
into a repo; it is not meant to run inside an application's runtime.

Run:
    uv run generate_art.py --prompt "..." --out docs/assets/diagram.png
    uv run generate_art.py --prompt-file /tmp/p.txt --out assets/portraits/foo.png --aspect 3:4
    uv run generate_art.py --prompt "..." --out x.png --ref existing.png   # style/edit continuity

Reads GEMINI_API_KEY (falls back to GOOGLE_API_KEY) from the environment.
"""

from __future__ import annotations

import argparse
import io
import os
import random
import sys
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

# Friendly aliases → model ids. "pro" is Nano Banana Pro; "flash" is the
# cheaper/faster standard Nano Banana.
BANANA_MODELS = {
    "pro": "gemini-3-pro-image-preview",
    "flash": "gemini-2.5-flash-image",
}
DEFAULT_BANANA = "pro"
VALID_ASPECTS = {
    "1:1",
    "3:2",
    "2:3",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
}
VALID_SIZES = {"1K", "2K", "4K"}

# Style presets are PROJECT content, not part of this generic skill. A preset is
# a markdown file of distilled style guidance appended to the prompt so a house
# look stays consistent across calls without passing a character image as --ref.
# The project keeps its own presets; --styles-dir points at them.
DEFAULT_STYLES_DIR = Path("docs/styles")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_CAST_DIR = Path("assets/portraits")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate artwork with Nano Banana (Pro or Flash)."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="Inline text prompt.")
    src.add_argument("--prompt-file", type=Path, help="Read the prompt from a file.")
    p.add_argument("--out", required=True, type=Path, help="Output image path (PNG).")
    p.add_argument(
        "--banana",
        choices=sorted(BANANA_MODELS),
        default=DEFAULT_BANANA,
        help=f"Banana model: 'pro' (Gemini 3 Pro Image) or 'flash' (Gemini 2.5 Flash Image). Default: {DEFAULT_BANANA}.",
    )
    p.add_argument("--model", help="Explicit model id; overrides --banana.")
    p.add_argument(
        "--aspect", default="16:9", choices=sorted(VALID_ASPECTS), help="Aspect ratio."
    )
    p.add_argument(
        "--size",
        default="2K",
        choices=sorted(VALID_SIZES),
        help="Resolution tier (Pro only; ignored for Flash).",
    )
    p.add_argument(
        "--ref",
        action="append",
        type=Path,
        default=[],
        metavar="IMAGE",
        help="Reference image for style/edit continuity. Repeatable.",
    )
    p.add_argument(
        "--style",
        help="Named style preset from --styles-dir (e.g. 'house').",
    )
    p.add_argument(
        "--styles-dir",
        type=Path,
        default=DEFAULT_STYLES_DIR,
        help=f"Directory of project style presets for --style (default: {DEFAULT_STYLES_DIR}).",
    )
    p.add_argument(
        "--style-file",
        type=Path,
        help="Path to an ad-hoc style preset file; overrides --style.",
    )
    p.add_argument(
        "--cast",
        metavar="NAME|random",
        help="Opt-in: feature a real person's likeness by adding their portrait "
        "as a ref. 'random' picks one; or pass a name (file stem in "
        "--cast-dir). Off by default.",
    )
    p.add_argument(
        "--cast-dir",
        type=Path,
        default=DEFAULT_CAST_DIR,
        help=f"Portrait directory for --cast (default: {DEFAULT_CAST_DIR}).",
    )
    return p.parse_args()


def resolve_cast(args: argparse.Namespace) -> list[Path]:
    if not args.cast:
        return []
    if not args.cast_dir.is_dir():
        sys.exit(f"error: --cast-dir not found: {args.cast_dir}")
    portraits = sorted(
        p for p in args.cast_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not portraits:
        sys.exit(f"error: no portraits in {args.cast_dir}")
    if args.cast == "random":
        choice = random.choice(portraits)
    else:
        matches = [p for p in portraits if p.stem == args.cast]
        if not matches:
            names = ", ".join(p.stem for p in portraits)
            sys.exit(
                f"error: no portrait '{args.cast}' in {args.cast_dir}\navailable: {names}"
            )
        choice = matches[0]
    print(f"cast: {choice.stem} ({choice.name})", file=sys.stderr)
    return [choice]


def resolve_style(args: argparse.Namespace) -> str | None:
    if args.style_file:
        path = args.style_file
    elif args.style:
        path = args.styles_dir / f"{args.style}.md"
    else:
        return None
    if not path.exists():
        available = (
            ", ".join(sorted(p.stem for p in args.styles_dir.glob("*.md"))) or "(none)"
        )
        sys.exit(
            f"error: style preset not found: {path}\navailable presets: {available}"
        )
    text = path.read_text().strip()
    if not text:
        sys.exit(f"error: style preset is empty: {path}")
    return text


def load_prompt(args: argparse.Namespace) -> str:
    text = args.prompt_file.read_text() if args.prompt_file else args.prompt
    text = text.strip()
    if not text:
        sys.exit("error: prompt is empty")
    style = resolve_style(args)
    if style:
        text = f"{text}\n\n--- STYLE (apply consistently) ---\n{style}"
    return text


def build_contents(prompt: str, refs: list[Path]) -> list:
    contents: list = []
    for ref in refs:
        if not ref.exists():
            sys.exit(f"error: reference image not found: {ref}")
        contents.append(Image.open(ref))
    contents.append(prompt)
    return contents


def extract_image(response) -> Image.Image:
    for part in response.parts or []:
        if getattr(part, "text", None):
            print(part.text, file=sys.stderr)
        inline = getattr(part, "inline_data", None)
        if inline is not None and inline.data:
            return Image.open(io.BytesIO(inline.data))
    sys.exit("error: response contained no image (check prompt / safety filters)")


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("error: set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment")

    args = parse_args()
    prompt = load_prompt(args)
    refs = args.ref + resolve_cast(args)
    model = args.model or BANANA_MODELS[args.banana]
    client = genai.Client(api_key=api_key)

    # image_size (1K/2K/4K) is a Gemini 3 Pro Image feature; Flash only honours
    # aspect_ratio. Only send size to a Pro-tier model so Flash doesn't reject it.
    is_pro = "gemini-3" in model
    image_config = types.ImageConfig(
        aspect_ratio=args.aspect,
        **({"image_size": args.size} if is_pro else {}),
    )

    response = client.models.generate_content(
        model=model,
        contents=build_contents(prompt, refs),
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=image_config,
        ),
    )

    image = extract_image(response)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)
    print(f"saved {args.out} ({image.width}x{image.height}) via {model}")


if __name__ == "__main__":
    main()
