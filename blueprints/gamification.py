"""
blueprints/gamification.py — Phase 3A + 3B
Hub, badges, Rhine route map, season challenges.
Phase 3C (versus board) adds to this file next.
"""

from flask import Blueprint, render_template, jsonify
from models import db, Badge, Workout, PersonalBest, Journey
from badge_engine import evaluate_badges, BADGE_ICONS, get_badge_progress
from datetime import date, timedelta
from sqlalchemy import func, extract

gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


# ---------------------------------------------------------------------------
# Route map label layout — shared by the horizontal routes (Trans-Canada,
# Route 66). A handful of waypoints on every real route end up close
# together in x once the whole map is scaled to the full route length (e.g.
# Trans-Canada's Victoria/Nanaimo/Vancouver/Kamloops all sit inside the
# first 5% of 7,821 km), so a fixed above/below alternation isn't enough —
# consecutive same-side labels there collide. This fans them out: each
# label alternates above/below as before, but if the last label placed on
# that side is closer than min_gap, it's pushed one more "rung" outward.
# ---------------------------------------------------------------------------

def _fan_label_layout(coords, min_gap=42):
    """
    coords: [(x, y), ...] in path order.
    Returns a parallel list of {"above": bool, "rank": int} — rank 0 is the
    closest rung, higher ranks push the label further from the dot.
    """
    layout = []
    last_x = {True: None, False: None}
    last_rank = {True: -1, False: -1}
    above = True
    for x, _y in coords:
        if last_x[above] is not None and (x - last_x[above]) < min_gap:
            rank = last_rank[above] + 1
        else:
            rank = 0
        layout.append({"above": above, "rank": rank})
        last_x[above] = x
        last_rank[above] = rank
        above = not above
    return layout


def _marker_label_clearance(flank_a, flank_b, closer_is_a):
    """
    Placement for the animated "You are here" label: opposite side from
    whichever flanking waypoint it's closer to, and pushed one rung further
    out than either neighbour, so it never lands in the same lane as a
    waypoint label that happens to be nearby.
    """
    near = flank_a if closer_is_a else flank_b
    return {
        "above": not near["above"],
        "rank": max(flank_a["rank"], flank_b["rank"]) + 1,
    }


def _layout_horizontal_route(path_points, waypoints, pct, min_gap=42):
    """
    Attach map coordinates + fanned label placement to each waypoint, and
    compute the current-position marker's coordinates + label placement.
    Shared by the two horizontal (west-to-east) routes — Trans-Canada and
    Route 66 — which hit the same problem: a handful of waypoints always
    end up close together in x once the map is scaled to the full route
    length (e.g. Victoria/Nanaimo/Vancouver/Kamloops all sit inside the
    first 5% of Trans-Canada's 7,821 km).
    """
    layout = _fan_label_layout(path_points, min_gap=min_gap)
    out_waypoints = [
        {**wp, "x": x, "y": y, "label_above": lay["above"], "label_rank": lay["rank"]}
        for wp, (x, y), lay in zip(waypoints, path_points, layout)
    ]

    n = len(path_points)
    idx_f = (pct / 100) * (n - 1)
    idx_i = int(idx_f)
    idx_j = min(idx_i + 1, n - 1)
    frac = idx_f - idx_i
    mx = path_points[idx_i][0] + frac * (path_points[idx_j][0] - path_points[idx_i][0])
    my = path_points[idx_i][1] + frac * (path_points[idx_j][1] - path_points[idx_i][1])

    marker_layout = _marker_label_clearance(layout[idx_i], layout[idx_j], closer_is_a=frac < 0.5)
    marker = {
        "x": round(mx), "y": round(my),
        "label_above": marker_layout["above"], "label_rank": marker_layout["rank"],
    }
    return out_waypoints, marker


