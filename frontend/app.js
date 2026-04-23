"use strict";

const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && data.detail) || res.statusText || "요청에 실패했습니다.";
    if (res.status === 401 && path !== "/api/login") {
      resetSession(false);
      showToast("세션이 만료되었습니다. 다시 로그인해 주세요.", "error");
      navLogin();
    }
    throw new Error(msg);
  }
  return data;
};

const $ = (sel) => document.querySelector(sel);
const h = (tag, props = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "className") el.className = v;
    else if (k === "dataset" && v) {
      Object.entries(v).forEach(([name, value]) => {
        el.dataset[name] = value;
      });
    } else if (k === "textContent") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === "hidden" && !v) {
      continue;
    } else if (k === "style" && typeof v === "object") {
      Object.assign(el.style, v);
    } else if (v !== undefined && v !== null && v !== false) {
      el.setAttribute(k, v);
    }
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
};

const state = {
  license: null,
  user: null,
  children: [],
  view: "license",
  currentChildId: null,
  currentAlbumId: null,
  albumsByChild: {},
  albumDetail: null,
  jobs: {},
};

function resetSession(shouldRender = true) {
  state.user = null;
  state.children = [];
  state.currentChildId = null;
  state.currentAlbumId = null;
  state.albumsByChild = {};
  state.albumDetail = null;
  state.jobs = {};
  if (shouldRender) render();
}

function hasActiveLicense() {
  return Boolean(state.license && state.license.is_active);
}

function jobCounts() {
  const jobs = Object.values(state.jobs);
  return {
    active: jobs.filter((job) => job.status === "pending" || job.status === "running").length,
    done: jobs.filter((job) => job.status === "done" || job.status === "partial").length,
    failed: jobs.filter((job) => job.status === "failed").length,
  };
}

function formatDate(value) {
  if (!value) return "날짜 없음";
  return String(value).slice(0, 10);
}

function formatDateTime(value) {
  if (!value) return "기록 없음";
  const date = new Date(value * 1000);
  return date.toLocaleString("ko-KR");
}

function formatJobStatus(status) {
  return {
    pending: "대기 중",
    running: "진행 중",
    done: "완료",
    partial: "부분 완료",
    failed: "실패",
  }[status] || status;
}

function progressPct(job) {
  if (!job.total) return 0;
  return Math.min(Math.floor(((job.downloaded + job.skipped + job.failed) / job.total) * 100), 100);
}

function isJobActive(job) {
  return job && (job.status === "pending" || job.status === "running");
}

function findActiveJob(predicate) {
  return Object.values(state.jobs).find((job) => isJobActive(job) && predicate(job)) || null;
}

function findActiveChildJob(childId) {
  return findActiveJob((job) => Number(job.child_id) === Number(childId));
}

function findActiveAlbumJob(albumId) {
  return findActiveJob((job) => Number(job.album_id) === Number(albumId));
}

function mergeUniqueById(items) {
  const seen = new Map();
  for (const item of items || []) {
    seen.set(String(item.id), item);
  }
  return [...seen.values()];
}

function sameSet(left, right) {
  if (left.size !== right.size) return false;
  for (const value of left) {
    if (!right.has(value)) return false;
  }
  return true;
}

function showToast(message, kind = "info") {
  const host = $("#toast-host");
  if (!host) return;
  const toast = h(
    "div",
    { className: `toast ${kind}` },
    h("strong", {}, kind === "error" ? "오류" : kind === "success" ? "완료" : "안내"),
    h("span", {}, message)
  );
  host.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("leaving");
    window.setTimeout(() => toast.remove(), 220);
  }, 3800);
}

async function boot() {
  try {
    state.license = await api("/api/license/status");
  } catch (_err) {
    state.license = null;
  }
  if (!hasActiveLicense()) {
    navLicense();
    pollJobs();
    return;
  }
  try {
    const me = await api("/api/me");
    state.user = me.user;
    state.children = me.children;
    navChildren();
  } catch (_err) {
    navLogin();
  }
  pollJobs();
}

function render() {
  renderUserBar();
  renderJobs();
  const view = $("#view");
  view.innerHTML = "";
  if (state.view === "license") view.appendChild(viewLicense());
  if (state.view === "login") view.appendChild(viewLogin());
  if (state.view === "children") view.appendChild(viewChildren());
  if (state.view === "albums") view.appendChild(viewAlbums());
  if (state.view === "album") view.appendChild(viewAlbum());
}

