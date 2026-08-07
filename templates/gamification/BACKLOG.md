# Row Tracker — Product Backlog

> Last updated: 2026-08-07

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
| 3 | Improve virtual journey maps | Virtual Journeys | Low | Done |
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
**Area:** Virtual Journeys · **Priority:** Low · **Status:** Done

Label positioning and mobile scaling addressed:
- Waypoint label sides/positions and the "You are here" marker's placement are now computed in `blueprints/gamification.py` instead of hardcoded in each template — a fan-out algorithm pushes labels further from the line when neighbours are closely spaced (e.g. Trans-Canada's Victoria/Nanaimo/Vancouver/Kamloops, all within the first 5% of the route), and the marker label always lands opposite whichever waypoint it's nearest to, with a background pill so it stays legible even when close to other text.
- Mobile: waypoint labels are sized in SVG units and were shrinking to illegibility as the whole map scaled down to fit a phone screen. The map now holds a legible minimum width and the card scrolls horizontally instead (`.map-scroll-wrap`, same pattern as the workout-detail splits table).
- Known remaining limitation: Trans-Canada's western BC cluster (4 stops inside ~5% of a 7,821 km route) is improved but still tight — a real geometric constraint (not enough horizontal room for the labels), not a bug in the layout logic. Terrain silhouette/geographic-accuracy polish and smoother bezier curves are untouched — SVG maps were already reasonably developed there for Holland/Trans-Canada/Route 66; Rhine's curve is plainer but functional.

---

### 4 — Virtual Journeys — click on city/waypoint for facts
**Area:** Virtual Journeys · **Priority:** Low · **Status:** Done

Implemented via the Wikipedia summary API (no key required) — clicking a waypoint (map or list) opens `_waypoint_modal.html` with details and a Wikipedia link, using the original-resolution photo rather than a rescaled thumbnail.

---

## Notes & Ideas

<!-- Add any unstructured ideas or observations here -->
