from __future__ import annotations

import os
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from license_server_store import LicenseServerStore

ADMIN_TOKEN = os.environ.get("KIDSNOTE_LICENSE_ADMIN_TOKEN", "dev-admin-token")
store = LicenseServerStore()

app = FastAPI(title="Kidsnote License Server")


class ActivateBody(BaseModel):
    license_key: str
    device_id: str = ""


class CheckBody(BaseModel):
    license_key: str
    device_id: str = ""


class IssueBody(BaseModel):
    order_id: str = ""
    note: str = ""
    expires_at: Optional[float] = None


class RevokeBody(BaseModel):
    license_key: str


def require_admin(x_admin_token: Optional[str]) -> None:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="invalid admin token")


def serialize_record(record: dict, message: str = "") -> dict:
    expires_at = record.get("expires_at")
    is_active = (
        record["status"] == "active"
        and not (expires_at and float(expires_at) <= time.time())
    )
    return {
        "status": record["status"],
        "is_active": is_active,
        "license_key_masked": _mask_key(record["license_key"]),
        "bound_device_id": record.get("bound_device_id") or "",
        "bound_device_id_masked": _mask_device_id(record.get("bound_device_id") or ""),
        "order_id": record.get("order_id") or "",
        "issued_at": record.get("issued_at"),
        "activated_at": record.get("activated_at"),
        "last_checked_at": record.get("last_checked_at"),
        "expires_at": record.get("expires_at"),
        "activation_count": record.get("activation_count", 0),
        "message": message or default_message(record),
    }


def default_message(record: dict) -> str:
    if record["status"] == "issued":
        return "발급된 라이선스입니다. 아직 활성화되지 않았습니다."
    if record["status"] == "active":
        return "현재 기기에 바인딩된 유효한 라이선스입니다."
    if record["status"] == "revoked":
        return "비활성화된 라이선스입니다."
    return "라이선스 상태를 확인할 수 없습니다."


def _mask_key(license_key: str) -> str:
    parts = [part for part in license_key.split("-") if part]
    if len(parts) >= 2:
        return f"{parts[0]}-****-{parts[-1]}"
    return "****"


def _mask_device_id(device_id: str) -> str:
    if not device_id:
        return ""
    if len(device_id) <= 16:
        return f"{device_id[:4]}...{device_id[-4:]}"
    return f"{device_id[:8]}...{device_id[-8:]}"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "kidsnote-license-server"}


@app.post("/api/v1/licenses/activate")
def activate_license(body: ActivateBody):
    try:
        record = store.activate(body.license_key.strip().upper(), body.device_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return serialize_record(record)


@app.post("/api/v1/licenses/check")
def check_license(body: CheckBody):
    try:
        record = store.check(body.license_key.strip().upper(), body.device_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return serialize_record(record)


@app.post("/api/v1/admin/licenses/issue")
def issue_license(body: IssueBody, x_admin_token: Optional[str] = Header(default=None)):
    require_admin(x_admin_token)
    record = store.issue(order_id=body.order_id, note=body.note, expires_at=body.expires_at)
    return {
        "license_key": record["license_key"],
        **serialize_record(record, message="새 라이선스 키가 발급되었습니다."),
    }


@app.post("/api/v1/admin/licenses/revoke")
def revoke_license(body: RevokeBody, x_admin_token: Optional[str] = Header(default=None)):
    require_admin(x_admin_token)
    try:
        record = store.revoke(body.license_key.strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return serialize_record(record, message="라이선스가 비활성화되었습니다.")
