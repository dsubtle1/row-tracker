# Row Tracker — FAQ & Known Issues

*Alpha release · v0.9.0*

---

## Frequently Asked Questions

### Getting Started

**What is Row Tracker?**
Row Tracker is a personal analytics app for Concept2 rowing machine workouts. It connects to your Concept2 Online Logbook and pulls your workout data automatically, giving you pace trends, personal bests, badges, virtual journeys, and daily workout recommendations — all in one place.

**Do I need a Concept2 account?**
Yes. Row Tracker pulls your data from the Concept2 Online Logbook. If you row with a Concept2 machine and use the ErgData app, your workouts are already being synced to your logbook automatically after each session.

**How does Row Tracker get my workout data?**
It connects to the Concept2 Logbook API using your account credentials. Once connected, it syncs your workouts automatically every night at 3:00 AM (Toronto time) and you can also trigger a manual sync at any time from the Dashboard.

**Does it work on my phone or tablet?**
Yes — Row Tracker is fully responsive and optimised for iPhone and iPad, with a hamburger nav drawer on smaller screens.

**Can I install Row Tracker like an app on my phone?**
Yes. On iPhone/iPad, open Row Tracker in Safari, tap the Share icon, then **Add to Home Screen** — it launches full-screen with its own icon, no browser chrome. On Android/Chrome, look for an **Install app** option in the browser menu. Full install support (the browser-native install prompt) requires the app to be served over HTTPS — on a plain-HTTP homelab setup, iOS's Add to Home Screen still works, but Android's install prompt may not appear until you put a reverse proxy with a certificate in front of it.

---

### Data & Sync

**How often does my data sync?**
Automatically every night at 3:00 AM (see `TZ` in your `.env` — defaults to Toronto time). You can also click the Sync button on the Dashboard at any time to pull in your latest workouts immediately.

**How do I know if the nightly sync is actually working?**
The Dashboard shows a "Last synced" indicator next to the Sync button, so you don't have to take it on faith. If a nightly sync, PB recalc, badge evaluation, or backup job fails, Row Tracker also emails whatever address `NOTIFY_EMAIL` (or `MAIL_USERNAME`) points to — the same address badge and milestone notifications use — so a broken sync doesn't go unnoticed.

**My latest workout isn't showing — what should I do?**
First, make sure your workout has synced to the Concept2 Online Logbook via ErgData. Then click the Sync button on the Dashboard. If it still doesn't appear, wait a few minutes and try again — occasionally the Concept2 API has a short delay.

**Can I import workouts from a CSV or other file?**
Yes — for seasons your Concept2 account didn't have API access for yet, export a season CSV from the Concept2 Online Logbook and upload it on the Import CSV page (linked from the Dashboard). Already-synced workouts are skipped automatically.

**Will my historical workouts appear?**
Yes. The first time Row Tracker syncs, it backfills your full workout history from the Concept2 Logbook.

**Is my data backed up?**
Yes — every night at 3:30 AM (right after sync, PB recalculation, and badge evaluation), Row Tracker copies the database to `data/backups/`, keeping the last 30 days. It's still worth copying that folder to another disk or machine occasionally in case the whole server goes down.

**Can I export my data?**
Yes — click **Export Data** next to the Sync button on the Dashboard. You can download your full workout history or personal bests as CSV (for spreadsheets) or JSON (for other tools), separately from the automatic nightly backup.

**My lifetime metres don't match the Concept2 website — why?**
If you do interval workouts, Concept2 tracks the light rowing between intervals as separate "rest" meters, apart from each interval's own distance. Row Tracker includes those rest meters in lifetime and volume totals (the Dashboard total, volume badges, virtual journeys, and Season Challenges) — matching what Concept2's own site counts — but never in pace, personal bests, or single-piece test results, which stay based on work-interval meters only so a slower recovery split can't inflate your times. A small remaining gap usually means a manually-entered starting/legacy total on your Concept2 profile that predates connected-device logging, since that number isn't exposed by Concept2's results API at all.

---

### Personal Bests

**How are personal bests calculated?**
PBs are recalculated automatically after every sync across 8 categories: 100m, 500m, 1000m, 2000m, 5000m, 10000m, 30 minutes, and 60 minutes. The app scans your full workout history each time.

**What does the "stale PB" warning mean?**
If a personal best hasn't been improved in 90 or more days, Row Tracker flags it as stale and shows a nudge on the Achievements hub. It's a reminder to test that category again.

---

### Workout of the Day

**How is the daily WOD generated?**
The WOD engine looks at your last 28 days of training to determine your current phase (base, build, peak, or recovery) and generates a workout appropriate for that phase. Pace targets are based on your 2k personal best.

**Can I get a different WOD if I don't like today's?**
Yes — click Force Regenerate on the WOD page to get a new one. You can also browse the full WOD library and assign any workout manually.

**What is the Random WOD Generator?**
It lets you generate a one-off workout by specifying intensity (light / medium / heavy), effort level (low / medium / high), and type (steady state / intervals / threshold / surprise me). You can also add optional notes like "tired legs today."

