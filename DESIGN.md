---
version: "alpha"
name: "MSTC Chat"
description: "A live chat room for one MSTC lecture at Texas McCombs, where students send the lecturer feedback, questions and links."
colors:
  primary: "#bf5700"
  secondary: "#d6d2c4"
  accent: "#005f86"
  neutral: "#333f48"
  background: "#ffffff"
  base-200: "#f3f2ed"
  base-300: "#eae8e2"
  text: "#333f48"
  info: "#005f86"
  success: "#a6cd57"
  warning: "#f8971f"
  error: "#333f48"
  charcoal-80: "#5c656d"
typography:
  display:
    fontFamily: "Charis SIL"
  body:
    fontFamily: "Libre Franklin"
  mono:
    fontFamily: "ui-monospace"
---

# MSTC Chat design system

## Overview

MSTC Chat uses The University of Texas at Austin's brand as the McCombs School of Business
applies it: burnt orange as the one strong color, white and Limestone surfaces, Charcoal text,
Libre Franklin for the interface and Charis SIL for the title. It is built from daisyUI 5
components in one custom theme named `mstc`. The look is calm and professional: a white card on
a quiet neutral for the login page, and a white room with soft neutral message bubbles for the
chat. Burnt orange appears only where it matters: the Join and Send buttons, the "MSTC Chat"
title, and a thin band at the top of each screen.

The design agent wrote this file on 2026-10-08 without impeccable, from the feature's
`request.md`, `spec.md` and `research/design-web.md` (bundle
`F-2026-10-08-135451-lecture-chat-room-with-shared-pa`). The token file is that bundle's
`design-tokens.json`; the component rules are its `component-specs.md`; the reasons are its
`gray-areas-design.md`. Every brand fact below cites an official UT or McCombs page, listed under
Sources. The Google `design.md` lint was not run.

Accessibility floor: WCAG 2.2 AA. Every text pair below meets 4.5:1, and every control boundary
and focus ring meets 3:1.

## Colors

### The `mstc` daisyUI theme

The build applies the brand as one daisyUI 5 theme. In the app's CSS:

```css
@plugin "daisyui/theme" {
  name: "mstc";
  default: true;
  prefersdark: false;
  color-scheme: light;
  --color-base-100: #ffffff;
  --color-base-200: #f3f2ed;
  --color-base-300: #eae8e2;
  --color-base-content: #333f48;
  --color-primary: #bf5700;
  --color-primary-content: #ffffff;
  --color-secondary: #d6d2c4;
  --color-secondary-content: #333f48;
  --color-accent: #005f86;
  --color-accent-content: #ffffff;
  --color-neutral: #333f48;
  --color-neutral-content: #ffffff;
  --color-info: #005f86;
  --color-info-content: #ffffff;
  --color-success: #a6cd57;
  --color-success-content: #333f48;
  --color-warning: #f8971f;
  --color-warning-content: #333f48;
  --color-error: #333f48;
  --color-error-content: #ffffff;
  --radius-selector: 0.5rem;
  --radius-field: 0.5rem;
  --radius-box: 0.75rem;
  --size-selector: 0.25rem;
  --size-field: 0.275rem;
  --border: 1px;
  --depth: 0;
  --noise: 0;
}
```

Add one extra variable beside the theme: `--color-charcoal-80: #5c656d`.

### Roles, values and sources

| Role | Name | Value | Content color | Ratio | Source |
|---|---|---|---|---|---|
| primary | Burnt orange | `#bf5700` | `#ffffff` | 4.59 | [UT-C], [MC-C] |
| secondary | Limestone | `#d6d2c4` | Charcoal | 7.13 | [UT-C], [MC-C] |
| accent | Bluebonnet | `#005f86` | `#ffffff` | 7.04 | [UT-C], [MC-C] |
| neutral | Charcoal | `#333f48` | `#ffffff` | 10.80 | [UT-C], [MC-C] |
| base-100 | White | `#ffffff` | Charcoal | 10.80 | [UT-C] |
| base-200 | Limestone 30% | `#f3f2ed` | Charcoal | 9.63 | Tint allowed by [MC-C]; value computed |
| base-300 | Limestone 50% | `#eae8e2` | Charcoal | 8.81 | Tint allowed by [MC-C]; value computed |
| base-content | Charcoal | `#333f48` | — | 10.80 on white | [UT-C], [MC-C] |
| info | Bluebonnet | `#005f86` | `#ffffff` | 7.04 | [UT-C] |
| success | Cactus | `#a6cd57` | Charcoal | 5.91 | [UT-C]; defined, not used |
| warning | Tangerine | `#f8971f` | Charcoal | 4.85 | [UT-C]; defined, not used |
| error | Charcoal | `#333f48` | `#ffffff` | 10.80 | Design agent's choice (UT advises against red) |
| extra | Charcoal 80% | `#5c656d` | — | 5.94 on white, 5.30 on base-200 | Tint allowed by [MC-C]; value computed |

### Where each color appears