def _layout_side_alternating_route(path_points, waypoints, pct, side_fn):
    """
    Attach map coordinates + label side to each waypoint (side_fn decides
    left/right per index, same rule the template used to apply inline),
    and compute the current-position marker's placement — opposite side
    from its nearest neighbour, pushed further out — so it doesn't land in
    the same lane as a nearby waypoint label. Shared by Rhine (mostly
    vertical) and Holland (loop), whose waypoints alternate sides by a
    fixed per-index rule rather than the horizontal routes' proximity-based
    fan-out (see _layout_horizontal_route).
    """
    out_waypoints = [
        {**wp, "x": x, "y": y, "label_right": side_fn(i)}
        for i, (wp, (x, y)) in enumerate(zip(waypoints, path_points))
    ]

    n = len(path_points)
    idx_f = (pct / 100) * (n - 1)
    idx_i = int(idx_f)
    idx_j = min(idx_i + 1, n - 1)
    frac = idx_f - idx_i
    mx = path_points[idx_i][0] + frac * (path_points[idx_j][0] - path_points[idx_i][0])
    my = path_points[idx_i][1] + frac * (path_points[idx_j][1] - path_points[idx_i][1])

    flank_a = {"above": side_fn(idx_i), "rank": 0}
    flank_b = {"above": side_fn(idx_j), "rank": 0}
    marker_layout = _marker_label_clearance(flank_a, flank_b, closer_is_a=frac < 0.5)
    marker = {
        "x": round(mx), "y": round(my),
        "right": marker_layout["above"], "rank": marker_layout["rank"],
    }
    return out_waypoints, marker


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
    cutoff = date.today() - timedelta(days=90)
    return PersonalBest.query.filter(
        PersonalBest.achieved_date != None,
        PersonalBest.achieved_date < cutoff
    ).all()

def _get_gamification_stats():
    total_metres = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
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
    {"km":   0, "name": "Basel, Switzerland",          "emoji": "🇨🇭"},
    {"km":  74, "name": "Breisach am Rhein",            "emoji": "🏰"},
    {"km": 145, "name": "Strasbourg, France",           "emoji": "🇫🇷"},
    {"km": 220, "name": "Karlsruhe, Germany",           "emoji": "🏛️"},
    {"km": 293, "name": "Mannheim / Heidelberg",        "emoji": "🎓"},
    {"km": 360, "name": "Frankfurt am Main",            "emoji": "🏙️"},
    {"km": 430, "name": "Koblenz",                      "emoji": "⛰️"},
    {"km": 500, "name": "Bonn",                         "emoji": "🎵"},
    {"km": 530, "name": "Cologne — Kölner Dom",         "emoji": "⛪"},
    {"km": 590, "name": "Düsseldorf",                   "emoji": "🎨"},
    {"km": 640, "name": "Duisburg",                     "emoji": "⚓"},
    {"km": 710, "name": "Arnhem, Netherlands",          "emoji": "🇳🇱"},
    {"km": 760, "name": "Utrecht",                      "emoji": "🚲"},
    {"km": 820, "name": "Rotterdam",                    "emoji": "🚢"},
]

# Map coordinates — 700×520 viewBox, index-aligned with RHINE_WAYPOINTS
# (0=Basel at the bottom, 13=Rotterdam at the top).
RHINE_PATH_POINTS = [
    (350, 470), (338, 432), (325, 395), (345, 358), (335, 322), (320, 286),
    (342, 250), (330, 214), (325, 195), (318, 170), (328, 148), (335, 112),
    (338, 82),  (340, 50),
]


def _rhine_waypoint_side(i):
    """Right/left rule the template used inline — kept as-is; only the
    marker's placement changes (see _layout_side_alternating_route)."""
    return i % 2 == 0


