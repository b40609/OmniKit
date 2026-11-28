// OmniKit 本機控制面板：首頁開箱精靈與總覽、專案狀態板、精選工作台商店、Agent 健康檢查與額度、設定
(() => {
  const state = {
    activeTab: "home",
    filter: "all",
    search: "",
    selectedId: null,
    mobileDetail: false,
    bootstrap: null,
    overview: null,
    tools: null,
    accounts: null,
    doctor: null,
    workbenchView: "curated",
    toolStatuses: new Set(["default", "trial", "on_demand"]),
    toolSearch: "",
    triFormOpen: new Set(),
    mapLoaded: false,
    forceSetupWizard: false,
    setupDraft: null,
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
  const LAYER_LABELS = {
    L1: "L1 核心防護與真機瀏覽器（強烈建議常駐）",
    L2: "L2 開箱精選技能與自動化（免金鑰即裝即用）",
    L3: "L3 進階專業工作流與選配整合",
    L4: "L4 試用評估中（定期檢視去留）",
  };
  const AGENT_DISPLAY = {
    "claude-code": "Claude Code",
    claude: "Claude",
    codex: "Codex",
    antigravity: "Antigravity",
  };
  const PROFILE_TEXT = {
    thinking_preference: { max_available: "用能開的最高程度", high: "high", xhigh: "xhigh", default: "依任務分級" },
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
    shield: svg(`<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>`),
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

  function safeUrl(raw) {
    const s = String(raw || "").trim();
    return /^https?:\/\//i.test(s) ? s : "";
  }

  const stripOwnerTag = (text) => String(text || "").replace(/^\s*【[^】]{1,16}】\s*/, "");

  let toastTimer = null;
  function showToast(msg) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 3000);
  }

  const READONLY_MSG = "經 Tailscale 開啟時為唯讀檢視；請在這台電腦本機開啟面板進行變更";

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

  async function copyText(text, label = "") {
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

  function initTheme() {
    try {
      const saved = localStorage.getItem("omnikit-theme");
      if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
    } catch {
      // 私密瀏覽讀不到時跟隨系統
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
      // ignore
    }
  }

  // ---------- 分頁切換 ----------
  function switchTab(tab) {
    state.activeTab = tab;
    for (const btn of $$("[data-tab]")) {
      if (btn.dataset.tab === tab) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    }
    for (const sec of $$(".tab-panel")) sec.hidden = sec.id !== `tab-${tab}`;
    syncDetailChrome();
    if (tab === "tools") {
      renderWorkbenchTab();
      if (state.workbenchView === "catalog" && !state.tools) loadTools(false);
    }
    if (tab === "accounts") {
      if (!state.doctor) loadDoctor(false);
      if (!state.accounts) loadAccounts(false);
    }
    if (tab === "settings") {
      renderSettingsPage();
    }
  }

  function setMobileDetail(open) {
    state.mobileDetail = Boolean(open);
    $("#tab-cockpit").classList.toggle("mobile-detail", state.mobileDetail);
    syncDetailChrome();
    if (state.mobileDetail) $("#main-scroll").scrollTop = 0;
  }

  function syncDetailChrome() {
    document.body.classList.toggle("in-detail", state.activeTab === "cockpit" && state.mobileDetail);
  }

  // ---------- 預算與草稿計算 ----------
  function normalizeAgentKey(raw) {
    const k = String(raw || "").trim().toLowerCase();
    if (k === "claude" || k === "claude-code") return "claude-code";
    if (k === "agy" || k === "antigravity") return "antigravity";
    return k;
  }

  function filterCompatibleTools(toolIds, boot) {
    const installed = (boot?.installed_agents || []).map(normalizeAgentKey).filter(Boolean);
    if (!installed.length) return new Set(toolIds);
    const byId = new Map((boot?.workbench?.items || []).map((it) => [it.id, it]));
    const out = new Set();
    for (const tid of toolIds) {
      const item = byId.get(tid);
      if (!item) continue;
      if (item.needs_key) continue;
      const works = (item.compatible_agents || item.works_with || []).map(normalizeAgentKey).filter(Boolean);
      if (!works.length || works.some((w) => installed.includes(w))) {
        out.add(tid);
      }
    }
    return out;
  }

  function initSetupDraft(boot) {
    if (!boot) return;
    const prev = boot.previous_answers || {};
    const items = boot.workbench?.items || [];
    const baseEnabled = items.filter((i) => i.enabled).map((i) => i.id);
    const enabledTools = boot.onboarding_completed
      ? new Set(baseEnabled)
      : filterCompatibleTools(baseEnabled, boot);
    const defaultProfName = boot.is_handwritten_profile
      ? `${boot.active_profile}-panel`
      : (boot.active_profile !== "default" ? boot.active_profile : (boot.suggested_profile || "personal"));
    state.setupDraft = {
      profileName: defaultProfName,
      preset: "fullstack-app",
      doneCheck: boot.done_check || "log",
      language: prev.language || "zh-TW",
      verbosity: prev.verbosity || "concise",
      autonomy: prev.autonomy || "balanced",
      domains: new Set(prev.domains?.length ? prev.domains : ["software-dev"]),
      pains: new Set(prev.pains?.length ? prev.pains : ["anti-fake-done", "no-verification", "guesses", "scope-creep", "manual-steps"]),
      evaluateTools: Boolean(prev.evaluate_tools),
      background: prev.background || "",
      projects: prev.projects || null,
      tools: enabledTools,
      importCandidates: new Set((boot.candidate_projects || []).slice(0, 3).map((c) => c.path)),
    };
  }

  function computeDraftBudget(enabledSet) {
    const items = state.bootstrap?.workbench?.items || [];
    const totals = { "claude-code": 1970, codex: 1970, antigravity: 1970 };
    for (const it of items) {
      if (!enabledSet.has(it.id)) continue;
      const c = it.context_cost || {};
      totals["claude-code"] += Number(c["claude-code"] || 0);
      totals.codex += Number(c.codex || 0);
      totals.antigravity += Number(c.antigravity || 0);
    }
    const out = {};
    for (const [k, tok] of Object.entries(totals)) {
      const pct = Math.round((tok / 200000) * 1000) / 10;
      const level = tok >= 20000 ? "danger" : tok >= 10000 ? "warn" : "ok";
      out[k] = { tokens: tok, percent_of_200k: pct, level };
    }
    return out;
  }

  function renderBudgetHtml(budget, title = "開場常駐 Context 預算估算（以 200k 視窗為基準，建議控制在 5% 內）") {
    if (!budget) return "";
    const cells = ["claude-code", "codex", "antigravity"].map((ag) => {
      const b = budget[ag] || { tokens: 0, percent_of_200k: 0, level: "ok" };
      const barPct = Math.min(100, Math.max(2, b.percent_of_200k * 5));
      const lvlCls = b.level === "danger" ? "is-danger" : b.level === "warn" ? "is-warn" : "";
      const note = b.level === "danger" ? "偏高，建議關閉不常用常駐工具" : b.level === "warn" ? "接近 5% 提醒線" : "精簡健康";
      return `
        <div class="budget-cell ${lvlCls}">
          <div class="budget-top"><b>${esc(AGENT_DISPLAY[ag] || ag)}</b><span class="num">${b.tokens.toLocaleString()} tokens (${b.percent_of_200k}%)</span></div>
          <div class="budget-bar"><i style="width:${barPct}%"></i></div>
          <div class="budget-sub">${note}</div>
        </div>`;
    });
    return `
      <div class="budget-head">
        <h3>${esc(title)}</h3>
        <span class="muted-sm">按需讀取的技能不占開場額度</span>
      </div>
      <div class="budget-grid">${cells.join("")}</div>`;
  }

  // ---------- 漂移橫幅 ----------
  function renderDrifts() {
    const el = $("#drift-banner");
    const drifts = state.bootstrap?.drifts || [];
    if (!drifts.length || !state.session.writable) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    el.hidden = false;
    el.innerHTML = drifts.map((d) => `
      <div class="drift-item">
        <div class="drift-msg"><i></i><span><b>偵測到外部修改</b>：${esc(d.title)}</span></div>
        <div class="drift-actions">
          <button type="button" class="btn btn-sm" data-drift-id="${esc(d.id)}" data-drift-act="adopt">採用外部修改</button>
          <button type="button" class="btn btn-sm" data-drift-id="${esc(d.id)}" data-drift-act="restore">還原面板設定</button>
          <button type="button" class="btn btn-sm btn-quiet" data-drift-id="${esc(d.id)}" data-drift-act="snooze">暫緩 7 天</button>
        </div>
      </div>`).join("");
  }

  // ---------- 首頁渲染（開箱精靈 vs 日常總覽） ----------
  function renderHome() {
    const root = $("#home-root");
    const boot = state.bootstrap;
    if (!boot) return;
    renderDrifts();

    const showWizard = !boot.onboarding_completed || state.forceSetupWizard;
    if (showWizard) {
      if (!state.setupDraft) initSetupDraft(boot);
      const d = state.setupDraft;
      const draftBudget = computeDraftBudget(d.tools);
      const agentsHtml = (boot.agents || []).map((a) => `
        <span class="agent-pill ${a.found ? "is-found" : ""}">
          <i></i>${esc(a.name)} · ${a.found ? "已偵測就緒" : "尚未安裝（可略過）"}
        </span>`).join("");

      const presetsHtml = (boot.workbench?.presets || []).map((p) => `
        <button type="button" class="preset-card ${d.preset === p.id ? "is-selected" : ""}" data-pick-preset="${esc(p.id)}">
          <span class="preset-card-title"><span>${esc(p.name)}</span>${d.preset === p.id ? `<span class="tag tag-accent">已選</span>` : ""}</span>
          <span class="preset-card-sub">${esc(p.summary)}</span>
        </button>`).join("");

      const habitsHtml = (boot.habits_catalog || []).map((h) => {
        const checked = d.pains.has(h.id);
        return `
          <label class="habit-item ${checked ? "is-checked" : ""}">
            <input type="checkbox" data-wizard-habit="${esc(h.id)}" ${checked ? "checked" : ""}>
            <span>${esc(h.label)}</span>
          </label>`;
      }).join("");

      const quickTools = (boot.workbench?.items || []).filter((it) => it.layer === "L1" || it.layer === "L2" || it.status === "default");
      const quickToolsHtml = quickTools.map((it) => {
        const on = d.tools.has(it.id);
        const lockedKey = it.needs_key ? `（需環境變數 ${it.needs_key}）` : "";
        const modeTag = it.install_badge || (it.install_mode === "manual" ? "記錄偏好" : "一鍵啟停");
        return `
          <div class="quick-tool-row ${on ? "is-on" : ""}">
            <div class="qt-main">
              <div class="qt-title">
                <span>${esc(it.name)}</span>
                <span class="tag">${esc(modeTag)}</span>
                ${it.recommended_reason ? `<span class="tag tag-accent">推薦</span>` : ""}
              </div>
              <div class="qt-desc">${esc(it.summary)}${esc(lockedKey)}</div>
            </div>
            <button type="button" role="switch" aria-checked="${on}" aria-label="切換 ${esc(it.name)}" class="switch-btn" data-wizard-tool="${esc(it.id)}"></button>
          </div>`;
      }).join("");

      const cands = boot.candidate_projects || [];
      const candBlock = cands.length
        ? `<div class="panel-card">
            <div class="panel-head">
              <div>
                <h2>順手納管這台電腦上的專案（選填）</h2>
                <p>勾選後會自動建立本機狀態板（NOW.md），完全不需要先建 GitHub 私人儲存庫</p>
              </div>
            </div>
            <div class="cand-list">
              ${cands.slice(0, 6).map((c) => `
                <label class="cand-row">
                  <span><b>${esc(c.name)}</b> <span class="cand-path">${esc(c.path)}</span></span>
                  <input type="checkbox" data-wizard-cand="${esc(c.path)}" data-cand-name="${esc(c.name)}" ${d.importCandidates.has(c.path) ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent);">
                </label>`).join("")}
            </div>
          </div>`
        : `<div class="panel-card">
            <div class="panel-head">
              <div>
                <h2>還沒建立任何專案也沒問題</h2>
                <p>先按下方套用工作台，接著就能在首頁一鍵建立你的第一個專案資料夾與破冰提示詞</p>
              </div>
            </div>
          </div>`;

      root.innerHTML = `
        <div class="page-head">
          <div>
            <h1>歡迎使用 OmniKit 本機工作台</h1>
            <p class="page-sub">預設已幫你勾好免金鑰精選工具與防假完工護欄，確認後按下方按鈕一次裝到好</p>
          </div>
          ${boot.onboarding_completed ? `<button type="button" class="btn btn-sm" id="btn-cancel-wizard">返回日常總覽</button>` : ""}
        </div>

        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>1. 本機偵測到的 AI Agent</h2>
              <p>已安裝的 Agent 會自動同步同一份安全底線、個人習慣、核心技能與精選工具</p>
            </div>
          </div>
          <div class="agent-pills">${agentsHtml}</div>
        </div>

        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>2. 你主要想用 AI 做什麼？（點選套用推薦組合）</h2>
              <p>隨時可在「工作台」分頁單獨開關任何工具</p>
            </div>
          </div>
          <div class="preset-grid">${presetsHtml}</div>
        </div>

        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>3. 你希望 AI 遵守哪些習慣？（自由複選，不限數量）</h2>
              <p>已預設勾選「防假完工」與核心工程紀律，徹底終結「只跑假測試就說改好了，一開就壞」</p>
            </div>
          </div>
          <div class="habit-grid">${habitsHtml}</div>
          <div class="inline-options">
            <label class="opt-group">
              <span>回覆語言與詳略</span>
              <select id="wiz-lang-verb" class="select-field">
                <option value="zh-TW:concise" ${d.language === "zh-TW" && d.verbosity === "concise" ? "selected" : ""}>繁體中文 · 精簡扼要（推薦）</option>
                <option value="zh-TW:detailed" ${d.language === "zh-TW" && d.verbosity === "detailed" ? "selected" : ""}>繁體中文 · 完整說明理由</option>
                <option value="en:concise" ${d.language === "en" && d.verbosity === "concise" ? "selected" : ""}>English · Concise</option>
                <option value="en:detailed" ${d.language === "en" && d.verbosity === "detailed" ? "selected" : ""}>English · Detailed</option>
              </select>
            </label>
            <label class="opt-group">
              <span>Agent 自動執行程度</span>
              <select id="wiz-autonomy" class="select-field">
                <option value="balanced" ${d.autonomy === "balanced" ? "selected" : ""}>專案內直接改，安裝套件先問（推薦）</option>
                <option value="hands-off" ${d.autonomy === "hands-off" ? "selected" : ""}>大多放手自動做（僅危險紅線先問）</option>
                <option value="cautious" ${d.autonomy === "cautious" ? "selected" : ""}>每步先列計畫等我同意</option>
              </select>
            </label>
            <label class="opt-group">
              <span>完工檢查護欄（done_check）</span>
              <select id="wiz-done-check" class="select-field">
                <option value="log" ${d.doneCheck === "log" ? "selected" : ""}>僅記錄，不阻斷對話（推薦預設）</option>
                <option value="block" ${d.doneCheck === "block" ? "selected" : ""}>強制攔截未驗證收尾</option>
                <option value="off" ${d.doneCheck === "off" ? "selected" : ""}>關閉檢查</option>
              </select>
            </label>
            <label class="opt-group">
              <span>${boot.is_handwritten_profile ? "另存新設定檔代號（保留原手寫 AGENTS.md）" : "個人設定檔代號（小寫英數）"}</span>
              <input id="wiz-prof-name" type="text" class="composer-input" value="${esc(d.profileName)}" style="min-height:38px;">
            </label>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>4. 精選免金鑰工作台套件</h2>
              <p>勾選後自動同步至支援的 Agent（需外部 API Key 的工具預設不勾選，不卡安裝）</p>
            </div>
          </div>
          <div class="budget-panel" id="wiz-budget-box" style="margin-bottom:16px;">
            ${renderBudgetHtml(draftBudget)}
          </div>
          <div class="quick-tool-list">${quickToolsHtml}</div>
        </div>

        ${candBlock}

        <div class="panel-card" style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;" data-write-only>
          <div>
            <b style="font-size:15px;">準備就緒</b>
            <div class="muted-sm">所有設定存在本機 ~/.omnikit，不會污染專案 git status，隨時可一鍵修改或還原</div>
          </div>
          <button type="button" class="btn btn-lg btn-accent" id="btn-apply-wizard">一鍵套用工作台與個人設定</button>
        </div>
      `;
      return;
    }

    // 日常控制總覽
    const ov = state.overview;
    const enabledCount = (boot.workbench?.items || []).filter((i) => i.enabled).length;
    const foundAgents = (boot.agents || []).filter((a) => a.found);
    const blockedCount = ov?.summary?.blocked_on_me ?? 0;
    const projTotal = ov?.summary?.total ?? 0;
    const dcLabel = boot.done_check === "block" ? "強制攔截中" : boot.done_check === "log" ? "僅記錄" : "已關閉";
    const trip30 = boot.tripwire?.recent_30d ?? 0;
    const statusModeTxt = boot.status_repo?.mode === "remote" ? "已綁定遠端同步庫" : "本機免帳號版本庫";
    const cands = boot.candidate_projects || [];

    const shortcutsHtml = (boot.cli_shortcuts || []).map((s) => `
      <div class="prompt-copy-row">
        <div class="prompt-copy-main">
          <div class="prompt-copy-cmd">${esc(s.cmd)} <span class="tag">${esc(s.agent)}</span></div>
          <div class="prompt-copy-desc">${esc(s.desc)}</div>
        </div>
        <button type="button" class="btn btn-sm" data-copy-raw="${esc(s.cmd)}">${ICON.copy}複製</button>
      </div>`).join("");

    const candSection = cands.length
      ? `<div class="cand-list">
          ${cands.slice(0, 5).map((c) => `
            <div class="cand-row">
              <div><b>${esc(c.name)}</b><div class="cand-path">${esc(c.path)}</div></div>
              <button type="button" class="btn btn-sm" data-import-one="${esc(c.path)}" data-import-name="${esc(c.name)}" data-write-only>匯入狀態板</button>
            </div>`).join("")}
        </div>`
      : `<p class="empty-muted">目前常見開發目錄沒有尚未納管的專案。你可以隨時建立一個全新的練習或正式專案。</p>`;

    root.innerHTML = `
      <div class="page-head">
        <div>
          <h1>本機控制面板總覽</h1>
          <p class="page-sub">目前設定檔：<b>${esc(boot.active_profile)}</b> · 狀態板：${esc(statusModeTxt)} · 已接上 ${foundAgents.map((a) => esc(a.name)).join("、") || "尚無 Agent"}</p>
        </div>
        <div class="head-btn-row" data-write-only>
          <button type="button" class="btn btn-sm" id="btn-reopen-wizard">快速設定精靈</button>
          <button type="button" class="btn btn-sm btn-primary" id="btn-home-new-proj">${projTotal > 0 ? "建立新專案" : "建立第一個新專案"}</button>
        </div>
      </div>

      <div class="stat-strip">
        <button type="button" class="stat-box" data-goto-tab="cockpit">
          <span class="stat-label">專案狀態板（NOW.md）</span>
          <span class="stat-value">${projTotal} 個專案</span>
          <span class="stat-note">${blockedCount > 0 ? `有 ${blockedCount} 個卡在你身上等你拍板` : "目前無阻塞項目，點此檢視進度"}</span>
        </button>
        <button type="button" class="stat-box" data-goto-tab="tools">
          <span class="stat-label">精選工作台套件</span>
          <span class="stat-value">已啟用 ${enabledCount} 項</span>
          <span class="stat-note">Claude 開場約 ${(boot.workbench?.budget?.["claude-code"]?.percent_of_200k ?? 1.1)}% · 點此管理</span>
        </button>
        <button type="button" class="stat-box" data-goto-tab="settings">
          <span class="stat-label">防假完工護欄（done_check）</span>
          <span class="stat-value">${esc(dcLabel)}</span>
          <span class="stat-note">近 30 天擋下 ${boot.tripwire?.blocked_30d ?? 0} 次 · 記錄 ${boot.tripwire?.logged_30d ?? trip30} 次</span>
        </button>
        <button type="button" class="stat-box" data-goto-tab="accounts">
          <span class="stat-label">本機 Agent 與額度</span>
          <span class="stat-value">${foundAgents.length} 家已就緒</span>
          <span class="stat-note">點此查看健康檢查（Doctor）與剩餘額度</span>
        </button>
      </div>

      <div class="home-two-col">
        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>對話中隨時可用的快捷指令</h2>
              <p>複製貼進 Claude Code、Codex 或 Antigravity 即可觸發</p>
            </div>
          </div>
          <div class="prompt-copy-list">${shortcutsHtml}</div>
        </div>

        <div class="panel-card">
          <div class="panel-head">
            <div>
              <h2>快速開始新專案或匯入資料夾</h2>
              <p>免設定 GitHub 私人 repo，所有進度與歷史自動保存在本機</p>
            </div>
            <button type="button" class="btn btn-sm btn-primary" id="btn-card-starter" data-write-only>建立新專案</button>
          </div>
          ${candSection}
        </div>
      </div>
    `;
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
        ? `<b>更新狀態板中</b> ${esc(runJob.project_name)}${rest ? `，後面還有 ${rest} 個` : ""}`
        : `<b>更新狀態板中</b> 還有 ${reconcile.active_count} 個專案`;
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
      if (state.wasBusy) showToast("狀態板已更新完成");
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
      // 下一輪重試
    }
  }

  async function triggerReconcile(projectId) {
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/reconcile`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      showToast(`已開始更新 ${projectId} 狀態板`);
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
      const local = (state.overview?.projects || []).filter((p) => p.local_available && !p.remote_only).length;
      if (local === 0) {
        showToast("沒有需要對帳的本機專案");
        return;
      }
      confirmAll = window.confirm(`目前沒有過期的專案。要把全部 ${local} 個本機專案重新對帳更新嗎？`);
      if (!confirmAll) return;
    }
    try {
      const res = await api("/api/reconcile-all", {
        method: "POST",
        body: JSON.stringify(stale > 0 ? { only_stale: true } : { only_stale: false, confirm_all: confirmAll }),
      });
      if (state.overview) state.overview.reconcile = res.reconcile;
      const n = res.queued?.length || 0;
      showToast(n === 0 ? "沒有需要對帳的本機專案" : `已排入 ${n} 個專案依序更新`);
      syncPolling(res.reconcile);
      renderList();
      renderInspector();
    } catch (err) {
      showToast(err.message);
    }
  }

  // ---------- 載入 Bootstrap 與 Overview ----------
  async function loadBootstrap(force = false) {
    try {
      state.bootstrap = await api(`/api/bootstrap${force ? "?refresh=1" : ""}`);
      renderHome();
      if (state.activeTab === "tools") renderWorkbenchTab();
      if (state.activeTab === "settings") renderSettingsPage();
    } catch (err) {
      $("#home-root").innerHTML = `<div class="empty-inline">讀取環境資訊失敗：${esc(err.message)}</div>`;
    }
  }

  async function loadOverview(sync = false, silent = false) {
    const syncBtn = $("#btn-sync");
    if (!silent && syncBtn) syncBtn.disabled = true;
    try {
      const data = await api(`/api/overview${sync ? "?sync=1" : ""}`);
      state.overview = data;
      if (!state.selectedId || !data.projects.some((p) => p.id === state.selectedId)) {
        state.selectedId = data.projects[0]?.id || null;
      }
      renderOverview();
      if (state.bootstrap && state.bootstrap.onboarding_completed && !state.forceSetupWizard) renderHome();
      if (sync) showToast(data.sync?.synced ? "已同步狀態板並重新整理" : "已重新掃描本機專案");
    } catch (err) {
      $("#project-list").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
      if (!silent) showToast(err.message);
    } finally {
      if (syncBtn) syncBtn.disabled = false;
    }
  }

  // ---------- 專案清單與詳情 ----------
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
    return p.stale ? "尚未建立 NOW.md，點一下對帳即可自動產生" : "沒有待辦項目";
  }

  function projectRightTag(p, job) {
    if (job && (job.status === "running" || job.status === "queued")) {
      return { text: job.status === "running" ? "對帳中" : "排隊中", cls: "t-accent" };
    }
    if (p.open_critiques_count > 0) return { text: `待改 ${p.open_critiques_count}`, cls: "t-warn" };
    const behind = p.git?.commits_since_now || 0;
    if (behind > 0) return { text: `落後 ${behind} 個 commit`, cls: "t-warn" };
    if (p.stale) return { text: p.now.exists ? "需更新" : "缺 NOW.md", cls: "t-warn" };
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
        } else if (p.local_available) {
          foot.push("<span>本機資料夾</span>");
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
      root.innerHTML = `<div class="empty-inline">目前沒有專案，點擊左上角「建立新專案」即可開始</div>`;
      return;
    }

    const job = ov.reconcile?.jobs?.[p.id];
    const isBusy = job && (job.status === "running" || job.status === "queued");
    const prog = p.now.progress || {};
    const hasSteps = prog.total != null && prog.total > 0;
    const slope = SLOPE_LABEL[prog.slope];
    const triOpen = state.triFormOpen.has(p.id);

    let alertBanner = "";
    const jobThreadUrl = safeUrl(job?.thread_url);
    if (isBusy) {
      alertBanner = `
        <div class="alert-strip is-running">
          <div class="alert-strip-msg"><span class="live-dot"></span><span>${esc(job.message)}</span></div>
          ${jobThreadUrl ? `<a class="btn btn-sm" href="${esc(jobThreadUrl)}" target="_blank" rel="noopener">看過程 ${ICON.ext}</a>` : ""}
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
    } else if (p.local_available) {
      meta.push("<span>本機資料夾（尚未初始化 Git）</span>");
    } else {
      meta.push("<span>遠端專案，這台沒有目錄</span>");
    }
    if (p.t3?.unsettled_count > 0) meta.push(`<span>${p.t3.unsettled_count} 條對話未結案</span>`);
    meta.push(`<span>${esc(p.last_activity_age)}活躍</span>`);

    const reconcileBtn = (extra = "") => p.local_available
      ? `<button type="button" class="btn btn-sm ${p.stale && !isBusy ? "btn-primary" : ""} ${extra}" data-reconcile="${esc(p.id)}" ${isBusy ? "disabled" : ""}>${ICON.sync}${isBusy ? "更新中" : "更新狀態板"}</button>`
      : "";
    const safePrimaryT3 = safeUrl(p.primary_t3_url);
    const t3Link = safePrimaryT3
      ? `<a class="btn btn-sm" href="${esc(safePrimaryT3)}" target="_blank" rel="noopener">T3 ${ICON.ext}</a>`
      : "";

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
      : `<p class="empty-muted">${esc(prog.summary || "尚未拆解步驟，點擊「更新狀態板」自動整理")}</p>`;

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
      : `<p class="empty-muted" style="margin-bottom:12px;">沒有未收斂的不滿意項目</p>`;

    const threads = p.t3?.threads || [];
    const threadsSection = p.t3?.available
      ? `<section class="insp-section">
          <div class="sec-head"><h3 class="sec-title">T3 未結案對話</h3><span class="sec-aside">${p.t3?.unsettled_count || 0} 條</span></div>
          ${threads.length ? `<div class="thread-table">${threads.map((t) => {
            const safeTLink = safeUrl(t.link);
            return `
            <div class="thread-item">
              <div class="thread-main">
                <div class="thread-name">${esc(t.title)}</div>
                <div class="thread-sub">${esc(t.status)} · <span class="${t.overloaded ? "is-over" : ""}">${t.item_count} 項${t.overloaded ? "，超載" : ""}</span>${t.model ? ` · ${esc(t.model)}` : ""}</div>
              </div>
              ${safeTLink ? `<a class="btn btn-sm" href="${esc(safeTLink)}" target="_blank" rel="noopener">開啟 ${ICON.ext}</a>` : ""}
            </div>`;
          }).join("")}</div>` : `<p class="empty-muted">沒有未結案的對話</p>`}
        </section>`
      : "";

    const okPrefix = state.bootstrap?.ok_prefix || "/ok";
    const verifyPrompt = `${okPrefix} 驗收 請針對專案「${p.name}」（${p.path || p.id}）執行防假完工真機驗收：檢查斷線引用與假綠燈，並實際啟動服務與瀏覽器確認桌機與手機寬度 0 錯誤。`;

    root.innerHTML = `
      <div class="detail-bar">
        <button type="button" class="btn btn-quiet" id="btn-mobile-back">${ICON.back}專案清單</button>
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
          <span class="desk-only actions-contents">${reconcileBtn()}${safePrimaryT3 ? `<a class="btn btn-sm" href="${esc(safePrimaryT3)}" target="_blank" rel="noopener">打開 T3 ${ICON.ext}</a>` : ""}</span>
          <button type="button" class="btn btn-sm" data-view-now="${esc(p.id)}">${ICON.file}NOW.md 與歷史</button>
          <button type="button" class="btn btn-sm" data-copy-next="${esc(p.id)}">${ICON.copy}複製下一步</button>
          <button type="button" class="btn btn-sm" data-copy-raw="${esc(verifyPrompt)}">${ICON.shield}複製驗收指令</button>
          <button type="button" class="btn btn-sm btn-quiet" data-park="${esc(p.id)}" data-parked="${p.manual_parked ? "1" : "0"}">${p.manual_parked ? `${ICON.play}移回` : `${ICON.pause}停泊`}</button>
        </div>
      </header>

      ${alertBanner}

      <section class="insp-section">
        <div class="sec-head"><h3 class="sec-title">下一步</h3>${owner}</div>
        <p class="next-lead">${nxt ? esc(stripOwnerTag(nxt.text)) : "尚未填寫下一步，點一下「更新狀態板」即可從本機 Git 狀態補上"}</p>
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
            : `<p class="empty-muted">尚未整理結論</p>`}
          ${p.git?.last_subject ? `<p class="commit-line">最新 commit <code>${esc(p.git.last_hash)}</code> ${esc(p.git.last_subject)}</p>` : ""}
        </div>
      </section>

      <section class="insp-section">
        <div class="sec-head"><h3 class="sec-title">不滿意待改（寫入本機 NOW.md）</h3><span class="sec-aside">${p.open_critiques_count} 項未收斂</span></div>
        ${critiquesHtml}
        <form class="critique-composer" data-add-critique="${esc(p.id)}" data-path="${esc(p.path || "")}" data-write-only>
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
              <input class="composer-input" name="text" placeholder="記一條不滿意待改，Enter 寫入 NOW.md" required>
              <button type="submit" class="btn btn-sm">記下</button>
              <button type="button" class="btn btn-sm btn-quiet" data-toggle-tri="${esc(p.id)}">分三欄</button>
            </div>
          `}
        </form>
      </section>

      ${threadsSection}
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

  // ---------- 分頁 3：工作台（精選開關 ＋ 完整名冊） ----------
  function renderWorkbenchTab() {
    const wb = state.bootstrap?.workbench;
    const budgetBox = $("#workbench-budget-bar");
    const curatedRoot = $("#workbench-curated-root");
    const catalogRoot = $("#workbench-catalog-root");

    if (budgetBox && wb) {
      budgetBox.innerHTML = renderBudgetHtml(wb.budget);
    }

    const isCurated = state.workbenchView === "curated";
    curatedRoot.hidden = !isCurated;
    catalogRoot.hidden = isCurated;

    if (!isCurated) return;
    if (!wb || !wb.items) {
      curatedRoot.innerHTML = `<div class="empty-inline">正在載入精選工作台…</div>`;
      return;
    }

    const byLayer = { L1: [], L2: [], L3: [], L4: [] };
    for (const it of wb.items) {
      (byLayer[it.layer] || byLayer.L3).push(it);
    }

    const sections = Object.entries(LAYER_LABELS).map(([layer, label]) => {
      const items = byLayer[layer] || [];
      if (!items.length) return "";
      const cards = items.map((it) => {
        const works = (it.works_with || []).map((w) => AGENT_DISPLAY[w] || w).join(" · ");
        const cCost = it.context_cost?.["claude-code"] || 0;
        const costTag = cCost > 0 ? `開場 ~${cCost} tok` : "按需載入 0 tok";
        const safeItUrl = safeUrl(it.url);
        const nameEl = safeItUrl
          ? `<a class="tool-name" href="${esc(safeItUrl)}" target="_blank" rel="noopener">${esc(it.name)}${ICON.ext}</a>`
          : `<span class="tool-name">${esc(it.name)}</span>`;
        const installBadge = it.install_badge || (it.install_mode === "manual" ? "記錄偏好（需手動裝）" : "一鍵啟停");
        const manualBlock = it.install_mode === "manual" && it.manual_hint
          ? `<div class="tool-desc" style="margin-top:6px;"><b>安裝方式</b>　<code class="mono">${esc(it.manual_hint)}</code></div>`
          : "";
        return `
          <article class="tool-card ${it.enabled ? "is-enabled" : ""}">
            <div class="tool-head">
              <div>
                ${nameEl}
                <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;">
                  <span class="tag ${it.enabled ? "tag-accent" : ""}">${esc(it.trust?.label || "實測精選")}</span>
                  <span class="tag tag-outline">${esc(installBadge)}</span>
                  ${it.recommended_reason ? `<span class="tag tag-outline" title="${esc(it.recommended_reason)}">專案推薦</span>` : ""}
                  ${it.needs_key ? `<span class="tag tag-warn">需 ${esc(it.needs_key)}</span>` : ""}
                </div>
              </div>
              <button type="button" role="switch" aria-checked="${it.enabled}" aria-label="啟用或停用 ${esc(it.name)}" class="switch-btn" data-toggle-tool="${esc(it.id)}" data-cur-enabled="${it.enabled ? "1" : "0"}" ${!state.session.writable ? "disabled" : ""}></button>
            </div>
            ${it.summary ? `<p class="tool-desc">${esc(it.summary)}</p>` : ""}
            ${it.trigger_when ? `<p class="tool-desc"><b>使用時機</b>　${esc(it.trigger_when)}</p>` : ""}
            ${manualBlock}
            <div class="tool-tags">
              <span>支援：${esc(works)}</span>
              <span>·</span>
              <span class="num">${esc(costTag)}</span>
              ${it.slot_names?.length ? `<span>· ${esc(it.slot_names[0])}</span>` : ""}
            </div>
          </article>`;
      }).join("");
      return `
        <section class="slot-group">
          <div class="slot-head"><h2 class="slot-name">${esc(label)}</h2><span class="muted-sm">${items.length} 個套件</span></div>
          <div class="tool-grid">${cards}</div>
        </section>`;
    }).filter(Boolean);

    curatedRoot.innerHTML = sections.join("");
  }

  async function toggleWorkbenchTool(toolId, currentlyEnabled, btnEl) {
    const nextTier = currentlyEnabled ? "disabled" : "resident";
    if (btnEl) btnEl.disabled = true;
    try {
      const res = await api("/api/tools/toggle", {
        method: "POST",
        body: JSON.stringify({ tool_id: toolId, tier: nextTier }),
      });
      if (!res.ok) {
        showToast(res.message || (res.warnings || [])[0] || "切換失敗，請檢查環境設定");
      } else {
        if (state.bootstrap && res.workbench) {
          state.bootstrap.workbench = res.workbench;
          state.bootstrap.rev = res.workbench.rev;
        }
        const warnTxt = (res.warnings || [])[0];
        if (warnTxt) {
          showToast(`已更新設定（${warnTxt}）`);
        } else if (res.install_mode === "manual") {
          showToast(currentlyEnabled ? `已停用 ${toolId} 偏好記錄` : `已記錄 ${toolId} 偏好（請依卡片指令手動安裝）`);
        } else {
          showToast(currentlyEnabled ? `已停用 ${toolId}` : `已啟用 ${toolId}`);
        }
      }
      renderWorkbenchTab();
      renderHome();
    } catch (err) {
      showToast(err.message);
    } finally {
      if (btnEl) btnEl.disabled = false;
    }
  }

  async function loadTools(refresh = false) {
    $("#tools-grid").innerHTML = `<div class="empty-inline">讀取完整評估名冊中…</div>`;
    try {
      state.tools = await api(`/api/tools${refresh ? "?refresh=1" : ""}`);
      renderToolsCatalog();
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
    const meta = [t.kind, (t.works_with || []).map((w) => AGENT_DISPLAY[w] || w).join("、"), otherSlots.length ? `也用在 ${otherSlots.join("、")}` : ""].filter(Boolean);
    const safeTUrl = safeUrl(t.url);
    const name = safeTUrl
      ? `<a class="tool-name" href="${esc(safeTUrl)}" target="_blank" rel="noopener">${esc(t.name)}${ICON.ext}</a>`
      : `<span class="tool-name">${esc(t.name)}</span>`;
    return `
      <article class="tool-card">
        <div class="tool-head">${name}${statusTag(t)}</div>
        ${t.summary ? `<p class="tool-desc">${esc(t.summary)}</p>` : ""}
        ${t.trigger_when ? `<p class="tool-desc"><b>什麼時候用</b>　${esc(t.trigger_when)}</p>` : ""}
        ${meta.length ? `<div class="tool-tags">${meta.map(esc).join(" · ")}</div>` : ""}
      </article>`;
  }

  function renderToolsCatalog() {
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
      for (const slot of t.slot_names?.length ? t.slot_names : ["未分類槽位"]) {
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
      $("#tools-grid").innerHTML = `<div class="empty-inline">沒有符合條件的工具</div>`;
      return;
    }
    $("#tools-grid").innerHTML = slots.map(([slot, g]) => {
      const others = g.others.sort((a, b) => rank(a) - rank(b));
      const othersText = others.length
        ? `<p class="slot-others">同槽位候選：${others.slice(0, 6).map((t) => `${esc(t.name)}（${STATUS_LABELS[t.status] || esc(t.status)}）`).join("、")}${others.length > 6 ? ` 等 ${others.length} 個` : ""}</p>`
        : "";
      return `
        <section class="slot-group">
          <div class="slot-head"><h2 class="slot-name">${esc(slot)}</h2><span class="muted-sm">${g.shown.length + g.others.length} 個工具</span></div>
          ${othersText}
          <div class="tool-grid">${g.shown.sort((a, b) => rank(a) - rank(b)).map((t) => toolCard(t, slot)).join("")}</div>
        </section>`;
    }).join("");
  }

  // ---------- 分頁 4：Agent 健康檢查 Doctor 與額度 ----------
  async function loadDoctor(showMsg = false) {
    const panel = $("#doctor-panel");
    const btn = $("#btn-run-doctor");
    if (btn) btn.disabled = true;
    panel.innerHTML = `<div class="empty-inline" style="padding:12px;">正在檢查三家 Agent 規則、技能連結、MCP 與護欄健康度…</div>`;
    try {
      state.doctor = await api("/api/doctor");
      renderDoctor();
      if (showMsg) showToast("已完成健康檢查");
    } catch (err) {
      panel.innerHTML = `<div class="empty-inline">健康檢查失敗：${esc(err.message)}</div>`;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function fixDoctor() {
    const hasDrifts = (state.bootstrap?.drifts || []).length > 0;
    if (hasDrifts) {
      if (!window.confirm("目前有偵測到外部手改的規則區塊。按「確定」將修復遺失的技能連結、外掛與 MCP，並自動保護保留你的手改區塊不被覆寫。要繼續嗎？")) {
        return;
      }
    }
    const btn = $("#btn-fix-doctor");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "修復同步中…";
    }
    try {
      const res = await api("/api/doctor/fix", { method: "POST", body: JSON.stringify({ force_overwrite: false }) });
      state.doctor = res.doctor;
      renderDoctor();
      await loadBootstrap(true);
      showToast(res.ok ? "已完成同步修復（手改區塊已保護保留）" : "已執行同步，請查看剩餘提醒項目");
    } catch (err) {
      showToast(err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "一鍵修復同步";
      }
    }
  }

  function renderDoctor() {
    const panel = $("#doctor-panel");
    const doc = state.doctor;
    if (!doc) return;
    const c = doc.counts || { ok: 0, warn: 0, fail: 0, unknown: 0 };
    const problems = (doc.rows || []).filter((r) => r.status !== "ok");
    const markSym = { ok: "✓", warn: "！", fail: "✗", unknown: "？" };

    const problemRows = problems.map((r) => `
      <div class="doc-row">
        <span class="doc-mark st-${esc(r.status)}">${markSym[r.status] || "？"}</span>
        <span class="doc-area">${esc(r.agent ? `${r.area} · ${r.agent}` : r.area)}</span>
        <span class="doc-detail"><b>${esc(r.item)}</b>${r.detail ? ` — ${esc(r.detail)}` : ""}</span>
      </div>`).join("");

    const okRows = (doc.rows || []).filter((r) => r.status === "ok").map((r) => `
      <div class="doc-row">
        <span class="doc-mark st-ok">✓</span>
        <span class="doc-area">${esc(r.agent ? `${r.area} · ${r.agent}` : r.area)}</span>
        <span class="doc-detail">${esc(r.item)}${r.detail ? `（${esc(r.detail)}）` : ""}</span>
      </div>`).join("");

    panel.innerHTML = `
      <div class="panel-head" style="margin-bottom:8px;">
        <div>
          <h2>健康檢查結果（Doctor）</h2>
          <p>通過 ${c.ok} 項 · 提醒 ${c.warn} 項 · 失敗 ${c.fail} 項${c.unknown ? ` · 未知 ${c.unknown} 項` : ""}</p>
        </div>
        <span class="tag ${c.fail > 0 ? "tag-danger" : c.warn > 0 ? "tag-warn" : "tag-accent"}">
          ${c.fail > 0 ? "有項目需修復" : c.warn > 0 ? "運作中（含提醒）" : "全部健康"}
        </span>
      </div>
      ${problems.length ? `<div class="doc-list">${problemRows}</div>` : ""}
      <details class="steps-done" style="margin-top:10px;margin-bottom:0;">
        <summary>${ICON.chev}檢視全部 ${c.ok} 項通過明細</summary>
        <div class="doc-list">${okRows}</div>
      </details>
    `;
  }

  async function loadAccounts(refresh = false) {
    const btn = $("#btn-refresh-agy");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "讀取中…";
    }
    try {
      state.accounts = await api(`/api/accounts${refresh ? "?refresh=1" : ""}`);
      renderAccounts();
      if (refresh) showToast("已重新讀取帳號額度");
    } catch (err) {
      $("#accounts-root").innerHTML = `<div class="empty-inline">讀取失敗：${esc(err.message)}</div>`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "刷新額度";
      }
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
    if (!data) return;

    const codexRows = (data.codex || []).map((x) => {
      const tags = [
        x.cli_installed ? "CLI 已安裝" : "未偵測到 codex CLI",
        x.logged_in ? "已登入" : "尚未登入",
        x.rules_connected ? "規則已接上" : "規則未接上",
      ];
      return `
        <div class="acct-row">
          <div>
            <div class="acct-name"><span>${esc(x.label)}</span>${x.hooks_trusted ? `<span class="tag tag-accent">Hooks 已信任</span>` : `<span class="tag tag-warn">待執行 /hooks 信任</span>`}</div>
            <div class="acct-sub">${tags.map(esc).join(" · ")}</div>
          </div>
          <div class="acct-sub" style="font-size:13px;color:var(--text-2);">${esc(x.quota_note)}</div>
        </div>`;
    }).join("");

    if (!data.available) {
      $("#accounts-root").innerHTML = `
        <section class="acct-group">
          <div class="acct-group-head"><h2>Codex</h2><span class="muted-sm">${(data.codex || []).length} 個設定目錄</span></div>
          <div class="acct-table">${codexRows || `<div class="empty-inline">這台尚未安裝 Codex</div>`}</div>
        </section>
        <div class="empty-inline">${esc(data.error || "這台目前使用單一帳號（尚未設定多帳號輪替紀錄）")}</div>`;
      return;
    }

    const alerts = data.alerts || [];
    $("#accounts-alerts").innerHTML = alerts.map((a) => `
      <div class="alert-strip" style="margin:0 0 16px;"><div class="alert-strip-msg">${ICON.alert}<span>${esc(typeof a === "string" ? a : (a.message || a.text || JSON.stringify(a)))}</span></div></div>`).join("");

    const sel = data.claude_selection || {};
    const chosen = sel.chosen || "";
    const chosenRow = (data.claude || []).find((c) => c.instance === chosen);
    const reco = chosenRow
      ? `<div class="acct-reco">
          <div>
            <p class="acct-reco-title">下一個工作包建議使用 Claude · ${esc(chosenRow.account || chosenRow.instance)}</p>
            ${sel.reason ? `<p class="acct-reco-why">${esc(String(sel.reason).replace(/^策略\s*[\w-]+：/, ""))}</p>` : ""}
          </div>
        </div>`
      : "";

    const srcName = { statusline: "Claude Code 狀態列", t3_cache: "T3", manual: "手動登記" };
    const claudeRows = (data.claude || []).map((c) => {
      const sub = [c.source ? `來自 ${esc(srcName[c.source] || c.source)}` : "尚無用量快照", fmtAge(c.age_hours)].filter(Boolean);
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
        <div class="acct-group-head"><h2>Codex</h2><span class="muted-sm">${(data.codex || []).length} 個設定目錄</span></div>
        <div class="acct-table">${codexRows || `<div class="empty-inline">這台尚未安裝 Codex</div>`}</div>
      </section>
      <section class="acct-group">
        <div class="acct-group-head"><h2>Claude Code</h2><span class="muted-sm">${(data.claude || []).length} 個帳號</span></div>
        <div class="acct-table">${claudeRows || `<div class="empty-inline">這台尚未設定 Claude 帳號</div>`}</div>
      </section>
      <section class="acct-group">
        <div class="acct-group-head"><h2>Antigravity</h2><span class="muted-sm">${(data.antigravity || []).length} 個帳號</span></div>
        <div class="acct-table">${agyRows || `<div class="empty-inline">這台尚未設定 Antigravity 帳號</div>`}</div>
      </section>
    `;
  }

  // ---------- 分頁 5：設定頁 ----------
  function renderSettingsPage() {
    const root = $("#settings-page-root");
    const boot = state.bootstrap;
    const ovSet = state.overview?.settings || {};
    if (!boot) return;

    const prev = boot.previous_answers || {};
    const curPains = new Set(prev.pains || ["anti-fake-done", "no-verification"]);
    const habitsHtml = (boot.habits_catalog || []).map((h) => `
      <label class="habit-item ${curPains.has(h.id) ? "is-checked" : ""}">
        <input type="checkbox" name="pain" value="${esc(h.id)}" ${curPains.has(h.id) ? "checked" : ""}>
        <span>${esc(h.label)}</span>
      </label>`).join("");

    const trip = boot.tripwire || { recent_30d: 0, total: 0, recent_events: [] };
    const eventsHtml = (trip.recent_events || []).length
      ? `<div class="doc-list" style="margin-top:12px;">${trip.recent_events.map((ev) => `
          <div class="doc-row">
            <span class="doc-mark st-warn">攔</span>
            <span class="doc-area mono">${esc(ev.hook)}:${esc(ev.rule)}</span>
            <span class="doc-detail">${esc(ev.agent || "agent")} · ${esc(ev.ts)}</span>
          </div>`).join("")}</div>`
      : `<p class="empty-muted" style="margin-top:8px;">近期尚無攔截事件紀錄。</p>`;

    root.innerHTML = `
      <div class="page-head">
        <div>
          <h1>偏好設定與護欄控制</h1>
          <p class="page-sub">單一事實來源：~/.omnikit/kit.yaml（rev ${boot.rev}）</p>
        </div>
        <button type="button" class="btn btn-sm" id="btn-page-theme">切換深淺色</button>
      </div>

      <form id="form-guard-and-panel" class="panel-card">
        <div class="panel-head">
          <div>
            <h2>防假完工護欄（Anti-Fake-Done Gate）</h2>
            <p>當 AI 偷加 .skip 跳過失敗測試、或改完程式畫面卻沒附上真實執行／瀏覽器驗證就宣稱完成時，自動攔截打回重做</p>
          </div>
          <span class="tag tag-accent">近 30 天攔截 ${trip.recent_30d} 次（累計 ${trip.total} 次）</span>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="set-done-check">完工檢查攔截強度</label>
            <select id="set-done-check" class="select-field">
              <option value="block" ${boot.done_check === "block" ? "selected" : ""}>強制攔截（推薦：抓到假綠燈或無實測證據立即擋回）</option>
              <option value="log" ${boot.done_check === "log" ? "selected" : ""}>僅記錄到日誌，不阻擋回覆</option>
              <option value="off" ${boot.done_check === "off" ? "selected" : ""}>暫時關閉</option>
            </select>
          </div>
          <div class="field">
            <label for="set-t3-url">T3 Code 遠端網址（選填，Tailscale 手機跳轉用）</label>
            <input id="set-t3-url" type="url" value="${esc(ovSet.t3_base_url || "")}" placeholder="https://pc.example.ts.net:2388">
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="set-parked-days">專案幾天沒動自動歸入停泊</label>
            <input id="set-parked-days" type="number" min="1" max="60" value="${ovSet.parked_days ?? 3}">
          </div>
          <div class="field">
            <label for="set-overload">主線對話超過幾項提醒交接</label>
            <input id="set-overload" type="number" min="100" max="10000" step="100" value="${ovSet.overload_items ?? 1000}">
          </div>
        </div>
        <label class="check-row">
          <input id="set-auto-commit" type="checkbox" ${ovSet.auto_commit_status !== false ? "checked" : ""}>
          <span>修改 NOW.md 時自動寫入本機 Git 版本歷史（可隨時還原舊版）</span>
        </label>
        <label class="check-row">
          <input id="set-auto-push" type="checkbox" ${ovSet.auto_push_status ? "checked" : ""}>
          <span>若 ~/.omnikit/status 有綁定遠端私人儲存庫，儲存後順便推送</span>
        </label>
        ${eventsHtml}
        <div class="modal-foot" data-write-only>
          <button type="submit" class="btn btn-primary">儲存護欄與面板設定</button>
        </div>
      </form>

      <form id="form-profile-habits" class="panel-card">
        <div class="panel-head">
          <div>
            <h2>個人 AI 溝通與工程習慣（Profile：${esc(boot.active_profile)}）</h2>
            <p>${boot.is_handwritten_profile
              ? `目前使用手寫規則檔「${esc(boot.active_profile)}」；勾選並儲存時會自動另存為下方新設定檔並切換，原手寫 AGENTS.md 完整保留不被覆蓋。`
              : "可依需求自由複選，儲存後立即同步到這台所有已安裝的 Agent"}</p>
          </div>
        </div>
        <div class="habit-grid">${habitsHtml}</div>
        <div class="inline-options">
          <label class="opt-group">
            <span>回覆語言與詳略</span>
            <select id="set-lang-verb" class="select-field">
              <option value="zh-TW:concise" ${(prev.language || "zh-TW") === "zh-TW" && (prev.verbosity || "concise") === "concise" ? "selected" : ""}>繁體中文 · 精簡扼要</option>
              <option value="zh-TW:detailed" ${(prev.language || "zh-TW") === "zh-TW" && prev.verbosity === "detailed" ? "selected" : ""}>繁體中文 · 完整說明</option>
              <option value="en:concise" ${prev.language === "en" && (prev.verbosity || "concise") === "concise" ? "selected" : ""}>English · Concise</option>
              <option value="en:detailed" ${prev.language === "en" && prev.verbosity === "detailed" ? "selected" : ""}>English · Detailed</option>
            </select>
          </label>
          <label class="opt-group">
            <span>Agent 自動執行程度</span>
            <select id="set-autonomy" class="select-field">
              <option value="balanced" ${(prev.autonomy || "balanced") === "balanced" ? "selected" : ""}>專案內直接改，安裝先問</option>
              <option value="hands-off" ${prev.autonomy === "hands-off" ? "selected" : ""}>大多放手自動做</option>
              <option value="cautious" ${prev.autonomy === "cautious" ? "selected" : ""}>每步先列計畫等我同意</option>
            </select>
          </label>
          ${boot.is_handwritten_profile ? `
            <label class="opt-group">
              <span>另存新設定檔代號（小寫英數）</span>
              <input id="set-new-prof-name" type="text" class="composer-input" value="${esc(`${boot.active_profile}-panel`)}" required style="min-height:38px;">
            </label>
          ` : ""}
        </div>
        <div class="modal-foot" data-write-only>
          <button type="submit" class="btn btn-primary">${boot.is_handwritten_profile ? "另存新設定檔並同步習慣規則" : "儲存並同步習慣規則"}</button>
        </div>
      </form>

      <div class="panel-card" data-write-only>
        <div class="panel-head">
          <div>
            <h2>背景服務與按需啟動控制</h2>
            <p>預設採「需要時啟動、用完即關」零常駐負擔；若你想用手機透過 Tailscale 隨時查看進度，可開啟登入自動啟動</p>
          </div>
        </div>
        <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;">
          <label style="display:flex;align-items:center;gap:12px;cursor:pointer;">
            <button type="button" role="switch" aria-checked="${Boolean(boot.autostart_enabled)}" class="switch-btn" id="btn-toggle-autostart"></button>
            <span>Windows 登入時自動在背景啟動控制面板（無黑窗）</span>
          </label>
          <button type="button" class="btn btn-sm btn-danger" id="btn-stop-server">停止本機面板伺服器</button>
        </div>
      </div>

      <details class="panel-card" id="adv-map-details">
        <summary style="cursor:pointer;font-weight:600;display:flex;align-items:center;justify-content:space-between;">
          <span>進階檢視：OmniKit 系統架構地圖（map.html）</span>
          <a class="btn btn-sm" href="/map.html" target="_blank" rel="noopener">新分頁開啟 ${ICON.ext}</a>
        </summary>
        <div class="map-frame-wrap">
          <iframe id="map-iframe" title="OmniKit 架構地圖" loading="lazy"></iframe>
        </div>
      </details>
    `;

    const det = $("#adv-map-details");
    if (det) {
      det.addEventListener("toggle", () => {
        if (det.open && !state.mapLoaded) {
          $("#map-iframe").src = "/map.html";
          state.mapLoaded = true;
        }
      });
    }
  }

  // ---------- NOW.md 檢視與歷史還原 ----------
  async function openNowDialog(pid) {
    try {
      const [nowRes, histRes] = await Promise.all([
        api(`/api/projects/${encodeURIComponent(pid)}/now`),
        api(`/api/projects/${encodeURIComponent(pid)}/history`),
      ]);
      $("#dlg-now-title").textContent = `${pid} · NOW.md`;
      $("#dlg-now-path").textContent = nowRes.path || "尚未建立";
      $("#dlg-now-body").textContent = nowRes.exists ? nowRes.content : "尚未建立 NOW.md，點一下「更新狀態板」即可自動產生";

      const entries = histRes.entries || [];
      const histBox = $("#dlg-now-history");
      if (!entries.length) {
        histBox.innerHTML = `<span class="muted-sm">尚無歷史版本紀錄</span>`;
      } else {
        histBox.innerHTML = `
          <div style="font-size:13px;font-weight:600;">本機版本歷史（${entries.length} 筆）</div>
          <div class="history-list">
            ${entries.map((e) => `
              <div class="history-row">
                <span><code>${esc(e.rev)}</code> · ${esc(e.summary)} <span class="muted-sm">(${esc(fmtWhen(e.at))})</span></span>
                ${state.session.writable ? `<button type="button" class="btn btn-sm" data-restore-pid="${esc(pid)}" data-restore-rev="${esc(e.rev)}">還原此版</button>` : ""}
              </div>`).join("")}
          </div>`;
      }
      $("#dlg-now").showModal();
    } catch (err) {
      showToast(err.message);
    }
  }

  // ---------- 事件綁定 ----------
  function bindEvents() {
    for (const btn of $$("[data-tab]")) btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    $("#btn-theme").addEventListener("click", toggleTheme);
    $("#btn-sync").addEventListener("click", () => {
      loadOverview(true);
      loadBootstrap(true);
    });
    $("#btn-reconcile-all").addEventListener("click", triggerReconcileAll);
    $("#btn-refresh-tools").addEventListener("click", () => {
      loadBootstrap(true);
      if (state.workbenchView === "catalog") loadTools(true);
    });
    $("#btn-run-doctor").addEventListener("click", () => loadDoctor(true));
    $("#btn-fix-doctor").addEventListener("click", fixDoctor);
    $("#btn-refresh-agy").addEventListener("click", () => loadAccounts(true));

    // 匯出／匯入設定包
    $("#btn-export-bundle").addEventListener("click", async () => {
      try {
        const bundle = await api("/api/kit/bundle");
        await copyText(JSON.stringify(bundle, null, 2), "工作台設定包 JSON");
      } catch (err) {
        showToast(err.message);
      }
    });
    $("#btn-import-bundle").addEventListener("click", () => {
      $("#form-bundle").reset();
      $("#dlg-bundle").showModal();
    });
    $("#form-bundle").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const parsed = JSON.parse($("#inp-bundle-json").value.trim());
        await api("/api/kit/import", { method: "POST", body: JSON.stringify({ bundle: parsed }) });
        $("#dlg-bundle").close();
        showToast("已套用工作台設定包");
        await loadBootstrap(true);
      } catch (err) {
        showToast(`匯入失敗：${err.message}`);
      }
    });

    // 工作台雙視圖切換與即時開關
    $("#tools-view-switch").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-wview]");
      if (!btn) return;
      state.workbenchView = btn.dataset.wview;
      for (const b of $$("#tools-view-switch [data-wview]")) {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", String(on));
      }
      renderWorkbenchTab();
      if (state.workbenchView === "catalog" && !state.tools) loadTools(false);
    });

    $("#workbench-curated-root").addEventListener("click", (e) => {
      const sw = e.target.closest("[data-toggle-tool]");
      if (!sw) return;
      toggleWorkbenchTool(sw.dataset.toggleTool, sw.dataset.curEnabled === "1", sw);
    });

    // 漂移橫幅動作
    $("#drift-banner").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-drift-id]");
      if (!btn) return;
      btn.disabled = true;
      try {
        await api("/api/kit/drift", {
          method: "POST",
          body: JSON.stringify({ id: btn.dataset.driftId, action: btn.dataset.driftAct }),
        });
        showToast("已處理外部設定變更");
        await loadBootstrap(true);
      } catch (err) {
        showToast(err.message);
      } finally {
        btn.disabled = false;
      }
    });

    // 首頁互動（精靈與總覽）
    $("#home-root").addEventListener("click", async (e) => {
      const gotoBtn = e.target.closest("[data-goto-tab]");
      if (gotoBtn) {
        switchTab(gotoBtn.dataset.gotoTab);
        return;
      }
      const copyRaw = e.target.closest("[data-copy-raw]");
      if (copyRaw) {
        copyText(copyRaw.dataset.copyRaw, "指令");
        return;
      }
      if (e.target.closest("#btn-reopen-wizard")) {
        state.forceSetupWizard = true;
        initSetupDraft(state.bootstrap);
        renderHome();
        return;
      }
      if (e.target.closest("#btn-cancel-wizard")) {
        state.forceSetupWizard = false;
        renderHome();
        return;
      }
      if (e.target.closest("#btn-home-new-proj") || e.target.closest("#btn-card-starter")) {
        openStarterModal();
        return;
      }

      const impBtn = e.target.closest("[data-import-one]");
      if (impBtn) {
        impBtn.disabled = true;
        try {
          await api("/api/projects/import", {
            method: "POST",
            body: JSON.stringify({ projects: [{ name: impBtn.dataset.importName, path: impBtn.dataset.importOne }] }),
          });
          showToast(`已匯入專案 ${impBtn.dataset.importName}`);
          await Promise.all([loadBootstrap(true), loadOverview(false, true)]);
        } catch (err) {
          showToast(err.message);
        } finally {
          impBtn.disabled = false;
        }
        return;
      }

      const presetBtn = e.target.closest("[data-pick-preset]");
      if (presetBtn && state.setupDraft) {
        const pid = presetBtn.dataset.pickPreset;
        const pObj = (state.bootstrap?.workbench?.presets || []).find((x) => x.id === pid);
        if (pObj) {
          state.setupDraft.preset = pid;
          state.setupDraft.domains = new Set(pObj.domains || ["software-dev"]);
          state.setupDraft.tools = filterCompatibleTools(pObj.tools || [], state.bootstrap);
          renderHome();
        }
        return;
      }

      const wizTool = e.target.closest("[data-wizard-tool]");
      if (wizTool && state.setupDraft) {
        const tid = wizTool.dataset.wizardTool;
        if (state.setupDraft.tools.has(tid)) state.setupDraft.tools.delete(tid);
        else state.setupDraft.tools.add(tid);
        renderHome();
        return;
      }

      const applyWiz = e.target.closest("#btn-apply-wizard");
      if (applyWiz && state.setupDraft) {
        applyWiz.disabled = true;
        applyWiz.textContent = "正在套用工作台與規則…";
        try {
          const d = state.setupDraft;
          const lv = ($("#wiz-lang-verb")?.value || "zh-TW:concise").split(":");
          const autonomy = $("#wiz-autonomy")?.value || "balanced";
          const wizDoneCheck = $("#wiz-done-check")?.value || d.doneCheck || "log";
          const profName = ($("#wiz-prof-name")?.value || d.profileName || "personal").trim().toLowerCase();

          const ansPayload = {
            name: profName,
            language: lv[0],
            verbosity: lv[1],
            autonomy,
            domains: [...d.domains],
            pains: [...d.pains],
            evaluate_tools: Boolean(d.evaluateTools),
          };
          if (d.background) ansPayload.background = d.background;
          if (d.projects) ansPayload.projects = d.projects;

          const res = await api("/api/kit/apply", {
            method: "POST",
            body: JSON.stringify({
              expected_rev: state.bootstrap?.rev,
              preset: [d.preset],
              done_check: wizDoneCheck,
              tools: [...d.tools],
              answers: ansPayload,
            }),
          });
          if (res.rev && state.bootstrap) state.bootstrap.rev = res.rev;

          const candChecks = $$("[data-wizard-cand]:checked", $("#home-root"));
          if (candChecks.length) {
            const toImp = candChecks.map((c) => ({ path: c.dataset.wizardCand, name: c.dataset.candName }));
            await api("/api/projects/import", { method: "POST", body: JSON.stringify({ projects: toImp }) });
          }

          state.forceSetupWizard = false;
          state.bootstrap = res.bootstrap || (await api("/api/bootstrap?refresh=1"));
          await loadOverview(false, true);
          renderHome();
          showToast("已成功套用精選工作台與個人設定！");
        } catch (err) {
          showToast(err.message);
          applyWiz.disabled = false;
          applyWiz.textContent = "一鍵套用工作台與個人設定";
        }
      }
    });

    $("#home-root").addEventListener("change", (e) => {
      if (!state.setupDraft) return;
      const hab = e.target.closest("[data-wizard-habit]");
      if (hab) {
        if (hab.checked) state.setupDraft.pains.add(hab.dataset.wizardHabit);
        else state.setupDraft.pains.delete(hab.dataset.wizardHabit);
        hab.closest(".habit-item")?.classList.toggle("is-checked", hab.checked);
        return;
      }
      const cand = e.target.closest("[data-wizard-cand]");
      if (cand) {
        if (cand.checked) state.setupDraft.importCandidates.add(cand.dataset.wizardCand);
        else state.setupDraft.importCandidates.delete(cand.dataset.wizardCand);
      }
      if (e.target.id === "wiz-lang-verb") {
        const [l, v] = e.target.value.split(":");
        state.setupDraft.language = l;
        state.setupDraft.verbosity = v;
      }
      if (e.target.id === "wiz-autonomy") state.setupDraft.autonomy = e.target.value;
      if (e.target.id === "wiz-done-check") state.setupDraft.doneCheck = e.target.value;
      if (e.target.id === "wiz-prof-name") state.setupDraft.profileName = e.target.value;
    });

    // 設定頁互動
    $("#settings-page-root").addEventListener("click", async (e) => {
      if (e.target.closest("#btn-page-theme")) {
        toggleTheme();
        return;
      }
      const autoSw = e.target.closest("#btn-toggle-autostart");
      if (autoSw) {
        const cur = autoSw.getAttribute("aria-checked") === "true";
        autoSw.disabled = true;
        try {
          await api("/api/autostart", { method: "POST", body: JSON.stringify({ enabled: !cur }) });
          await loadBootstrap(true);
          showToast(!cur ? "已開啟登入背景自動啟動" : "已關閉登入自動啟動");
        } catch (err) {
          showToast(err.message);
        } finally {
          autoSw.disabled = false;
        }
        return;
      }
      const stopBtn = e.target.closest("#btn-stop-server");
      if (stopBtn) {
        if (!window.confirm("確定要停止本機控制面板伺服器嗎？（隨時可執行 uv run scripts/cockpit.py open 或 /ok 面板 重新啟動）")) return;
        try {
          await api("/api/server/stop", { method: "POST", body: JSON.stringify({}) });
          showToast("本機面板伺服器已停止，可關閉此分頁");
        } catch (err) {
          showToast(err.message);
        }
      }
    });

    $("#settings-page-root").addEventListener("submit", async (e) => {
      if (e.target.id === "form-guard-and-panel") {
        e.preventDefault();
        try {
          await api("/api/settings", {
            method: "PATCH",
            body: JSON.stringify({
              done_check: $("#set-done-check").value,
              t3_base_url: $("#set-t3-url").value.trim(),
              parked_days: Number($("#set-parked-days").value || 3),
              overload_items: Number($("#set-overload").value || 1000),
              auto_commit_status: $("#set-auto-commit").checked,
              auto_push_status: $("#set-auto-push").checked,
            }),
          });
          showToast("護欄與面板設定已儲存");
          await Promise.all([loadBootstrap(true), loadOverview(false, true)]);
        } catch (err) {
          showToast(err.message);
        }
      } else if (e.target.id === "form-profile-habits") {
        e.preventDefault();
        const pains = $$('input[name="pain"]:checked', e.target).map((x) => x.value);
        const [lang, verb] = ($("#set-lang-verb")?.value || "zh-TW:concise").split(":");
        const autonomy = $("#set-autonomy")?.value || "balanced";
        const prev = state.bootstrap?.previous_answers || {};
        const customProf = $("#set-new-prof-name")?.value.trim().toLowerCase();
        const targetProf = customProf || (state.bootstrap?.active_profile === "default" ? "personal" : state.bootstrap?.active_profile);
        try {
          await api("/api/kit/apply", {
            method: "POST",
            body: JSON.stringify({
              expected_rev: state.bootstrap?.rev,
              answers: {
                name: targetProf,
                language: lang,
                verbosity: verb,
                autonomy,
                domains: prev.domains || ["software-dev"],
                pains,
                evaluate_tools: Boolean(prev.evaluate_tools),
                projects: prev.projects,
                background: prev.background,
              },
            }),
          });
          showToast("個人習慣規則已儲存並同步至所有 Agent");
          await loadBootstrap(true);
        } catch (err) {
          showToast(err.message);
        }
      }
    });

    // 專案分頁互動
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
        if (p) copyText(p.commands.next_prompt, ` ${p.name} 的下一步提示詞`);
        return;
      }
      const copyRaw = e.target.closest("[data-copy-raw]");
      if (copyRaw) {
        copyText(copyRaw.dataset.copyRaw, "驗收指令");
        return;
      }
      const viewNow = e.target.closest("[data-view-now]");
      if (viewNow) {
        openNowDialog(viewNow.dataset.viewNow);
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
          showToast(curDone ? "已重開待改項目" : "已勾銷待改項目");
          await loadOverview(false, true);
        } catch (err) {
          showToast(err.message);
        } finally {
          togBtn.disabled = false;
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
          showToast(curParked ? `已把 ${pid} 移回執行清單` : `已停泊 ${pid}`);
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
        showToast(`已寫入 ${pid} 的 NOW.md`);
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      }
    });

    // NOW.md 歷史還原按鈕
    $("#dlg-now-history").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-restore-pid]");
      if (!btn) return;
      const pid = btn.dataset.restorePid;
      const rev = btn.dataset.restoreRev;
      btn.disabled = true;
      try {
        await api(`/api/projects/${encodeURIComponent(pid)}/restore`, {
          method: "POST",
          body: JSON.stringify({ rev }),
        });
        showToast(`已還原至版本 ${rev}`);
        await openNowDialog(pid);
        await loadOverview(false, true);
      } catch (err) {
        showToast(err.message);
      } finally {
        btn.disabled = false;
      }
    });

    $("#tools-search").addEventListener("input", (e) => {
      state.toolSearch = e.target.value;
      renderToolsCatalog();
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
      renderToolsCatalog();
    });

    for (const closeBtn of $$("[data-close]")) {
      closeBtn.addEventListener("click", () => closeBtn.closest("dialog")?.close());
    }

    // 新增與登記專案對話框
    function openStarterModal() {
      $("#form-starter").reset();
      $("#starter-result-box").hidden = true;
      $("#starter-result-box").innerHTML = "";
      $("#btn-starter-submit").hidden = false;
      $("#dlg-starter").showModal();
    }

    $("#btn-add-project").addEventListener("click", openStarterModal);
    $("#btn-new-starter-proj").addEventListener("click", openStarterModal);
    $("#btn-open-register-proj").addEventListener("click", () => {
      $("#form-project").reset();
      $("#dlg-project").showModal();
    });

    $("#form-project").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const name = String(fd.get("name") || "").trim();
      const customId = String(fd.get("id") || "").trim();
      const path = String(fd.get("path") || "").trim();
      const ensureNow = $("#inp-proj-ensure-now").checked;
      if (!name) return;
      try {
        const regRes = await api("/api/projects/register", {
          method: "POST",
          body: JSON.stringify({ name, id: customId || undefined, path, ensure_now: ensureNow }),
        });
        $("#dlg-project").close();
        showToast(`已登記專案 ${name}`);
        await Promise.all([loadOverview(false, true), loadBootstrap(true)]);
        state.selectedId = regRes.project?.id || customId || name;
        renderList();
        renderInspector();
        switchTab("cockpit");
      } catch (err) {
        showToast(err.message);
      }
    });

    $("#form-starter").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("#btn-starter-submit");
      btn.disabled = true;
      try {
        const name = $("#inp-starter-name").value.trim();
        const parentDir = $("#inp-starter-parent").value.trim();
        const res = await api("/api/projects/create", {
          method: "POST",
          body: JSON.stringify({ name, parent_dir: parentDir }),
        });
        await Promise.all([loadOverview(false, true), loadBootstrap(true)]);
        state.selectedId = res.project?.id || name;
        btn.hidden = true;
        const box = $("#starter-result-box");
        box.hidden = false;
        box.innerHTML = `
          <div class="panel-card" style="padding:14px;background:var(--bg);">
            <div style="font-weight:600;color:var(--accent);margin-bottom:6px;">✓ 已建立專案資料夾與本機 NOW.md！</div>
            <div class="cand-path" style="margin-bottom:10px;">路徑：${esc(res.project?.path || "")}</div>
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">複製任一句貼給 AI 即可馬上開工：</div>
            <div class="prompt-copy-list">
              ${(res.starter_prompts || []).map((pr) => `
                <div class="prompt-copy-row" style="background:var(--surface);">
                  <div class="prompt-copy-desc" style="color:var(--text);">${esc(pr)}</div>
                  <button type="button" class="btn btn-sm" data-copy-starter="${esc(pr)}">複製</button>
                </div>`).join("")}
            </div>
          </div>`;
        showToast(`已建立新專案 ${name}`);
      } catch (err) {
        showToast(err.message);
      } finally {
        btn.disabled = false;
      }
    });

    $("#starter-result-box").addEventListener("click", (e) => {
      const b = e.target.closest("[data-copy-starter]");
      if (b) copyText(b.dataset.copyStarter, "破冰提示詞");
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) {
        e.preventDefault();
        if (state.activeTab === "tools") $("#tools-search")?.focus();
        else if (state.activeTab === "cockpit") $("#project-search")?.focus();
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
      // 維持預設
    }
    document.body.classList.toggle("is-readonly", !state.session.writable);
    const banner = $("#readonly-banner");
    if (banner) banner.hidden = state.session.writable;
  }

  initTheme();
  bindEvents();
  loadSession().finally(() => {
    loadBootstrap(false);
    loadOverview(false);
  });
})();
