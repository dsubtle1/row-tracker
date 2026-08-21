"""
SQLAlchemy ORM models for Row Tracker.
All three builds share this single database file.
Builds 2 and 3 add tables only — never modify Build 1 tables.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property

db = SQLAlchemy()


class Workout(db.Model):
    """
    Build 1 core table.
    C2 workout ID is used as PK to prevent duplicate syncs.
    CSV import and future API sync both write to this table.
    """
    __tablename__ = "workouts"

    id                = db.Column(db.Integer, primary_key=True)   # C2 Log ID
    workout_date      = db.Column(db.Date, nullable=False, index=True)
    workout_type      = db.Column(db.Text, nullable=False, default="rower")
    time_seconds      = db.Column(db.Integer)                     # work-interval time only — drives pace/PBs, never mixed with rest
    rest_time_seconds = db.Column(db.Integer, nullable=True)      # time spent on rest-interval rowing (C2 "rest_time"); NULL = unknown, 0 = confirmed no rest
    distance_meters   = db.Column(db.Integer)                     # work-interval distance only — drives pace/PBs, never mixed with rest
    rest_distance_meters = db.Column(db.Integer, nullable=True)   # light rowing between intervals (C2 "rest_distance"); NULL = unknown (CSV import / no raw_json), 0 = confirmed no rest
    avg_pace_seconds  = db.Column(db.Integer)                     # 500m split in seconds
    avg_stroke_rate   = db.Column(db.Integer)
    total_calories    = db.Column(db.Integer)
    stroke_data       = db.Column(db.JSON, nullable=True)         # per-stroke array, fetched on demand; NULL until first detail-page view
    raw_json          = db.Column(db.JSON, nullable=True)         # full API payload; NULL from CSV
    synced_at         = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    personal_bests    = db.relationship("PersonalBest", back_populates="workout")
    wod_completions   = db.relationship("WodHistory", back_populates="actual_workout")
    badges            = db.relationship("Badge", back_populates="workout")

    def __repr__(self):
        return f"<Workout id={self.id} date={self.workout_date} dist={self.distance_meters}m>"

    @hybrid_property
    def total_distance_meters(self):
        """Work distance plus any rest-interval distance — the real distance rowed.
        Used for lifetime/volume totals (badges, journeys, challenges); never for
        pace or PBs, which stay work-only so rest doesn't dilute effort pace."""
        return (self.distance_meters or 0) + (self.rest_distance_meters or 0)

    @total_distance_meters.expression
    def total_distance_meters(cls):
        return func.coalesce(cls.distance_meters, 0) + func.coalesce(cls.rest_distance_meters, 0)

    @hybrid_property
    def total_time_seconds(self):
        """Work time plus any rest-interval time — real time spent rowing.
        Used for lifetime totals; never for pace or PBs, which stay work-only."""
        return (self.time_seconds or 0) + (self.rest_time_seconds or 0)

    @total_time_seconds.expression
    def total_time_seconds(cls):
        return func.coalesce(cls.time_seconds, 0) + func.coalesce(cls.rest_time_seconds, 0)

    @total_time_seconds.expression
    def total_time_seconds(cls):
        return cls.time_seconds + func.coalesce(cls.rest_time_seconds, 0)

    @property
    def avg_pace_formatted(self):
        """Return average pace as m:ss string."""
        if self.avg_pace_seconds is None:
            return "—"
        m, s = divmod(self.avg_pace_seconds, 60)
        return f"{m}:{s:02d}"

    @property
    def time_formatted(self):
        """Return elapsed time as h:mm:ss or m:ss string."""
        if self.time_seconds is None:
            return "—"
        total = int(self.time_seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


class PersonalBest(db.Model):
    """
    Build 1. One row per PB category. Recalculated after every sync.
    Fixed-distance categories store time in value_seconds.
    Time-based categories store elapsed seconds in value_seconds and metres in value_meters.
    """
    __tablename__ = "personal_bests"

    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category       = db.Column(db.Text, nullable=False)           # e.g. '2000m', '30min'
    value_seconds  = db.Column(db.Integer)                        # best time or elapsed time
    value_meters   = db.Column(db.Integer, nullable=True)         # best distance (time pieces)
    workout_id     = db.Column(db.Integer, db.ForeignKey("workouts.id"))
    achieved_date  = db.Column(db.Date)
    previous_value = db.Column(db.Integer, nullable=True)         # prior PB for delta display

    workout        = db.relationship("Workout", back_populates="personal_bests")

    def __repr__(self):
        return f"<PersonalBest category={self.category} value={self.value_seconds}s>"

    @property
    def value_formatted(self):
        """Return PB value as m:ss for distance pieces, or metres for time pieces."""
        if self.value_seconds is None:
            return "—"
        if self.value_meters is not None:
            return f"{self.value_meters:,}m"
        m, s = divmod(self.value_seconds, 60)
        return f"{m}:{s:02d}"

    @property
    def delta_seconds(self):
        """Improvement over previous PB (positive = faster/further)."""
        if self.previous_value is None or self.value_seconds is None:
            return None
        return self.previous_value - self.value_seconds

    @property
    def days_since_achieved(self):
        if self.achieved_date is None:
            return None
        return (datetime.utcnow().date() - self.achieved_date).days

    @property
    def is_stale(self):
        d = self.days_since_achieved
        return d is not None and d > 90


class WodHistory(db.Model):
    """Build 2. One row per generated WOD."""
    __tablename__ = "wod_history"

    id                 = db.Column(db.Integer, primary_key=True, autoincrement=True)
    generated_date     = db.Column(db.Date, nullable=False, index=True)
    wod_type           = db.Column(db.Text)                       # steady_state / interval / threshold / long / test
    wod_json           = db.Column(db.JSON)                       # full WOD structure
    completed          = db.Column(db.Boolean, default=False)
    actual_workout_id  = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=True)

    actual_workout     = db.relationship("Workout", back_populates="wod_completions")

    def __repr__(self):
        return f"<WodHistory date={self.generated_date} type={self.wod_type} completed={self.completed}>"


