# Row Tracker — Design Tokens (Master)

Extracted from `static/css/main.css` as of v0.31.2. This is a **description of
what already exists in the codebase**, not a new design direction — every
primitive/semantic value below is copied verbatim from `:root` and
`[data-theme="light"]`. Where the app has no token yet (spacing, type scale),
this doc says so explicitly rather than inventing one.

**v0.31.2 update:** the gaps flagged below (§2 badge/status colors, dark-mode
heatmap, pill radius, breakpoint drift) have since been fixed in the
codebase — this doc is left as the original audit trail, with a status note
added to each fixed section rather than rewritten, so the reasoning stays
visible.

Dark is the default theme; light is an override block, toggled via
`[data-theme="light"]` on `:root`.

---

## 1. Primitive tokens

Raw values as they appear in `:root` (dark) and `[data-theme="light"]`.

| Primitive | Dark | Light |
|---|---|---|
| `--color-bg` | `#0a0b10` | `#f1f5f9` |
| `--color-surface` | `#16181f` | `#ffffff` |
| `--color-surface-2` | `#1e212b` | `#e8eef5` |
| `--color-border` | `#262a35` | `#cbd5e1` |
| `--color-text` | `#e6e9ef` | `#0f172a` |
| `--color-text-muted` | `#838ca3` | `#475569` |
| `--color-accent` | `#cdfa3f` | `#5a7209` |
| `--color-accent-2` | `#e2ff85` | `#516808` |
| `--color-nav-bg` | `#0e0f14` | `#1e293b` |
| `--color-green` | `#22c55e` | (inherited) |
| `--color-red` | `#ef4444` | (inherited) |
| `--color-amber` | `#f59e0b` | (inherited) |

Both accent pairs are contrast-tuned, not arbitrary — see the inline comments
at `main.css:13-17` (muted text brightened to clear 4.5:1 against
`--color-surface-2`) and `main.css:42-49` (light-theme accent darkened from
`#67840b` to `#5a7209` to clear 4.5:1 as *text*, not just as a background/
border color). **Do not re-tune these without re-checking contrast** — they
were already adjusted once for exactly this reason.

Light-theme-only primitives (no dark equivalent defined):

| Primitive | Value | Note |
|---|---|---|
| `--color-text-primary` | `#0f172a` | Fallback used in later-phase components (same value as `--color-text` in light) |
| `--color-accent-val` | `#f59e0b` | Fallback, unclear consumer — flagged below |
| `--heatmap-0..4` | `#e2e8f0 → #86efac → #4ade80 → #16a34a → #14532d` | Light-theme heatmap greens |

~~Dark-theme heatmap cells are **not tokenized**...~~ **Fixed in v0.31.2.**
`--heatmap-0..4` now also exist in `:root` (dark), and both themes'
`.heatmap-cell[data-level="N"]` rules reference `var(--heatmap-N)`. This also
fixed a latent bug: the *light-theme* `--heatmap-0..4` tokens existed before
but were never actually referenced — the light heatmap rules used their own
raw hex literals, so the tokens were dead. They're wired up now.

### Typography primitives

| Primitive | Value |
|---|---|
| `--font-sans` | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` |
| `--font-mono` | `"SF Mono", "Fira Code", "Fira Mono", monospace` |

### Shape & elevation primitives

| Primitive | Value |
|---|---|
| `--radius` | `18px` |
| `--radius-sm` | `10px` |
| `--card-shadow` | `0 4px 24px rgba(0, 0, 0, 0.35)` |
| `--accent-glow` | `0 0 18px color-mix(in srgb, var(--color-accent) 45%, transparent)` |
| `--transition` | `150ms ease` |

---

## 2. Semantic tokens

Purpose-aliases already defined, resolving through the primitives above so
theme switching is automatic:

| Semantic | Resolves to | Purpose |
|---|---|---|
| `--color-teal` | `var(--color-accent)` | Legacy name, same value as accent — kept for back-compat, treat as an alias not a distinct color |
| `--color-bg` / `--color-surface` / `--color-surface-2` | primitives | Page background / card background / raised panel background, 3-step elevation |
| `--color-text` / `--color-text-muted` | primitives | Primary / secondary text |
| `--color-border` | primitive | All hairline borders |
| `--color-accent` / `--color-accent-2` | primitives | Brand accent (default / hover-lighter) |
| `--color-green` / `--color-red` / `--color-amber` | primitives | Status semantics (success / error / warning) — **not theme-overridden**, same in light and dark |

### Gaps (no semantic token yet, found via grep of literal usage)

- **Focus/active states** on interactive elements mostly reuse `--color-accent` directly rather than a `--color-focus` semantic — fine today since there's only one accent, but if a second brand color is ever introduced this coupling will need to be broken out.
- ~~**Badge/status colors**...~~ **Fixed in v0.31.2.** `#3ddc84`/`#ff6b6b` are now formal tokens `--color-success`/`--color-danger` (kept as a *second* pair, deliberately not merged into `--color-green`/`--color-red` — different hue, already visually established across sync-status/versus/pace-badge/badge-glow, so merging would have been a visual redesign, not a token extraction). All call sites now reference the tokens instead of repeating the hex.

