---
name: Row Tracker
description: A dark, instrument-panel-styled rowing analytics console for Concept2 RowErg athletes
colors:
  bg-console: "#0a0b10"
  surface-panel: "#16181f"
  surface-panel-raised: "#1e212b"
  border-hairline: "#262a35"
  text-primary: "#e6e9ef"
  text-muted: "#838ca3"
  accent-chartreuse: "#cdfa3f"
  accent-chartreuse-light: "#e2ff85"
  status-positive: "#22c55e"
  status-negative: "#ef4444"
  status-warning: "#f59e0b"
  status-success-alt: "#3ddc84"
  status-danger-alt: "#ff6b6b"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.05em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  numeric:
    fontFamily: "'SF Mono', 'Fira Code', 'Fira Mono', monospace"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  sm: "10px"
  md: "18px"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
  xxl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.accent-chartreuse}"
    textColor: "#0a0b10"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.25rem"
  button-primary-hover:
    backgroundColor: "{colors.accent-chartreuse-light}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.25rem"
  button-ghost-hover:
    backgroundColor: "{colors.surface-panel-raised}"
    textColor: "{colors.text-primary}"
  card:
    backgroundColor: "{colors.surface-panel}"
    rounded: "{rounded.md}"
    padding: "1.25rem"
---

# Design System: Row Tracker

## Overview

**Creative North Star: "The Erg Console"**

Row Tracker reads like the console of the machine it tracks: near-black
surfaces, one alert-bright accent, numbers given room to be the largest
thing on screen. Nothing decorative competes with the data. Panels sit flush
against a dark background rather than floating above it; the interface's job
is to disappear behind the training numbers it's reporting, the way a PM5
monitor's own display disappears behind a stroke rate the moment you glance
at it.

The palette is almost entirely neutral (near-black background, three steps
of dark-gray surface, muted gray-blue text) with a single chartreuse accent
used sparingly enough that its appearance always means something: this is
active, this is new, this is yours to act on. Confirmed visual rejection:
no gradients, no illustration, no decorative imagery — every visual element
either carries data or marks an interactive affordance.

**Key Characteristics:**
- Dark-default, near-black console background with a light-mode toggle (not
  a second design language — a straightforward inversion of the same tokens)
- One accent color, used rarely, always meaningfully (active states, primary
  actions, "new" and "earned" moments, live progress)
- Numbers set larger and heavier than their labels, with `tabular-nums` on
  any figure that updates or sits beside another number in a row
- Flat-by-default surfaces; the one soft ambient shadow plus an occasional
  accent-colored glow are the entire depth vocabulary — no layered elevation
- Restrained motion: a 150ms ease transition, a 2px hover lift, nothing more
  theatrical

## Colors

Nearly monochrome dark neutrals with a single loud accent — the "instrument
panel" rule made literal: everything is off until something needs attention.

### Primary
- **Chartreuse / Neon-Lime** (`#cdfa3f`, hover `#e2ff85` in dark; `#5a7209` /
  `#516808` in light theme — re-tuned per-theme, not a simple opacity shift,
  specifically to hold 4.5:1 text contrast in light mode): the one accent.
  Primary buttons, active nav/tab states, progress-bar fills, "new" badge
  glow, links. If more than roughly a fifth of a screen is chartreuse,
  something has gone wrong — its rarity is what makes it read as a signal.

### Neutral
- **Console Black** (`#0a0b10`): page background (dark theme).
- **Panel** (`#16181f`): card and panel background — one step up from the
  console floor.
- **Panel Raised** (`#1e212b`): hover/active surface state, nav-adjacent
  raised elements.
- **Hairline** (`#262a35`): all borders. Never more than 1px, never a
  decorative accent color.
- **Primary Text** (`#e6e9ef`): body and numeric text.
- **Muted Text** (`#838ca3`): secondary labels, captions, eyebrow text —
  deliberately brightened from an earlier `#7a8399` to clear 4.5:1 AA
  contrast against `--color-surface-2`; do not darken this back down.

### Status (two parallel pairs — see Named Rule below)
- **Positive / Negative** (`#22c55e` / `#ef4444`): PB deltas, workout vs.
  target comparisons.
- **Success / Danger (alt)** (`#3ddc84` / `#ff6b6b`): sync status, versus
  comparisons, pace badges, badge/journey completion. A visually distinct
  second green/red pair — not a duplicate to merge, an intentional second
  register for a more "live status indicator" feel than the PB pair's flatter
  comparison feel.
