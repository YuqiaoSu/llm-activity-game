from __future__ import annotations
import hashlib
import random
from fastapi import APIRouter, Request, HTTPException, Query
from services.progression.weekly_challenges import get_week_start
from services.progression.xp import award_category_xp, get_total_xp, compute_level
from services.models.enums import Category
from services.reward_ledger.ledger import insert_level_up_notification
from datetime import date, datetime, timezone

router = APIRouter()

# Fixed fraction of each challenge's threshold assigned as each ghost's score.
# Grinder slightly exceeds threshold (shows "completed"), Focus is beatable
# mid-week, Casual is trivially easy — creating a natural difficulty spread.
_GHOST_FRACTIONS: dict[str, float] = {
    "ghost_grinder": 1.10,
    "ghost_focus":   0.75,
    "ghost_casual":  0.30,
}

_GHOST_NAMES: dict[str, str] = {
    "ghost_grinder": "XP Grinder",
    "ghost_focus":   "FocusBot",
    "ghost_casual":  "CasualMax",
}

# XP bonus awarded when a player claims a completed challenge reward
_CLAIM_REWARD_XP = 50
_DAILY_BONUS_MULTIPLIER = 2.0


def _get_daily_bonus_challenge_id(db) -> str | None:
    """Return today's challenge-of-the-day ID using a stable hash of the ISO date.

    Uses MD5 (not Python's hash()) so the result is reproducible across processes
    and restarts without a fixed random seed.
    """
    rows = db.execute(
        "SELECT challenge_id FROM weekly_challenges ORDER BY challenge_id"
    ).fetchall()
    if not rows:
        return None
    today_key = date.today().isoformat().encode()
    index = int(hashlib.md5(today_key).hexdigest(), 16) % len(rows)
    return rows[index]["challenge_id"]


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