---

## 3. Component tokens (inferred, not formally declared)

The codebase doesn't have explicit `--button-bg`-style component tokens —
components consume semantic tokens directly in their rule blocks. Documenting
the effective per-component values as-implemented:

| Component | Property | Value |
|---|---|---|
| `.btn-primary` | background / border | `var(--color-accent)` |
| `.btn-primary` | text | `#fff` (light theme) / `#0a0b10` (dark theme — override at `main.css:1199-1202`, because the neon accent is too light for white text) |
| `.btn-primary:hover` | background / border | `var(--color-accent-2)` |
| `.btn-ghost` | background | `transparent` |
| `.btn-ghost` | text / border | `var(--color-text-muted)` / `var(--color-border)` |
| `.btn-ghost:hover` | background / text | `var(--color-surface-2)` / `var(--color-text)` |
| `.btn-sm` | padding / font-size | `0.3rem 0.75rem` / `0.78rem` (single definition as of v0.31.1 — a duplicate at a later line was removed) |
| Cards (`.card`, `.badge-card`, etc.) | shadow | `var(--card-shadow)`, some with `+ var(--accent-glow)` |
| `code` | radius | `var(--radius)` — reuses the *card* radius for an inline text element; `--radius-sm` would read as more proportionate here |

---

## 4. Spacing — not yet tokenized

**No `--space-*` scale exists.** Margin/padding/gap values are authored as
raw `rem` literals throughout. Frequency survey across `main.css`
(occurrences of each value across `margin`/`padding`/`gap` declarations):

| Value | Uses | Value | Uses |
|---|---|---|---|
| `0.5rem` | 38 | `1.25rem` | 15 |
| `1rem` | 37 | `0.25rem` | 14 |
| `0.75rem` | 26 | `2rem` | 7 |
| `0.4rem` | 18 | `1.75rem` | 5 |
| `1.5rem` | 17 | `3rem` | 1 |
| `0.6rem` | 16 | `2.5rem` | 1 |

The top 6 values (`0.25 / 0.5 / 0.75 / 1 / 1.25 / 1.5 / 2rem`) already form a
near-perfect 4px-based scale (4/8/12/16/20/24/32px at the 16px root) — this
is a **recommendation**, not an existing token, since the instruction here
was to describe what's real, not invent new values:

```css
/* Proposed --space-* scale — NOT YET IN THE CODEBASE.
   Values are the app's own most-used numbers, just named. */
--space-1: 0.25rem;  /* 4px */
--space-2: 0.5rem;   /* 8px */
--space-3: 0.75rem;  /* 12px */
--space-4: 1rem;     /* 16px */
--space-5: 1.25rem;  /* 20px */
--space-6: 1.5rem;   /* 24px */
--space-8: 2rem;     /* 32px */
```
The long tail (`0.1rem`, `0.15rem`, `0.2rem`, `0.3rem`, `0.35rem`, `0.45rem`,
`0.55rem`, `0.65rem`, `0.9rem`, `1.1rem`, `1.2rem`, `1.75rem`...) is one-off
fine-tuning on individual components and shouldn't be forced onto a scale.

---