def _get_rhine_data():
    """Compute Rhine journey position from journey start date only."""
    journey = (
        Journey.query
        .filter_by(route_key="rhine")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_side_alternating_route(
            RHINE_PATH_POINTS, [{**wp, "passed": False} for wp in RHINE_WAYPOINTS], pct=0,
            side_fn=_rhine_waypoint_side,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": RHINE_TOTAL_KM, "remaining_m": RHINE_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": RHINE_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.distance_meters)).filter(
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

    waypoints, marker = _layout_side_alternating_route(
        RHINE_PATH_POINTS, waypoints, pct, side_fn=_rhine_waypoint_side,
    )

    cutoff = date.today() - timedelta(days=28)
    recent_m = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= cutoff, Workout.workout_type == "rower",
    ).scalar() or 0
    weekly_avg_m = (recent_m / 28) * 7
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
    {"km":   0, "name": "Amsterdam",              "emoji": "🌷"},
    {"km":  25, "name": "Volendam",               "emoji": "🐟"},
    {"km":  50, "name": "Edam",                   "emoji": "🧀"},
    {"km":  90, "name": "Alkmaar",                "emoji": "🧀"},
    {"km": 130, "name": "Zandvoort aan Zee",      "emoji": "🏖️"},
    {"km": 165, "name": "Haarlem",                "emoji": "🌸"},
    {"km": 200, "name": "Keukenhof / Lisse",      "emoji": "🌺"},
    {"km": 230, "name": "Leiden",                 "emoji": "🎓"},
    {"km": 265, "name": "Delft",                  "emoji": "🏺"},
    {"km": 295, "name": "The Hague",              "emoji": "⚖️"},
    {"km": 330, "name": "Rotterdam",              "emoji": "🚢"},
    {"km": 360, "name": "Kinderdijk Windmills",   "emoji": "🌬️"},
    {"km": 395, "name": "Gouda",                  "emoji": "🧀"},
    {"km": 430, "name": "Utrecht",                "emoji": "🔔"},
    {"km": 480, "name": "Muiden Castle",          "emoji": "🏰"},
    {"km": 515, "name": "Waterland Polder",       "emoji": "🐄"},
    {"km": 550, "name": "Amsterdam (return)",     "emoji": "🌷"},
]

# Map coordinates — 700×400 viewBox, index-aligned with HOLLAND_WAYPOINTS.
HOLLAND_PATH_POINTS = [
    (360, 120), (400, 85),  (420, 68),  (435, 42),  (320, 42),  (255, 85),
    (210, 135), (225, 185), (235, 230), (220, 268), (265, 318), (330, 330),
    (370, 295), (415, 250), (460, 245), (430, 180), (370, 120),
]


def _holland_waypoint_side(i):
    """Right/left rule the template used inline — kept as-is; only the
    marker's placement changes (see _layout_side_alternating_route)."""
    return i not in (0, 4, 5, 6, 7, 8, 9)


def _get_holland_data():
    """Compute Holland Tour journey position from journey start date."""
    journey = (
        Journey.query
        .filter_by(route_key="holland")
        .order_by(Journey.id.desc())
        .first()
    )

    if not journey:
        empty_waypoints, empty_marker = _layout_side_alternating_route(
            HOLLAND_PATH_POINTS, [{**wp, "passed": False} for wp in HOLLAND_WAYPOINTS], pct=0,
            side_fn=_holland_waypoint_side,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": HOLLAND_TOTAL_KM, "remaining_m": HOLLAND_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": HOLLAND_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.distance_meters)).filter(
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

    waypoints, marker = _layout_side_alternating_route(
        HOLLAND_PATH_POINTS, waypoints, pct, side_fn=_holland_waypoint_side,
    )

    cutoff = date.today() - timedelta(days=28)
    recent_m = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= cutoff, Workout.workout_type == "rower",
    ).scalar() or 0
    weekly_avg_m = (recent_m / 28) * 7
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
    {"km":    0, "name": "Chicago, IL — Start",          "emoji": "🌆"},
    {"km":   80, "name": "Joliet, IL",                   "emoji": "🎰"},
    {"km":  210, "name": "Bloomington, IL",               "emoji": "🌽"},
    {"km":  320, "name": "Springfield, IL",               "emoji": "🎩"},
    {"km":  440, "name": "St. Louis, MO — Gateway Arch", "emoji": "⛩️"},
    {"km":  590, "name": "Cuba, MO",                     "emoji": "🛣️"},
    {"km":  700, "name": "Springfield, MO",               "emoji": "🎸"},
    {"km":  830, "name": "Joplin, MO",                   "emoji": "🏙️"},
    {"km":  920, "name": "Tulsa, OK — Oil Capital",      "emoji": "🛢️"},
    {"km": 1100, "name": "Oklahoma City, OK",             "emoji": "🤠"},
    {"km": 1280, "name": "Amarillo, TX — Big Texan",     "emoji": "🥩"},
    {"km": 1490, "name": "Tucumcari, NM",                "emoji": "🌵"},
    {"km": 1640, "name": "Santa Fe, NM",                 "emoji": "🏺"},
    {"km": 1780, "name": "Albuquerque, NM",              "emoji": "🎈"},
    {"km": 1960, "name": "Gallup, NM",                   "emoji": "🪶"},
    {"km": 2080, "name": "Flagstaff, AZ",                "emoji": "🌲"},
    {"km": 2180, "name": "Williams, AZ — Grand Canyon",  "emoji": "🏔️"},
    {"km": 2310, "name": "Kingman, AZ",                  "emoji": "🎲"},
    {"km": 2430, "name": "Oatman, AZ — Gold Rush Town",  "emoji": "🫏"},
    {"km": 2560, "name": "Needles, CA",                  "emoji": "🌡️"},
    {"km": 2720, "name": "Barstow, CA",                  "emoji": "🏜️"},
    {"km": 2880, "name": "San Bernardino, CA",           "emoji": "🍊"},
    {"km": 3020, "name": "Pasadena, CA",                 "emoji": "🌸"},
    {"km": 3940, "name": "Santa Monica, CA — End",       "emoji": "🏖️"},
]

