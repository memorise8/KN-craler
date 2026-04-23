from __future__ import annotations

import os
import time
from dataclasses import replace

from device_identity import get_device_identity, mask_device_id
from license_server_client import (
    LicenseServerClient,
    LicenseServerError,
    LicenseServerUnavailable,
)
from license_store import LicenseState, store


class LicenseService:
    def __init__(self):
        self._server_url = os.environ.get("KIDSNOTE_LICENSE_SERVER_URL", "").strip()
        self._offline_grace_days = max(float(os.environ.get("KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS", "7")), 0.0)

    def _decorate_with_device(self, state: LicenseState) -> LicenseState:
        identity = get_device_identity()
        return replace(
            state,
            current_device_id=identity.device_id,
            current_device_id_masked=mask_device_id(identity.device_id),
            device_id_source=identity.source,
            bound_device_id_masked=state.bound_device_id_masked or mask_device_id(state.bound_device_id),
        )

    def _offline_grace_until(self, last_checked_at: float | None) -> float | None:
        if not last_checked_at or self._offline_grace_days <= 0:
            return None
        return float(last_checked_at) + (self._offline_grace_days * 86400)

    def _offline_grace_state(self, cached: LicenseState, reason: str) -> LicenseState | None:
        grace_until = self._offline_grace_until(cached.last_checked_at)
        if not grace_until or not cached.is_active:
            return None
        if time.time() > grace_until:
            return None
        return self._decorate_with_device(
            replace(
                cached,
                status="active",
                is_active=True,
                verification_mode="remote_server_grace",
                server_url=self._server_url,
                offline_grace_until=grace_until,
                message=f"라이선스 서버에 연결할 수 없지만 최근 검증 기록으로 오프라인 유예 중입니다: {reason}",
            )
        )

    def status(self) -> LicenseState:
        identity = get_device_identity()
        cached = store.get()
        if not self._server_url:
            return self._decorate_with_device(cached)
        if not cached.license_key:
            state = LicenseState(
                status="inactive",
                is_active=False,
                verification_mode="remote_server",
                server_url=self._server_url,
                current_device_id=identity.device_id,
                current_device_id_masked=mask_device_id(identity.device_id),
                device_id_source=identity.source,
                message="라이선스 서버에서 인증할 키를 입력해 주세요.",
            )
            return state
        client = LicenseServerClient(self._server_url)
        try:
            payload = client.check(cached.license_key, device_id=identity.device_id)
        except LicenseServerError as exc:
            return store.deactivate(
                message=f"라이선스 서버 검증 실패: {exc}",
                verification_mode="remote_server",
                server_url=self._server_url,
                license_key_masked=cached.license_key_masked,
                current_device_id=identity.device_id,
                device_id_source=identity.source,
            )
        except LicenseServerUnavailable as exc:
            grace_state = self._offline_grace_state(cached, str(exc))
            if grace_state is not None:
                return grace_state
            return LicenseState(
                status="inactive",
                is_active=False,
                verification_mode="remote_server",
                license_key_masked=cached.license_key_masked,
                license_key_sha256=cached.license_key_sha256,
                server_url=self._server_url,
                current_device_id=identity.device_id,
                current_device_id_masked=mask_device_id(identity.device_id),
                device_id_source=identity.source,
                offline_grace_until=self._offline_grace_until(cached.last_checked_at),
                message=f"라이선스 서버에 연결할 수 없습니다: {exc}",
            )
        return store.activate_remote(
            cached.license_key,
            payload,
            self._server_url,
            current_device_id=identity.device_id,
            device_id_source=identity.source,
        )

    def activate(self, license_key: str) -> LicenseState:
        identity = get_device_identity()
        if not self._server_url:
            return store.activate_local(
                license_key,
                current_device_id=identity.device_id,
                device_id_source=identity.source,
            )
        client = LicenseServerClient(self._server_url)
        try:
            payload = client.activate(license_key.strip().upper(), device_id=identity.device_id)
        except LicenseServerError as exc:
            raise ValueError(str(exc))
        except LicenseServerUnavailable as exc:
            raise ValueError(f"라이선스 서버에 연결할 수 없습니다: {exc}")
        return store.activate_remote(
            license_key,
            payload,
            self._server_url,
            current_device_id=identity.device_id,
            device_id_source=identity.source,
        )

    def deactivate(self) -> LicenseState:
        identity = get_device_identity()
        if self._server_url:
            return store.deactivate(
                message="로컬 활성화 상태를 해제했습니다. 서버 라이선스 자체는 유지됩니다.",
                verification_mode="remote_server",
                server_url=self._server_url,
                current_device_id=identity.device_id,
                device_id_source=identity.source,
            )
        return store.deactivate(
            current_device_id=identity.device_id,
            device_id_source=identity.source,
        )


service = LicenseService()
