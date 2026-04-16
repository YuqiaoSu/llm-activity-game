"""Rule-based smart quest suggestion engine.

Generates short-term activity suggestions for the player based on:
- Recent category XP distribution (last 7 days)
- Streak state (warn if today has no activity yet)
- Weekly challenge progress (nudge toward incomplete challenges)
- All-time category gaps (categories never or rarely touched)

No LLM required — all rules are deterministic and computed from SQLite.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, date, timedelta
from services.models.enums import Category

_WINDOW_DAYS = 7          # look-back window for "recent" activity
_GAP_THRESHOLD_SEC = 0    # if a category has 0 seconds in the window it's a "gap"
_TARGET_MINUTES = {       # suggested target per session (minutes) per category
    "WORK":    45,
    "GAME":    30,
    "VIDEO":   30,
    "SOCIAL":  20,
    "EXPLORE": 30,
    "SLEEP":   480,
    "SPECIAL": 20,
}
_MAX_SUGGESTIONS = 5


def get_suggestions(conn: sqlite3.Connection, character_id: str = "player_default") -> list[dict]:
    """Return up to _MAX_SUGGESTIONS personalised activity suggestions.

    Each suggestion dict has:
      type        : str  — "streak_danger" | "gap" | "challenge_nudge" | "diversify"
      category    : str  — Category value or "" for non-category suggestions
      text        : str  — Human-readable suggestion sentence
      target_min  : int  — Suggested session length in minutes (0 if not applicable)
      priority    : int  — Lower = more important (used for sorting before trimming)
    """
    suggestions: list[dict] = []
    today_utc = datetime.now(timezone.utc).date()

    # ── 1. Streak danger ────────────────────────────────────────────────────
    streak_row = conn.execute(
        "SELECT current_streak, last_active_date FROM streak_state WHERE player_id='default'"
    ).fetchone()
    if streak_row:
        last_active = streak_row["last_active_date"]
        streak = streak_row["current_streak"]
        if streak > 0 and last_active != str(today_utc):
            suggestions.append({
                "type": "streak_danger",
                "category": "",
                "text": (
                    f"Your {streak}-day streak is at risk! "
                    "Do any activity today to keep it alive."
                ),
                "target_min": 15,
                "priority": 0,
            })

    # ── 2. Recent activity per category (last WINDOW_DAYS days) ─────────────
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """
        SELECT category, SUM(duration_sec) AS total_sec
        FROM chunk_log
        WHERE processed_at >= ?
        GROUP BY category
        """,
        (cutoff,),
    ).fetchall()
    recent_sec: dict[str, int] = {r["category"]: r["total_sec"] for r in rows}

    # ── 3. Gap suggestions (categories with no recent activity) ─────────────
    all_categories = [c.value for c in Category]
    gap_cats: list[str] = [
        cat for cat in all_categories
        if recent_sec.get(cat, 0) <= _GAP_THRESHOLD_SEC
    ]
    # Sort: categories with all-time XP come first (more relevant to the player)
    all_xp_rows = conn.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id=?",
        (character_id,),
    ).fetchall()
    all_xp: dict[str, int] = {r["category"]: r["xp"] for r in all_xp_rows}

    gap_cats_with_xp = sorted(
        [c for c in gap_cats if all_xp.get(c, 0) > 0],
        key=lambda c: all_xp.get(c, 0),
        reverse=True,
    )
    gap_cats_without_xp = [c for c in gap_cats if all_xp.get(c, 0) == 0]

    for cat in (gap_cats_with_xp + gap_cats_without_xp)[:2]:
        target = _TARGET_MINUTES.get(cat, 30)
        if all_xp.get(cat, 0) > 0:
            text = (
                f"You haven't done any {cat.capitalize()} activity in the last "
                f"{_WINDOW_DAYS} days. Try {target} minutes today!"
            )
        else:
            text = (
                f"You've never logged {cat.capitalize()} activity. "
                f"Give it a try for {target} minutes — you might earn a new item!"
            )
        suggestions.append({
            "type": "gap",
            "category": cat,
            "text": text,
            "target_min": target,
            "priority": 1 if all_xp.get(cat, 0) > 0 else 2,
        })

    # ── 4. Challenge nudge (closest incomplete challenge to completion) ──────
    challenge_row = conn.execute(
        """
        SELECT c.challenge_id, c.description, c.threshold,
               COALESCE(p.progress, 0) AS progress
        FROM weekly_challenges c
        LEFT JOIN player_weekly_progress p
            ON c.challenge_id = p.challenge_id AND p.player_id = 'default'
                AND p.week_start = date('now', 'weekday 0', '-7 days')
        WHERE COALESCE(p.completed, 0) = 0
          AND COALESCE(p.reward_given, 0) = 0
        ORDER BY (CAST(COALESCE(p.progress, 0) AS REAL) / c.threshold) DESC
        LIMIT 1
        """,
    ).fetchone()
    if challenge_row:
        cur = challenge_row["progress"]
        tgt = challenge_row["threshold"]
        pct = int(cur / tgt * 100) if tgt > 0 else 0
        suggestions.append({
            "type": "challenge_nudge",
            "category": "",
            "text": (
                f"Weekly challenge: \"{challenge_row['description']}\" — "
                f"{pct}% complete ({cur}/{tgt}). Keep going!"
            ),
            "target_min": 20,
            "priority": 1,
        })

    # ── 5. Diversify (if player heavily concentrates in one category) ────────
    if len(recent_sec) >= 2:
        total_recent = sum(recent_sec.values()) or 1
        dominant = max(recent_sec, key=lambda k: recent_sec[k])
        dominant_pct = recent_sec[dominant] / total_recent
        if dominant_pct > 0.70:
            # Recommend a non-dominant category they do have history with
            other_cats = sorted(
                [c for c in all_categories if c != dominant and all_xp.get(c, 0) > 0],
                key=lambda c: recent_sec.get(c, 0),
            )
            if other_cats:
                other = other_cats[0]
                target = _TARGET_MINUTES.get(other, 30)
                suggestions.append({
                    "type": "diversify",
                    "category": other,
                    "text": (
                        f"You've been spending {int(dominant_pct * 100)}% of your time on "
                        f"{dominant.capitalize()} lately. Try {target} minutes of "
                        f"{other.capitalize()} to diversify!"
                    ),
                    "target_min": target,
                    "priority": 3,
                })

    # ── Sort and trim ────────────────────────────────────────────────────────
    suggestions.sort(key=lambda s: s["priority"])
    return suggestions[:_MAX_SUGGESTIONS]