- Burnt orange: the Join and Send buttons (white text, 4.59:1), the "MSTC Chat" title on white
  (4.59:1, large text), and a 4 px band across the top of each screen.
- White: the login card, the chat header, the message area and the message box bar.
- base-200: the login page background and the online list column.
- base-300: others' message bubbles (Charcoal text, 8.81:1) and hairline borders.
- Limestone: your own message bubbles (Charcoal text, 7.13:1) and the reconnecting notice.
- Charcoal: all text, error alerts, code panels, focus rings, and the Join and Send buttons on
  hover.
- Bluebonnet: links (7.04:1 on white, 5.75:1 on base-300, 4.65:1 on Limestone) and info alerts.
- Charcoal 80%: input borders (5.94:1), placeholders, message times and "(you)".

### Errors without red

UT advises against red, especially beside burnt orange [UT-C]. Errors here use a Charcoal fill
with white text (10.80:1), an exclamation icon, and a sentence that names the problem and the
fix. A field in error gets a 2 px Charcoal border, `aria-invalid="true"` and its message below
it. The words and the icon carry the meaning, so color is never the only cue (WCAG 1.4.1).
The person is asked to confirm this choice.

### Pairs never to use

- Burnt orange text on anything but white: 4.09:1 on base-200 and 3.03:1 on Limestone fail.
- Charcoal 80% text on Limestone: 3.92:1 fails.
- Links on burnt orange: Bluebonnet on burnt orange is 1.54:1.
- Sunshine beside Bluebonnet [MC-C]; red or purple beside burnt orange [UT-C].

## Typography

| Role | Family | Fallback | Weight | Size / line height | Use |
|---|---|---|---|---|---|
| display-lg | Charis SIL | Georgia, serif | 700 | 2.25rem (2.5rem from 768 px) / 1.15 | Login title |
| display-sm | Charis SIL | Georgia, serif | 700 | 1.25rem / 1.2 | Chat header title |
| body | Libre Franklin | Arial, sans-serif | 400 | 1rem / 1.5 | Messages, inputs, alerts |
| label | Libre Franklin | Arial, sans-serif | 600 | 0.875rem / 1.4 | Labels, author names, "Online" |
| small | Libre Franklin | Arial, sans-serif | 400 | 0.875rem / 1.45 | Subtitle, hints, names in the list |
| meta | Libre Franklin | Arial, sans-serif | 400 | 0.75rem / 1.35 | Times, counter, key hint |
| mono | system monospace | — | 400 | 0.875rem / 1.5 | Code |

- UT names Libre Franklin and Charis SIL as the web replacements for Benton Sans and GT Sectra,
  free through Google Fonts, and forbids other substitutes [UT-T]. Load Libre Franklin 400, 600
  and 700 and Charis SIL 700 only.
- The monospace stack is `ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono",
  monospace`; UT names no monospace font.
- No all-caps text, no capitals across three or more lines, no condensed or stretched type
  [UT-T].
- Never lower text contrast with opacity.
- For the deployed app, serve the font files from the app itself rather than Google Fonts, so
  students' browsers do not contact Google; the architecture node decides. Both fonts are
  believed to be under the SIL Open Font License; the research marks that unconfirmed.

## Layout

- Spacing uses a 4 px scale (0.25rem steps).
- Breakpoints are Tailwind's defaults: 640, 768, 1024 and 1280 px. The layout changes once, at
  768 px. Both screens work at 320 px without sideways scrolling.
- Login page: a centered card, at most 28rem wide, on the base-200 background, below a 4 px burnt
  orange band.
- Chat screen: a 3.5rem header; a notice area; the message list on the left, filling the width,
  and the online list in a 16rem column on the right from 768 px; the message box docked at the
  bottom of the message column. Below 768 px the online list folds behind an "Online · N"
  toggle under the header.
- Message bubbles are at most 42rem wide (90% on phones). Code panels cap at 30rem tall.
- Controls are 44 px tall (`--size-field: 0.275rem`).

## Elevation & Depth

Flat. `--depth: 0` and `--noise: 0`: no shadows, no texture. Surfaces separate by color
(white, base-200, base-300, Limestone) and 1 px base-300 borders.

## Shapes

- Login card: 0.75rem radius on three corners and a square top-left corner, after the McCombs
  card shape [MC-B].
- Inputs, buttons, bubbles and code panels: 0.5rem. Alerts: 0.75rem.
- Focus: a 2 px outline, 2 px outside the element; Charcoal for inputs, links, code panels and
  the message list; the button's own fill color for primary buttons (burnt orange on white,
  4.59:1).

## Components

The full specs are in the feature bundle's `component-specs.md`. In short:

- **Buttons**: `btn btn-primary` for Join and Send: burnt orange with white text; Charcoal with
  white text on hover and press. Never `btn-soft`, `btn-outline` or `btn-dash` with `primary`,
  because daisyUI makes those by tinting the color, and UT forbids tints of burnt orange
  [UT-C], [MC-C].
