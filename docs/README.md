# Kidsnote Photo Grabber — 문서 인덱스

Kidsnote 학부모 계정으로 로그인하여 자녀 앨범 사진을 일괄 다운로드하는 독립 실행형 풀스택 앱.

이 `docs/` 폴더는 현재까지 개발된 내용과 앞으로 개발해야 할 항목들을 정리합니다.

## 목차

| 문서 | 설명 |
|---|---|
| [01-overview.md](./01-overview.md) | 프로젝트 개요, 목표, 전체 아키텍처 |
| [02-architecture.md](./02-architecture.md) | 백엔드/프론트엔드 구조, 데이터 흐름 |
| [03-api-reference.md](./03-api-reference.md) | 내부 REST API 및 외부 Kidsnote API |
| [04-auth-flow.md](./04-auth-flow.md) | 인증 플로우 (Kidsnote `/sb-login` 세션 쿠키) |
| [05-completed.md](./05-completed.md) | 현재까지 완료된 기능 (MVP 범위) |
| [06-roadmap.md](./06-roadmap.md) | 앞으로 개발할 기능 / 우선순위 |
| [07-known-issues.md](./07-known-issues.md) | 알려진 이슈 / 한계점 |
| [08-deployment.md](./08-deployment.md) | 배포/운영 관련 고려사항 |
| [09-desktop-local-app-todo.md](./09-desktop-local-app-todo.md) | 설치형 로컬 앱 판매를 위한 개발 체크리스트 |
| [10-job-status.md](./10-job-status.md) | 현재 작업 상태 / 다음 작업 / 검증 로그 |

## 빠르게 시작하기

```bash
cd kidsnote-app
./run.sh             # macOS/Linux
# 또는 Windows:
run.bat
# macOS/Linux는 브라우저, Windows는 데스크톱 앱 창으로 실행
```

기본 사용자 데이터는 OS별 앱 데이터 폴더에 저장되며, `KIDSNOTE_APP_HOME`, `KIDSNOTE_RUNTIME_ROOT`, `KIDSNOTE_DOWNLOAD_ROOT` 환경변수로 재정의할 수 있습니다.

## 저장소 위치

- 소스: `/home/ruci/repo/develop/kidsnote-app/`
- 원본 크롤러(참고용): `/home/ruci/repo/develop/frwaler/crawler/sites/custom/kidsnote.py` (`fino-crawler` 브랜치)
