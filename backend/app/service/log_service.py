from datetime import datetime

from app.db.database import get_db


class LogService:
    def write(self, request_id: str, endpoint: str, status: str, latency_ms: int, error: str = "") -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO logs(request_id, endpoint, status, latency_ms, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, endpoint, status, latency_ms, error, datetime.utcnow().isoformat()),
            )

    def latest(self, limit: int = 100) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT request_id, endpoint, status, latency_ms, error, created_at
                FROM logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