- **Warning** (`#f59e0b`): stale-PB flags, load-zone warnings.

### Named Rules
**The One Signal Rule.** Chartreuse appears only where the interface wants
the eye to land first — a primary action, something newly earned, something
currently in progress. It is never used as a passive decorative fill.

**The Two Greens Rule.** `--color-green`/`--color-red` (PB/comparison
context) and `--color-success`/`--color-danger` (live-status context) are
deliberately distinct token pairs, not drift to consolidate. Don't
cross-substitute them; each communicates a slightly different kind of
"good"/"bad."

## Typography

**Body Font:** System UI stack (`-apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, sans-serif`) — no display or label font is distinct
from it; the entire interface runs on one sans stack.
**Label/Mono Font:** `"SF Mono", "Fira Code", "Fira Mono", monospace` — used
specifically for numeric/data readouts (split times, pace tables).

**Character:** A plain, honest system-font console — the typography does no
branding work of its own; hierarchy comes entirely from size, weight, and
number treatment, not from a distinctive typeface choice.

### Hierarchy
- **Display** (700, `1.75rem`, 1.1 line-height, `tabular-nums`): the big
  stat readouts — lifetime metres, hero numbers on the dashboard gauge.
- **Title** (600, `1.5rem`, 1.3): page headers (`.page-header h1`).
- **Label** (600, `0.9rem`, `0.05em` letter-spacing, uppercase, muted color):
  section eyebrows — "the smaller muted caps line above a section," e.g.
  "Volume — past 52 weeks."
- **Body** (400, `1rem`, 1.6 line-height): all prose and default UI text.
- **Numeric** (400, `0.85rem`, monospace): tabular data — split tables,
  pace readouts — anywhere numbers must align in a column.

### Named Rules
**The Tabular Numbers Rule.** Any figure that updates live or sits next to
another number in a row (`.stat-value`, split tables, pace deltas) gets
`font-variant-numeric: tabular-nums`. Digits must not visually shift width
as they change.

## Layout

Card- and stat-block-based composition on a single-column-scales-to-grid
responsive model; no dedicated design-system container grid, just consistent
card padding and gap rhythm. Sticky top nav (56px, `.site-nav`) with a
hamburger drawer below 768px; no left icon rail (explicitly descoped in a
past redesign pass — see `docs/redesign-spec.md`). Two consolidated
breakpoints: `768px` (nav/summary-bar behavior) and `640px` (chart sizing,
tighter component stacking). Spacing runs on an unnamed-but-real 4px-based
rhythm in practice (`0.25 / 0.5 / 0.75 / 1 / 1.25 / 1.5 / 2rem` cover the
large majority of margin/padding/gap declarations) — treat those seven
values as the spacing scale for new work; anything finer is component-local
fine-tuning, not a rhythm to match.

## Elevation & Depth

Mostly flat. Cards and stat-blocks carry one shared soft ambient shadow
(`--card-shadow: 0 4px 24px rgba(0,0,0,0.35)`) for separation from the
console-black background — not a layering system, just enough lift to read
as a panel rather than a print on the page. Depth is not how the interface
marks importance; the chartreuse glow is.

### Shadow Vocabulary
- **Ambient card shadow** (`0 4px 24px rgba(0,0,0,0.35)`): default lift for
  every card/panel/stat-block. The only "at rest" shadow in the system.
- **Accent glow** (`0 0 18px color-mix(in srgb, var(--color-accent) 45%,
  transparent)`): stacked on top of the ambient shadow for elements that are
  currently primary/active (`.stat-block--primary`) or newly significant
  (a just-earned badge). Never appears alone — always additive to the
  ambient shadow, and always tied to the accent color specifically.

### Named Rules
**The Glow-Not-Depth Rule.** Don't reach for a bigger/darker shadow to mark
something as more important. Reach for the accent glow instead. Shadow depth
in this system says "this is a surface," not "this matters more."

## Shapes

Two radius steps plus a pill: `18px` (`--radius`, the default for cards,
panels, and `code`) and `10px` (`--radius-sm`, smaller components — badge
cards, form fields). A `--radius-pill` (`999px`) token covers every
fully-round element (status chips, sync buttons, avatar-style icons) — as of
this pass, the two historical spellings of "fully round" (`999px`/`99px`)
have been consolidated to this one token. All corners are soft-rounded;
nothing in the system uses a sharp 0px corner or an asymmetric/cut corner.
Borders are always 1px hairline (`--color-border`), except the signature
`.card` top edge (see below).

