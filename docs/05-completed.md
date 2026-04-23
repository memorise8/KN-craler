# 05. 완료된 기능 (MVP)

현 시점 (2026-04-23) 기준 동작 검증이 끝난 기능 목록.

## ✅ 백엔드

### 독립형 Kidsnote 클라이언트 (`kidsnote_client.py`)
- [x] `login(username, password, retries=3)` — form-encoded POST + sessionid 쿠키 검증, 3회 재시도(지수 백오프).
- [x] `restore_session(sessionid)` — 기존 sessionid를 직접 주입.
- [x] `get_me()` — `/api/v1/me/info/` 호출 + 401/403 시 `KidsnoteAuthError`.
- [x] `list_children()` — me 응답에서 자녀 요약 추출.
- [x] `iter_child_albums(child_id, page_size=30, max_albums=None)` — 제너레이터로 커서 페이지네이션 순회.
- [x] `fetch_album(album_id)` — 앨범 상세.
- [x] `download_image(url, out_path, retries=3)` — 스트림 다운로드 + `.part` → 최종 이름 원자적 rename, 3회 재시도.
- [x] `sanitize_filename`, `image_filename`, `image_url` 유틸.
- [x] 프레임워크 비의존 — 다른 스크립트에서 `from kidsnote_client import KidsnoteClient`로 바로 사용 가능.

### 세션 스토어 (`session_store.py`)
- [x] SQLite 기반 세션 저장소 (기본: OS별 앱 데이터 폴더의 `runtime/sessions.sqlite3`).
- [x] 기본 TTL 2시간, 슬라이딩 윈도우 (`get()` 호출 시 `last_seen_at` 갱신).
- [x] `create / get / delete / prune`.
- [x] Kidsnote `sessionid` 복원으로 서버 재시작 후 로그인 유지.

### 잡 매니저 (`job_manager.py`)
- [x] `submit_album(...)` — 단일 앨범 다운로드 잡.
- [x] `submit_child_all(...)` — 자녀의 전 앨범 순회 + 다운로드.
- [x] 진행률 필드: `total / downloaded / skipped / failed / bytes / message / status`.
- [x] 기존 파일 스킵 로직 — 재개 지원.
- [x] daemon 스레드 실행 → 메인 프로세스 종료 시 잡도 정리.
- [x] 세션 소유권 기준으로 잡 목록 격리.

### FastAPI 라우터 (`main.py`)
- [x] `POST /api/login` — `auto_prefetch` 파라미터 수신 (실제 프리패치 실행은 프론트에서 처리).
- [x] `POST /api/logout`, `GET /api/me`.
- [x] `GET /api/license/status`, `POST /api/license/activate`, `POST /api/license/deactivate`.
- [x] `KIDSNOTE_LICENSE_SERVER_URL` 설정 시 원격 라이선스 서버 검증 사용, 미설정 시 로컬 임시 검증 fallback.
- [x] 로컬 `device_id` 생성 및 원격 라이선스 검증 연동.
- [x] 같은 기기 재활성화 허용, 다른 기기 활성화 차단.
- [x] 최근 원격 검증 성공 기록 기준 오프라인 유예 (`KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS`, 기본 7일).
- [x] `GET /api/children/{id}/albums?page=<cursor>&page_size=30` — Kidsnote의 next 커서를 그대로 전달/반환.
- [x] `GET /api/albums/{id}` — 이미지 variant URL 모두 포함.
- [x] `POST /api/albums/{id}/download`, `POST /api/children/{id}/download-all`.
- [x] `GET /api/jobs`, `GET /api/jobs/{id}`.
- [x] `GET /api/jobs/{id}/zip` — 완료된 작업 결과 ZIP 다운로드.
- [x] 동일 대상 중복 백업 요청 시 기존 진행 중 잡 재사용.
- [x] 잡 상태를 `done/partial/failed`로 구분하고 저장 파일 수를 반환.
- [x] 저장 파일이 없는 경우 ZIP 생성 차단.
- [x] `GET /api/health`.
- [x] 정적 파일 서빙 (`/` → `index.html`, `/static/*` → frontend 디렉터리).
- [x] 환경변수: `KIDSNOTE_DOWNLOAD_ROOT`, `KIDSNOTE_DEFAULT_VARIANT`, `KIDSNOTE_DELAY`, `KIDSNOTE_SESSION_DB`, `KIDSNOTE_ALLOWED_ORIGINS`, `KIDSNOTE_COOKIE_SECURE`, `KIDSNOTE_COOKIE_SAMESITE`.
- [x] OS별 앱 데이터 기본 경로 (`KIDSNOTE_APP_HOME`, `KIDSNOTE_RUNTIME_ROOT` 포함).

