# Row Tracker — Product Backlog

> Last updated: 2026-08-06

---

## How to use this document

Add new items as they come up. Update **Status** and **Priority** as work progresses.

**Status values:** `Open` · `In Progress` · `Done` · `Deferred` · `Cancelled`  
**Priority values:** `High` · `Medium` · `Low`

---

## Backlog Items

| # | Item | Area | Priority | Status |
|---|------|------|----------|--------|
| 1 | Colours in light mode — review and refine palette | UI / Design | Medium | Done |
| 2 | Achievements page refinement | Gamification | Medium | Done |
| 3 | Improve virtual journey maps | Virtual Journeys | Low | Open |
| 4 | Virtual Journeys — click on city/waypoint for facts | Virtual Journeys | Low | Done |

---

## Item Details

### 1 — Colours in light mode
**Area:** UI / Design · **Priority:** Medium · **Status:** Done

Light mode now has 87 dedicated `[data-theme="light"]` overrides in `main.css` covering cards, badges, challenges, journeys, WOD, charts, and modals. Charts were brought in line with the site palette (see "Finish chart work: match site palette, add empty/error states").

---

### 2 — Achievements page refinement
**Area:** Gamification · **Priority:** Medium · **Status:** Done

`templates/gamification/badges.html` now has distinct `earned` / `locked` badge-card states, per-category earned/total counts, in-progress badges show a progress bar with current/target, and a summary progress bar sits at the top of the page.

---

### 3 — Improve virtual journey maps
**Area:** Virtual Journeys · **Priority:** Low · **Status:** Open

SVG maps are in place for Rhine, Holland Tour, Trans-Canada, and Route 66. Further refinement options:
- Better terrain silhouettes and geographic accuracy
- Improved label positioning to reduce overlap
- Smoother bezier curves on tighter route sections
- Mobile scaling review

---

### 4 — Virtual Journeys — click on city/waypoint for facts
**Area:** Virtual Journeys · **Priority:** Low · **Status:** Done

Implemented via the Wikipedia summary API (no key required) — clicking a waypoint (map or list) opens `_waypoint_modal.html` with details and a Wikipedia link, using the original-resolution photo rather than a rescaled thumbnail.

---

## Notes & Ideas

<!-- Add any unstructured ideas or observations here -->