- **Inputs**: a visible label above each field, a 1 px Charcoal 80% border, 44 px tall.
- **Chat bubbles**: daisyUI `chat`. Others: `chat-start` with the default base-300 bubble. Own:
  `chat-end` with `chat-bubble-secondary`. The author's name and time sit above each bubble at
  full opacity.
- **Code**: fenced blocks in a Charcoal panel with white monospace text, no wrapping, scrolling
  inside the panel; inline code on white.
- **Links**: Bluebonnet, always underlined, opening in a new tab.
- **Alerts**: `alert-error` (Charcoal) and `alert-info` (Bluebonnet), each with an icon and a
  full sentence. The reconnecting notice is a Limestone bar with Charcoal text.
- **Logo slot**: filled with the official McCombs or MSTC logo, with the text wordmark as the
  fallback. See "Logo" below.

### Logo

The person holds permission to use the McCombs mark for this class tool (the person's ruling of
2026-10-08). The build therefore fills the logo slot above the login title with the official
McCombs or MSTC logo. It downloads that file from the official source in the table below, and
uses it unchanged.

McCombs publishes its logos on UT's Box service [MC-D]. A McCombs or UT logo outside UT's own
sites needs permission from UT's Office of Brand, Trademarks and Licensing [MC-CB], which the
person's ruling covers for this tool. No mark may imply UT endorses a company's product [TM-P].
UT owns all rights in its marks [TM-M].

The text wordmark is the fallback. If no official downloadable file exists, or the file fails to
load, the login page shows "MSTC Chat" in Charis SIL, with "Master of Science in Technology
Commercialization" and "McCombs School of Business · The University of Texas at Austin" below it
in Libre Franklin [UT-E], [MC-N]. The title and subtitle appear with the logo too, below it and
separated by its clear space.

The logo follows these published rules [MC-U], [MC-L]:

- supplied artwork only, unchanged: never retyped, recolored, tinted, outlined, distorted,
  rotated, or given effects or gradients;
- a shield at least 32 px tall;
- clear space at least as tall as the shield on every side, away from the card's edge;
- a white background only;
- no other logo, mark or icon beside it, and no divider between it and the title, so the title
  does not look locked up with it;
- never the shield alone; never the Tower, the Longhorn silhouette or the seal [UT-S].

| Mark | File | Source |
|---|---|---|
| McCombs logo, formal (preferred) | https://utexas.box.com/s/b88qfe69z1mhr4d441yj28k1gwo7c402 | [MC-D] |
| McCombs logo, informal | https://utexas.box.com/s/0jw7xtqs6nmcni44e01wd134dkuuael0 | [MC-D] |
| McCombs logo, stacked | https://utexas.box.com/s/55t71p7n61cpr75z3rbq7h4k7nmmycz7 | [MC-D] |
| Program secondary logos (an MSTC logo is unconfirmed) | https://utexas.box.com/s/e0mwewuu832dwiv52eiq4h0pdq5hg7zn | [MC-D] |
| UT wordmarks | https://utexas.box.com/s/z2ftow9b0svxq4j51bv9y7ty3uque0me | [UT-W] |

## Do's and Don'ts

Do:
- Keep burnt orange solid, and use it for the one action on each screen.
- Set text in Charcoal on white, base-200, base-300 or Limestone.
- Underline every link.
- Give every error an icon and a sentence that says what to do.
- Honour reduced motion: every duration is 0 ms when the system asks.
- Use secondary colors sparingly [UT-C].

Don't:
- Tint burnt orange, or set burnt orange text on anything but white.
- Use red for errors, or put red or purple beside burnt orange.
- Put Sunshine beside Bluebonnet.
- Use gradients, glass panels, gradient blobs, heavy shadows, nested cards or gray text on
  colored surfaces.
- Use all-caps or condensed type, or imitate a logo lockup with the title.
- Use the Tower, the Longhorn silhouette or the seal.
- Lower text contrast with opacity.

## Sources

All brand pages were read by the researcher on 2026-10-08 (`research/design-web.md` in the
feature bundle).

| Key | URL |
|---|---|
| UT-C | https://umac.utexas.edu/brand-center/colors/ |
| UT-T | https://umac.utexas.edu/brand-center/typography/ |
| UT-W | https://umac.utexas.edu/brand-center/university-csu-wordmarks/ |
| UT-S | https://umac.utexas.edu/brand-center/supporting-marks/ |
| UT-E | https://umac.utexas.edu/resources/editorial-style-guide/ |
| TM-P | https://trademarks.utexas.edu/permission-use |
| TM-M | https://trademarks.utexas.edu/ut-protected-marks |
| MC-C | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/45581062/Color |
| MC-T | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214860581/Typography |
| MC-L | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/206882387 |
| MC-U | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214958765 |
| MC-D | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214958651 |
| MC-N | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/45580961 |
| MC-CB | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214958781 |
| MC-B | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/214860766 |
| MC-H | https://cloud.wikis.utexas.edu/wiki/spaces/texasmccombscommunications/pages/207230133 |
| MSTC | https://www.mccombs.utexas.edu/graduate/specialized-masters/ms-technology-commercialization/ |
