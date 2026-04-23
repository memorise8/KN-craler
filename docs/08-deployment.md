# 08. 배포 / 운영

## 로컬 실행

```bash
cd kidsnote-app
./run.sh                      # macOS/Linux: 최초엔 .venv 생성 + requirements 설치
# Windows:
run.bat
# 또는 수동:
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8787 --reload
```

브라우저 http://localhost:8787 접속 → 로그인 페이지.
Windows의 `run.bat`는 브라우저 대신 데스크톱 앱 창으로 실행된다.

## Windows 패키징

### 번들 빌드

Windows에서 PowerShell 또는 `cmd` 기준:

```bat
cd kidsnote-app
backend\.venv\Scripts\python.exe packaging\windows\build_windows.py --install-build-deps --bundle-only
```

결과물:

- 번들 디렉터리: `dist\windows\app\KidsnoteBackup\`
- 실행 파일: `dist\windows\app\KidsnoteBackup\KidsnoteBackup.exe`

### 설치 프로그램 빌드

Inno Setup 6 설치 후:

```bat
cd kidsnote-app
backend\.venv\Scripts\python.exe packaging\windows\build_windows.py --install-build-deps
```

Inno Setup 경로를 직접 지정하려면:

```bat
backend\.venv\Scripts\python.exe packaging\windows\build_windows.py --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

결과물:

- 설치 프로그램: `dist\windows\installer\KidsnoteBackup-Setup-<version>.exe`

### 패키징 파일

- 빌드 스크립트: `packaging/windows/build_windows.py`
- Inno Setup 정의: `packaging/windows/installer.iss`
- 빌드 의존성: `packaging/windows/requirements-build.txt`

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8787` | uvicorn 리스닝 포트 (`run.sh`) |
| `KIDSNOTE_APP_HOME` | OS별 앱 데이터 폴더 | 앱 전용 데이터 루트 |
| `KIDSNOTE_RUNTIME_ROOT` | `<APP_HOME>/runtime` | SQLite 세션 DB 등 런타임 파일 위치 |
| `KIDSNOTE_DOWNLOAD_ROOT` | `<APP_HOME>/downloads` | 사진 저장 루트. `{username}/{child_id}/{album_id}/` 하위 생성 |
| `KIDSNOTE_LICENSE_SERVER_URL` | 빈 값 | 원격 라이선스 서버 URL |
| `KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS` | `7` | 라이선스 서버 장애 시 최근 검증 성공 기록으로 허용할 오프라인 유예 일수 |
| `KIDSNOTE_DEFAULT_VARIANT` | `large` | 다운로드 기본 해상도. `original \| large \| small_resize \| small` |
| `KIDSNOTE_DELAY` | `0.1` | 이미지 간 딜레이(초). rate limit 방어용 |
| `KIDSNOTE_SESSION_DB` | `<RUNTIME_ROOT>/sessions.sqlite3` | 세션 SQLite 파일 위치 |
| `KIDSNOTE_DEVICE_ID` | 자동 생성 | 테스트/복구용 기기 식별값 강제 지정 |
| `KIDSNOTE_DEVICE_ID_FILE` | `<RUNTIME_ROOT>/device_identity.json` | 로컬 기기 식별값 캐시 위치 |
| `KIDSNOTE_ALLOWED_ORIGINS` | `http://localhost:8787,http://127.0.0.1:8787` | CORS 허용 오리진 CSV |
| `KIDSNOTE_COOKIE_SECURE` | `false` | HTTPS 배포 시 `true` 권장 |
| `KIDSNOTE_COOKIE_SAMESITE` | `lax` | 세션 쿠키 SameSite 설정 |
| `KIDSNOTE_BUILD_PYTHON` | backend `.venv` 우선 | Windows 번들 빌드에 사용할 Python 실행 파일 |
| `ISCC_EXE` | 자동 탐색 | Inno Setup `ISCC.exe` 경로 |

## 배포 시 체크리스트

