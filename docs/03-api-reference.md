# 03. API 레퍼런스

## 내부 REST API (백엔드 → 프론트)

모든 보호된 엔드포인트는 `kn_session` httpOnly 쿠키가 필요하며, 없거나 만료되면 `401`.

### Auth

| Method | Path | Body | 응답 |
|---|---|---|---|
| POST | `/api/login` | `{username, password, auto_prefetch?}` | `{ok, user, children}` + `Set-Cookie: kn_session` |
| POST | `/api/logout` | — | `{ok: true}` + 쿠키 삭제 |
| GET  | `/api/me` | — | `{user, children}` |

### License

| Method | Path | Body | 응답 |
|---|---|---|---|
| GET | `/api/license/status` | — | `{status, is_active, verification_mode, license_key_masked, bound_device_id_masked, current_device_id_masked, device_id_source, activated_at, offline_grace_until, ...}` |
| POST | `/api/license/activate` | `{license_key}` | 라이선스 상태 객체 |
| POST | `/api/license/deactivate` | — | 비활성화된 라이선스 상태 객체 |

### 앨범 / 사진

| Method | Path | Query/Body | 응답 |
|---|---|---|---|
| GET  | `/api/children/{child_id}/albums` | `?page=<cursor>&page_size=30` | `{count, next, results:[{id,title,created,num_images,thumb,author_name,content}]}` |
| GET  | `/api/albums/{album_id}` | — | `{id,title,created,author_name,content, images:[{idx,id,width,height,file_size,thumb,large,original}]}` |

### 다운로드

| Method | Path | Body | 응답 |
|---|---|---|---|
| POST | `/api/albums/{album_id}/download` | `{variant: "large"}` | `JobProgress + {reused_existing}` |
| POST | `/api/children/{child_id}/download-all` | `{variant, max_albums?}` | `JobProgress + {reused_existing}` |
| GET  | `/api/jobs` | — | `JobProgress[]` |
| GET  | `/api/jobs/{job_id}` | — | `JobProgress` |
| GET  | `/api/jobs/{job_id}/zip` | — | `application/zip` |

### 시스템

| Method | Path | 응답 |
|---|---|---|
| GET | `/api/health` | `{status:"ok", service:"kidsnote-app"}` |
| GET | `/` | `index.html` |
| GET | `/static/*` | 프론트 정적 자원 |

### `JobProgress` 스키마

```json
{
  "job_id": "uuid",
  "kind": "album | child",
  "subject": "앨범 제목 또는 작업 이름",
  "status": "pending | running | done | partial | failed",
  "child_id": 5066947,
  "album_id": 157503878,
  "variant": "large",
  "total": 55,
  "downloaded": 35,
  "skipped": 0,
  "failed": 0,
  "saved_files": 35,
  "bytes": 1258291,
  "message": "[35/55] 157503878_001.jpg",
  "started_at": 1745368000.12,
  "finished_at": null,
  "path": "/.../KidsnoteBackup/downloads/memorise8/5066947/157503878"
}
```

---

## 외부 Kidsnote API (참고용)

리버스 엔지니어링으로 파악한 엔드포인트. 모두 `sessionid` 쿠키가 필요 (`/sb-login` 제외).

### 1. 로그인
```
POST https://www.kidsnote.com/sb-login
Content-Type: application/x-www-form-urlencoded

username=<ID>&password=<PW>
```
- 응답: 200 + `Set-Cookie: sessionid=...; HttpOnly`.
- 실패 시: sessionid 쿠키가 없음.

### 2. 내 정보 + 자녀 목록
```
GET https://www.kidsnote.com/api/v1/me/info/
```
- 응답: `{user:{username,name,email,...}, children:[{id,name,date_birth,gender,picture:{small,large}}]}`.

### 3. 자녀 앨범 목록 (커서 페이지네이션)
```
GET https://www.kidsnote.com/api/v1/children/{child_id}/albums/?page_size=30[&page=<cursor>]
```
- **중요**: cursor 파라미터 이름은 `page`이며, 값은 서버가 돌려주는 `next` 문자열을 그대로 전달.
- 실제 값은 base64로 `p=<last_album_id>`를 인코딩한 것 — 직접 만들지 말고 서버 응답의 `next`를 그대로 사용.
- 응답: `{count, next, previous, results:[album...]}`. `results[*].attached_images`가 이미 포함되어 있어 요약 페이지 구성 시 추가 요청 불필요.

### 4. 앨범 상세
```
GET https://www.kidsnote.com/api/v1/albums/{album_id}
```
- 응답: 앨범 객체 + `attached_images`. 리스트와 거의 동일하지만 상세 컨텐츠 필드 전체 포함.

### 5. 이미지 CDN (인증 불요)
```
GET https://up-kids-kage.kakao.com/.../<hash>.jpg
```
- `sessionid` 쿠키 없어도 접근 가능한 공개 URL.
- 각 이미지 객체에는 4가지 variant URL이 들어있음: `original` (원본, ~8MB), `large` (1024×768 ~500KB), `small_resize`, `small`.

## 로그인 플로우를 알아낸 과정 (메모)

- 초기 가설 "HTTP Basic auth"는 JS 번들의 axios 헤더 셋업을 오독한 것이었음. 실제로는 Django REST Framework + session 쿠키.
- JS 번들에서 `/sb_login` 문자열을 grep해 form-encoded POST 엔드포인트를 발견.
- 페이지네이션 파라미터 이름은 `useInfiniteQuery` + `pageParam` 사용처를 추적해 `params: {...o, page: t}`로 파악.
