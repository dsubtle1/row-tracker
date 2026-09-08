# Changelog

All notable changes to Row Tracker are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/) — while the major version is `0`, minor bumps may
include breaking changes (`.env` keys, schema, etc.), same as any other pre-1.0 project.

History below `0.9.0` is backfilled from commit history at the point versioning was introduced —
these releases weren't tagged contemporaneously, but the groupings and dates reflect what actually shipped.

## [0.26.1] — 2026-09-08

### Fixed
- **FAQ described a WOD training-phase system that doesn't exist.** The docs claimed the engine
  "looks at your last 28 days of training to determine your current phase (base, build, peak, or
  recovery)" — there is no phase concept anywhere in `wod_engine.py`. Corrected the FAQ (and its
  in-app twin, plus the unused `faq_template.html` and the README Features list) to describe what
  the engine actually does: a 7-day under-representation check against a target session-type mix,
  modified by the CAWR training-load signal. No behavior change — documentation only.

## [0.26.0] — 2026-09-08

### Added
- **Unified Day View.** A single day's story used to be scattered across four separate pages
  with no connection between them: the WOD plan, the actual workout, notes, and any PB. A new
  page at `/day/<date>` pulls all of it together — the planned WOD (with its actual-vs-planned
  comparison when the two are linked), every workout actually synced that day, notes, and any
  personal best achieved — with prev/next-day navigation and a "Today" badge. Linked from the
  dashboard heatmap's day-click modal, the WOD History calendar's day-click modal, and every
  workout detail page.

### Changed
- Moved `actual_vs_planned()` and the WOD-enrichment helper from `blueprints/wod.py`'s private
  functions into `wod_engine.py` as public functions, so both `blueprints/wod.py` and the new
  Day View route can share the same logic without duplication.

## [0.25.1] — 2026-09-07

