import sqlite3
import random
from pathlib import Path
from datetime import datetime, timedelta

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DB_DIR / "conversations.db"

MAX_TURNS = 20
MAX_MESSAGE_LENGTH = 2000

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=10000")
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_ts   TEXT NOT NULL,
            channel_id  TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_thread ON conversations(channel_id, thread_ts);
        CREATE INDEX IF NOT EXISTS idx_created ON conversations(created_at);
    """)
    conn.commit()


def save_message(channel_id: str, thread_ts: str, role: str, content: str) -> None:
    truncated = content[:MAX_MESSAGE_LENGTH] if len(content) > MAX_MESSAGE_LENGTH else content
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO conversations (thread_ts, channel_id, role, content) VALUES (?, ?, ?, ?)",
            (thread_ts, channel_id, role, truncated),
        )
        conn.commit()
    except Exception:
        pass  # DB 실패해도 봇 동작에 영향 없음


def get_thread_history(channel_id: str, thread_ts: str) -> list[dict]:
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT role, content FROM conversations
            WHERE channel_id = ? AND thread_ts = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (channel_id, thread_ts, MAX_TURNS * 2),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
    except Exception:
        return []  # DB 실패 시 맥락 없이 진행


def cleanup_old_conversations(days: int = 7) -> int:
    try:
        conn = _get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = conn.execute("DELETE FROM conversations WHERE created_at < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount
    except Exception:
        return 0


def maybe_cleanup() -> None:
    if random.random() < 0.05:
        cleanup_old_conversations()
