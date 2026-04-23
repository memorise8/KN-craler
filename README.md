# Kidsnote Photo Grabber

독립 실행형 풀스택 앱. Kidsnote 학부모 계정으로 로그인하면 자녀의 모든 앨범과 사진을 조회/다운로드할 수 있습니다.

## 구조

```
kidsnote-app/
├── backend/                    FastAPI 서버
│   ├── kidsnote_client.py      독립형 Kidsnote API 클라이언트 (requests만 사용)
│   ├── device_identity.py      1인 1기기 바인딩용 로컬 device_id 생성
│   ├── session_store.py        SQLite 세션 저장소 (2시간 TTL)
│   ├── job_manager.py          백그라운드 다운로드 잡 관리 (스레드)
│   ├── main.py                 FastAPI 앱
│   └── requirements.txt
├── frontend/                   바닐라 JS SPA (빌드 불필요)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── run.py                      크로스플랫폼 실행 런처
├── backend/desktop_app.py      데스크톱 앱 창 진입점
├── run.bat                     Windows 실행 스크립트
├── run.sh                      macOS/Linux 실행 스크립트
└── README.md
```

기본 사용자 데이터 위치:

- Windows: `%LOCALAPPDATA%\KidsnoteBackup\`
- macOS: `~/Library/Application Support/KidsnoteBackup/`
- Linux: `~/.local/share/KidsnoteBackup/`

## 실행

### Windows

```bat
cd kidsnote-app
run.bat
```

`run.bat`는 로컬 서버를 띄운 뒤 네이티브 앱 창으로 실행합니다.

또는:

```bat
py -3 run.py --desktop
```

Windows 배포 번들/설치 프로그램 빌드:

```bat
cd kidsnote-app
backend\.venv\Scripts\python.exe packaging\windows\build_windows.py --install-build-deps
```

- PyInstaller 번들만 만들려면: `--bundle-only`
- Inno Setup 경로를 직접 지정하려면: `--iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`

### macOS / Linux

```bash
cd kidsnote-app
./run.sh
```

또는:

```bash
python3 run.py --reload --host 0.0.0.0
```

데스크톱 창으로 실행하려면:

```bash
python3 run.py --desktop
```

### 수동 실행

```bash
cd kidsnote-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8787 --reload
```

macOS/Linux는 브라우저에서 `http://localhost:8787`로 접속하고, Windows의 `run.bat`는 데스크톱 앱 창으로 실행됩니다.

## 환경변수 (선택)

- `KIDSNOTE_APP_HOME` — 앱 데이터 루트 경로
- `KIDSNOTE_RUNTIME_ROOT` — 런타임 폴더 경로 (기본: 앱 데이터 루트의 `runtime`)
- `KIDSNOTE_DOWNLOAD_ROOT` — 다운로드 폴더 경로 (기본: 앱 데이터 루트의 `downloads`)
- `KIDSNOTE_LICENSE_SERVER_URL` — 원격 라이선스 서버 URL
- `KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS` — 원격 서버 장애 시 최근 검증 기록으로 허용할 오프라인 유예 일수 (기본 7)
- `KIDSNOTE_DEFAULT_VARIANT` — 기본 해상도 (`original`|`large`|`small_resize`|`small`, 기본 `large`)
- `KIDSNOTE_DELAY` — 이미지 간 딜레이 초 (기본 0.1)
- `KIDSNOTE_SESSION_DB` — 세션 SQLite 파일 경로 (기본: 런타임 폴더의 `sessions.sqlite3`)
- `KIDSNOTE_DEVICE_ID` — 테스트/복구용 기기 식별값 강제 지정
- `KIDSNOTE_DEVICE_ID_FILE` — 로컬 기기 식별값 캐시 파일 경로 (기본: 런타임 폴더의 `device_identity.json`)
- `KIDSNOTE_ALLOWED_ORIGINS` — CORS 허용 오리진 CSV (기본: `http://localhost:8787,http://127.0.0.1:8787`)
- `KIDSNOTE_COOKIE_SECURE` — HTTPS 배포 시 `true`
- `KIDSNOTE_COOKIE_SAMESITE` — 쿠키 SameSite 값 (기본 `lax`)

