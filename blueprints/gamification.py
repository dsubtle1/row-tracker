"""
blueprints/gamification.py — Phase 3A + 3B
Hub, badges, Rhine route map, season challenges.
Phase 3C (versus board) adds to this file next.
"""

from flask import Blueprint, render_template, jsonify
from models import db, Badge, Workout, PersonalBest, Journey, CustomGoal
from badge_engine import evaluate_badges, BADGE_ICONS, get_badge_progress, weekly_avg_meters
from datetime import date, timedelta
from sqlalchemy import func, extract

gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


# ---------------------------------------------------------------------------
# Route map marker interpolation — shared by all four journeys now that the
# map itself is real (Leaflet + OpenStreetMap tiles, see journey-map.js)
# instead of a hand-tuned SVG illustration. Real maps handle marker
# placement and zoom themselves, so this replaces what used to be a much
# larger SVG-label-collision-avoidance system (fan-out ranks, left/right
# alternation) — none of that applies once waypoints are real lat/lon pins
# on real tiles.
# ---------------------------------------------------------------------------

def _layout_geo_route(waypoints, pct):
    """
    Interpolate the current-position marker's lat/lon between whichever two
    waypoints straddle the current progress percentage — same index-based
    interpolation the old SVG layout used for x/y, just in lat/lon instead.
    Waypoints themselves need no per-route layout; each already carries its
    own real "lat"/"lon".
    """
    n = len(waypoints)
    idx_f = (pct / 100) * (n - 1)
    idx_i = int(idx_f)
    idx_j = min(idx_i + 1, n - 1)
    frac = idx_f - idx_i
    a, b = waypoints[idx_i], waypoints[idx_j]
    marker = {
        "lat": a["lat"] + frac * (b["lat"] - a["lat"]),
        "lon": a["lon"] + frac * (b["lon"] - a["lon"]),
    }
    return waypoints, marker


# ---------------------------------------------------------------------------
# BADGE helpers (Phase 3A — unchanged)
# ---------------------------------------------------------------------------

BADGE_CATEGORIES = {
    "Performance": [
        "sub_2_06_pace", "sub_2_00_pace", "sub_1_55_pace",
        "pb_crusher", "2k_legend", "10k_club", "half_marathon",
    ],
    "Volume": [
        "first_100k", "quarter_million", "half_million",
        "one_million", "century_month",
    ],
    "Consistency": [
        "week_warrior", "iron_month", "streak_30",
    ],
    "Efficiency": [
        "technique_gain", "load_master",
    ],
}

def _get_badges_by_category():
    all_badges = {b.badge_key: b for b in Badge.query.all()}
    categorized = {}
    for category, keys in BADGE_CATEGORIES.items():
        categorized[category] = [all_badges[k] for k in keys if k in all_badges]
    return categorized

def _attach_badge_display(badges):
    """Attach transient .icon / .progress attributes for template rendering.
    Not mapped columns, so nothing is persisted by this."""
    for badge in badges:
        badge.icon = BADGE_ICONS.get(badge.badge_key, "🏅")
        badge.progress = None if badge.earned_date else get_badge_progress(badge.badge_key)

def _get_stale_pbs():
    """PBs due for a retest (90 days - 1 year old).

    Bounded on both ends: under 90 days isn't stale yet, and over a year
    isn't a "nudge" anymore — see PersonalBest.staleness_tier. Without the
    upper bound, every PB on a multi-year account nudges forever, which
    defeats the point of a nudge list.
    """
    today = date.today()
    lower_cutoff = today - timedelta(days=365)
    upper_cutoff = today - timedelta(days=90)
    return PersonalBest.query.filter(
        PersonalBest.achieved_date != None,
        PersonalBest.achieved_date < upper_cutoff,
        PersonalBest.achieved_date >= lower_cutoff,
    ).all()

def _get_gamification_stats():
    total_metres = db.session.query(func.sum(Workout.total_distance_meters)).scalar() or 0
    earned_count = Badge.query.filter(Badge.earned_date != None).count()
    total_count  = Badge.query.count()
    return {
        "total_metres":  total_metres,
        "earned_badges": earned_count,
        "total_badges":  total_count,
        "progress_pct":  round((earned_count / total_count * 100) if total_count else 0, 1),
    }


# ---------------------------------------------------------------------------
# RHINE ROUTE helpers (Phase 3B)
# ---------------------------------------------------------------------------

RHINE_TOTAL_KM = 820
RHINE_TOTAL_M  = 820_000

RHINE_WAYPOINTS = [
    {"km":   0, "name": "Basel, Switzerland",          "emoji": "🇨🇭", "lat": 47.5596, "lon": 7.5886},
    {"km":  74, "name": "Breisach am Rhein",            "emoji": "🏰", "lat": 48.0333, "lon": 7.5833},
    {"km": 145, "name": "Strasbourg, France",           "emoji": "🇫🇷", "lat": 48.5734, "lon": 7.7521},
    {"km": 220, "name": "Karlsruhe, Germany",           "emoji": "🏛️", "lat": 49.0069, "lon": 8.4037},
    {"km": 293, "name": "Mannheim / Heidelberg",        "emoji": "🎓", "lat": 49.4875, "lon": 8.4660},
    {"km": 360, "name": "Frankfurt am Main",            "emoji": "🏙️", "lat": 50.1109, "lon": 8.6821},
    {"km": 430, "name": "Koblenz",                      "emoji": "⛰️", "lat": 50.3569, "lon": 7.5890},
    {"km": 500, "name": "Bonn",                         "emoji": "🎵", "lat": 50.7374, "lon": 7.0982},
    {"km": 530, "name": "Cologne — Kölner Dom",         "emoji": "⛪", "lat": 50.9375, "lon": 6.9603},
    {"km": 590, "name": "Düsseldorf",                   "emoji": "🎨", "lat": 51.2277, "lon": 6.7735},
    {"km": 640, "name": "Duisburg",                     "emoji": "⚓", "lat": 51.4344, "lon": 6.7623},
    {"km": 710, "name": "Arnhem, Netherlands",          "emoji": "🇳🇱", "lat": 51.9851, "lon": 5.8987},
    {"km": 760, "name": "Utrecht",                      "emoji": "🚲", "lat": 52.0907, "lon": 5.1214},
    {"km": 820, "name": "Rotterdam",                    "emoji": "🚢", "lat": 51.9244, "lon": 4.4777},
]


