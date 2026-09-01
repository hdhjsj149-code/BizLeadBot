"""
database.py

SQLite data-access layer for BizLeadBot.

Design notes:
- This module is the ONLY place that should contain raw SQL.
- bot.py should call functions here, never touch sqlite3 directly.
- Users are deactivated (is_active = 0) rather than deleted, so history
  and future quota/plan data is preserved.
- The schema intentionally leaves room for future plan/quota columns
  (see the 'plan' column) without requiring a rewrite.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import config

# SQLite + multithreaded access (bot handlers can run in a thread pool) needs
# a lock, since the default sqlite3 connection isn't safe to share across
# threads without care.
_db_lock = threading.Lock()


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


@contextmanager
def _get_connection():
    _ensure_parent_dir(config.DATABASE_PATH)
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        with _db_lock:
            yield conn
            conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist. Safe to call every startup."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username    TEXT,
                is_active   INTEGER NOT NULL DEFAULT 0,
                plan        TEXT NOT NULL DEFAULT 'free',
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                url         TEXT NOT NULL,
                pages       INTEGER NOT NULL,
                results     INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- User management ----------------------------------------------------------

def get_user(telegram_id: int) -> Optional[sqlite3.Row]:
    with _get_connection() as conn:
        cur = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cur.fetchone()


def is_user_active(telegram_id: int) -> bool:
    user = get_user(telegram_id)
    return bool(user and user["is_active"] == 1)


def is_admin(telegram_id: int) -> bool:
    return config.ADMIN_ID != 0 and telegram_id == config.ADMIN_ID


def register_or_touch_user(telegram_id: int, username: Optional[str]) -> None:
    """
    Ensure a user row exists for anyone who interacts with the bot,
    even if inactive. This lets the admin see "who has tried the bot"
    and simply flip is_active later.
    """
    with _get_connection() as conn:
        existing = conn.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (telegram_id, username, is_active, plan, created_at) "
                "VALUES (?, ?, 0, 'free', ?)",
                (telegram_id, username or "", _now()),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ? WHERE telegram_id = ?",
                (username or "", telegram_id),
            )


def add_user(telegram_id: int, username: Optional[str] = None) -> bool:
    """Whitelist (activate) a user. Creates the row if needed. Returns True on success."""
    with _get_connection() as conn:
        existing = conn.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO users (telegram_id, username, is_active, plan, created_at) "
                "VALUES (?, ?, 1, 'free', ?)",
                (telegram_id, username or "", _now()),
            )
        else:
            conn.execute(
                "UPDATE users SET is_active = 1 WHERE telegram_id = ?", (telegram_id,)
            )
    return True


def remove_user(telegram_id: int) -> bool:
    """Deactivate a user (soft delete). Returns True if a row existed."""
    with _get_connection() as conn:
        existing = conn.execute(
            "SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing is None:
            return False
        conn.execute(
            "UPDATE users SET is_active = 0 WHERE telegram_id = ?", (telegram_id,)
        )
    return True


def list_users(limit: int = 50) -> list:
    with _get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()


def count_users() -> dict:
    with _get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE is_active = 1"
        ).fetchone()["c"]
        return {"total": total, "active": active}


# --- Job tracking (foundation for future history / quotas) --------------------

def create_job(telegram_id: int, url: str, pages: int) -> int:
    with _get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (telegram_id, url, pages, results, status, created_at) "
            "VALUES (?, ?, ?, 0, 'pending', ?)",
            (telegram_id, url, pages, _now()),
        )
        return cur.lastrowid


def finish_job(job_id: int, results: int, status: str = "done") -> None:
    with _get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET results = ?, status = ? WHERE id = ?",
            (results, status, job_id),
        )