function navLicense() {
  state.view = "license";
  render();
}

function navLogin() {
  state.view = hasActiveLicense() ? "login" : "license";
  render();
}

function navChildren() {
  if (!hasActiveLicense()) {
    navLicense();
    return;
  }
  state.view = "children";
  render();
}

function navAlbums(childId) {
  if (!hasActiveLicense()) {
    navLicense();
    return;
  }
  state.currentChildId = childId;
  state.view = "albums";
  render();
  loadAlbums(childId);
}

function navAlbum(albumId) {
  if (!hasActiveLicense()) {
    navLicense();
    return;
  }
  state.currentAlbumId = albumId;
  state.view = "album";
  state.albumDetail = null;
  render();
  loadAlbum(albumId);
}

function renderUserBar() {
  const bar = $("#user-bar");
  bar.innerHTML = "";
  if (!hasActiveLicense()) {
    bar.appendChild(h("div", { className: "user-bar is-logged-out" }, "라이선스 인증 필요"));
    return;
  }
  if (!state.user) {
    bar.appendChild(
      h(
        "div",
        { className: "user-bar is-logged-out" },
        h("span", { className: "pill success" }, "라이선스 활성"),
        "Kidsnote 로그인 전"
      )
    );
    return;
  }
  const counts = jobCounts();
  bar.appendChild(
    h(
      "div",
      { className: "user-bar" },
      h("span", { className: "pill cool" }, state.license.license_key_masked || "로컬 인증"),
      h("span", { className: "pill success" }, "재시작 후에도 로그인 유지"),
      h("span", {}, `${state.user.name || state.user.username} 님`),
      h("span", { className: "pill subtle" }, `진행 중 ${counts.active}`),
      h("button", { onClick: changeLicense }, "라이선스 변경"),
      h("button", { onClick: doLogout }, "로그아웃")
    )
  );
}

function metricCard(label, value, tone = "neutral") {
  return h(
    "div",
    { className: `metric-card ${tone}` },
    h("div", { className: "metric-label" }, label),
    h("div", { className: "metric-value" }, value)
  );
}

