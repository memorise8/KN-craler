"""FastAPI backend for the standalone Kidsnote photo app.

Run:
  cd backend
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8787
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app_paths import app_home, default_download_root, default_runtime_root
from bundle_paths import frontend_dir
from job_manager import manager
from license_service import service as license_service
from kidsnote_client import (
    KidsnoteAuthError,
    KidsnoteClient,
    VARIANTS,
    sanitize_filename,
)
from session_store import store

APP_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = frontend_dir()
APP_HOME = app_home()
RUNTIME_ROOT = default_runtime_root()
DOWNLOAD_ROOT = default_download_root()
APP_HOME.mkdir(parents=True, exist_ok=True)
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

SESSION_COOKIE = "kn_session"
DEFAULT_VARIANT = os.environ.get("KIDSNOTE_DEFAULT_VARIANT", "large")
DOWNLOAD_DELAY = float(os.environ.get("KIDSNOTE_DELAY", "0.1"))
COOKIE_SECURE = os.environ.get("KIDSNOTE_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"}
COOKIE_SAMESITE = os.environ.get("KIDSNOTE_COOKIE_SAMESITE", "lax").lower()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "KIDSNOTE_ALLOWED_ORIGINS",
        "http://localhost:8787,http://127.0.0.1:8787",
    ).split(",")
    if origin.strip()
]

app = FastAPI(title="Kidsnote Photo Grabber")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class LoginBody(BaseModel):
    username: str
    password: str
    auto_prefetch: bool = False  # if true, also kick off list of all albums


class DownloadAlbumBody(BaseModel):
    variant: str = DEFAULT_VARIANT


class DownloadChildAllBody(BaseModel):
    variant: str = DEFAULT_VARIANT
    max_albums: Optional[int] = None


class LicenseActivateBody(BaseModel):
    license_key: str


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------

def require_license():
    license_state = license_service.status()
    if not license_state.is_active:
        raise HTTPException(status_code=403, detail="license activation required")
    return license_state


def require_session(token: Optional[str]):
    sess = store.get(token)
    if not sess:
        raise HTTPException(status_code=401, detail="not logged in")
    return sess


# --------------------------------------------------------------------------
# License
# --------------------------------------------------------------------------

@app.get("/api/license/status")
def license_status():
    return store_public_license_state(license_service.status())


@app.post("/api/license/activate")
def activate_license(body: LicenseActivateBody):
    try:
        state = license_service.activate(body.license_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return store_public_license_state(state)


@app.post("/api/license/deactivate")
def deactivate_license():
    return store_public_license_state(license_service.deactivate())


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

@app.post("/api/login")
def login(body: LoginBody, response: Response):
    require_license()
    client = KidsnoteClient()
    try:
        me = client.login(body.username, body.password)
    except KidsnoteAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    user = (me or {}).get("user", {})
    sess = store.create(
        client=client,
        username=body.username,
        user_name=user.get("name", ""),
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sess.token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=store.ttl_seconds,
        path="/",
    )
    return {
        "ok": True,
        "user": {
            "username": user.get("username"),
            "name": user.get("name"),
            "email": user.get("email"),
        },
        "children": client.list_children(),
    }


@app.post("/api/logout")
def logout(response: Response, kn_session: Optional[str] = Cookie(default=None)):
    store.delete(kn_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    sess = require_session(kn_session)
    try:
        me_data = sess.client.get_me()
    except KidsnoteAuthError:
        store.delete(kn_session)
        raise HTTPException(status_code=401, detail="session expired; please log in again")
    user = (me_data or {}).get("user", {})
    return {
        "user": {
            "username": user.get("username"),
            "name": user.get("name"),
            "email": user.get("email"),
        },
        "children": sess.client.list_children(),
    }


# --------------------------------------------------------------------------
# Albums
# --------------------------------------------------------------------------

@app.get("/api/children/{child_id}/albums")
def list_child_albums(
    child_id: int,
    page: Optional[str] = None,
    page_size: int = 30,
    kn_session: Optional[str] = Cookie(default=None),
):
    require_license()
    sess = require_session(kn_session)
    try:
        url = f"https://www.kidsnote.com/api/v1/children/{child_id}/albums/"
        params: dict = {"page_size": page_size}
        if page:
            params["page"] = page
        r = sess.client.session.get(url, params=params, timeout=sess.client.timeout)
        if r.status_code in (401, 403):
            store.delete(kn_session)
            raise HTTPException(status_code=401, detail="session expired")
        r.raise_for_status()
        data = r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    summarized = []
    for a in data.get("results") or []:
        imgs = a.get("attached_images") or []
        summarized.append({
            "id": a.get("id"),
            "title": a.get("title"),
            "created": a.get("created"),
            "modified": a.get("modified"),
            "num_images": len(imgs),
            "thumb": _first_thumb(imgs),
            "author_name": a.get("author_name"),
            "content": a.get("content"),
        })
    return {"count": data.get("count"), "next": data.get("next"), "results": summarized}


@app.get("/api/albums/{album_id}")
def get_album(album_id: int, kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    sess = require_session(kn_session)
    try:
        album = sess.client.fetch_album(album_id)
    except KidsnoteAuthError:
        store.delete(kn_session)
        raise HTTPException(status_code=401, detail="session expired")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    imgs = []
    for i, img in enumerate(album.get("attached_images") or []):
        imgs.append({
            "idx": i,
            "id": img.get("id"),
            "width": img.get("width"),
            "height": img.get("height"),
            "file_size": img.get("file_size"),
            "thumb": img.get("small_resize") or img.get("small"),
            "large": img.get("large"),
            "original": img.get("original"),
        })
    return {
        "id": album.get("id"),
        "title": album.get("title"),
        "created": album.get("created"),
        "author_name": album.get("author_name"),
        "content": album.get("content"),
        "images": imgs,
    }


# --------------------------------------------------------------------------
# Downloads (background jobs)
# --------------------------------------------------------------------------

@app.post("/api/albums/{album_id}/download")
def download_album(album_id: int, body: DownloadAlbumBody,
                   kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    sess = require_session(kn_session)
    variant = body.variant if body.variant in VARIANTS else DEFAULT_VARIANT
    try:
        album = sess.client.fetch_album(album_id)
    except KidsnoteAuthError:
        store.delete(kn_session)
        raise HTTPException(status_code=401, detail="session expired")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    root = DOWNLOAD_ROOT / sess.username
    job, reused = manager.submit_album(
        client=sess.client,
        album=album,
        root=root,
        variant=variant,
        delay=DOWNLOAD_DELAY,
        owner_token=kn_session or "",
    )
    return {**asdict(job), "reused_existing": reused}


@app.post("/api/children/{child_id}/download-all")
def download_child_all(child_id: int, body: DownloadChildAllBody,
                       kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    sess = require_session(kn_session)
    variant = body.variant if body.variant in VARIANTS else DEFAULT_VARIANT
    root = DOWNLOAD_ROOT / sess.username / str(child_id)
    try:
        children = sess.client.list_children()
    except KidsnoteAuthError:
        store.delete(kn_session)
        raise HTTPException(status_code=401, detail="session expired")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    child_name = next((child.get("name", "") for child in children if child.get("id") == child_id), "")
    job, reused = manager.submit_child_all(
        client=sess.client,
        child_id=child_id,
        root=root,
        variant=variant,
        delay=DOWNLOAD_DELAY,
        owner_token=kn_session or "",
        max_albums=body.max_albums,
        child_name=child_name,
    )
    return {**asdict(job), "reused_existing": reused}


@app.get("/api/jobs")
def list_jobs(kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    require_session(kn_session)
    return manager.list_owned(kn_session or "")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    require_session(kn_session)
    j = manager.get_owned(job_id, kn_session or "")
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return asdict(j)


@app.get("/api/jobs/{job_id}/zip")
def download_job_zip(job_id: str, kn_session: Optional[str] = Cookie(default=None)):
    require_license()
    require_session(kn_session)
    job = manager.get_owned(job_id, kn_session or "")
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="download is still in progress")
    target = Path(job.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="download files not found on server")
    if not any(path.is_file() and not path.name.endswith(".part") for path in target.rglob("*")):
        raise HTTPException(status_code=409, detail="download finished but there are no completed files to archive")
    archive_name = _archive_name(job)
    archive_path = _create_zip_archive(target, archive_name)
    return FileResponse(
        path=str(archive_path),
        media_type="application/zip",
        filename=archive_name,
        background=BackgroundTask(_cleanup_file, archive_path),
    )


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "kidsnote-app"}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _first_thumb(imgs: list) -> Optional[str]:
    if not imgs:
        return None
    img = imgs[0]
    return (
        img.get("small_resize")
        or img.get("small")
        or img.get("large")
        or img.get("original")
    )


def _archive_name(job) -> str:
    stem = sanitize_filename(job.subject or f"{job.kind}-{job.job_id}")
    return f"{stem}-{job.job_id[:8]}.zip"


def _create_zip_archive(source_dir: Path, archive_name: str) -> Path:
    fd, tmp_name = tempfile.mkstemp(prefix="kidsnote-", suffix=".zip")
    os.close(fd)
    archive_path = Path(tmp_name)
    root_name = sanitize_filename(Path(archive_name).stem)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or path.name.endswith(".part"):
                continue
            arcname = Path(root_name) / path.relative_to(source_dir)
            zf.write(path, arcname=str(arcname))
    return archive_path


def _cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def store_public_license_state(state) -> dict:
    payload = asdict(state)
    payload.pop("license_key", None)
    payload.pop("license_key_sha256", None)
    payload.pop("bound_device_id", None)
    payload.pop("current_device_id", None)
    return payload


# --------------------------------------------------------------------------
# Serve frontend
# --------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