@router.get("/daily-bonus")
def get_daily_bonus(request: Request) -> dict:
    """Return today's Challenge of the Day with its 2× XP multiplier.

    Selection is deterministic: stable hash of today's ISO date mod total challenges.
    Returns 404 if no challenges exist in the database.
    """
    db = request.app.state.db
    challenge_id = _get_daily_bonus_challenge_id(db)
    if challenge_id is None:
        raise HTTPException(status_code=404, detail="No challenges available")

    row = db.execute(
        "SELECT * FROM weekly_challenges WHERE challenge_id=?", (challenge_id,)
    ).fetchone()

    return {
        "challenge_id": row["challenge_id"],
        "name":         row["name"],
        "description":  row["description"],
        "category":     row["category"],
        "multiplier":   _DAILY_BONUS_MULTIPLIER,
        "date":         date.today().isoformat(),
    }


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

    is_daily_bonus = challenge_id == _get_daily_bonus_challenge_id(db)
    multiplier = _DAILY_BONUS_MULTIPLIER if is_daily_bonus else 1.0
    xp_awarded = int(_CLAIM_REWARD_XP * multiplier)

    prev_level = compute_level(get_total_xp(db, "player_default"))
    award_category_xp(db, "player_default", cat, xp_awarded)
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
    streak_info = _update_challenge_streak(db, week_start)
    db.commit()

    return {
        "challenge_id":      challenge_id,
        "xp_awarded":        xp_awarded,
        "category":          cat.value,
        "daily_bonus":       is_daily_bonus,
        "challenge_streak":  streak_info["current_streak"],
        "streak_bonus_item": streak_info["bonus_item"],
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


@router.get("/history")
def get_challenge_history(
    request: Request,
    weeks: int = Query(default=8, ge=1, le=52),
) -> list[dict]:
    """Return per-week challenge completion summaries for the last N weeks.

    Each entry: {week_start, completed_count, total_count, all_complete}
    Only weeks where the player attempted at least one challenge are included.
    Sorted newest-first.
    """
    db = request.app.state.db
    total_challenges = db.execute(
        "SELECT COUNT(*) AS n FROM weekly_challenges"
    ).fetchone()["n"]

    rows = db.execute(
        """
        SELECT
            p.week_start,
            COUNT(DISTINCT p.challenge_id)              AS attempted,
            SUM(CASE WHEN p.completed = 1 THEN 1 ELSE 0 END) AS completed_count
        FROM player_weekly_progress p
        WHERE p.player_id = 'player_default'
        GROUP BY p.week_start
        ORDER BY p.week_start DESC
        LIMIT ?
        """,
        (weeks,),
    ).fetchall()

    return [
        {
            "week_start":       row["week_start"],
            "completed_count":  int(row["completed_count"]),
            "total_count":      int(total_challenges),
            "all_complete":     int(row["completed_count"]) >= int(total_challenges) > 0,
        }
        for row in rows
    ]


@router.get("/leaderboard")
def get_challenge_leaderboard(
    request: Request,
    challenge_id: str = Query(..., description="Challenge to show leaderboard for"),
) -> dict:
    """Return a mini leaderboard for one weekly challenge.

    Compares the player's current progress against three ghost players whose
    scores are fixed fractions of the challenge threshold. Returns player score,
    all ghost entries with rank, and the player's own rank among all entries.
    """
    db = request.app.state.db
    week_start = get_week_start(datetime.now(timezone.utc))

    challenge_row = db.execute(
        "SELECT threshold FROM weekly_challenges WHERE challenge_id=?",
        (challenge_id,),
    ).fetchone()
    if challenge_row is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    threshold: int = int(challenge_row["threshold"])

    progress_row = db.execute(
        """
        SELECT COALESCE(progress, 0) AS progress
        FROM player_weekly_progress
        WHERE player_id='player_default' AND challenge_id=? AND week_start=?
        """,
        (challenge_id, week_start),
    ).fetchone()
    player_score = int(progress_row["progress"]) if progress_row else 0

    ghosts = [
        {
            "player_id":    gid,
            "name":         _GHOST_NAMES[gid],
            "score":        min(threshold, int(threshold * frac)),
            "rank":         0,
            "is_you":       False,
            "pct_complete": 0.0,
        }
        for gid, frac in _GHOST_FRACTIONS.items()
    ]

    # Rank all entries together (player + ghosts)
    all_scores = sorted(
        [player_score] + [g["score"] for g in ghosts], reverse=True
    )
    # Build score → rank (dense rank: ties share rank)
    unique_scores = sorted(set(all_scores), reverse=True)
    score_to_rank = {s: i + 1 for i, s in enumerate(unique_scores)}

    for g in ghosts:
        g["rank"] = score_to_rank[g["score"]]
        g["pct_complete"] = round(min(100.0, g["score"] / threshold * 100), 1) if threshold else 0.0

    your_rank = score_to_rank[player_score]
    player_pct = round(min(100.0, player_score / threshold * 100), 1) if threshold else 0.0

    return {
        "challenge_id":  challenge_id,
        "threshold":     threshold,
        "player_score":  player_score,
        "your_rank":     your_rank,
        "total_entries": 1 + len(ghosts),
        "player_pct_complete": player_pct,
        "is_you":        True,
        "ghosts":        ghosts,
    }


_STREAK_MILESTONES = [3, 5, 10]
_MILESTONE_RARITY  = {3: "RARE", 5: "EPIC", 10: "LEGENDARY"}


def _update_challenge_streak(db, week_start: str) -> dict:
    """Increment or reset the weekly challenge streak after a successful claim.

    Returns the updated streak state dict.
    """
    row = db.execute(
        "SELECT challenge_weekly_streak, challenge_longest_streak, last_challenge_week"
        " FROM streak_state WHERE player_id='default'"
    ).fetchone()
    current  = int(row["challenge_weekly_streak"])  if row else 0
    longest  = int(row["challenge_longest_streak"]) if row else 0
    last_wk  = str(row["last_challenge_week"]) if row and row["last_challenge_week"] else ""

    # week_start is YYYY-MM-DD (Monday); previous week's Monday is 7 days earlier
    from datetime import timedelta
    ws_date   = date.fromisoformat(week_start)
    prev_week = (ws_date - timedelta(weeks=1)).isoformat()
    this_week = ws_date.isoformat()

    if last_wk == this_week:
        # Already counted this week (second claim same week) — no change
        return {"current_streak": current, "longest_streak": longest,
                "last_challenge_week": last_wk, "bonus_item": None}

    new_streak = current + 1 if last_wk == prev_week else 1
    new_longest = max(longest, new_streak)

    db.execute(
        "UPDATE streak_state SET challenge_weekly_streak=?, challenge_longest_streak=?,"
        " last_challenge_week=? WHERE player_id='default'",
        (new_streak, new_longest, this_week),
    )

    # Milestone bonus item — insert a random item of the milestone rarity
    bonus_item = None
    if new_streak in _STREAK_MILESTONES:
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        rarity = _MILESTONE_RARITY[new_streak]
        chunk_id = f"challenge_streak_{new_streak}"
        already = db.execute(
            "SELECT 1 FROM reward_ledger WHERE chunk_id=? AND roll_n=0", (chunk_id,)
        ).fetchone()
        if not already:
            item_row = db.execute(
                "SELECT item_id FROM item_definitions"
                " WHERE json_extract(data, '$.rarity') = ? ORDER BY RANDOM() LIMIT 1",
                (rarity,),
            ).fetchone()
            if item_row:
                now_ts = _dt.now(_tz.utc).isoformat()
                ledger_id = str(_uuid.uuid4())
                instance_id = str(_uuid.uuid4())
                bonus_item = item_row["item_id"]
                db.execute(
                    "INSERT INTO reward_ledger (ledger_id, chunk_id, roll_n, item_id, character_id, awarded_at)"
                    " VALUES (?, ?, 0, ?, 'player_default', ?)",
                    (ledger_id, chunk_id, bonus_item, now_ts),
                )
                db.execute(
                    "INSERT INTO inventory (instance_id, character_id, item_id, acquired_at, source_chunk)"
                    " VALUES (?, 'player_default', ?, ?, ?)",
                    (instance_id, bonus_item, now_ts, chunk_id),
                )

    return {"current_streak": new_streak, "longest_streak": new_longest,
            "last_challenge_week": this_week, "bonus_item": bonus_item}


@router.get("/streak")
def get_challenge_streak(request: Request) -> dict:
    """Return the player's weekly challenge completion streak."""
    db = request.app.state.db
    row = db.execute(
        "SELECT challenge_weekly_streak, challenge_longest_streak, last_challenge_week"
        " FROM streak_state WHERE player_id='default'"
    ).fetchone()
    current = int(row["challenge_weekly_streak"])  if row else 0
    longest = int(row["challenge_longest_streak"]) if row else 0
    # Next milestone at or above current
    next_milestone = next((m for m in sorted(_STREAK_MILESTONES) if m > current), None)
    return {
        "current_streak":  current,
        "longest_streak":  longest,
        "next_milestone_at": next_milestone,
    }
