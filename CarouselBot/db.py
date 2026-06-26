"""
db.py — Gestión de usuarios y base de datos SQLite.
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "users.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id     INTEGER PRIMARY KEY,
            username        TEXT,
            email           TEXT,
            plan            TEXT DEFAULT 'free',
            active          INTEGER DEFAULT 0,
            carousels_used  INTEGER DEFAULT 0,
            carousels_limit INTEGER DEFAULT 5,
            brand_color     TEXT DEFAULT '#1E3A5F',
            brand_name      TEXT,
            brand_handle    TEXT,
            onboarded       INTEGER DEFAULT 0,
            joined_at       TEXT DEFAULT (datetime('now')),
            stan_order_id   TEXT
        );
        CREATE TABLE IF NOT EXISTS carousels (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            topic       TEXT,
            platform    TEXT DEFAULT 'instagram',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS pending_activations (
            email      TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)


def get_user(telegram_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


def create_user(telegram_id: int, username: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?,?)",
            (telegram_id, username)
        )


def activate_user(telegram_id: int, email: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE users SET active=1, plan='pro', email=?, carousels_limit=100
            WHERE telegram_id=?
        """, (email, telegram_id))


def set_pending_email(email: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pending_activations (email) VALUES (?)", (email,)
        )


def check_pending_activation(email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT email FROM pending_activations WHERE email=?", (email,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM pending_activations WHERE email=?", (email,))
            return True
        return False


def update_brand(telegram_id: int, color: str, name: str, handle: str):
    with get_conn() as conn:
        conn.execute("""
            UPDATE users SET brand_color=?, brand_name=?, brand_handle=?, onboarded=1
            WHERE telegram_id=?
        """, (color, name, handle, telegram_id))


def increment_usage(telegram_id: int, topic: str, platform: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET carousels_used=carousels_used+1 WHERE telegram_id=?",
            (telegram_id,)
        )
        conn.execute(
            "INSERT INTO carousels (telegram_id, topic, platform) VALUES (?,?,?)",
            (telegram_id, topic, platform)
        )


def can_create(telegram_id: int) -> tuple:
    user = get_user(telegram_id)
    if not user:
        return False, "no_user"
    if not user["active"]:
        return False, "not_active"
    if not user["onboarded"]:
        return False, "not_onboarded"
    if user["carousels_used"] >= user["carousels_limit"]:
        return False, "limit_reached"
    return True, "ok"


def get_stats():
    with get_conn() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active   = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
        carousels = conn.execute("SELECT COUNT(*) FROM carousels").fetchone()[0]
        return {"total_users": total, "active_users": active, "total_carousels": carousels}


def list_users(limit=20):
    with get_conn() as conn:
        return conn.execute("""
            SELECT telegram_id, username, email, plan, active, carousels_used, carousels_limit
            FROM users ORDER BY joined_at DESC LIMIT ?
        """, (limit,)).fetchall()


init_db()
