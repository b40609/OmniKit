// OmniKit 個人指揮台（Linear × Raycast 主從工作台 + 一鍵背景自動對帳）
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
    pollTimer: null,
    wasBusy: false,
  };

  const LANE_ORDER = ["blocked_on_me", "ready_to_settle", "active", "parked"];
  const LANE_NAMES = {
    blocked_on_me: "等你處理",
    ready_to_settle: "跑完待收尾／需對帳",
    active: "執行中",
    parked: "已停泊",
  };
  const LANE_DOT = {
    blocked_on_me: "d-blocked",
    ready_to_settle: "d-settle",
    active: "d-active",
    parked: "d-parked",
  };
  const SLOPE_LABEL = {
    uphill: { text: "上坡 · 探索中", cls: "pill-trial" },
    downhill: { text: "下坡 · 純執行", cls: "pill-active" },
    unknown: null,
  };
  const STATUS_LABELS = {
    default: "預設",
    trial: "試用",
    on_demand: "按需備案",
    assess: "觀察",
    pending: "待評估",
    rejected: "拒絕",
    retired: "退役",
  };

  const ICON = {
    zap: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
    ext: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
    back: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>`,
    alert: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
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

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `請求失敗 (${res.status})`);
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
      showToast(`已複製：${label}`);
    } catch {
      showToast("複製失敗，請手動選取");
    }
  }

  // ---------- 深淺色切換 ----------
  function initTheme() {
    const saved = localStorage.getItem("omnikit-theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.dataset.theme = saved;
    }
  }

  function toggleTheme() {
    const cur = document.documentElement.dataset.theme;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDarkNow = cur ? cur === "dark" : prefersDark;
    const next = isDarkNow ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("omnikit-theme", next);
  }

  // ---------- 分頁切換 ----------
  function switchTab(tab) {
    state.activeTab = tab;
    for (const btn of $$("[data-tab]")) {
      const on = btn.dataset.tab === tab;
      if (on) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    }
    for (const sec of $$(".tab-panel")) {
      sec.hidden = sec.id !== `tab-${tab}`;
    }
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
    if (state.mobileDetail) $("#main-scroll").scrollTop = 0;
  }

  // ---------- 自動對帳輪詢 ----------
  function syncPolling(reconcile) {
    const busy = Boolean(reconcile?.busy);
    const banner = $("#reconcile-banner");
    const bannerText = $("#reconcile-banner-text");
    const allBtn = $("#btn-reconcile-all");
    const allLabel = $("#reconcile-all-label");

    const staleLocal = (state.overview?.projects || []).filter((p) => p.stale && p.local_available).length;

    if (busy) {
      const running = reconcile.running_project;
      const runJob = running ? reconcile.jobs?.[running] : null;
      banner.hidden = false;
      bannerText.textContent = runJob
        ? `背景自動對帳中（佇列剩 ${reconcile.active_count}）：${runJob.project_name} — ${runJob.message}`
        : `背景自動對帳中（剩 ${reconcile.active_count} 個專案）…`;
      allLabel.textContent = `對帳中 (${reconcile.active_count})`;
      allBtn.disabled = true;
      if (!state.pollTimer) {
        state.pollTimer = setInterval(pollReconcile, 3000);
      }
    } else {
      banner.hidden = true;
      allBtn.disabled = false;
      allLabel.textContent = staleLocal > 0 ? `對帳 (${staleLocal})` : "全部對帳";
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
      if (state.wasBusy) {
        showToast("背景自動對帳已完成，已更新最新狀態");
      }
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
      // 忽略短暫網路波動，下一輪續試
    }
  }

  async function triggerReconcile(projectId) {
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/reconcile`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      showToast(`已派送 ${projectId} 自動對帳（T3 可見對話）`);
      syncPolling(res.reconcile);
      renderList();
      renderInspector();
    } catch (err) {
      showToast(err.message);
    }
  }

  async function triggerReconcileAll() {
    const staleLocal = (state.overview?.projects || []).filter((p) => p.stale && p.local_available).length;
    try {
      const res = await api("/api/reconcile-all", {
        method: "POST",
        body: JSON.stringify({ only_stale: staleLocal > 0 }),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      const n = res.queued?.length || 0;
      if (n === 0) {
        showToast("目前沒有需要對帳的本機專案");
      } else {
        showToast(`已將 ${n} 個專案排入自動對帳佇列（一次一條安全執行）`);
      }
      syncPolling(res.reconcile);
      renderList();
      renderInspector();
    } catch (err) {
      showToast(err.message);
    }
  }

  // ---------- 載入與渲染：專案指揮台 ----------
  async function loadOverview(sync = false, silent = false) {
    const syncBtn = $("#btn-sync");
    if (!silent) syncBtn.disabled = true;
    try {
      const data = await api(`/api/overview${sync ? "?sync=1" : ""}`);
      state.overview = data;
      // 確保預設選中第一順位專案
      if (!state.selectedId || !data.projects.some((p) => p.id === state.selectedId)) {
        state.selectedId = data.projects[0]?.id || null;
      }
      renderOverview();
      if (sync) {
        showToast(data.sync?.synced ? "已同步狀態庫並重新掃描" : "已完成本機重新掃描");
      }
    } catch (err) {
      $("#project-list").innerHTML = `<div class="empty-inline">載入失敗：${esc(err.message)}</div>`;
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
    if (p.now.next_action?.text) return p.now.next_action.text;
    if (p.now.conclusions?.[0]) return p.now.conclusions[0];
    if (p.git?.last_subject) return `${p.git.last_hash} ${p.git.last_subject}`;
    return p.stale ? "尚未同步 NOW.md，點自動對帳補齊" : "目前狀態乾淨";
  }

  function projectRightTag(p, job) {
    if (job && (job.status === "running" || job.status === "queued")) {
      return { text: job.status === "running" ? "對帳中…" : "排隊中", cls: "t-accent" };
    }
    if (p.open_critiques_count > 0) {
      return { text: `待改 ${p.open_critiques_count}`, cls: "t-blocked" };
    }
    const commitsBehind = p.git?.commits_since_now || 0;
    if (commitsBehind > 0) {
      return { text: `落後 ${commitsBehind}`, cls: "t-warn" };
    }
    if (p.stale) {
      return { text: p.now.exists ? "已過期" : "缺 NOW", cls: "t-warn" };
    }
    const prog = p.now.progress;
    if (prog?.total) {
      return { text: `${prog.done}/${prog.total}`, cls: "" };
    }
    return { text: p.last_activity_age, cls: "" };
  }

  function renderList() {
    const list = filteredProjects();
    const root = $("#project-list");
    const jobs = state.overview?.reconcile?.jobs || {};

    if (!list.length) {
      root.innerHTML = `<div class="empty-inline">沒有符合條件的專案。</div>`;
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
        const selected = p.id === state.selectedId;
        const job = jobs[p.id];
        const tag = projectRightTag(p, job);
        const prog = p.now.progress || {};
        const hasSteps = prog.total != null && prog.total > 0;
        const pct = hasSteps ? Math.min(100, Math.round((prog.done / prog.total) * 100)) : 0;

        const foot = [];
        if (p.git?.available) {
          foot.push(esc(p.git.branch));
          if (p.git.dirty_count > 0) foot.push(`<span class="f-warn">+${p.git.dirty_count}</span>`);
        } else if (p.remote_only) {
          foot.push("遠端");
        }
        if (p.t3?.unsettled_count > 0) foot.push(`${p.t3.unsettled_count} 對話`);
        if (p.t3?.overloaded_count > 0) foot.push(`<span class="f-alert">超載</span>`);
        foot.push(esc(p.last_activity_age));

        html.push(`
          <button type="button" class="proj-row ${selected ? "is-selected" : ""}" data-select-project="${esc(p.id)}">
            <div class="row-top">
              <span class="row-title">
                <i class="sdot ${LANE_DOT[p.lane]}"></i>
                <span class="row-title-text">${esc(p.name)}</span>
              </span>
              <span class="row-tag ${tag.cls}">${esc(tag.text)}</span>
            </div>
            <div class="row-preview">${esc(projectPreviewLine(p))}</div>
            <div class="row-foot">${foot.join(" · ")}</div>
            ${hasSteps ? `<div class="mini-progress"><i style="width:${pct}%"></i></div>` : ""}
          </button>
        `);
      }
    }
    root.innerHTML = html.join("");
  }

  function renderInspector() {
    const ov = state.overview;
    const root = $("#inspector-root");
    if (!ov) return;

    const p = ov.projects.find((x) => x.id === state.selectedId) || filteredProjects()[0];
    if (!p) {
      root.innerHTML = `<div class="empty-inline">目前沒有可顯示的專案。</div>`;
      return;
    }

    const job = ov.reconcile?.jobs?.[p.id];
    const isBusy = job && (job.status === "running" || job.status === "queued");
    const prog = p.now.progress || {};
    const hasSteps = prog.total != null && prog.total > 0;
    const pct = hasSteps ? Math.min(100, Math.round((prog.done / prog.total) * 100)) : 0;
    const slope = SLOPE_LABEL[prog.slope];
    const triOpen = state.triFormOpen.has(p.id);

    // 狀態警示橫幅（有過期、超載或正在對帳時才顯示）
    let alertBanner = "";
    if (isBusy) {
      alertBanner = `
        <div class="alert-strip is-running">
          <div class="alert-strip-msg"><span class="pulse-dot"></span><span>${esc(job.message)}</span></div>
          ${job.thread_url ? `<a class="btn btn-subtle btn-sm" href="${esc(job.thread_url)}" target="_blank" rel="noopener">看 T3 過程 ↗</a>` : ""}
        </div>
      `;
    } else if (job && job.status === "error") {
      alertBanner = `
        <div class="alert-strip">
          <div class="alert-strip-msg">${ICON.alert}<span>${esc(job.message)}</span></div>
          <button type="button" class="btn btn-subtle btn-sm" data-reconcile="${esc(p.id)}">重試對帳</button>
        </div>
      `;
    } else if (p.stale || p.t3?.overloaded_count > 0) {
      const msgs = [...p.stale_reasons];
      if (p.t3?.overloaded_count > 0) msgs.push(`${p.t3.overloaded_count} 條主線超過 ${ov.settings.overload_items} 項建議交接`);
      alertBanner = `
        <div class="alert-strip">
          <div class="alert-strip-msg">${ICON.alert}<span>${esc(msgs.join(" · "))}</span></div>
        </div>
      `;
    }

    // 元資訊條
    const meta = [];
    if (p.git?.available) {
      meta.push(`<span>${esc(p.git.branch)}</span>`);
      if (p.git.last_hash) meta.push(`<span>${esc(p.git.last_hash)}</span>`);
      if (p.git.dirty_count > 0) meta.push(`<span class="m-warn">未提交 ${p.git.dirty_count} 檔</span>`);
      if (p.git.ahead > 0) meta.push(`<span class="m-warn">未推 ${p.git.ahead}</span>`);
    } else {
      meta.push(`<span>遠端專案（無本機目錄）</span>`);
    }
    if (p.t3?.available) {
      meta.push(`<span>未結案 ${p.t3.unsettled_count} 條</span>`);
    }
    meta.push(`<span>最後活躍 ${esc(p.last_activity_age)}</span>`);

    // 1. 下一步
    const nxt = p.now.next_action;
    const ownerPill = nxt
      ? (nxt.owner === "user"
        ? `<span class="pill pill-blocked">球權：等你處理</span>`
        : nxt.owner === "agent"
          ? `<span class="pill pill-active">球權：Agent 可直接跑</span>`
          : "")
      : "";
    const decisionsHtml = p.now.decisions?.length
      ? `<div class="decisions-block"><div class="sec-label">待拍板決定</div><ul>${p.now.decisions.map((d) => `<li>${esc(d)}</li>`).join("")}</ul></div>`
      : "";

    // 2. 不滿意待改清單
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
            <button type="button" class="check-hit" data-toggle-critique="${esc(p.id)}" data-idx="${c.index}" data-done="${c.done ? "1" : "0"}" aria-label="${c.done ? "重開待改項" : "勾銷待改項"}">
              <span class="check-box">${c.done ? "✓" : ""}</span>
            </button>
            <div class="critique-text">${body}</div>
          </li>`;
        }).join("")}</ul>`
      : `<p class="empty-muted" style="margin-bottom:10px;">目前沒有未收斂的不滿意項目。</p>`;

    // 3. T3 活躍對話列表
    const threads = p.t3?.threads || [];
    const threadsHtml = threads.length
      ? `<div class="thread-table">${threads.map((t) => `
          <div class="thread-item">
            <div class="thread-main">
              <div class="thread-name">${esc(t.title)}</div>
              <div class="thread-sub">
                ${esc(t.status)} · <span class="${t.overloaded ? "is-over" : ""}">${t.item_count} items${t.overloaded ? "（超載）" : ""}</span>${t.model ? ` · ${esc(t.model)}` : ""}
              </div>
            </div>
            ${t.link ? `<a class="btn btn-subtle btn-sm" href="${esc(t.link)}" target="_blank" rel="noopener">開啟 ↗</a>` : ""}
          </div>
        `).join("")}</div>`
      : `<p class="empty-muted">目前沒有未結案的 T3 對話。</p>`;

    const lanePillCls = {
      blocked_on_me: "pill-blocked",
      ready_to_settle: "pill-settle",
      active: "pill-active",
      parked: "pill-muted",
    }[p.lane] || "pill-muted";

    root.innerHTML = `
      <div class="mobile-back-bar">
        <button type="button" class="btn btn-subtle btn-sm" id="btn-mobile-back">${ICON.back} 所有專案</button>
        <div style="display:flex;gap:6px;">
          ${p.local_available ? `<button type="button" class="btn btn-accent btn-sm" data-reconcile="${esc(p.id)}" ${isBusy ? "disabled" : ""}>${ICON.zap} ${isBusy ? "對帳中" : "自動對帳"}</button>` : ""}
          ${p.primary_t3_url ? `<a class="btn btn-subtle btn-sm" href="${esc(p.primary_t3_url)}" target="_blank" rel="noopener">T3 ↗</a>` : ""}
        </div>
      </div>

      <div class="insp-header">
        <div>
          <div class="insp-title-row">
            <h2 class="insp-title">${esc(p.name)}</h2>
            <span class="pill ${lanePillCls}">${esc(LANE_NAMES[p.lane])}</span>
            ${slope ? `<span class="pill ${slope.cls}">${slope.text}</span>` : ""}
            ${p.remote_only ? `<span class="pill pill-info">遠端專案</span>` : ""}
          </div>
          <div class="insp-meta">${meta.join("")}</div>
          <div class="sub-actions">
            <button type="button" class="link-btn" data-view-now="${esc(p.id)}">檢視 NOW.md 原文</button>
            <button type="button" class="link-btn" data-copy-next="${esc(p.id)}">複製下一步指令</button>
            <button type="button" class="link-btn" data-park="${esc(p.id)}" data-parked="${p.manual_parked ? "1" : "0"}">${p.manual_parked ? "移回活躍區" : "移入停泊區"}</button>
          </div>
        </div>

        <div class="insp-actions">
          ${p.local_available ? `<button type="button" class="btn btn-accent" data-reconcile="${esc(p.id)}" ${isBusy ? "disabled" : ""}>${ICON.zap} ${isBusy ? "對帳中…" : "自動對帳"}</button>` : ""}
          ${p.primary_t3_url ? `<a class="btn btn-subtle" href="${esc(p.primary_t3_url)}" target="_blank" rel="noopener">打開 T3 ${ICON.ext}</a>` : ""}
        </div>
      </div>

      ${alertBanner}

      <!-- 焦點 1：下一步 -->
      <section class="insp-section">
        <div class="sec-kicker">
          <span class="sec-label">下一步</span>
          ${ownerPill}
        </div>
        <p class="next-lead">${nxt ? esc(nxt.text) : "尚未填寫下一步 — 點右上角「自動對帳」即可由最近進度補齊。"}</p>
        ${decisionsHtml}
      </section>

      <!-- 焦點 2：進度 ＋ 現行結論 -->
      <section class="insp-section two-col">
        <div>
          <div class="sec-kicker"><span class="sec-label">進度與完工路徑</span></div>
          <div class="big-metric">
            <strong>${hasSteps ? `${prog.done}/${prog.total}` : "—"}</strong>
            <span>${hasSteps ? `完成 ${pct}%` : "尚未標記步數"}</span>
          </div>
          ${hasSteps ? `<div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>` : ""}
          ${prog.steps?.length
            ? `<ul class="clean-list">${prog.steps.map((s) => `<li><span class="step-mark ${s.done ? "is-done" : ""}">${s.done ? "✓" : "○"}</span><span>${esc(s.text)}</span></li>`).join("")}</ul>`
            : `<p class="empty-muted">${esc(prog.summary || "點「自動對帳」自動整理階段步驟。")}</p>`}
        </div>

        <div>
          <div class="sec-kicker"><span class="sec-label">現行結論（最新定案）</span></div>
          ${p.now.conclusions?.length
            ? `<ul class="clean-list">${p.now.conclusions.slice(0, 3).map((c) => `<li><i class="bullet-dot"></i><span>${esc(c)}</span></li>`).join("")}</ul>`
            : `<p class="empty-muted">尚未整理現行結論，點「自動對帳」自動摘要近期決策。</p>`}
          ${p.git?.last_subject ? `<p class="empty-muted" style="margin-top:12px;font-family:var(--mono);font-size:12px;">最新 commit：${esc(p.git.last_hash)} ${esc(p.git.last_subject)}</p>` : ""}
        </div>
      </section>

      <!-- 焦點 3：不滿意待改匣 -->
      <section class="insp-section">
        <div class="sec-kicker">
          <span class="sec-label">不滿意待改匣</span>
          <span class="mono muted-sm">未收斂 ${p.open_critiques_count} 條</span>
        </div>
        ${critiquesHtml}
        <form class="critique-composer" data-add-critique="${esc(p.id)}" data-path="${esc(p.path || "")}">
          ${triOpen ? `
            <div class="tri-inputs">
              <input class="composer-input" name="symptom" placeholder="① 現況（現在長怎樣）">
              <input class="composer-input" name="pain" placeholder="② 痛點（嫌哪裡不滿意）" required>
              <input class="composer-input" name="criteria" placeholder="③ 過關標準（改成怎樣算過）">
            </div>
            <div class="composer-row">
              <button type="submit" class="btn btn-accent btn-sm">新增待改</button>
              <button type="button" class="btn btn-subtle btn-sm" data-toggle-tri="${esc(p.id)}">切回單行速記</button>
            </div>
          ` : `
            <div class="composer-row">
              <input class="composer-input" name="text" placeholder="隨手記一條不滿意，Enter 直接寫入 NOW.md…" required>
              <button type="submit" class="btn btn-accent btn-sm">記下</button>
              <button type="button" class="btn btn-subtle btn-sm" data-toggle-tri="${esc(p.id)}">三段式</button>
            </div>
          `}
        </form>
      </section>

      <!-- 焦點 4：T3 未結案對話 -->
      <section class="insp-section">
        <div class="sec-kicker">
          <span class="sec-label">T3 未結案對話</span>
          <span class="mono muted-sm">${p.t3?.unsettled_count || 0} 條</span>
        </div>
        ${threadsHtml}
      </section>
    `;
  }

  function renderOverview() {
    const ov = state.overview;
    if (!ov) return;
    const s = ov.summary;
    $("#sync-meta").textContent = ov.generated_local;
    $("#kpi-total").textContent = s.total;
    $("#kpi-blocked").textContent = s.blocked_on_me;
    $("#kpi-settle").textContent = s.ready_to_settle;
    $("#kpi-active").textContent = s.active;
    $("#kpi-stale").textContent = s.stale;

    syncPolling(ov.reconcile);
    renderList();
    renderInspector();
  }

  // ---------- 分頁 2：工具與模型 ----------
  async function loadTools(refresh = false) {
    $("#tools-grid").innerHTML = `<div class="empty-inline">載入工具名冊中…</div>`;
    try {
      state.tools = await api(`/api/tools${refresh ? "?refresh=1" : ""}`);
      renderTools();
    } catch (err) {
      $("#tools-grid").innerHTML = `<div class="empty-inline">載入失敗：${esc(err.message)}</div>`;
    }
  }

  function renderTools() {
    const data = state.tools;
    if (!data || !data.available) {
      $("#profile-overlay-body").textContent = data?.error || "無法載入名冊";
      $("#tools-grid").innerHTML = "";
      return;
    }
    const pf = data.profile;
    const excludes = (pf.exclude_models || []).length
      ? pf.exclude_models.map((m) => `<span class="pill pill-blocked mono">${esc(m)}</span>`).join("")
      : `<span class="muted-sm">無</span>`;

    $("#profile-overlay-body").innerHTML = `
      <div class="kv"><span>Profile</span><b>${esc(pf.name)}</b></div>
      <div class="kv"><span>思考偏好</span><code class="pill pill-active">${esc(pf.thinking_preference)}</code></div>
      <div class="kv"><span>派送模式</span><code class="pill pill-info">${esc(pf.visibility)}</code></div>
      <div class="kv"><span>耗盡策略</span><code class="pill pill-settle">${esc(pf.on_exhausted)}</code></div>
      <div class="kv"><span>屏蔽模型</span>${excludes}</div>
    `;

    const term = state.toolSearch.trim().toLowerCase();
    const list = (data.tools || []).filter((t) => {
      if (!state.toolStatuses.has(t.status)) return false;
      if (!term) return true;
      const hay = [t.id, t.name, t.summary, t.trigger_when, ...(t.slot_names || [])].join(" ").toLowerCase();
      return hay.includes(term);
    });

    $("#tools-count").textContent = `${list.length} / ${data.counts.total}`;
    if (!list.length) {
      $("#tools-grid").innerHTML = `<div class="empty-inline">沒有符合的工具卡。</div>`;
      return;
    }
    const clsMap = { default: "pill-active", trial: "pill-trial", on_demand: "pill-info", assess: "pill-info", pending: "pill-muted", rejected: "pill-blocked", retired: "pill-settle" };
    $("#tools-grid").innerHTML = list.map((t) => `
      <article class="tool-card">
        <div class="tool-head">
          <span class="tool-name">${t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.name)}</a>` : esc(t.name)}</span>
          <span class="pill ${clsMap[t.status] || "pill-muted"}">${STATUS_LABELS[t.status] || esc(t.status)}</span>
        </div>
        ${t.summary ? `<p class="tool-desc">${esc(t.summary)}</p>` : ""}
        ${t.trigger_when ? `<p class="tool-desc"><b>喚起：</b>${esc(t.trigger_when)}</p>` : ""}
        <div class="tool-tags">${[t.kind, ...(t.slot_names || [])].filter(Boolean).map((x) => `<span>${esc(x)}</span>`).join(" · ")}</div>
      </article>
    `).join("");
  }

  // ---------- 分頁 3：帳號與額度 ----------
  async function loadAccounts(refreshAgy = false) {
    const btn = $("#btn-refresh-agy");
    btn.disabled = true;
    btn.textContent = refreshAgy ? "刷新中…" : "載入中…";
    try {
      state.accounts = await api(`/api/accounts${refreshAgy ? "?refresh=1" : ""}`);
      renderAccounts();
      if (refreshAgy) showToast("已刷新 Antigravity 額度");
    } catch (err) {
      $("#accounts-root").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "刷新 Antigravity 額度";
    }
  }

  function shortIso(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} 重置`;
  }

  function qRow(label, remPct, resetIso) {
    const val = remPct == null ? null : Math.max(0, Math.min(100, Math.round(Number(remPct))));
    const cls = val == null ? "" : val <= 20 ? "is-low" : val <= 45 ? "is-mid" : "";
    const reset = shortIso(resetIso);
    return `
      <div class="qrow">
        <div class="qrow-head"><span>${esc(label)}${reset ? ` · ${reset}` : ""}</span><b>${val == null ? "未知" : `剩 ${val}%`}</b></div>
        <div class="bar-track"><div class="bar-fill ${cls}" style="width:${val == null ? 0 : val}%"></div></div>
      </div>
    `;
  }

  function renderAccounts() {
    const data = state.accounts;
    if (!data || !data.available) {
      $("#accounts-root").innerHTML = `<div class="empty-inline">${esc(data?.error || "無帳號資料")}</div>`;
      return;
    }
    const alerts = data.alerts || [];
    $("#accounts-alerts").innerHTML = alerts.length
      ? alerts.map((a) => `<div class="alert-strip" style="margin-bottom:12px;"><div class="alert-strip-msg">${ICON.alert}<span>${esc(typeof a === "string" ? a : (a.message || a.text || JSON.stringify(a)))}</span></div></div>`).join("")
      : "";

    const recInst = data.claude_selection?.selected || data.claude_selection?.instance || "";
    const claudeHtml = (data.claude || []).map((c) => {
      const isRec = recInst && c.instance === recInst;
      return `
        <article class="acct-card ${isRec ? "is-rec" : ""}">
          <div class="acct-head">
            <span class="acct-title">Claude · ${esc(c.account || c.instance)}</span>
            <span class="pill ${isRec ? "pill-active" : "pill-muted"}">${isRec ? "優先選號" : esc(c.status || "ok")}</span>
          </div>
          ${qRow("5 小時", c.five_hour_remaining_pct, c.five_hour_resets_at)}
          ${qRow("本週", c.weekly_remaining_pct, c.weekly_resets_at)}
          <div class="thread-sub">${esc(c.instance)} · ${c.age_hours != null ? `${c.age_hours}h 前快照` : "無快照"}</div>
        </article>
      `;
    }).join("");

    const agyHtml = (data.antigravity || []).map((a) => {
      const b = a.buckets || {};
      const g = b.gemini || {};
      const t = b["3p"] || {};
      return `
        <article class="acct-card">
          <div class="acct-head">
            <span class="acct-title">Antigravity · ${esc(a.account || a.instance)}</span>
            <span class="pill ${a.auto ? "pill-active" : "pill-muted"}">${a.auto ? "自動派工" : "手動池"}</span>
          </div>
          ${qRow("Gemini 5h", g.five_hour_remaining_pct, g.five_hour_resets_at)}
          ${qRow("Gemini 週", g.weekly_remaining_pct, g.weekly_resets_at)}
          ${qRow("Claude & GPT 桶", t.weekly_remaining_pct ?? t.five_hour_remaining_pct, t.weekly_resets_at || t.five_hour_resets_at)}
          <div class="thread-sub">${esc(a.instance)}${g.stale ? " · 舊快照" : ""}</div>
        </article>
      `;
    }).join("");

    $("#accounts-root").innerHTML = `
      <div>
        <div class="sec-kicker"><span class="sec-label">Claude 實例（${(data.claude || []).length}）</span></div>
        <div class="acct-grid">${claudeHtml}</div>
      </div>
      <div>
        <div class="sec-kicker"><span class="sec-label">Antigravity 實例（${(data.antigravity || []).length}）</span></div>
        <div class="acct-grid">${agyHtml}</div>
      </div>
    `;
  }

  // ---------- 事件綁定 ----------
  function bindEvents() {
    for (const btn of $$("[data-tab]")) {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    }
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

    // 左欄選擇專案
    $("#project-list").addEventListener("click", (e) => {
      const row = e.target.closest("[data-select-project]");
      if (!row) return;
      state.selectedId = row.dataset.selectProject;
      renderList();
      renderInspector();
      if (window.innerWidth < 920) setMobileDetail(true);
    });

    // 右側焦點工作區互動
    $("#inspector-root").addEventListener("click", async (e) => {
      if (e.target.closest("#btn-mobile-back")) {
        setMobileDetail(false);
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
        if (p) copyText(p.commands.next_prompt, `${p.name} 下一步指令`);
        return;
      }

      const viewNow = e.target.closest("[data-view-now]");
      if (viewNow) {
        const pid = viewNow.dataset.viewNow;
        try {
          const data = await api(`/api/projects/${encodeURIComponent(pid)}/now`);
          $("#dlg-now-title").textContent = `${pid} · NOW.md`;
          $("#dlg-now-path").textContent = data.path || "尚未建立";
          $("#dlg-now-body").textContent = data.exists ? data.content : "（尚未建立 NOW.md，點「自動對帳」即可自動建立。）";
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
          showToast(curDone ? "已重開待改項" : "已勾銷待改項");
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
          showToast(curParked ? `已恢復 ${pid}` : `已將 ${pid} 移入停泊`);
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
        showToast(`已記下不滿意待改（${pid}）`);
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      }
    });

    // 工具頁過濾
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

    // Modal 控制
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

  initTheme();
  bindEvents();
  loadOverview(false);
})();