function viewLicense() {
  const status = state.license || {
    is_active: false,
    verification_mode: "local_placeholder",
    license_key_masked: "",
    bound_device_id_masked: "",
    current_device_id_masked: "",
    device_id_source: "",
    activated_at: null,
    offline_grace_until: null,
    message: "라이선스 키를 입력하면 앱이 잠금 해제됩니다.",
  };
  const usesRemoteServer = String(status.verification_mode || "").startsWith("remote_server");
  const err = h("div", { className: "error" });
  const btn = h("button", { className: "primary", type: "submit" }, "앱 잠금 해제");
  const keyInput = h("input", {
    type: "text",
    name: "license_key",
    placeholder: "예: KNB-LOCAL-2026-0001",
    required: true,
    autocomplete: "off",
    spellcheck: "false",
  });

  const form = h(
    "form",
    {
      className: "card form product-form license-form",
      onSubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        btn.disabled = true;
        btn.textContent = "검증 중…";
        try {
          state.license = await api("/api/license/activate", {
            method: "POST",
            body: JSON.stringify({ license_key: keyInput.value.trim() }),
          });
          showToast("라이선스가 활성화되었습니다.", "success");
          try {
            const me = await api("/api/me");
            state.user = me.user;
            state.children = me.children;
            navChildren();
          } catch (_err) {
            navLogin();
          }
        } catch (apiError) {
          err.textContent = apiError.message || "라이선스 검증에 실패했습니다.";
        } finally {
          btn.disabled = false;
          btn.textContent = "앱 잠금 해제";
        }
      },
    },
    h("div", { className: "eyebrow" }, "License Gate"),
    h("h2", {}, "라이선스 인증 후 사용 가능합니다"),
    h(
      "p",
      { className: "muted" },
      usesRemoteServer
        ? "라이선스 서버와 현재 기기 식별값을 함께 검증합니다. 같은 PC 재설치는 허용되고, 다른 PC에서는 같은 키를 다시 쓸 수 없습니다."
        : "개발 모드에서는 로컬 임시 검증을 사용할 수 있습니다. 배포 시에는 라이선스 서버 검증이 기본 경로입니다."
    ),
    h("label", {}, "라이선스 키", keyInput),
    h("div", { className: "form-actions" }, btn),
    err
  );

  const summary = h(
    "div",
    { className: "card license-summary" },
    h("div", { className: "eyebrow" }, "Activation Status"),
    h("h3", {}, status.is_active ? "앱 사용 가능" : "앱 잠금 상태"),
    h("p", { className: "muted" }, status.message),
    h(
      "div",
      { className: "license-meta" },
      h("div", { className: "metric-card cool" }, h("div", { className: "metric-label" }, "검증 방식"), h("div", { className: "metric-value metric-value-small" }, status.verification_mode)),
      h("div", { className: "metric-card accent" }, h("div", { className: "metric-label" }, "현재 키"), h("div", { className: "metric-value metric-value-small" }, status.license_key_masked || "미인증")),
      h("div", { className: "metric-card neutral" }, h("div", { className: "metric-label" }, "현재 기기"), h("div", { className: "metric-value metric-value-small" }, status.current_device_id_masked || "미검출")),
      h("div", { className: "metric-card warm" }, h("div", { className: "metric-label" }, "활성화 시각"), h("div", { className: "metric-value metric-value-small" }, formatDateTime(status.activated_at)))
    ),
    (status.bound_device_id_masked || status.device_id_source)
      ? h(
          "p",
          { className: "muted", style: { marginTop: "12px" } },
          `바인딩 기기: ${status.bound_device_id_masked || "미확정"} · 식별값 소스: ${status.device_id_source || "미확인"}`
        )
      : null,
    status.offline_grace_until
      ? h(
          "p",
          { className: "muted", style: { marginTop: "8px" } },
          `오프라인 유예 종료: ${formatDateTime(status.offline_grace_until)}`
        )
      : null,
    status.is_active
      ? h("div", { className: "inline-actions", style: { marginTop: "16px" } },
        h("button", { onClick: deactivateLicense, type: "button" }, "라이선스 비활성화"),
        h("button", { className: "primary", onClick: () => navLogin(), type: "button" }, "로그인 화면으로")
      )
      : null
  );

  return h(
    "div",
    { className: "login-layout" },
    h(
      "section",
      { className: "hero-panel" },
      h("div", { className: "eyebrow" }, "Desktop Local App"),
      h("h2", {}, "로컬 설치형 백업 앱 사용 준비"),
      h(
        "p",
        { className: "hero-copy" },
        "라이선스가 활성화된 기기에서만 Kidsnote 로그인과 다운로드를 사용할 수 있습니다. 인증이 끝나면 기존 로그인/백업 흐름은 모두 로컬에서 실행됩니다."
      ),
      h(
        "div",
        { className: "hero-metrics" },
        metricCard("라이선스 정책", "1인 1기기", "accent"),
        metricCard("검증 위치", usesRemoteServer ? "우리 서버" : "로컬 개발 모드", "cool"),
        metricCard("Kidsnote 처리", "내 PC 로컬", "warm")
      ),
      h(
        "div",
        { className: "feature-list" },
        h("div", { className: "feature-item" }, "우리 서버는 라이선스 상태만 확인합니다."),
        h("div", { className: "feature-item" }, "Kidsnote 계정과 세션은 사용자 PC에서만 처리됩니다."),
        h("div", { className: "feature-item" }, usesRemoteServer ? "같은 기기 재설치는 허용되고, 다른 기기에서는 같은 키가 차단됩니다." : "개발 모드에서는 원격 라이선스 서버 없이도 UI를 점검할 수 있습니다."),
        usesRemoteServer ? h("div", { className: "feature-item" }, "최근 검증 성공 기록이 있으면 일정 기간 오프라인에서도 앱을 사용할 수 있습니다.") : null
      ),
      summary
    ),
    form
  );
}

