"""Daily goals — short-lived (24h) activity targets.

Goals are auto-generated from the suggestion engine once per UTC day.
Progress is updated alongside XP award in the sync agent.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from services.progression.suggestions import get_suggestions

# Milestone thresholds and the rarity each awards
_GOAL_STREAK_MILESTONES: list[tuple[int, str]] = [
    (30, "LEGENDARY"),
    (14, "EPIC"),
    (7,  "RARE"),
]

_DIFFICULTY_TIER_DAYS   = 3      # streak tiers: every 3 consecutive days
_DIFFICULTY_FACTOR      = 1.20   # 20% harder per tier
_MAX_TARGET_SEC         = 7200   # hard cap: 2 hours per goal


def compute_goal_difficulty_multiplier(goal_streak: int) -> float:
    """Return the target_sec multiplier for a given goal_streak.

    Tiers:  0–2 → 1.0×
            3–5 → 1.2×
            6–8 → 1.44×  etc., compounding every 3 days.

    The multiplier is applied when generating goals; the cap is enforced
    in ensure_daily_goals.
    """
    tiers = max(0, goal_streak // _DIFFICULTY_TIER_DAYS)
    return _DIFFICULTY_FACTOR ** tiers


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def ensure_daily_goals(conn: sqlite3.Connection, player_id: str = "player_default") -> None:
    """Create today's goals if none exist yet (idempotent — safe to call every poll).

    Picks up to 3 'gap' or 'diversify' suggestions and converts them into
    concrete goals. Streak-danger and challenge-nudge suggestions are skipped
    (they aren't category-specific activity goals).
    """
    today = _today()
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM daily_goals WHERE player_id=? AND date=?",
        (player_id, today),
    ).fetchone()["n"]
    if existing > 0:
        return

    # Read goal streak to scale difficulty
    streak_row = conn.execute(
        "SELECT goal_streak FROM streak_state WHERE player_id='default'"
    ).fetchone()
    goal_streak: int = int(streak_row["goal_streak"]) if streak_row else 0
    difficulty_mult = compute_goal_difficulty_multiplier(goal_streak)

    # Apply manual override scale from player_settings (default 1.0 = no change)
    settings_row = conn.execute(
        "SELECT goal_difficulty_scale FROM player_settings WHERE player_id='player_default'"
    ).fetchone()
    if settings_row and settings_row["goal_difficulty_scale"] is not None:
        difficulty_mult *= float(settings_row["goal_difficulty_scale"])

    suggestions = get_suggestions(conn, player_id)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for s in suggestions:
        if s["type"] not in ("gap", "diversify"):
            continue
        cat = s.get("category", "")
        if not cat:
            continue
        base_sec = s.get("target_min", 20) * 60
        target_sec = min(_MAX_TARGET_SEC, int(base_sec * difficulty_mult))
        conn.execute(
            """
            INSERT OR IGNORE INTO daily_goals
                (goal_id, player_id, date, category, target_sec, progress_sec, completed, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (str(uuid.uuid4()), player_id, today, cat, target_sec, now),
        )
        added += 1
        if added >= 3:
            break
    conn.commit()


def update_daily_goal_progress(
    conn: sqlite3.Connection,
    category: str,
    duration_sec: int,
    player_id: str = "player_default",
) -> None:
    """Add `duration_sec` to today's goal progress for `category`.

    Marks the goal as completed when progress_sec >= target_sec.
    No-op if no goal exists for this category today.
    """
    today = _today()
    conn.execute(
        """
        UPDATE daily_goals
        SET progress_sec = MIN(progress_sec + ?, target_sec + 1),
            completed = CASE WHEN progress_sec + ? >= target_sec THEN 1 ELSE completed END
        WHERE player_id=? AND date=? AND category=?
        """,
        (duration_sec, duration_sec, player_id, today, category),
    )
    # No commit here — caller (agent) commits in batch


def get_daily_goals(
    conn: sqlite3.Connection,
    player_id: str = "player_default",
) -> list[dict]:
    """Return today's goal rows as dicts, ordered by completion then category."""
    today = _today()
    rows = conn.execute(
        """
        SELECT goal_id, category, target_sec, progress_sec, completed, created_at
        FROM daily_goals
        WHERE player_id=? AND date=?
        ORDER BY completed ASC, category ASC
        """,
        (player_id, today),
    ).fetchall()
    result = []
    for r in rows:
        target = r["target_sec"]
        progress = r["progress_sec"]
        result.append({
            "goal_id": r["goal_id"],
            "category": r["category"],
            "target_min": round(target / 60),
            "progress_min": round(progress / 60, 1),
            "progress_pct": min(100, int(progress / target * 100)) if target > 0 else 0,
            "completed": bool(r["completed"]),
        })
    return result


def get_goal_streak_status(
    conn: sqlite3.Connection,
    player_id: str = "default",
) -> dict:
    """Return the current goal streak and info about the next milestone.

    Returns:
        goal_streak        — consecutive days all goals were completed
        next_milestone_at  — streak count at which the next reward fires (7/14/30)
        days_to_milestone  — how many more days until the next milestone
        milestones         — list of {days, rarity, reached} for each defined milestone
    """
    row = conn.execute(
        "SELECT goal_streak FROM streak_state WHERE player_id=?", (player_id,)
    ).fetchone()
    streak: int = int(row["goal_streak"]) if row else 0

    milestone_defs = [(7, "RARE"), (14, "EPIC"), (30, "LEGENDARY")]
    milestones_out = [
        {"days": d, "rarity": r, "reached": streak >= d}
        for d, r in milestone_defs
    ]

    next_milestone: int | None = None
    for days, _ in milestone_defs:
        if streak < days:
            next_milestone = days
            break

    return {
        "goal_streak":       streak,
        "next_milestone_at": next_milestone,
        "days_to_milestone": (next_milestone - streak) if next_milestone else None,
        "milestones":        milestones_out,
    }


def check_goal_streak_reward(
    conn: sqlite3.Connection,
    character_id: str = "player_default",
) -> bool:
    """Increment goal_streak if all today's goals are completed; award a drop on milestone.

    Returns True if a streak milestone was crossed and a drop was awarded.
    Idempotent: only processes once per calendar day via last_goal_streak_date.
    No-op when there are no goals today (avoids rewarding vacuous completion).
    """
    today = _today()
    streak_player_id = "default"   # streak_state always uses 'default' (see streak.py)
    goals_player_id = character_id  # daily_goals uses character_id

    # Ensure streak_state row exists
    conn.execute(
        "INSERT OR IGNORE INTO streak_state (player_id) VALUES (?)",
        (streak_player_id,),
    )
    conn.commit()

    state = conn.execute(
        "SELECT goal_streak, last_goal_streak_date FROM streak_state WHERE player_id=?",
        (streak_player_id,),
    ).fetchone()
    if state is None:
        return False

    # Already processed today
    if state["last_goal_streak_date"] == today:
        return False

    # Check today's goals: must have at least one and all must be completed
    totals = conn.execute(
        "SELECT COUNT(*) AS total, SUM(completed) AS done FROM daily_goals WHERE player_id=? AND date=?",
        (goals_player_id, today),
    ).fetchone()
    total: int = totals["total"] or 0
    done: int = int(totals["done"] or 0)

    if total == 0 or done < total:
        # Not all completed — reset streak, stamp date so we don't re-check today
        conn.execute(
            "UPDATE streak_state SET goal_streak=0, last_goal_streak_date=? WHERE player_id=?",
            (today, streak_player_id),
        )
        conn.commit()
        return False

    # All goals met — increment streak
    new_streak: int = (state["goal_streak"] or 0) + 1
    conn.execute(
        "UPDATE streak_state SET goal_streak=?, last_goal_streak_date=? WHERE player_id=?",
        (new_streak, today, streak_player_id),
    )
    conn.commit()

    # Check for milestone reward
    for threshold, rarity in _GOAL_STREAK_MILESTONES:
        if new_streak % threshold != 0:
            continue
        # Idempotent: use milestone + date as synthetic chunk_id
        synthetic_chunk_id = f"goal_streak_{threshold}_{today}"
        already = conn.execute(
            "SELECT 1 FROM reward_ledger WHERE chunk_id=? AND roll_n=0",
            (synthetic_chunk_id,),
        ).fetchone()
        if already:
            break  # already awarded this milestone today

        # Pick a random item at the milestone rarity
        candidates = conn.execute(
            """
            SELECT item_id FROM item_definitions
            WHERE json_extract(data, '$.rarity') = ?
            """,
            (rarity,),
        ).fetchall()
        if not candidates:
            break

        import random
        winner_id: str = random.choice(candidates)["item_id"]
        now = datetime.now(timezone.utc).isoformat()

        # Insert into inventory
        new_iid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_iid, character_id, winner_id, now, synthetic_chunk_id),
        )
        # Stamp reward_ledger to prevent duplicates
        conn.execute(
            "INSERT OR IGNORE INTO reward_ledger "
            "(ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at) "
            "VALUES (?, ?, 0, ?, ?, ?)",
            (str(uuid.uuid4()), synthetic_chunk_id, winner_id, character_id, now),
        )
        # Stamp collection_log
        conn.execute(
            "INSERT OR IGNORE INTO collection_log (player_id, item_id, first_seen_at) "
            "VALUES (?, ?, ?)",
            (character_id, winner_id, now),
        )
        # Notify player
        from services.reward_ledger.ledger import _insert_notification
        _insert_notification(conn, character_id, "item_drop", {
            "item_id": winner_id,
            "rarity": rarity,
            "source": f"goal_streak_{threshold}",
        })
        conn.commit()
        return True
        break  # only award the highest matching milestone

    return False