### Fixed
- **Waypoint detail card rendered behind the journey map instead of in front of it.** Leaflet's
  own panes and zoom control use z-index values up to 1000, higher than the shared modal shell's
  z-index of 100/101 — so on a journey page (the only place a modal now shares the page with a
  map) the card and its dimming backdrop were losing the stacking order to the map underneath.
  Raised both to 2000/2001, comfortably above Leaflet's range. Click-outside-to-close was already
  wired (the backdrop's own click handler) and needed no change — it just couldn't be reached
  while the map sat on top of it.

## [0.25.0] — 2026-09-07

### Added
- **Real maps for all four virtual journeys**, replacing hand-tuned SVG route illustrations —
  Leaflet.js + OpenStreetMap, every waypoint at its real-world latitude/longitude, a smoothed
  curve through them (not a literal river/highway trace — see docs/feature-ideas.md), and your
  current position as a pulsing marker. Works identically in dark and light theme.

### Changed
- Deleted ~200 lines of now-dead SVG label-collision-avoidance code (fan-out ranks, left/right
  alternation) — real maps handle marker placement themselves. The waypoint-click-for-Wikipedia
  feature needed zero changes; its click delegation worked immediately against the new markers.
- README/FAQ/QUICKSTART: corrected the Trans-Canada waypoint count (24, not 23) and documented two
  network dependencies the "nothing leaves your server" pitch didn't previously mention — map
  tiles fetched live on every journey-map view, and the pre-existing (undocumented) Wikipedia API
  call on waypoint click.

## [0.24.1] — 2026-09-07

### Changed
- **The pre-built GHCR image is now the primary install path in the README**, not an alternative
  buried after the build-from-source instructions. A fresh install no longer needs a `git clone`
  at all — just a `.env` and a `docker-compose.yml` pointing at
  `ghcr.io/dsubtle1/row-tracker:latest`, both shown inline. Verified end-to-end in a clean
  directory with no repo present. Building from source (for unreleased changes or contributing)
  is now the documented alternative. No code change — the repo's own `docker-compose.yml` stays on
  `build: .` since local dev and the homelab's deploy script depend on always running the exact
  latest committed source, not the last tagged release.

## [0.24.0] — 2026-09-07

### Added
- **WOD actual-vs-planned feedback.** `actual_workout_id` on a completed WOD was never actually
  reachable — no template ever submitted a `workout_id` when marking a WOD complete. Marking one
  complete now auto-links the workout you synced that day, but only when there's exactly one
  same-day candidate; more than one is left unlinked rather than guessing wrong. Once linked, the
  WOD card shows whether you hit target pace within 2%, or how far off you were — same treatment
  on both the periodization WOD page and the Random WOD Generator result page.

## [0.23.0] — 2026-09-07

### Added
- **Head-to-head workout comparison.** Tick the checkbox next to any two workouts on the Workouts
  page and click Compare for a split-by-split pace chart overlaying both, plus a side-by-side
  split table. Different granularity from the existing "You vs Past You" (monthly aggregates) —
  this is workout-vs-workout. The split-parsing logic already used by the workout detail page was
  extracted into a shared `_compute_splits()` helper rather than duplicated. Same limitation the
  detail page already has: workouts with no per-split data (a single continuous piece, or a
  CSV-imported workout) can't be compared — surfaced as a clear message, not a silent failure.

## [0.22.0] — 2026-09-07

### Added
- **Sync now detects and logs non-rower results excluded from the Concept2 API.** `c2_api.py`'s
  `type=rower` filter is applied server-side, so a workout logged under a different Concept2
  machine type never even appeared in the response — silently, with no trace. Sync now makes one
  extra lightweight request per run to compare the rower-only result total against the true total
  across every machine type, logging a warning if they ever diverge. Pure observability: nothing
  about what gets synced or stored changes, and this account currently has zero excluded results
  (verified live against the real API before shipping).

## [0.21.0] — 2026-09-07

### Added
- **PB progression chart.** Every PB card on the Personal Bests page now has a "View progression"
  button opening a chart of every genuine record-breaking result in that category over time — not
  just the current-vs-previous comparison the card itself already showed. `PersonalBest` only
  ever stored the current best plus one prior value, so this is computed on request
  (`pb_engine.progression_for_category()`) using the exact same category-matching filters
  `recalculate_all_pbs()` already trusts, not a new history table. Reuses the already-vendored
  Chart.js include and the existing day-detail modal shell (new `.day-modal--wide` modifier for
  the extra width a chart needs) rather than adding new chart or modal infrastructure.

## [0.20.0] — 2026-09-07

### Added
- **Insights page transparency for gated insight types.** Below the 60-workout sample floor, a
  banner now shows progress toward it. Separately, the day-of-week and rest-gap-effect checks —
  which the v0.9.6 release already found are gated because the signal is genuinely flat for some
  accounts, not just short on data — now say so explicitly ("Checked — no day of the week stands
  out in your pace right now") instead of staying silently absent. Deliberately no countdown for
  that second case, since more workouts logged doesn't guarantee a pattern will appear.
  `generate_insights()`'s existing signature is unchanged; a new `generate_insights_and_gates()`
  powers this without touching any other rule or caller.

## [0.19.0] — 2026-09-07

### Added
- **Workout notes.** Every workout detail page now has a free-text Notes field (up to 2,000
  characters) — somewhere to record how a session felt, an equipment change, or why it got cut
  short, none of which Concept2 tracks.
- **Automatic schema sync on startup (`app._sync_schema()`).** `db.create_all()` only creates
  missing tables, never alters existing ones — every nullable column this app has added
  post-launch (`rest_distance_meters`, `rest_time_seconds`, `stroke_count`, `heart_rate_max`, and
  now `notes`) has needed someone to manually run `ALTER TABLE` against every already-running
  instance. This makes that step automatic and idempotent instead: on every startup, any model
  column missing from the live database is added on the spot, logged, and never touched again.
  SQLite `ADD COLUMN` only — additive, safe, no drops or renames.

## [0.18.0] — 2026-09-07

### Added
- **Date-range and distance-range filters on the Workouts page.** `workout_list()` previously took
  only a `page` parameter. Filters are plain GET query params (bookmarkable/shareable), combine
  together, and are validated leniently — a bad hand-edited date is ignored rather than 400ing.
- **Pagination controls on the Workouts page.** Found while building the filters: the page had no
  prev/next links at all before this, so anything past page 1 was only reachable by hand-editing
  the URL. New pagination carries the active filters across pages.

## [0.17.0] — 2026-09-07

### Added
- **ETA projections on the four lifetime-metres badges** (First 100k, Quarter Million, Half
  Million, One Million). While locked, each now shows a rough unlock date projected from your
  rolling 28-day average pace — the same calculation the virtual journeys already use for
  waypoint ETAs, now shared via `badge_engine.weekly_avg_meters()` instead of copy-pasted four
  times across the journey routes in `blueprints/gamification.py`. No ETA shown when recent pace
  is flat or the target's already passed.

## [0.16.0] — 2026-09-07

### Added
- **Backup restore, from the Export Data page.** `backup.py` has written nightly snapshots to
  `data/backups/` since day one, but there was no way to restore one short of SSHing in and
  copying a file over the live database by hand. The Export Data page now lists every backup
  with a Restore button; restoring requires typing RESTORE into a confirmation dialog first,
  since it replaces all current data. The live database is automatically snapshotted to its own
  timestamped safety copy immediately before the swap, so a restore is itself undoable. Uses the
  same SQLite online-backup API `backup.py` already relies on, just with source and destination
  reversed — no new backup mechanism, no schema change.

## [0.15.0] — 2026-09-07

### Added
- **Multi-channel notifications: ntfy.sh, Discord, and a generic webhook, alongside email.**
  `notify.py`'s `_send()` used to be hardcoded to Flask-Mail; it now fans out independently to any
  combination of `NOTIFY_EMAIL` (existing), `NOTIFY_NTFY_TOPIC`, `NOTIFY_DISCORD_WEBHOOK_URL`, and
  `NOTIFY_WEBHOOK_URL` — all optional, all blank/off by default, and each fails independently so a
  broken webhook can't block email or vice versa. Covers all four existing notification types
  (badges, milestones, job failures, journey completions) with no changes to their call sites.
  `.env`-configured only, no UI, matching the existing Concept2/mail integration pattern.

## [0.14.0] — 2026-09-06

### Added
- **CAWR training-load transparency on the WOD page.** The periodization engine has always computed
  your acute:chronic workload ratio and silently swapped today's session to steady-state when it's
  elevated (or biased it toward interval/threshold when it's low) — but never said why. The WOD
  card now shows the CAWR value and a plain-language note whenever it's available, so a session
  swap is explainable instead of mysterious. No schema change: `WodSpec` gained `cawr`/`cawr_note`
  fields that ride along in the existing `wod_history.wod_json` blob. Random-generator WODs are
  unaffected — that path never used periodization or CAWR to begin with.

## [0.13.0] — 2026-08-21

### Added
- **Two more Insights Milestones: total strokes taken and peak heart rate.** New `stroke_count`
  and `heart_rate_max` columns, captured on every sync going forward. Neither has a work/rest
  split to worry about — C2 doesn't report rest-period strokes or a separate rest heart rate, so
  both are plain per-session values (total strokes is a whole-session sum; peak HR is the highest
  single reading across history, with the date it happened).
- `backfill_strokes_hr.py` — same live-API backfill pattern as `backfill_rest_meters.py`, for the
  same reason (most historical workouts here were CSV-imported, no local raw_json to read this
  from). Unlike badges/journeys, Insights milestones are computed fresh on every page load rather
  than earned-once-and-locked, so there's nothing to retroactively correct here.

## [0.12.0] — 2026-08-21

### Added
- **Two new Insights Milestones: total workouts logged and total calories burned.** Lifetime
  counterparts to the existing "years rowing" and "hours on the erg" cards, same "always-true
  fun fact" treatment (gated only on having enough history, no significance test). Concept2 has
  no rest-period calorie figure anywhere in its API, so total calories is a plain sum — no
  work/rest split to worry about there, unlike distance and time.
- **New `rest_time_seconds` column, mirroring `rest_distance_meters` (0.11.0).** Concept2 tracks
  rest-interval time separately from work-interval time the same way it does distance —
  `Workout.total_time_seconds` (work + rest) now feeds the "hours on the erg" milestone, so a
  session with light rowing between intervals counts all of it as real time spent rowing. Pace
  and PBs stay on work-only `time_seconds`, untouched, same reasoning as the meters fix.
- `backfill_rest_meters.py` now backfills both `rest_distance_meters` and `rest_time_seconds` in
  the same live-API pass.

## [0.11.2] — 2026-08-20

### Added
- **GitHub Releases are now created automatically on every version tag push**
  (`.github/workflows/publish-image.yml`), with notes pulled straight from that version's
  CHANGELOG.md section. Previously a tag push only built the GHCR image — the Release itself was
  always a manual step, and it quietly stopped happening after v0.10.4 (v0.10.5 through v0.11.1
  shipped with tags but no Releases until this was noticed and backfilled).

### Fixed
- CHANGELOG.md was missing the `## [0.10.4]` header — the Dependabot entry had been folded
  invisibly into `[0.10.5]`'s section since it shipped.

## [0.11.1] — 2026-08-20

### Fixed
- **`C2ApiClient.get_results()` was reading the wrong pagination key** (`meta.last_page` instead
  of the real `meta.pagination.total_pages`), so it silently stopped after the first 100 results
  on every sync. Nightly incremental syncs rarely hit that ceiling so it went unnoticed, but a
  historical backfill or a sync recovering from a long outage would have quietly dropped
  everything past page 1. Fixed, and now covered by a regression test.
- Added retries (3 attempts, short backoff) for transient C2 API failures — its results endpoint
  returns occasional bare 500s in normal operation, seen firsthand in production, and one of
  those was tripping the nightly sync's failure alert for no real reason.
- `backfill_rest_meters.py` (see 0.11.0) now sources rest-distance values from a live re-fetch of
  the full C2 history (matched by workout ID) instead of local `raw_json` — most historical
  workouts here were CSV-imported and never had `raw_json` locally, so the previous approach only
  recovered data for ~150 of 2559 workouts. Re-running it against the live API on top of this
  release backfilled the rest correctly.

## [0.11.0] — 2026-08-20

### Fixed
- **Interval workout "rest" meters (light rowing between intervals) were silently dropped from
  every lifetime/volume total.** Concept2 tracks rest-interval distance as a separate
  `rest_distance` field, apart from each interval's own `distance` — the C2 sync only ever read
  `distance`, so none of it ever made it into Row Tracker. Discovered by comparing against the
  Concept2 website's "Lifetime Meters" figure, which includes it. New `rest_distance_meters`
  column (`models.py`) captured on every sync going forward; `backfill_rest_meters.py` backfills
  it from `raw_json` for existing workouts and retroactively corrects the earned dates of the
  five volume badges and one virtual journey that had already crossed their thresholds under the
  old, undercounted totals.
- Pace, personal bests, single-piece test results, and CAWR/training-load are unaffected — they
  were already, and remain, based on work-interval distance/time only, so a slower recovery split
  can never inflate a time or a PB.

### Added
- Workout detail page now shows rest-interval meters alongside the main distance stat when a
  session had any.

## [0.10.5] — 2026-08-16

### Added
- **Pre-built multi-arch Docker images, published to GHCR on every version tag**
  (`.github/workflows/publish-image.yml`) — `linux/amd64` and `linux/arm64` (Raspberry Pi and
  other ARM boards), tagged with the version, `major.minor`, and `latest`. This is an
  *additional* way to run Row Tracker, not a replacement — `docker-compose.yml` still defaults
  to `build: .` so the homelab deploy flow (`deploy.sh`) is unaffected. Self-hosters who'd rather
  `docker compose pull` than build locally can swap in `image: ghcr.io/dsubtle1/row-tracker:latest`
  — documented in the README under "Using the pre-built image instead of building locally."

## [0.10.4] — 2026-08-16

### Added
- **Dependabot** (`.github/dependabot.yml`) — weekly automated PRs for outdated pip dependencies
  (`requirements.txt`/`requirements-dev.txt`), the Docker base image, and the GitHub Actions added
  in 0.10.2. Every Dependabot PR gets checked by the same CI workflow as any other PR, so a bump
  that breaks something fails the check instead of merging silently.

## [0.10.3] — 2026-08-16

### Fixed
- CI workflow pinned `actions/checkout@v4` and `actions/setup-python@v5` — the first run flagged
  both as being forced onto a deprecated Node.js runtime. Bumped to the current majors
  (`@v7`/`@v7`).

## [0.10.2] — 2026-08-16

### Added
- **CI: GitHub Actions now runs the full test suite on every push to `main` and every PR**
  (`.github/workflows/tests.yml`) — 228 tests, Python 3.11 to match the Docker base image, pip
  dependency caching. The test suite has existed for a while but nothing ran it automatically;
  now a red check on a PR means something needs a look before merge. Status badge added to the
  top of the README, alongside the license badge.
- `CONTRIBUTING.md` updated to mention the automated check.

## [0.10.1] — 2026-08-15

### Fixed
- **"Insights" was missing from the mobile nav drawer** — it was added to the desktop nav when
  the Insights page shipped (0.9.5) but never added to the hamburger menu, so it was invisible on
  phones/tablets ever since. Added, and covered by a new regression test that diffs the desktop
  and mobile nav link sets so a future addition can't silently repeat this.

## [0.10.0] — 2026-08-15

### Fixed
- **The v0.9.12 timezone fix didn't actually fix the root cause.** `scheduler.py` has always
  passed `timezone="America/Toronto"` to `BackgroundScheduler`, which looks correct — but that
  setting does **not** propagate to a job's `CronTrigger` unless the trigger is *also* given an
  explicit timezone. Every nightly `CronTrigger(hour=3, ...)` call was silently falling back to
  the container's OS clock instead, which is exactly the bug v0.9.12's `TZ` env var papered over
  by making the OS clock coincidentally correct. Every `CronTrigger` now gets the timezone
  explicitly (sourced from the `TZ` env var, defaulting to `America/Toronto`), so the schedule is
  correct regardless of the container's OS timezone.
- **A bad or expired C2 API token was indistinguishable from "nothing new to sync."** `get_results()`
  caught 401s and network failures internally and just returned an empty list — identical to a
  genuinely successful call that found zero new workouts. `C2ApiClient` now tracks the actual
  failure reason (`last_error`) and `sync_workouts()` surfaces it as a real error instead of a
  silent no-op.
- The manual Sync button's frontend only treated `status: "error"` as a failure, missing the
  `"partial"` state the `/sync` route already returns when a sync completes with errors — a
  partially-failed sync showed as a plain success in the UI. Now shown as a failure with the
  actual error message.

### Added
- **"Last synced" indicator on the Dashboard**, next to the Sync button — shows how long ago the
  last successful sync ran, or a clear warning if the most recent attempt failed. Backed by a new
  `SyncStatus` table, updated by both the nightly scheduler and manual syncs.
- **Email alerts on scheduled-job failure.** The nightly sync, PB recalc, badge evaluation, and
  backup jobs previously only logged their own failures — now they also email `NOTIFY_EMAIL`
  (same address badge/milestone notifications already use), so a broken job doesn't sit unnoticed
  until someone happens to check container logs.

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
