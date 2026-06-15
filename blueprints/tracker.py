"""
Build 1B + 1C — Row Tracker Blueprint
Dashboard, PB board, pace trend, efficiency scatter, CAWR load chart.
"""

from datetime import date, timedelta
from collections import defaultdict

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func

from models import db, Workout, PersonalBest

tracker_bp = Blueprint("tracker", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def _rower():
    return Workout.query.filter_by(workout_type="rower")


def _compute_streak():
    rows = (
        db.session.query(Workout.workout_date)
        .filter_by(workout_type="rower")
        .distinct()
        .order_by(Workout.workout_date.desc())
        .all()
    )
    if not rows:
        return 0
    dates = sorted({r.workout_date for r in rows}, reverse=True)
    today = date.today()
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def _workouts_this_week():
    monday = date.today() - timedelta(days=date.today().weekday())
    return _rower().filter(Workout.workout_date >= monday).count()


def _workouts_this_month():
    today = date.today()
    return _rower().filter(Workout.workout_date >= today.replace(day=1)).count()


def _lifetime_meters():
    result = db.session.query(func.sum(Workout.distance_meters)).filter_by(workout_type="rower").scalar()
    return result or 0


def _nearest_milestone(meters):
    for m, label in [
        (100_000, "100k"), (250_000, "250k"), (500_000, "500k"),
        (1_000_000, "1M"), (2_000_000, "2M"), (5_000_000, "5M"),
    ]:
        if meters < m:
            return m, label
    return None, None


def _heatmap_data(weeks=52):
    today = date.today()
    start = today - timedelta(weeks=weeks)
    rows = (
        db.session.query(Workout.workout_date, func.sum(Workout.distance_meters))
        .filter_by(workout_type="rower")
        .filter(Workout.workout_date >= start)
        .group_by(Workout.workout_date)
        .all()
    )
    by_date = {r[0]: r[1] for r in rows}
    values = [v for v in by_date.values() if v]
    if values:
        mx = max(values)
        thresholds = [mx * 0.25, mx * 0.5, mx * 0.75, mx]
    else:
        thresholds = [5000, 10000, 15000, 20000]

    def level(m):
        if not m:
            return 0
        for i, t in enumerate(thresholds, 1):
            if m <= t:
                return i
        return 4

    days, d = [], start
    while d <= today:
        m = by_date.get(d, 0)
        days.append({"date": d.isoformat(), "meters": m or 0, "level": level(m), "dow": d.weekday()})
        d += timedelta(days=1)
    return days


def _pace_series(days=365):
    q = _rower().filter(Workout.avg_pace_seconds.isnot(None))
    if days:
        q = q.filter(Workout.workout_date >= date.today() - timedelta(days=days))
    workouts = q.order_by(Workout.workout_date.asc()).all()
    result = []
    for w in workouts:
        m, s = divmod(w.avg_pace_seconds, 60)
        result.append({
            "date":            w.workout_date.isoformat(),
            "pace_seconds":    w.avg_pace_seconds,
            "pace_str":        f"{m}:{s:02d}",
            "distance_meters": w.distance_meters,
            "distance_km":     round((w.distance_meters or 0) / 1000, 1),
        })
    return result


def _rolling_avg_pace(series, window=10):
    out = []
    for i, pt in enumerate(series):
        start = max(0, i - window + 1)
        window_paces = [series[j]["pace_seconds"] for j in range(start, i + 1)]
        avg = sum(window_paces) / len(window_paces)
        out.append({**pt, "rolling_avg_seconds": round(avg, 1)})
    return out


def _efficiency_series(days=365):
    q = (
        _rower()
        .filter(Workout.avg_pace_seconds.isnot(None))
        .filter(Workout.avg_stroke_rate.isnot(None))
    )
    if days:
        q = q.filter(Workout.workout_date >= date.today() - timedelta(days=days))
    workouts = q.order_by(Workout.workout_date.asc()).all()
    result = []
    for w in workouts:
        m, s = divmod(w.avg_pace_seconds, 60)
        result.append({
            "date":         w.workout_date.isoformat(),
            "pace_seconds": w.avg_pace_seconds,
            "pace_str":     f"{m}:{s:02d}",
            "stroke_rate":  w.avg_stroke_rate,
            "distance_km":  round((w.distance_meters or 0) / 1000, 1),
        })
    return result


def _cawr_series():
    rows = (
        db.session.query(Workout.workout_date, func.sum(Workout.distance_meters))
        .filter_by(workout_type="rower")
        .group_by(Workout.workout_date)
        .order_by(Workout.workout_date.asc())
        .all()
    )
    if not rows:
        return []

    by_date  = {r[0]: r[1] for r in rows}
    first_day = min(by_date.keys())
    last_day  = date.today()

    all_days, d = [], first_day
    while d <= last_day:
        all_days.append((d, by_date.get(d, 0)))
        d += timedelta(days=1)

    CHRONIC = 42
    ACUTE   = 7
    cutoff  = last_day - timedelta(days=730)
    result  = []

    for i, (day, _) in enumerate(all_days):
        if i < CHRONIC - 1:
            continue
        acute_window   = [m for _, m in all_days[max(0, i - ACUTE + 1):i + 1]]
        chronic_window = [m for _, m in all_days[i - CHRONIC + 1:i + 1]]
        acute_avg      = sum(acute_window)   / len(acute_window)
        chronic_avg    = sum(chronic_window) / len(chronic_window)
        cawr = round(acute_avg / chronic_avg, 3) if chronic_avg else None
        if day < cutoff:
            continue
        result.append({
            "date":        day.isoformat(),
            "acute_avg":   round(acute_avg),
            "chronic_avg": round(chronic_avg),
            "cawr":        cawr,
        })

    return result


# ── Routes ─────────────────────────────────────────────────────────────────

@tracker_bp.route("/")
def dashboard():
    lifetime_m = _lifetime_meters()
    next_milestone, next_label = _nearest_milestone(lifetime_m)
    milestone_pct = round((lifetime_m / next_milestone) * 100, 1) if next_milestone else None
    last = _rower().order_by(Workout.workout_date.desc()).first()
    summary = {
        "lifetime_meters":     lifetime_m,
        "lifetime_km":         round(lifetime_m / 1000, 1),
        "workouts_week":       _workouts_this_week(),
        "workouts_month":      _workouts_this_month(),
        "streak":              _compute_streak(),
        "next_milestone":      next_milestone,
        "next_label":          next_label,
        "milestone_pct":       milestone_pct,
        "meters_to_milestone": (next_milestone - lifetime_m) if next_milestone else None,
        "last_workout":        last,
    }
    return render_template("tracker/dashboard.html", summary=summary, heatmap=_heatmap_data(52))


@tracker_bp.route("/workouts")
def workout_list():
    page = request.args.get("page", 1, type=int)
    workouts = (
        _rower()
        .order_by(Workout.workout_date.desc())
        .paginate(page=page, per_page=50, error_out=False)
    )
    return render_template("tracker/workouts.html", workouts=workouts)


@tracker_bp.route("/workouts/<int:workout_id>")
def workout_detail(workout_id):
    workout = db.get_or_404(Workout, workout_id)
    return render_template("tracker/workout_detail.html", workout=workout)


@tracker_bp.route("/pb")
def personal_bests():
    order   = ["100m", "500m", "1000m", "2000m", "5000m", "10000m", "30min", "60min"]
    pbs_raw = PersonalBest.query.all()
    pb_map  = {pb.category: pb for pb in pbs_raw}
    pbs     = [pb_map[cat] for cat in order if cat in pb_map]
    extras  = [pb for pb in pbs_raw if pb.category not in set(order)]
    pbs.extend(extras)
    return render_template("tracker/pb.html", pbs=pbs)


@tracker_bp.route("/charts/pace")
def chart_pace():
    days = request.args.get("days", 365, type=int)
    return render_template("tracker/chart_pace.html", days=days)


@tracker_bp.route("/charts/efficiency")
def chart_efficiency():
    days = request.args.get("days", 365, type=int)
    return render_template("tracker/chart_efficiency.html", days=days)


@tracker_bp.route("/charts/load")
def chart_load():
    return render_template("tracker/chart_load.html")


# ── JSON API ───────────────────────────────────────────────────────────────

@tracker_bp.route("/api/data/heatmap")
def api_heatmap():
    return jsonify(_heatmap_data(request.args.get("weeks", 52, type=int)))


@tracker_bp.route("/api/data/summary")
def api_summary():
    lifetime_m = _lifetime_meters()
    last = _rower().order_by(Workout.workout_date.desc()).first()
    return jsonify({
        "lifetime_meters": lifetime_m,
        "total_workouts":  _rower().count(),
        "streak":          _compute_streak(),
        "last_workout": {
            "date":     last.workout_date.isoformat() if last else None,
            "distance": last.distance_meters if last else None,
            "pace":     last.avg_pace_formatted if last else None,
        },
    })


@tracker_bp.route("/api/data/pace")
def api_pace():
    days   = request.args.get("days", 365, type=int)
    series = _pace_series(days=days if days else None)
    series = _rolling_avg_pace(series, window=10)
    return jsonify(series)


@tracker_bp.route("/api/data/efficiency")
def api_efficiency():
    days = request.args.get("days", 365, type=int)
    return jsonify(_efficiency_series(days=days if days else None))


@tracker_bp.route("/api/data/load")
def api_load():
    return jsonify(_cawr_series())


@tracker_bp.route("/sync", methods=["POST"])
def sync():
    """Manual sync trigger — calls C2 API and runs post-sync jobs."""
    from flask import current_app
    from c2_api import C2ApiClient
    from pb_engine import recalculate_all_pbs
    from badge_engine import evaluate_badges

    app = current_app._get_current_object()

    client = C2ApiClient(
        client_id     = app.config.get("C2_CLIENT_ID", ""),
        client_secret = app.config.get("C2_CLIENT_SECRET", ""),
        refresh_token = app.config.get("C2_REFRESH_TOKEN", ""),
    )

    if not client.is_configured():
        return jsonify({
            "status":  "error",
            "message": "C2 API credentials not configured. Add C2_CLIENT_ID, C2_CLIENT_SECRET, and C2_REFRESH_TOKEN to .env.",
        }), 400

    # Run sync
    result = client.sync_workouts()

    # Post-sync jobs only if new data arrived
    newly_awarded = []
    if result.get("inserted", 0) > 0:
        try:
            recalculate_all_pbs()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"PB recalc failed: {e}")
        try:
            newly_awarded = evaluate_badges()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Badge eval failed: {e}")

    return jsonify({
        "status":         "ok" if not result.get("errors") else "partial",
        "inserted":       result.get("inserted", 0),
        "skipped":        result.get("skipped", 0),
        "errors":         result.get("errors", 0),
        "message":        result.get("message", ""),
        "badges_awarded": newly_awarded,
    })