**What does the WOD History calendar show?**
Click View all under History on the WOD page to open a month-by-month calendar of every day a WOD was generated. Days are colour-coded for pending vs. completed, and clicking any day opens its workout title, target pace, zone, and status. Use Prev/Next to browse other months, including previous years.

**Can Claude write my coaching notes?**
Optionally. Set `USE_AI_WOD=true` and add an `ANTHROPIC_API_KEY` in your `.env` and Claude Haiku will write the warm-up, cool-down, and coaching notes for each WOD, tailored to your recent training load, effort request, or any notes you type into the Random WOD Generator. The workout structure itself (intervals, pace targets) is always rule-based and unaffected. If the API key isn't set, or the request fails for any reason, Row Tracker silently falls back to the built-in static coaching text — this feature is off by default and never blocks WOD generation.

---

### Insights

**What is the Insights page?**
It reads your whole workout history and surfaces patterns in plain language — things like which day you tend to row fastest, whether a rest day sharpens your next session, how your pace is trending, which stroke rate your steady pieces fly at, and how this year compares to last. It also closes with a Milestones section of all-time highlights (years rowing, biggest single day, total hours on the erg, total workouts logged, total calories burned, longest streak). Each card may carry a suggested next step.

**Why don't I see many insights yet?**
Every insight has to clear a minimum-sample and significance check before it appears — a pattern won't show up on three data points. Cards are tagged **Strong pattern** or **Early signal** so you can tell how much weight to give each one. As you log more sessions, more cards unlock.

**Are the insights AI-generated?**
No — the cards are computed entirely on your own server by a rule-based engine, and work fully offline. There's an *optional* extra: set `USE_AI_INSIGHTS=true` with an `ANTHROPIC_API_KEY` and Claude Haiku adds a short first-person "coach's read" at the top that ties the cards together. It only ever rephrases the numbers the engine already computed — it never invents a figure — and everything works the same without it.

---

### Achievements & Badges

**How do I earn badges?**
Badges are awarded automatically after each sync when the conditions are met. There are 17 badges across four categories: Performance, Volume, Consistency, and Efficiency. Once earned, a badge is yours permanently.

**Why hasn't my badge been awarded yet?**
Badge evaluation runs after each sync. Try triggering a manual sync from the Dashboard. If the conditions have been met and the badge still hasn't appeared, use the Feedback button to let us know.

**Why do some locked badges show a progress bar and others just say "Locked"?**
Badges with a single clear numeric target (lifetime metres, best single-session distance, streak length, or best 7-day workout count) show a progress bar toward that target. Badges based on a one-off condition (like a specific pace threshold or a PB improvement) don't reduce to a meaningful percentage, so they stay a plain "Locked" until earned.

**What are Season Challenges?**
Quarterly targets that reset on January 1, April 1, July 1, and October 1. They include a distance target, a PB season checklist, a consistency challenge, and a monthly volume goal.

**Will I get notified when I earn a badge, hit a milestone, or finish a journey?**
Yes — Row Tracker emails you automatically after every sync that earns a new badge, crosses a lifetime-metres milestone (100k, 250k, 500k, 1M, and so on), or completes a virtual journey. It reuses the same Flask-Mail setup as the feedback form, but sends to `NOTIFY_EMAIL` in your `.env` (defaults to `MAIL_USERNAME` — your own inbox — if left blank) rather than the feedback address.

---

### Virtual Journeys

**What are the virtual journeys?**
Four independent routes you can row your way along using real workout metres:
- **Rhine River** — Basel to Rotterdam, 820 km, 14 waypoints
- **Holland Tour** — Amsterdam scenic loop, 550 km, 17 waypoints
- **Trans-Canada Highway** — Victoria BC to St. John's NL, 7,821 km, 23 waypoints
- **Route 66** — Chicago, IL to Santa Monica, CA, 3,940 km

**How do I start a journey?**
Go to Journeys in the navigation and click Start on any route. Metres from workouts completed after that date count toward your progress. Multiple journeys can run at the same time.

**Do journey metres count from my full history?**
No — only workouts completed after you clicked Start count. This is intentional so the journey feels like a real ongoing trip.

**Can I get more info about a waypoint?**
Yes — click any waypoint, on the map itself or in the list below it, to open a popup with its name, distance mark, and whether you've passed it, plus a link to look it up on Wikipedia.

**What's the "Journey Map" card on the dashboard?**
A small decorative map preview showing whichever active journey you're furthest along on (by percent complete). It's purely a visual teaser — not to scale, no real geography — and links through to that journey's full route page. It only appears once at least one journey is active.

---

### Feedback

**How do I report a bug or suggest a feature?**
Click the 💬 Feedback button in the navigation bar on any page. Fill in the category, an optional name, and your message. It goes directly to the Row Tracker team.

---

## Known Issues

| # | Area | Issue | Status |
|---|---|---|---|
| 1 | Multi-user | Row Tracker is single-user only in this release | Out of scope for alpha |
| 2 | Social / sharing | There are no sharing features — the app is for personal use only | Out of scope for alpha |

---

*Last updated: August 7, 2026*
*To report an issue not listed here, use the 💬 Feedback button in the app.*
