# WOD Calendar View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paginated WOD history list at `/wod/history` with a month-by-month calendar grid showing which days had a WOD generated and whether it was completed, with click-to-detail.

**Architecture:** Two pure/DB-query helper functions added to `wod_engine.py` (testable in isolation, following the existing engine-logic-lives-here convention). `blueprints/wod.py` gets a thin route rewrite plus one new JSON endpoint. `templates/wod/history.html` is rewritten from a `<table>` to a calendar grid with a self-contained detail modal (mirroring the dashboard's existing day-modal pattern, not extracting a shared component — that modal isn't shared anywhere else in the codebase today). New CSS added alongside removal of now-dead CSS from the old list view.

**Tech Stack:** Flask, Jinja2, SQLAlchemy, vanilla JS (no build step), pytest.

## Global Constraints

- This codebase has **no Flask test client / blueprint route test infrastructure** — `tests/conftest.py`'s `app_ctx` fixture only binds `models.db` to a throwaway SQLite DB via a bare `Flask(__name__)`, it never registers blueprints. Every existing test (`test_wod_engine.py`, `test_badge_engine.py`, etc.) tests engine functions directly, never routes. Follow this convention: put testable logic in `wod_engine.py` and unit-test it there; verify the Flask routes and templates manually via the browser, not via new test-client machinery.
- Per project convention (see prior session), after any code change that could affect the running app: rebuild and restart the Docker container (`docker compose up -d --build`) so the change can be tested live, without being asked.
- Per project convention, whenever user-facing behavior changes, update `README.md`, `FAQ.md`, `QUICKSTART.md`, and their in-app template twins (`templates/tracker/faq.html` + `faq_template.html`, `templates/tracker/quickstart.html` + `quickstart_template.html`), without being asked.
- `docs/redesign-spec.md` is intentionally untracked in git (local-only design notes) — still update it to reflect progress, but do not `git add` it.

---

### Task 1: Calendar-grid and day-lookup helpers in `wod_engine.py`

**Files:**
- Modify: `wod_engine.py` (add `import calendar` to the import block at the top; add two new functions near `get_or_create_today`, which is defined around line 591)
- Test: `tests/test_wod_engine.py`

**Interfaces:**
- Produces: `build_month_calendar(year: int, month: int) -> list[list[dict]]` — each cell dict has keys `date` (a `datetime.date`), `day` (int, day-of-month number), `in_month` (bool), `status` (one of `"none"`, `"pending"`, `"completed"`).
- Produces: `get_wod_for_date(target_date: date) -> WodHistory | None` — the most-recently-created `WodHistory` row for that date, or `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_wod_engine.py` (append at the end of the file; add `build_month_calendar` and `get_wod_for_date` to the existing `from wod_engine import (...)` block at the top):

