"""
db.py — Vedika SQLite Memory Module
====================================
Replaces the flat vedika_memory.json with a structured SQLite database.
Supports multi-user memory keyed by email, structured retrieval queries,
and automatic migration from the legacy JSON format.

Database file: ~/.vedika_mascot/vedika_memory.db
"""

import os
import json
import sqlite3
import time
from contextlib import contextmanager


# ═══════════════════════════════════════════════════════════════
#   PATH HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_data_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".vedika_mascot")
    os.makedirs(d, exist_ok=True)
    return d

DB_PATH      = os.path.join(_get_data_dir(), "vedika_memory.db")
LEGACY_JSON  = os.path.join(_get_data_dir(), "vedika_memory.json")
# Also check project-local JSON for migration
_LOCAL_JSON  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vedika_memory.json")

DEFAULT_EMAIL = "local_user"


# ═══════════════════════════════════════════════════════════════
#   CONNECTION + SCHEMA
# ═══════════════════════════════════════════════════════════════

@contextmanager
def _get_conn():
    """Thread-safe SQLite connection with WAL mode for concurrent access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def db_init():
    """Create all tables if they don't exist. Safe to call multiple times."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                email           TEXT PRIMARY KEY,
                user_name       TEXT,
                user_age        INTEGER,
                total_sessions  INTEGER DEFAULT 0,
                last_session_end REAL,
                created_at      REAL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS strengths_weaknesses (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                email   TEXT NOT NULL,
                type    TEXT NOT NULL CHECK(type IN ('strength','weakness')),
                topic   TEXT NOT NULL,
                UNIQUE(email, type, topic)
            );

            CREATE TABLE IF NOT EXISTS progress (
                email        TEXT NOT NULL,
                module_id    TEXT NOT NULL,
                lesson_id    TEXT NOT NULL,
                lesson_title TEXT,
                updated_at   REAL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (email, module_id)
            );

            CREATE TABLE IF NOT EXISTS quizzes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                email     TEXT NOT NULL,
                topic     TEXT NOT NULL,
                score     REAL NOT NULL,
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                email     TEXT NOT NULL,
                title     TEXT NOT NULL,
                status    TEXT NOT NULL,
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT NOT NULL,
                user_msg   TEXT NOT NULL,
                ai_reply   TEXT NOT NULL,
                timestamp  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                data_json     TEXT NOT NULL DEFAULT '{}',
                timestamp     REAL NOT NULL
            );

            -- Indexes for fast per-user queries
            CREATE INDEX IF NOT EXISTS idx_quizzes_email     ON quizzes(email, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_activities_email  ON activities(email, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_chats_email       ON chats(email, timestamp DESC);
        """)
    print("[DB] SQLite database initialized:", DB_PATH)


# ═══════════════════════════════════════════════════════════════
#   USER UPSERT
# ═══════════════════════════════════════════════════════════════

def db_ensure_user(email: str):
    """Create user row if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users(email) VALUES(?)",
            (email,)
        )


# ═══════════════════════════════════════════════════════════════
#   LOAD / SAVE MEMORY  (unified dict format for backward compat)
# ═══════════════════════════════════════════════════════════════

def db_load_memory(email: str = DEFAULT_EMAIL) -> dict:
    """
    Load a unified memory dict for the given user.
    Returns the same shape as the old _default_memory() for drop-in compat.
    """
    db_ensure_user(email)
    with _get_conn() as conn:
        # Users row
        user_row = conn.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()

        # Strengths & weaknesses
        sw_rows = conn.execute(
            "SELECT type, topic FROM strengths_weaknesses WHERE email=?", (email,)
        ).fetchall()
        strengths  = [r["topic"] for r in sw_rows if r["type"] == "strength"]
        weaknesses = [r["topic"] for r in sw_rows if r["type"] == "weakness"]

        # Progress
        prog_rows = conn.execute(
            "SELECT module_id, lesson_id FROM progress WHERE email=?", (email,)
        ).fetchall()
        progress = {r["module_id"]: r["lesson_id"] for r in prog_rows}

        # Quizzes (last 50)
        quiz_rows = conn.execute(
            "SELECT topic, score, timestamp FROM quizzes WHERE email=? ORDER BY timestamp DESC LIMIT 50",
            (email,)
        ).fetchall()
        quizzes = [{"topic": r["topic"], "score": r["score"], "timestamp": r["timestamp"]}
                   for r in quiz_rows]

        # Assignments (last 50)
        asgn_rows = conn.execute(
            "SELECT title, status, timestamp FROM assignments WHERE email=? ORDER BY timestamp DESC LIMIT 50",
            (email,)
        ).fetchall()
        assignments = [{"title": r["title"], "status": r["status"], "timestamp": r["timestamp"]}
                       for r in asgn_rows]

        # Chats (last 50)
        chat_rows = conn.execute(
            "SELECT user_msg, ai_reply, timestamp FROM chats WHERE email=? ORDER BY timestamp DESC LIMIT 50",
            (email,)
        ).fetchall()
        chats = [{"user": r["user_msg"], "companion": r["ai_reply"], "timestamp": r["timestamp"]}
                 for r in chat_rows]

        # Recent activities (last 100)
        act_rows = conn.execute(
            "SELECT activity_type, data_json, timestamp FROM activities WHERE email=? ORDER BY timestamp DESC LIMIT 100",
            (email,)
        ).fetchall()
        recent_activities = [
            {"activity_type": r["activity_type"], "data": json.loads(r["data_json"]), "timestamp": r["timestamp"]}
            for r in act_rows
        ]

    return {
        "email":             email,
        "user_name":         user_row["user_name"]        if user_row else None,
        "user_age":          user_row["user_age"]         if user_row else None,
        "total_sessions":    user_row["total_sessions"]   if user_row else 0,
        "last_session_end":  user_row["last_session_end"] if user_row else None,
        "strengths":         strengths,
        "weaknesses":        weaknesses,
        "current_progress":  progress,
        "quizzes":           quizzes,
        "assignments":       assignments,
        "chats":             chats,
        "recent_activities": recent_activities,
    }


def db_save_memory(email: str, data: dict):
    """
    Save/update memory fields from the unified dict back to SQLite.
    Handles: user profile, strengths, weaknesses, progress.
    For time-series data (quizzes, chats, activities), use the specific append functions.
    """
    db_ensure_user(email)
    with _get_conn() as conn:
        # Update user profile
        conn.execute("""
            UPDATE users SET
                user_name        = COALESCE(?, user_name),
                user_age         = COALESCE(?, user_age),
                total_sessions   = ?,
                last_session_end = COALESCE(?, last_session_end)
            WHERE email = ?
        """, (
            data.get("user_name"),
            data.get("user_age"),
            data.get("total_sessions", 0),
            data.get("last_session_end"),
            email,
        ))

        # Overwrite progress
        if "current_progress" in data:
            for module_id, lesson_id in data["current_progress"].items():
                conn.execute("""
                    INSERT OR REPLACE INTO progress(email, module_id, lesson_id, updated_at)
                    VALUES(?, ?, ?, ?)
                """, (email, module_id, lesson_id, time.time()))

        # Strengths
        if "strengths" in data:
            for topic in data["strengths"]:
                conn.execute("""
                    INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic)
                    VALUES(?, 'strength', ?)
                """, (email, topic))

        # Weaknesses
        if "weaknesses" in data:
            for topic in data["weaknesses"]:
                conn.execute("""
                    INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic)
                    VALUES(?, 'weakness', ?)
                """, (email, topic))


# ═══════════════════════════════════════════════════════════════
#   APPEND-ONLY TIME-SERIES WRITES
# ═══════════════════════════════════════════════════════════════

def db_log_quiz(email: str, topic: str, score: float):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO quizzes(email, topic, score, timestamp) VALUES(?,?,?,?)",
            (email, topic, score, time.time())
        )
        # Auto-classify strength / weakness
        if score >= 80:
            conn.execute(
                "INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic) VALUES(?, 'strength', ?)",
                (email, topic)
            )
        elif score < 50:
            conn.execute(
                "INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic) VALUES(?, 'weakness', ?)",
                (email, topic)
            )


