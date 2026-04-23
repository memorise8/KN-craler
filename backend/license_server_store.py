"""SQLite-backed license server storage."""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path(
    os.environ.get("KIDSNOTE_LICENSE_SERVER_DB", Path(__file__).resolve().parent / "license_server.sqlite3")
)


def _now() -> float:
    return time.time()


class LicenseServerStore:
    def __init__(self, db_path: Optional[str | Path] = None):
        self._db_path = Path(db_path or DEFAULT_DB_PATH).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS licenses (
                    license_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    order_id TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    issued_at REAL NOT NULL,
                    activated_at REAL,
                    revoked_at REAL,
                    expires_at REAL,
                    bound_device_id TEXT NOT NULL DEFAULT '',
                    activation_count INTEGER NOT NULL DEFAULT 0,
                    last_checked_at REAL
                )
                """
            )
            conn.commit()

    def issue(self, order_id: str = "", note: str = "", expires_at: Optional[float] = None) -> dict:
        license_key = generate_license_key()
        issued_at = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO licenses (
                    license_key, status, order_id, note, issued_at, expires_at
                ) VALUES (?, 'issued', ?, ?, ?, ?)
                """,
                (license_key, order_id, note, issued_at, expires_at),
            )
            conn.commit()
        return self.get_required(license_key)

    def get(self, license_key: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT license_key, status, order_id, note, issued_at, activated_at,
                       revoked_at, expires_at, bound_device_id, activation_count, last_checked_at
                FROM licenses
                WHERE license_key = ?
                """,
                (license_key,),
            ).fetchone()
        return dict(row) if row else None

    def get_required(self, license_key: str) -> dict:
        row = self.get(license_key)
        if not row:
            raise ValueError("license not found")
        return row

    def activate(self, license_key: str, device_id: str = "") -> dict:
        normalized_device_id = device_id.strip()
        record = self.get_required(license_key)
        self._ensure_usable(record, normalized_device_id)
        now = _now()
        activated_at = record["activated_at"] or now
        activation_count = int(record["activation_count"] or 0)
        bound_device_id = record["bound_device_id"] or normalized_device_id
        if record["status"] != "active":
            activation_count += 1
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE licenses
                SET status = 'active',
                    activated_at = ?,
                    bound_device_id = ?,
                    activation_count = ?,
                    last_checked_at = ?
                WHERE license_key = ?
                """,
                (activated_at, bound_device_id, activation_count, now, license_key),
            )
            conn.commit()
        return self.get_required(license_key)

    def check(self, license_key: str, device_id: str = "") -> dict:
        normalized_device_id = device_id.strip()
        record = self.get_required(license_key)
        self._ensure_usable(record, normalized_device_id)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE licenses SET last_checked_at = ? WHERE license_key = ?",
                (now, license_key),
            )
            conn.commit()
        return self.get_required(license_key)

    def revoke(self, license_key: str) -> dict:
        self.get_required(license_key)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE licenses
                SET status = 'revoked',
                    revoked_at = ?
                WHERE license_key = ?
                """,
                (now, license_key),
            )
            conn.commit()
        return self.get_required(license_key)

    def _ensure_usable(self, record: dict, device_id: str) -> None:
        if not device_id:
            raise ValueError("device id required")
        if record["status"] == "revoked":
            raise ValueError("license revoked")
        expires_at = record.get("expires_at")
        if expires_at and float(expires_at) <= _now():
            raise ValueError("license expired")
        bound_device_id = record.get("bound_device_id") or ""
        if bound_device_id and bound_device_id != device_id:
            raise ValueError("license bound to another device")


def generate_license_key() -> str:
    chunks = ["KNB"]
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(3):
        chunks.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "-".join(chunks)