function viewLogin() {
  const err = h("div", { className: "error" });
  const btn = h("button", { className: "primary", type: "submit" }, "Kidsnote 연결");
  const usernameInput = h("input", {
    type: "text",
    name: "username",
    placeholder: "Kidsnote 아이디",
    required: true,
    autocomplete: "username",
  });
  const passwordInput = h("input", {
    type: "password",
    name: "password",
    placeholder: "비밀번호",
    required: true,
    autocomplete: "current-password",
  });
  const autoCheck = h("input", { type: "checkbox", name: "auto", id: "auto-prefetch" });

  const form = h(
    "form",
    {
      className: "card form product-form",
      onSubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        btn.disabled = true;
        btn.textContent = "연결 중…";
        try {
          const body = {
            username: usernameInput.value.trim(),
            password: passwordInput.value,
            auto_prefetch: autoCheck.checked,
          };
          const res = await api("/api/login", {
            method: "POST",
            body: JSON.stringify(body),
          });
          state.user = res.user;
          state.children = res.children;
          if (autoCheck.checked) {
            await autoDownloadAll();
          }
          showToast("Kidsnote 계정이 연결되었습니다.", "success");
          navChildren();
        } catch (apiError) {
          err.textContent = apiError.message || "로그인에 실패했습니다.";
        } finally {
          btn.disabled = false;
          btn.textContent = "Kidsnote 연결";
        }
      },
    },
    h("div", { className: "eyebrow" }, "Parents Backup Console"),
    h("h2", {}, "Kidsnote 사진을 안전하게 백업하세요"),
    h(
      "p",
      { className: "muted" },
      "계정 정보는 서버 DB에 저장하지 않고, 인증 세션만 복원 가능한 형태로 유지합니다."
    ),
    h("label", {}, "아이디", usernameInput),
    h("label", {}, "비밀번호", passwordInput),
    h(
      "label",
      { className: "check-row" },
      autoCheck,
      h("span", {}, "로그인 직후 모든 자녀의 앨범 백업 시작")
    ),
    h("div", { className: "form-actions" }, btn),
    err
  );

  return h(
    "div",
    { className: "login-layout" },
    h(
      "section",
      { className: "hero-panel" },
      h("div", { className: "eyebrow" }, "Sellable v1"),
      h("h2", {}, "운영 가능한 학부모 사진 백업 제품"),
      h(
        "p",
        { className: "hero-copy" },
        "로컬 개발용 크롤러가 아니라, 세션 유지와 ZIP 인도까지 갖춘 고객용 다운로드 콘솔로 정리했습니다."
      ),
      h(
        "div",
        { className: "hero-metrics" },
        metricCard("재시작 내성", "SQLite 세션", "accent"),
        metricCard("결과 인도", "ZIP 다운로드", "warm"),
        metricCard("사용자 피드백", "토스트/상태 UI", "cool")
      ),
      h(
        "div",
        { className: "feature-list" },
        h("div", { className: "feature-item" }, "별도 가입 없이 Kidsnote 계정으로 바로 연결"),
        h("div", { className: "feature-item" }, "앨범 단위 또는 자녀 전체 백업 작업 실행"),
        h("div", { className: "feature-item" }, "작업 완료 후 브라우저에서 바로 ZIP 받기")
      )
    ),
    form
  );
}

function viewChildren() {
  const counts = jobCounts();
  if (!state.children.length) {
    return h(
      "div",
      { className: "page-stack" },
      h("section", { className: "hero-banner" }, h("h2", {}, "연결된 자녀가 없습니다.")),
      h("div", { className: "card empty-state" }, "Kidsnote 계정에 연결된 자녀 정보가 없습니다.")
    );
  }

  const cards = state.children.map((child) =>
    (() => {
      const activeJob = findActiveChildJob(child.id);
      return h(
        "article",
        { className: "card child-card", onClick: () => navAlbums(child.id) },
        h(
          "div",
          { className: "child-card-top" },
          child.picture
            ? h("img", { src: child.picture, alt: child.name, loading: "lazy" })
            : h("div", { className: "avatar-fallback" }, child.name ? child.name.slice(0, 1) : "?"),
          h(
            "div",
            {},
            h("h3", {}, child.name || `아이 #${child.id}`),
            h(
              "div",
              { className: "muted" },
              [child.date_birth, child.gender].filter(Boolean).join(" · ") || "기본 프로필 정보 없음"
            )
          )
        ),
        h("p", { className: "muted" }, activeJob ? `백업 진행 중: ${activeJob.message || formatJobStatus(activeJob.status)}` : "앨범을 탐색하거나 전체 백업 작업을 실행할 수 있습니다."),
        h(
          "div",
          { className: "inline-actions" },
          h("button", { className: "primary", disabled: !!activeJob, onClick: (e) => {
            e.stopPropagation();
            downloadChildAll(child.id);
          } }, activeJob ? "백업 진행 중" : "전체 백업"),
          h("button", { onClick: (e) => {
            e.stopPropagation();
            navAlbums(child.id);
          } }, "앨범 보기")
        )
      );
    })()
  );

  return h(
    "div",
    { className: "page-stack" },
    h(
      "section",
      { className: "hero-banner" },
      h("div", { className: "eyebrow" }, "Backup Dashboard"),
      h("h2", {}, "가족별 백업 운영 대시보드"),
      h(
        "p",
        { className: "hero-copy" },
        "자녀별로 모든 앨범을 백업하고, 완료된 작업은 브라우저에서 ZIP으로 바로 내려받을 수 있습니다."
      ),
      h(
        "div",
        { className: "hero-metrics" },
        metricCard("등록 자녀", `${state.children.length}명`, "accent"),
        metricCard("진행 중 작업", `${counts.active}건`, "cool"),
        metricCard("완료된 작업", `${counts.done}건`, "warm")
      )
    ),
    h("section", { className: "children" }, ...cards)
  );
}

