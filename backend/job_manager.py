"""Background job manager for photo downloads.

Jobs run in daemon threads and update progress in memory. The frontend polls
GET /api/jobs/{id} to render progress.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from kidsnote_client import (
    KidsnoteClient,
    image_filename,
    image_url,
)


@dataclass
class JobProgress:
    job_id: str
    kind: str  # "album" | "child"
    subject: str = ""
    status: str = "pending"  # pending|running|done|partial|failed
    child_id: Optional[int] = None
    album_id: Optional[int] = None
    variant: str = ""
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    saved_files: int = 0
    bytes: int = 0
    message: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    path: str = ""


class JobManager:
    def __init__(self):
        self._jobs: dict[str, JobProgress] = {}
        self._owners: dict[str, str] = {}
        self._active_keys: dict[tuple[str, str, str, str], str] = {}
        self._lock = threading.Lock()

    def submit_album(
        self,
        client: KidsnoteClient,
        album: dict,
        root: Path,
        variant: str,
        delay: float,
        owner_token: str,
    ) -> tuple[JobProgress, bool]:
        album_id = str(album.get("id", "unknown"))
        active_key = ("album", owner_token, album_id, variant)
        with self._lock:
            existing_id = self._active_keys.get(active_key)
            existing = self._jobs.get(existing_id) if existing_id else None
            if existing and existing.status in {"pending", "running"}:
                return existing, True
            job = JobProgress(
                job_id=str(uuid.uuid4()),
                kind="album",
                subject=album.get("title") or f"앨범 {album.get('id', '')}".strip(),
                album_id=int(album.get("id")) if album.get("id") is not None else None,
                variant=variant,
                total=len(album.get("attached_images") or []),
                path=str(root / str(album.get("id", "unknown"))),
            )
            self._jobs[job.job_id] = job
            self._owners[job.job_id] = owner_token
            self._active_keys[active_key] = job.job_id
        t = threading.Thread(
            target=self._run_album,
            args=(job, active_key, client, album, root, variant, delay),
            daemon=True,
        )
        t.start()
        return job, False

    def submit_child_all(
        self,
        client: KidsnoteClient,
        child_id: int,
        root: Path,
        variant: str,
        delay: float,
        owner_token: str,
        max_albums: Optional[int] = None,
        child_name: str = "",
    ) -> tuple[JobProgress, bool]:
        active_key = ("child", owner_token, str(child_id), variant)
        with self._lock:
            existing_id = self._active_keys.get(active_key)
            existing = self._jobs.get(existing_id) if existing_id else None
            if existing and existing.status in {"pending", "running"}:
                return existing, True
            job = JobProgress(
                job_id=str(uuid.uuid4()),
                kind="child",
                subject=f"{child_name or f'자녀 {child_id}'} 전체 다운로드",
                child_id=child_id,
                variant=variant,
                path=str(root),
            )
            self._jobs[job.job_id] = job
            self._owners[job.job_id] = owner_token
            self._active_keys[active_key] = job.job_id
        t = threading.Thread(
            target=self._run_child_all,
            args=(job, active_key, client, child_id, root, variant, delay, max_albums),
            daemon=True,
        )
        t.start()
        return job, False

    def get_owned(self, job_id: str, owner_token: str) -> Optional[JobProgress]:
        with self._lock:
            if self._owners.get(job_id) != owner_token:
                return None
            return self._jobs.get(job_id)

    def list_owned(self, owner_token: str) -> list[dict]:
        with self._lock:
            return [
                asdict(job)
                for job_id, job in self._jobs.items()
                if self._owners.get(job_id) == owner_token
            ]

    # ---- runners ----

    def _run_album(self, job: JobProgress, active_key: tuple[str, str, str, str],
                   client: KidsnoteClient, album: dict, root: Path,
                   variant: str, delay: float) -> None:
        job.status = "running"
        target = root / str(album.get("id"))
        try:
            images = album.get("attached_images") or []
            target.mkdir(parents=True, exist_ok=True)
            for idx, img in enumerate(images, 1):
                try:
                    url = image_url(img, variant)
                    if not url:
                        job.failed += 1
                        job.message = f"[{idx}/{len(images)}] 다운로드 URL 없음"
                        continue
                    name = image_filename(idx, img, variant)
                    out_path = target / name
                    if out_path.exists() and out_path.stat().st_size > 0:
                        job.skipped += 1
                        job.downloaded += 1
                        job.message = f"[{idx}/{len(images)}] {name} (skip existing)"
                        continue
                    size = client.download_image(url, out_path)
                    if size > 0:
                        job.downloaded += 1
                        job.bytes += size
                        job.message = f"[{idx}/{len(images)}] {name}"
                    else:
                        job.failed += 1
                        job.message = f"[{idx}/{len(images)}] FAILED {name}"
                except Exception as exc:
                    job.failed += 1
                    job.message = f"[{idx}/{len(images)}] 처리 실패: {exc}"
                if delay:
                    time.sleep(delay)
            job.saved_files = _count_saved_files(target)
            job.status = _final_status(job)
            job.message = (
                f"완료: {job.saved_files}개 파일, {job.skipped}개 기존 파일 유지, "
                f"{job.failed}개 실패"
            )
        except Exception as exc:
            job.status = "failed"
            job.message = f"앨범 백업 실패: {exc}"
        finally:
            job.saved_files = _count_saved_files(target)
            job.finished_at = time.time()
            self._release_active_key(active_key, job.job_id)

    def _run_child_all(self, job: JobProgress, active_key: tuple[str, str, str, str],
                       client: KidsnoteClient, child_id: int, root: Path,
                       variant: str, delay: float,
                       max_albums: Optional[int]) -> None:
        job.status = "running"
        try:
            albums = list(client.iter_child_albums(child_id, max_albums=max_albums))
        except Exception as exc:
            job.status = "failed"
            job.message = f"앨범 목록 조회 실패: {exc}"
            job.finished_at = time.time()
            self._release_active_key(active_key, job.job_id)
            return
        try:
            job.total = sum(len(a.get("attached_images") or []) for a in albums)
            for a in albums:
                target = root / str(a.get("id"))
                target.mkdir(parents=True, exist_ok=True)
                imgs = a.get("attached_images") or []
                for idx, img in enumerate(imgs, 1):
                    try:
                        url = image_url(img, variant)
                        if not url:
                            job.failed += 1
                            job.message = f"{a.get('title', '')[:30]} · 다운로드 URL 없음"
                            continue
                        name = image_filename(idx, img, variant)
                        out_path = target / name
                        if out_path.exists() and out_path.stat().st_size > 0:
                            job.skipped += 1
                            job.downloaded += 1
                            job.message = f"{a.get('title', '')[:30]} · {name} (skip existing)"
                            continue
                        size = client.download_image(url, out_path)
                        if size > 0:
                            job.downloaded += 1
                            job.bytes += size
                            job.message = f"{a.get('title', '')[:30]} [{idx}/{len(imgs)}]"
                        else:
                            job.failed += 1
                            job.message = f"{a.get('title', '')[:30]} · FAILED {name}"
                    except Exception as exc:
                        job.failed += 1
                        job.message = f"{a.get('title', '')[:30]} · 처리 실패: {exc}"
                    if delay:
                        time.sleep(delay)
            job.saved_files = _count_saved_files(root)
            job.status = _final_status(job)
            if not albums:
                job.message = "백업할 앨범이 없습니다."
            else:
                job.message = (
                    f"완료: {len(albums)}개 앨범, {job.saved_files}개 파일, "
                    f"{job.skipped}개 기존 파일 유지, {job.failed}개 실패"
                )
        except Exception as exc:
            job.status = "failed"
            job.message = f"전체 백업 실패: {exc}"
        finally:
            job.saved_files = _count_saved_files(root)
            job.finished_at = time.time()
            self._release_active_key(active_key, job.job_id)

    def _release_active_key(self, active_key: tuple[str, str, str, str], job_id: str) -> None:
        with self._lock:
            if self._active_keys.get(active_key) == job_id:
                self._active_keys.pop(active_key, None)


def _count_saved_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and not path.name.endswith(".part"))


def _final_status(job: JobProgress) -> str:
    processed = job.downloaded + job.failed
    if job.total == 0 or (job.failed == 0 and processed >= 0):
        return "done"
    if processed == 0 and job.saved_files == 0:
        return "failed"
    if job.failed > 0 and job.saved_files > 0:
        return "partial"
    if job.failed > 0:
        return "failed"
    return "done"


manager = JobManager()