# Map coordinates — 900×250 viewBox, index-aligned with ROUTE66_WAYPOINTS.
ROUTE66_PATH_POINTS = [
    (28,  90),  (68,  94),  (130, 96),  (190, 95),  (265, 108), (318, 118),
    (364, 122), (402, 138), (440, 158), (476, 172), (518, 178), (555, 172),
    (578, 162), (598, 168), (622, 175), (646, 168), (664, 160), (690, 158),
    (706, 148), (724, 142), (748, 136), (774, 118), (800, 105), (870, 92),
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
        empty_waypoints, empty_marker = _layout_horizontal_route(
            ROUTE66_PATH_POINTS, [{**wp, "passed": False} for wp in ROUTE66_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": ROUTE66_TOTAL_KM, "remaining_m": ROUTE66_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": ROUTE66_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.distance_meters)).filter(
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

    waypoints, marker = _layout_horizontal_route(ROUTE66_PATH_POINTS, waypoints, pct)

    cutoff = date.today() - timedelta(days=28)
    recent_m = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= cutoff, Workout.workout_type == "rower",
    ).scalar() or 0
    weekly_avg_m = (recent_m / 28) * 7
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
    {"km":    0, "name": "Victoria, BC — Mile Zero",         "emoji": "🇨🇦"},
    {"km":   99, "name": "Nanaimo, BC (ferry to mainland)",  "emoji": "⛴️"},
    {"km":  200, "name": "Vancouver, BC",                    "emoji": "🌁"},
    {"km":  380, "name": "Kamloops, BC",                     "emoji": "🏔️"},
    {"km":  610, "name": "Banff, AB",                        "emoji": "🦌"},
    {"km":  730, "name": "Calgary, AB",                      "emoji": "🤠"},
    {"km": 1100, "name": "Medicine Hat, AB",                 "emoji": "🎩"},
    {"km": 1300, "name": "Regina, SK",                       "emoji": "🌾"},
    {"km": 1600, "name": "Brandon, MB",                      "emoji": "🌻"},
    {"km": 1780, "name": "Winnipeg, MB",                     "emoji": "🦬"},
    {"km": 2300, "name": "Thunder Bay, ON",                  "emoji": "⛈️"},
    {"km": 2750, "name": "Sault Ste. Marie, ON",             "emoji": "🌊"},
    {"km": 3040, "name": "Sudbury, ON",                      "emoji": "🪨"},
    {"km": 3380, "name": "Ottawa, ON",                       "emoji": "🏛️"},
    {"km": 3560, "name": "Montreal, QC",                     "emoji": "🥐"},
    {"km": 3820, "name": "Quebec City, QC",                  "emoji": "⚜️"},
    {"km": 4280, "name": "Fredericton, NB",                  "emoji": "🍁"},
    {"km": 4450, "name": "Moncton, NB",                      "emoji": "🌊"},
    {"km": 4660, "name": "Halifax, NS",                      "emoji": "⚓"},
    {"km": 4900, "name": "North Sydney, NS (ferry to NL)",   "emoji": "⛴️"},
    {"km": 5400, "name": "Corner Brook, NL",                 "emoji": "🌲"},
    {"km": 5900, "name": "Gander, NL",                       "emoji": "✈️"},
    {"km": 6300, "name": "Terra Nova National Park",         "emoji": "🦦"},
    {"km": 7821, "name": "St. John's, NL — Journey's End",  "emoji": "🏁"},
]