function viewAlbums() {
  const child = state.children.find((item) => item.id === state.currentChildId);
  const data = albumsState(state.currentChildId);
  const activeJob = findActiveChildJob(state.currentChildId);
  const albums = h("div", { className: "albums" });

  for (const album of data.results) {
    albums.appendChild(
      h(
        "article",
        { className: "album card", onClick: () => navAlbum(album.id) },
        h(
          "div",
          { className: "thumb" },
          album.thumb ? h("img", { src: album.thumb, alt: "", loading: "lazy" }) : h("div", { className: "thumb-fallback" }, "NO IMAGE")
        ),
        h("div", { className: "album-badge" }, `${album.num_images}장`),
        h("h3", {}, album.title || `앨범 #${album.id}`),
        h("div", { className: "meta" }, `${formatDate(album.created)} · ${album.author_name || "작성자 정보 없음"}`),
        album.content ? h("p", { className: "album-snippet" }, album.content.slice(0, 90)) : null
      )
    );
  }

  return h(
    "div",
    { className: "page-stack" },
    h(
      "div",
      { className: "breadcrumb" },
      h("a", { onClick: navChildren }, "← 자녀 목록"),
      child ? ` · ${child.name}` : ""
    ),
    h(
      "section",
      { className: "hero-banner compact" },
      h("div", { className: "eyebrow" }, "Albums"),
      h("h2", {}, `${child ? child.name : "선택한 자녀"}의 앨범`),
      h(
        "p",
        { className: "hero-copy" },
        "앱을 새로고침해도 로그인 세션은 유지됩니다. 필요한 경우 특정 앨범만 선택해서 받을 수 있습니다."
      ),
      h(
        "div",
        { className: "toolbar" },
        h("button", { className: "primary", disabled: !!activeJob, onClick: () => downloadChildAll(state.currentChildId) }, activeJob ? "전체 백업 진행 중" : "이 자녀 전체 백업"),
        h("span", { className: "muted" }, data.loading ? "앨범을 불러오는 중입니다." : `${data.results.length}개 앨범 표시 중${activeJob ? " · 백업 진행 중" : ""}`)
      )
    ),
    albums,
    data.next
      ? h("div", { className: "load-more-wrap" }, h("button", { disabled: data.loading, onClick: () => loadAlbums(state.currentChildId, { append: true }) }, data.loading ? "불러오는 중…" : "앨범 더 불러오기"))
      : null
  );
}

function viewAlbum() {
  const album = state.albumDetail && state.albumDetail.id === state.currentAlbumId ? state.albumDetail : null;
  if (!album) {
    return h(
      "div",
      { className: "page-stack" },
      h("div", { className: "breadcrumb" }, h("a", { onClick: () => navAlbums(state.currentChildId) }, "← 앨범 목록")),
      h("div", { className: "card loading-card" }, h("span", { className: "spinner" }), "앨범을 불러오는 중입니다.")
    );
  }
  const activeJob = findActiveAlbumJob(album.id);

  const gallery = h("div", { className: "gallery" });
  for (const image of album.images) {
    const fullUrl = image.large || image.original || image.thumb;
    gallery.appendChild(
      h("img", {
        src: image.thumb || fullUrl,
        alt: album.title || "",
        loading: "lazy",
        onClick: () => openLightbox(fullUrl),
      })
    );
  }

  return h(
    "div",
    { className: "page-stack" },
    h(
      "div",
      { className: "breadcrumb" },
      h("a", { onClick: () => navAlbums(state.currentChildId) }, "← 앨범 목록"),
      ` · ${album.title || ""}`
    ),
    h(
      "section",
      { className: "hero-banner compact" },
      h("div", { className: "eyebrow" }, "Album Detail"),
      h("h2", {}, album.title || `앨범 #${album.id}`),
      h(
        "div",
        { className: "toolbar" },
        h("button", { className: "primary", disabled: !!activeJob, onClick: () => downloadAlbum(album.id, "large") }, activeJob ? "백업 진행 중" : "Large 백업"),
        h("button", { disabled: !!activeJob, onClick: () => downloadAlbum(album.id, "original") }, "원본 백업"),
        h("span", { className: "muted" }, `${album.images.length}장 · ${album.author_name || "작성자 정보 없음"} · ${formatDate(album.created)}`)
      )
    ),
    album.content ? h("div", { className: "card album-content" }, album.content) : null,
    gallery
  );
}

