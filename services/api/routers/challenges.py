from __future__ import annotations
import random
from fastapi import APIRouter, Request, HTTPException
from services.progression.weekly_challenges import get_week_start
from services.progression.xp import award_category_xp, get_total_xp, compute_level
from services.models.enums import Category
from services.reward_ledger.ledger import insert_level_up_notification
from datetime import datetime, timezone

router = APIRouter()

# XP bonus awarded when a player claims a completed challenge reward
_CLAIM_REWARD_XP = 50


@router.get("")
def get_challenges(request: Request) -> list[dict]:
    """Return all weekly challenge definitions with current-week progress.

    Each entry includes the challenge definition fields plus the player's
    progress and completion status for the running ISO week.
    """
    db = request.app.state.db
    week_start = get_week_start(datetime.now(timezone.utc))

    rows = db.execute(
        """
        SELECT
            c.challenge_id,
            c.name,
            c.description,
            c.category,
            c.metric,
            c.threshold,
            COALESCE(p.progress, 0)     AS progress,
            COALESCE(p.completed, 0)    AS completed,
            COALESCE(p.reward_given, 0) AS reward_given,
            COALESCE(p.week_start, ?)   AS week_start
        FROM weekly_challenges c
        LEFT JOIN player_weekly_progress p
            ON p.challenge_id = c.challenge_id
            AND p.player_id   = 'player_default'
            AND p.week_start  = ?
        ORDER BY c.challenge_id
        """,
        (week_start, week_start),
    ).fetchall()

    return [
        {
            "challenge_id": row["challenge_id"],
            "name":         row["name"],
            "description":  row["description"],
            "category":     row["category"],
            "metric":       row["metric"],
            "threshold":    row["threshold"],
            "progress":     row["progress"],
            "completed":    bool(row["completed"]),
            "reward_given": bool(row["reward_given"]),
            "week_start":   row["week_start"],
        }
        for row in rows
    ]


@router.post("/{challenge_id}/claim")
def claim_challenge(challenge_id: str, request: Request) -> dict:
    """Claim the XP reward for a completed weekly challenge.

    Returns 404 if the challenge doesn't exist.
    Returns 409 if the challenge is not completed or reward already given.
    Awards `_CLAIM_REWARD_XP` bonus XP in the challenge's category on first claim.
    """
    db = request.app.state.db
    week_start = get_week_start(datetime.now(timezone.utc))

    row = db.execute(
        """
        SELECT p.completed, p.reward_given, c.category, c.name
        FROM player_weekly_progress p
        JOIN weekly_challenges c ON c.challenge_id = p.challenge_id
        WHERE p.player_id = 'player_default'
          AND p.challenge_id = ?
          AND p.week_start   = ?
        """,
        (challenge_id, week_start),
    ).fetchone()

    if row is None:
        # Check if challenge exists at all
        exists = db.execute(
            "SELECT 1 FROM weekly_challenges WHERE challenge_id=?", (challenge_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        raise HTTPException(status_code=409, detail="Challenge not completed yet")

    if not row["completed"]:
        raise HTTPException(status_code=409, detail="Challenge not completed yet")
    if row["reward_given"]:
        raise HTTPException(status_code=409, detail="Reward already claimed")

    # Award bonus XP (use SPECIAL if category is ALL or unknown)
    cat_str: str = row["category"]
    try:
        cat = Category(cat_str)
    except ValueError:
        cat = Category.SPECIAL

    prev_level = compute_level(get_total_xp(db, "player_default"))
    award_category_xp(db, "player_default", cat, _CLAIM_REWARD_XP)
    new_level = compute_level(get_total_xp(db, "player_default"))
    if new_level > prev_level:
        for lvl in range(prev_level + 1, new_level + 1):
            insert_level_up_notification(db, "player_default", lvl)

    db.execute(
        """
        UPDATE player_weekly_progress
        SET reward_given = 1
        WHERE player_id = 'player_default' AND challenge_id = ? AND week_start = ?
        """,
        (challenge_id, week_start),
    )
    db.commit()

    return {
        "challenge_id": challenge_id,
        "xp_awarded": _CLAIM_REWARD_XP,
        "category": cat.value,
    }


@router.post("/reroll")
def reroll_challenge(request: Request) -> dict:
    """Replace one random uncompleted challenge this week with a new random challenge.

    Each player may reroll once per ISO week.
    Returns 409 if reroll already used this week or no uncompleted challenges exist.
    Returns the new challenge definition.
    """
    db = request.app.state.db
    week_start = get_week_start(datetime.now(timezone.utc))

    # Check if reroll already used
    used = db.execute(
        "SELECT 1 FROM weekly_reroll_state WHERE player_id='player_default' AND week_start=?",
        (week_start,),
    ).fetchone()
    if used:
        raise HTTPException(status_code=409, detail="Reroll already used this week")

    # Find all uncompleted challenges for this week
    uncompleted = db.execute(
        """
        SELECT c.challenge_id
        FROM weekly_challenges c
        LEFT JOIN player_weekly_progress p
            ON p.challenge_id = c.challenge_id
            AND p.player_id   = 'player_default'
            AND p.week_start  = ?
        WHERE COALESCE(p.completed, 0) = 0
        """,
        (week_start,),
    ).fetchall()

    if not uncompleted:
        raise HTTPException(status_code=409, detail="All challenges already completed")

    # Pick a random one to replace
    target_id: str = random.choice(uncompleted)["challenge_id"]

    # Zero out its progress for this week (or delete the row)
    db.execute(
        """
        DELETE FROM player_weekly_progress
        WHERE player_id='player_default' AND challenge_id=? AND week_start=?
        """,
        (target_id, week_start),
    )

    # Record reroll usage
    db.execute(
        """
        INSERT INTO weekly_reroll_state (player_id, week_start, rerolled_challenge_id, rerolled_at)
        VALUES ('player_default', ?, ?, ?)
        """,
        (week_start, target_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()

    # Return the challenge that was rerolled (fresh, progress = 0)
    row = db.execute(
        "SELECT * FROM weekly_challenges WHERE challenge_id=?", (target_id,)
    ).fetchone()

    return {
        "rerolled_challenge_id": target_id,
        "name":        row["name"],
        "description": row["description"],
        "category":    row["category"],
        "metric":      row["metric"],
        "threshold":   row["threshold"],
        "progress":    0,
        "completed":   False,
        "week_start":  week_start,
    }
