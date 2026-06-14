"""
Build 2A — Workout of the Day Blueprint.
Rule-based WOD engine. AI-assisted mode is Build 2B (feature-flagged).
"""

from datetime import date, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from models import db, Workout, WodHistory
from wod_engine import WOD_LIBRARY, generate_wod, generate_random_wod, get_or_create_today, save_wod

wod_bp = Blueprint("wod", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _enrich(row: WodHistory) -> dict:
    """Merge WodHistory row with its wod_json into a flat display dict."""
    j = row.wod_json or {}
    return {
        "id":            row.id,
        "date":          row.generated_date,
        "completed":     row.completed,
        "wod_type":      row.wod_type,
        "title":         j.get("title", "—"),
        "structure_key": j.get("structure_key", ""),
        "intervals":     j.get("intervals", []),
        "pace_zone":     j.get("pace_zone", ""),
        "target_pace_str": j.get("target_pace_str", "—"),
        "warm_up":       j.get("warm_up", ""),
        "cool_down":     j.get("cool_down", ""),
        "coaching_notes": j.get("coaching_notes", ""),
        "total_work_meters":  j.get("total_work_meters", 0),
        "total_work_seconds": j.get("total_work_seconds", 0),
        "actual_workout": row.actual_workout,
    }


def _fmt_duration(seconds: int) -> str:
    if not seconds:
        return ""
    m, s = divmod(seconds, 60)
    if s:
        return f"{m}:{s:02d} min"
    return f"{m} min"


# ── Routes ─────────────────────────────────────────────────────────────────

@wod_bp.route("/wod")
def wod():
    """Today's WOD — shows periodization WOD and random generator tabs."""
    row, created = get_or_create_today()
    wod_data = _enrich(row)
    active_tab = request.args.get("tab", "today")
    return render_template("wod/index.html", wod=wod_data, wod_id=row.id, active_tab=active_tab)


@wod_bp.route("/wod/random", methods=["POST"])
def wod_random():
    """Generate and save a random WOD from user parameters."""
    intensity = request.form.get("intensity", "medium")
    effort    = request.form.get("effort", "medium")
    wod_type  = request.form.get("wod_type", "surprise")
    notes     = request.form.get("notes", "").strip()

    try:
        spec = generate_random_wod(
            intensity=intensity,
            effort=effort,
            wod_type=wod_type,
            notes=notes,
        )
        row = save_wod(spec)
        return redirect(url_for("wod.wod_random_result", wod_id=row.id))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Random WOD generation failed: {e}")
        return redirect(url_for("wod.wod") + "?tab=random")


@wod_bp.route("/wod/random/<int:wod_id>")
def wod_random_result(wod_id):
    """Display a generated random WOD."""
    row = db.get_or_404(WodHistory, wod_id)
    wod_data = _enrich(row)
    return render_template("wod/random_result.html", wod=wod_data, wod_id=row.id)


@wod_bp.route("/wod/generate", methods=["POST"])
def wod_generate():
    """Force-regenerate today's WOD (new random selection of same periodization type)."""
    force_type = request.form.get("force_type")  # optional override from library page
    spec = generate_wod(force_type=force_type or None)
    save_wod(spec)
    return redirect(url_for("wod.wod"))


@wod_bp.route("/wod/complete", methods=["POST"])
def wod_complete():
    """Mark a WOD as completed, optionally linking to an actual synced workout."""
    wod_id = request.form.get("wod_id", type=int)
    workout_id = request.form.get("workout_id", type=int)

    row = db.get_or_404(WodHistory, wod_id)
    row.completed = True
    if workout_id:
        workout = Workout.query.get(workout_id)
        if workout:
            row.actual_workout_id = workout_id
    db.session.commit()
    return redirect(url_for("wod.wod"))


@wod_bp.route("/wod/history")
def wod_history():
    """Past WODs with completion status — most recent first."""
    page = request.args.get("page", 1, type=int)
    rows = (
        WodHistory.query
        .order_by(WodHistory.generated_date.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )
    history = [_enrich(r) for r in rows.items]
    return render_template("wod/history.html", history=history, pagination=rows)


@wod_bp.route("/wod/library")
def wod_library():
    """Browse the full WOD type library."""
    # Group library entries by wod_type for display
    grouped: dict[str, list] = {}
    type_order = ["interval", "steady_state", "threshold", "long", "test"]
    type_labels = {
        "interval":    "Intervals",
        "steady_state": "Steady State",
        "threshold":   "Threshold",
        "long":        "Long Rows",
        "test":        "Time Trials",
    }
    for key, defn in WOD_LIBRARY.items():
        t = defn["wod_type"]
        grouped.setdefault(t, []).append({
            "key":     key,
            "title":   defn["title"],
            "zone":    defn["pace_zone"],
            "coaching": defn["coaching"],
        })

    sections = [
        {"type": t, "label": type_labels[t], "wods": grouped.get(t, [])}
        for t in type_order
        if t in grouped
    ]
    return render_template("wod/library.html", sections=sections)


@wod_bp.route("/api/wod/today")
def api_wod_today():
    """JSON — today's WOD for dashboard widget use."""
    row, _ = get_or_create_today()
    j = row.wod_json or {}
    return jsonify({
        "id":              row.id,
        "date":            row.generated_date.isoformat(),
        "wod_type":        row.wod_type,
        "title":           j.get("title"),
        "target_pace_str": j.get("target_pace_str"),
        "pace_zone":       j.get("pace_zone"),
        "completed":       row.completed,
    })
