"""Standalone Kidsnote API client.

No framework dependency — only requests. Reusable outside of this app.

Auth flow:
  1. POST https://www.kidsnote.com/sb-login (form-encoded)
  2. Server sets `sessionid` cookie
  3. All /api/v1/* calls use this cookie

Key endpoints:
  GET  /api/v1/me/info/
  GET  /api/v1/children/{child_id}/albums/?page_size=30[&page=<cursor>]
  GET  /api/v1/albums/{album_id}
  Images on up-kids-kage.kakao.com are public (no auth needed).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlparse

import requests

BASE = "https://www.kidsnote.com"
LOGIN_URL = f"{BASE}/sb-login"
ME_INFO_URL = f"{BASE}/api/v1/me/info/"
ALBUM_URL = f"{BASE}/api/v1/albums/{{album_id}}"
CHILD_ALBUMS_URL = f"{BASE}/api/v1/children/{{child_id}}/albums/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

VARIANTS = ("original", "large", "small_resize", "small")


class KidsnoteAuthError(Exception):
    pass


class KidsnoteClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        self.me: Optional[dict] = None

    def sessionid(self) -> Optional[str]:
        for c in self.session.cookies:
            if c.name == "sessionid":
                return c.value
        return None

    def restore_session(self, sessionid: str) -> None:
        self.session.cookies.set("sessionid", sessionid, domain=".kidsnote.com", path="/")

    def login(self, username: str, password: str, retries: int = 3) -> dict:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            self.session.cookies.clear()
            try:
                r = self.session.post(
                    LOGIN_URL,
                    data={"username": username, "password": password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                if r.status_code >= 400:
                    raise KidsnoteAuthError(f"login POST returned HTTP {r.status_code}")
                if not self.sessionid():
                    raise KidsnoteAuthError("login failed: no sessionid cookie set — check credentials")
                me = self.get_me()
                self.me = me
                return me
            except KidsnoteAuthError:
                raise
            except Exception as exc:
                last_err = exc
                if attempt < retries - 1:
                    time.sleep((attempt + 1) * 2)
        raise KidsnoteAuthError(f"login failed after {retries} attempts: {last_err}")

    def get_me(self) -> dict:
        r = self.session.get(ME_INFO_URL, timeout=self.timeout)
        if r.status_code == 401 or r.status_code == 403:
            raise KidsnoteAuthError(f"session invalid (HTTP {r.status_code})")
        r.raise_for_status()
        data = r.json()
        self.me = data
        return data

    def list_children(self) -> list[dict]:
        me = self.me or self.get_me()
        out = []
        for c in me.get("children") or []:
            out.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "date_birth": c.get("date_birth"),
                "gender": c.get("gender"),
                "picture": (c.get("picture") or {}).get("small") if c.get("picture") else None,
            })
        return out

    def iter_child_albums(self, child_id: int, page_size: int = 30,
                          max_albums: Optional[int] = None) -> Iterator[dict]:
        url = CHILD_ALBUMS_URL.format(child_id=child_id)
        cursor: Optional[str] = None
        seen = 0
        while True:
            params: dict = {"page_size": page_size}
            if cursor:
                params["page"] = cursor
            r = self.session.get(url, params=params, timeout=self.timeout)
            if r.status_code in (401, 403):
                raise KidsnoteAuthError(f"session invalid (HTTP {r.status_code})")
            r.raise_for_status()
            data = r.json()
            for album in data.get("results") or []:
                yield album
                seen += 1
                if max_albums is not None and seen >= max_albums:
                    return
            cursor = data.get("next")
            if not cursor:
                return

    def fetch_album(self, album_id: int) -> dict:
        r = self.session.get(ALBUM_URL.format(album_id=album_id), timeout=self.timeout)
        if r.status_code in (401, 403):
            raise KidsnoteAuthError(f"session invalid (HTTP {r.status_code})")
        r.raise_for_status()
        return r.json()

    def download_image(self, url: str, out_path: Path, retries: int = 3) -> int:
        """Download a single image. Returns bytes written, or 0 on failure."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(retries):
            try:
                with self.session.get(url, stream=True, timeout=60) as r:
                    if r.status_code != 200:
                        raise RuntimeError(f"HTTP {r.status_code}")
                    tmp = out_path.with_suffix(out_path.suffix + ".part")
                    size = 0
                    with open(tmp, "wb") as fh:
                        for chunk in r.iter_content(chunk_size=64 * 1024):
                            if chunk:
                                fh.write(chunk)
                                size += len(chunk)
                    tmp.rename(out_path)
                    return size
            except Exception:
                if attempt < retries - 1:
                    time.sleep((attempt + 1) * 2)
        return 0


def sanitize_filename(name: str) -> str:
    bad = '<>:"/\\|?*\n\r\t'
    cleaned = "".join("_" if c in bad else c for c in name)
    return cleaned.strip(" .") or "file"


def image_filename(idx: int, img: dict, variant: str) -> str:
    url = img.get(variant) or img.get("original") or ""
    ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
    base = img.get("original_file_name") or f"{img.get('id', idx)}{ext}"
    return f"{idx:03d}_{sanitize_filename(base)}"


def image_url(img: dict, variant: str) -> Optional[str]:
    return img.get(variant) or img.get("original") or img.get("large")