### Named Rules
**The Accent Top-Edge Rule.** The generic `.card` component (used on
challenges/versus/export/goals/hub pages) carries a 2px chartreuse top
border as its signature, distinguishing it from the plain-hairline
`.stat-block`/`.badge-card` family without introducing a whole new visual
language.

## Components

### Buttons
- **Shape:** `10px` radius (`--radius-sm`), never the pill or card radius.
- **Primary:** Chartreuse background; text is `#fff` in light theme but
  `#0a0b10` in dark theme (the neon accent is too light for white text to
  read on dark backgrounds — an intentional per-theme override, not a bug).
  Hover swaps to the lighter chartreuse (`#e2ff85`).
- **Ghost/Secondary:** Transparent background, muted text, hairline border.
  Hover fills with `--color-surface-2` and text brightens to full contrast.
  This is the system's only secondary-button style — every "Cancel"/"Close"
  action uses it.
- **Small variant:** `.btn-sm` reduces padding/font-size for inline/compact
  contexts (e.g. "Check for new badges").

### Cards / Containers
- **Corner Style:** `18px` (`--radius`) for the primary `.card`/`.stat-block`
  family; `10px` for the denser `.badge-card` grid.
- **Background:** `--color-surface`, one step above console black.
- **Shadow Strategy:** ambient card shadow at rest; add accent glow only for
  primary/active/earned states (see Elevation & Depth).
- **Border:** 1px hairline; `.card` specifically adds the 2px chartreuse top
  edge as its signature.
- **Internal Padding:** `1.25rem` is the default card-body padding.

### Inputs / Fields
- **Style:** `--color-surface-2` background, hairline border, `6px` radius
  (feedback form — slightly tighter than the `--radius-sm` token; a
  candidate to align in a future pass, not changed here), `0.5rem 0.75rem`
  padding.
- **Focus:** border color shifts to the accent; no glow or shadow added on
  focus, keeping focus treatment quieter than the "earned/active" glow
  reserved for bigger moments.

### Navigation
- **Style:** sticky top bar, `56px` tall, near-black background
  (`--color-nav-bg`, deliberately darker than the page background in light
  theme so the nav stays visually anchored regardless of theme), hairline
  bottom border.
- **States:** icon-only actions (feedback, theme toggle) now carry both
  `title` and `aria-label`; active/current nav item uses the accent color.
- **Mobile:** collapses to a hamburger-triggered drawer below `768px`
  rather than a bottom nav or icon rail.

### Progress / Gauges
A signature component family: linear `.progress-track`/`.progress-fill`
bars (used for badge progress, journey distance, goal completion) and a
circular gauge on the dashboard for lifetime-metres-toward-milestone. Fill
color is contextual — chartreuse for general progress, the teal alias for
Rhine-journey progress, `--color-success` for a completed bar — always a
flat fill, never a gradient.

## Do's and Don'ts

### Do:
- **Do** keep the accent to genuinely primary/active/new moments — the One
  Signal Rule.
- **Do** use `tabular-nums` on any numeric readout that updates or sits in a
  column with other numbers.
- **Do** use the accent glow, not a heavier shadow, to mark something as
  more important than its neighbors.
- **Do** route every new secondary/cancel button through `.btn-ghost` — it
  is the system's only secondary style, not one of several.
- **Do** stay within the seven-value spacing rhythm (`0.25` through `2rem`)
  for new margin/padding/gap unless a component genuinely needs finer
  fine-tuning.

### Don't:
- **Don't** introduce a second accent color. The One Signal Rule depends on
  there being exactly one.
- **Don't** add gradients, illustration, or decorative imagery — confirmed
  visual rejection, not an oversight to "improve."
- **Don't** reach for `999px`/`99px` literals for pill shapes — use
  `--radius-pill`.
- **Don't** merge `--color-green`/`--color-red` with `--color-success`/
  `--color-danger` — they're deliberately separate registers (Two Greens
  Rule), not unresolved drift.
- **Don't** treat this visual identity as locked for future work — per
  `PRODUCT.md`, the current look is negotiable, not a brand commitment; a
  future redesign proposal is legitimate, but it replaces this file
  wholesale rather than blending old and new.
