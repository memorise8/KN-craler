# 06. 로드맵 / 앞으로 개발할 것

우선순위는 **P0 필수 → P1 강화 → P2 장기** 순서로 분류.

## P0 — 현업 배포 전 필수

### P0-1. 세션 저장 암호화
- **현재 상태**: SQLite 영속 세션 저장까지는 완료.
- **남은 문제**: `sessionid`가 평문으로 런타임 DB에 저장됨.
- **방향**: 로컬 키 또는 KMS 기반 암호화 레이어 추가.

### P0-2. 다운로드 큐 & 동시성 제한
- **문제**: `children/download-all`로 수백 앨범을 돌리면 수천~수만 장을 한 스레드에서 직렬 처리 → 느리고, 여러 유저가 동시에 요청하면 프로세스에 부하.
- **방향**: `ThreadPoolExecutor(max_workers=N)` 또는 asyncio + `aiohttp`로 이미지 다운로드 병렬화. Kidsnote/Kakao CDN rate limit 확인 필요 (현재 0.1초 딜레이만 설정).

### P0-3. 대용량 ZIP 최적화
- **현재 상태**: 완료된 작업은 `/api/jobs/{id}/zip`으로 바로 다운로드 가능.
- **남은 문제**: 매우 큰 백업은 ZIP 생성 시간이 길고 임시 디스크를 사용.
- **방향**: 스트리밍 ZIP 또는 비동기 아카이브 캐시 도입.

### P0-4. 에러 메시지 한글화 + 토스트 UI
- **문제**: 프론트가 실패 시 alert 없이 콘솔에만 에러. 유저가 원인을 모름.
- **방향**: 전역 토스트 컴포넌트 추가 + 한글 메시지(로그인 실패, 세션 만료, 네트워크 오류).

### P0-5. HTTPS 가이드 & Secure 플래그
- **문제**: 배포 시 HTTP면 sessionid 노출.
- **방향**: 배포 환경에서는 `Secure` 플래그 + reverse proxy(Caddy/Nginx) 템플릿 제공. `README`에 배포 섹션 추가.

## P1 — 사용성 강화

### P1-1. 다이어리 / 알림장 / 출석 등 Kidsnote 다른 콘텐츠 지원
- Kidsnote에는 앨범(`/album`) 외에도 `diary`(알림장), `attendance`, `report` 같은 컨텐츠가 있음.
- 원본 크롤러(`frwaler/crawler/sites/custom/kidsnote.py`)에서 확장 가능 — 상세 엔드포인트 조사 후 `kidsnote_client.py`에 `iter_child_diaries()` 등 추가.

### P1-2. 비디오 다운로드
- 현재 클라이언트는 이미지 variant만 처리. 앨범 응답에 `attached_videos`가 있는 경우 처리 미흡.
- MP4 등 원본 URL 추출 + 동일 잡 매니저로 통합.

### P1-3. EXIF / 촬영시간 기반 파일명
- 현재 파일명: `{idx:03d}_{원본파일명}`.
- 개선: `{YYYYMMDD}_{album_title}_{idx}.{ext}` 포맷 옵션. 날짜는 앨범의 `created` 필드 사용.

### P1-4. 앨범/자녀별 다운로드 이력
- 언제 무엇을 받았는지 SQLite에 로그 → 프론트에 "마지막 다운로드" 배지.
- 재다운로드 시 변경된 이미지만 가져오는 증분 모드.

### P1-5. 검색 / 필터 / 기간
- 앨범 title/content 검색, 날짜 범위 필터.
- Kidsnote API 자체 필터 지원 확인 필요 — 없으면 클라이언트 측 필터.

### P1-6. i18n (영/한)
- 현재 UI는 한글 고정. `app.js`에 간단한 사전 기반 번역 도입.

## P2 — 장기 과제

### P2-1. 멀티유저 멀티프로세스
- FastAPI + Gunicorn `--workers N` 지원. 위의 P0-1 완료가 선결 조건.

### P2-2. 모바일 앱 (React Native / PWA)
- 현재 반응형이지만 네이티브 경험 필요 시 PWA 매니페스트 + 서비스워커부터.

### P2-3. 자녀 단위 공유 링크
- 할아버지/할머니 등 가족에게 임시 URL로 앨범 공유. 읽기 전용 세션 분리 필요.

### P2-4. E2E 테스트
- Playwright로 로그인 → 앨범 선택 → 다운로드 → 파일 존재 확인 자동화.
- 테스트용 Kidsnote 계정 또는 mock 서버 필요.

### P2-5. 원본 크롤러(`frwaler`)와 코드 공유
- 현재는 `kidsnote_client.py`를 따로 두어 중복. 장기적으로는 패키지화해 양쪽에서 import.

### P2-6. 옵저버빌리티
- 구조화 로그 (JSON) + Sentry. 현재 print 기반.

## 기록용 — 리버스 엔지니어링으로 아직 확정 못한 항목

- `/sb-login` 5xx 응답 포맷 (존재한다면): 실패 코드 분기 향상 필요.
- 로그인 시 reCAPTCHA가 트리거되는 조건 — 대량 실패 후일 것으로 추정, 방어 로직 미구현.
- `attached_videos` 실제 URL 구조 — 샘플 응답 수집 필요.
- `/api/v1/me/info/` 외에 `me/agreement/`, `me/notifications/` 등이 있는지 — 부가 정보 확장 여지.
