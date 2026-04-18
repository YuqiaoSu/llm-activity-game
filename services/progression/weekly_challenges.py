"""Weekly challenge progress tracking.

update_weekly_progress() is called once per poll, after XP is awarded.
It receives a mapping of {category_label: xp_earned} for all chunks processed
in that poll, then upserts progress rows for the current ISO week and fires
challenge_complete notifications for first-time completions.

The week_start key (Monday ISO date) is the reset mechanism — no scheduled
job needed. Old weeks become historical records automatically.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta, timezone
from services.reward_ledger.ledger import insert_challenge_notification, insert_challenge_progress_notification


def get_week_start(dt: datetime) -> str:
    """Return the ISO date string (YYYY-MM-DD) of the Monday of dt's week."""
    monday = dt.date() - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def update_weekly_progress(
    conn: sqlite3.Connection,
    character_id: str,
    xp_by_category: dict[str, int],
) -> list[str]:
    """Update weekly challenge progress for the current ISO week.

    xp_by_category maps category label strings (e.g. 'WORK') to XP earned
    this poll. Returns a list of challenge_ids that were completed for the
    first time this week. Caller is responsible for commit.
    """
    if not xp_by_category:
        return []

    week_start = get_week_start(datetime.now(timezone.utc))

    all_challenges = conn.execute(
        "SELECT challenge_id, name, category, metric, threshold FROM weekly_challenges"
    ).fetchall()
    if not all_challenges:
        return []

    newly_completed: list[str] = []

    for ch in all_challenges:
        cid = ch["challenge_id"]
        metric = ch["metric"]
        threshold = ch["threshold"]

        # Compute the progress delta (or absolute value for 'categories' metric)
        if metric == "xp":
            delta = xp_by_category.get(ch["category"], 0)
            if delta == 0:
                continue
        elif metric == "total_xp":
            delta = sum(xp_by_category.values())
            if delta == 0:
                continue
        elif metric == "categories":
            delta = None  # absolute recompute below
        else:
            continue  # unknown metric — skip

        # Fetch existing row for this week
        existing = conn.execute(
            "SELECT progress, completed FROM player_weekly_progress "
            "WHERE player_id=? AND challenge_id=? AND week_start=?",
            (character_id, cid, week_start),
        ).fetchone()

        old_progress = existing["progress"] if existing else 0
        was_completed = bool(existing["completed"]) if existing else False

        # Compute new progress value
        if metric == "categories":
            # Count distinct categories in chunk_log for this week.
            # chunk_log.processed_at is ISO format — string >= week_start works
            # for UTC timestamps.
            row = conn.execute(
                "SELECT COUNT(DISTINCT category) AS cnt FROM chunk_log WHERE processed_at >= ?",
                (week_start,),
            ).fetchone()
            new_progress = row["cnt"] if row else 0
        else:
            new_progress = old_progress + delta

        # Upsert progress row
        conn.execute(
            """
            INSERT INTO player_weekly_progress (player_id, challenge_id, week_start, progress)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (player_id, challenge_id, week_start)
            DO UPDATE SET progress = excluded.progress
            """,
            (character_id, cid, week_start, new_progress),
        )

        # Fire 50% progress notification on first half-way crossing
        old_half = old_progress * 2 >= threshold
        new_half = new_progress * 2 >= threshold
        if not was_completed and not old_half and new_half and new_progress < threshold:
            insert_challenge_progress_notification(conn, character_id, cid, ch["name"], 50)

        # Fire completion on first threshold crossing
        if not was_completed and new_progress >= threshold:
            conn.execute(
                """
                UPDATE player_weekly_progress SET completed=1, reward_given=1
                WHERE player_id=? AND challenge_id=? AND week_start=?
                """,
                (character_id, cid, week_start),
            )
            insert_challenge_notification(conn, character_id, cid, ch["name"])
            newly_completed.append(cid)

    return newly_completed
