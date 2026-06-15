# Row Tracker — FAQ & Known Issues

*Alpha release · June 2026*

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
Row Tracker is browser-based and works best on a desktop or laptop browser. Mobile and iPad layouts are not yet optimised — see Known Issues below.

---

### Data & Sync

**How often does my data sync?**
Automatically every night at 3:00 AM Toronto time. You can also click the Sync button on the Dashboard at any time to pull in your latest workouts immediately.

**My latest workout isn't showing — what should I do?**
First, make sure your workout has synced to the Concept2 Online Logbook via ErgData. Then click the Sync button on the Dashboard. If it still doesn't appear, wait a few minutes and try again — occasionally the Concept2 API has a short delay.

**Can I import workouts from a CSV or other file?**
Not currently. Row Tracker only pulls data via the Concept2 Logbook API.

**Will my historical workouts appear?**
Yes. The first time Row Tracker syncs, it backfills your full workout history from the Concept2 Logbook.

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

---

### Achievements & Badges

**How do I earn badges?**
Badges are awarded automatically after each sync when the conditions are met. There are 16 badges across four categories: Performance, Volume, Consistency, and Efficiency. Once earned, a badge is yours permanently.

**Why hasn't my badge been awarded yet?**
Badge evaluation runs after each sync. Try triggering a manual sync from the Dashboard. If the conditions have been met and the badge still hasn't appeared, use the Feedback button to let us know.

**What are Season Challenges?**
Quarterly targets that reset on January 1, April 1, July 1, and October 1. They include a distance target, a PB season checklist, a consistency challenge, and a monthly volume goal.

---

### Virtual Journeys

**What are the virtual journeys?**
Three independent routes you can row your way along using real workout metres:
- **Rhine River** — Basel to Rotterdam, 820 km, 14 waypoints
- **Holland Tour** — Amsterdam scenic loop, 550 km, 17 waypoints
- **Trans-Canada Highway** — Victoria BC to St. John's NL, 7,821 km, 23 waypoints

**How do I start a journey?**
Go to Journeys in the navigation and click Start on any route. Metres from workouts completed after that date count toward your progress. Multiple journeys can run at the same time.

**Do journey metres count from my full history?**
No — only workouts completed after you clicked Start count. This is intentional so the journey feels like a real ongoing trip.

---

### Feedback

**How do I report a bug or suggest a feature?**
Click the 💬 Feedback button in the navigation bar on any page. Fill in the category, an optional name, and your message. It goes directly to the Row Tracker team.

---

## Known Issues

| # | Area | Issue | Status |
|---|---|---|---|
| 1 | Charts | All three charts are functional but visual quality needs improvement — axis labels, tooltips, and colour consistency are being worked on | In progress |
| 2 | Mobile / iPad | No responsive CSS — the app is not optimised for small screens or touch interfaces | Planned |
| 3 | Heart rate | Heart rate data is captured from your Concept2 workouts and stored, but is not yet displayed anywhere in the app | Planned |
| 4 | Stroke data | Per-stroke data is stored per workout but no visualisation has been built yet | Planned |
| 5 | Iron Month badge | The Iron Month badge (20+ workouts in a calendar month) uses a session count proxy. Planned session tracking has not been built yet | Known limitation |
| 6 | AI-assisted WOD | The AI coaching mode for the WOD generator has been deferred and is not available in this alpha | Deferred |
| 7 | Notifications | There are no push or email notifications for badges, milestones, or journey completions | Planned |
| 8 | Multi-user | Row Tracker is single-user only in this release | Out of scope for alpha |
| 9 | Social / sharing | There are no sharing features — the app is for personal use only | Out of scope for alpha |

---

*Last updated: June 14, 2026*
*To report an issue not listed here, use the 💬 Feedback button in the app.*