class Badge(db.Model):
    """Build 3. One row per badge definition. earned_date=None means not yet earned."""
    __tablename__ = "badges"

    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    badge_key    = db.Column(db.Text, unique=True, nullable=False)
    badge_name   = db.Column(db.Text, nullable=False)
    badge_desc   = db.Column(db.Text)
    earned_date  = db.Column(db.Date, nullable=True)              # None = locked
    workout_id   = db.Column(db.Integer, db.ForeignKey("workouts.id"), nullable=True)

    workout      = db.relationship("Workout", back_populates="badges")

    def __repr__(self):
        status = "earned" if self.earned_date else "locked"
        return f"<Badge key={self.badge_key} {status}>"

    @property
    def is_earned(self):
        return self.earned_date is not None


class Journey(db.Model):
    """
    Build 3B+. One row per journey attempt.
    Metres counted from start_date forward only.
    Only one journey per route_key can be active at a time.
    """
    __tablename__ = "journeys"

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    route_key   = db.Column(db.Text, nullable=False)          # e.g. "rhine"
    start_date  = db.Column(db.Date, nullable=False)
    completed   = db.Column(db.Boolean, default=False)
    completed_date = db.Column(db.Date, nullable=True)

    def __repr__(self):
        status = "complete" if self.completed else "active"
        return f"<Journey route={self.route_key} started={self.start_date} [{status}]>"


class SyncStatus(db.Model):
    """
    Singleton row (there's only ever one, since this is a single-user app)
    tracking the last sync attempt/success/failure — powers the Dashboard's
    "last synced" indicator and lets scheduled jobs tell a genuine failure
    apart from a quiet night with nothing new. Updated by both the nightly
    scheduler and the manual /sync route.
    """
    __tablename__ = "sync_status"

    id               = db.Column(db.Integer, primary_key=True)
    last_attempt_at  = db.Column(db.DateTime)
    last_success_at  = db.Column(db.DateTime)
    last_result      = db.Column(db.Text, nullable=True)   # human-readable summary of the last successful run
    last_error       = db.Column(db.Text, nullable=True)   # cleared on the next success

    def __repr__(self):
        state = "error" if self.last_error else "ok"
        return f"<SyncStatus last_attempt={self.last_attempt_at} [{state}]>"
