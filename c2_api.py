"""
Concept2 Logbook API Client — Phase 1C
========================================
Concept2 issues a non-expiring bearer token, stored in .env as
C2_REFRESH_TOKEN — used directly as the Authorization header on every
request, no OAuth token exchange or rotation involved.

Endpoints used:
  GET  /api/users/me/results           — paginated workout list (read-only)
  GET  /api/users/me/results/{id}/strokes — per-stroke detail for one workout,
                                             fetched on demand (see get_stroke_data)

Scopes: user:read, results:read
"""

import logging
import time
from datetime import datetime, date

import requests

logger = logging.getLogger(__name__)

C2_BASE_URL   = "https://log.concept2.com"
TOKEN_URL     = f"{C2_BASE_URL}/oauth/access_token"
RESULTS_URL   = f"{C2_BASE_URL}/api/users/me/results"
PAGE_SIZE     = 100

# C2's API returns occasional bare 5xx errors under normal conditions (seen
# in production, not just under load) — retried a few times with a short
# backoff before giving up, rather than failing the whole nightly sync (and
# paging the user) over what's usually a transient blip.
MAX_PAGE_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


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
        # Set by get_results() when the API call itself fails (bad token,
        # network error) — distinct from a call that succeeded and simply
        # returned zero results. Without this, an expired/bad token looks
        # identical to "already up to date" to every caller.
        self.last_error    = None

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
        self.last_error = None

        if not self.access_token:
            if not self.refresh_access_token():
                self.last_error = "Could not obtain a C2 access token — check C2_CLIENT_ID/C2_CLIENT_SECRET/C2_REFRESH_TOKEN."
                return []

        results = []
        page    = 1

        while True:
            params = {"per_page": PAGE_SIZE, "page": page, "type": "rower"}
            if since_date:
                params["from"] = since_date.isoformat()

            data = None
            page_error = None
            for attempt in range(1, MAX_PAGE_RETRIES + 1):
                try:
                    resp = requests.get(
                        RESULTS_URL,
                        headers=self._get_headers(),
                        params=params,
                        timeout=30,
                    )
                    if resp.status_code == 401:
                        logger.error("C2 API returned 401 — check that C2_REFRESH_TOKEN in .env is correct.")
                        self.last_error = "C2 API returned 401 (unauthorized) — check that C2_REFRESH_TOKEN in .env is correct."
                        return results

                    resp.raise_for_status()
                    data = resp.json()
                    page_error = None
                    break
                except requests.RequestException as e:
                    page_error = e
                    if attempt < MAX_PAGE_RETRIES:
                        logger.warning(f"C2 API request failed (page {page}, attempt {attempt}/{MAX_PAGE_RETRIES}): {e} — retrying")
                        time.sleep(RETRY_BACKOFF_SECONDS)

            if page_error is not None:
                logger.error(f"C2 API request failed (page {page}) after {MAX_PAGE_RETRIES} attempts: {page_error}")
                self.last_error = f"C2 API request failed: {page_error}"
                break

            page_data = data.get("data", [])
            results.extend(page_data)

            # Pagination — C2 nests it under meta.pagination.total_pages, not
            # meta.last_page. Reading the wrong key silently capped every
            # sync at page 1 (100 results); harmless for nightly incremental
            # syncs (rarely >100 new results) but would have quietly dropped
            # data after any outage long enough to queue up more than that.
            pagination = data.get("meta", {}).get("pagination", {})
            last_page = pagination.get("total_pages", 1)
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
        if self.last_error:
            return {"inserted": 0, "skipped": 0, "errors": 1,
                    "message": self.last_error}
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

    # Distance and time — "distance" is work-interval only; C2 tracks light
    # rowing between intervals separately as "rest_distance" (absent/0 for
    # non-interval workouts, so default to 0 rather than leaving it unknown).
    distance_m = result.get("distance", 0) or 0
    rest_distance_m = result.get("rest_distance", 0) or 0
    # C2 time is in tenths of a second. "rest_time" is the rest-interval
    # counterpart to "rest_distance" above — same work/rest split, same reason.
    time_raw      = result.get("time", 0) or 0
    time_s        = round(time_raw / 10) if time_raw else None
    rest_time_raw = result.get("rest_time", 0) or 0
    rest_time_s   = round(rest_time_raw / 10) if rest_time_raw else 0

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
        rest_time_seconds = rest_time_s,
        distance_meters  = int(distance_m),
        rest_distance_meters = int(rest_distance_m),
        avg_pace_seconds = pace_s,
        avg_stroke_rate  = stroke_rate,
        total_calories   = calories,
        stroke_data      = None,
        raw_json         = result,
        synced_at        = datetime.utcnow(),
    )
