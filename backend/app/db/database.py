import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config.settings import settings

sqlite_dir = Path(settings.data_dir) / "sqlite"
sqlite_dir.mkdir(parents=True, exist_ok=True)
db_path = sqlite_dir / "raceagent.db"


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row


@contextmanager
def get_db():
    conn = sqlite3.connect(db_path, timeout=10)
    _configure_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Legacy compat - prefer get_db() context manager."""
    conn = sqlite3.connect(db_path, timeout=10)
    _configure_connection(conn)
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY,
              file_name TEXT NOT NULL,
              file_path TEXT NOT NULL,
              file_type TEXT NOT NULL,
              parse_status TEXT NOT NULL,
              chunk_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              task_type TEXT NOT NULL,
              priority TEXT NOT NULL,
              difficulty TEXT NOT NULL,
              estimated_hours REAL NOT NULL,
              dependency TEXT,
              deliverable TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              status TEXT NOT NULL,
              latency_ms INTEGER NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              conversation_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            """
        )
