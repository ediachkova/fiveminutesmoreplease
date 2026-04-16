mport sqlite3
import os
from datetime import datetime
import pytz
from config import TIMEZONE

DB_PATH = os.environ.get("DB_PATH", "planner.db")


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        db_dir = os.path.dirname(self.path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    day         TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    start_time  TEXT NOT NULL,
                    end_time    TEXT NOT NULL,
                    status      TEXT DEFAULT 'pending',
                    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

    def ensure_user(self, user_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,)
            )

    def add_task(self, user_id: int, day: str, name: str,
                 start_time: str, end_time: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO tasks (user_id, day, name, start_time, end_time)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, day, name, start_time, end_time)
            )
            return cur.lastrowid

    def get_task(self, task_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_task_status(self, task_id: int, status: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status, task_id)
            )

    def get_upcoming_tasks(self, user_id: int) -> list[dict]:
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE user_id = ?
                   AND day >= ?
                   ORDER BY day, start_time""",
                (user_id, today)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks WHERE user_id = ? GROUP BY status",
                (user_id,)
            ).fetchall()
        stats = {"total": 0, "done": 0, "snoozed": 0, "pending": 0, "in_progress": 0}
        for row in rows:
            s, cnt = row["status"], row["cnt"]
            stats["total"] += cnt
            if s == "done":
                stats["done"] += cnt
            elif s in ("snoozed",):
                stats["snoozed"] += cnt
            elif s in ("pending", "reminded"):
                stats["pending"] += cnt
            elif s == "in_progress":
                stats["in_progress"] += cnt
        return stats