function openLightbox(url) {
  const box = h(
    "div",
    {
      className: "lightbox",
      onClick: (e) => {
        if (e.target === box || e.target.tagName === "BUTTON") close();
      },
    },
    h("button", { className: "close", type: "button" }, "닫기"),
    h("img", { src: url, alt: "원본 보기" })
  );

  const onKeydown = (e) => {
    if (e.key === "Escape") close();
  };

  function close() {
    document.removeEventListener("keydown", onKeydown);
    box.remove();
  }

  document.addEventListener("keydown", onKeydown);
  document.body.appendChild(box);
}

async function doLogout() {
  try {
    await api("/api/logout", { method: "POST" });
  } catch (_err) {
    // Ignore logout errors and reset client state anyway.
  }
  resetSession(false);
  showToast("로그아웃되었습니다.", "info");
  navLogin();
}

async function deactivateLicense() {
  if (!window.confirm("현재 기기의 라이선스를 비활성화할까요?")) {
    return;
  }
  try {
    try {
      await api("/api/logout", { method: "POST" });
    } catch (_err) {
      // Ignore logout errors during license reset.
    }
    state.license = await api("/api/license/deactivate", { method: "POST" });
    resetSession(false);
    showToast("라이선스가 비활성화되었습니다.", "info");
    navLicense();
  } catch (apiError) {
    showToast(`라이선스를 비활성화하지 못했습니다: ${apiError.message}`, "error");
  }
}

function changeLicense() {
  deactivateLicense();
}

function albumsState(childId) {
  return state.albumsByChild[String(childId)] || {
    results: [],
    next: null,
    count: 0,
    loading: false,
    loadedOnce: false,
  };
}

async function loadAlbumsInternal(childId, { append = false } = {}) {
  const key = String(childId);
  const prev = albumsState(childId);
  if (prev.loading) return;
  if (!append && prev.loadedOnce) return;
  if (append && !prev.next) return;
  state.albumsByChild[key] = { ...prev, loading: true };
  render();
  try {
    const params = new URLSearchParams({ page_size: "30" });
    if (append && prev.next) params.set("page", prev.next);
    const data = await api(`/api/children/${childId}/albums?${params}`);
    state.albumsByChild[key] = {
      ...prev,
      loading: false,
      loadedOnce: true,
      count: data.count || 0,
      next: data.next || null,
      results: mergeUniqueById([...(append ? prev.results : []), ...(data.results || [])]),
    };
  } catch (apiError) {
    showToast(`앨범 목록을 불러오지 못했습니다: ${apiError.message}`, "error");
    state.albumsByChild[key] = { ...prev, loading: false };
  } finally {
    render();
  }
}

async function loadAlbum(albumId) {
  try {
    state.albumDetail = await api(`/api/albums/${albumId}`);
    render();
  } catch (apiError) {
    showToast(`앨범 상세를 불러오지 못했습니다: ${apiError.message}`, "error");
  }
}

async function downloadAlbum(albumId, variant = "large") {
  try {
    const job = await api(`/api/albums/${albumId}/download`, {
      method: "POST",
      body: JSON.stringify({ variant }),
    });
    state.jobs[job.job_id] = job;
    showToast(job.reused_existing ? "이미 진행 중인 앨범 백업 작업이 있습니다." : "앨범 백업 작업을 시작했습니다.", job.reused_existing ? "info" : "success");
    renderJobs();
    render();
  } catch (apiError) {
    showToast(`다운로드를 시작하지 못했습니다: ${apiError.message}`, "error");
  }
}