```python
# ---------------------------------------------------------------------------
# build_month_calendar — month grid shape, padding, and per-day status
# ---------------------------------------------------------------------------

def test_build_month_calendar_shape_and_padding(app_ctx):
    # August 2026: starts on a Friday, so the grid pads 5 days from July
    # and 6 days from September to complete Mon-Sun weeks.
    weeks = build_month_calendar(2026, 8)

    assert len(weeks) == 6
    assert all(len(week) == 7 for week in weeks)

    first_week_dates = [c["date"] for c in weeks[0]]
    assert first_week_dates == [
        date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29),
        date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2),
    ]
    first_week_in_month = [c["in_month"] for c in weeks[0]]
    assert first_week_in_month == [False, False, False, False, False, True, True]

    last_week = weeks[-1]
    assert last_week[0]["date"] == date(2026, 8, 31)
    assert last_week[0]["in_month"] is True
    assert last_week[1]["date"] == date(2026, 9, 1)
    assert last_week[1]["in_month"] is False


def test_build_month_calendar_status_per_day(app_ctx):
    db.session.add_all([
        WodHistory(generated_date=date(2026, 8, 5), wod_type="interval", wod_json={}, completed=True),
        WodHistory(generated_date=date(2026, 8, 6), wod_type="steady_state", wod_json={}, completed=False),
    ])
    db.session.commit()

    weeks = build_month_calendar(2026, 8)
    by_date = {c["date"]: c for week in weeks for c in week}

    assert by_date[date(2026, 8, 5)]["status"] == "completed"
    assert by_date[date(2026, 8, 6)]["status"] == "pending"
    assert by_date[date(2026, 8, 7)]["status"] == "none"
    # Out-of-month padding days are always "none" regardless of any data
    assert by_date[date(2026, 7, 27)]["status"] == "none"


def test_build_month_calendar_latest_row_wins_on_regeneration(app_ctx):
    # A day can have multiple WodHistory rows if the WOD was regenerated
    # (wod_generate() always inserts a new row rather than updating).
    db.session.add(WodHistory(id=1, generated_date=date(2026, 8, 5), wod_type="interval", wod_json={}, completed=True))
    db.session.commit()
    db.session.add(WodHistory(id=2, generated_date=date(2026, 8, 5), wod_type="steady_state", wod_json={}, completed=False))
    db.session.commit()

    weeks = build_month_calendar(2026, 8)
    by_date = {c["date"]: c for week in weeks for c in week}
    assert by_date[date(2026, 8, 5)]["status"] == "pending"


# ---------------------------------------------------------------------------
# get_wod_for_date
# ---------------------------------------------------------------------------

def test_get_wod_for_date_returns_latest_row(app_ctx):
    db.session.add(WodHistory(id=1, generated_date=date(2026, 8, 5), wod_type="interval", wod_json={"title": "First"}, completed=True))
    db.session.commit()
    db.session.add(WodHistory(id=2, generated_date=date(2026, 8, 5), wod_type="steady_state", wod_json={"title": "Second"}, completed=False))
    db.session.commit()

    row = get_wod_for_date(date(2026, 8, 5))
    assert row.id == 2
    assert row.wod_json["title"] == "Second"


def test_get_wod_for_date_returns_none_when_absent(app_ctx):
    assert get_wod_for_date(date(2026, 8, 5)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_wod_engine.py -k "build_month_calendar or get_wod_for_date" -v`
Expected: FAIL with `ImportError` (names not yet defined in `wod_engine.py`).

- [ ] **Step 3: Implement the two functions**

Add `import calendar` to the top of `wod_engine.py`, in the import block:

```python
from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
```

Add the two functions near `get_or_create_today` (after it, same file):