## 5. Typography scale — not yet tokenized

Same situation: **no `--font-size-*` variables exist.** `font-size` is set
directly per-rule, and the values are considerably more scattered than
spacing — 30 distinct values across the file, many within 0.02–0.05rem of
each other (`0.7 / 0.72 / 0.75 / 0.78rem`, `0.85 / 0.88 / 0.9rem`), which
reads as organic drift across separate additions rather than a deliberate
scale. Most-used values:

| Value | Uses | Value | Uses |
|---|---|---|---|
| `0.85rem` | 25 | `0.7rem` | 11 |
| `0.8rem` | 22 | `0.78rem` | 10 |
| `0.9rem` | 13 | `1rem` (body) | 10 |
| `0.72rem` | 13 | `0.65rem` | 8 |
| `0.75rem` | 12 | `0.88rem` | 6 |

Font weights are cleaner and closer to a real scale already: `400` (rare),
`500`, `600` (dominant — 53 uses), `700`, `800` (one use, headline-only).

**Not proposing a type-scale token set here** — unlike spacing, the existing
values don't cluster into an obvious clean scale, so collapsing them would be
a design decision (which sizes get merged into which), not a mechanical
extraction. Flagging as a candidate for a follow-up pass if you want one.

---

## 6. Radius — mixed tokenized / untokenized

Two formal tokens exist (`--radius: 18px`, `--radius-sm: 10px`) but several
components bypass them with their own literal radius:

| Literal | Uses | Likely should be |
|---|---|---|
| `999px` / `99px` | ~~12 combined~~ **Fixed in v0.31.2** — both spellings replaced with a new `--radius-pill: 999px` token, all 12 call sites now reference it | Pill/full-round shape |
| `10px` / `12px` | 2 each | `--radius-sm` (10px matches exactly; 12px is a near-miss) |
| `8px` | 3 | Close to `--radius-sm`, not identical |
| `4px` / `6px` | 3 each | No existing token this small — candidate for a `--radius-xs` if kept intentional |
| `2px` / `3px` | 2 each | Likely a focus-ring or indicator detail, probably fine as one-offs |

---

## 7. Breakpoints — not tokenized (CSS custom properties can't hold media queries)

Actual breakpoints in use, as literals in `@media`:

| Breakpoint | Uses | Purpose (inferred from context) |
|---|---|---|
| `max-width: 768px` | 4 | Primary mobile/tablet breakpoint |
| `max-width: 640px` | 4 | Secondary, tighter mobile breakpoint |
| `max-width: 600px` | 1 | One-off, close enough to 640px to likely be mergeable |
| `max-width: 700px` | 1 | One-off, sits between the two main breakpoints |
| `min-width: 769px and max-width: 1024px` | 1 | Tablet band |
| `prefers-reduced-motion: reduce` | 1 | Accessibility — good that this exists |

~~Three near-duplicate mobile breakpoints...~~ **Fixed in v0.31.2.** The
`600px` block (chart sizing) now triggers at `640px`, and the `700px` block
(summary-bar stacking) now triggers at `768px` — both self-contained blocks
with no dependency on the exact number, so widening the trigger threshold
was a safe, value-only change. Down to two consistent breakpoints across the
whole file.

---

## Summary: what's already a real token vs. what's documented-only

| Category | Status |
|---|---|
| Color (primitive + semantic) | ✅ Fully tokenized, theme-aware, contrast-audited. As of v0.31.2, also covers the success/danger pair and dark-mode heatmap. |
| Font family | ✅ Tokenized |
| Radius | ⚠️ `--radius`, `--radius-sm`, `--radius-pill` (new in v0.31.2) exist; a few small-radius components (4-12px) still bypass them |
| Shadow | ⚠️ One shared token (`--card-shadow`) + several one-off `box-shadow` literals |
| Transition | ✅ Tokenized (`--transition`, though not universally applied) |
| Breakpoints | ✅ Consolidated to two values (`640px`/`768px`) as of v0.31.2; still literals, not CSS vars — media queries can't hold them |
| Spacing | ❌ No tokens — proposal only, §4 |
| Font size | ❌ No tokens — not proposed, needs a design decision, §5 |
