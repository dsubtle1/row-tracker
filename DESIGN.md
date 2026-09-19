---
name: Row Tracker
description: A modern, open dashboard for Concept2 rowing analytics — big type, tonal zones, wave dividers, full dark/light support
colors:
  bg-dark: "#0D0F12"
  bg-alt-dark: "#15181C"
  text-dark: "#F3F4F5"
  muted-dark: "#8A9099"
  accent-dark: "#4C7FFF"
  bg-light: "#FFFFFF"
  bg-alt-light: "#F4F5F7"
  text-light: "#14171B"
  muted-light: "#5B6168"
  accent-light: "#2F54D6"
  success: "#34D399"
  success-light-mode: "#0F9D64"
  warning-dark: "#E8A33D"
  warning-light-mode: "#A8670A"
typography:
  display:
    fontFamily: "'Bricolage Grotesque', sans-serif"
    fontSize: "5.75rem"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  title:
    fontFamily: "'Instrument Sans', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "'Instrument Sans', sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "'Instrument Sans', sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  pill: "999px"
spacing:
  sm: "8px"
  md: "24px"
  lg: "40px"
  xl: "56px"
components:
  button-primary:
    backgroundColor: "{colors.accent-dark}"
    textColor: "#FFFFFF"
    rounded: "{rounded.pill}"
    padding: "13px 24px"
---

# Design System: Row Tracker

## Overview

**Creative North Star: "Open Deck"**

Row Tracker's dashboard is composed like an open, uncluttered instrument
readout, not a grid of boxed widgets. Structure comes from type scale,
whitespace, and full-width tonal zones — never from bordered, shadowed
rectangles floating on the page. The page is organized into wide horizontal
bands of alternating background tone, each one a distinct topic (hero,
status, trends, activity, journeys), transitioning into the next through a
gentle SVG wave rather than a hard edge — a quiet nod to the sport itself,
water and stroke rhythm, without illustrating it literally anywhere else.

This is a deliberate replacement of the prior "Erg Console" identity
(near-black, neon-chartreuse, card-and-border-heavy), not a refinement of
it. The old system is evidence of what came before, not a constraint on
this one — per `PRODUCT.md`, the visual identity was always negotiable.
Big, confident numbers carry the page; nothing needs a box drawn around it
to be legible as a group.

**Key Characteristics:**
- No bordered/shadowed card containers anywhere — grouping and hierarchy
  come from type scale and generous whitespace instead
- Full-bleed tonal zones (alternating base/alt background) separate major
  sections, edge to edge, rather than boxes floating on a page
- Zone transitions are gentle SVG waves, not straight lines — alternating
  curve direction between consecutive transitions so the rhythm doesn't
  feel mechanically repeated
- One accent color per theme, reserved for the page's genuinely primary
  action and for active/progress fills — never decorative
- Full, equally-considered support for both dark and light themes is a
  hard requirement, not an afterthought bolted onto one default

## Colors

Two complete, independently-tuned palettes — dark is not simply light
inverted, and light is not dark with the lights turned up. Every token has
a considered value in both themes, including contrast-corrected accents.

### Primary
- **Signal Blue** (dark `#4C7FFF`, light `#2F54D6`): the one accent. Primary
  action button, progress-bar fills, milestone-progress line, active links.
  The light-mode value is deliberately deeper than the dark-mode one — the
  bright dark-mode blue falls short of 4.5:1 as text on white, so light
  mode gets its own darker value tuned to hold that contrast, the same
  reasoning the prior system already used for its own accent.

### Neutral
- **Base** (dark `#0D0F12`, light `#FFFFFF`): the page's primary zone
  background (hero, trends, journeys zones).
- **Alt** (dark `#15181C`, light `#F4F5F7`): the alternating zone background
  (stats/sync, activity zones) — a barely-there tonal shift, not a second
  hue.