## ✅ 프론트엔드

### SPA 셸 + 스타일
- [x] `index.html` — 헤더, 뷰 컨테이너, 우하단 잡 패널.
- [x] `style.css` — 제품형 랜딩/대시보드 스타일, 라이트박스, 진행 바, 토스트.
- [x] 빌드 툴체인 없음 — 브라우저가 직접 로드.

### 뷰/라우팅 (`app.js`)
- [x] `viewLogin` — ID/PW 폼 + "로그인 후 전체 자동 다운로드" 체크박스.
- [x] `viewChildren` — 자녀 카드 그리드 (프로필 사진 + 이름).
- [x] `viewAlbums` — 앨범 카드 그리드, 커서 기반 "더 불러오기" 페이지네이션.
- [x] `viewAlbum` — 썸네일 갤러리 + 클릭 시 라이트박스(ESC 닫기).
- [x] Breadcrumb 네비게이션.

### 액션
- [x] 라이선스 게이트 — 인증 전 앱 잠금.
- [x] 로그인 / 로그아웃.
- [x] 앨범 단위 다운로드.
- [x] 자녀 전체 다운로드.
- [x] 로그인 직후 전체 자동 다운로드 토글.
- [x] `pollJobs()` — 2초 간격으로 진행률 폴링.
- [x] 완료된 작업 ZIP 다운로드 액션.
- [x] 자녀/앨범 화면에서 진행 중인 백업 버튼 잠금.
- [x] 자녀 앨범 화면 재진입 시 중복 로딩 방지.
- [x] 전역 토스트 기반 오류/성공 피드백.

## ✅ 엔드투엔드 검증 (재확인 필요)

최초 개발 시 다음 시나리오가 통과했습니다 (환경 변동 가능):
- Health endpoint — `{"status":"ok","service":"kidsnote-app"}`
- 로그인 — `memorise8 (성원준)` + 자녀 2명 인식
- 앨범 페이지네이션 — 3개 / `next: cD0xNTc1MDM4NzQ=`
- 앨범 상세 — 55 images + 썸네일 URL
- 다운로드 잡 — 35/55 (약 4초, 1.26MB)
- 정적 파일 서빙 — `/` 665B, `/static/app.js` 14KB

## ✅ 운영 편의
- [x] `run.py` — 크로스플랫폼 실행 런처 (Windows/macOS/Linux).
- [x] `backend/desktop_app.py` — 로컬 서버 + 네이티브 데스크톱 창 실행 진입점.
- [x] `backend/bundle_paths.py` — PyInstaller 번들 환경의 정적 자원 경로 해석.
- [x] `run.bat` — Windows에서 데스크톱 창 모드로 실행.
- [x] `run.sh` — macOS/Linux 개발용 실행 스크립트 (`--reload`).
- [x] `backend/license_server.py` — 최소 라이선스 서버.
- [x] `backend/license_admin.py` — 관리자용 키 발급/비활성화 CLI.
- [x] `backend/device_identity.py` — 기기 식별값 생성/캐시.
- [x] `packaging/windows/build_windows.py` — Windows 번들/설치 프로그램 빌드 스크립트.
- [x] `packaging/windows/installer.iss` — Inno Setup 설치 프로그램 정의.
- [x] `.gitignore` — `.venv`, `__pycache__`, `downloads/`, `*.log`, `.DS_Store`.
- [x] `README.md` — 실행 + 환경변수 + 엔드포인트 요약.
