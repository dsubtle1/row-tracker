# Changelog

All notable changes to Row Tracker are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) — while the major version is `0`, minor bumps may
include breaking changes (`.env` keys, schema, etc.), same as any other pre-1.0 project.

History below `0.9.0` is backfilled from commit history at the point versioning was introduced —
these releases weren't tagged contemporaneously, but the groupings and dates reflect what actually shipped.

## [0.9.2] — 2026-08-07

Fixes from a pre-public-release audit. See also the still-open items from that audit
(a leaked credential in git history, a couple of untracked-file cleanup questions) —
those required user decisions and aren't closed out by this release alone.

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
