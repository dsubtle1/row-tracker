# WOD Calendar View — Design

> Status: Approved, not yet implemented
> Related: R3 item in `docs/redesign-spec.md` ("WOD calendar view")

## Background

The R1/R2 visual redesign spec called for a WOD calendar view, repurposing the
reference mockup's "Trainer's Appointment" calendar panel — there's no
trainer/appointment concept in Row Tracker, so it was earmarked to show which
days had a WOD generated or completed instead.

Investigating the WOD engine (`wod_engine.py`, `blueprints/wod.py`,
`models.WodHistory`) surfaced two things that narrow the original idea:

- **No "rest day" concept exists.** Every generated WOD is a real workout type
  (`steady_state` / `interval` / `threshold` / `long` / `test`) — the engine
  never produces a rest-day entry. The original backlog note ("upcoming rest
  days") doesn't map to anything real.
- **WODs are generated lazily, not scheduled.** `get_or_create_today()` only
  creates a `WodHistory` row when `/wod` is visited on that date. A day the
  app wasn't opened has no row at all — it isn't a "rest day," it's simply
  absent. There is no future/upcoming WOD data to show.

Given that, the calendar is a view of **past** WODs and their completion
status — not a scheduling or planning tool.

## Scope

Replace the existing paginated list at `/wod/history`
(`blueprints/wod.py::wod_history()`, `templates/wod/history.html`) with a
month-grid calendar view. Same URL, reached the same way (the "View all →"
link from the recent-history preview on `/wod`).

**Out of scope:** `/wod` (today's WOD), the random generator, the library
page, and anything resembling a future/scheduled view.

## Backend changes

### `blueprints/wod.py::wod_history()`

- Accepts `?year=YYYY&month=MM` query params, defaulting to the current
  month.
- Queries `WodHistory` rows where `generated_date` falls within that month.
- Builds a Mon–Sun week grid for the month (padding leading/trailing days
  outside the month as blank, non-interactive cells — same convention the
  dashboard's 52-week heatmap already uses).
- For each in-month calendar day, computes a status:
  - `none` — no `WodHistory` row for that date
  - `pending` — row exists, `completed` is `False`
  - `completed` — row exists, `completed` is `True`
- Passes the grid plus prev/next month links to the template.

### New endpoint: `GET /api/wod/day?date=YYYY-MM-DD`

- Looks up the `WodHistory` row for that date and returns it through the
  existing `_enrich()` helper (same shape already used by `/wod` and
  `/wod/random/<id>`).
- Returns `{"exists": false}` if no row exists for that date.
- Powers the click-to-detail modal; no other consumer.

## Frontend changes

### `templates/wod/history.html`

Rewritten from a flat `<table>` to a calendar grid:

- Weekday header row (Mon–Sun) + week rows of day cells, numbered like a
  real calendar.
- Prev/Next month navigation (links to `?year=&month=`), plus the current
  month/year as a heading.
- Each in-month day cell is clickable (including `none`-status days, matching
  the existing heatmap's pattern of making every real day clickable) and
  opens a detail modal on click.
- The modal is a self-contained copy of the dashboard's existing day-modal
  pattern (own markup + JS in this template — that modal isn't currently a
  shared component anywhere in the codebase, so this follows the existing
  per-page convention rather than introducing a new shared abstraction).
  It reuses the existing global `.day-modal*` CSS classes already defined in
  `static/css/main.css`, so no new modal styling is needed.
- Modal content for a clicked day:
  - `none` → "No WOD generated this day."
  - `pending`/`completed` → title, wod_type badge, target pace, zone,
    completion status — same fields already shown in the old list view.

### New CSS (`static/css/main.css`)

A small set of calendar-grid classes, styled with the existing `--color-*`
tokens and accent-glow conventions from R1/R2:

- `.wod-cal-grid`, `.wod-cal-header`, `.wod-cal-day`
- Status color variants: `.wod-cal-day--none`, `--pending`, `--completed`
- `.wod-cal-nav` (prev/next month links)

## Testing

- `tests/test_wod_engine.py` covers the engine; no changes needed there.
- Add coverage (new or extended test file under `tests/`) for:
  - `wod_history()` month-grid construction: correct status per day,
    correct padding for a month that doesn't start on Monday.
  - `/api/wod/day` — existing date, non-existent date, malformed date.

## Non-goals

- No changes to how/when WODs are generated.
- No "upcoming" or scheduled-future view.
- No new shared modal component — the duplication with the dashboard's
  day-modal is intentional, following the existing per-page pattern.