def db_log_assignment(email: str, title: str, status: str):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO assignments(email, title, status, timestamp) VALUES(?,?,?,?)",
            (email, title, status, time.time())
        )


def db_log_chat(email: str, user_msg: str, ai_reply: str):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO chats(email, user_msg, ai_reply, timestamp) VALUES(?,?,?,?)",
            (email, user_msg, ai_reply, time.time())
        )
        # Keep only last 50 chats per user
        conn.execute("""
            DELETE FROM chats WHERE email=? AND id NOT IN (
                SELECT id FROM chats WHERE email=? ORDER BY timestamp DESC LIMIT 50
            )
        """, (email, email))


def db_log_activity(email: str, activity_type: str, data: dict):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO activities(email, activity_type, data_json, timestamp) VALUES(?,?,?,?)",
            (email, activity_type, json.dumps(data), time.time())
        )
        # Keep only last 100 activities per user
        conn.execute("""
            DELETE FROM activities WHERE email=? AND id NOT IN (
                SELECT id FROM activities WHERE email=? ORDER BY timestamp DESC LIMIT 100
            )
        """, (email, email))


def db_update_progress(email: str, module_id: str, lesson_id: str, lesson_title: str = ""):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO progress(email, module_id, lesson_id, lesson_title, updated_at)
            VALUES(?,?,?,?,?)
        """, (email, module_id, lesson_id, lesson_title, time.time()))


def db_increment_sessions(email: str):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET total_sessions = total_sessions + 1 WHERE email=?",
            (email,)
        )


def db_set_session_end(email: str):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_session_end=? WHERE email=?",
            (time.time(), email)
        )


def db_set_profile(email: str, name: str, age: int):
    db_ensure_user(email)
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET user_name=?, user_age=? WHERE email=?",
            (name, age, email)
        )


# ═══════════════════════════════════════════════════════════════
#   STRUCTURED RETRIEVAL QUERIES
# ═══════════════════════════════════════════════════════════════

def db_get_recent_errors(email: str, limit: int = 5) -> list[dict]:
    """Get the most recent error activities for a user."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT data_json, timestamp FROM activities
            WHERE email=? AND activity_type='error'
            ORDER BY timestamp DESC LIMIT ?
        """, (email, limit)).fetchall()
    return [{"data": json.loads(r["data_json"]), "timestamp": r["timestamp"]} for r in rows]


def db_get_weak_topics(email: str) -> list[str]:
    """Return topics the user is struggling with (quiz score < 50)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT topic FROM quizzes
            WHERE email=? AND score < 50
            ORDER BY timestamp DESC LIMIT 10
        """, (email,)).fetchall()
    return [r["topic"] for r in rows]


def db_get_quiz_summary(email: str, limit: int = 5) -> list[dict]:
    """Get last N quiz results."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT topic, score, timestamp FROM quizzes
            WHERE email=? ORDER BY timestamp DESC LIMIT ?
        """, (email, limit)).fetchall()
    return [{"topic": r["topic"], "score": r["score"]} for r in rows]


def db_needs_onboarding(email: str = DEFAULT_EMAIL) -> bool:
    """Return True if user has no name/age set yet."""
    db_ensure_user(email)
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT user_name, user_age FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return True
    return not row["user_name"] or not row["user_age"]


def db_list_users() -> list[str]:
    """Return all known user emails."""
    with _get_conn() as conn:
        rows = conn.execute("SELECT email FROM users ORDER BY created_at DESC").fetchall()
    return [r["email"] for r in rows]


# ═══════════════════════════════════════════════════════════════
#   MIGRATION  (JSON → SQLite, runs once)
# ═══════════════════════════════════════════════════════════════

def _migrate_json_file(json_path: str, label: str):
    """Import a single legacy JSON memory file into the DB."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[DB] Could not read {label}: {e}")
        return

    email = data.get("email") or DEFAULT_EMAIL
    print(f"[DB] Migrating {label} -> user '{email}'")

    db_ensure_user(email)

    # Profile
    name = data.get("user_name")
    age  = data.get("user_age")
    if name or age:
        db_set_profile(email, name or "Student", int(age or 16))

    # Sessions
    sessions = data.get("total_sessions", 0)
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET total_sessions=?, last_session_end=? WHERE email=?",
            (sessions, data.get("last_session_end"), email)
        )

    # Strengths / weaknesses
    with _get_conn() as conn:
        for topic in data.get("strengths", []):
            conn.execute(
                "INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic) VALUES(?,?,?)",
                (email, "strength", topic)
            )
        for topic in data.get("weaknesses", []):
            conn.execute(
                "INSERT OR IGNORE INTO strengths_weaknesses(email, type, topic) VALUES(?,?,?)",
                (email, "weakness", topic)
            )

    # Progress
    with _get_conn() as conn:
        for mod_id, les_id in data.get("current_progress", {}).items():
            conn.execute(
                "INSERT OR REPLACE INTO progress(email, module_id, lesson_id, updated_at) VALUES(?,?,?,?)",
                (email, mod_id, les_id, time.time())
            )

    # Quizzes
    with _get_conn() as conn:
        for q in data.get("quizzes", []):
            conn.execute(
                "INSERT INTO quizzes(email, topic, score, timestamp) VALUES(?,?,?,?)",
                (email, q.get("topic", "Quiz"), q.get("score", 0), q.get("timestamp", time.time()))
            )

    # Assignments
    with _get_conn() as conn:
        for a in data.get("assignments", []):
            conn.execute(
                "INSERT INTO assignments(email, title, status, timestamp) VALUES(?,?,?,?)",
                (email, a.get("title", "Assignment"), a.get("status", "completed"), a.get("timestamp", time.time()))
            )

    # Chats
    with _get_conn() as conn:
        for c in data.get("chats", []):
            conn.execute(
                "INSERT INTO chats(email, user_msg, ai_reply, timestamp) VALUES(?,?,?,?)",
                (email, c.get("user", ""), c.get("companion", ""), c.get("timestamp", time.time()))
            )

    # Activities
    with _get_conn() as conn:
        for act in data.get("recent_activities", []):
            conn.execute(
                "INSERT INTO activities(email, activity_type, data_json, timestamp) VALUES(?,?,?,?)",
                (email, act.get("activity_type", "unknown"),
                 json.dumps(act.get("data", {})), act.get("timestamp", time.time()))
            )

    print(f"[DB] Migration of {label} complete.")


_MIGRATION_FLAG = os.path.join(_get_data_dir(), ".migrated_to_sqlite")


def migrate_json_to_sqlite():
    """
    One-time migration from legacy JSON files to SQLite.
    Checks a flag file so it only runs once.
    """
    if os.path.exists(_MIGRATION_FLAG):
        return  # Already migrated

    migrated_any = False

    # Try the data-dir JSON first, then the project-local one
    for path, label in [
        (LEGACY_JSON, "data-dir JSON"),
        (_LOCAL_JSON, "project-local JSON"),
    ]:
        if os.path.exists(path):
            _migrate_json_file(path, label)
            migrated_any = True
            # Rename old file as backup
            backup = path + ".bak"
            try:
                os.rename(path, backup)
                print(f"[DB] Old JSON backed up as: {backup}")
            except Exception:
                pass
            break  # Only migrate one file

    if not migrated_any:
        print("[DB] No legacy JSON found — starting fresh.")

    # Write migration flag
    try:
        with open(_MIGRATION_FLAG, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#   STARTUP  (call this once at app launch)
# ═══════════════════════════════════════════════════════════════

def startup():
    """Initialize DB and run migration. Call once at app startup."""
    db_init()
    migrate_json_to_sqlite()
