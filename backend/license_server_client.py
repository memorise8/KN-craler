from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests


class LicenseServerError(Exception):
    pass


class LicenseServerUnavailable(Exception):
    pass


@dataclass
class LicenseServerClient:
    base_url: str
    timeout: float = 10.0

    def activate(self, license_key: str, device_id: str = "") -> dict:
        return self._post("/api/v1/licenses/activate", {"license_key": license_key, "device_id": device_id})

    def check(self, license_key: str, device_id: str = "") -> dict:
        return self._post("/api/v1/licenses/check", {"license_key": license_key, "device_id": device_id})

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LicenseServerUnavailable(str(exc))
        data = _decode_json(response)
        if response.status_code >= 400:
            raise LicenseServerError((data or {}).get("detail") or response.text or "license server rejected request")
        return data


def _decode_json(response: requests.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {}
