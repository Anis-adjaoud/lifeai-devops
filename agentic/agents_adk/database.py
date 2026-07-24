"""
LifeAI — Couche base de données PostgreSQL.

Tables :
  users          — utilisateurs enregistrés
  user_profiles  — données personnelles clé/valeur par utilisateur
  sessions       — historique des scores d'analyse
  patterns       — patterns récurrents détectés
  user_notes     — observations libres enregistrées pendant les conversations
  oauth_tokens   — tokens OAuth2 par utilisateur et provider (Google Fit, etc.)
  health_metrics — métriques brutes Google Fit
  conversations  — historique des conversations du chatbot
  conv_messages  — messages de chaque conversation

Configuration (variables d'environnement) :
  DATABASE_URL   — DSN complet  ex: postgresql://user:pass@host:5432/dbname
  ou bien :
  POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD
"""

from __future__ import annotations

import os
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

# ── Chargement .env si disponible ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Pool de connexions (créé au premier appel) ────────────────────────────────
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _dsn() -> str:
    """Construit le DSN PostgreSQL depuis les variables d'environnement."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host     = os.environ.get("POSTGRES_HOST",     "localhost")
    port     = os.environ.get("POSTGRES_PORT",     "5432")
    dbname   = os.environ.get("POSTGRES_DB",       "lifeai")
    user     = os.environ.get("POSTGRES_USER",     "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=_dsn())
    return _pool


class _Conn:
    """
    Adaptateur minimal qui expose la même interface que sqlite3.Connection
    (conn.execute / conn.fetchall / conn.fetchone) mais derrière psycopg2.
    """

    def __init__(self, raw: psycopg2.extensions.connection) -> None:
        self._raw = raw
        self._cur = raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, query: str, params=None):
        # sqlite3 utilise ? comme placeholder, psycopg2 utilise %s
        self._cur.execute(query.replace("?", "%s"), params)
        return self

    def fetchall(self) -> list:
        return self._cur.fetchall()

    def fetchone(self):
        return self._cur.fetchone()

    def close(self):
        self._cur.close()


@contextmanager
def _connect():
    """
    Obtient une connexion du pool, l'enveloppe dans _Conn,
    commit si succès / rollback si exception.
    """
    pool = _get_pool()
    raw = pool.getconn()
    conn = _Conn(raw)
    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        conn.close()
        pool.putconn(raw)


def init_db() -> None:
    """Crée les tables et index si ils n'existent pas encore."""
    stmts = [
        # ── users ──────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id    TEXT PRIMARY KEY,
            name       TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        # ── user_profiles ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id    TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── sessions ───────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id               SERIAL PRIMARY KEY,
            user_id          TEXT NOT NULL,
            date             TIMESTAMPTZ DEFAULT NOW(),
            global_score     REAL,
            activity_score   REAL,
            sleep_score      REAL,
            nutrition_score  REAL,
            risk_score       REAL,
            synthesis        TEXT,
            priority_action  TEXT,
            weekly_plan      TEXT,
            alerts           TEXT,
            prediction       TEXT,
            health_level     TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── patterns ───────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS patterns (
            user_id      TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            description  TEXT,
            occurrences  INTEGER DEFAULT 1,
            detected_at  TIMESTAMPTZ DEFAULT NOW(),
            last_seen    TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, pattern_type),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── user_notes ─────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS user_notes (
            id         SERIAL PRIMARY KEY,
            user_id    TEXT NOT NULL,
            note       TEXT NOT NULL,
            category   TEXT DEFAULT 'general',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── oauth_tokens ───────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            user_id       TEXT NOT NULL,
            provider      TEXT NOT NULL,
            access_token  TEXT NOT NULL,
            refresh_token TEXT,
            token_expiry  TEXT,
            updated_at    TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, provider),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── health_metrics ─────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS health_metrics (
            id             SERIAL PRIMARY KEY,
            user_id        TEXT NOT NULL,
            date           TIMESTAMPTZ DEFAULT NOW(),
            steps_today    INTEGER DEFAULT 0,
            steps_7d       TEXT    DEFAULT '[]',
            active_minutes INTEGER DEFAULT 0,
            sleep_hours    REAL    DEFAULT 0,
            sleep_7d       TEXT    DEFAULT '[]',
            calories       INTEGER DEFAULT 0,
            heart_rate     REAL,
            weight_kg      REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── conversations ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            title      TEXT DEFAULT 'Nouvelle conversation',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── conv_messages ──────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS conv_messages (
            id              SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """,
        # ── usage_metrics — tokens/temps consommés par analyse ou message de chat ──
        """
        CREATE TABLE IF NOT EXISTS usage_metrics (
            id                SERIAL PRIMARY KEY,
            user_id           TEXT NOT NULL,
            kind              TEXT NOT NULL,
            conversation_id   TEXT,
            elapsed_seconds   REAL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            thoughts_tokens   INTEGER DEFAULT 0,
            cached_tokens     INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            llm_calls         INTEGER DEFAULT 0,
            per_agent         TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """,
        # ── Migrations colonnes (idempotent) ──────────────────────────────
        "ALTER TABLE users    ADD COLUMN IF NOT EXISTS numero_tel      TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS synthesis       TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS priority_action TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS weekly_plan     TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS alerts          TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS prediction      TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS health_level    TEXT",
        # Supporte l'auth JWT email/password (nullable pour les users Google OAuth)
        "ALTER TABLE users    ADD COLUMN IF NOT EXISTS password_hash   TEXT",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ml_risks        TEXT",
        "ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS thoughts_tokens INTEGER DEFAULT 0",
        "ALTER TABLE usage_metrics ADD COLUMN IF NOT EXISTS cached_tokens   INTEGER DEFAULT 0",
        # ── Index ──────────────────────────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_date    ON sessions(user_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user_category   ON user_notes(user_id, category)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_user_date     ON health_metrics(user_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_conv_messages_conv    ON conv_messages(conversation_id, created_at ASC)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user    ON conversations(user_id, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_usage_metrics_user_kind ON usage_metrics(user_id, kind, created_at DESC)",
    ]
    with _connect() as conn:
        for stmt in stmts:
            conn.execute(stmt)


# ── Utilisateurs ──────────────────────────────────────────────────────────────

def ensure_user(user_id: str, name: str = None) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users(user_id, name) VALUES (?, ?) ON CONFLICT (user_id) DO NOTHING",
            (user_id, name),
        )


def set_user_phone(user_id: str, phone: str) -> None:
    """Met à jour le numéro de téléphone dans la table users."""
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET numero_tel = ? WHERE user_id = ?",
            (phone.lstrip("+").strip(), user_id),
        )


def get_user_phone(user_id: str) -> str | None:
    """Retourne le numéro de téléphone d'un utilisateur depuis la table users."""
    with _connect() as conn:
        conn.execute("SELECT numero_tel FROM users WHERE user_id = ?", (user_id,))
        row = conn.fetchone()
    return row["numero_tel"] if row else None


def get_all_users() -> list[dict]:
    with _connect() as conn:
        conn.execute("SELECT user_id, name, numero_tel, created_at FROM users ORDER BY created_at DESC")
        return [dict(r) for r in conn.fetchall()]


# ── Profil ────────────────────────────────────────────────────────────────────

def get_profile(user_id: str) -> dict:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            "SELECT key, value FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        rows = conn.fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


def update_profile(user_id: str, **kwargs) -> None:
    ensure_user(user_id)
    now = datetime.now().isoformat()
    with _connect() as conn:
        for key, value in kwargs.items():
            conn.execute(
                """INSERT INTO user_profiles(user_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (user_id, key)
                   DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at""",
                (user_id, key, json.dumps(value, ensure_ascii=False), now),
            )


# ── Sessions ──────────────────────────────────────────────────────────────────

def add_session(
    user_id: str,
    global_score: float,
    activity_score: float,
    sleep_score: float,
    nutrition_score: Optional[float],
    risk_score: float,
    synthesis: str = None,
    priority_action: str = None,
    weekly_plan: list = None,
    alerts: list = None,
    prediction: str = None,
    health_level: str = None,
    ml_risks: dict = None,
) -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sessions
               (user_id, global_score, activity_score, sleep_score, nutrition_score, risk_score,
                synthesis, priority_action, weekly_plan, alerts, prediction, health_level, ml_risks)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id,
             round(global_score, 1), round(activity_score, 1),
             round(sleep_score, 1),
             round(nutrition_score, 1) if nutrition_score is not None else None,
             round(risk_score, 1),
             synthesis, priority_action,
             json.dumps(weekly_plan or [], ensure_ascii=False),
             json.dumps(alerts or [],      ensure_ascii=False),
             prediction, health_level,
             json.dumps(ml_risks, ensure_ascii=False) if ml_risks else None),
        )


def update_today_session_narrative(
    user_id: str,
    synthesis: str = None,
    priority_action: str = None,
    weekly_plan: list = None,
    alerts: list = None,
    prediction: str = None,
    health_level: str = None,
) -> bool:
    """
    Met à jour la session la plus récente du jour (créée dans les 6 dernières heures)
    avec les champs narratifs fournis par le LLM.
    Retourne True si une session a été mise à jour, False sinon.
    """
    cutoff = (datetime.now() - timedelta(hours=6)).isoformat()
    pool = _get_pool()
    raw = pool.getconn()
    try:
        cur = raw.cursor()
        cur.execute(
            """UPDATE sessions
               SET synthesis       = COALESCE(%s, synthesis),
                   priority_action = COALESCE(%s, priority_action),
                   weekly_plan     = COALESCE(%s, weekly_plan),
                   alerts          = COALESCE(%s, alerts),
                   prediction      = COALESCE(%s, prediction),
                   health_level    = COALESCE(%s, health_level)
               WHERE id = (
                   SELECT id FROM sessions
                   WHERE user_id = %s AND date >= %s
                   ORDER BY date DESC LIMIT 1
               )""",
            (
                synthesis, priority_action,
                json.dumps(weekly_plan, ensure_ascii=False) if weekly_plan is not None else None,
                json.dumps(alerts,      ensure_ascii=False) if alerts      is not None else None,
                prediction, health_level,
                user_id, cutoff,
            ),
        )
        updated = cur.rowcount > 0
        cur.close()
        raw.commit()
    except Exception:
        raw.rollback()
        updated = False
    finally:
        pool.putconn(raw)
    return updated


def get_sessions(user_id: str, days: int = 30) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _connect() as conn:
        conn.execute(
            """SELECT date, global_score, activity_score, sleep_score,
                      nutrition_score, risk_score,
                      synthesis, priority_action, weekly_plan, alerts, prediction, health_level,
                      ml_risks
               FROM sessions
               WHERE user_id = ? AND date >= ?
               ORDER BY date DESC""",
            (user_id, cutoff),
        )
        rows = conn.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["weekly_plan"] = json.loads(d["weekly_plan"] or "[]")
        d["alerts"]      = json.loads(d["alerts"]      or "[]")
        d["ml_risks"]    = json.loads(d["ml_risks"]) if d.get("ml_risks") else None
        result.append(d)
    return result


def get_score_trend(user_id: str, window: int = 7) -> Optional[str]:
    sessions = get_sessions(user_id, days=window * 2)
    if len(sessions) < 4:
        return None
    recent = [s["global_score"] for s in sessions[:window]]
    older  = [s["global_score"] for s in sessions[window:]]
    if not recent or not older:
        return None
    avg_r = sum(recent) / len(recent)
    avg_o = sum(older)  / len(older)
    delta = avg_r - avg_o
    if delta > 3:
        return f"↑ en hausse (+{delta:.1f} pts sur {window}j)"
    if delta < -3:
        return f"↓ en baisse ({delta:.1f} pts sur {window}j)"
    return f"→ stable ({avg_r:.1f} pts)"


# ── Patterns ──────────────────────────────────────────────────────────────────

def add_pattern(user_id: str, pattern_type: str, description: str) -> bool:
    """Enregistre/incrémente un pattern récurrent. Retourne True seulement à la
    première détection (xmax=0 distingue un INSERT d'un UPDATE)."""
    ensure_user(user_id)
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, detected_at, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (user_id, pattern_type)
               DO UPDATE SET
                   occurrences = patterns.occurrences + 1,
                   last_seen   = EXCLUDED.last_seen
               RETURNING (xmax = 0) AS is_new""",
            (user_id, pattern_type, description, now, now),
        )
        row = conn.fetchone()
        return bool(row["is_new"]) if row else False


def get_patterns(user_id: str, min_occurrences: int = 2) -> list[dict]:
    with _connect() as conn:
        conn.execute(
            """SELECT pattern_type, description, occurrences, last_seen
               FROM patterns
               WHERE user_id = ? AND occurrences >= ?
               ORDER BY occurrences DESC""",
            (user_id, min_occurrences),
        )
        return [dict(r) for r in conn.fetchall()]


# ── Notes ─────────────────────────────────────────────────────────────────────

def add_note(user_id: str, note: str, category: str = "general") -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category) VALUES (?, ?, ?)",
            (user_id, note, category),
        )


def get_notes(user_id: str, category: str = None) -> list[dict]:
    with _connect() as conn:
        if category:
            conn.execute(
                "SELECT note, category, created_at FROM user_notes WHERE user_id = ? AND category = ? ORDER BY created_at DESC",
                (user_id, category),
            )
        else:
            conn.execute(
                "SELECT note, category, created_at FROM user_notes WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        return [dict(r) for r in conn.fetchall()]


# ── Métriques brutes Google Fit ───────────────────────────────────────────────

def add_health_metrics(
    user_id: str,
    steps_today: int = 0,
    steps_7d: list = None,
    active_minutes: int = 0,
    sleep_hours: float = 0,
    sleep_7d: list = None,
    calories: int = 0,
    heart_rate: float = None,
    weight_kg: float = None,
) -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO health_metrics
               (user_id, steps_today, steps_7d, active_minutes, sleep_hours, sleep_7d, calories, heart_rate, weight_kg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, steps_today,
             json.dumps(steps_7d or []),
             active_minutes, sleep_hours,
             json.dumps(sleep_7d or []),
             calories, heart_rate, weight_kg),
        )


def get_health_metrics(user_id: str, days: int = 30) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _connect() as conn:
        conn.execute(
            """SELECT date, steps_today, steps_7d, active_minutes,
                      sleep_hours, sleep_7d, calories, heart_rate, weight_kg
               FROM health_metrics
               WHERE user_id = ? AND date >= ?
               ORDER BY date DESC""",
            (user_id, cutoff),
        )
        rows = conn.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["steps_7d"] = json.loads(d["steps_7d"] or "[]")
        d["sleep_7d"]  = json.loads(d["sleep_7d"]  or "[]")
        result.append(d)
    return result


# ── Contexte coaching (agrégé) ────────────────────────────────────────────────

def get_coaching_context(user_id: str) -> dict:
    sessions = get_sessions(user_id, days=30)
    return {
        "sessions_count":    len(sessions),
        "trend":             get_score_trend(user_id) or "Pas assez de données",
        "recurring_patterns": get_patterns(user_id, min_occurrences=2),
        "recent_notes":      get_notes(user_id)[:10],
        "last_scores":       sessions[0] if sessions else None,
    }


# ── Conversations & messages ──────────────────────────────────────────────────

def create_conversation(user_id: str, title: str = "Nouvelle conversation") -> str:
    import uuid
    conv_id = uuid.uuid4().hex
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations(id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, user_id, title),
        )
    return conv_id


def update_conversation(conv_id: str, title: str = None) -> None:
    with _connect() as conn:
        if title is not None:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = NOW() WHERE id = ?",
                (title, conv_id),
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = NOW() WHERE id = ?",
                (conv_id,),
            )


def add_conv_message(conv_id: str, role: str, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conv_messages(conversation_id, role, content) VALUES (?, ?, ?)",
            (conv_id, role, content),
        )


def get_conversations(user_id: str, limit: int = 40) -> list[dict]:
    with _connect() as conn:
        conn.execute(
            """SELECT c.id, c.title, c.created_at, c.updated_at,
                      COUNT(m.id) AS message_count
               FROM conversations c
               LEFT JOIN conv_messages m ON m.conversation_id = c.id
               WHERE c.user_id = ?
               GROUP BY c.id, c.title, c.created_at, c.updated_at
               ORDER BY c.updated_at DESC
               LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in conn.fetchall()]


def get_conversation_owner(conv_id: str) -> str | None:
    """Retourne le user_id propriétaire d'une conversation, ou None si introuvable."""
    with _connect() as conn:
        conn.execute("SELECT user_id FROM conversations WHERE id = ?", (conv_id,))
        row = conn.fetchone()
        return row["user_id"] if row else None


def get_conv_messages(conv_id: str) -> list[dict]:
    with _connect() as conn:
        conn.execute(
            "SELECT role, content, created_at FROM conv_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,),
        )
        return [dict(r) for r in conn.fetchall()]


def delete_conversation(conv_id: str) -> None:
    with _connect() as conn:
        # CASCADE supprime automatiquement conv_messages
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


# ── Usage (tokens/temps) ────────────────────────────────────────────────────────

def add_usage_metric(
    user_id: str,
    kind: str,
    elapsed_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    thoughts_tokens: int = 0,
    cached_tokens: int = 0,
    total_tokens: int = 0,
    llm_calls: int = 0,
    per_agent: dict = None,
    conversation_id: str = None,
) -> None:
    """Enregistre le coût (tokens + latence) d'une analyse ('analyze') ou d'un message de chat ('chat')."""
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO usage_metrics
               (user_id, kind, conversation_id, elapsed_seconds,
                prompt_tokens, completion_tokens, thoughts_tokens, cached_tokens,
                total_tokens, llm_calls, per_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, kind, conversation_id, round(elapsed_seconds, 3),
             prompt_tokens, completion_tokens, thoughts_tokens, cached_tokens,
             total_tokens, llm_calls,
             json.dumps(per_agent or {}, ensure_ascii=False)),
        )


