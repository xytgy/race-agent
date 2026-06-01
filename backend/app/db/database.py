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
              tags TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT '',
              project_id TEXT NOT NULL DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS task_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER NOT NULL,
              document_id TEXT,
              chunk_id TEXT,
              source_file TEXT,
              page_no INTEGER,
              section TEXT,
              score REAL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (task_id) REFERENCES tasks(id)
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
        _migrate_documents_table(conn)
        _migrate_tasks_table(conn)


def _migrate_documents_table(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    migrations = [
        ("tags", "TEXT NOT NULL DEFAULT ''"),
        ("summary", "TEXT NOT NULL DEFAULT ''"),
        ("project_id", "TEXT NOT NULL DEFAULT ''"),
    ]
    for col, definition in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {definition}")


def _migrate_tasks_table(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    migrations = [
        ("conversation_id", "TEXT"),
        ("assignee", "TEXT DEFAULT ''"),
        ("deadline", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ]
    for col, definition in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {definition}")
