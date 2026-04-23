"""App-local storage paths for desktop distribution.

Defaults are chosen to behave like an installed local app:
- Windows: %LOCALAPPDATA%/KidsnoteBackup
- macOS: ~/Library/Application Support/KidsnoteBackup
- Linux: ~/.local/share/KidsnoteBackup (or XDG_DATA_HOME)

Every path can still be overridden by environment variables.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "KidsnoteBackup"


def app_home() -> Path:
    override = os.environ.get("KIDSNOTE_APP_HOME")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / APP_DIR_NAME


def default_runtime_root() -> Path:
    override = os.environ.get("KIDSNOTE_RUNTIME_ROOT")
    if override:
        return Path(override).expanduser()
    return app_home() / "runtime"


def default_download_root() -> Path:
    override = os.environ.get("KIDSNOTE_DOWNLOAD_ROOT")
    if override:
        return Path(override).expanduser()
    return app_home() / "downloads"


def default_session_db() -> Path:
    override = os.environ.get("KIDSNOTE_SESSION_DB")
    if override:
        return Path(override).expanduser()
    return default_runtime_root() / "sessions.sqlite3"