async function downloadChildAll(childId) {
  if (!window.confirm("해당 자녀의 모든 앨범을 백업합니다. 용량이 크게 증가할 수 있습니다. 계속할까요?")) {
    return;
  }
  try {
    const job = await api(`/api/children/${childId}/download-all`, {
      method: "POST",
      body: JSON.stringify({ variant: "large" }),
    });
    state.jobs[job.job_id] = job;
    showToast(job.reused_existing ? "이미 진행 중인 전체 백업 작업이 있습니다." : "전체 백업 작업을 시작했습니다.", job.reused_existing ? "info" : "success");
    renderJobs();
    render();
  } catch (apiError) {
    showToast(`전체 백업을 시작하지 못했습니다: ${apiError.message}`, "error");
  }
}

async function autoDownloadAll() {
  const results = await Promise.allSettled(
    state.children.map((child) =>
      api(`/api/children/${child.id}/download-all`, {
        method: "POST",
        body: JSON.stringify({ variant: "large" }),
      }).then((job) => ({ child, job }))
    )
  );
  for (const [index, result] of results.entries()) {
    if (result.status === "fulfilled") {
      state.jobs[result.value.job.job_id] = result.value.job;
      continue;
    }
    const child = state.children[index];
    showToast(`${(child && (child.name || child.id)) || "자녀"} 자동 백업 시작 실패: ${result.reason.message}`, "error");
  }
  renderJobs();
  render();
}

async function pollJobs() {
  try {
    if (state.user) {
      const activeBefore = new Set(
        Object.values(state.jobs)
          .filter((job) => isJobActive(job))
          .map((job) => job.job_id)
      );
      const jobs = await api("/api/jobs");
      for (const job of jobs) state.jobs[job.job_id] = job;
      const activeAfter = new Set(
        Object.values(state.jobs)
          .filter((job) => isJobActive(job))
          .map((job) => job.job_id)
      );
      renderJobs();
      if (!sameSet(activeBefore, activeAfter)) {
        render();
      }
    }
  } catch (_err) {
    // Session expiry is handled in api().
  }
  window.setTimeout(pollJobs, 2000);
}

function renderJobs() {
  const panel = $("#jobs-panel");
  const list = $("#jobs-list");
  if (!panel || !list) return;
  const jobs = Object.values(state.jobs).sort((a, b) => b.started_at - a.started_at);
  panel.hidden = !hasActiveLicense() || !state.user || jobs.length === 0;
  list.innerHTML = "";

  if (!jobs.length) {
    return;
  }

  for (const job of jobs) {
    const canDownload = !isJobActive(job) && Number(job.saved_files || 0) > 0;
    list.appendChild(
      h(
        "div",
        { className: "job" },
        h(
          "div",
          { className: "job-topline" },
          h("span", { className: `status ${job.status}` }, formatJobStatus(job.status)),
          h("strong", {}, job.subject || (job.kind === "album" ? "앨범 백업" : "전체 백업"))
        ),
        h(
          "div",
          { className: "muted" },
          job.kind === "album"
            ? `${job.downloaded}/${job.total}장 처리 · 기존 ${job.skipped} · 실패 ${job.failed}`
            : `${job.downloaded}/${job.total || "?"}장 처리 · 기존 ${job.skipped} · 실패 ${job.failed}`
        ),
        job.message ? h("div", { className: "muted job-message" }, job.message) : null,
        h("div", { className: "progress" }, h("div", { className: "progress-bar", style: { width: `${progressPct(job)}%` } })),
        h(
          "div",
          { className: "job-actions" },
          h("span", { className: "muted" }, canDownload ? `ZIP 준비됨 · 파일 ${job.saved_files}개` : "작업 완료 후 ZIP 제공"),
          canDownload
            ? h("a", { className: "button-link", href: `/api/jobs/${job.job_id}/zip` }, "ZIP 받기")
            : null
        )
      )
    );
  }
}

async function loadAlbums(childId, options = {}) {
  return loadAlbumsInternal(childId, options);
}

const toggleBtn = document.getElementById("jobs-toggle");
if (toggleBtn) {
  toggleBtn.addEventListener("click", () => {
    const list = document.getElementById("jobs-list");
    if (!list) return;
    if (list.style.display === "none") {
      list.style.display = "";
      toggleBtn.textContent = "접기";
    } else {
      list.style.display = "none";
      toggleBtn.textContent = "펼치기";
    }
  });
}

boot();
