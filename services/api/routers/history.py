from fastapi import APIRouter, Request

router = APIRouter()

_LIMIT = 50


@router.get("")
def get_history(request: Request) -> list[dict]:
    db = request.app.state.db

    rows = db.execute(
        """
        SELECT log_id, chunk_id, category, xp_awarded, duration_sec, processed_at
        FROM chunk_log
        ORDER BY processed_at DESC
        LIMIT ?
        """,
        (_LIMIT,),
    ).fetchall()

    result: list[dict] = []
    for row in rows:
        drop_count: int = db.execute(
            "SELECT COUNT(*) FROM reward_ledger WHERE chunk_id = ?",
            (row["chunk_id"],),
        ).fetchone()[0]
        result.append({
            "chunk_id": row["chunk_id"],
            "category": row["category"],
            "xp_awarded": row["xp_awarded"],
            "duration_sec": row["duration_sec"],
            "processed_at": row["processed_at"],
            "drops": drop_count,
        })

    return result