# Map coordinates — 900×220 viewBox, index-aligned with TRANSCAN_WAYPOINTS.
TRANSCAN_PATH_POINTS = [
    (18,  165), (27,  155), (38,  148), (62,  130), (98,  108), (116, 118),
    (162, 128), (198, 130), (244, 130), (270, 128), (348, 125), (413, 120),
    (457, 118), (508, 115), (533, 112), (573, 108), (638, 112), (662, 115),
    (693, 118), (720, 116), (755, 122), (790, 128), (818, 132), (876, 148),
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
        empty_waypoints, empty_marker = _layout_horizontal_route(
            TRANSCAN_PATH_POINTS, [{**wp, "passed": False} for wp in TRANSCAN_WAYPOINTS], pct=0,
        )
        return {
            "active": False, "complete": False, "start_date": None,
            "position_km": 0, "pct": 0,
            "remaining_km": TRANSCAN_TOTAL_KM, "remaining_m": TRANSCAN_TOTAL_M,
            "waypoints": empty_waypoints, "marker": empty_marker,
            "last_passed": None, "next_waypoint": TRANSCAN_WAYPOINTS[1],
            "eta": None, "weekly_avg_km": 0, "journey_metres": 0,
        }

    journey_m = db.session.query(func.sum(Workout.distance_meters)).filter(
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

    waypoints, marker = _layout_horizontal_route(TRANSCAN_PATH_POINTS, waypoints, pct)

    cutoff = date.today() - timedelta(days=28)
    recent_m = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= cutoff, Workout.workout_type == "rower",
    ).scalar() or 0
    weekly_avg_m = (recent_m / 28) * 7
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

def _current_quarter():
    """Return (start_date, end_date, label) for the current quarter."""
    today = date.today()
    q_starts = [date(today.year, 1, 1), date(today.year, 4, 1),
                date(today.year, 7, 1), date(today.year, 10, 1)]
    q_labels = ["Q1", "Q2", "Q3", "Q4"]
    for i in range(3, -1, -1):
        if today >= q_starts[i]:
            start = q_starts[i]
            end   = q_starts[i + 1] - timedelta(days=1) if i < 3 else date(today.year, 12, 31)
            return start, end, q_labels[i]
    return q_starts[0], date(today.year, 3, 31), "Q1"

def _get_challenges():
    today         = date.today()
    q_start, q_end, q_label = _current_quarter()
    days_in_q     = (q_end - q_start).days + 1
    days_elapsed  = (today - q_start).days + 1
    days_remaining = max((q_end - today).days, 0)

    # ── 1. Quarterly metre target ──────────────────────────────────────────
    # Target: 200,000m per quarter (~5 sessions/week at ~10k each)
    QUARTER_TARGET = 200_000
    q_metres = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= q_start,
        Workout.workout_date <= today,
    ).scalar() or 0
    q_pct = min(round((q_metres / QUARTER_TARGET) * 100, 1), 100)
    daily_needed = round((QUARTER_TARGET - q_metres) / days_remaining) if days_remaining > 0 else 0
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
    month_metres = db.session.query(func.sum(Workout.distance_meters)).filter(
        Workout.workout_date >= month_start,
        Workout.workout_date <= today,
    ).scalar() or 0
    month_pct = min(round((month_metres / MONTH_TARGET) * 100, 1), 100)
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
            "days_remaining": month_days_remaining,
            "month_name":    today.strftime("%B"),
        },
    }


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
    return render_template(
        "gamification/challenges.html",
        challenges=data,
        active_page="gamification",
    )


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


def _get_versus_data():
    today      = date.today()

    # Window boundaries
    this_month_start  = today.replace(day=1)
    last_month_end    = this_month_start - timedelta(days=1)
    last_month_start  = last_month_end.replace(day=1)
    three_months_ago_end   = last_month_start - timedelta(days=1)
    three_months_ago_start = (three_months_ago_end - timedelta(days=89)).replace(day=1)
    twelve_months_ago_end   = three_months_ago_start - timedelta(days=1)
    twelve_months_ago_start = twelve_months_ago_end.replace(day=1)

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

            # Delta vs this_month (skip for this_month itself)
            delta = None
            if col != "this_month" and this_val is not None and raw is not None:
                diff = this_val - raw
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