def get_usage_metrics(user_id: str = None, kind: str = None, days: int = 30) -> list[dict]:
    """Historique des métriques d'usage, du plus récent au plus ancien (filtrable par user/kind)."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    query = """SELECT user_id, kind, conversation_id, elapsed_seconds,
                      prompt_tokens, completion_tokens, thoughts_tokens, cached_tokens,
                      total_tokens, llm_calls,
                      per_agent, created_at
               FROM usage_metrics
               WHERE created_at >= ?"""
    params: list = [cutoff]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    query += " ORDER BY created_at DESC"
    with _connect() as conn:
        conn.execute(query, params)
        rows = conn.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["per_agent"] = json.loads(d["per_agent"]) if d.get("per_agent") else {}
        result.append(d)
    return result


# ── OAuth tokens ──────────────────────────────────────────────────────────────

def save_oauth_token(
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str = None,
    token_expiry: str = None,
) -> None:
    ensure_user(user_id)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO oauth_tokens(user_id, provider, access_token, refresh_token, token_expiry, updated_at)
               VALUES (?, ?, ?, ?, ?, NOW())
               ON CONFLICT (user_id, provider)
               DO UPDATE SET
                   access_token  = EXCLUDED.access_token,
                   refresh_token = COALESCE(EXCLUDED.refresh_token, oauth_tokens.refresh_token),
                   token_expiry  = EXCLUDED.token_expiry,
                   updated_at    = NOW()""",
            (user_id, provider, access_token, refresh_token, token_expiry),
        )