- **Text** (dark `#F3F4F5`, light `#14171B`): primary text and big numbers.
- **Muted** (dark `#8A9099`, light `#5B6168`): secondary labels, captions.
- **Divider** (dark `rgba(255,255,255,0.08)`, light `rgba(0,0,0,0.08)`): the
  only hairlines in the system — used strictly within tightly-grouped
  inline items (a stat trio's column dividers, list-row separators), never
  to box a section.

### Status
- **Success** (`#34D399` dark / `#0F9D64` light): completed journeys,
  positive states. Same darkening-for-light-mode-contrast pattern as the
  accent.
- **Warning** (`#E8A33D` dark / `#A8670A` light): stale-sync and
  attention-needed states.

### Named Rules
**The One Signal Rule (carried forward).** Exactly one accent per theme,
reserved for the page's one genuinely actionable element and for
in-progress fills. This is the same discipline the prior system named —
only the color and the material language around it changed.

**The No-Box Rule.** No component gets a border-plus-background-plus-shadow
treatment to read as a group. If something needs visual separation, that's
a signal to either add whitespace, use a zone boundary, or use a single
hairline — never all three, never a bounding box.

## Typography

**Display Font:** Bricolage Grotesque (weights 500–700) — the wordmark and
every large hero/stat number.
**Body Font:** Instrument Sans (weights 400–600) — everything else: labels,
body text, buttons, captions.

**Character:** Bricolage Grotesque has just enough personality in its
curves to feel considered rather than off-the-shelf, without tipping into
novelty — it carries the page's few big numbers. Instrument Sans stays
completely out of the way for everything else. Two families, clearly
distinct roles, never mixed within one text element.

### Hierarchy
- **Display** (600–700, 56–92px depending on context, line-height ~1,
  tabular numerals): the hero lifetime-metres figure and other headline
  numbers. Large numbers are abbreviated at display size (`16.8M`) with the
  full precision given as body-font supporting text directly below
  (`16,811,637m rowed — lifetime`) — the display figure is for impact, the
  supporting line is for accuracy.
- **Section label** (500, 15px): the small label introducing each zone's
  content ("Pace trend", "Your progress") — sentence case, never tracked-out
  caps.
- **Stat number** (600–700, 22–34px, tabular numerals): secondary numbers
  in the stats row and journey list.
- **Body** (400–500, 13–17px): everything else.

### Named Rules
**The Abbreviate-Then-Confirm Rule.** Any headline-scale number gets a
short display form plus a full-precision confirmation line immediately
below it in the body font — never the full unabbreviated digit string set
at display size, and never the abbreviation alone with no way to see the
real number.

## Layout

No grid of uniform cards. The page is a single column of five full-bleed
zones, top to bottom: **Hero** (wordmark, lifetime figure, milestone
progress), **Status** (stat trio, last session, sync state and action),
**Trends** (pace sparkline, weekly volume), **Activity** (the volume
heatmap), **Journeys** (progress list, journey map). Each zone spans the
full viewport width with its own background tone and internal padding
(40px sides, more generous top/bottom); content within a zone uses normal
flow with type-scale-driven spacing (24–56px between groups) rather than a
component grid.

Left-aligned throughout — no centered blocks, no asymmetric overlap. The
one deliberate rhythm break is the zone-to-zone wave transition (see
Elevation & Depth), which exists specifically so five flat-colored bands
don't read as a stack of unrelated slides.

## Elevation & Depth

Flat, full stop — no shadows anywhere in this system, which is itself the
main departure from the prior system's ambient-card-shadow-everywhere
approach. Depth is not this system's vocabulary; separation is handled
entirely by background-tone zoning and the wave dividers between them.

### Named Rules
**The Wave-Not-Line Rule.** Every zone boundary is a gentle SVG wave
(a single smooth S-curve, ~32px tall, full viewport width), not a straight
edge — alternating curve direction at each successive transition so
consecutive dividers don't look like a stamped repeat. This is the system's
one recurring motif tying the layout back to rowing/water without
illustrating either literally. Never use a straight horizontal rule to
separate two zones; a straight hairline is reserved for separating rows
*within* a zone (see Colors → Neutral → Divider).

## Shapes

One radius value in active use: fully round (`999px`) on the primary
action button — a pill, not a rounded rectangle. Everything else (stat
blocks, zones, list rows) has no radius at all, since nothing is drawn as
a bounded shape to begin with. Small UI elements (chart bars, progress-bar
fills) use a modest 2–3px radius purely to soften their own tiny corners,
not as a system-wide corner language.

## Components

### Buttons
- **Primary:** the only button style in this system so far. Fully rounded
  pill, filled with the accent color, white text in both themes (the
  accent is tuned dark enough in light mode to hold white-text contrast
  too), no border. Generous padding (13px × 24px) — reads as a real tap
  target, not a compressed chip.
- No secondary/ghost button exists yet in this system; when one is needed,
  it should stay borderless and rely on text color + underline or a subtle
  background tint on hover, consistent with the No-Box Rule — not a
  bordered rectangle.

### Stat Groups
- **Style:** a row of value-over-label pairs, divided only by a single
  1px hairline between columns (not around the group). No background, no
  padding-as-container — the numbers and their whitespace ARE the
  component.
- Where a pairing is logically related but there isn't room for a fourth
  full column (e.g. "this week" + "this month"), two numbers share one
  column side by side rather than adding a fifth column — keeps the row at
  four visual chunks, not five.

### Progress
- **Style:** a 3px flat line (track = neutral tint, fill = accent or
  success), fully rounded ends. No circular gauge, no percentage ring —
  progress is always a horizontal line, whether it's the milestone
  indicator, a journey's completion, or a list row's inline bar.

### Lists (journey rows, etc.)
- **Style:** each row is icon + label + value/progress, separated from its
  neighbors by a single top hairline (the whole list has hairlines between
  rows, plus one closing rule at the very bottom — never a box around the
  list).

### Charts (sparkline, bar chart, heatmap)
- **Style:** drawn directly on the zone background with no surrounding
  frame — a bare SVG polyline for trend lines, bare flat-topped bars (no
  gradient) for the volume chart, a compact cell grid for the heatmap
  (cell color intensity = accent color at increasing opacity, from a
  neutral empty state to full accent at peak activity). A small legend
  (Less → More) sits directly below the heatmap, same as the prior system.

## Do's and Don'ts

### Do:
- **Do** keep every component's separation to whitespace, a zone boundary,
  or a single hairline — pick exactly one per situation, never stack them.
- **Do** give every token a real, separately-tuned value in both dark and
  light mode — including re-deriving an accent's exact value per theme
  when contrast demands it, not just swapping background/foreground.
- **Do** abbreviate headline numbers with a full-precision line directly
  beneath.
- **Do** alternate the wave-divider's curve direction between consecutive
  transitions.

### Don't:
- **Don't** add a border, background fill, and shadow to the same element
  to make it read as a "card" — that's the exact pattern this system
  replaced.
- **Don't** use a straight rule to separate two zones; that's what the wave
  divider is for.
- **Don't** introduce a second accent color, in either theme.
- **Don't** default to dark-only or light-only in future work on this
  system — both are first-class, and a change that only considers one
  theme is an incomplete change.
