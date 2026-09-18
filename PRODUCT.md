# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: Concept2 RowErg athletes who want deeper training analytics than the
stock Concept2 Online Logbook provides, and are comfortable self-hosting a
Docker container (technical enough to run `docker compose up`, supply their
own Concept2 API credentials, and manage their own SQLite data file).

The maintainer (the user in this session) is the first and primary user,
running it on a homelab server for personal daily use. The project is public
and built to also serve other self-hosters in the same position — confirmed:
"Me + other self-hosters." Still early-stage/alpha, single-maintainer
software (per `CONTRIBUTING.md`); real external adoption is nascent, not yet
established at scale.

## Product Purpose

A self-hosted personal rowing analytics app for Concept2 RowErg machines. It
syncs automatically from the Concept2 Logbook API, tracks personal bests
across 8 standard distances/times, generates daily workout recommendations,
surfaces pattern-based insights across training history, and turns lifetime
metres rowed into virtual journeys (real-world routes like the Rhine or
Route 66) as a gamified progress metaphor. Success means an athlete
understands their training trends and progress better than the stock
Concept2 Logbook shows them, without giving up control of their data.

## Positioning

100% self-hosted with no Row Tracker-operated backend: the app talks
directly to the user's own Concept2 Logbook account using their own API
credentials, and all data lives in a SQLite file on their own machine. A
hosted competitor could replicate individual features (PB tracking, badges,
journeys) but could not truthfully make the same "your server, your
credentials, your data" claim without abandoning the hosted-SaaS model
entirely — this is a structural, not cosmetic, difference.

## Operating Context

- Deployed via Docker Compose on a home server (the maintainer's own
  homelab), single port, no external dependencies beyond the Concept2 API
  and (optionally) SMTP for feedback and Anthropic's API for AI coaching.
- Nightly automatic sync from Concept2 at 3:00 AM; on-demand manual sync
  also available.
- CSV import path exists for pre-API-era workout history (Concept2 Logbook
  exports), with explicit accounting for skipped/invalid/duplicate rows.
- Fully responsive; used on desktop and installed as a home-screen PWA on
  iPhone/iPad (Add to Home Screen) and Android.
- Single-user per deployment — no auth/multi-user concept. Each self-hoster
  runs their own isolated instance for themselves.

## Capabilities and Constraints

- Backend: Flask + SQLite, no frontend build step — plain Jinja2 templates,
  vanilla JS, hand-written CSS in `static/`. Engine logic (PB calculation,
  badges, WOD generation, insights) lives in top-level modules, unit-tested
  directly; Flask routes in `blueprints/` stay thin.
- No GPS/route data exists per workout (indoor erg, Concept2 doesn't provide
  it) — "Virtual Journeys" are a distance-accumulation metaphor over static
  real-world routes, not actual GPS tracks.
- AI-assisted coaching exists in the codebase but is currently **off** — it
  requires an Anthropic API key the maintainer doesn't currently hold (on
  Claude Pro, not API access). Do not design as if it's a one-click/always-on
  feature.
- In-app feedback button emails the maintainer directly via the user's own
  SMTP credentials.
- Alpha-stage software; conventions may still shift, per `CONTRIBUTING.md`.

## Brand Commitments

None locked in as binding for future design work — confirmed: "Current look
is negotiable." Treat the current visual identity (dark-mode-default with
light-mode toggle, neon-green/lime accent `#cdfa3f`, existing logo) as the
incumbent starting point and useful evidence, not a constraint future
redesign work must preserve.

Note for context: the current look is itself the product of a deliberate,
already-completed redesign (`docs/redesign-spec.md` — moved from a
blue-accent/top-nav layout to the current dark-card/neon-green-accent
identity, referencing a "Thrive Form" fitness-dashboard mockup, shipped in
stages R1–R3). It reflects one past decision, not an ongoing constraint.

## Evidence on Hand

- Real screenshots of every major surface in `docs/screenshots/` (Dashboard,
  Workout of the Day, Virtual Journeys, Charts, Insights, Quick Start).
- `design-system/row-tracker/MASTER.md` — a token audit of the existing
  `static/css/main.css` (color, radius, shadow, spacing/type-scale usage
  frequency), written 2026-09-18.
- `docs/redesign-spec.md` — prior visual-redesign spec/history (see Brand
  Commitments above).
- `docs/feature-ideas.md` and `docs/marketing-plan.md` — existing
  brainstormed backlog and marketing thinking; check before re-deriving
  "what's next" or proposing new positioning.
- No testimonials, case studies, press, or usage-benchmark data exist yet —
  do not fabricate any; the product is pre-wide-adoption.

## Product Principles

1. **Data ownership is the point, not a footnote.** Every design decision
   should read as consistent with "your server, your credentials, your
   data" — no dark patterns, no implying data leaves the user's control.
2. **Self-hoster-legible, not consumer-SaaS-polished.** The audience is
   technical enough to run Docker and manage API credentials; clarity and
   honesty (e.g. explicit disclosure of CSV-import data gaps, honest
   "not yet earned" states) matter more than gloss that papers over real
   limitations.
3. **Single-user, single-purpose.** No multi-tenant/auth complexity to
   design around; every screen can assume "this is the one athlete who
   owns this instance."
4. **Alpha-honest.** Don't over-promise polish or completeness the product
   doesn't have yet; the FAQ and CONTRIBUTING docs already model this tone
   and future design work should match it.
5. **Gamification serves motivation, not vanity metrics.** Badges, journeys,
   and streaks exist to sustain a real training habit, not to manufacture
   engagement for its own sake.

## Accessibility & Inclusion

WCAG 2.1 AA, explicit — confirmed. This formalizes work already done ad hoc
(e.g. `--color-text-muted` was deliberately brightened from `#7a8399` to
`#838ca3` because the former only cleared 4.2:1 against `--color-surface-2`,
below the 4.5:1 AA minimum for normal text; the light-theme accent was
similarly re-tuned for the same reason — see `main.css:13-17` and
`main.css:42-49`). Future design work should be checked against 4.5:1 text
contrast and other AA criteria as a named requirement, not incidental care.
