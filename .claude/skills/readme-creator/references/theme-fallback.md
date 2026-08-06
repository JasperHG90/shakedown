# Theme fallback

Use this reference when `theme-factory` or `bencium-innovative-ux-designer` are not installed
or the user declines to invoke them.

## Theme-factory presets

Pick one of these ten presets and apply its mood to the README's visual assets (badges,
Mermaid diagrams, embedded HTML/CSS, generated images).

| Preset | Mood | Suggested accent |
|---|---|---|
| Ocean Depths | Maritime, calming | Deep teal `#0e7490` |
| Sunset Boulevard | Warm, vibrant | Coral `#f97316` |
| Forest Canopy | Earthy, grounded | Moss `#65a30d` |
| Modern Minimalist | Clean grayscale | Charcoal `#171717` |
| Golden Hour | Warm autumnal | Amber `#d97706` |
| Arctic Frost | Crisp winter | Ice blue `#38bdf8` |
| Desert Rose | Soft, dusty | Dusty rose `#e11d48` |
| Tech Innovation | Bold tech | Electric blue `#2563eb` |
| Botanical Garden | Fresh organic | Leaf `#16a34a` |
| Midnight Galaxy | Dramatic cosmic | Violet `#7c3aed` |

Apply the chosen accent to badges, dividers, and Mermaid `%%{init} {'theme': '...'}`
directives. Keep a neutral background and use the accent sparingly.

## Default safe palette

If no theme is chosen, use this accessible baseline:

- Dark text: `#0f172a`
- Light background: `#ffffff`
- Muted text: `#64748b`
- Accent: `#0ea5e9`

## Condensed bencium design protocol

1. **Ask context** — purpose, audience, constraints.
2. **Commit to one tone** — pick an extreme and stay there.
3. **Use 4–5 neutral shades + 1–3 accents.**
4. **Prefer 2–3 characterful typefaces** for any generated images; GitHub Markdown itself
cannot load custom fonts.
5. **Use a 1.25x type scale** and a 4px spacing grid for any generated assets.
6. **Meet WCAG 2.1 AA** — 4.5:1 normal text, 3:1 large text.
7. **Avoid generic AI aesthetics** — Inter, Roboto, Space Grotesk, SaaS blue, glass
morphism, Apple mimicry.

## Scope note

GitHub READMEs cannot load custom fonts or arbitrary CSS. Promise only color, image, and
badge-level styling inside the markdown file. Full typeface and spacing control requires
a separate docs site or generated image assets.
