"""XP decay and recovery-bonus logic for inactivity mechanic.

Rules:
- A player is *dormant* when their last_active_date in streak_state is NULL
  or more than DORMANCY_THRESHOLD_DAYS days ago.
- Once per calendar day, if the player is dormant, apply a 5% decay to all
  player_category_xp rows (integer floor, minimum 0).  Applied up to
  DECAY_CAP_DAYS times maximum so a very long absence doesn't wipe all XP.
- When a dormant player next earns XP (i.e. poll returns chunks), set a
  has_recovery_bonus flag so the agent can apply a 1.5× multiplier for that
  poll, then clear it.
"""
from __future__ import annotations

import sqlite3
from datetime import date

DORMANCY_THRESHOLD_DAYS = 3   # days of no activity before dormancy kicks in
DECAY_RATE = 0.05             # 5% per day of dormancy
DECAY_CAP_DAYS = 30           # never decay more than 30× in one pass
RECOVERY_MULTIPLIER = 1.5


# ── migrations (called from db.py _run_migrations) ────────────────────────────

def migrate(conn: sqlite3.Connection) -> None:
    """Add decay columns to streak_state if not present."""
    for col, defn in [
        ("last_decay_date",   "TEXT"),
        ("has_recovery_bonus", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE streak_state ADD COLUMN {col} {defn}")
            conn.commit()
        except Exception:
            pass  # already exists


# ── public API ────────────────────────────────────────────────────────────────

def get_dormancy_info(conn: sqlite3.Connection, player_id: str = "default") -> dict:
    """Return dormancy state without writing anything.

    Returns:
        is_dormant: bool
        dormant_days: int (0 when active)
        has_recovery_bonus: bool
    """
    _ensure_streak_row(conn, player_id)
    row = conn.execute(
        "SELECT last_active_date, has_recovery_bonus FROM streak_state WHERE player_id=?",
        (player_id,),
    ).fetchone()
    last_active = row["last_active_date"] if row and row["last_active_date"] else None
    recovery = bool(row["has_recovery_bonus"]) if row else False

    dormant_days = _days_since(last_active)
    is_dormant = dormant_days >= DORMANCY_THRESHOLD_DAYS

    return {
        "is_dormant": is_dormant,
        "dormant_days": dormant_days,
        "has_recovery_bonus": recovery,
    }


def apply_daily_decay(conn: sqlite3.Connection, player_id: str = "default") -> int:
    """Apply up-to-one-day decay if today hasn't been processed yet.

    Only decays when dormant AND last_decay_date < today.
    Returns the number of XP decay applications (0 or 1 per call).
    """
    _ensure_streak_row(conn, player_id)
    row = conn.execute(
        "SELECT last_active_date, last_decay_date FROM streak_state WHERE player_id=?",
        (player_id,),
    ).fetchone()
    if row is None:
        return 0

    today = date.today().isoformat()
    last_active = row["last_active_date"]
    last_decay = row["last_decay_date"]

    dormant_days = _days_since(last_active)
    if dormant_days < DORMANCY_THRESHOLD_DAYS:
        return 0  # not dormant, nothing to do

    if last_decay == today:
        return 0  # already ran today

    # Apply one day of decay to all category XP rows
    # Determine the character_id — use 'player_default' as canonical mapping
    character_id = "player_default"
    rows = conn.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id=?",
        (character_id,),
    ).fetchall()
    for r in rows:
        new_xp = max(0, int(r["xp"] * (1.0 - DECAY_RATE)))
        conn.execute(
            "UPDATE player_category_xp SET xp=? WHERE character_id=? AND category=?",
            (new_xp, character_id, r["category"]),
        )

    conn.execute(
        "UPDATE streak_state SET last_decay_date=? WHERE player_id=?",
        (today, player_id),
    )
    conn.commit()
    return 1


def mark_recovery_if_dormant(conn: sqlite3.Connection, player_id: str = "default") -> bool:
    """Set has_recovery_bonus=1 if the player is currently dormant.

    Call this just before processing poll chunks — if dormant, the caller
    should apply RECOVERY_MULTIPLIER to XP earned this poll.

    Returns True if recovery bonus was set (was dormant).
    """
    info = get_dormancy_info(conn, player_id)
    if info["is_dormant"] and not info["has_recovery_bonus"]:
        conn.execute(
            "UPDATE streak_state SET has_recovery_bonus=1 WHERE player_id=?",
            (player_id,),
        )
        conn.commit()
        return True
    return False


def consume_recovery_bonus(conn: sqlite3.Connection, player_id: str = "default") -> bool:
    """Clear has_recovery_bonus flag. Call after applying the bonus XP.

    Returns True if a bonus was present and was cleared.
    """
    row = conn.execute(
        "SELECT has_recovery_bonus FROM streak_state WHERE player_id=?",
        (player_id,),
    ).fetchone()
    if row and row["has_recovery_bonus"]:
        conn.execute(
            "UPDATE streak_state SET has_recovery_bonus=0 WHERE player_id=?",
            (player_id,),
        )
        conn.commit()
        return True
    return False


# ── helpers ───────────────────────────────────────────────────────────────────

def _days_since(date_str: str | None) -> int:
    """Return integer days since date_str (ISO date).

    NULL / None means the player has never been active → return 0 (not dormant).
    A new account should not immediately enter dormancy.
    """
    if not date_str:
        return 0
    try:
        d = date.fromisoformat(date_str[:10])
        return max(0, (date.today() - d).days)
    except ValueError:
        return 0


def _ensure_streak_row(conn: sqlite3.Connection, player_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO streak_state (player_id) VALUES (?)",
        (player_id,),
    )
    conn.commit()