```python
def build_month_calendar(year: int, month: int) -> list[list[dict]]:
    """
    Return a Mon-Sun week grid for the given year/month.

    Each cell is a dict:
        {"date": date, "day": int, "in_month": bool,
         "status": "none" | "pending" | "completed"}

    Days outside the requested month (padding to complete the first/last
    week) always get status "none" and in_month=False.
    """
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    rows = (
        WodHistory.query
        .filter(WodHistory.generated_date >= first_day, WodHistory.generated_date <= last_day)
        .order_by(WodHistory.id.asc())
        .all()
    )
    # A day can have multiple rows if the WOD was regenerated — the latest
    # (highest id) row wins, matching get_or_create_today()'s convention.
    latest_by_date: dict[date, WodHistory] = {}
    for row in rows:
        latest_by_date[row.generated_date] = row

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        week_cells = []
        for d in week:
            in_month = d.month == month
            row = latest_by_date.get(d) if in_month else None
            if row is None:
                status = "none"
            else:
                status = "completed" if row.completed else "pending"
            week_cells.append({"date": d, "day": d.day, "in_month": in_month, "status": status})
        weeks.append(week_cells)
    return weeks


def get_wod_for_date(target_date: date) -> Optional[WodHistory]:
    """Return the most recently created WodHistory row for target_date, or None."""
    return (
        WodHistory.query
        .filter(WodHistory.generated_date == target_date)
        .order_by(WodHistory.id.desc())
        .first()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_wod_engine.py -k "build_month_calendar or get_wod_for_date" -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass (no change to any existing behavior).

- [ ] **Step 6: Commit**

```bash
git add wod_engine.py tests/test_wod_engine.py
git commit -m "Add month-calendar and day-lookup helpers to wod_engine"
```

---

### Task 2: Route rewrite in `blueprints/wod.py`

**Files:**
- Modify: `blueprints/wod.py`

**Interfaces:**
- Consumes: `build_month_calendar(year, month)` and `get_wod_for_date(target_date)` from Task 1; existing `_enrich(row)` helper already in this file.
- Produces: `GET /wod/history?year=&month=` (template context: `weeks`, `month_label`, `prev_year`, `prev_month`, `next_year`, `next_month`) and `GET /api/wod/day?date=YYYY-MM-DD` (JSON) for Task 3's template to consume.

- [ ] **Step 1: Update the import line**

Find:
```python
from wod_engine import WOD_LIBRARY, generate_wod, generate_random_wod, get_or_create_today, save_wod
```

Replace with:
```python
from wod_engine import (
    WOD_LIBRARY,
    build_month_calendar,
    generate_wod,
    generate_random_wod,
    get_or_create_today,
    get_wod_for_date,
    save_wod,
)
```

- [ ] **Step 2: Add a private month-arithmetic helper**

Add near the other helpers at the top of the file (after `_fmt_duration`):

```python
def _adjacent_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by delta months (delta is +1 or -1)."""
    total = year * 12 + (month - 1) + delta
    shifted_year, shifted_month0 = divmod(total, 12)
    return shifted_year, shifted_month0 + 1
```

- [ ] **Step 3: Replace the `wod_history` route and add `api_wod_day`**

Find this whole block:
```python
@wod_bp.route("/wod/history")
def wod_history():
    """Past WODs with completion status — most recent first."""
    page = request.args.get("page", 1, type=int)
    rows = (
        WodHistory.query
        .order_by(WodHistory.generated_date.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )
    history = [_enrich(r) for r in rows.items]
    return render_template("wod/history.html", history=history, pagination=rows)
```

Replace with:
```python
@wod_bp.route("/wod/history")
def wod_history():
    """Calendar view of past WODs — browse month by month, click a day for detail."""
    today = date.today()
    year  = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)

    weeks = build_month_calendar(year, month)
    prev_year, prev_month = _adjacent_month(year, month, -1)
    next_year, next_month = _adjacent_month(year, month, 1)

    return render_template(
        "wod/history.html",
        weeks=weeks,
        month_label=date(year, month, 1).strftime("%B %Y"),
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
    )
```

Add this new route at the bottom of the file, after `api_wod_today`:

```python
@wod_bp.route("/api/wod/day")
def api_wod_day():
    """JSON — WOD detail for a single date. Powers the calendar's click-to-detail modal."""
    date_str = request.args.get("date", "")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    row = get_wod_for_date(target)
    if row is None:
        return jsonify({"exists": False})

    data = _enrich(row)
    data.pop("actual_workout", None)   # SQLAlchemy object — not JSON serializable
    data["date"] = data["date"].isoformat()
    data["exists"] = True
    return jsonify(data)
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests pass (this task adds no new automated tests — see Global Constraints on why routes aren't unit-tested in this codebase). Manual verification happens in Task 5.

- [ ] **Step 5: Commit**

```bash
git add blueprints/wod.py
git commit -m "Rewrite /wod/history as a month calendar, add /api/wod/day"
```

---

### Task 3: Rewrite `templates/wod/history.html`

**Files:**
- Modify: `templates/wod/history.html` (full rewrite)

**Interfaces:**
- Consumes: template context from Task 2's `wod_history()` route (`weeks`, `month_label`, `prev_year`, `prev_month`, `next_year`, `next_month`); `GET /api/wod/day?date=` from Task 2.
- Consumes CSS classes added in Task 4 (`.wod-cal-*`) and pre-existing global classes (`.day-modal*`, `.dms-block`, `.dms-value`, `.dms-label`, `.day-modal-empty`, `.day-modal-loading`).

- [ ] **Step 1: Replace the full file contents**

```html
{% extends "base.html" %}
{% block title %}WOD History — Row Tracker{% endblock %}

{% block content %}

<div class="page-header">
  <h1>WOD History</h1>
</div>

<div class="wod-cal-nav">
  <a href="{{ url_for('wod.wod_history', year=prev_year, month=prev_month) }}" class="wod-cal-nav-link">← Prev</a>
  <span class="wod-cal-nav-label">{{ month_label }}</span>
  <a href="{{ url_for('wod.wod_history', year=next_year, month=next_month) }}" class="wod-cal-nav-link">Next →</a>
</div>

<div class="wod-cal-grid">
  <div class="wod-cal-header-row">
    {% for label in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] %}
      <div class="wod-cal-header-cell">{{ label }}</div>
    {% endfor %}
  </div>
  {% for week in weeks %}
  <div class="wod-cal-week">
    {% for cell in week %}
      <div class="wod-cal-day wod-cal-day--{{ cell.status }}{% if not cell.in_month %} wod-cal-day--outside{% endif %}"
           {% if cell.in_month %}data-date="{{ cell.date.isoformat() }}"{% endif %}>
        <span class="wod-cal-daynum">{{ cell.day }}</span>
      </div>
    {% endfor %}
  </div>
  {% endfor %}
</div>

{# Day detail modal #}
<div class="day-modal-backdrop" id="wodDayModalBackdrop" onclick="closeWodDayModal()"></div>
<div class="day-modal" id="wodDayModal">
  <div class="day-modal-header">
    <span class="day-modal-date" id="wodDayModalDate"></span>
    <button class="day-modal-close" onclick="closeWodDayModal()">✕</button>
  </div>
  <div class="day-modal-body" id="wodDayModalBody">
    <div class="day-modal-loading">Loading…</div>
  </div>
</div>

{% endblock %}

{% block extra_js %}
<script>
document.querySelectorAll(".wod-cal-day[data-date]").forEach(function (cell) {
  cell.addEventListener("click", function () {
    openWodDayModal(this.dataset.date);
  });
});

function openWodDayModal(dateStr) {
  const backdrop = document.getElementById("wodDayModalBackdrop");
  const modal    = document.getElementById("wodDayModal");
  const dateEl   = document.getElementById("wodDayModalDate");
  const body     = document.getElementById("wodDayModalBody");

  const dt = new Date(dateStr + "T00:00:00");
  dateEl.textContent = dt.toLocaleDateString("default", {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });

  body.innerHTML = '<div class="day-modal-loading">Loading…</div>';
  backdrop.classList.add("day-modal-backdrop--open");
  modal.classList.add("day-modal--open");

  fetch("/api/wod/day?date=" + dateStr)
    .then(r => r.json())
    .then(data => {
      if (!data.exists) {
        body.innerHTML = '<p class="day-modal-empty">No WOD generated this day.</p>';
        return;
      }
      body.innerHTML =
        '<div class="day-modal-workout">' +
          '<div class="day-modal-stats">' +
            '<div class="dms-block"><span class="dms-value">' + data.title + '</span><span class="dms-label">workout</span></div>' +
            '<div class="dms-block"><span class="dms-value">' + data.target_pace_str + '/500m</span><span class="dms-label">target pace</span></div>' +
            '<div class="dms-block"><span class="dms-value">' + data.pace_zone + '</span><span class="dms-label">zone</span></div>' +
            '<div class="dms-block"><span class="dms-value">' + (data.completed ? "✓ Done" : "—") + '</span><span class="dms-label">status</span></div>' +
          '</div>' +
        '</div>';
    });
}

function closeWodDayModal() {
  document.getElementById("wodDayModalBackdrop").classList.remove("day-modal-backdrop--open");
  document.getElementById("wodDayModal").classList.remove("day-modal--open");
}
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/wod/history.html
git commit -m "Rewrite WOD history template as a month calendar grid"
```

---

### Task 4: Calendar CSS — add new classes, remove dead ones

**Files:**
- Modify: `static/css/main.css`

**Interfaces:**
- Produces: `.wod-cal-nav`, `.wod-cal-nav-link`, `.wod-cal-nav-label`, `.wod-cal-grid`, `.wod-cal-header-row`, `.wod-cal-week`, `.wod-cal-header-cell`, `.wod-cal-day`, `.wod-cal-daynum`, `.wod-cal-day--outside`, `.wod-cal-day--pending`, `.wod-cal-day--completed` — consumed by Task 3's template.

- [ ] **Step 1: Remove the now-dead CSS from the old list view**

Find (in the `/* ---- History table ---- */` section):
```css
/* ---- History table ---- */
.wod-history-table-wrap {
  overflow-x: auto;
  margin-bottom: 1.5rem;
}

.wod-row--completed td { opacity: 0.7; }

.status-done    { color: var(--color-green); font-size: 0.85rem; font-weight: 500; }
.status-pending { color: var(--color-text-muted); font-size: 0.85rem; }

.mono { font-family: var(--font-mono); font-size: 0.85rem; }

/* ---- Pagination ---- */
.pagination {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.5rem;
}

.page-link {
  font-size: 0.85rem;
  color: var(--color-accent);
}

.page-info {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
```

Replace with (keeping `.status-done`/`.status-pending`/`.mono` — they're used elsewhere; only `.wod-history-table-wrap`, `.wod-row--completed`, and the whole `.pagination`/`.page-link`/`.page-info` block are page-specific to the old list and become fully dead once Task 3 lands):
```css
.status-done    { color: var(--color-green); font-size: 0.85rem; font-weight: 500; }
.status-pending { color: var(--color-text-muted); font-size: 0.85rem; }

.mono { font-family: var(--font-mono); font-size: 0.85rem; }
```

- [ ] **Step 2: Add the calendar CSS**

Add a new section (e.g. right after the block edited in Step 1):

```css
/* ---- WOD Calendar (history page) ---- */
.wod-cal-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}

.wod-cal-nav-link {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-accent);
}

.wod-cal-nav-label {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text);
}

.wod-cal-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wod-cal-header-row,
.wod-cal-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}

.wod-cal-header-cell {
  text-align: center;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  padding-bottom: 0.4rem;
}

.wod-cal-day {
  aspect-ratio: 1;
  border-radius: var(--radius-sm, 8px);
  background: var(--color-surface-2);
  padding: 0.4rem;
  transition: opacity var(--transition);
}

.wod-cal-day[data-date] {
  cursor: pointer;
}

.wod-cal-day[data-date]:hover {
  opacity: 0.8;
}

.wod-cal-daynum {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.wod-cal-day--outside {
  background: transparent;
  opacity: 0.35;
}

.wod-cal-day--pending {
  background: color-mix(in srgb, var(--color-accent) 20%, var(--color-surface-2));
}

.wod-cal-day--completed {
  background: color-mix(in srgb, var(--color-green) 55%, var(--color-surface-2));
}

@media (max-width: 640px) {
  .wod-cal-header-cell { font-size: 0.6rem; }
  .wod-cal-daynum { font-size: 0.7rem; }
}
```

- [ ] **Step 3: Commit**

```bash
git add static/css/main.css
git commit -m "Add WOD calendar CSS, remove dead history-list/pagination CSS"
```

---

### Task 5: Manual verification, docs, and redeploy

**Files:**
- Modify: `README.md`, `QUICKSTART.md`, `FAQ.md`, `templates/tracker/faq.html`, `templates/tracker/faq_template.html`, `templates/tracker/quickstart.html`, `templates/tracker/quickstart_template.html`, `docs/redesign-spec.md` (untracked, do not `git add`)

- [ ] **Step 1: Rebuild and restart the container**

Run: `docker compose up -d --build`
Expected: container recreated and started with no build errors.

- [ ] **Step 2: Manual browser walkthrough**

Using the `claude-in-chrome` tools (or equivalent manual check):
- Navigate to `/wod/history`. Confirm the current month renders as a grid, weekday headers read Mon–Sun, and today's cell is visually distinguishable if it has a WOD.
- Click Prev repeatedly until crossing a January boundary (e.g. land on January, click Prev again) — confirm it lands on December of the previous year, not a broken date.
- Click Next repeatedly across a December→January boundary — confirm it advances to January of the next year.
- Click a day with status `none` — modal should open and show "No WOD generated this day."
- Click a day with status `pending` or `completed` (generate one via `/wod` first if the current month has none) — modal should show title, target pace, zone, and status.
- Toggle light/dark theme and confirm the calendar cells and modal remain legible in both.
- Check at a mobile viewport width (~375px) that the 7-column grid doesn't overflow.

- [ ] **Step 3: Update docs**

In `README.md`, find the "Training Data" or WOD-related feature bullet list and add a line describing the calendar (mirroring the style of existing bullets, e.g. under wherever WOD-related features are listed).

In `QUICKSTART.md` and `FAQ.md`, add a short mention of the new calendar view at `/wod/history`, following the existing tone (see how the Journey Map card was documented in the FAQ's "Virtual Journeys" section for the pattern to match: state what it shows and when it appears).

Apply the same additions to the in-app twins: `templates/tracker/faq_template.html` and `templates/tracker/faq.html` (identical `<details class="faq-item">` block in both), and `templates/tracker/quickstart_template.html` and `templates/tracker/quickstart.html` (identical `<li>` in both).

- [ ] **Step 4: Update the local redesign spec**

In `docs/redesign-spec.md`, find the R3 section and mark the WOD calendar item done with a short implementation note (matching the style already used for the Journey Map item in that same section). This file is gitignored — edit it but do not stage or commit it.

- [ ] **Step 5: Rebuild and restart again, then commit docs**

Run: `docker compose up -d --build`

```bash
git add README.md QUICKSTART.md FAQ.md templates/tracker/faq.html templates/tracker/faq_template.html templates/tracker/quickstart.html templates/tracker/quickstart_template.html
git commit -m "Document the WOD calendar view in README/FAQ/QUICKSTART and in-app twins"
```

---

## Self-Review Notes

- **Spec coverage:** month-grid backend (Task 1), route + API (Task 2), template + modal (Task 3), CSS (Task 4), manual verification + docs + redeploy (Task 5) — all spec sections are covered.
- **Known gotcha called out explicitly:** `_enrich()`'s `actual_workout` field is a raw SQLAlchemy `Workout` object, not JSON-serializable — Task 2's `api_wod_day` explicitly pops it before `jsonify`, and the `date` field is explicitly converted with `.isoformat()`. Without these two lines the endpoint would 500 on its first real call.
- **Type/name consistency checked:** `build_month_calendar` and `get_wod_for_date` signatures in Task 1 match exactly how they're imported and called in Task 2; cell dict keys (`date`, `day`, `in_month`, `status`) match what Task 3's template reads (`cell.date`, `cell.day`, `cell.in_month`, `cell.status`); JS field names read in Task 3 (`data.exists`, `data.title`, `data.target_pace_str`, `data.pace_zone`, `data.completed`) match what Task 2's `api_wod_day` actually returns via `_enrich()`.
