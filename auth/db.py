import sqlite3
import hashlib
import os
import secrets
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ideios.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        _init_sessions(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS essay_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                topic TEXT DEFAULT '',
                final_draft TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions_data (
                email TEXT PRIMARY KEY,
                topic TEXT DEFAULT '',
                resources TEXT DEFAULT '',
                conversation TEXT DEFAULT '[]',
                result TEXT DEFAULT '',
                mode TEXT DEFAULT 'essay',
                research_area TEXT DEFAULT ''
            )
        """)
        try:
            conn.execute("ALTER TABLE sessions_data ADD COLUMN mode TEXT DEFAULT 'essay'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE sessions_data ADD COLUMN research_area TEXT DEFAULT ''")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                verified INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'free',
                essays_used INTEGER DEFAULT 0,
                essays_reset_month TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # migrate existing DB that lacks the essays_reset_month column
        try:
            conn.execute("ALTER TABLE users ADD COLUMN essays_reset_month TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN research_used INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN research_reset_month TEXT DEFAULT ''")
        except Exception:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER DEFAULT 0
            )
        """)
        try:
            conn.execute("ALTER TABLE verification_codes ADD COLUMN attempts INTEGER DEFAULT 0")
        except Exception:
            pass


def _hash(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def _check(password: str, stored: str) -> bool:
    salt, key = stored.split(":")
    new_key = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return new_key.hex() == key


def create_user(email: str, password: str, tier: str) -> bool:
    """Returns False if email already exists."""
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, tier) VALUES (?, ?, ?)",
                (email.lower(), _hash(password), tier),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user(email: str):
    with _conn() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()


def check_password(email: str, password: str) -> bool:
    user = get_user(email)
    if not user:
        return False
    return _check(password, user["password_hash"])


def mark_verified(email: str):
    with _conn() as conn:
        conn.execute("UPDATE users SET verified = 1 WHERE email = ?", (email.lower(),))


def generate_code(email: str) -> str:
    code = str(secrets.randbelow(900000) + 100000)  # 6-digit, never starts with 0
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires = (datetime.now() + timedelta(minutes=10)).isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO verification_codes (email, code_hash, expires_at, attempts) VALUES (?, ?, ?, 0)",
            (email.lower(), code_hash, expires),
        )
    return code


MAX_VERIFY_ATTEMPTS = 5

def verify_code(email: str, code: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT code_hash, expires_at, attempts FROM verification_codes WHERE email = ?",
            (email.lower(),),
        ).fetchone()
        if not row:
            return False
        if row["attempts"] >= MAX_VERIFY_ATTEMPTS:
            return False
        if datetime.now() > datetime.fromisoformat(row["expires_at"]):
            return False
        code_hash = hashlib.sha256(code.strip().encode()).hexdigest()
        if row["code_hash"] == code_hash:
            conn.execute("DELETE FROM verification_codes WHERE email = ?", (email.lower(),))
            return True
        conn.execute(
            "UPDATE verification_codes SET attempts = attempts + 1 WHERE email = ?",
            (email.lower(),),
        )
        return False


def _maybe_reset_essays(conn, email: str):
    """Reset essays_used to 0 if we're in a new calendar month."""
    current_month = datetime.now().strftime("%Y-%m")
    row = conn.execute(
        "SELECT essays_used, essays_reset_month FROM users WHERE email = ?",
        (email.lower(),),
    ).fetchone()
    if row and row["essays_reset_month"] != current_month:
        conn.execute(
            "UPDATE users SET essays_used = 0, essays_reset_month = ? WHERE email = ?",
            (current_month, email.lower()),
        )


def increment_essays(email: str):
    with _conn() as conn:
        _maybe_reset_essays(conn, email)
        conn.execute(
            "UPDATE users SET essays_used = essays_used + 1 WHERE email = ?",
            (email.lower(),),
        )


def get_essays_used(email: str) -> int:
    with _conn() as conn:
        _maybe_reset_essays(conn, email)
    user = get_user(email)
    return user["essays_used"] if user else 0


# ── Session management (one active session per account) ───────────────────────

def _init_sessions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            email TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def create_session(email: str) -> str:
    """Invalidate any existing session and create a new one. Returns the token."""
    token = os.urandom(32).hex()
    with _conn() as conn:
        _init_sessions(conn)
        conn.execute(
            "INSERT OR REPLACE INTO sessions (email, token, created_at) VALUES (?, ?, ?)",
            (email.lower(), token, datetime.now().isoformat()),
        )
    return token


def save_session_data(email: str, topic: str, resources: str, conversation: list, result: dict,
                      mode: str = "essay", research_area: str = ""):
    import json
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sessions_data (email, topic, resources, conversation, result, mode, research_area)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            email.lower(), topic, resources,
            json.dumps(conversation),
            json.dumps(result) if result else "",
            mode, research_area,
        ))


def load_session_data(email: str) -> dict:
    import json
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions_data WHERE email = ?", (email.lower(),)
        ).fetchone()
    if not row:
        return {"topic": "", "resources": "", "conversation": [], "result": None,
                "mode": "essay", "research_area": ""}
    keys = row.keys()
    return {
        "topic": row["topic"],
        "resources": row["resources"],
        "conversation": json.loads(row["conversation"]),
        "result": json.loads(row["result"]) if row["result"] else None,
        "mode": row["mode"] if "mode" in keys else "essay",
        "research_area": row["research_area"] if "research_area" in keys else "",
    }


def validate_session(email: str, token: str) -> bool:
    """Returns True only if this token is the current active session for this email."""
    with _conn() as conn:
        _init_sessions(conn)
        row = conn.execute(
            "SELECT token FROM sessions WHERE email = ?", (email.lower(),)
        ).fetchone()
    if not row:
        return False
    return row["token"] == token


def save_essay_history(email: str, topic: str, final_draft: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO essay_history (email, topic, final_draft, created_at) VALUES (?, ?, ?, ?)",
            (email.lower(), topic, final_draft, datetime.now().isoformat()),
        )


def _maybe_reset_research(conn, email: str):
    current_month = datetime.now().strftime("%Y-%m")
    row = conn.execute(
        "SELECT research_used, research_reset_month FROM users WHERE email = ?",
        (email.lower(),),
    ).fetchone()
    if row and row["research_reset_month"] != current_month:
        conn.execute(
            "UPDATE users SET research_used = 0, research_reset_month = ? WHERE email = ?",
            (current_month, email.lower()),
        )


def increment_research(email: str):
    with _conn() as conn:
        _maybe_reset_research(conn, email)
        conn.execute(
            "UPDATE users SET research_used = research_used + 1 WHERE email = ?",
            (email.lower(),),
        )


def get_research_used(email: str) -> int:
    with _conn() as conn:
        _maybe_reset_research(conn, email)
    user = get_user(email)
    return user["research_used"] if user else 0


def get_essay_history(email: str) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, topic, final_draft, created_at FROM essay_history WHERE email = ? ORDER BY created_at DESC",
            (email.lower(),),
        ).fetchall()
    return [{"id": r["id"], "topic": r["topic"], "final_draft": r["final_draft"], "created_at": r["created_at"]} for r in rows]
