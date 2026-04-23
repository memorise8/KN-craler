# 02. 아키텍처

## 폴더 레이아웃

```
kidsnote-app/
├── backend/
│   ├── kidsnote_client.py    독립형 Kidsnote HTTP 클라이언트 (requests만 사용)
│   ├── session_store.py      SQLite 세션 저장소 (token → sessionid)
│   ├── job_manager.py        백그라운드 다운로드 잡 매니저 (thread 기반)
│   ├── main.py               FastAPI 라우터 + 정적 파일 서빙
│   └── requirements.txt
├── frontend/
│   ├── index.html            SPA 셸
│   ├── app.js                바닐라 JS 뷰/상태/라우팅
│   └── style.css
├── docs/                     ← 이 문서 폴더
├── run.py                    크로스플랫폼 실행 런처
├── backend/desktop_app.py    로컬 서버 + 데스크톱 창 진입점
├── run.bat                   Windows 실행 스크립트
├── run.sh                    macOS/Linux 실행 스크립트
└── README.md
```

런타임 데이터 기본 위치:

- Windows: `%LOCALAPPDATA%\KidsnoteBackup\`
- macOS: `~/Library/Application Support/KidsnoteBackup/`
- Linux: `~/.local/share/KidsnoteBackup/`

## 런타임 구성

단일 `uvicorn` 프로세스가 FastAPI 앱을 호스팅하고, `/static/*`로 프론트 정적 파일을 서빙. 같은 오리진에서 API + 프론트를 모두 처리하므로 CORS 이슈 없음.

```
┌────────────────┐      HTTP + kn_session cookie      ┌──────────────────────┐
│ Browser (SPA)  │ ─────────────────────────────────▶ │ FastAPI (uvicorn)    │
│ app.js         │ ◀───────── JSON ──────────────────│ main.py              │
└────────────────┘                                    │  ├─ SessionStore     │
│  ├─ JobManager (🧵)  │
│  └─ KidsnoteClient   │
                                                      └──────────┬───────────┘
                                                                 │ sessionid cookie
                                                                 ▼
                                                      ┌──────────────────────┐
                                                      │ www.kidsnote.com     │
                                                      │  /sb-login           │
                                                      │  /api/v1/me/info/    │
                                                      │  /api/v1/children/…  │
                                                      │  /api/v1/albums/…    │
                                                      └──────────────────────┘
                                                                 │ 이미지 CDN
                                                                 ▼
                                                      ┌──────────────────────┐
                                                      │ up-kids-kage.kakao   │
                                                      │  .com (public)       │
                                                      └──────────────────────┘
```

## 핵심 컴포넌트

### `kidsnote_client.py`
- **역할**: Kidsnote 외부 API 호출 전담. FastAPI에 독립적이어서 다른 스크립트에서도 `from kidsnote_client import KidsnoteClient`로 바로 재사용.
- **주요 메서드**: `login()`, `get_me()`, `list_children()`, `iter_child_albums()`, `fetch_album()`, `download_image()`.
- **상태**: `requests.Session` 내부 쿠키 자(`sessionid`) + 마지막 `me` 캐시.

### `app_paths.py`
- **역할**: 설치형 로컬 앱 관점에서 사용할 기본 저장 경로를 OS별 사용자 폴더로 계산.
- **재정의**: `KIDSNOTE_APP_HOME`, `KIDSNOTE_RUNTIME_ROOT`, `KIDSNOTE_DOWNLOAD_ROOT`, `KIDSNOTE_SESSION_DB`.

### `bundle_paths.py`
- **역할**: PyInstaller 번들 환경과 소스 실행 환경에서 프런트 정적 파일 경로를 동일하게 해석.
- **효과**: 설치형 `.exe`로 실행해도 `/`와 `/static/*`가 같은 방식으로 서빙된다.

### `device_identity.py`
- **역할**: `1인 1기기` 라이선스 정책을 위한 로컬 `device_id` 생성.
- **동작**: Windows는 `MachineGuid`, macOS는 `IOPlatformUUID`, Linux는 `machine-id`를 우선 사용하고, 불가할 때만 랜덤 fallback.
- **저장**: 기본적으로 앱 데이터 폴더의 `runtime/device_identity.json`에 캐시.

### `desktop_app.py`
- **역할**: 로컬 FastAPI 서버를 서브프로세스로 띄우고, 준비가 끝나면 네이티브 앱 창을 열어 실행.
- **종료 처리**: 앱 창이 닫히면 로컬 서버도 같이 정리.

### `session_store.py`
- **역할**: 브라우저 세션 토큰(`kn_session` 쿠키) → `sessionid`/사용자 메타데이터를 SQLite에 저장하고, 요청 시 `KidsnoteClient`를 복원.
- **TTL**: 기본 2시간 (`DEFAULT_TTL_SECONDS`). `get()` 호출 시 `last_seen_at` 갱신.
- **보안**: username/password는 저장하지 않음. 오직 `sessionid`만 런타임 DB에 유지.
- **효과**: 서버 재시작 후에도 브라우저 쿠키가 유효하면 다시 로그인하지 않아도 됨.

### `job_manager.py`
- **역할**: 다운로드 백그라운드 실행 + 진행률 추적.
- **잡 종류**: `album` (특정 앨범), `child` (자녀의 전체 앨범).
- **실행**: `daemon=True` 스레드, 상태/카운터는 `JobProgress` dataclass에 적재.
- **정책**: 기존 파일이 존재하면 `skipped` 카운트로 처리해 재개 지원.
- **소유권**: 잡은 생성 세션 기준으로 격리되어, 다른 사용자의 작업 목록이 노출되지 않음.

### `main.py`
- **역할**: FastAPI 라우터. `require_session()` 의존성 함수로 모든 보호된 엔드포인트 앞단에 인증 검사.
- **라이선스**: `license_service.py`를 통해 원격 라이선스 서버 상태와 로컬 `device_id`를 함께 확인.
- **오프라인 유예**: 최근 원격 검증 성공 기록이 있으면 일정 기간 `remote_server_grace` 상태로 앱 사용 허용.
- **세션 쿠키**: `kn_session` — httpOnly, sameSite/secure/max_age를 환경변수 기반으로 설정.
- **다운로드 루트**: 기본적으로 OS별 앱 데이터 폴더의 `downloads/{username}/{child_id}/{album_id}/`.
- **결과 전달**: 완료된 다운로드 경로를 임시 ZIP으로 묶어 `/api/jobs/{id}/zip`에서 제공.

### 프론트엔드
- **상태 관리**: 전역 `state` 객체 하나 (user, children, view, albumsByChild, jobs).
- **라우팅**: `state.view` 스위치로 `viewLogin | viewChildren | viewAlbums | viewAlbum` 렌더.
- **페이지네이션**: 페이지 단위 더보기 버튼으로 커서 페이지네이션.
- **진행률 폴링**: `pollJobs()`가 `setTimeout` 2s 간격으로 `/api/jobs` 호출.
- **라이트박스**: 갤러리 이미지 클릭 시 `<div class="lightbox">` 오버레이 + ESC 닫기.
- **피드백**: 토스트, 상태 배지, ZIP 다운로드 액션 제공.

## 데이터 흐름 (전체 다운로드 시나리오)

1. `POST /api/login` → `KidsnoteClient.login()` → 세션 쿠키 생성 → `{user, children}` 반환.
2. 프론트 `state.children` 저장 → `viewChildren` 렌더.
3. 사용자가 "전체 다운로드" 클릭 → `POST /api/children/{id}/download-all`.
4. `JobManager.submit_child_all()` → 새 스레드 시작.
5. 스레드가 `iter_child_albums()`로 페이지네이션하며 전 앨범 수집, 순차적으로 각 이미지 `download_image()`.
6. 프론트 `pollJobs()`가 2초마다 `/api/jobs/{id}` 폴링 → progress bar 갱신.
