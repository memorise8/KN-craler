"""Stable device identity for one-device license binding."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app_paths import default_runtime_root

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{12,96}$")
DEFAULT_STATE_FILE = default_runtime_root() / "device_identity.json"
_IDENTITY_CACHE: Optional["DeviceIdentity"] = None


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    source: str
    created_at: Optional[float] = None


def get_device_identity() -> DeviceIdentity:
    global _IDENTITY_CACHE
    if _IDENTITY_CACHE is not None:
        return _IDENTITY_CACHE

    override = _normalize_device_id(os.environ.get("KIDSNOTE_DEVICE_ID", ""))
    if override:
        _IDENTITY_CACHE = DeviceIdentity(device_id=override, source="env_override")
        return _IDENTITY_CACHE

    state_file = _state_file()
    cached = _read_cached_identity(state_file)
    if cached:
        _IDENTITY_CACHE = cached
        return cached

    raw_identity, source = _resolve_machine_identity()
    created_at = time.time()
    if raw_identity:
        device_id = _derive_device_id(raw_identity)
    else:
        device_id = f"kn-device-{uuid.uuid4().hex}"
        source = "random_fallback"

    payload = {
        "device_id": device_id,
        "source": source,
        "created_at": created_at,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _IDENTITY_CACHE = DeviceIdentity(device_id=device_id, source=source, created_at=created_at)
    return _IDENTITY_CACHE


def mask_device_id(device_id: str) -> str:
    normalized = _normalize_device_id(device_id)
    if not normalized:
        return ""
    if len(normalized) <= 16:
        return f"{normalized[:4]}...{normalized[-4:]}"
    return f"{normalized[:8]}...{normalized[-8:]}"


def _state_file() -> Path:
    configured = os.environ.get("KIDSNOTE_DEVICE_ID_FILE") or DEFAULT_STATE_FILE
    return Path(configured).expanduser()


def _read_cached_identity(state_file: Path) -> Optional[DeviceIdentity]:
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    device_id = _normalize_device_id(data.get("device_id", ""))
    if not device_id:
        return None
    source = str(data.get("source", "cached")).strip() or "cached"
    created_at = data.get("created_at")
    return DeviceIdentity(device_id=device_id, source=source, created_at=created_at)


def _derive_device_id(raw_identity: str) -> str:
    digest = hashlib.sha256(f"KidsnoteBackup|{raw_identity}".encode("utf-8")).hexdigest()
    return f"kn-device-{digest[:32]}"


def _normalize_device_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if not DEVICE_ID_PATTERN.fullmatch(normalized):
        return ""
    return normalized


def _resolve_machine_identity() -> Tuple[str, str]:
    readers = []
    if sys.platform == "win32":
        readers.append(_read_windows_machine_guid)
    elif sys.platform == "darwin":
        readers.append(_read_macos_platform_uuid)
    else:
        readers.append(_read_linux_machine_id)
    readers.append(_read_mac_address)

    for reader in readers:
        value, source = reader()
        if value:
            return value, source
    return "", ""


def _read_windows_machine_guid() -> Tuple[str, str]:
    try:
        import winreg
    except ImportError:
        return "", ""
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return "", ""
    normalized = str(value).strip()
    return (normalized, "windows_machine_guid") if normalized else ("", "")


def _read_macos_platform_uuid() -> Tuple[str, str]:
    try:
        output = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except Exception:
        return "", ""
    match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', output)
    if not match:
        return "", ""
    return match.group(1).strip(), "macos_platform_uuid"


def _read_linux_machine_id() -> Tuple[str, str]:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if value:
            return value, "linux_machine_id"
    return "", ""


def _read_mac_address() -> Tuple[str, str]:
    try:
        node = uuid.getnode()
    except Exception:
        return "", ""
    if node in (0, None):
        return "", ""
    return f"{node:012x}", "mac_address_fallback"
