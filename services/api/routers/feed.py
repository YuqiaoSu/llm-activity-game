"""Activity feed — recent notable player events in reverse-chronological order.

GET /feed?limit=N  (default 20, max 100)

Aggregates events from three sources:
  - chunk_log        → "activity" events (per-category XP sessions)
  - reward_ledger    → "item_drop" events
  - pending_notifications → "level_up", "achievement_unlocked", "place_unlock",
                            "place_level_up", "streak_milestone" events

Returns newest-first list of:
  event_type    string
  description   human-readable summary
  happened_at   ISO datetime
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query

router = APIRouter()

_MAX_LIMIT = 100


@router.get("")
def get_feed(
    request: Request,
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
) -> list[dict]:
    db = request.app.state.db

    # ── activity chunks (summarised: one event per chunk) ────────────────────
    chunk_rows = db.execute(
        """
        SELECT 'activity' AS event_type,
               category || ' session — ' || xp_awarded || ' XP' AS description,
               processed_at AS happened_at
        FROM chunk_log
        ORDER BY processed_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    # ── item drops (with resolved item name from definitions) ────────────────
    drop_rows = db.execute(
        """
        SELECT 'item_drop' AS event_type,
               'Item drop: ' || COALESCE(
                   json_extract(d.data, '$.name'), rl.item_id
               ) AS description,
               rl.awarded_at AS happened_at
        FROM reward_ledger rl
        LEFT JOIN item_definitions d ON d.item_id = rl.item_id
        WHERE rl.character_id = 'player_default'
        ORDER BY rl.awarded_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    # ── notable notifications (level-up, achievements, etc.) ─────────────────
    # level_up payload stores {"new_level": N}; parse it for a richer message.
    notif_rows = db.execute(
        """
        SELECT event_type,
               CASE event_type
                   WHEN 'level_up'
                       THEN 'Level up! → Lv.' || COALESCE(
                               json_extract(payload, '$.new_level'), '?')
                   WHEN 'achievement_unlocked'  THEN 'Achievement unlocked'
                   WHEN 'place_unlock'          THEN 'New place unlocked'
                   WHEN 'place_level_up'        THEN 'Place levelled up'
                   WHEN 'streak_milestone'
                       THEN 'Streak milestone reached — Day ' || COALESCE(
                               json_extract(payload, '$.milestone'), '?')
                   ELSE event_type
               END AS description,
               created_at AS happened_at
        FROM pending_notifications
        WHERE character_id = 'player_default'
          AND event_type IN ('level_up', 'achievement_unlocked', 'place_unlock',
                             'place_level_up', 'streak_milestone')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    # Merge and sort newest-first
    all_events: list[dict] = (
        [dict(r) for r in chunk_rows]
        + [dict(r) for r in drop_rows]
        + [dict(r) for r in notif_rows]
    )
    all_events.sort(key=lambda e: e["happened_at"], reverse=True)
    return all_events[:limit]
