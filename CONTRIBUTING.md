# Contributing to Row Tracker

Thanks for considering it — this is a personal hobby project, but it's public because other Concept2 rowers might find it useful, and because improvements from people who actually use it are welcome.

This is early-stage (alpha), single-maintainer software, so keep expectations calibrated: response times may be slow, and conventions here may still shift. That said, real contributions — bug fixes, small features, doc corrections — are genuinely appreciated.

## Reporting bugs or suggesting features

Open a [GitHub Issue](https://github.com/dsubtle1/row-tracker/issues). Include:
- What you expected vs. what happened
- Steps to reproduce, if it's a bug
- Your setup if relevant (self-hosted, so environment details sometimes matter)

If you're running the app and just want to flag something quickly, the in-app **💬 Feedback** button also reaches the maintainer directly — that one's better for quick notes than for anything you want tracked publicly.

## Proposing a code change

1. Fork the repo and create a branch off `main`.
2. Follow the [Self-Hosting](README.md#self-hosting) steps to get a local dev instance running.
3. Make your change. A few conventions this codebase follows:
   - Engine logic (PB calculation, badges, WOD generation) lives in top-level modules (`pb_engine.py`, `badge_engine.py`, `wod_engine.py`, ...) and is unit-tested directly — Flask routes in `blueprints/` stay thin.
   - No frontend build step — plain Jinja2 templates, vanilla JS, and hand-written CSS in `static/`.
   - If your change affects user-facing behavior, update `README.md`, `FAQ.md`, and/or `QUICKSTART.md` — and their in-app template twins (`templates/tracker/faq.html` + `faq_template.html`, `templates/tracker/quickstart.html` + `quickstart_template.html`, which should stay identical to each other) — as part of the same PR, not a follow-up.
4. Run the test suite before opening a PR:
   ```bash
   docker compose exec row-tracker pip install -r requirements-dev.txt
   docker compose exec row-tracker python -m pytest
   ```
5. Open a PR against `main` with a short description of what changed and why.

## What's especially useful

- Bug fixes with a clear repro
- Fixes for anything in [FAQ.md's Known Issues](FAQ.md#known-issues)
- Small, focused features rather than large speculative ones — easier to review, easier to merge
- Doc corrections, typo fixes, clarity improvements — always welcome, no need to ask first

## License

By contributing, you agree your contribution is licensed under the project's [MIT License](LICENSE.md).
