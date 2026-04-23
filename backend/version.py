"""Application metadata shared by runtime and packaging."""
from __future__ import annotations

import os

APP_NAME = "Kidsnote Backup Console"
APP_SLUG = "KidsnoteBackup"
APP_PUBLISHER = "Kidsnote Backup"
APP_VERSION = os.environ.get("KIDSNOTE_APP_VERSION", "0.1.0")
