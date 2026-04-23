"""Local license cache storage."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from app_paths import default_runtime_root

LICENSE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{10,64}$")
DEFAULT_STATE_FILE = default_runtime_root() / "license_state.json"


@dataclass
class LicenseState:
    status: str = "inactive"
    is_active: bool = False
    verification_mode: str = "local_placeholder"
    license_key: str = ""
    license_key_masked: str = ""
    license_key_sha256: str = ""
    server_url: str = ""
    bound_device_id: str = ""
    bound_device_id_masked: str = ""
    current_device_id: str = ""
    current_device_id_masked: str = ""
    device_id_source: str = ""
    activated_at: Optional[float] = None
    last_checked_at: Optional[float] = None
    offline_grace_until: Optional[float] = None
    expires_at: Optional[float] = None
    message: str = "라이선스 키를 입력하면 앱이 잠금 해제됩니다."


class LicenseStore:
    def __init__(self, state_file: Optional[str | Path] = None):
        configured = state_file or os.environ.get("KIDSNOTE_LICENSE_STATE_FILE") or DEFAULT_STATE_FILE
        self._state_file = Path(configured).expanduser()
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> LicenseState:
        if not self._state_file.exists():
            return LicenseState()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return LicenseState(message="라이선스 상태 파일을 읽지 못했습니다. 다시 인증해 주세요.")
        return LicenseState(
            status=data.get("status", "inactive"),
            is_active=bool(data.get("is_active", False)),
            verification_mode=data.get("verification_mode", "local_placeholder"),
            license_key=data.get("license_key", ""),
            license_key_masked=data.get("license_key_masked", ""),
            license_key_sha256=data.get("license_key_sha256", ""),
            server_url=data.get("server_url", ""),
            bound_device_id=data.get("bound_device_id", ""),
            bound_device_id_masked=data.get("bound_device_id_masked") or _mask_device_id(data.get("bound_device_id", "")),
            current_device_id=data.get("current_device_id", ""),
            current_device_id_masked=data.get("current_device_id_masked") or _mask_device_id(data.get("current_device_id", "")),
            device_id_source=data.get("device_id_source", ""),
            activated_at=data.get("activated_at"),
            last_checked_at=data.get("last_checked_at"),
            offline_grace_until=data.get("offline_grace_until"),
            expires_at=data.get("expires_at"),
            message=data.get("message", "라이선스 키를 입력하면 앱이 잠금 해제됩니다."),
        )

    def is_active(self) -> bool:
        return self.get().is_active

    def activate_local(
        self,
        license_key: str,
        current_device_id: str = "",
        device_id_source: str = "",
    ) -> LicenseState:
        normalized = license_key.strip().upper()
        if not LICENSE_KEY_PATTERN.fullmatch(normalized):
            raise ValueError("라이선스 키 형식이 올바르지 않습니다.")
        now = time.time()
        state = LicenseState(
            status="active",
            is_active=True,
            verification_mode="local_placeholder",
            license_key=normalized,
            license_key_masked=_mask_key(normalized),
            license_key_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            bound_device_id=current_device_id,
            bound_device_id_masked=_mask_device_id(current_device_id),
            current_device_id=current_device_id,
            current_device_id_masked=_mask_device_id(current_device_id),
            device_id_source=device_id_source,
            activated_at=now,
            last_checked_at=now,
            message="임시 로컬 검증으로 라이선스가 활성화되었습니다. 다음 단계에서 서버 검증으로 교체됩니다.",
        )
        self._write(state)
        return state

    def activate_remote(
        self,
        license_key: str,
        payload: dict,
        server_url: str,
        current_device_id: str = "",
        device_id_source: str = "",
    ) -> LicenseState:
        normalized = license_key.strip().upper()
        if not LICENSE_KEY_PATTERN.fullmatch(normalized):
            raise ValueError("라이선스 키 형식이 올바르지 않습니다.")
        now = time.time()
        bound_device_id = payload.get("bound_device_id", "")
        state = LicenseState(
            status=payload.get("status", "inactive"),
            is_active=bool(payload.get("is_active", False)),
            verification_mode="remote_server",
            license_key=normalized,
            license_key_masked=payload.get("license_key_masked") or _mask_key(normalized),
            license_key_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            server_url=server_url,
            bound_device_id=bound_device_id,
            bound_device_id_masked=payload.get("bound_device_id_masked") or _mask_device_id(bound_device_id),
            current_device_id=current_device_id,
            current_device_id_masked=_mask_device_id(current_device_id),
            device_id_source=device_id_source,
            activated_at=payload.get("activated_at"),
            last_checked_at=payload.get("last_checked_at") or now,
            expires_at=payload.get("expires_at"),
            message=payload.get("message", "라이선스 서버에서 상태를 확인했습니다."),
        )
        self._write(state)
        return state

    def deactivate(
        self,
        message: str = "라이선스가 비활성화되었습니다. 다시 키를 입력해 주세요.",
        verification_mode: str = "local_placeholder",
        server_url: str = "",
        license_key_masked: str = "",
        current_device_id: str = "",
        device_id_source: str = "",
    ) -> LicenseState:
        state = LicenseState(
            verification_mode=verification_mode,
            server_url=server_url,
            license_key_masked=license_key_masked,
            current_device_id=current_device_id,
            current_device_id_masked=_mask_device_id(current_device_id),
            device_id_source=device_id_source,
            message=message,
        )
        self._write(state)
        return state

    def _write(self, state: LicenseState) -> None:
        payload = asdict(state)
        self._state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_public_dict(self, state: Optional[LicenseState] = None) -> dict:
        current = state or self.get()
        payload = asdict(current)
        payload.pop("license_key", None)
        payload.pop("license_key_sha256", None)
        payload.pop("bound_device_id", None)
        payload.pop("current_device_id", None)
        return payload


def _mask_key(license_key: str) -> str:
    parts = [part for part in license_key.split("-") if part]
    if len(parts) >= 2:
        return f"{parts[0]}-****-{parts[-1]}"
    if len(license_key) <= 8:
        return "*" * len(license_key)
    return f"{license_key[:4]}****{license_key[-4:]}"


def _mask_device_id(device_id: str) -> str:
    if not device_id:
        return ""
    if len(device_id) <= 16:
        return f"{device_id[:4]}...{device_id[-4:]}"
    return f"{device_id[:8]}...{device_id[-8:]}"


store = LicenseStore()
