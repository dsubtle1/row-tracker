# Row Tracker — Quick Start Guide

*Alpha release · June 2026*

---

You've completed the installation and Row Tracker is running at `http://localhost:7376`. This guide walks you through everything to do next.

---

## Step 1 — Sync Your Workouts

On the Dashboard, click the **Sync Workouts** button.

Row Tracker will connect to your Concept2 Logbook and pull in your full workout history. Depending on how many workouts you have, this may take up to a minute. You'll see a message when it's done showing how many workouts were imported.

> After the first sync, Row Tracker syncs automatically every night at 3:00 AM. You can always click Sync manually to pull in your latest session straight away.

If you have older seasons your Concept2 account didn't have API access for, click **Import CSV** next to the Sync button to upload a season export from the Concept2 Online Logbook instead. Already-synced workouts are skipped automatically.

---

## Step 2 — Explore the Dashboard

Once synced, your Dashboard shows:

- **Lifetime metres** — your total rowing distance with a circular gauge toward the next milestone
- **Current streak** — consecutive days with at least one workout
- **This week / this month** — workout counts for the current periods
- **Last session** — distance, pace, and date of your most recent row
- **Pace trend & weekly volume** — mini sparkline previews of your recent training
- **Your Progress** — a checklist of every active or completed virtual journey
- **Journey Map** — a small map preview of whichever active journey you're furthest along on, with a link to its full route page
- **52-week heatmap** — a full year of training volume at a glance; click any square to see that day's individual workouts

---

## Step 3 — Check Your Personal Bests

Click **PBs** in the navigation bar.

Row Tracker automatically calculates your best times and distances across 8 standard categories:

- Distance pieces: 100m, 500m, 1,000m, 2,000m, 5,000m, 10,000m
- Time pieces: 30 minutes, 60 minutes

PBs are recalculated after every sync. If a PB is more than 90 days old, you'll see a nudge to go test it again.

---

## Step 4 — Look at Your Charts

Click **Charts** in the navigation bar to explore three views:

- **Pace Trend** — your 500m pace over time with a 10-session rolling average
- **Efficiency** — pace vs. stroke rate to see how your technique is evolving
- **Training Load** — your acute vs. chronic workload ratio (CAWR) to track training stress over time

---

## Step 5 — Get Today's Workout

Click **WOD** in the navigation bar.

Row Tracker generates a daily Workout of the Day based on your recent training. Pace targets are set automatically from your 2k personal best.

If today's WOD doesn't suit you, you can:
- Click **Force Regenerate** for a new one
- Browse the **WOD Library** and assign any workout manually
- Use the **Random WOD Generator** to build your own by choosing intensity, effort level, and type

Click **View all →** under History to open the WOD calendar — a month-by-month grid of every past WOD, colour-coded for pending vs. completed. Click any day to see its workout detail, or use Prev/Next to browse other months.

---

## Step 6 — Start a Journey

Click **Journeys** in the navigation bar.

Pick one of four virtual routes and click **Start**. Every metre you row from that point counts toward your progress along the route:

- 🇨🇭 **Rhine River** — Basel to Rotterdam, 820 km, 14 waypoints
- 🇳🇱 **Holland Tour** — Amsterdam scenic loop, 550 km, 17 waypoints
- 🇨🇦 **Trans-Canada Highway** — Victoria BC to St. John's NL, 7,821 km, 23 waypoints
- 🇺🇸 **Route 66** — Chicago, IL to Santa Monica, CA, 3,940 km

You can run all four simultaneously. Each shows your current position, upcoming waypoints, and an estimated arrival date based on your recent training pace. Click any waypoint — on the map or in the list — for a popup with more detail and a link to look it up on Wikipedia.

---

## Step 7 — Check Your Achievements

Click **Achievements** in the navigation bar to see:

- **Badges** — 17 badges across Performance, Volume, Consistency, and Efficiency categories, awarded automatically as you hit milestones
- **Season Challenges** — quarterly targets including distance goals, PB attempts, and consistency streaks
- **You vs. Past You** — a side-by-side comparison of your training across this month, last month, 3 months ago, and 12 months ago

---

## A Few Tips

- **Dark/light mode** — use the ☀️ toggle in the top-right corner to switch themes
- **Install as an app** — on iPhone/iPad, tap Share → Add to Home Screen in Safari for a full-screen, icon-launched app. On Android/Chrome, use the browser's Install app option (needs HTTPS to appear — see the FAQ)
- **Heatmap drill-down** — click any square in the 52-week heatmap to see that day's individual workouts in detail
- **Keeping your app running** — if you want Row Tracker to run in the background without keeping a terminal window open, use `docker compose up -d` instead of `docker compose up`. See the Installation Guide for details.
- **Your data** — all workout data is stored in `row-tracker/data/row_tracker.db`. It's backed up automatically every night to `row-tracker/data/backups/`, keeping the last 30 days — worth copying that folder somewhere off the server occasionally too. Want just your workouts or PBs as a CSV or JSON file? Use **Export Data** next to the Sync button on the Dashboard.

---

## Sending Feedback

This is an alpha release and your input matters. Click the **💬 Feedback** button in the navigation bar on any page to report a bug, suggest a feature, or ask a question.

For a list of known issues and common questions, click **FAQ** in the navigation bar.

---

*Last updated: August 6, 2026*