### HTTPS 필수
- 세션 쿠키(`kn_session`)는 httpOnly지만 HTTP로는 평문 전송. MITM 시 탈취 가능.
- 리버스 프록시(Caddy/Nginx)로 TLS 종단 처리 권장.
- 배포 환경에서는 `KIDSNOTE_COOKIE_SECURE=true` 설정 필요.

### CORS 설정
- `KIDSNOTE_ALLOWED_ORIGINS`에 구체적 오리진을 지정:
  ```bash
  export KIDSNOTE_ALLOWED_ORIGINS="https://kidsnote.example.com"
  export KIDSNOTE_COOKIE_SECURE=true
  ```

### Reverse proxy 예시 (Caddy)
```
kidsnote.example.com {
  encode gzip
  reverse_proxy localhost:8787
}
```

### systemd 유닛 예시
```ini
[Unit]
Description=Kidsnote Photo Grabber
After=network.target

[Service]
WorkingDirectory=/opt/kidsnote-app/backend
Environment=KIDSNOTE_DOWNLOAD_ROOT=/var/lib/kidsnote/downloads
ExecStart=/opt/kidsnote-app/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8787
Restart=on-failure
User=kidsnote

[Install]
WantedBy=multi-user.target
```

> `--workers N` 금지 — 현재는 **단일 프로세스만 지원** (잡 매니저가 프로세스 메모리 기반).
> 세션은 SQLite에 저장되지만, 다운로드 잡 상태는 여전히 단일 프로세스 메모리 기반이다.

### 디스크 용량 계획
- `original` variant 기준 평균 3~8MB/장. 한 아이 수백 앨범 = 수만 장 = 수백 GB 가능.
- 앱 데이터 폴더의 `downloads/` 디렉터리가 위치한 볼륨의 여유 공간을 사전 확보.

### 로그
- 현재 structured 로깅 미도입. `uvicorn`의 access log와 예외 stderr만 존재.
- 장기적으론 JSON 로그 + rotation (`logrotate` 또는 Python `logging.handlers.RotatingFileHandler`).

## 업그레이드 절차

1. `git pull`로 코드 갱신.
2. `./.venv/bin/pip install -r backend/requirements.txt --upgrade`.
3. `systemctl restart kidsnote-app`.
4. 세션 DB를 유지하면 로그인 세션은 복구되지만, 진행 중이던 잡은 복구되지 않음.

### Windows 설치형 앱 업그레이드

1. 새 버전으로 `packaging/windows/build_windows.py`를 다시 실행.
2. 생성된 새 설치 프로그램으로 덮어 설치.
3. 앱 데이터는 `%LOCALAPPDATA%\KidsnoteBackup\`에 남아 있으므로 라이선스 상태와 세션, 다운로드 파일은 유지된다.

## 백업 전략

- **세션**: 현재 휘발성 — 백업 불필요.
- **다운로드 파일**: `KIDSNOTE_DOWNLOAD_ROOT` 전체를 rsync/restic 등으로 주기 백업.
- **코드**: Git 저장소 자체가 정답.

## 문제 해결

| 증상 | 원인/확인 |
|---|---|
| 로그인은 되는데 모든 요청이 401 | 쿠키가 설정 안됨 → CORS/secure 플래그 확인, 프론트에서 `credentials: "include"` 여부 |
| 다운로드가 시작만 되고 안 찜 | `KIDSNOTE_DOWNLOAD_ROOT` 쓰기 권한 확인 |
| 앨범 목록이 비어 있음 | Kidsnote sessionid 만료 — 재로그인 필요. 콘솔 로그에서 `KidsnoteAuthError` 확인 |
| `uvicorn` 재시작 후 계속 로그인 요구 | 세션 DB 경로/권한 확인, 또는 SQLite 파일이 초기화되었는지 확인 |
| 이미지가 403 | CDN URL이 만료되었거나 network 정책 문제 — sessionid 갱신해 앨범 재요청 |
