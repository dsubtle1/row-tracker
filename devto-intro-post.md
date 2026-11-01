# Draft: dev.to post

**Suggested tags:** `selfhosted`, `python`, `flask`, `docker`

**Suggested cover image:** Dashboard or Insights screenshot.

---

## Title: I vibe-coded a self-hosted tracker for my rowing machine, then learned the hard way what "safe to make public" actually means

I row on a Concept2 RowErg most mornings, and the Concept2 Logbook logs a workout fine but doesn't really *do* anything with the data — no trends, no sense of whether today should be a hard day or an easy one. So over a couple months I built [Row Tracker](https://github.com/dsubtle1/row-tracker) with a lot of AI help. I'm not a professional developer — this is my first real "vibe coded" project — so a good chunk of this build was me learning what things like Docker, SQLite, and CSRF tokens even are while asking Claude to build them.

It syncs from the Concept2 Logbook API, tracks personal bests, spits out a daily workout based on your training load, and has an "Insights" page that tries to spot patterns in your history.

### The one thing I made sure I understood: keep the AI part honest

Even not fully understanding the codebase, I cared a lot about one thing: the Insights page shouldn't just be an LLM making stuff up about my training. So it's a rule-based engine — plain code, no AI — that only shows a pattern once there's actually enough data to back it up. There's an *optional* AI layer on top (your own API key, off by default) that just rephrases numbers the rule-based part already calculated. It's not allowed to invent a number. Even as someone still learning how all the pieces fit together, that felt like a line worth holding.

### Then I tried to make it "safe to share" and found out I had no idea what that meant

Before making the repo public I asked for a proper security pass instead of just assuming two months of AI-assisted vibes were fine. They were not, and honestly most of this was new to me:

- A **Gmail app password had been sitting in `.env.example`** for weeks. I didn't know that deleting a secret from a file doesn't remove it from git history — had to learn what rewriting git history even means, then force-push the fix.
- **My actual `.env` file was getting copied straight into the Docker image** because nothing told Docker not to. I didn't know `.dockerignore` was a thing I needed until it wasn't there.
- A scan turned up **known CVEs sitting in the base Docker image** that had just never been patched, because I didn't know that was something you had to think about.
- I'd grabbed a copy of Chart.js off the internet at some point with **no version tracked anywhere**. Now it loads from a CDN with an integrity hash, so if the file it serves ever doesn't match, it just won't run instead of silently running whatever it got.

None of this was stuff I knew to ask for upfront — it only surfaced because I asked for a real audit instead of assuming "it runs" meant "it's fine."

### Stack, for what it's worth

Flask + SQLAlchemy + SQLite, one Docker container, no telemetry, no backend of mine involved anywhere — it talks to *your own* Concept2 account with *your own* credentials.

Still rough, still very much a learning project, but it's been my actual daily-use app for two months now. Repo's here if you want to poke at it: **https://github.com/dsubtle1/row-tracker** — genuinely curious what more experienced self-hosters would flag that I haven't thought to ask about yet.
