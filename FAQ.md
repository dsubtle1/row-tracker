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
The Dashboard shows a "Last synced" indicator next to the Sync button, so you don't have to take it on faith. If a nightly sync, PB recalc, badge evaluation, or backup job fails, Row Tracker also sends a notification through whichever channels you've configured (email, ntfy, Discord, webhook — see the notifications question above), so a broken sync doesn't go unnoticed.

**My latest workout isn't showing — what should I do?**
First, make sure your workout has synced to the Concept2 Online Logbook via ErgData. Then click the Sync button on the Dashboard. If it still doesn't appear, wait a few minutes and try again — occasionally the Concept2 API has a short delay.

**I also own a SkiErg or BikeErg — will those show up?**
No — Row Tracker only pulls RowErg results by design; SkiErg/BikeErg support isn't currently on the roadmap. If your Concept2 account has non-rower results logged, sync now checks for that and logs a warning (visible via `docker logs`) rather than silently dropping them with no trace, so it's diagnosable if it ever matters to you.

**Can I import workouts from a CSV or other file?**
Yes — for seasons your Concept2 account didn't have API access for yet, export a season CSV from the Concept2 Online Logbook and upload it on the Import CSV page (linked from the Dashboard). Already-synced workouts are skipped automatically.

**Will my historical workouts appear?**
Yes. The first time Row Tracker syncs, it backfills your full workout history from the Concept2 Logbook.

**Is my data backed up?**
Yes — every night at 3:30 AM (right after sync, PB recalculation, and badge evaluation), Row Tracker copies the database to `data/backups/`, keeping the last 30 days. It's still worth copying that folder to another disk or machine occasionally in case the whole server goes down.

**Can I restore from a backup myself?**
Yes — the Export Data page lists every backup with a Restore button next to it. Restoring requires typing RESTORE into a confirmation dialog first, since it's destructive: it replaces all current data with the chosen snapshot. Your current data is automatically saved as its own timestamped safety copy right before the swap, so a restore is itself undoable — just restore that safety copy if you change your mind. No SSH or terminal access needed.

**Can I export my data?**
Yes — click **Export Data** next to the Sync button on the Dashboard. You can download your full workout history or personal bests as CSV (for spreadsheets) or JSON (for other tools), separately from the automatic nightly backup.

**Can I filter or search my workout list?**
Yes — the Workouts page has a filter bar for date range and distance range (e.g. every 10k+ session in a given month). Filters combine, carry across pages, and can be bookmarked or shared since they're plain URL parameters — clear them with the Clear button or by revisiting the page with no filters.

**Can I add a note to a workout?**
Yes — every workout detail page has a Notes field near the top. Free text, up to 2,000 characters, saved with its own button. Good for things Concept2 doesn't track: how you felt, equipment changes, why a session got cut short.

**My lifetime metres don't match the Concept2 website — why?**
If you do interval workouts, Concept2 tracks the light rowing between intervals as separate "rest" meters, apart from each interval's own distance. Row Tracker includes those rest meters in lifetime and volume totals (the Dashboard total, volume badges, virtual journeys, and Season Challenges) — matching what Concept2's own site counts — but never in pace, personal bests, or single-piece test results, which stay based on work-interval meters only so a slower recovery split can't inflate your times. A small remaining gap usually means a manually-entered starting/legacy total on your Concept2 profile that predates connected-device logging, since that number isn't exposed by Concept2's results API at all.

---

### Personal Bests

**How are personal bests calculated?**
PBs are recalculated automatically after every sync across 8 categories: 100m, 500m, 1000m, 2000m, 5000m, 10000m, 30 minutes, and 60 minutes. The app scans your full workout history each time.

**What does the "stale PB" warning mean?**
If a personal best hasn't been improved in 90 or more days, Row Tracker flags it as stale and shows a nudge on the Achievements hub. It's a reminder to test that category again.

**Can I see how a PB improved over time, not just the current best?**
Yes — click **View progression** on any PB card to open a chart of every genuine record-breaking result in that category, in order, not just the current-vs-previous comparison shown on the card itself. Categories with fewer than two recorded improvements show a "not enough data yet" message instead of an empty chart.

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

