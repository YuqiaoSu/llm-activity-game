import sqlite3
from services.models.enums import Category
from services.progression.config import XP_PER_LEVEL, EVOLUTION_STAGES, XP_PER_MINUTE
from services.contracts.chunk import Chunk


def compute_level(total_xp: int) -> int:
    """Return the level corresponding to total_xp (1-indexed)."""
    level = 1
    for i, threshold in enumerate(XP_PER_LEVEL):
        if total_xp >= threshold:
            level = i + 1
    return level


def compute_level_xp_range(level: int) -> tuple[int, int | None]:
    """Return (start_xp, end_xp) for the given level.

    start_xp: cumulative XP at which this level begins.
    end_xp: cumulative XP required to reach the next level,
            or None if level is at or beyond the defined maximum.
    """
    start = XP_PER_LEVEL[level - 1] if level - 1 < len(XP_PER_LEVEL) else XP_PER_LEVEL[-1]
    end: int | None = XP_PER_LEVEL[level] if level < len(XP_PER_LEVEL) else None
    return start, end


def compute_evolution_stage(level: int) -> int:
    """Return evolution stage for a given level."""
    for stage, (min_lvl, max_lvl) in sorted(EVOLUTION_STAGES.items(), reverse=True):
        if level >= min_lvl:
            return stage
    return 0


def xp_for_chunk(chunk: Chunk) -> int:
    """XP to award for one processed chunk: 1 XP per minute, minimum 1."""
    return max(1, chunk.duration_sec // 60 * XP_PER_MINUTE)


def award_category_xp(
    conn: sqlite3.Connection,
    character_id: str,
    category: Category,
    xp: int,
) -> None:
    """Upsert XP into player_category_xp. Safe to call multiple times."""
    conn.execute(
        """
        INSERT INTO player_category_xp (character_id, category, xp)
        VALUES (?, ?, ?)
        ON CONFLICT (character_id, category) DO UPDATE SET xp = xp + excluded.xp
        """,
        (character_id, str(category.value), xp),
    )


def get_total_xp(conn: sqlite3.Connection, character_id: str) -> int:
    """Sum all category XP rows for a character."""
    row = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) as total FROM player_category_xp WHERE character_id=?",
        (character_id,),
    ).fetchone()
    return int(row[0])


def deduct_total_xp(conn: sqlite3.Connection, character_id: str, amount: int) -> None:
    """Deduct `amount` XP proportionally across all category rows.

    Deducts from categories in descending XP order until `amount` is consumed.
    Raises ValueError if the player's total XP is less than `amount`.
    Caller is responsible for commit.
    """
    total = get_total_xp(conn, character_id)
    if total < amount:
        raise ValueError(f"Insufficient XP: have {total}, need {amount}")
    remaining = amount
    rows = conn.execute(
        "SELECT category, xp FROM player_category_xp WHERE character_id=? ORDER BY xp DESC",
        (character_id,),
    ).fetchall()
    for row in rows:
        if remaining <= 0:
            break
        deduct = min(row["xp"], remaining)
        conn.execute(
            "UPDATE player_category_xp SET xp = xp - ? WHERE character_id=? AND category=?",
            (deduct, character_id, row["category"]),
        )
        remaining -= deduct