def _get_rhine_data():
    """Compute Rhine journey position from journey start date only."""
    journey = (
        Journey.query
        .filter_by(route_key="rhine")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_geo_route(
            [{**wp, "passed": False} for wp in RHINE_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": RHINE_TOTAL_KM, "remaining_m": RHINE_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": RHINE_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= journey.start_date,
        Workout.workout_type == "rower",
    ).scalar() or 0

    position_km = min((journey_m / RHINE_TOTAL_M) * RHINE_TOTAL_KM, RHINE_TOTAL_KM)
    pct = min(round((journey_m / RHINE_TOTAL_M) * 100, 2), 100)

    if journey_m >= RHINE_TOTAL_M and not journey.completed:
        journey.completed = True
        journey.completed_date = date.today()
        db.session.commit()

    waypoints, last_passed, next_wp = [], None, None
    for wp in RHINE_WAYPOINTS:
        passed = position_km >= wp["km"]
        if passed: last_passed = wp
        elif next_wp is None: next_wp = wp
        waypoints.append({**wp, "passed": passed})

    waypoints, marker = _layout_geo_route(waypoints, pct)

    weekly_avg_m = weekly_avg_meters()
    remaining_m = max(RHINE_TOTAL_M - journey_m, 0)
    eta = (date.today() + timedelta(weeks=remaining_m / weekly_avg_m)) if weekly_avg_m > 0 and remaining_m > 0 else None

    return {
        "active":         not journey.completed,
        "complete":       journey.completed,
        "start_date":     journey.start_date.isoformat(),
        "completed_date": journey.completed_date.isoformat() if journey.completed_date else None,
        "journey_metres": journey_m,
        "position_km":    round(position_km, 1),
        "pct":            pct,
        "remaining_km":   round(RHINE_TOTAL_KM - position_km, 1),
        "remaining_m":    remaining_m,
        "waypoints":      waypoints,
        "marker":         marker,
        "last_passed":    last_passed,
        "next_waypoint":  next_wp,
        "eta":            eta.isoformat() if eta else None,
        "weekly_avg_km":  round(weekly_avg_m / 1000, 1),
    }


# ---------------------------------------------------------------------------
# HOLLAND TOUR route (Phase 3B+)
# Scenic loop through Holland's famous cities and villages ~550 km
# ---------------------------------------------------------------------------

HOLLAND_TOTAL_KM = 550
HOLLAND_TOTAL_M  = 550_000

HOLLAND_WAYPOINTS = [
    {"km":   0, "name": "Amsterdam",              "emoji": "🌷", "lat": 52.3676, "lon": 4.9041},
    {"km":  25, "name": "Volendam",               "emoji": "🐟", "lat": 52.4990, "lon": 5.0723},
    {"km":  50, "name": "Edam",                   "emoji": "🧀", "lat": 52.5125, "lon": 5.0367},
    {"km":  90, "name": "Alkmaar",                "emoji": "🧀", "lat": 52.6324, "lon": 4.7534},
    {"km": 130, "name": "Zandvoort aan Zee",      "emoji": "🏖️", "lat": 52.3730, "lon": 4.5327},
    {"km": 165, "name": "Haarlem",                "emoji": "🌸", "lat": 52.3874, "lon": 4.6462},
    {"km": 200, "name": "Keukenhof / Lisse",      "emoji": "🌺", "lat": 52.2693, "lon": 4.5497},
    {"km": 230, "name": "Leiden",                 "emoji": "🎓", "lat": 52.1601, "lon": 4.4970},
    {"km": 265, "name": "Delft",                  "emoji": "🏺", "lat": 52.0116, "lon": 4.3571},
    {"km": 295, "name": "The Hague",              "emoji": "⚖️", "lat": 52.0705, "lon": 4.3007},
    {"km": 330, "name": "Rotterdam",              "emoji": "🚢", "lat": 51.9244, "lon": 4.4777},
    {"km": 360, "name": "Kinderdijk Windmills",   "emoji": "🌬️", "lat": 51.8825, "lon": 4.6317},
    {"km": 395, "name": "Gouda",                  "emoji": "🧀", "lat": 52.0115, "lon": 4.7104},
    {"km": 430, "name": "Utrecht",                "emoji": "🔔", "lat": 52.0907, "lon": 5.1214},
    {"km": 480, "name": "Muiden Castle",          "emoji": "🏰", "lat": 52.3336, "lon": 5.0714},
    {"km": 515, "name": "Waterland Polder",       "emoji": "🐄", "lat": 52.4167, "lon": 4.9667},
    {"km": 550, "name": "Amsterdam (return)",     "emoji": "🌷", "lat": 52.3676, "lon": 4.9041},
]


def _get_holland_data():
    """Compute Holland Tour journey position from journey start date."""
    journey = (
        Journey.query
        .filter_by(route_key="holland")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_geo_route(
            [{**wp, "passed": False} for wp in HOLLAND_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": HOLLAND_TOTAL_KM, "remaining_m": HOLLAND_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": HOLLAND_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= journey.start_date,
        Workout.workout_type == "rower",
    ).scalar() or 0

    position_km = min((journey_m / HOLLAND_TOTAL_M) * HOLLAND_TOTAL_KM, HOLLAND_TOTAL_KM)
    pct = min(round((journey_m / HOLLAND_TOTAL_M) * 100, 2), 100)

    if journey_m >= HOLLAND_TOTAL_M and not journey.completed:
        journey.completed = True
        journey.completed_date = date.today()
        db.session.commit()

    waypoints, last_passed, next_wp = [], None, None
    for wp in HOLLAND_WAYPOINTS:
        passed = position_km >= wp["km"]
        if passed: last_passed = wp
        elif next_wp is None: next_wp = wp
        waypoints.append({**wp, "passed": passed})

    waypoints, marker = _layout_geo_route(waypoints, pct)

    weekly_avg_m = weekly_avg_meters()
    remaining_m = max(HOLLAND_TOTAL_M - journey_m, 0)
    eta = (date.today() + timedelta(weeks=remaining_m / weekly_avg_m)) if weekly_avg_m > 0 and remaining_m > 0 else None

    return {
        "active": not journey.completed, "complete": journey.completed,
        "start_date": journey.start_date.isoformat(),
        "completed_date": journey.completed_date.isoformat() if journey.completed_date else None,
        "journey_metres": journey_m, "position_km": round(position_km, 1),
        "pct": pct, "remaining_km": round(HOLLAND_TOTAL_KM - position_km, 1),
        "remaining_m": remaining_m, "waypoints": waypoints, "marker": marker,
        "last_passed": last_passed, "next_waypoint": next_wp,
        "eta": eta.isoformat() if eta else None,
        "weekly_avg_km": round(weekly_avg_m / 1000, 1),
    }


# ---------------------------------------------------------------------------
# TRANS-CANADA HIGHWAY route (Phase 3B+)
# Victoria, BC → St. John's, NL — 7,821 km
# ---------------------------------------------------------------------------
# ROUTE 66 (Phase 3B+)
# Chicago, IL → Santa Monica, CA — 3,940 km
# ---------------------------------------------------------------------------

ROUTE66_TOTAL_KM = 3940
ROUTE66_TOTAL_M  = 3_940_000

ROUTE66_WAYPOINTS = [
    {"km":    0, "name": "Chicago, IL — Start",          "emoji": "🌆", "lat": 41.8781, "lon": -87.6298},
    {"km":   80, "name": "Joliet, IL",                   "emoji": "🎰", "lat": 41.5250, "lon": -88.0817},
    {"km":  210, "name": "Bloomington, IL",               "emoji": "🌽", "lat": 40.4842, "lon": -88.9937},
    {"km":  320, "name": "Springfield, IL",               "emoji": "🎩", "lat": 39.7817, "lon": -89.6501},
    {"km":  440, "name": "St. Louis, MO — Gateway Arch", "emoji": "⛩️", "lat": 38.6270, "lon": -90.1994},
    {"km":  590, "name": "Cuba, MO",                     "emoji": "🛣️", "lat": 38.0645, "lon": -91.4093},
    {"km":  700, "name": "Springfield, MO",               "emoji": "🎸", "lat": 37.2090, "lon": -93.2923},
    {"km":  830, "name": "Joplin, MO",                   "emoji": "🏙️", "lat": 37.0842, "lon": -94.5133},
    {"km":  920, "name": "Tulsa, OK — Oil Capital",      "emoji": "🛢️", "lat": 36.1540, "lon": -95.9928},
    {"km": 1100, "name": "Oklahoma City, OK",             "emoji": "🤠", "lat": 35.4676, "lon": -97.5164},
    {"km": 1280, "name": "Amarillo, TX — Big Texan",     "emoji": "🥩", "lat": 35.2220, "lon": -101.8313},
    {"km": 1490, "name": "Tucumcari, NM",                "emoji": "🌵", "lat": 35.1717, "lon": -103.7250},
    {"km": 1640, "name": "Santa Fe, NM",                 "emoji": "🏺", "lat": 35.6870, "lon": -105.9378},
    {"km": 1780, "name": "Albuquerque, NM",              "emoji": "🎈", "lat": 35.0844, "lon": -106.6504},
    {"km": 1960, "name": "Gallup, NM",                   "emoji": "🪶", "lat": 35.5281, "lon": -108.7426},
    {"km": 2080, "name": "Flagstaff, AZ",                "emoji": "🌲", "lat": 35.1983, "lon": -111.6513},
    {"km": 2180, "name": "Williams, AZ — Grand Canyon",  "emoji": "🏔️", "lat": 35.2494, "lon": -112.1901},
    {"km": 2310, "name": "Kingman, AZ",                  "emoji": "🎲", "lat": 35.1894, "lon": -114.0530},
    {"km": 2430, "name": "Oatman, AZ — Gold Rush Town",  "emoji": "🫏", "lat": 35.0264, "lon": -114.3830},
    {"km": 2560, "name": "Needles, CA",                  "emoji": "🌡️", "lat": 34.8481, "lon": -114.6141},
    {"km": 2720, "name": "Barstow, CA",                  "emoji": "🏜️", "lat": 34.8958, "lon": -117.0173},
    {"km": 2880, "name": "San Bernardino, CA",           "emoji": "🍊", "lat": 34.1083, "lon": -117.2898},
    {"km": 3020, "name": "Pasadena, CA",                 "emoji": "🌸", "lat": 34.1478, "lon": -118.1445},
    {"km": 3940, "name": "Santa Monica, CA — End",       "emoji": "🏖️", "lat": 34.0195, "lon": -118.4912},
]


def _get_route66_data():
    """Compute Route 66 journey position from journey start date."""
    journey = (
        Journey.query
        .filter_by(route_key="route66")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_geo_route(
            [{**wp, "passed": False} for wp in ROUTE66_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": ROUTE66_TOTAL_KM, "remaining_m": ROUTE66_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": ROUTE66_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= journey.start_date,
        Workout.workout_type == "rower",
    ).scalar() or 0

    position_km = min((journey_m / ROUTE66_TOTAL_M) * ROUTE66_TOTAL_KM, ROUTE66_TOTAL_KM)
    pct = min(round((journey_m / ROUTE66_TOTAL_M) * 100, 2), 100)

    if journey_m >= ROUTE66_TOTAL_M and not journey.completed:
        journey.completed = True
        journey.completed_date = date.today()
        db.session.commit()

    waypoints, last_passed, next_wp = [], None, None
    for wp in ROUTE66_WAYPOINTS:
        passed = position_km >= wp["km"]
        if passed: last_passed = wp
        elif next_wp is None: next_wp = wp
        waypoints.append({**wp, "passed": passed})

    waypoints, marker = _layout_geo_route(waypoints, pct)

    weekly_avg_m = weekly_avg_meters()
    remaining_m = max(ROUTE66_TOTAL_M - journey_m, 0)
    eta = (date.today() + timedelta(weeks=remaining_m / weekly_avg_m)) if weekly_avg_m > 0 and remaining_m > 0 else None

    return {
        "active":         not journey.completed,
        "complete":       journey.completed,
        "start_date":     journey.start_date.isoformat(),
        "completed_date": journey.completed_date.isoformat() if journey.completed_date else None,
        "journey_metres": journey_m,
        "position_km":    round(position_km, 1),
        "pct":            pct,
        "remaining_km":   round(ROUTE66_TOTAL_KM - position_km, 1),
        "remaining_m":    remaining_m,
        "waypoints":      waypoints,
        "marker":         marker,
        "last_passed":    last_passed,
        "next_waypoint":  next_wp,
        "eta":            eta.isoformat() if eta else None,
        "weekly_avg_km":  round(weekly_avg_m / 1000, 1),
    }


# ---------------------------------------------------------------------------

TRANSCAN_TOTAL_KM = 7821
TRANSCAN_TOTAL_M  = 7_821_000

TRANSCAN_WAYPOINTS = [
    {"km":    0, "name": "Victoria, BC — Mile Zero",         "emoji": "🇨🇦", "lat": 48.4284, "lon": -123.3656},
    {"km":   99, "name": "Nanaimo, BC (ferry to mainland)",  "emoji": "⛴️", "lat": 49.1659, "lon": -123.9401},
    {"km":  200, "name": "Vancouver, BC",                    "emoji": "🌁", "lat": 49.2827, "lon": -123.1207},
    {"km":  380, "name": "Kamloops, BC",                     "emoji": "🏔️", "lat": 50.6745, "lon": -120.3273},
    {"km":  610, "name": "Banff, AB",                        "emoji": "🦌", "lat": 51.1784, "lon": -115.5708},
    {"km":  730, "name": "Calgary, AB",                      "emoji": "🤠", "lat": 51.0447, "lon": -114.0719},
    {"km": 1100, "name": "Medicine Hat, AB",                 "emoji": "🎩", "lat": 50.0405, "lon": -110.6764},
    {"km": 1300, "name": "Regina, SK",                       "emoji": "🌾", "lat": 50.4452, "lon": -104.6189},
    {"km": 1600, "name": "Brandon, MB",                      "emoji": "🌻", "lat": 49.8483, "lon": -99.9501},
    {"km": 1780, "name": "Winnipeg, MB",                     "emoji": "🦬", "lat": 49.8951, "lon": -97.1384},
    {"km": 2300, "name": "Thunder Bay, ON",                  "emoji": "⛈️", "lat": 48.3809, "lon": -89.2477},
    {"km": 2750, "name": "Sault Ste. Marie, ON",             "emoji": "🌊", "lat": 46.5136, "lon": -84.3358},
    {"km": 3040, "name": "Sudbury, ON",                      "emoji": "🪨", "lat": 46.4917, "lon": -80.9930},
    {"km": 3380, "name": "Ottawa, ON",                       "emoji": "🏛️", "lat": 45.4215, "lon": -75.6972},
    {"km": 3560, "name": "Montreal, QC",                     "emoji": "🥐", "lat": 45.5017, "lon": -73.5673},
    {"km": 3820, "name": "Quebec City, QC",                  "emoji": "⚜️", "lat": 46.8139, "lon": -71.2080},
    {"km": 4280, "name": "Fredericton, NB",                  "emoji": "🍁", "lat": 45.9636, "lon": -66.6431},
    {"km": 4450, "name": "Moncton, NB",                      "emoji": "🌊", "lat": 46.0878, "lon": -64.7782},
    {"km": 4660, "name": "Halifax, NS",                      "emoji": "⚓", "lat": 44.6488, "lon": -63.5752},
    {"km": 4900, "name": "North Sydney, NS (ferry to NL)",   "emoji": "⛴️", "lat": 46.2151, "lon": -60.2517},
    {"km": 5400, "name": "Corner Brook, NL",                 "emoji": "🌲", "lat": 48.9500, "lon": -57.9522},
    {"km": 5900, "name": "Gander, NL",                       "emoji": "✈️", "lat": 48.9564, "lon": -54.6089},
    {"km": 6300, "name": "Terra Nova National Park",         "emoji": "🦦", "lat": 48.5000, "lon": -53.9667},
    {"km": 7821, "name": "St. John's, NL — Journey's End",  "emoji": "🏁", "lat": 47.5615, "lon": -52.7126},
]


def _get_transcan_data():
    """Compute Trans-Canada journey position from journey start date."""
    journey = (
        Journey.query
        .filter_by(route_key="transcan")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_geo_route(
            [{**wp, "passed": False} for wp in TRANSCAN_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": TRANSCAN_TOTAL_KM, "remaining_m": TRANSCAN_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": TRANSCAN_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= journey.start_date,
        Workout.workout_type == "rower",
    ).scalar() or 0

    position_km = min((journey_m / TRANSCAN_TOTAL_M) * TRANSCAN_TOTAL_KM, TRANSCAN_TOTAL_KM)
    pct = min(round((journey_m / TRANSCAN_TOTAL_M) * 100, 2), 100)

    if journey_m >= TRANSCAN_TOTAL_M and not journey.completed:
        journey.completed = True
        journey.completed_date = date.today()
        db.session.commit()

    waypoints, last_passed, next_wp = [], None, None
    for wp in TRANSCAN_WAYPOINTS:
        passed = position_km >= wp["km"]
        if passed: last_passed = wp
        elif next_wp is None: next_wp = wp
        waypoints.append({**wp, "passed": passed})

    waypoints, marker = _layout_geo_route(waypoints, pct)

    weekly_avg_m = weekly_avg_meters()
    remaining_m = max(TRANSCAN_TOTAL_M - journey_m, 0)
    eta = (date.today() + timedelta(weeks=remaining_m / weekly_avg_m)) if weekly_avg_m > 0 and remaining_m > 0 else None

    return {
        "active": not journey.completed, "complete": journey.completed,
        "start_date": journey.start_date.isoformat(),
        "completed_date": journey.completed_date.isoformat() if journey.completed_date else None,
        "journey_metres": journey_m, "position_km": round(position_km, 1),
        "pct": pct, "remaining_km": round(TRANSCAN_TOTAL_KM - position_km, 1),
        "remaining_m": remaining_m, "waypoints": waypoints, "marker": marker,
        "last_passed": last_passed, "next_waypoint": next_wp,
        "eta": eta.isoformat() if eta else None,
        "weekly_avg_km": round(weekly_avg_m / 1000, 1),
    }


# ---------------------------------------------------------------------------
# SEASON CHALLENGES helpers (Phase 3B)
# ---------------------------------------------------------------------------

def _quarter_bounds(quarters_ago: int = 0):
    """
    (start, end, label) for the quarter `quarters_ago` quarters before the
    current one — 0 is the current (in-progress) quarter, 1 is the last
    completed one, etc. Generalizes what used to be _current_quarter() so
    challenge history can walk backwards through past quarters with the
    same math instead of a second copy of it.
    """
    today = date.today()
    current_q_index = (today.month - 1) // 3   # 0..3
    total = today.year * 4 + current_q_index - quarters_ago
    year, q = divmod(total, 4)
    start = date(year, q * 3 + 1, 1)
    end = date(year, 12, 31) if q == 3 else date(year, q * 3 + 4, 1) - timedelta(days=1)
    label = f"Q{q + 1} {year}"
    return start, end, label


def _current_quarter():
    """Return (start_date, end_date, label) for the current quarter."""
    return _quarter_bounds(0)

def _get_challenges():
    today         = date.today()
    q_start, q_end, q_label = _current_quarter()
    days_in_q     = (q_end - q_start).days + 1
    days_elapsed  = (today - q_start).days + 1
    days_remaining = max((q_end - today).days, 0)

    # ── 1. Quarterly metre target ──────────────────────────────────────────
    # Target: 200,000m per quarter (~5 sessions/week at ~10k each)
    QUARTER_TARGET = 200_000
    q_metres = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= q_start,
        Workout.workout_date <= today,
    ).scalar() or 0
    q_pct = min(round((q_metres / QUARTER_TARGET) * 100, 1), 100)
    q_remaining = max(QUARTER_TARGET - q_metres, 0)
    q_exceeded = q_metres > QUARTER_TARGET
    daily_needed = round(q_remaining / days_remaining) if days_remaining > 0 else 0
    on_pace_daily = round(QUARTER_TARGET / days_in_q)

    # ── 2. PB season — attempt all 8 categories this quarter ──────────────
    PB_CATS = ["100m", "500m", "1000m", "2000m", "5000m", "10000m", "30min", "60min"]
    attempted = {
        pb.category
        for pb in PersonalBest.query.filter(
            PersonalBest.achieved_date >= q_start,
            PersonalBest.achieved_date <= today,
        ).all()
    }
    pb_season = [
        {"category": cat, "attempted": cat in attempted}
        for cat in PB_CATS
    ]
    pb_attempted_count = len(attempted)

    # ── 3. Consistency challenge — 15 workouts in any 30-day window ───────
    CONSISTENCY_TARGET = 15
    CONSISTENCY_WINDOW = 30
    cutoff_30 = today - timedelta(days=CONSISTENCY_WINDOW - 1)
    workouts_30 = Workout.query.filter(
        Workout.workout_date >= cutoff_30,
        Workout.workout_date <= today,
    ).count()
    consistency_pct = min(round((workouts_30 / CONSISTENCY_TARGET) * 100, 1), 100)

    # ── 4. Volume month — current calendar month stretch goal ─────────────
    MONTH_TARGET = 80_000
    month_start = today.replace(day=1)
    month_metres = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= month_start,
        Workout.workout_date <= today,
    ).scalar() or 0
    month_pct = min(round((month_metres / MONTH_TARGET) * 100, 1), 100)
    month_remaining = max(MONTH_TARGET - month_metres, 0)
    month_exceeded = month_metres > MONTH_TARGET
    month_days_remaining = (
        date(today.year, today.month % 12 + 1, 1) - timedelta(days=1) - today
    ).days if today.month < 12 else (date(today.year, 12, 31) - today).days

    return {
        "q_label":           q_label,
        "q_start":           q_start.strftime("%b %d"),
        "q_end":             q_end.strftime("%b %d, %Y"),
        "days_remaining":    days_remaining,

        "quarter": {
            "target":        QUARTER_TARGET,
            "achieved":      q_metres,
            "pct":           q_pct,
            "remaining":     q_remaining,
            "exceeded":      q_exceeded,
            "overshoot_multiple": round(q_metres / QUARTER_TARGET, 1) if q_exceeded else None,
            "daily_needed":  daily_needed,
            "on_pace_daily": on_pace_daily,
            "on_pace":       q_metres >= round(QUARTER_TARGET * (days_elapsed / days_in_q)),
        },

        "pb_season": {
            "categories":    pb_season,
            "attempted":     pb_attempted_count,
            "total":         len(PB_CATS),
            "pct":           round((pb_attempted_count / len(PB_CATS)) * 100, 1),
        },

        "consistency": {
            "count":         workouts_30,
            "target":        CONSISTENCY_TARGET,
            "window_days":   CONSISTENCY_WINDOW,
            "pct":           consistency_pct,
            "complete":      workouts_30 >= CONSISTENCY_TARGET,
        },

        "volume_month": {
            "target":        MONTH_TARGET,
            "achieved":      month_metres,
            "pct":           month_pct,
            "remaining":     month_remaining,
            "exceeded":      month_exceeded,
            "overshoot_multiple": round(month_metres / MONTH_TARGET, 1) if month_exceeded else None,
            "days_remaining": month_days_remaining,
            "month_name":    today.strftime("%B"),
        },
    }


def challenge_history(n_quarters: int = 4, n_months: int = 6):
    """
    Whether past (completed, not current) quarters and months hit their
    challenge targets. _get_challenges() only ever shows the live, in-
    progress period — once a quarter or month rolls over, whether you hit
    last quarter's 200,000m target used to just vanish, resetting to 0%
    with no record. This runs the same query logic retroactively instead
    of needing a new table, the same way PB progression was built.
    """
    QUARTER_TARGET = 200_000
    MONTH_TARGET   = 80_000
    PB_CATS = ["100m", "500m", "1000m", "2000m", "5000m", "10000m", "30min", "60min"]

    quarters = []
    for i in range(1, n_quarters + 1):
        start, end, label = _quarter_bounds(i)
        metres = db.session.query(func.sum(Workout.total_distance_meters)).filter(
            Workout.workout_date >= start,
            Workout.workout_date <= end,
        ).scalar() or 0
        pb_attempted = db.session.query(func.count(func.distinct(PersonalBest.category))).filter(
            PersonalBest.achieved_date >= start,
            PersonalBest.achieved_date <= end,
            PersonalBest.category.in_(PB_CATS),
        ).scalar() or 0
        quarters.append({
            "label":        label,
            "range":        f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}",
            "metres":       metres,
            "target":       QUARTER_TARGET,
            "pct":          min(round(metres / QUARTER_TARGET * 100, 1), 100),
            "hit":          metres >= QUARTER_TARGET,
            "pb_attempted": pb_attempted,
            "pb_total":     len(PB_CATS),
        })

    today = date.today()
    months = []
    for i in range(1, n_months + 1):
        start = _months_ago_start(today, i)
        end   = _months_ago_start(today, i - 1) - timedelta(days=1)
        metres = db.session.query(func.sum(Workout.total_distance_meters)).filter(
            Workout.workout_date >= start,
            Workout.workout_date <= end,
        ).scalar() or 0
        months.append({
            "label":  start.strftime("%B %Y"),
            "metres": metres,
            "target": MONTH_TARGET,
            "pct":    min(round(metres / MONTH_TARGET * 100, 1), 100),
            "hit":    metres >= MONTH_TARGET,
        })

    return {"quarters": quarters, "months": months}


# ---------------------------------------------------------------------------
# Journey completion notifications
# ---------------------------------------------------------------------------

def check_journey_completions():
    """
    Check every active journey for completion, emailing for any that just
    finished. Each _get_X_data() getter already flips journey.completed to
    True and commits as a side effect when the distance threshold is
    crossed — this reuses that single source of truth rather than
    re-deriving the same math, and relies on SQLAlchemy's identity map
    (same session, same PK) for `journey.completed` to reflect the getter's
    mutation on the same Python object. Call after a sync that inserted new
    workouts; safe to call anytime otherwise (already-completed journeys
    are skipped by the `completed=False` filter).
    """
    from notify import notify_journey_complete

    getters = [
        ("rhine",    _get_rhine_data),
        ("holland",  _get_holland_data),
        ("transcan", _get_transcan_data),
        ("route66",  _get_route66_data),
    ]
    for route_key, getter in getters:
        journey = Journey.query.filter_by(route_key=route_key, completed=False).order_by(Journey.id.desc()).first()
        if not journey:
            continue
        getter()
        if journey.completed:
            notify_journey_complete(route_key, journey)


# ---------------------------------------------------------------------------
# Routes — Phase 3A (unchanged)
# ---------------------------------------------------------------------------

@gamification_bp.route("/")
def hub():
    stats          = _get_gamification_stats()
    by_category    = _get_badges_by_category()
    stale_pbs      = _get_stale_pbs()
    recent_cutoff  = date.today() - timedelta(days=30)
    recently_earned = Badge.query.filter(
        Badge.earned_date != None,
        Badge.earned_date >= recent_cutoff
    ).order_by(Badge.earned_date.desc()).all()
    for badge_list in by_category.values():
        _attach_badge_display(badge_list)
    _attach_badge_display(recently_earned)
    rhine          = _get_rhine_data()
    holland        = _get_holland_data()
    transcan       = _get_transcan_data()
    challenges     = _get_challenges()
    versus         = _get_versus_data()

    from goals_engine import active_goals, goal_progress
    goals = [(g, goal_progress(g)) for g in active_goals() if not g.achieved_date][:4]

    return render_template(
        "gamification/hub.html",
        stats=stats,
        by_category=by_category,
        stale_pbs=stale_pbs,
        recently_earned=recently_earned,
        rhine=rhine,
        holland=holland,
        transcan=transcan,
        challenges=challenges,
        versus=versus,
        goals=goals,
        active_page="gamification",
        today=date.today(),
    )


@gamification_bp.route("/badges")
def badges():
    by_category = _get_badges_by_category()
    for badge_list in by_category.values():
        _attach_badge_display(badge_list)
    stats       = _get_gamification_stats()
    return render_template(
        "gamification/badges.html",
        by_category=by_category,
        stats=stats,
        active_page="gamification",
    )


# ---------------------------------------------------------------------------
# Routes — Phase 3B
# ---------------------------------------------------------------------------

@gamification_bp.route("/journeys")
def journeys():
    """All journeys hub — choose and track virtual routes."""
    return render_template("gamification/journeys.html",
        rhine=_get_rhine_data(),
        holland=_get_holland_data(),
        transcan=_get_transcan_data(),
        route66=_get_route66_data(),
        active_page="gamification",
    )


@gamification_bp.route("/route")
def route():
    """Rhine virtual route — full page view."""
    rhine = _get_rhine_data()
    return render_template(
        "gamification/route.html",
        rhine=rhine,
        active_page="gamification",
    )


@gamification_bp.route("/challenges")
def challenges():
    """Season challenges — full page view."""
    data = _get_challenges()
    history = challenge_history()
    return render_template(
        "gamification/challenges.html",
        challenges=data,
        history=history,
        active_page="gamification",
    )


@gamification_bp.route("/goals", methods=["GET", "POST"])
def goals():
    """Custom goals — every other target in the app is hardcoded; this lets
    the user set their own (distance-by-deadline, or a PB-pace target)."""
    from flask import redirect, request
    from goals_engine import create_goal, active_goals, goal_progress, parse_time_str, PB_CATEGORY_CHOICES
    from pb_engine import DISTANCE_CATEGORIES

    if request.method == "POST":
        goal_type = request.form.get("goal_type", "").strip()
        label     = request.form.get("label", "").strip()[:200]
        deadline_raw = request.form.get("deadline", "").strip()
        deadline  = date.fromisoformat(deadline_raw) if deadline_raw else None

        if goal_type == "distance":
            try:
                target_value = int(request.form.get("target_metres", "").strip())
            except ValueError:
                target_value = None
            if label and target_value and target_value > 0:
                create_goal("distance", label, target_value, deadline=deadline)
        elif goal_type == "pb_pace":
            pb_category = request.form.get("pb_category", "").strip()
            if pb_category in PB_CATEGORY_CHOICES:
                if pb_category in DISTANCE_CATEGORIES:
                    target_value = parse_time_str(request.form.get("target_time", ""))
                else:
                    try:
                        target_value = int(request.form.get("target_metres_pace", "").strip())
                    except ValueError:
                        target_value = None
                if label and target_value and target_value > 0:
                    create_goal("pb_pace", label, target_value, pb_category=pb_category, deadline=deadline)

        return redirect("/gamification/goals")

    goals_with_progress = [(g, goal_progress(g)) for g in active_goals()]
    return render_template(
        "gamification/goals.html",
        goals=goals_with_progress,
        pb_categories=PB_CATEGORY_CHOICES,
        distance_categories=DISTANCE_CATEGORIES,
        active_page="gamification",
    )


@gamification_bp.route("/goals/<int:goal_id>/archive", methods=["POST"])
def archive_goal(goal_id):
    from flask import redirect
    goal = db.get_or_404(CustomGoal, goal_id)
    goal.archived = True
    db.session.commit()
    return redirect("/gamification/goals")


@gamification_bp.route("/goals/<int:goal_id>/delete", methods=["POST"])
def delete_goal(goal_id):
    from flask import redirect
    goal = db.get_or_404(CustomGoal, goal_id)
    db.session.delete(goal)
    db.session.commit()
    return redirect("/gamification/goals")


@gamification_bp.route("/route/holland")
def route_holland():
    """Holland Tour — full page view."""
    return render_template("gamification/route_holland.html",
        holland=_get_holland_data(), active_page="gamification")


@gamification_bp.route("/route/transcan")
def route_transcan():
    """Trans-Canada — full page view."""
    return render_template("gamification/route_transcan.html",
        transcan=_get_transcan_data(), active_page="gamification")


@gamification_bp.route("/journey/start", methods=["POST"])
def journey_start():
    """Start (or restart) the Rhine journey from today."""
    from flask import redirect
    existing = Journey.query.filter_by(route_key="rhine", completed=False).first()
    if existing:
        existing.completed = True
        existing.completed_date = date.today()
    db.session.add(Journey(route_key="rhine", start_date=date.today(), completed=False))
    db.session.commit()
    return redirect("/gamification/route")


@gamification_bp.route("/journey/holland/start", methods=["POST"])
def journey_holland_start():
    """Start (or restart) the Holland Tour from today."""
    from flask import redirect
    existing = Journey.query.filter_by(route_key="holland", completed=False).first()
    if existing:
        existing.completed = True
        existing.completed_date = date.today()
    db.session.add(Journey(route_key="holland", start_date=date.today(), completed=False))
    db.session.commit()
    return redirect("/gamification/route/holland")


@gamification_bp.route("/journey/transcan/start", methods=["POST"])
def journey_transcan_start():
    """Start (or restart) the Trans-Canada journey from today."""
    from flask import redirect
    existing = Journey.query.filter_by(route_key="transcan", completed=False).first()
    if existing:
        existing.completed = True
        existing.completed_date = date.today()
    db.session.add(Journey(route_key="transcan", start_date=date.today(), completed=False))
    db.session.commit()
    return redirect("/gamification/route/transcan")


@gamification_bp.route("/api/rhine")
def api_rhine():
    """JSON Rhine position data."""
    return jsonify(_get_rhine_data())


@gamification_bp.route("/api/holland")
def api_holland():
    return jsonify(_get_holland_data())


@gamification_bp.route("/api/transcan")
def api_transcan():
    return jsonify(_get_transcan_data())


@gamification_bp.route("/route/route66")
def route_route66():
    """Route 66 — full page view."""
    return render_template("gamification/route_route66.html",
        route66=_get_route66_data(), active_page="gamification")


@gamification_bp.route("/journey/route66/start", methods=["POST"])
def journey_route66_start():
    """Start (or restart) the Route 66 journey from today."""
    from flask import redirect
    existing = Journey.query.filter_by(route_key="route66", completed=False).first()
    if existing:
        existing.completed = True
        existing.completed_date = date.today()
    db.session.add(Journey(route_key="route66", start_date=date.today(), completed=False))
    db.session.commit()
    return redirect("/gamification/route/route66")


@gamification_bp.route("/api/route66")
def api_route66():
    return jsonify(_get_route66_data())


@gamification_bp.route("/api/challenges")
def api_challenges():
    """JSON challenges data."""
    return jsonify(_get_challenges())


# ---------------------------------------------------------------------------
# Routes — Phase 3A API (unchanged)
# ---------------------------------------------------------------------------

@gamification_bp.route("/api/badges/check", methods=["POST"])
def check_badges():
    try:
        newly_awarded = evaluate_badges()
        if newly_awarded:
            from notify import notify_badges
            notify_badges(newly_awarded)
        return jsonify({
            "status":        "ok",
            "newly_awarded": newly_awarded,
            "count":         len(newly_awarded),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@gamification_bp.route("/api/badges", methods=["GET"])
def api_badges():
    badges = Badge.query.order_by(Badge.earned_date.desc().nullslast()).all()
    return jsonify([{
        "badge_key":   b.badge_key,
        "badge_name":  b.badge_name,
        "badge_desc":  b.badge_desc,
        "earned_date": b.earned_date.isoformat() if b.earned_date else None,
        "is_earned":   b.is_earned,
        "workout_id":  b.workout_id,
    } for b in badges])


# ---------------------------------------------------------------------------
# VERSUS BOARD helpers (Phase 3C)
# ---------------------------------------------------------------------------

def _window_stats(start, end):
    """Compute all versus metrics for a given date window."""
    workouts = Workout.query.filter(
        Workout.workout_date >= start,
        Workout.workout_date <= end,
        Workout.workout_type == "rower",
    ).all()

    if not workouts:
        return None

    total_metres    = sum(w.distance_meters or 0 for w in workouts)
    count           = len(workouts)
    days_in_window  = (end - start).days + 1
    weeks_in_window = days_in_window / 7

    paces = [w.avg_pace_seconds for w in workouts if w.avg_pace_seconds]
    rates = [w.avg_stroke_rate  for w in workouts if w.avg_stroke_rate]
    times = [w.time_seconds     for w in workouts if w.time_seconds]

    best_pace = min(paces) if paces else None
    avg_spm   = round(sum(rates) / len(rates)) if rates else None
    avg_len_s = round(sum(times) / len(times)) if times else None

    # Best 2k in window — exact 2000m workouts by best pace
    two_k = [w for w in workouts if w.distance_meters == 2000 and w.time_seconds]
    best_2k = min(two_k, key=lambda w: w.time_seconds).time_seconds if two_k else None

    def fmt_pace(s):
        if s is None: return None
        m, sec = divmod(s, 60)
        return f"{m}:{sec:02d}"

    def fmt_time(s):
        if s is None: return None
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"

    return {
        "total_metres":    total_metres,
        "total_km":        round(total_metres / 1000, 1),
        "count":           count,
        "avg_per_week":    round(count / weeks_in_window, 1),
        "best_pace_s":     best_pace,
        "best_pace_str":   fmt_pace(best_pace),
        "best_2k_s":       best_2k,
        "best_2k_str":     fmt_time(best_2k),
        "avg_spm":         avg_spm,
        "avg_length_s":    avg_len_s,
        "avg_length_str":  fmt_time(avg_len_s),
    }


def _months_ago_start(d: date, n: int) -> date:
    """First day of the calendar month that is `n` months before `d`'s month."""
    total = (d.year * 12 + (d.month - 1)) - n
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def _get_versus_data():
    today = date.today()

    # Window boundaries — each window is exactly one calendar month, offset
    # by calendar months (not a fixed day count, which drifts across months
    # of different lengths and previously left "3 months ago" spanning a
    # 3-month range and "12 months ago" only ~4-5 months back).
    this_month_start  = today.replace(day=1)
    last_month_start  = _months_ago_start(today, 1)
    last_month_end    = this_month_start - timedelta(days=1)
    three_months_ago_start = _months_ago_start(today, 3)
    three_months_ago_end   = _months_ago_start(today, 2) - timedelta(days=1)
    twelve_months_ago_start = _months_ago_start(today, 12)
    twelve_months_ago_end   = _months_ago_start(today, 11) - timedelta(days=1)

    windows = {
        "this_month":       _window_stats(this_month_start,       today),
        "last_month":       _window_stats(last_month_start,       last_month_end),
        "three_months_ago": _window_stats(three_months_ago_start, three_months_ago_end),
        "twelve_months_ago":_window_stats(twelve_months_ago_start,twelve_months_ago_end),
    }

    # Labels for display
    labels = {
        "this_month":        today.strftime("%B"),
        "last_month":        last_month_start.strftime("%B"),
        "three_months_ago":  three_months_ago_start.strftime("%b '%y"),
        "twelve_months_ago": twelve_months_ago_start.strftime("%b '%y"),
    }

    # Build rows for the comparison table
    # Each row: metric key, label, format hint, lower_is_better flag
    METRICS = [
        ("total_metres",   "Total Metres",        "metres",  False),
        ("count",          "Workouts",             "int",     False),
        ("avg_per_week",   "Avg / Week",           "decimal", False),
        ("best_pace_s",    "Best 500m Pace",       "pace",    True),
        ("best_2k_s",      "Best 2k Time",         "time",    True),
        ("avg_spm",        "Avg Stroke Rate",      "int",     True),
        ("avg_length_s",   "Avg Workout Length",   "time",    False),
    ]

    # Display value keys (pre-formatted strings where available)
    DISPLAY_KEYS = {
        "total_metres":   "total_metres",
        "count":          "count",
        "avg_per_week":   "avg_per_week",
        "best_pace_s":    "best_pace_str",
        "best_2k_s":      "best_2k_str",
        "avg_spm":        "avg_spm",
        "avg_length_s":   "avg_length_str",
    }

    col_order = ["this_month", "last_month", "three_months_ago", "twelve_months_ago"]

    rows = []
    for metric_key, metric_label, fmt, lower_is_better in METRICS:
        cells = {}
        ref_val = None  # compare all others against this_month
        this_val = (windows["this_month"] or {}).get(metric_key)

        for col in col_order:
            w = windows[col]
            if w is None:
                cells[col] = {"raw": None, "display": "—", "delta": None}
                continue

            raw = w.get(metric_key)
            display_key = DISPLAY_KEYS[metric_key]
            display = w.get(display_key)

            # Format metres with commas
            if fmt == "metres" and isinstance(display, int):
                display = f"{display:,}"

            # Delta of THIS column vs this_month (skip for this_month itself).
            # diff is "this column's value minus this month's value": a
            # positive diff means the column outperformed this month on a
            # higher-is-better metric. Previously computed the other way
            # around (this_month minus raw), which inverted every label —
            # e.g. a past month with far more metres than the partial
            # current month was marked "worse than this month".
            delta = None
            if col != "this_month" and this_val is not None and raw is not None:
                diff = raw - this_val
                if lower_is_better:
                    delta = "better" if diff < 0 else ("worse" if diff > 0 else "same")
                else:
                    delta = "better" if diff > 0 else ("worse" if diff < 0 else "same")

            cells[col] = {"raw": raw, "display": display, "delta": delta}

        rows.append({
            "label":  metric_label,
            "metric": metric_key,
            "cells":  cells,
        })

    return {
        "windows":   windows,
        "labels":    labels,
        "col_order": col_order,
        "rows":      rows,
    }


# ---------------------------------------------------------------------------
# Routes — Phase 3C
# ---------------------------------------------------------------------------

@gamification_bp.route("/versus")
def versus():
    """You vs. Past You leaderboard."""
    data = _get_versus_data()
    return render_template(
        "gamification/versus.html",
        versus=data,
        active_page="gamification",
    )


@gamification_bp.route("/api/versus")
def api_versus():
    """JSON versus data."""
    data = _get_versus_data()
    # Strip non-serialisable keys for JSON
    return jsonify({
        "labels":    data["labels"],
        "col_order": data["col_order"],
        "rows": [
            {
                "label":  r["label"],
                "metric": r["metric"],
                "cells":  {
                    col: {"display": r["cells"][col]["display"], "delta": r["cells"][col]["delta"]}
                    for col in data["col_order"]
                }
            }
            for r in data["rows"]
        ]
    })
