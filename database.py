import os
from datetime import datetime
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import pytz

from config import TIMEZONE

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class Database:
    def __init__(self, url: str = DATABASE_URL):
        self.url = url

    @contextmanager
    def _conn(self):
        conn = psycopg2.connect(self.url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS tasks (
                        id          SERIAL PRIMARY KEY,
                        user_id     BIGINT NOT NULL REFERENCES users(user_id),
                        day         TEXT NOT NULL,
                        name        TEXT NOT NULL,
                        start_time  TEXT NOT NULL,
                        end_time    TEXT NOT NULL,
                        status      TEXT DEFAULT 'pending',
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

    def ensure_user(self, user_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user_id,)
                )

    def add_task(self, user_id: int, day: str, name: str,
                 start_time: str, end_time: str) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tasks (user_id, day, name, start_time, end_time)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (user_id, day, name, start_time, end_time)
                )
                return cur.fetchone()["id"]

    def get_task(self, task_id: int) -> dict | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def update_task_status(self, task_id: int, status: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tasks SET status = %s WHERE id = %s",
                    (status, task_id)
                )

    def get_upcoming_tasks(self, user_id: int) -> list[dict]:
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM tasks
                       WHERE user_id = %s AND day >= %s
                       ORDER BY day, start_time""",
                    (user_id, today)
                )
                return [dict(r) for r in cur.fetchall()]

    def get_stats(self, user_id: int) -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, COUNT(*) as cnt FROM tasks WHERE user_id = %s GROUP BY status",
                    (user_id,)
                )
                rows = cur.fetchall()
        stats = {"total": 0, "done": 0, "snoozed": 0, "pending": 0, "in_progress": 0}
        for row in rows:
            s, cnt = row["status"], int(row["cnt"])
            stats["total"] += cnt
            if s == "done":
                stats["done"] += cnt
            elif s == "snoozed":
                stats["snoozed"] += cnt
            elif s in ("pending", "reminded"):
                stats["pending"] += cnt
            elif s == "in_progress":
                stats["in_progress"] += cnt
        return stats
