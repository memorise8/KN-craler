# 10. Job Status

현재 작업 상태를 빠르게 확인하기 위한 운영 문서.

## Now

- `TODO-011` 코드 서명 적용
  - Windows 번들/설치 프로그램 스크립트는 준비됨
  - 다음 단계에서 SmartScreen 경고를 줄이기 위한 서명 절차를 정리할 예정

## Next

- `TODO-011` 코드 서명 적용
- `TODO-009` 에러/복구 UX 정리
- `TODO-012` 결제 후 라이선스 발급 연결

## Done

- `TODO-001` 로컬 전용 제품 구조 확정
  - 우리 서버는 라이선스 확인만 담당
  - Kidsnote 로그인/세션/다운로드는 사용자 PC 로컬 처리

- `TODO-002` 사용자 데이터 저장 경로 OS별 표준화
  - 기본 저장 경로를 OS별 앱 데이터 폴더로 이동
  - `downloads`, `runtime`, `sessions.sqlite3` 기본 경로 정리

- `TODO-003` 데스크톱 실행 진입점 통합
  - `run.py --desktop` 추가
  - `backend/desktop_app.py` 추가
  - `run.bat`가 데스크톱 창 모드로 실행되도록 변경

- `TODO-004` 라이선스 인증 화면 추가
  - 앱 시작 시 라이선스 상태를 먼저 확인하도록 변경
  - 인증 전에는 로그인/앨범/다운로드 API 접근 차단
  - 임시 로컬 검증용 `license_state.json` 저장 구조 추가

- `TODO-005` 라이선스 서버 최소 기능
  - `license_server.py` 추가
  - 관리자용 키 발급/비활성화 API 추가
  - 앱용 활성화/상태 확인 API 추가
  - 앱 백엔드가 `KIDSNOTE_LICENSE_SERVER_URL` 설정 시 원격 검증을 사용하도록 변경

- `TODO-006` 기기 식별값 생성 및 바인딩
  - `device_identity.py` 추가
  - OS 기반 식별값에서 앱 전용 `device_id` 생성 및 로컬 캐시
  - 원격 라이선스 활성화/검증 시 `device_id`를 함께 전송
  - 같은 기기 재활성화 허용, 다른 기기 활성화 차단

- `TODO-007` 오프라인 유예 정책 적용
  - `KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS` 기본 7일 적용
  - 최근 검증 성공 기록이 있으면 서버 일시 장애 시에도 앱 사용 허용
  - 유예 기간이 0이거나 만료되면 다시 서버 검증이 필요

- `TODO-008` 로그인/백업 핵심 플로우 안정화
  - 동일 앨범/동일 자녀 전체 백업 중복 요청 시 기존 진행 중 잡 재사용
  - `done/partial/failed` 상태 구분 및 저장 파일 수 노출
  - 저장 파일이 0개면 ZIP 다운로드 차단
  - 자녀/앨범 화면에서 진행 중인 백업 버튼 잠금
  - 자녀 앨범 목록 재진입 시 중복 로딩/중복 카드 생성 방지

- `TODO-010` Windows 패키징 및 설치 프로그램
  - `desktop_app.py`가 내장 uvicorn 스레드 기반으로 동작하도록 변경
  - 번들 자원 경로 해석용 `bundle_paths.py` 추가
  - `packaging/windows/build_windows.py` 빌드 스크립트 추가
  - `packaging/windows/installer.iss` Inno Setup 정의 추가
  - `packaging/windows/requirements-build.txt`로 PyInstaller 빌드 의존성 분리

## Blocked

- 현재 치명적인 블로커 없음
- 다만 실제 Windows에서 Inno Setup으로 `.exe` 설치 프로그램을 컴파일하는 마지막 단계는 별도로 확인 필요

## Validation

- `python3 run.py --desktop --desktop-smoke-test --port 8882`
  - 로컬 서버 기동/정리 확인
  - `/api/health` 응답 확인

- `python3 run.py --skip-install --port 8883`
  - `/` HTML 서빙 확인

- `python3 -m py_compile run.py backend/desktop_app.py backend/main.py backend/app_paths.py`
  - 문법 검증 통과

- `TMP_HOME=$(mktemp -d) ... python3 run.py --skip-install --port 8884`
  - 초기 라이선스 상태 `inactive` 확인
  - 비활성 상태에서 `/api/login`이 `403`으로 차단되는지 확인
  - `/api/license/activate` 후 상태가 `active`로 바뀌는지 확인

- `license_server -> issue -> app activate -> revoke -> app status`
  - 키 발급 확인
  - 앱 원격 활성화 확인
  - 서버 revoke 후 앱 상태가 `inactive`로 반영되는지 확인

- `device_identity -> remote activate -> same device re-activate -> different device reject`
  - 서로 다른 앱 홈에서 계산한 기기 ID가 같은지 확인
  - 같은 `device_id`로 재활성화가 허용되는지 확인
  - 다른 `device_id`에서는 동일 키가 `license bound to another device`로 거절되는지 확인
  - `device_id` 없는 서버 검증 요청이 `device id required`로 거절되는지 확인

- `remote activate -> server down -> offline grace allow/block`
  - 최근 검증 성공 기록이 있으면 `remote_server_grace` 상태로 계속 사용 가능한지 확인
  - `KIDSNOTE_LICENSE_OFFLINE_GRACE_DAYS=0`에서는 서버 장애 시 즉시 차단되는지 확인

- `job manager duplicate guard + partial completion`
  - 동일 앨범 백업 요청이 진행 중일 때 기존 잡이 재사용되는지 확인
  - 일부 파일 실패 시 잡 상태가 `partial`로 남고 저장 파일 수가 집계되는지 확인
  - 자녀 전체 백업도 일부 실패 시 `partial`로 끝나는지 확인

- `desktop smoke test + PyInstaller bundle validation`
  - `python3 run.py --desktop --desktop-smoke-test --skip-install --port 8888` 통과
  - `python3 packaging/windows/build_windows.py --allow-non-windows --bundle-only --install-build-deps`로 PyInstaller 번들 생성 확인
  - 생성된 번들 실행 파일 `dist/windows/app/KidsnoteBackup/KidsnoteBackup --smoke-test --port 8892` 통과

## Notes

- 현재 기준 주 실행 경로:
  - Windows: `run.bat`
  - macOS/Linux 개발: `./run.sh`
  - 데스크톱 모드 직접 실행: `python3 run.py --desktop`

- 실제 제품 방향:
  - 설치형 로컬 앱
  - `1인 1기기` 라이선스
  - 우리 서버는 라이선스 상태만 확인
  - Kidsnote 로그인은 사용자 개인 계정으로 로컬에서 직접 처리