@tracker_bp.route("/faq")
def faq():
    return render_template("tracker/faq.html")


@tracker_bp.route("/quickstart")
def quickstart():
    return render_template("tracker/quickstart.html")


@tracker_bp.route("/auth/callback")
def auth_callback():
    """OAuth callback — not needed when using a pre-issued refresh token."""
    return jsonify({"status": "ok", "message": "OAuth callback not required — using pre-issued token."})


@tracker_bp.route("/api/data/workouts_by_date")
def api_workouts_by_date():
    """Return all workouts for a given date. ?date=YYYY-MM-DD"""
    date_str = request.args.get("date", "")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    workouts = (
        _rower()
        .filter(Workout.workout_date == target)
        .order_by(Workout.id.asc())
        .all()
    )

    def fmt_pace(s):
        if not s: return "—"
        m, sec = divmod(s, 60)
        return f"{m}:{sec:02d}"

    def fmt_time(s):
        if not s: return "—"
        s = int(s)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    return jsonify([
        {
            "id":           w.id,
            "distance_m":   w.distance_meters,
            "distance_km":  round((w.distance_meters or 0) / 1000, 2),
            "time_str":     fmt_time(w.time_seconds),
            "pace_str":     fmt_pace(w.avg_pace_seconds),
            "stroke_rate":  w.avg_stroke_rate,
            "calories":     w.total_calories,
        }
        for w in workouts
    ])
