# Changelog

All notable changes to Row Tracker are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) — while the major version is `0`, minor bumps may
include breaking changes (`.env` keys, schema, etc.), same as any other pre-1.0 project.

History below `0.9.0` is backfilled from commit history at the point versioning was introduced —
these releases weren't tagged contemporaneously, but the groupings and dates reflect what actually shipped.

## [0.9.12] — 2026-08-15

### Fixed
- **The nightly 3:00 AM scheduler (sync, PB recalc, badge eval, backup) was actually running at
  3:00 AM UTC**, not 3:00 AM local time as the FAQ/Quick Start have always documented ("3:00 AM
  Toronto time"). The container had no timezone configured, so it silently defaulted to UTC —
  for anyone east of Greenwich in winter or west of it generally, that's several hours off from
  the documented time, and any workout logged in that gap wouldn't sync until the *following*
  night. Added a `TZ` variable to `.env.example` (defaults to `America/Toronto`, matching the
  docs) — set it to your own [IANA zone](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
  if you're elsewhere. Existing deployments need to add `TZ=` to their own `.env` and restart —
  see the updated README.

## [0.9.11] — 2026-08-14

### Security
- **Chart.js now loads from a CDN with Subresource Integrity**, closing the one blind spot left
  from the earlier security review: the vendored copy had no version pinned anywhere and no way
  to know if it went stale. It's now pinned to Chart.js 4.4.1 with a `sha384` SRI hash verified
  against the actual bytes jsDelivr serves — a tampered or compromised CDN response would simply
  fail to execute rather than run silently.
- **The local copy stays as an automatic fallback** (`window.Chart || document.write(...)`) so
  Row Tracker's "no external dependencies required" promise holds even fully offline — an
  air-gapped homelab or a CDN outage falls back to the same file the service worker already
  pre-caches for offline PWA use. The fallback file is now byte-identical to the pinned CDN
  version (previously a different, unverified build had been hand-vendored).
- All five chart-rendering templates now share one partial (`_chart_cdn.html`) instead of
  duplicating the script tag, with the exact commands to regenerate the hash and fallback file
  documented inline for the next version bump.

## [0.9.10] — 2026-08-14

### Security
- **Upgraded the Docker image's build toolchain and OS packages.** A vulnerability scan of the
  built image found known CVEs in the base image's bundled `pip`/`setuptools`/`wheel` (and
  `jaraco-context`, a pip dependency) — none had ever been upgraded past whatever version shipped
  with the `python:3.11-slim` base image. The Dockerfile now explicitly upgrades them before
  installing app dependencies, and runs `apt-get upgrade` for OS-level packages so future rebuilds
  pick up Debian's security patches automatically. This resolved every fixable finding from the
  scan (1 HIGH, 1 HIGH, 5 MEDIUM/LOW). The remaining findings are in Debian OS utilities (chiefly
  `perl`, present in every Debian-based image) with no upstream fix published yet, and are not
  reachable through the application's own code — Row Tracker never shells out to any OS binary.

## [0.9.9] — 2026-08-11

### Fixed
- **Insights volume figures now read in consistent kilometres.** The year-over-year and
  weekly-volume cards rendered distances as an ambiguous "k m" hybrid (e.g. `1,996k m`,
  `56.0k m/week`) that read like a typo. They now show clean kilometres (`1,996 km`,
  `56.0 km/week`), including the pill and sparkline labels.

## [0.9.8] — 2026-08-10

### Added
- **`RUN_SCHEDULER` env flag** (default `true`). Set it to `false` on a secondary or
  development instance so it doesn't run the nightly Concept2 sync, PB recalc, badge
  evaluation, and backup — and doesn't fire duplicate notification emails — alongside the
  instance that owns your live data. Documented in `.env.example`.

## [0.9.7] — 2026-08-10

### Added
- **Brand logo throughout the app.** The circular rower emblem now sits in the nav bar
  (desktop and mobile) in place of the placeholder emoji, and the full "ROW TRACKER"
  lockup anchors the top of the Dashboard as a theme-switched hero — the dark-mode
  artwork in dark mode, the light-mode artwork in light mode. Logos were processed to
  transparent backgrounds so they sit cleanly on any surface, and both versions share an
  identical frame so switching themes causes no size shift.

## [0.9.6] — 2026-08-10

### Added
- **Milestones section on the Insights page** — all-time-highlight cards rendered as a
  big-number treatment: years rowing (with session count), biggest single day, total
  hours on the erg, and longest unbroken streak. These are facts rather than patterns,
  so they carry no confidence tag and appear once there's a real history behind them.
- **Year-over-year volume insight** — compares meters logged Jan 1 → today against the
  identical span of last year, so progress (or a lull) shows up as it happens.

### Changed
- **Pace-trend insight now measures steady pieces only** (20 min+). Trending pace across
  all workout types was confounded by changes in workout mix — more sprints or more easy
  volume could masquerade as a pace change. Restricting to steady work makes the trend
  mean what it says.
- Tuned insight surfacing against real data: day-of-week, rest-gap, and seasonal pace
  effects were left gated (the underlying signal is genuinely flat at the median, so
  loosening thresholds would have manufactured noise) while the new milestone and
  year-over-year rules add substance that the data actually supports.

## [0.9.5] — 2026-08-10

### Added
- **Insights page** — a new nav section that reads your whole history and surfaces
  patterns in plain language (best day of the week, rest-day effect, pace and volume
  trends, fastest stroke rate in steady pieces, session-length clusters, consistency,
  PB clustering). Each insight clears a minimum-sample and significance check before it
  appears and is tagged **Strong pattern** or **Early signal**; the strongest carry a
  recommendation, some linking into the WOD generator. Implemented as a deterministic,
  rule-based engine (`insights_engine.py`) that runs entirely on your server.
- **Optional AI "coach's read"** (`insights_ai.py`, gated by `USE_AI_INSIGHTS=true` +
  `ANTHROPIC_API_KEY`, off by default) — a short first-person synthesis at the top of the
  Insights page. It only rephrases the facts the engine already computed and never
  invents a number; the cards render identically without it.

## [0.9.4] — 2026-08-10

### Fixed
- **Manual Sync (and any other POST) no longer fails after the page has been open a while.**
  CSRF tokens carried a default 1-hour time limit, so clicking "Sync workouts" on a
  long-open dashboard returned `400 request failed — check logs` with a
  `CSRF token has expired` log line. The time limit is now disabled; tokens stay
  session-bound, which is the actual CSRF protection.

## [0.9.3] — 2026-08-07

Closes out the pre-public-release audit started in 0.9.2.

### Security
- **Rewrote git history to remove a leaked Gmail App Password** that had been present in
  `.env.example` from 2026-06-14 to 2026-07-23 (the value itself was already revoked before
  this fix). Every commit SHA from that point forward changed as a result — this repo's history
  was force-pushed once as part of this fix. No other secrets were found anywhere in history.

### Added
- `CONTRIBUTING.md` — how to report bugs/features, the fork→branch→PR flow, dev setup, and the
  doc-sync convention this codebase follows. Linked from the README.
- GitHub topics for discoverability: `self-hosted`, `concept2`, `rowing`, `ergometer`, `flask`,
  `docker`, `python`, `fitness-tracker`, `homelab`.

### Fixed
- README claimed AI coaching was "the only feature that talks to a third party" — inaccurate,
  since the Feedback button also emails the developer directly (recipient is hardcoded, not
  `.env`-configurable). Added a dedicated Feedback section spelling out exactly what it does
  and doesn't send.
- Removed dead code in `c2_api.py`: `_persist_refresh_token()` had no callers (Concept2 issues a
  non-expiring bearer token, so nothing ever rotates it) and wouldn't have worked reliably even
  if called — it wrote to `.env` inside the container, which isn't a mounted file and is now
  correctly excluded from the image entirely. Also fixed the module docstring, which still
  described an OAuth token-exchange flow the code never actually implements.

### Changed
- Untracked `designidea.webp` (unreferenced design-reference image) and two internal
  `docs/superpowers/` AI-agent planning docs — kept locally, gitignored, consistent with the
  existing `row-tracker-spec.md` / `docs/redesign-spec.md` convention.

## [0.9.2] — 2026-08-07

Fixes from a pre-public-release audit. The remaining items from that audit (a leaked
credential in git history, a couple of untracked-file cleanup questions) required user
decisions and are closed out in 0.9.3 above.

### Fixed
- **`.env` was being baked directly into the built Docker image** — no `.dockerignore` existed,
  so `COPY . .` copied the real, secret-filled `.env` file (and the entire `.git` history) into
  every image layer. The app never actually reads that in-image copy (all config comes from
  `os.environ`, populated by Compose's `env_file` at container start), so excluding it is purely
  a fix, not a behavior change. Added `.dockerignore` excluding `.env`, `.git/`, `data/`,
  `csv-data/`, caches, and other build-irrelevant paths.
- README's clone command still had the placeholder `yourusername` instead of the real
  `dsubtle1` — first-time visitors couldn't copy-paste it correctly.
- `LICENSE.md` and the README's embedded license text had mismatched copyright-name casing
  (`dSubtle1` vs `dsubtle1`).

### Changed
- Removed `python-dotenv` from `requirements.txt` — never actually imported anywhere; the app
  reads config exclusively via `os.environ`.
- Minor doc-sync polish: added `VERSION`/`CHANGELOG.md` to the README's Project Structure tree,
  normalized a wording mismatch between `QUICKSTART.md` and its in-app twin ("Start a Journey" →
  "Start a Virtual Journey").

## [0.9.1] — 2026-08-07

### Changed
- The version display moved from a centered line at the bottom of page content to a small,
  low-opacity `vX.Y.Z` badge fixed to the bottom-right corner of the viewport on every page

### Fixed
- The service worker's static-asset cache (`CACHE_NAME`) was a fixed string that never changed
  across deploys, so any CSS/JS update was invisible to a browser that had already loaded the app
  once — cache-first meant it just kept serving the old file forever. `sw.js` is now rendered from
  a Jinja template with `CACHE_NAME` tied to `app_version`, so every version bump automatically
  invalidates the old cache instead of silently serving stale static assets

## [0.9.0] — 2026-08-07

### Added
- AI-assisted WOD coaching narrative — optional Claude Haiku-generated warm-up/cool-down/coaching
  notes, feature-flagged via `USE_AI_WOD` + `ANTHROPIC_API_KEY`; falls back to the static rule-based
  text automatically if disabled or unavailable
- Versioning: `VERSION` file, this changelog, and the version now shown in the site footer and FAQ page
- Explicit self-hosting/privacy statement in the README — no Row Tracker backend, your own Concept2
  and Anthropic credentials, your own data

### Changed
- Removed the Support/sponsorship section from the README for now

## [0.8.0] — 2026-08-07

### Added
- Email notifications for newly earned badges, lifetime-metres milestones, and virtual journey completions
  (`NOTIFY_EMAIL`, defaults to `MAIL_USERNAME`)

### Changed
- Refreshed README screenshots and fixed stale documentation

## [0.7.0] — 2026-08-06

### Added
- PWA install support — manifest, app icons, service worker for offline-capable static asset caching
- Nightly automated SQLite database backups (30-day retention) via APScheduler
- Data export — workout history and personal bests as CSV or JSON
- Route test coverage across all four blueprints
- Distinct icon + progress bar per badge
- Clickable journey waypoints with a details popup and Wikipedia photo banner

### Fixed
- Badge `earned_date` defaulting to today instead of the actual earned date
- Journey map label overlap and mobile scaling
- Grainy waypoint banner images (now uses the original file, not a rescaled thumbnail)
- Dependency bump to close known CVEs

### Changed
- Vendored Chart.js locally instead of loading from a CDN

## [0.6.0] — 2026-08-05

### Added
- WOD History rewritten as a month-by-month calendar (`/wod/history`, `/api/wod/day`)
- Journey Map teaser card on the dashboard

## [0.5.0] — 2026-08-04

### Added
- Dashboard redesign (Phase R2) — circular lifetime-metres gauge, pace/volume sparklines,
  "Your Progress" journey checklist

### Fixed
- Badges never being earnable — `seed_badges()` was never actually called on startup

## [0.4.0] — 2026-08-04

### Added
- Full pytest suite for engine modules (PBs, badges, WOD generation)
- Real planned-session tracking for the Iron Month badge
- Per-stroke pace/stroke-rate visualization on the workout detail page
- UI-driven CSV import for pre-API-access seasons
- CSRF protection on every state-changing route

### Fixed
- Personal best delta (improvement-vs-previous) tracking bug

### Changed
- Redesign polish (Phase R1) — light mode and teal accent consistency
- `SECRET_KEY` fallback behavior

## [0.3.0] — 2026-06-28 to 2026-07-23

### Changed
- README screenshots, license, and formatting refresh

### Security
- Replaced a leaked Gmail app password in `.env.example` with a placeholder

## [0.2.0] — 2026-06-17 to 2026-06-18

### Added
- Mobile-responsive layout
- Heart rate data on workout detail (min/avg/max, zone classification)
- Chart improvements

## [0.1.0] — 2026-06-14

### Added
- Initial release: dashboard, Concept2 Logbook sync, personal bests, in-app feedback form,
  FAQ and Quick Start guide
