# 07. 알려진 이슈 / 한계점

현재 MVP 상태에서 **의도적으로 타협한 부분** 또는 **운영 중 발견된 문제**.

## 설계상 한계 (Known Limitations)

### L1. 단일 프로세스 전용
- `SessionStore`는 SQLite라서 재시작 복구는 되지만, `JobManager`는 여전히 프로세스 메모리 기반. `uvicorn --workers N`을 사용하면 진행 중 잡 상태가 워커마다 갈라짐.
- **대응 계획**: 큐/워커 분리 또는 Redis 기반 잡 저장소 도입.

### L2. 리로드 시 세션/잡 휘발
- `--reload` 중 코드 편집 → 프로세스 재시작 시 **로그인 세션은 복구되지만**, 진행 중이던 잡 상태는 사라진다.
- 개발 편의상 현 상태로 유지. 운영 배포 시에는 `--reload` 끄기.

### L3. 잡은 취소 불가
- `JobManager.submit_*`가 daemon 스레드 제출 후 중단 API 없음.
- 큰 잡을 시작하면 완료/오류까지 기다려야 함.
- **대응 계획**: `threading.Event`를 `JobProgress`에 추가하고 루프 안에서 주기적으로 체크.

### L4. 다운로드 루트 쓰기 권한
- `KIDSNOTE_DOWNLOAD_ROOT` (기본: OS별 앱 데이터 폴더의 `downloads`)에 대한 쓰기 권한 없으면 잡이 조용히 실패.
- `main.py`가 시작 시 mkdir 시도 — 실패하면 프로세스가 크래시.

### L5. 대형 앨범의 UI 경험
- `viewAlbum`은 전체 썸네일을 한 번에 렌더. 500+ 장 앨범에서 느릴 수 있음.
- 가상 스크롤 (react-window류) 미도입.

## 보안 관련 주의

### S1. CSRF 미대응
- `/api/*` POST 경로에 CSRF 토큰 없음. `SameSite=Lax` 쿠키로 어느 정도 막히지만, 강화된 방어 필요.

### S2. CORS `*` 고정
- 기본값은 로컬 오리진으로 제한되지만, 운영 환경에서 `KIDSNOTE_ALLOWED_ORIGINS`를 명시하지 않으면 외부 도메인 프런트와 연결되지 않음.

### S3. 평문 sessionid in memory
- 프로세스 메모리 덤프 시 sessionid 노출. 고보안 환경 부적합.

### S4. 로그에 민감 정보 출력 가능성
- 현재 예외 메시지에 URL + username이 섞여 나올 수 있음. 프로덕션 로깅 시 마스킹 필요.

## Kidsnote API 리버스 엔지니어링 이슈

### R1. 페이지네이션 파라미터가 공식 문서 없음
- `page=<base64 cursor>` 형식은 JS 번들 분석으로 얻은 사실. Kidsnote가 언젠가 DRF의 기본 cursor pagination으로 바꾸면 깨질 수 있음.
- 방어: 응답의 `next` 필드를 그대로 사용하고 직접 cursor를 합성하지 않음 → 포맷 변경에 상대적으로 강건.

### R2. reCAPTCHA 트리거 불확실
- 대량 로그인 실패 시 Kidsnote가 reCAPTCHA를 요구할 수 있음. 현재 감지/처리 없음 → 무한 실패 가능.
- 지수 백오프로 완화 중이나, 페이지 HTML에 reCAPTCHA 감지 로직 추가 필요.

### R3. 세션 만료 시각이 불분명
- Kidsnote 측 sessionid 만료 정확한 시간 미확인. 우리는 2시간으로 가정하나 서버가 더 빨리 만료시킬 수 있음.
- 현재는 요청 시 401/403이 오면 삭제하므로 결과적으로 동작하나, 선제적 갱신은 불가.

### R4. variant URL 정적성 가정
- `original/large/small_resize/small` 네 가지가 항상 존재한다고 가정하고 fallback 체인만 둠.
- Kidsnote가 필드 이름을 추가/변경하면 `image_url()`이 반환을 못함.

## 운영 중 발견된 이슈 (현장 메모)

### O1. "write operation failed" 훅 false positive
- 개발 시 Claude Code 훅이 성공한 쓰기 작업에도 "failed"를 표시하는 경우가 있음. 실제 파일은 생성됨 — `ls -la`로 확인 가능.

### O2. `python3-venv` 미설치 환경
- 시스템에 따라 `python -m venv`가 실패할 수 있음. Windows에서는 `py -3`, Linux/macOS에서는 `python3`가 필요할 수 있음.
- 현재는 `run.py`가 현재 실행 중인 Python으로 가상환경을 만들기 때문에 예전보다 설치 진입 장벽은 낮아졌지만, Python 자체가 설치되어 있어야 함.

### O3. MIME/확장자 추정 실패 가능성
- `image_filename()`이 URL 경로에서 확장자를 잘라 쓰므로, 쿼리스트링이 붙은 URL에서 정확. 하지만 확장자가 아예 없으면 `.jpg` 기본값 → 실제가 png/mp4일 수 있음.

### O4. 같은 파일명 다른 이미지 충돌
- 동일 앨범 내 이미지 ID로 파일명을 만들지만, Kidsnote가 같은 ID로 여러 variant를 돌려주지 않기에 일반적으로는 안전. 경계 케이스(재업로드 후 ID 재활용) 미테스트.
