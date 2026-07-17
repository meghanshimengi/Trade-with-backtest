import sqlite3
import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "broker_credentials.db")

ADMIN_USERNAME = "administrator"
ADMIN_DEFAULT_PASSWORD = "Jitu4680**"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                mobile TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                broker_name TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                api_secret TEXT NOT NULL DEFAULT '',
                additional_config TEXT NOT NULL DEFAULT '{}',
                access_token TEXT NOT NULL DEFAULT '',
                token_updated_at TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, broker_name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                broker_name TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        _migrate_add_columns(conn)
        _ensure_admin(conn)


def _ensure_admin(conn):
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, mobile, role) VALUES (?, ?, ?, ?, ?)",
            (ADMIN_USERNAME, _hash_password(ADMIN_DEFAULT_PASSWORD),
             "admin@system.local", "0000000000", "admin")
        )


def _migrate_add_columns(conn):
    try:
        conn.execute("SELECT email FROM users LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    try:
        conn.execute("SELECT mobile FROM users LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE users ADD COLUMN mobile TEXT NOT NULL DEFAULT ''")
    try:
        conn.execute("SELECT role FROM users LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    try:
        conn.execute("SELECT is_active FROM users LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


def create_user(username: str, password: str, email: str = "", mobile: str = "") -> int:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, mobile) VALUES (?, ?, ?, ?)",
            (username, _hash_password(password), email, mobile)
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def authenticate_user(username: str, password: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ? AND password_hash = ? AND is_active = 1",
            (username, _hash_password(password))
        ).fetchone()
        return row["id"] if row else None


def get_user(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, email, mobile, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, email, mobile, role, is_active FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        return dict(row) if row else None


def change_password(user_id: int, old_password: str, new_password: str) -> tuple[bool, str]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE id = ? AND password_hash = ?",
            (user_id, _hash_password(old_password))
        ).fetchone()
        if not row:
            return False, "Current password is incorrect"
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters"
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(new_password), user_id)
        )
        return True, "Password changed successfully"


def admin_reset_password(user_id: int, new_password: str) -> tuple[bool, str]:
    with get_db() as conn:
        user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, "User not found"
        if user["username"] == ADMIN_USERNAME:
            return False, "Cannot reset admin password from admin panel"
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters"
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(new_password), user_id)
        )
        return True, f"Password reset for {user['username']}"


def create_password_reset_token(user_id: int) -> str:
    token = _generate_reset_token()
    expires = (datetime.now() + timedelta(hours=1)).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires)
        )
    return token


def verify_reset_token(token: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT user_id FROM password_resets WHERE token = ? AND used = 0 AND expires_at > ?",
            (token, datetime.now().isoformat())
        ).fetchone()
        if row:
            return row["user_id"]
        return None


def use_reset_token(token: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE password_resets SET used = 1 WHERE token = ?", (token,)
        )


def reset_password_with_token(token: str, new_password: str) -> tuple[bool, str]:
    user_id = verify_reset_token(token)
    if not user_id:
        return False, "Invalid or expired reset token"
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters"
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(new_password), user_id)
        )
        conn.execute(
            "UPDATE password_resets SET used = 1 WHERE token = ?", (token,)
        )
    return True, "Password reset successful"


def find_user_by_email_or_mobile(identifier: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, email, mobile FROM users WHERE (email = ? OR mobile = ?) AND is_active = 1",
            (identifier, identifier)
        ).fetchone()
        return dict(row) if row else None


def list_all_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, email, mobile, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def admin_update_user(user_id: int, email: str = "", mobile: str = "",
                      is_active: int = 1) -> tuple[bool, str]:
    with get_db() as conn:
        user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, "User not found"
        if user["username"] == ADMIN_USERNAME:
            return False, "Cannot modify admin account"
        conn.execute(
            "UPDATE users SET email = ?, mobile = ?, is_active = ? WHERE id = ?",
            (email, mobile, is_active, user_id)
        )
        return True, "User updated"


def admin_delete_user(user_id: int) -> tuple[bool, str]:
    with get_db() as conn:
        user = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, "User not found"
        if user["username"] == ADMIN_USERNAME:
            return False, "Cannot delete admin account"
        conn.execute("DELETE FROM broker_credentials WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM trade_sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True, f"User {user['username']} deleted"


def admin_change_own_password(new_password: str) -> tuple[bool, str]:
    with get_db() as conn:
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters"
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (_hash_password(new_password), ADMIN_USERNAME)
        )
        return True, "Admin password changed successfully"


def get_user_count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]


def get_active_user_count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) as c FROM users WHERE is_active = 1").fetchone()["c"]


def save_broker_credentials(user_id: int, broker_name: str,
                            api_key: str = "", api_secret: str = "",
                            access_token: str = "",
                            additional_config: dict | None = None):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM broker_credentials WHERE user_id = ? AND broker_name = ?",
            (user_id, broker_name)
        ).fetchone()
        config_json = json.dumps(additional_config or {})
        now = datetime.now().isoformat()
        if existing:
            conn.execute("""
                UPDATE broker_credentials
                SET api_key = ?, api_secret = ?, access_token = ?,
                    additional_config = ?, token_updated_at = ?, is_active = 1
                WHERE user_id = ? AND broker_name = ?
            """, (api_key, api_secret, access_token, config_json, now,
                  user_id, broker_name))
        else:
            conn.execute("""
                INSERT INTO broker_credentials
                (user_id, broker_name, api_key, api_secret, access_token,
                 additional_config, token_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, broker_name, api_key, api_secret, access_token,
                  config_json, now))


def load_broker_credentials(user_id: int, broker_name: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("""
            SELECT api_key, api_secret, access_token, additional_config,
                   token_updated_at
            FROM broker_credentials
            WHERE user_id = ? AND broker_name = ? AND is_active = 1
        """, (user_id, broker_name)).fetchone()
        if not row:
            return None
        return {
            "api_key": row["api_key"],
            "api_secret": row["api_secret"],
            "access_token": row["access_token"],
            "additional_config": json.loads(row["additional_config"] or "{}"),
            "token_updated_at": row["token_updated_at"],
        }


def list_broker_credentials(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT broker_name, api_key, token_updated_at, is_active
            FROM broker_credentials WHERE user_id = ?
        """, (user_id,)).fetchall()
        return [
            {
                "broker_name": r["broker_name"],
                "has_api_key": bool(r["api_key"]),
                "has_token": bool(r["token_updated_at"]),
                "token_updated": r["token_updated_at"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]


def delete_broker_credentials(user_id: int, broker_name: str):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM broker_credentials WHERE user_id = ? AND broker_name = ?",
            (user_id, broker_name)
        )


def log_trade_session(user_id: int, broker_name: str) -> int:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO trade_sessions (user_id, broker_name) VALUES (?, ?)",
            (user_id, broker_name)
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def end_trade_session(session_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE trade_sessions SET ended_at = ? WHERE id = ?",
            (datetime.now().isoformat(), session_id)
        )


init_db()