## 주요 기능

- **라이선스 게이트** — 앱 시작 시 라이선스 인증이 먼저 필요하며, 활성화 전에는 로그인/다운로드 기능이 잠겨 있음.
- **1인 1기기 바인딩** — 앱이 로컬 기기 식별값을 생성해 라이선스 서버와 함께 검증하며, 같은 기기 재설치는 허용하고 다른 기기 재활성화는 차단.
- **오프라인 유예** — 최근 원격 검증 성공 기록이 있으면 서버 일시 장애 시에도 일정 기간 앱 사용을 허용.
- **Kidsnote 계정으로 직접 로그인** — 별도 가입 없음. 서버는 id/pw를 저장하지 않으며, `sessionid` 쿠키만 SQLite 세션 저장소에 유지.
- **Windows 패키징 준비** — `packaging/windows/build_windows.py`와 `installer.iss`로 배포 번들과 설치 프로그램 생성 경로를 제공.
- **자녀 자동 조회** — 로그인 후 `/api/v1/me/info/`로부터 자녀 목록 표시.
- **앨범 페이지네이션** — 커서 기반 "더 불러오기" 방식.
- **앨범 상세 갤러리** — 썸네일 그리드 + 클릭 시 라이트박스.
- **백그라운드 다운로드** — 앨범별 또는 자녀 전체를 스레드로 실행. 진행률은 우하단 패널에서 2초마다 폴링.
- **중복 백업 방지** — 같은 앨범/같은 자녀 전체 백업이 이미 진행 중이면 기존 작업을 재사용.
- **부분 완료 구분** — 일부 파일이 실패해도 `partial` 상태와 저장 파일 수를 보여 주고, 받은 파일이 있으면 ZIP 수령 가능.
- **ZIP 결과 전달** — 완료된 작업은 `/api/jobs/{id}/zip`으로 브라우저에서 바로 받을 수 있으며, 저장 파일이 하나도 없으면 ZIP 생성이 차단됨.
- **"로그인 후 전체 자동 다운로드" 체크박스** — 로그인과 동시에 모든 자녀의 모든 앨범을 `large` 해상도로 다운로드 시작.
- **중복 스킵** — 파일명이 이미 존재하면 재다운로드하지 않아 resume 지원.

## API 엔드포인트 (요약)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/login` | id/pw 로그인 → 세션 쿠키 설정 |
| POST | `/api/logout` | 로그아웃 |
| GET  | `/api/me` | 현재 사용자 + 자녀 목록 |
| GET  | `/api/children/{id}/albums?page=<cursor>` | 앨범 목록 (페이지네이션) |
| GET  | `/api/albums/{id}` | 앨범 상세 (이미지 URL 포함) |
| POST | `/api/albums/{id}/download` | 특정 앨범 다운로드 시작 |
| POST | `/api/children/{id}/download-all` | 자녀의 모든 앨범 다운로드 시작 |
| GET  | `/api/jobs` | 실행 중/완료된 잡 목록 |
| GET  | `/api/jobs/{id}` | 특정 잡 진행률 |
| GET  | `/api/jobs/{id}/zip` | 완료된 잡 결과 ZIP 다운로드 |

## 보안 고려사항

- **자격증명**: 절대 디스크에 저장되지 않음. 브라우저는 httpOnly 세션 쿠키만 받음.
- **세션 저장**: 재시작 복구를 위해 Kidsnote `sessionid`만 SQLite에 저장. 계정 ID/PW는 저장하지 않음.
- **세션 만료**: 2시간 비활성 시 서버 측 세션 삭제.
- **CORS**: `KIDSNOTE_ALLOWED_ORIGINS`로 제한.
- **HTTPS 권장**: 배포 시 `KIDSNOTE_COOKIE_SECURE=true`로 설정 필요.

## 스탠드얼론 client로 사용

`backend/kidsnote_client.py`는 FastAPI에 독립적입니다. 다른 스크립트에서 직접 사용 가능:

```python
from kidsnote_client import KidsnoteClient

c = KidsnoteClient()
c.login("memorise8", "password")
for album in c.iter_child_albums(5066947, max_albums=5):
    print(album["title"], len(album["attached_images"]))
```