**Why does my WOD sometimes say "training load elevated" or "training load is low"?**
The engine tracks your CAWR (acute:chronic workload ratio — your last 7 days of volume vs. your last 42 days) and quietly uses it to steer today's session: a high ratio forces an easy steady-state day so you can recover, a low ratio biases toward interval or threshold work to rebuild fitness. The note on the WOD card just makes that visible — same logic as always, it used to happen with no explanation. It only appears once you have 42+ days of workout history for the ratio to be computed.

**Can Claude write my coaching notes?**
Optionally. Set `USE_AI_WOD=true` and add an `ANTHROPIC_API_KEY` in your `.env` and Claude Haiku will write the warm-up, cool-down, and coaching notes for each WOD, tailored to your recent training load, effort request, or any notes you type into the Random WOD Generator. The workout structure itself (intervals, pace targets) is always rule-based and unaffected. If the API key isn't set, or the request fails for any reason, Row Tracker silently falls back to the built-in static coaching text — this feature is off by default and never blocks WOD generation.

---

### Insights

**What is the Insights page?**
It reads your whole workout history and surfaces patterns in plain language — things like which day you tend to row fastest, whether a rest day sharpens your next session, how your pace is trending, which stroke rate your steady pieces fly at, and how this year compares to last. It also closes with a Milestones section of all-time highlights (years rowing, biggest single day, total hours on the erg, total workouts logged, total calories burned, total strokes taken, peak heart rate, longest streak). Each card may carry a suggested next step.

**Why don't I see many insights yet?**
Every insight has to clear a minimum-sample and significance check before it appears — a pattern won't show up on three data points. Cards are tagged **Strong pattern** or **Early signal** so you can tell how much weight to give each one. If you're under 60 logged workouts, a banner at the top shows your progress toward that floor.

**Why does a section say "Checked — no pattern found" instead of just being empty?**
A couple of checks (day-of-week, rest-day effect) can fail for two different reasons, and the page is honest about which one happened: either there isn't enough data yet, or there's enough data and the pattern simply isn't there for you right now — your pace genuinely doesn't vary by weekday, say. The second case gets a plain "checked, nothing found" note instead of a countdown, since more workouts logged won't necessarily change that outcome. It's not a bug or a bare page — it's the engine telling you it looked and found nothing to report.

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

**What's the ETA shown on some locked badges?**
The four lifetime-metres badges (First 100k, Quarter Million, Half Million, One Million) project a rough unlock date from your rolling 28-day average pace — the same calculation the virtual journeys use for their waypoint ETAs. It disappears if your recent pace is flat (no data to project from) and updates as your pace changes, so treat it as a rough "at this rate" estimate, not a promise.

**What are Season Challenges?**
Quarterly targets that reset on January 1, April 1, July 1, and October 1. They include a distance target, a PB season checklist, a consistency challenge, and a monthly volume goal.

**Will I get notified when I earn a badge, hit a milestone, or finish a journey?**
Yes — Row Tracker notifies you automatically after every sync that earns a new badge, crosses a lifetime-metres milestone (100k, 250k, 500k, 1M, and so on), or completes a virtual journey. By default that's email: it reuses the same Flask-Mail setup as the feedback form, but sends to `NOTIFY_EMAIL` in your `.env` (defaults to `MAIL_USERNAME` — your own inbox — if left blank) rather than the feedback address.

**Can I get notifications somewhere other than email?**
Yes — set any of `NOTIFY_NTFY_TOPIC`, `NOTIFY_DISCORD_WEBHOOK_URL`, or `NOTIFY_WEBHOOK_URL` in your `.env` and Row Tracker sends the same notifications there too (ntfy.sh, a Discord channel, or any endpoint that accepts a JSON POST). All four channels are independent — enable any combination, including none of them plus email, or drop email entirely by leaving `NOTIFY_EMAIL`/`MAIL_USERNAME` blank. Each channel fails independently, so a broken webhook never blocks the others. There's no in-app settings page for this — it's `.env`-only, like the Concept2 and mail integrations.

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
