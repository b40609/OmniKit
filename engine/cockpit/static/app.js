// OmniKit 指揮台：專案值班板、工具名冊、帳號額度、架構地圖
(() => {
  const state = {
    activeTab: "cockpit",
    filter: "all",
    search: "",
    selectedId: null,
    mobileDetail: false,
    overview: null,
    tools: null,
    accounts: null,
    toolStatuses: new Set(["default", "trial", "on_demand"]),
    toolSearch: "",
    triFormOpen: new Set(),
    mapLoaded: false,
    // 2026-11-27：寫入要帶伺服器給的 token；經 Tailscale 開啟時只能看（writable=false）
    session: { writable: true, token: null, mode: "local" },
    pollTimer: null,
    wasBusy: false,
  };

  const LANE_ORDER = ["blocked_on_me", "ready_to_settle", "active", "parked"];
  const LANE_NAMES = {
    blocked_on_me: "等你處理",
    ready_to_settle: "待收尾",
    active: "執行中",
    parked: "已停泊",
  };
  const SLOPE_LABEL = { uphill: "上坡探索中", downhill: "下坡純執行" };
  const STATUS_LABELS = {
    default: "預設",
    trial: "試用",
    on_demand: "按需",
    assess: "觀察",
    pending: "待評估",
    rejected: "拒絕",
    retired: "退役",
  };
  const STATUS_ORDER = ["default", "trial", "on_demand", "assess", "pending", "rejected", "retired"];
  const PROFILE_TEXT = {
    thinking_preference: { max_available: "用能開的最高程度", high: "high", xhigh: "xhigh" },
    visibility: { visible: "開在 T3 看得到的對話", headless: "無頭執行，只看結果" },
    on_exhausted: {
      prompt_manual_switch: "停下來，讓你換帳號",
      fallback_paid_api: "改走付費 API 備援",
      fail_closed: "直接停，等額度重置",
    },
  };

  const svg = (d, size = 16) =>
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const ICON = {
    sync: svg(`<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>`),
    ext: svg(`<path d="M7 17 17 7"/><path d="M8 7h9v9"/>`),
    back: svg(`<path d="m15 18-6-6 6-6"/>`, 18),
    chev: svg(`<path d="m9 18 6-6-6-6"/>`),
    alert: svg(`<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>`),
    file: svg(`<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>`),
    copy: svg(`<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>`),
    pause: svg(`<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>`),
    play: svg(`<path d="m7 4 13 8-13 8Z"/>`),
    check: svg(`<path d="M20 6 9 17l-5-5"/>`, 14),
    stepDone: svg(`<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>`),
    stepNow: svg(`<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>`),
    stepTodo: svg(`<circle cx="12" cy="12" r="9"/>`),
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function esc(val) {
    return String(val ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // 下一步常以【等使用者】【agent 可直接做】開頭；球權已經用記號表示，畫面上不重複
  const stripOwnerTag = (text) => String(text || "").replace(/^\s*【[^】]{1,16}】\s*/, "");

  let toastTimer = null;
  function showToast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 2800);
  }

  const READONLY_MSG = "經 Tailscale 開啟時只能看；對帳、登記與改設定請在這台電腦上開 http://127.0.0.1:3780";

  async function api(url, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    const write = method !== "GET" && method !== "HEAD";
    if (write && !state.session.writable) throw new Error(READONLY_MSG);
    const headers = {};
    if (opts.body) headers["Content-Type"] = "application/json";
    if (write && state.session.token) headers["X-OmniKit-Token"] = state.session.token;
    const res = await fetch(url, { ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `請求失敗（${res.status}）`);
    return data;
  }

  async function copyText(text, label) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      showToast(`已複製${label}`);
    } catch {
      showToast("複製失敗，請手動選取");
    }
  }

  // ---------- 深淺色 ----------
  function initTheme() {
    try {
      const saved = localStorage.getItem("omnikit-theme");
      if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
    } catch {
      // 私密瀏覽等情況讀不到就跟系統
    }
  }

  function toggleTheme() {
    const cur = document.documentElement.dataset.theme;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDarkNow = cur ? cur === "dark" : prefersDark;
    const next = isDarkNow ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("omnikit-theme", next);
    } catch {
      // 存不了只影響下次開啟
    }
  }

  // ---------- 分頁 ----------
  function switchTab(tab) {
    state.activeTab = tab;
    for (const btn of $$("[data-tab]")) {
      if (btn.dataset.tab === tab) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    }
    for (const sec of $$(".tab-panel")) sec.hidden = sec.id !== `tab-${tab}`;
    syncDetailChrome();
    if (tab === "tools" && !state.tools) loadTools();
    if (tab === "accounts" && !state.accounts) loadAccounts(false);
    if (tab === "map" && !state.mapLoaded) {
      $("#map-iframe").src = "/map.html";
      state.mapLoaded = true;
    }
  }

  function setMobileDetail(open) {
    state.mobileDetail = Boolean(open);
    $("#tab-cockpit").classList.toggle("mobile-detail", state.mobileDetail);
    syncDetailChrome();
    if (state.mobileDetail) $("#main-scroll").scrollTop = 0;
  }

  // 手機詳情頁有自己的「對帳」，頂端的全部對帳先收起來，避免同一畫面兩顆
  function syncDetailChrome() {
    document.body.classList.toggle("in-detail", state.activeTab === "cockpit" && state.mobileDetail);
  }

  // ---------- 自動對帳輪詢 ----------
  function staleLocalCount() {
    return (state.overview?.projects || []).filter((p) => p.stale && p.local_available).length;
  }

  function syncPolling(reconcile) {
    const busy = Boolean(reconcile?.busy);
    const banner = $("#reconcile-banner");
    const bannerText = $("#reconcile-banner-text");
    const allBtn = $("#btn-reconcile-all");
    const allLabel = $("#reconcile-all-label");
    const stale = staleLocalCount();

    if (busy) {
      const running = reconcile.running_project;
      const runJob = running ? reconcile.jobs?.[running] : null;
      const rest = Math.max(0, (reconcile.active_count || 1) - 1);
      banner.hidden = false;
      bannerText.innerHTML = runJob
        ? `<b>對帳中</b> ${esc(runJob.project_name)}${rest ? `，後面還有 ${rest} 個` : ""}`
        : `<b>對帳中</b> 還有 ${reconcile.active_count} 個專案`;
      allLabel.textContent = "對帳中";
      allBtn.disabled = true;
      allBtn.classList.remove("btn-primary");
      if (!state.pollTimer) state.pollTimer = setInterval(pollReconcile, 3000);
    } else {
      banner.hidden = true;
      allBtn.disabled = false;
      allLabel.textContent = stale > 0 ? `對帳 ${stale}` : "對帳";
      allBtn.classList.toggle("btn-primary", stale > 0);
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      if (state.wasBusy) showToast("對帳完成，已更新");
    }
    state.wasBusy = busy;
  }

  async function pollReconcile() {
    try {
      const rec = await api("/api/reconcile/status");
      if (state.overview) {
        const prevRunning = state.overview.reconcile?.running_project;
        const prevActive = state.overview.reconcile?.active_count || 0;
        state.overview.reconcile = rec;
        if (rec.active_count !== prevActive || rec.running_project !== prevRunning || !rec.busy) {
          await loadOverview(false, true);
          return;
        }
        syncPolling(rec);
        renderInspector();
      }
    } catch {
      // 短暫網路波動，下一輪再試
    }
  }

  async function triggerReconcile(projectId) {
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/reconcile`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      showToast(`已派出 ${projectId} 的對帳，T3 看得到過程`);
      syncPolling(res.reconcile);
      renderList();
      renderInspector();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function triggerReconcileAll() {
    const stale = staleLocalCount();
    let confirmAll = false;
    if (stale === 0) {
      // 沒有過期的專案時按下去會替每個本機專案各開一條對話（KIT-B-16）：先問
      const local = (state.overview?.projects || []).filter((p) => p.local_available && !p.remote_only).length;
      if (local === 0) {
        showToast("沒有需要對帳的本機專案");
        return;
      }
      confirmAll = window.confirm(`目前沒有過期的專案。要把全部 ${local} 個本機專案重新對帳嗎？會開 ${local} 條 T3 對話、一次跑一條。`);
      if (!confirmAll) return;
    }
    try {
      const res = await api("/api/reconcile-all", {
        method: "POST",
        body: JSON.stringify(stale > 0 ? { only_stale: true } : { only_stale: false, confirm_all: confirmAll }),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      const n = res.queued?.length || 0;
      showToast(n === 0 ? "沒有需要對帳的本機專案" : `已排入 ${n} 個專案，一次跑一個`);
      syncPolling(res.reconcile);
      renderList();
      renderInspector();
    } catch (err) {
      showToast(err.message);
    }
  }

  // ---------- 專案 ----------
  async function loadOverview(sync = false, silent = false) {
    const syncBtn = $("#btn-sync");
    if (!silent) syncBtn.disabled = true;
    try {
      const data = await api(`/api/overview${sync ? "?sync=1" : ""}`);
      state.overview = data;
      if (!state.selectedId || !data.projects.some((p) => p.id === state.selectedId)) {
        state.selectedId = data.projects[0]?.id || null;
      }
      renderOverview();
      if (sync) showToast(data.sync?.synced ? "已同步狀態庫並重新掃描" : "已重新掃描本機");
    } catch (err) {
      $("#project-list").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
      if (!silent) showToast(err.message);
    } finally {
      syncBtn.disabled = false;
    }
  }

  function filteredProjects() {
    const ov = state.overview;
    if (!ov) return [];
    const term = state.search.trim().toLowerCase();
    return ov.projects.filter((p) => {
      if (state.filter === "stale" && !p.stale) return false;
      if (state.filter !== "all" && state.filter !== "stale" && p.lane !== state.filter) return false;
      if (!term) return true;
      const hay = [
        p.name,
        p.id,
        ...(p.now.conclusions || []),
        ...(p.now.decisions || []),
        ...(p.now.critiques || []).map((c) => c.text),
        p.now.next_action?.text || "",
        p.git?.branch || "",
        p.git?.last_subject || "",
      ].join(" ").toLowerCase();
      return hay.includes(term);
    });
  }

  function projectPreviewLine(p) {
    const openCrit = (p.now.critiques || []).find((c) => !c.done);
    if (openCrit) return `待改：${openCrit.pain || openCrit.text}`;
    if (p.now.next_action?.text) return stripOwnerTag(p.now.next_action.text);
    if (p.now.conclusions?.[0]) return p.now.conclusions[0];
    if (p.git?.last_subject) return `${p.git.last_hash} ${p.git.last_subject}`;
    return p.stale ? "還沒有 NOW.md，對帳一次就會補上" : "沒有待辦";
  }

  function projectRightTag(p, job) {
    if (job && (job.status === "running" || job.status === "queued")) {
      return { text: job.status === "running" ? "對帳中" : "排隊中", cls: "t-accent" };
    }
    if (p.open_critiques_count > 0) return { text: `待改 ${p.open_critiques_count}`, cls: "t-warn" };
    const behind = p.git?.commits_since_now || 0;
    if (behind > 0) return { text: `落後 ${behind} 個 commit`, cls: "t-warn" };
    if (p.stale) return { text: p.now.exists ? "需對帳" : "缺 NOW.md", cls: "t-warn" };
    const prog = p.now.progress;
    if (prog?.total) return { text: `${prog.done}/${prog.total}`, cls: "" };
    return { text: "", cls: "" };
  }

  function renderList() {
    const list = filteredProjects();
    const root = $("#project-list");
    const jobs = state.overview?.reconcile?.jobs || {};

    if (!list.length) {
      root.innerHTML = `<div class="empty-inline">沒有符合條件的專案</div>`;
      return;
    }

    const byLane = Object.fromEntries(LANE_ORDER.map((l) => [l, []]));
    for (const p of list) byLane[p.lane]?.push(p);

    const html = [];
    for (const lane of LANE_ORDER) {
      const items = byLane[lane];
      if (!items.length) continue;
      html.push(`<div class="list-group-head"><span>${LANE_NAMES[lane]}</span><span class="num">${items.length}</span></div>`);
      for (const p of items) {
        const tag = projectRightTag(p, jobs[p.id]);
        const foot = [];
        if (p.git?.available) {
          foot.push(`<span class="f-branch">${esc(p.git.branch)}</span>`);
          if (p.git.dirty_count > 0) foot.push(`<span class="f-warn">未提交 ${p.git.dirty_count}</span>`);
        } else if (p.remote_only) {
          foot.push("<span>遠端</span>");
        }
        if (p.t3?.unsettled_count > 0) foot.push(`<span>${p.t3.unsettled_count} 條對話</span>`);
        if (p.t3?.overloaded_count > 0) foot.push(`<span class="f-alert">對話超載</span>`);
        foot.push(`<span>${esc(p.last_activity_age)}</span>`);

        html.push(`
          <button type="button" class="proj-row ${p.id === state.selectedId ? "is-selected" : ""}" data-select-project="${esc(p.id)}">
            <span class="ball ball-${esc(p.lane)}" aria-hidden="true"></span>
            <span class="row-body">
              <span class="row-top">
                <span class="row-title">${esc(p.name)}</span>
                ${tag.text ? `<span class="row-tag ${tag.cls}">${esc(tag.text)}</span>` : ""}
              </span>
              <span class="row-preview">${esc(projectPreviewLine(p))}</span>
              <span class="row-foot">${foot.join("")}</span>
            </span>
          </button>
        `);
      }
    }
    root.innerHTML = html.join("");
  }

  function decisionHtml(text) {
    const m = String(text).match(/^([^：:]{2,60})[：:]\s*([\s\S]+)$/);
    return m ? `<b>${esc(m[1])}</b>：${esc(m[2])}` : esc(text);
  }

  function renderInspector() {
    const ov = state.overview;
    const root = $("#inspector-root");
    if (!ov) return;

    const p = ov.projects.find((x) => x.id === state.selectedId) || filteredProjects()[0];
    if (!p) {
      root.innerHTML = `<div class="empty-inline">目前沒有專案</div>`;
      return;
    }

    const job = ov.reconcile?.jobs?.[p.id];
    const isBusy = job && (job.status === "running" || job.status === "queued");
    const prog = p.now.progress || {};
    const hasSteps = prog.total != null && prog.total > 0;
    const slope = SLOPE_LABEL[prog.slope];
    const triOpen = state.triFormOpen.has(p.id);

    // 有狀況才出現的提示條
    let alertBanner = "";
    if (isBusy) {
      alertBanner = `
        <div class="alert-strip is-running">
          <div class="alert-strip-msg"><span class="live-dot"></span><span>${esc(job.message)}</span></div>
          ${job.thread_url ? `<a class="btn btn-sm" href="${esc(job.thread_url)}" target="_blank" rel="noopener">看 T3 過程 ${ICON.ext}</a>` : ""}
        </div>`;
    } else if (job && job.status === "error") {
      alertBanner = `
        <div class="alert-strip">
          <div class="alert-strip-msg">${ICON.alert}<span>${esc(job.message)}</span></div>
          <button type="button" class="btn btn-sm" data-reconcile="${esc(p.id)}">重試對帳</button>
        </div>`;
    } else if (p.stale || p.t3?.overloaded_count > 0) {
      const msgs = [...(p.stale_reasons || [])];
      if (p.t3?.overloaded_count > 0) msgs.push(`${p.t3.overloaded_count} 條主線超過 ${ov.settings.overload_items} 項，建議交接`);
      alertBanner = `
        <div class="alert-strip">
          <div class="alert-strip-msg">${ICON.alert}<span>${esc(msgs.join("；"))}</span></div>
        </div>`;
    }

    const meta = [];
    if (p.git?.available) {
      meta.push(`<span class="m-branch">${esc(p.git.branch)}${p.git.last_hash ? ` · ${esc(p.git.last_hash)}` : ""}</span>`);
      if (p.git.dirty_count > 0) meta.push(`<span class="m-warn">未提交 ${p.git.dirty_count} 檔</span>`);
      if (p.git.ahead > 0) meta.push(`<span class="m-warn">未推 ${p.git.ahead} 個 commit</span>`);
    } else {
      meta.push("<span>遠端專案，這台沒有目錄</span>");
    }
    if (p.t3?.unsettled_count > 0) meta.push(`<span>${p.t3.unsettled_count} 條對話未結案</span>`);
    meta.push(`<span>${esc(p.last_activity_age)}活躍</span>`);

    const reconcileBtn = (extra = "") => p.local_available
      ? `<button type="button" class="btn btn-sm ${p.stale && !isBusy ? "btn-primary" : ""} ${extra}" data-reconcile="${esc(p.id)}" ${isBusy ? "disabled" : ""}>${ICON.sync}${isBusy ? "對帳中" : "對帳"}</button>`
      : "";
    const t3Link = p.primary_t3_url
      ? `<a class="btn btn-sm" href="${esc(p.primary_t3_url)}" target="_blank" rel="noopener">T3 ${ICON.ext}</a>`
      : "";

    // 下一步與要你拍板
    const nxt = p.now.next_action;
    const owner = nxt?.owner === "user"
      ? `<span class="sec-aside is-you"><span class="ball ball-blocked_on_me"></span>輪到你</span>`
      : nxt?.owner === "agent"
        ? `<span class="sec-aside"><span class="ball ball-active"></span>Agent 可以直接做</span>`
        : "";
    const decisions = p.now.decisions || [];
    const decisionsHtml = decisions.length
      ? `<div class="decisions">
          <h4 class="decisions-title">要你拍板（${decisions.length}）</h4>
          <ol class="decision-list">${decisions.map((d) => `<li>${decisionHtml(d)}</li>`).join("")}</ol>
        </div>`
      : "";

    // 進度
    const steps = prog.steps || [];
    const doneSteps = steps.filter((s) => s.done);
    const todoSteps = steps.filter((s) => !s.done);
    const segs = hasSteps
      ? `<div class="seg-meter" aria-hidden="true">${Array.from({ length: prog.total }, (_, i) =>
          `<i class="${i < prog.done ? "is-done" : i === prog.done ? "is-current" : ""}"></i>`).join("")}</div>`
      : "";
    const stepsHtml = steps.length
      ? `${doneSteps.length ? `
          <details class="steps-done">
            <summary>${ICON.chev}已完成 ${doneSteps.length} 步</summary>
            <ol class="step-list">${doneSteps.map((s) => `<li class="is-done clampable"><span class="step-mark">${ICON.stepDone}</span><span>${esc(s.text)}</span></li>`).join("")}</ol>
          </details>` : ""}
        <ol class="step-list">${todoSteps.map((s, i) => `<li class="${i === 0 ? "is-current" : "clampable"}"><span class="step-mark">${i === 0 ? ICON.stepNow : ICON.stepTodo}</span><span>${esc(s.text)}</span></li>`).join("")}</ol>`
      : `<p class="empty-muted">${esc(prog.summary || "還沒拆步驟，對帳一次就會整理")}</p>`;

    // 不滿意待改
    const critiques = p.now.critiques || [];
    const critiquesHtml = critiques.length
      ? `<ul class="critique-list">${critiques.map((c) => {
          const isTri = c.symptom || c.pain || c.criteria;
          const body = isTri
            ? `<div class="tri-stack">
                ${c.symptom ? `<div><b>現況</b>${esc(c.symptom)}</div>` : ""}
                ${c.pain ? `<div><b>不滿</b>${esc(c.pain)}</div>` : ""}
                ${c.criteria ? `<div><b>過關</b>${esc(c.criteria)}</div>` : ""}
              </div>`
            : esc(c.text);
          return `<li class="critique-row ${c.done ? "is-done" : ""}">
            <button type="button" class="check-hit" data-toggle-critique="${esc(p.id)}" data-idx="${c.index}" data-done="${c.done ? "1" : "0"}" aria-label="${c.done ? "重開這一項" : "勾掉這一項"}">
              <span class="check-box">${c.done ? ICON.check : ""}</span>
            </button>
            <div class="critique-text">${body}</div>
          </li>`;
        }).join("")}</ul>`
      : `<p class="empty-muted" style="margin-bottom:12px;">沒有未收斂的項目</p>`;

    // T3 對話
    const threads = p.t3?.threads || [];
    const threadsHtml = threads.length
      ? `<div class="thread-table">${threads.map((t) => `
          <div class="thread-item">
            <div class="thread-main">
              <div class="thread-name">${esc(t.title)}</div>
              <div class="thread-sub">${esc(t.status)} · <span class="${t.overloaded ? "is-over" : ""}">${t.item_count} 項${t.overloaded ? "，超載" : ""}</span>${t.model ? ` · ${esc(t.model)}` : ""}</div>
            </div>
            ${t.link ? `<a class="btn btn-sm" href="${esc(t.link)}" target="_blank" rel="noopener">開啟 ${ICON.ext}</a>` : ""}
          </div>`).join("")}</div>`
      : `<p class="empty-muted">沒有未結案的對話</p>`;

    root.innerHTML = `
      <div class="detail-bar">
        <button type="button" class="btn btn-quiet" id="btn-mobile-back">${ICON.back}專案</button>
        <div class="detail-bar-actions">${reconcileBtn()}${t3Link}</div>
      </div>

      <header class="insp-header">
        <div class="insp-status">
          <span class="ball ball-${esc(p.lane)}" aria-hidden="true"></span>
          <span>${esc(LANE_NAMES[p.lane] || p.lane)}</span>
          ${slope ? `<span class="sep">·</span><span>${slope}</span>` : ""}
          ${p.remote_only ? `<span class="sep">·</span><span>遠端專案</span>` : ""}
        </div>
        <h2 class="insp-title">${esc(p.name)}</h2>
        <div class="insp-meta">${meta.join("")}</div>
        <div class="insp-actions">
          <span class="desk-only actions-contents">${reconcileBtn()}${p.primary_t3_url ? `<a class="btn btn-sm" href="${esc(p.primary_t3_url)}" target="_blank" rel="noopener">打開 T3 ${ICON.ext}</a>` : ""}</span>
          <button type="button" class="btn btn-sm" data-view-now="${esc(p.id)}">${ICON.file}NOW.md</button>
          <button type="button" class="btn btn-sm" data-copy-next="${esc(p.id)}">${ICON.copy}複製下一步</button>
          <button type="button" class="btn btn-sm btn-quiet" data-park="${esc(p.id)}" data-parked="${p.manual_parked ? "1" : "0"}">${p.manual_parked ? `${ICON.play}移回` : `${ICON.pause}停泊`}</button>
        </div>
      </header>

      ${alertBanner}

      <section class="insp-section">
        <div class="sec-head"><h3 class="sec-title">下一步</h3>${owner}</div>
        <p class="next-lead">${nxt ? esc(stripOwnerTag(nxt.text)) : "還沒寫下一步，對帳一次就會從最近進度補上"}</p>
        ${decisionsHtml}
      </section>

      <section class="insp-section two-col">
        <div>
          <div class="sec-head"><h3 class="sec-title">進度</h3>${hasSteps ? `<span class="sec-aside">${prog.done}/${prog.total}</span>` : ""}</div>
          ${segs}
          ${stepsHtml}
        </div>
        <div>
          <div class="sec-head"><h3 class="sec-title">現行結論</h3></div>
          ${p.now.conclusions?.length
            ? `<ul class="plain-list">${p.now.conclusions.slice(0, 3).map((c) => `<li class="clampable"><span>${esc(c)}</span></li>`).join("")}</ul>`
            : `<p class="empty-muted">還沒整理結論，對帳一次就會摘要</p>`}
          ${p.git?.last_subject ? `<p class="commit-line">最新 commit <code>${esc(p.git.last_hash)}</code> ${esc(p.git.last_subject)}</p>` : ""}
        </div>
      </section>

      <section class="insp-section">
        <div class="sec-head"><h3 class="sec-title">不滿意待改</h3><span class="sec-aside">${p.open_critiques_count} 項未收斂</span></div>
        ${critiquesHtml}
        <form class="critique-composer" data-add-critique="${esc(p.id)}" data-path="${esc(p.path || "")}">
          ${triOpen ? `
            <div class="tri-inputs">
              <input class="composer-input" name="symptom" placeholder="現況：現在長怎樣">
              <input class="composer-input" name="pain" placeholder="不滿：哪裡不滿意" required>
              <input class="composer-input" name="criteria" placeholder="過關：改成怎樣算過">
            </div>
            <div class="composer-row">
              <button type="submit" class="btn btn-sm">記下</button>
              <button type="button" class="btn btn-sm btn-quiet" data-toggle-tri="${esc(p.id)}">改回一行</button>
            </div>
          ` : `
            <div class="composer-row">
              <input class="composer-input" name="text" placeholder="記一條不滿意，Enter 寫進 NOW.md" required>
              <button type="submit" class="btn btn-sm">記下</button>
              <button type="button" class="btn btn-sm btn-quiet" data-toggle-tri="${esc(p.id)}">分三欄</button>
            </div>
          `}
        </form>
      </section>

      <section class="insp-section">
        <div class="sec-head"><h3 class="sec-title">T3 未結案對話</h3><span class="sec-aside">${p.t3?.unsettled_count || 0} 條</span></div>
        ${threadsHtml}
      </section>
    `;
  }

  function renderOverview() {
    const ov = state.overview;
    if (!ov) return;
    const s = ov.summary;
    $("#sync-meta").textContent = `${ov.generated_local} 更新`;
    $("#kpi-total").textContent = s.total;
    $("#kpi-blocked").textContent = s.blocked_on_me;
    $("#kpi-settle").textContent = s.ready_to_settle;
    $("#kpi-active").textContent = s.active;
    $("#kpi-stale").textContent = s.stale;
    syncPolling(ov.reconcile);
    renderList();
    renderInspector();
  }

  // ---------- 工具 ----------
  async function loadTools(refresh = false) {
    $("#tools-grid").innerHTML = `<div class="empty-inline">讀取工具名冊中</div>`;
    try {
      state.tools = await api(`/api/tools${refresh ? "?refresh=1" : ""}`);
      renderTools();
    } catch (err) {
      $("#tools-grid").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
    }
  }

  function profileValue(key, val) {
    const text = PROFILE_TEXT[key]?.[val];
    return text ? `<span title="${esc(val)}">${esc(text)}</span>` : `<span class="mono">${esc(val || "未設定")}</span>`;
  }

  function statusTag(t) {
    const label = STATUS_LABELS[t.status] || t.status;
    if (t.status === "default") return `<span class="tag tag-strong">${label}</span>`;
    if (t.status === "trial") {
      const until = t.trial_until ? ` 到 ${esc(t.trial_until.slice(5))}` : "";
      return `<span class="tag tag-outline">${label}${until}</span>`;
    }
    return `<span class="tag">${esc(label)}</span>`;
  }

  function toolCard(t, slotName) {
    const otherSlots = (t.slot_names || []).filter((n) => n !== slotName);
    const meta = [t.kind, (t.works_with || []).join("、"), otherSlots.length ? `也用在 ${otherSlots.join("、")}` : ""].filter(Boolean);
    const name = t.url
      ? `<a class="tool-name" href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.name)}${ICON.ext}</a>`
      : `<span class="tool-name">${esc(t.name)}</span>`;
    return `
      <article class="tool-card">
        <div class="tool-head">${name}${statusTag(t)}</div>
        ${t.summary ? `<p class="tool-desc">${esc(t.summary)}</p>` : ""}
        ${t.trigger_when ? `<p class="tool-desc"><b>什麼時候用</b>　${esc(t.trigger_when)}</p>` : ""}
        ${meta.length ? `<div class="tool-tags">${meta.map(esc).join(" · ")}</div>` : ""}
      </article>`;
  }

  function renderTools() {
    const data = state.tools;
    if (!data || !data.available) {
      $("#profile-overlay-body").innerHTML = `<div><dt>個人設定</dt><dd>${esc(data?.error || "讀不到名冊")}</dd></div>`;
      $("#tools-grid").innerHTML = "";
      return;
    }
    const pf = data.profile;
    const excludes = (pf.exclude_models || []).length
      ? `<span class="mono">${pf.exclude_models.map(esc).join("、")}</span>`
      : "沒有";
    $("#profile-overlay-body").innerHTML = `
      <div><dt>個人設定</dt><dd>${esc(pf.name)}</dd></div>
      <div><dt>思考程度</dt><dd>${profileValue("thinking_preference", pf.thinking_preference)}</dd></div>
      <div><dt>子任務</dt><dd>${profileValue("visibility", pf.visibility)}</dd></div>
      <div><dt>額度用完時</dt><dd>${profileValue("on_exhausted", pf.on_exhausted)}</dd></div>
      <div><dt>不用的模型</dt><dd>${excludes}</dd></div>
    `;

    const term = state.toolSearch.trim().toLowerCase();
    const groups = new Map();
    const shownIds = new Set();
    for (const t of data.tools || []) {
      const hay = [t.id, t.name, t.summary, t.trigger_when, ...(t.slot_names || [])].join(" ").toLowerCase();
      if (term && !hay.includes(term)) continue;
      const inFilter = state.toolStatuses.has(t.status);
      if (inFilter) shownIds.add(t.id);
      for (const slot of t.slot_names?.length ? t.slot_names : ["沒有歸槽位"]) {
        if (!groups.has(slot)) groups.set(slot, { shown: [], others: [] });
        groups.get(slot)[inFilter ? "shown" : "others"].push(t);
      }
    }

    $("#tools-count").textContent = `${shownIds.size} / ${data.counts.total} 個`;
    const rank = (t) => STATUS_ORDER.indexOf(t.status);
    const slots = [...groups.entries()]
      .filter(([, g]) => g.shown.length)
      .sort((a, b) => Math.min(...a[1].shown.map(rank)) - Math.min(...b[1].shown.map(rank)) || a[0].localeCompare(b[0], "zh-Hant"));

    if (!slots.length) {
      $("#tools-grid").innerHTML = `<div class="empty-inline">沒有符合的工具</div>`;
      return;
    }
    $("#tools-grid").innerHTML = slots.map(([slot, g]) => {
      const others = g.others.sort((a, b) => rank(a) - rank(b));
      const othersText = others.length
        ? `<p class="slot-others">其他候選：${others.slice(0, 6).map((t) => `${esc(t.name)}（${STATUS_LABELS[t.status] || esc(t.status)}）`).join("、")}${others.length > 6 ? ` 等 ${others.length} 個` : ""}</p>`
        : "";
      return `
        <section class="slot-group">
          <div class="slot-head"><h2 class="slot-name">${esc(slot)}</h2><span class="muted-sm">${g.shown.length + g.others.length} 個工具</span></div>
          ${othersText}
          <div class="tool-grid">${g.shown.sort((a, b) => rank(a) - rank(b)).map((t) => toolCard(t, slot)).join("")}</div>
        </section>`;
    }).join("");
  }

  // ---------- 額度 ----------
  async function loadAccounts(refresh = false) {
    const btn = $("#btn-refresh-agy");
    btn.disabled = true;
    btn.textContent = "讀取中";
    try {
      state.accounts = await api(`/api/accounts${refresh ? "?refresh=1" : ""}`);
      renderAccounts();
      if (refresh) showToast("已重新讀取額度");
    } catch (err) {
      $("#accounts-root").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "重新讀取";
    }
  }

  const pad2 = (n) => String(n).padStart(2, "0");
  function fmtWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(d) - day(now)) / 86400000);
    const hm = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
    if (diff === 0) return `今天 ${hm}`;
    if (diff === 1) return `明天 ${hm}`;
    return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${hm}`;
  }
  function fmtAge(hours) {
    if (hours == null) return "";
    if (hours < 1) return "剛更新";
    if (hours < 48) return `${Math.round(hours)} 小時前更新`;
    return `${Math.round(hours / 24)} 天前更新`;
  }

  function meter(label, rem, resetIso, passed) {
    if (passed) {
      return `<div class="meter is-reset"><div class="meter-label">${label}</div><div class="meter-val">已回滿</div><div class="meter-bar"><i style="width:100%"></i></div><div class="meter-sub">重置時間已過</div></div>`;
    }
    if (rem == null) {
      return `<div class="meter is-unknown"><div class="meter-label">${label}</div><div class="meter-val">未知</div><div class="meter-bar"><i style="width:0"></i></div><div class="meter-sub">&nbsp;</div></div>`;
    }
    const val = Math.max(0, Math.min(100, Math.round(Number(rem))));
    const cls = val <= 0 ? "is-empty" : val <= 20 ? "is-low" : "";
    const when = fmtWhen(resetIso);
    return `<div class="meter ${cls}"><div class="meter-label">${label}</div><div class="meter-val">${val}%</div><div class="meter-bar"><i style="width:${val}%"></i></div><div class="meter-sub">${when ? `${when} 回滿` : "&nbsp;"}</div></div>`;
  }

  const passedAt = (iso) => {
    const d = iso ? new Date(iso) : null;
    return Boolean(d && !Number.isNaN(d.getTime()) && d.getTime() <= Date.now());
  };

  function renderAccounts() {
    const data = state.accounts;
    if (!data || !data.available) {
      $("#accounts-root").innerHTML = `<div class="empty-inline">${esc(data?.error || "讀不到帳號資料")}</div>`;
      return;
    }
    if (data.generated_at) $("#accounts-meta").textContent = `讀取 T3 替每個帳號查到的額度 · ${fmtWhen(data.generated_at)} 讀取`;

    const alerts = data.alerts || [];
    $("#accounts-alerts").innerHTML = alerts.map((a) => `
      <div class="alert-strip" style="margin:0 0 16px;"><div class="alert-strip-msg">${ICON.alert}<span>${esc(typeof a === "string" ? a : (a.message || a.text || JSON.stringify(a)))}</span></div></div>`).join("");

    const sel = data.claude_selection || {};
    const chosen = sel.chosen || "";
    const chosenRow = (data.claude || []).find((c) => c.instance === chosen);
    const reco = chosenRow
      ? `<div class="acct-reco">
          <div>
            <p class="acct-reco-title">下一個工作包建議用 Claude · ${esc(chosenRow.account || chosenRow.instance)}</p>
            ${sel.reason ? `<p class="acct-reco-why">${esc(String(sel.reason).replace(/^策略\s*[\w-]+：/, ""))}</p>` : ""}
          </div>
        </div>`
      : "";

    const srcName = { statusline: "Claude Code 狀態列", t3_cache: "T3", manual: "手動登記" };
    const claudeRows = (data.claude || []).map((c) => {
      const sub = [c.source ? `來自 ${srcName[c.source] || c.source}` : "還沒有資料", fmtAge(c.age_hours)].filter(Boolean);
      if (c.status === "stale") sub.push(`<span class="is-warn">資料較舊</span>`);
      return `
        <div class="acct-row">
          <div>
            <div class="acct-name"><span>${esc(c.account || c.instance)}</span>${c.instance === chosen ? `<span class="tag tag-accent">建議</span>` : ""}</div>
            <div class="acct-sub" title="${esc(c.instance)}">${sub.join(" · ")}</div>
          </div>
          <div class="meters" style="--cols:2">
            ${meter("5 小時", c.five_hour_remaining_pct, c.five_hour_resets_at, passedAt(c.five_hour_resets_at))}
            ${meter("本週", c.weekly_remaining_pct, c.weekly_resets_at, passedAt(c.weekly_resets_at))}
          </div>
        </div>`;
    }).join("");

    const agyRows = (data.antigravity || []).map((a) => {
      const b = a.buckets || {};
      const g = b.gemini || {};
      const t = b["3p"] || {};
      const tWeekly = t.weekly_remaining_pct != null || t.weekly_reset_passed;
      const sub = [a.auto ? "自動派工" : "手動"];
      if (a.quota_source) sub.push(`來自 ${a.quota_source === "t3_cache" ? "T3" : "agy CLI"}`);
      if (a.quota_age_hours != null) sub.push(a.quota_stale || a.quota_age_hours > 2 ? `<span class="is-warn">${fmtAge(a.quota_age_hours)}</span>` : fmtAge(a.quota_age_hours));
      if (a.blocked) sub.push(`<span class="is-alert">${esc(a.blocked_reason)}</span>`);
      else if (!a.quota_source && a.quota_error) sub.push(`<span class="is-warn">${esc(a.quota_error)}</span>`);
      return `
        <div class="acct-row ${a.blocked ? "is-blocked" : ""}">
          <div>
            <div class="acct-name"><span>${esc(a.account || a.instance)}</span></div>
            <div class="acct-sub" title="${esc(a.instance)}">${sub.join(" · ")}</div>
          </div>
          <div class="meters" style="--cols:3">
            ${meter("Gemini 5h", g.five_hour_remaining_pct, g.five_hour_resets_at, g.five_hour_reset_passed)}
            ${meter("Gemini 週", g.weekly_remaining_pct, g.weekly_resets_at, g.weekly_reset_passed)}
            ${tWeekly
              ? meter("Claude/GPT 週", t.weekly_remaining_pct, t.weekly_resets_at, t.weekly_reset_passed)
              : meter("Claude/GPT 5h", t.five_hour_remaining_pct, t.five_hour_resets_at, t.five_hour_reset_passed)}
          </div>
        </div>`;
    }).join("");

    $("#accounts-root").innerHTML = `
      ${reco}
      <section class="acct-group">
        <div class="acct-group-head"><h2>Claude</h2><span class="muted-sm">${(data.claude || []).length} 個帳號</span></div>
        <div class="acct-table">${claudeRows || `<div class="empty-inline">沒有 Claude 帳號</div>`}</div>
      </section>
      <section class="acct-group">
        <div class="acct-group-head"><h2>Antigravity</h2><span class="muted-sm">${(data.antigravity || []).length} 個帳號</span></div>
        <div class="acct-table">${agyRows || `<div class="empty-inline">沒有 Antigravity 帳號</div>`}</div>
      </section>
    `;
  }

  // ---------- 事件 ----------
  function bindEvents() {
    for (const btn of $$("[data-tab]")) btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    $("#btn-theme").addEventListener("click", toggleTheme);
    $("#btn-settings-theme").addEventListener("click", toggleTheme);
    $("#btn-settings-sync").addEventListener("click", () => {
      $("#dlg-settings").close();
      loadOverview(true);
    });
    $("#btn-sync").addEventListener("click", () => loadOverview(true));
    $("#btn-reconcile-all").addEventListener("click", triggerReconcileAll);
    $("#btn-refresh-tools").addEventListener("click", () => loadTools(true));
    $("#btn-refresh-agy").addEventListener("click", () => loadAccounts(true));

    $("#kpi-strip").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      state.filter = btn.dataset.filter;
      for (const p of $$("#kpi-strip [data-filter]")) {
        const on = p === btn;
        p.classList.toggle("is-active", on);
        p.setAttribute("aria-pressed", String(on));
      }
      renderList();
      const vis = filteredProjects();
      if (vis.length && !vis.some((x) => x.id === state.selectedId)) {
        state.selectedId = vis[0].id;
        renderList();
        renderInspector();
      }
    });

    $("#project-search").addEventListener("input", (e) => {
      state.search = e.target.value;
      renderList();
    });

    $("#project-list").addEventListener("click", (e) => {
      const row = e.target.closest("[data-select-project]");
      if (!row) return;
      state.selectedId = row.dataset.selectProject;
      renderList();
      renderInspector();
      if (window.innerWidth < 920) setMobileDetail(true);
    });

    $("#inspector-root").addEventListener("click", async (e) => {
      if (e.target.closest("#btn-mobile-back")) {
        setMobileDetail(false);
        return;
      }

      const clamp = e.target.closest(".clampable");
      if (clamp && !e.target.closest("a, button")) {
        clamp.classList.toggle("is-open");
        return;
      }

      const recBtn = e.target.closest("[data-reconcile]");
      if (recBtn) {
        triggerReconcile(recBtn.dataset.reconcile);
        return;
      }

      const copyNext = e.target.closest("[data-copy-next]");
      if (copyNext) {
        const p = state.overview?.projects.find((x) => x.id === copyNext.dataset.copyNext);
        if (p) copyText(p.commands.next_prompt, ` ${p.name} 的下一步指令`);
        return;
      }

      const viewNow = e.target.closest("[data-view-now]");
      if (viewNow) {
        const pid = viewNow.dataset.viewNow;
        try {
          const data = await api(`/api/projects/${encodeURIComponent(pid)}/now`);
          $("#dlg-now-title").textContent = `${pid} · NOW.md`;
          $("#dlg-now-path").textContent = data.path || "尚未建立";
          $("#dlg-now-body").textContent = data.exists ? data.content : "還沒有 NOW.md，對帳一次就會建立";
          $("#dlg-now").showModal();
        } catch (err) {
          showToast(err.message);
        }
        return;
      }

      const triBtn = e.target.closest("[data-toggle-tri]");
      if (triBtn) {
        const pid = triBtn.dataset.toggleTri;
        if (state.triFormOpen.has(pid)) state.triFormOpen.delete(pid);
        else state.triFormOpen.add(pid);
        renderInspector();
        return;
      }

      const togBtn = e.target.closest("[data-toggle-critique]");
      if (togBtn) {
        const pid = togBtn.dataset.toggleCritique;
        const idx = Number(togBtn.dataset.idx);
        const curDone = togBtn.dataset.done === "1";
        togBtn.disabled = true;
        try {
          await api(`/api/projects/${encodeURIComponent(pid)}/critiques/${idx}`, {
            method: "PATCH",
            body: JSON.stringify({ done: !curDone }),
          });
          showToast(curDone ? "已重開" : "已勾掉");
          await loadOverview(false, true);
        } catch (err) {
          showToast(err.message);
        }
        return;
      }

      const parkBtn = e.target.closest("[data-park]");
      if (parkBtn) {
        const pid = parkBtn.dataset.park;
        const curParked = parkBtn.dataset.parked === "1";
        try {
          await api(`/api/projects/${encodeURIComponent(pid)}`, {
            method: "PATCH",
            body: JSON.stringify({ parked: !curParked }),
          });
          showToast(curParked ? `已把 ${pid} 移回` : `已停泊 ${pid}`);
          await loadOverview(false, true);
        } catch (err) {
          showToast(err.message);
        }
      }
    });

    $("#inspector-root").addEventListener("submit", async (e) => {
      const form = e.target.closest("[data-add-critique]");
      if (!form) return;
      e.preventDefault();
      const pid = form.dataset.addCritique;
      const fd = new FormData(form);
      const payload = {
        text: String(fd.get("text") || "").trim(),
        symptom: String(fd.get("symptom") || "").trim(),
        pain: String(fd.get("pain") || "").trim(),
        criteria: String(fd.get("criteria") || "").trim(),
        project_path: form.dataset.path || "",
      };
      if (!payload.text && !payload.pain && !payload.symptom && !payload.criteria) return;
      try {
        await api(`/api/projects/${encodeURIComponent(pid)}/critiques`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        form.reset();
        state.triFormOpen.delete(pid);
        showToast(`已記下（${pid}）`);
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      }
    });

    $("#tools-search").addEventListener("input", (e) => {
      state.toolSearch = e.target.value;
      renderTools();
    });
    $("#tools-status-chips").addEventListener("click", (e) => {
      const chip = e.target.closest("[data-st]");
      if (!chip) return;
      const st = chip.dataset.st;
      const next = !state.toolStatuses.has(st);
      if (next) state.toolStatuses.add(st);
      else state.toolStatuses.delete(st);
      chip.classList.toggle("is-active", next);
      chip.setAttribute("aria-pressed", String(next));
      renderTools();
    });

    for (const closeBtn of $$("[data-close]")) {
      closeBtn.addEventListener("click", () => closeBtn.closest("dialog")?.close());
    }

    $("#btn-add-project").addEventListener("click", () => {
      $("#form-project").reset();
      $("#dlg-project").showModal();
    });
    $("#form-project").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const name = String(fd.get("name") || "").trim();
      const path = String(fd.get("path") || "").trim();
      if (!name) return;
      try {
        await api("/api/projects/register", { method: "POST", body: JSON.stringify({ name, path }) });
        $("#dlg-project").close();
        showToast(`已登記 ${name}`);
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      }
    });

    $("#btn-settings").addEventListener("click", () => {
      const set = state.overview?.settings || {};
      $("#inp-t3-url").value = set.t3_base_url || "";
      $("#inp-parked-days").value = set.parked_days ?? 3;
      $("#inp-overload").value = set.overload_items ?? 1000;
      $("#inp-auto-commit").checked = set.auto_commit_status !== false;
      $("#inp-auto-push").checked = Boolean(set.auto_push_status);
      $("#dlg-settings").showModal();
    });
    $("#form-settings").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/settings", {
          method: "PATCH",
          body: JSON.stringify({
            t3_base_url: $("#inp-t3-url").value.trim(),
            parked_days: Number($("#inp-parked-days").value || 3),
            overload_items: Number($("#inp-overload").value || 1000),
            auto_commit_status: $("#inp-auto-commit").checked,
            auto_push_status: $("#inp-auto-push").checked,
          }),
        });
        $("#dlg-settings").close();
        showToast("設定已儲存");
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "")) {
        e.preventDefault();
        (state.activeTab === "tools" ? $("#tools-search") : $("#project-search"))?.focus();
      }
    });
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  async function loadSession() {
    try {
      const res = await fetch("/api/session", { cache: "no-store" });
      const s = await res.json();
      state.session = { writable: Boolean(s.writable), token: s.token || null, mode: s.mode || "local" };
    } catch {
      // 讀不到就維持預設；寫入時伺服器會再擋一次
    }
    document.body.classList.toggle("is-readonly", !state.session.writable);
    const banner = $("#readonly-banner");
    if (banner) banner.hidden = state.session.writable;
  }

  initTheme();
  bindEvents();
  loadSession().finally(() => loadOverview(false));
})();
