"""
Concept2 Logbook API Client — Phase 1C
========================================
OAuth 2.0 with refresh token. The refresh token is long-lived and stored
in .env as C2_REFRESH_TOKEN. On each sync we exchange it for a short-lived
access token, use it, then store the new refresh token back to .env.

Endpoints used:
  POST /oauth/access_token             — token refresh
  GET  /api/users/me/results           — paginated workout list (read-only)
  GET  /api/users/me/results/{id}/strokes — per-stroke detail for one workout,
                                             fetched on demand (see get_stroke_data)

Scopes: user:read, results:read
"""

import logging
import os
import re
from datetime import datetime, date

import requests

logger = logging.getLogger(__name__)

C2_BASE_URL   = "https://log.concept2.com"
TOKEN_URL     = f"{C2_BASE_URL}/oauth/access_token"
RESULTS_URL   = f"{C2_BASE_URL}/api/users/me/results"
PAGE_SIZE     = 100


class C2ApiClient:
    """
    Concept2 Logbook API client.
    Instantiated with credentials from app config.
    """

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token  = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def refresh_access_token(self) -> bool:
        """
        Concept2 issued a non-expiring bearer token directly.
        No token exchange needed — use it as-is.
        """
        if not self.is_configured():
            logger.error("C2 credentials not configured.")
            return False

        self.access_token = self.refresh_token
        logger.info("Using pre-issued C2 bearer token directly.")
        return True

    def _persist_refresh_token(self, new_token: str):
        """Write updated refresh token back to .env file."""
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if not os.path.exists(env_path):
            logger.warning(".env file not found — cannot persist new refresh token.")
            return
        try:
            with open(env_path, "r") as f:
                content = f.read()
            content = re.sub(
                r"^C2_REFRESH_TOKEN=.*$",
                f"C2_REFRESH_TOKEN={new_token}",
                content,
                flags=re.MULTILINE,
            )
            with open(env_path, "w") as f:
                f.write(content)
            logger.info("Refresh token persisted to .env.")
        except Exception as e:
            logger.error(f"Failed to persist refresh token: {e}")

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def get_results(self, since_date=None) -> list:
        """
        Fetch all workout results, paginating until exhausted.
        since_date: date object — only fetch results on or after this date.
        Returns list of raw result dicts from the API.
        """
        if not self.access_token:
            if not self.refresh_access_token():
                return []

        results = []
        page    = 1

        while True:
            params = {"per_page": PAGE_SIZE, "page": page, "type": "rower"}
            if since_date:
                params["from"] = since_date.isoformat()

            try:
                resp = requests.get(
                    RESULTS_URL,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 401:
                    logger.error("C2 API returned 401 — check that C2_REFRESH_TOKEN in .env is correct.")
                    break

                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.error(f"C2 API request failed (page {page}): {e}")
                break

            page_data = data.get("data", [])
            results.extend(page_data)

            # Pagination — stop when we get fewer results than page size
            meta = data.get("meta", {})
            last_page = meta.get("last_page", 1)
            if page >= last_page:
                break
            page += 1

        logger.info(f"Fetched {len(results)} results from C2 API.")
        return results

    def get_stroke_data(self, workout_id: int) -> list | None:
        """
        Fetch per-stroke detail for a single workout.

        Deliberately not part of sync_workouts() / get_results() — it's one
        extra API call per workout, so it's called lazily from the workout
        detail page (and cached in Workout.stroke_data) rather than for
        every historical result on every sync.

        Returns a list of stroke dicts in C2's native units — t: tenths of
        a second elapsed, d: cumulative metres, p: tenths of a second per
        500m pace, spm: stroke rate, hr: heart rate — or None on failure.
        """
        if not self.access_token:
            if not self.refresh_access_token():
                return None

        url = f"{C2_BASE_URL}/api/users/me/results/{workout_id}/strokes"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.RequestException as e:
            logger.error(f"C2 stroke-data request failed for workout {workout_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync_workouts(self, app=None) -> dict:
        """
        Sync workouts from C2 API into the local database.

        - First run: fetches all historical results
        - Subsequent runs: fetches only since the most recent synced_at date

        Returns summary dict: {inserted, skipped, errors}
        Requires Flask app context.
        """
        from models import db, Workout

        if not self.is_configured():
            return {"inserted": 0, "skipped": 0, "errors": 1,
                    "message": "C2 credentials not configured."}

        # Determine since_date from last synced workout
        latest = db.session.query(
            db.func.max(Workout.synced_at)
        ).scalar()

        since_date = latest.date() if latest else None
        logger.info(f"Syncing C2 workouts since: {since_date or 'beginning'}")

        raw_results = self.get_results(since_date=since_date)
        if not raw_results:
            return {"inserted": 0, "skipped": 0, "errors": 0,
                    "message": "No new results from C2 API."}

        inserted = 0
        skipped  = 0
        errors   = 0

        for result in raw_results:
            try:
                c2_id = result.get("id")
                if not c2_id:
                    errors += 1
                    continue

                # Skip if already in DB (C2 ID is PK)
                if Workout.query.get(c2_id):
                    skipped += 1
                    continue

                workout = _map_result_to_workout(result)
                db.session.add(workout)
                inserted += 1

            except Exception as e:
                logger.error(f"Error inserting result {result.get('id')}: {e}")
                errors += 1

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            return {"inserted": 0, "skipped": skipped, "errors": errors + 1,
                    "message": str(e)}

        logger.info(f"Sync complete — inserted: {inserted}, skipped: {skipped}, errors: {errors}")
        return {
            "inserted": inserted,
            "skipped":  skipped,
            "errors":   errors,
            "message":  f"Sync complete. {inserted} new workouts added.",
        }


# ------------------------------------------------------------------
# Field mapping — C2 API response → Workout model
# ------------------------------------------------------------------

def _map_result_to_workout(result: dict):
    """Map a single C2 API result dict to a Workout ORM object."""
    from models import Workout

    # C2 returns date as ISO string e.g. "2024-11-15 09:32:00"
    raw_date = result.get("date", "")
    try:
        workout_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        workout_date = date.today()

    # Distance and time
    distance_m = result.get("distance", 0) or 0
    # C2 time is in tenths of a second
    time_raw   = result.get("time", 0) or 0
    time_s     = round(time_raw / 10) if time_raw else None

    # Pace — not provided by C2, calculated from time and distance
    # pace = (time_seconds / distance_meters) * 500
    if time_s and distance_m:
        pace_s = round((time_s / distance_m) * 500)
    else:
        pace_s = None

    # Stroke rate — field is "stroke_rate" at top level
    stroke_rate = result.get("stroke_rate") or None
    if stroke_rate:
        stroke_rate = int(stroke_rate)

    # Calories — field is "calories_total"
    calories = result.get("calories_total") or None
    if calories:
        calories = int(calories)

    # result["stroke_data"] is just a boolean flag from the results-list
    # endpoint ("per-stroke detail exists on C2 for this workout"), not the
    # actual stroke array — that's stored in raw_json and read via
    # blueprints.tracker's has_stroke_data check. The real array is fetched
    # on demand by C2ApiClient.get_stroke_data() and cached here on first
    # view of the workout detail page, so it starts out empty at sync time.
    return Workout(
        id               = result["id"],
        workout_date     = workout_date,
        workout_type     = "rower",
        time_seconds     = time_s,
        distance_meters  = int(distance_m),
        avg_pace_seconds = pace_s,
        avg_stroke_rate  = stroke_rate,
        total_calories   = calories,
        stroke_data      = None,
        raw_json         = result,
        synced_at        = datetime.utcnow(),
    )