def get_oauth_token(user_id: str, provider: str) -> dict | None:
    with _connect() as conn:
        conn.execute(
            "SELECT access_token, refresh_token, token_expiry FROM oauth_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        row = conn.fetchone()
    return dict(row) if row else None


def delete_oauth_token(user_id: str, provider: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM oauth_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )


def get_all_oauth_tokens(provider: str) -> dict[str, dict]:
    with _connect() as conn:
        conn.execute(
            "SELECT user_id, access_token, refresh_token, token_expiry FROM oauth_tokens WHERE provider = ?",
            (provider,),
        )
        rows = conn.fetchall()
    return {
        r["user_id"]: {
            "access_token":  r["access_token"],
            "refresh_token": r["refresh_token"],
            "token_expiry":  r["token_expiry"],
        }
        for r in rows
    }


# ── Auth email/password (JWT) ──────────────────────────────────────────────────

def register_email_user(email: str, password_hash: str, name: str = "") -> None:
    """Crée un utilisateur avec auth email/password (user_id = email)."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO users(user_id, name, password_hash)
               VALUES (?, ?, ?)
               ON CONFLICT (user_id) DO NOTHING""",
            (email, name or email, password_hash),
        )


def get_user_for_auth(email: str) -> dict | None:
    """Retourne {user_id, name, password_hash} ou None si introuvable."""
    with _connect() as conn:
        conn.execute(
            "SELECT user_id, name, password_hash FROM users WHERE user_id = ?",
            (email,),
        )
        row = conn.fetchone()
    return dict(row) if row else None


# Initialisation automatique à l'import
init_db()
