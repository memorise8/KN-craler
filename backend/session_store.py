"""SQLite-backed session store with TTL.

Sessions are keyed by a random token (set in a httpOnly cookie on the
browser) and persist the Kidsnote ``sessionid`` cookie so the app can survive
backend restarts without forcing users to log in again.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app_paths import default_session_db
from kidsnote_client import KidsnoteClient

DEFAULT_TTL_SECONDS = 2 * 60 * 60  # 2 hours
DEFAULT_DB_PATH = default_session_db()


@dataclass
class Session:
    token: str
    client: KidsnoteClient
    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    user_name: str = ""
    username: str = ""


class SessionStore:
    def __init__(
        self,
        ttl: int = DEFAULT_TTL_SECONDS,
        db_path: Optional[str | Path] = None,
    ):
        self._ttl = ttl
        self._db_path = Path(db_path or os.environ.get("KIDSNOTE_SESSION_DB") or DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 3000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    sessionid TEXT NOT NULL,
                    username TEXT NOT NULL,
                    user_name TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def create(self, client: KidsnoteClient, username: str, user_name: str) -> Session:
        sessionid = client.sessionid()
        if not sessionid:
            raise ValueError("cannot create session without kidsnote sessionid")
        now = time.time()
        token = secrets.token_urlsafe(32)
        sess = Session(
            token=token,
            client=client,
            username=username,
            user_name=user_name,
            created_at=now,
            last_seen_at=now,
        )
        with self._lock, self._connect() as conn:
            self._prune_conn(conn)
            conn.execute(
                """
                INSERT INTO sessions (
                    token, sessionid, username, user_name, created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, sessionid, username, user_name, now, now),
            )
            conn.commit()
        return sess

    def get(self, token: Optional[str]) -> Optional[Session]:
        if not token:
            return None
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT token, sessionid, username, user_name, created_at, last_seen_at
                FROM sessions
                WHERE token = ?
                """,
                (token,),
            ).fetchone()
            if not row:
                return None
            if now - row["last_seen_at"] > self._ttl:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token = ?",
                (now, token),
            )
            conn.commit()
        client = KidsnoteClient()
        client.restore_session(row["sessionid"])
        return Session(
            token=row["token"],
            client=client,
            username=row["username"],
            user_name=row["user_name"],
            created_at=row["created_at"],
            last_seen_at=now,
        )

    def delete(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()

    def prune(self) -> int:
        with self._lock, self._connect() as conn:
            removed = self._prune_conn(conn)
            conn.commit()
            return removed

    def _prune_conn(self, conn: sqlite3.Connection) -> int:
        cutoff = time.time() - self._ttl
        cur = conn.execute("DELETE FROM sessions WHERE last_seen_at < ?", (cutoff,))
        return cur.rowcount if cur.rowcount is not None else 0


store = SessionStore()
