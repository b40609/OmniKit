// OmniKit 個人面板前端互動邏輯（純原生 JS，零外部依賴）
(() => {
  const state = {
    activeTab: "cockpit",
    filter: "all",
    search: "",
    overview: null,
    tools: null,
    accounts: null,
    toolStatuses: new Set(["default", "trial", "on_demand"]),
    toolSearch: "",
    expandedProjects: new Set(),
    triFormOpen: new Set(),
    mapLoaded: false,
  };

  const LANE_ORDER = ["blocked_on_me", "ready_to_settle", "active", "parked"];
  const LANE_TITLES = {
    blocked_on_me: "第一優先：卡在你身上（等你拍板／不滿意待改）",
    ready_to_settle: "跑完待收尾／需對帳（釋放側邊欄雜訊）",
    active: "執行中／隨時可推進",
    parked: "已停泊（超過停泊門檻或手動停泊）",
  };
  const STATUS_LABELS = {
    default: "預設",
    trial: "試用",
    on_demand: "按需備案",
    pending: "待評估",
    rejected: "拒絕",
    retired: "退役",
  };
  const SLOPE_BADGE = {
    uphill: { text: "上坡 · 探索中", cls: "b-trial" },
    downhill: { text: "下坡 · 純執行", cls: "b-active" },
    unknown: { text: "未標坡度", cls: "b-parked" },
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
    }, 2600);
  }

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `請求失敗 (${res.status})`);
    }
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

  // ---------- 分頁切換 ----------
  function switchTab(tab) {
    state.activeTab = tab;
    for (const btn of $$("[data-tab]")) {
      const active = btn.dataset.tab === tab;
      if (active) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    }
    for (const sec of $$(".tab-panel")) {
      sec.hidden = sec.id !== `tab-${tab}`;
    }
    $("#main-scroll").scrollTop = 0;

    if (tab === "tools" && !state.tools) loadTools();
    if (tab === "accounts" && !state.accounts) loadAccounts(false);
    if (tab === "map" && !state.mapLoaded) {
      $("#map-iframe").src = "/map.html";
      state.mapLoaded = true;
    }
  }

  // ---------- 分頁 1：專案指揮台 ----------
  async function loadOverview(sync = false) {
    const syncBtn = $("#btn-sync");
    syncBtn.disabled = true;
    syncBtn.textContent = sync ? "同步中…" : "更新中…";
    try {
      const data = await api(`/api/overview${sync ? "?sync=1" : ""}`);
      state.overview = data;
      renderOverview();
      if (sync) {
        const msg = data.sync?.synced
          ? "狀態庫已同步並完成對帳"
          : `已完成本機對帳${data.sync?.reason ? `（${data.sync.reason}）` : ""}`;
        showToast(msg);
      }
    } catch (err) {
      $("#lanes-root").innerHTML = `<div class="empty-box">載入失敗：${esc(err.message)}</div>`;
      showToast(err.message);
    } finally {
      syncBtn.disabled = false;
      syncBtn.textContent = "同步對帳";
    }
  }

  function renderCritiquesHtml(p) {
    const items = p.now.critiques || [];
    const listHtml = items.length
      ? `<ul class="critique-list">${items.map((c) => {
          const isTri = c.symptom || c.pain || c.criteria;
          const bodyHtml = isTri
            ? `<div class="critique-tri">
                ${c.symptom ? `<div><b>現況</b>${esc(c.symptom)}</div>` : ""}
                ${c.pain ? `<div><b>不滿</b>${esc(c.pain)}</div>` : ""}
                ${c.criteria ? `<div><b>過關</b>${esc(c.criteria)}</div>` : ""}
              </div>`
            : esc(c.text);
          return `<li class="critique-item ${c.done ? "is-done" : ""}">
            <button type="button" class="critique-check-btn" data-toggle-critique="${esc(p.id)}" data-idx="${c.index}" data-done="${c.done ? "1" : "0"}" aria-label="${c.done ? "重新開啟此待改項" : "標記為已解決"}">
              <span class="critique-box">${c.done ? "✓" : ""}</span>
            </button>
            <div class="critique-body">${bodyHtml}</div>
          </li>`;
        }).join("")}</ul>`
      : `<p class="quad-empty">目前沒有未收斂的不滿意項目。</p>`;

    const triOpen = state.triFormOpen.has(p.id);
    return `
      ${listHtml}
      <form class="critique-form" data-add-critique="${esc(p.id)}" data-path="${esc(p.path || "")}">
        ${triOpen ? `
          <div class="tri-fields">
            <input class="critique-input" name="symptom" placeholder="① 現況（現在長怎樣）">
            <input class="critique-input" name="pain" placeholder="② 痛點（你嫌哪裡不滿意）" required>
            <input class="critique-input" name="criteria" placeholder="③ 過關標準（改成怎樣算過）">
          </div>
          <div class="critique-quick-row">
            <button type="submit" class="btn btn-primary btn-sm">記進待改匣</button>
            <button type="button" class="btn btn-ghost btn-sm" data-toggle-tri="${esc(p.id)}">切回一句速記</button>
          </div>
        ` : `
          <div class="critique-quick-row">
            <input class="critique-input" name="text" placeholder="隨手記一條不滿意（Enter 送出）" required>
            <button type="submit" class="btn btn-primary btn-sm">＋記</button>
            <button type="button" class="btn btn-ghost btn-sm" data-toggle-tri="${esc(p.id)}" title="展開三段式欄位">三段</button>
          </div>
        `}
      </form>
    `;
  }

  function renderProjectCard(p) {
    const prog = p.now.progress || {};
    const hasSteps = prog.total != null && prog.total > 0;
    const pct = hasSteps ? Math.min(100, Math.round((prog.done / prog.total) * 100)) : 0;
    const stepText = hasSteps ? `${prog.done}/${prog.total} 步` : "步數未填";
    const slope = SLOPE_BADGE[prog.slope] || SLOPE_BADGE.unknown;
    const isExpanded = state.expandedProjects.has(p.id);

    const badges = [];
    if (p.remote_only) badges.push(`<span class="badge b-info">遠端專案</span>`);
    if (p.stale) badges.push(`<span class="badge b-warn">過期紅燈</span>`);
    if (p.open_critiques_count > 0) badges.push(`<span class="badge b-blocked">待改 ${p.open_critiques_count}</span>`);
    if (p.t3.overloaded_count > 0) badges.push(`<span class="badge b-blocked">主線超載</span>`);
    if (p.t3.ready_to_settle_count > 0) badges.push(`<span class="badge b-settle">待 Settle ${p.t3.ready_to_settle_count}</span>`);

    // 客觀遙測橫條
    const tele = [];
    if (p.git.available) {
      tele.push(`<span>分支 <b class="t-strong mono">${esc(p.git.branch)}</b></span>`);
      if (p.git.dirty_count > 0) tele.push(`<span class="t-warn">未提交 ${p.git.dirty_count} 檔</span>`);
      if (p.git.ahead > 0) tele.push(`<span class="t-warn">未推 ${p.git.ahead}</span>`);
      if (p.git.last_hash) tele.push(`<span class="mono">${esc(p.git.last_hash)}</span>`);
    } else {
      tele.push(`<span>${esc(p.git.reason || "無本機 Git")}</span>`);
    }
    if (p.t3.available) {
      tele.push(`<span>T3 未結案 <b class="t-strong">${p.t3.unsettled_count}</b> 條${p.t3.running_count ? `（跑中 ${p.t3.running_count}）` : ""}</span>`);
    }
    tele.push(`<span>活躍 ${esc(p.last_activity_age)}</span>`);
    if (p.stale_reasons.length) {
      tele.push(`<span class="t-danger">⚠ ${esc(p.stale_reasons.join("；"))}</span>`);
    }

    const conclusionsHtml = p.now.conclusions.length
      ? `<ul class="quad-list">${p.now.conclusions.slice(0, 3).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`
      : `<p class="quad-empty">尚未記下現行結論（可點下方「複製對帳指令」讓 Agent 補齊）。</p>`;

    const nxt = p.now.next_action;
    const ownerBadge = nxt
      ? (nxt.owner === "user"
        ? `<span class="badge b-blocked">等你處理</span>`
        : nxt.owner === "agent"
          ? `<span class="badge b-active">Agent 可直接跑</span>`
          : `<span class="badge b-parked">未指派</span>`)
      : "";

    const decisionsHtml = p.now.decisions.length
      ? `<ul class="quad-list">${p.now.decisions.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>`
      : "";

    const detailsHtml = isExpanded ? `
      <div class="card-details">
        ${prog.steps && prog.steps.length ? `
          <div>
            <div class="quad-label">完工路徑明細</div>
            <ul class="quad-list">${prog.steps.map((s) => `<li>${s.done ? "✓ " : "○ "}${esc(s.text)}</li>`).join("")}</ul>
          </div>
        ` : ""}
        ${p.t3.threads && p.t3.threads.length ? `
          <div>
            <div class="quad-label">T3 未結案對話（${p.t3.unsettled_count}）</div>
            <div style="display:grid;gap:6px;margin-top:6px;">
              ${p.t3.threads.map((t) => `
                <div class="thread-row">
                  <div>
                    <div class="thread-title">${esc(t.title)}</div>
                    <div class="thread-meta">${esc(t.status)} · ${t.item_count} items${t.overloaded ? " · 超載" : ""}${t.model ? ` · ${esc(t.model)}` : ""}</div>
                  </div>
                  ${t.link ? `<a class="btn btn-ghost btn-sm" href="${esc(t.link)}" target="_blank" rel="noopener">開啟對話</a>` : ""}
                </div>
              `).join("")}
            </div>
          </div>
        ` : ""}
        ${p.git.last_subject ? `<div class="quad-empty">最新 commit：<span class="mono">${esc(p.git.last_hash)}</span> ${esc(p.git.last_subject)}</div>` : ""}
      </div>
    ` : "";

    return `
      <article class="proj-card lane-${esc(p.lane)}" data-project="${esc(p.id)}">
        <div class="proj-head">
          <div class="proj-title-wrap">
            <h3 class="proj-title">${esc(p.name)}</h3>
            <span class="badge ${slope.cls}">${slope.text}</span>
          </div>
          <div class="proj-badges">${badges.join("")}</div>
        </div>

        <div class="telemetry-bar">${tele.join("")}</div>

        <div class="four-grid">
          <!-- 格 1：做到哪 / 完成度 -->
          <div class="quad">
            <div class="quad-head">
              <span class="quad-label">1. 做到哪／完成度</span>
              <span class="progress-num">${esc(stepText)}</span>
            </div>
            ${hasSteps ? `<div class="progress-row"><div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div><span class="progress-num">${pct}%</span></div>` : `<p class="quad-empty">${esc(prog.summary || "尚未在 NOW.md 填寫完工路徑步數")}</p>`}
          </div>

          <!-- 格 2：目前結論 -->
          <div class="quad">
            <div class="quad-head"><span class="quad-label">2. 目前結論（現行定案）</span></div>
            ${conclusionsHtml}
          </div>

          <!-- 格 3：不滿意待改匣 -->
          <div class="quad quad-critique ${p.open_critiques_count === 0 ? "is-clear" : ""}">
            <div class="quad-head">
              <span class="quad-label">3. 不滿意待改匣（未收斂 ${p.open_critiques_count}）</span>
            </div>
            ${renderCritiquesHtml(p)}
          </div>

          <!-- 格 4：唯一球權下一步 -->
          <div class="quad">
            <div class="quad-head">
              <span class="quad-label">4. 唯一球權下一步</span>
              ${ownerBadge}
            </div>
            <div class="next-box">
              <p class="next-text">${nxt ? esc(nxt.text) : "（尚未設定下一步）"}</p>
              ${decisionsHtml ? `<div class="quad-label" style="margin-top:4px;">等拍板清單</div>${decisionsHtml}` : ""}
            </div>
          </div>
        </div>

        <div class="card-actions">
          ${p.primary_t3_url ? `<a class="btn btn-primary btn-sm" href="${esc(p.primary_t3_url)}" target="_blank" rel="noopener">打開 T3 對話</a>` : ""}
          <button type="button" class="btn btn-ghost btn-sm" data-copy-next="${esc(p.id)}">複製下一步</button>
          <button type="button" class="btn btn-ghost btn-sm" data-copy-reconcile="${esc(p.id)}">複製對帳指令</button>
          <button type="button" class="btn btn-ghost btn-sm" data-view-now="${esc(p.id)}">NOW.md</button>
          <button type="button" class="btn btn-ghost btn-sm" data-expand="${esc(p.id)}">${isExpanded ? "收合明細" : "明細與對話"}</button>
          <button type="button" class="btn btn-ghost btn-sm" data-park="${esc(p.id)}" data-parked="${p.manual_parked ? "1" : "0"}">${p.manual_parked ? "恢復活躍" : "停泊"}</button>
        </div>

        ${detailsHtml}
      </article>
    `;
  }

  function renderOverview() {
    const ov = state.overview;
    if (!ov) return;
    const s = ov.summary;
    $("#sync-meta").textContent = `對帳於 ${ov.generated_local}`;
    $("#kpi-total").textContent = s.total;
    $("#kpi-blocked").textContent = s.blocked_on_me;
    $("#kpi-settle").textContent = s.ready_to_settle;
    $("#kpi-active").textContent = s.active;
    $("#kpi-stale").textContent = s.stale;

    const alertChips = [];
    if (s.open_critiques > 0) alertChips.push(`不滿意待改 ${s.open_critiques} 條`);
    if (s.ready_to_settle_threads > 0) alertChips.push(`待 Settle 對話 ${s.ready_to_settle_threads} 條`);
    if (s.overloaded_threads > 0) alertChips.push(`超載主線 ${s.overloaded_threads} 條`);
    $("#cockpit-alerts").textContent = alertChips.join(" · ");

    const term = state.search.trim().toLowerCase();
    const filtered = ov.projects.filter((p) => {
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
      ].join(" ").toLowerCase();
      return hay.includes(term);
    });

    if (!filtered.length) {
      $("#lanes-root").innerHTML = `<div class="empty-box">目前篩選條件下沒有符合的專案。</div>`;
      return;
    }

    const byLane = Object.fromEntries(LANE_ORDER.map((l) => [l, []]));
    for (const p of filtered) byLane[p.lane]?.push(p);

    const blocks = [];
    for (const lane of LANE_ORDER) {
      const list = byLane[lane];
      if (!list.length) continue;
      if (lane === "parked" && state.filter === "all" && !term) {
        blocks.push(`
          <details class="parked-details">
            <summary>
              <span>⚪ ${LANE_TITLES[lane]}（${list.length}）— 點此展開</span>
              <span class="mono">${list.map((p) => esc(p.name)).join("、")}</span>
            </summary>
            <div class="cards-grid">${list.map(renderProjectCard).join("")}</div>
          </details>
        `);
      } else {
        blocks.push(`
          <section class="lane-group lane-${lane}">
            <div class="lane-head">
              <span class="lane-dot"></span>
              <h2>${LANE_TITLES[lane]}</h2>
              <span class="lane-count">${list.length}</span>
            </div>
            <div class="cards-grid">${list.map(renderProjectCard).join("")}</div>
          </section>
        `);
      }
    }
    $("#lanes-root").innerHTML = blocks.join("");
  }

  // ---------- 分頁 2：工具與模型 ----------
  async function loadTools(refresh = false) {
    $("#tools-grid").innerHTML = `<div class="empty-box">正在載入工具名冊與個人疊層…</div>`;
    try {
      state.tools = await api(`/api/tools${refresh ? "?refresh=1" : ""}`);
      renderTools();
    } catch (err) {
      $("#tools-grid").innerHTML = `<div class="empty-box">載入失敗：${esc(err.message)}</div>`;
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
      ? pf.exclude_models.map((m) => `<span class="badge b-blocked mono">${esc(m)}</span>`).join("")
      : `<span class="badge b-parked">無</span>`;
    const priv = (pf.private_modules || []).length
      ? pf.private_modules.map((m) => `<span class="badge b-info">${esc(m)}</span>`).join("")
      : `<span class="badge b-parked">無</span>`;

    $("#profile-overlay-body").innerHTML = `
      <div class="kv-item"><span class="kv-key">Profile</span><b>${esc(pf.name)}</b></div>
      <div class="kv-item"><span class="kv-key">思考偏好</span><span class="badge b-active mono">${esc(pf.thinking_preference)}</span></div>
      <div class="kv-item"><span class="kv-key">子任務可見性</span><span class="badge b-info mono">${esc(pf.visibility)}</span></div>
      <div class="kv-item"><span class="kv-key">額度耗盡</span><span class="badge b-settle mono">${esc(pf.on_exhausted)}</span></div>
      <div class="kv-item"><span class="kv-key">已屏蔽模型</span>${excludes}</div>
      <div class="kv-item"><span class="kv-key">私有模組</span>${priv}</div>
    `;

    const term = state.toolSearch.trim().toLowerCase();
    const list = (data.tools || []).filter((t) => {
      if (!state.toolStatuses.has(t.status)) return false;
      if (!term) return true;
      const hay = [t.id, t.name, t.summary, t.trigger_when, ...(t.slot_names || []), ...(t.modules || [])].join(" ").toLowerCase();
      return hay.includes(term);
    });

    $("#tools-count").textContent = `顯示 ${list.length} / ${data.counts.total} 張工具卡`;
    if (!list.length) {
      $("#tools-grid").innerHTML = `<div class="empty-box">目前篩選條件下沒有符合的工具卡。</div>`;
      return;
    }

    const stCls = {
      default: "b-active",
      trial: "b-trial",
      on_demand: "b-info",
      pending: "b-parked",
      rejected: "b-blocked",
      retired: "b-settle",
    };

    $("#tools-grid").innerHTML = list.map((t) => `
      <article class="tool-card">
        <div class="tool-head">
          <span class="tool-name">${t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.name)}</a>` : esc(t.name)}</span>
          <span class="badge ${stCls[t.status] || "b-parked"}">${STATUS_LABELS[t.status] || esc(t.status)}</span>
        </div>
        ${t.summary ? `<p class="tool-summary">${esc(t.summary)}</p>` : ""}
        ${t.trigger_when ? `<p class="tool-summary"><b>喚起時機：</b>${esc(t.trigger_when)}</p>` : ""}
        <div class="tool-meta">
          ${t.kind ? `<span class="badge b-parked">${esc(t.kind)}</span>` : ""}
          ${(t.slot_names || []).map((s) => `<span class="badge b-parked">${esc(s)}</span>`).join("")}
          ${t.trial_until ? `<span class="badge b-trial mono">試用至 ${esc(t.trial_until)}</span>` : ""}
        </div>
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
      $("#accounts-root").innerHTML = `<div class="empty-box">讀取失敗：${esc(err.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "刷新 Antigravity 額度";
    }
  }

  function quotaBar(label, remPct, resetText) {
    const val = remPct == null ? null : Math.max(0, Math.min(100, Math.round(Number(remPct))));
    const cls = val == null ? "" : val <= 20 ? "is-low" : val <= 45 ? "is-mid" : "";
    return `
      <div class="quota-bar-wrap">
        <div class="quota-label">
          <span>${esc(label)}${resetText ? ` · ${esc(resetText)}` : ""}</span>
          <b>${val == null ? "未知" : `剩 ${val}%`}</b>
        </div>
        <div class="quota-track"><div class="quota-fill ${cls}" style="width:${val == null ? 0 : val}%"></div></div>
      </div>
    `;
  }

  function shortIso(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${m}-${day} ${hh}:${mm} 重置`;
  }

  function renderAccounts() {
    const data = state.accounts;
    if (!data || !data.available) {
      $("#accounts-root").innerHTML = `<div class="empty-box">${esc(data?.error || "尚無帳號額度資料")}</div>`;
      return;
    }

    const alerts = data.alerts || [];
    $("#accounts-alerts").innerHTML = alerts.length
      ? alerts.map((a) => `<div class="alert-banner">⚠ ${esc(typeof a === "string" ? a : (a.message || a.text || JSON.stringify(a)))}</div>`).join("")
      : "";

    const recInst = data.claude_selection?.selected || data.claude_selection?.instance || "";
    const claudeHtml = (data.claude || []).map((c) => {
      const isRec = recInst && c.instance === recInst;
      return `
        <article class="acct-card ${isRec ? "is-recommended" : ""}">
          <div class="acct-head">
            <span class="acct-title">Claude · ${esc(c.account || c.instance)}</span>
            <div class="proj-badges">
              ${isRec ? `<span class="badge b-active">優先選號</span>` : ""}
              <span class="badge ${c.status === "ok" ? "b-info" : "b-warn"}">${esc(c.status || "unknown")}</span>
            </div>
          </div>
          ${quotaBar("5 小時剩餘", c.five_hour_remaining_pct, shortIso(c.five_hour_resets_at))}
          ${quotaBar("本週剩餘", c.weekly_remaining_pct, shortIso(c.weekly_resets_at))}
          <div class="thread-meta">實例：${esc(c.instance)} · 來源：${esc(c.source || "-")} · ${c.age_hours != null ? `${c.age_hours}h 前` : "無快照"}</div>
        </article>
      `;
    }).join("");

    const agyHtml = (data.antigravity || []).map((a) => {
      const buckets = a.buckets || {};
      const gemini = buckets.gemini || {};
      const third = buckets["3p"] || {};
      return `
        <article class="acct-card">
          <div class="acct-head">
            <span class="acct-title">Antigravity · ${esc(a.account || a.instance)}</span>
            <div class="proj-badges">
              <span class="badge ${a.auto ? "b-active" : "b-parked"}">${a.auto ? "自動派工" : "手動切換池"}</span>
              ${a.blocked ? `<span class="badge b-blocked">受阻</span>` : ""}
            </div>
          </div>
          ${quotaBar("Gemini 5h", gemini.five_hour_remaining_pct, shortIso(gemini.five_hour_resets_at))}
          ${quotaBar("Gemini 本週", gemini.weekly_remaining_pct, shortIso(gemini.weekly_resets_at))}
          ${quotaBar("Claude & GPT 桶", third.weekly_remaining_pct ?? third.five_hour_remaining_pct, shortIso(third.weekly_resets_at || third.five_hour_resets_at))}
          ${a.blocked_reason ? `<div class="t-danger" style="font-size:12.5px;">${esc(a.blocked_reason)}</div>` : ""}
          <div class="thread-meta">實例：${esc(a.instance)}${gemini.stale ? " · 快照偏舊，可按右上刷新" : ""}</div>
        </article>
      `;
    }).join("");

    $("#accounts-root").innerHTML = `
      <div>
        <div class="lane-head" style="margin-bottom:10px;">
          <h2>Claude 實例（${(data.claude || []).length}）</h2>
        </div>
        <div class="acct-grid">${claudeHtml || `<div class="empty-box">無 Claude 實例資料</div>`}</div>
      </div>
      <div>
        <div class="lane-head" style="margin-bottom:10px;">
          <h2>Antigravity 實例（${(data.antigravity || []).length}）</h2>
        </div>
        <div class="acct-grid">${agyHtml || `<div class="empty-box">無 Antigravity 實例資料</div>`}</div>
      </div>
    `;
  }

  // ---------- 事件委派 ----------
  function bindEvents() {
    for (const btn of $$("[data-tab]")) {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    }

    $("#btn-sync").addEventListener("click", () => loadOverview(true));
    $("#btn-refresh-tools").addEventListener("click", () => loadTools(true));
    $("#btn-refresh-agy").addEventListener("click", () => loadAccounts(true));

    // KPI 球權過濾
    $("#kpi-strip").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-filter]");
      if (!btn) return;
      state.filter = btn.dataset.filter;
      for (const p of $$("#kpi-strip [data-filter]")) {
        const on = p === btn;
        p.classList.toggle("is-active", on);
        p.setAttribute("aria-pressed", String(on));
      }
      renderOverview();
    });

    $("#project-search").addEventListener("input", (e) => {
      state.search = e.target.value;
      renderOverview();
    });

    // 工具頁篩選
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
      chip.setAttribute("aria-pressed", String(next));
      renderTools();
    });

    // 專案卡動態互動（複製指令、勾銷待改、新增待改、停泊、看 NOW.md）
    $("#lanes-root").addEventListener("click", async (e) => {
      const copyNext = e.target.closest("[data-copy-next]");
      if (copyNext) {
        const p = state.overview?.projects.find((x) => x.id === copyNext.dataset.copyNext);
        if (p) copyText(p.commands.next_prompt, `${p.name} 下一步指令`);
        return;
      }

      const copyRec = e.target.closest("[data-copy-reconcile]");
      if (copyRec) {
        const p = state.overview?.projects.find((x) => x.id === copyRec.dataset.copyReconcile);
        if (p) copyText(p.commands.reconcile_prompt, `${p.name} 對帳刷新指令`);
        return;
      }

      const viewNow = e.target.closest("[data-view-now]");
      if (viewNow) {
        const pid = viewNow.dataset.viewNow;
        try {
          const data = await api(`/api/projects/${encodeURIComponent(pid)}/now`);
          $("#dlg-now-title").textContent = `${pid} · NOW.md`;
          $("#dlg-now-path").textContent = data.path || "尚未建立檔案";
          $("#dlg-now-body").textContent = data.exists ? data.content : "（此專案尚未建立 NOW.md，可在卡片上先新增不滿意待改自動建立，或在對話中請 Agent 產出。）";
          $("#dlg-now").showModal();
        } catch (err) {
          showToast(err.message);
        }
        return;
      }

      const expandBtn = e.target.closest("[data-expand]");
      if (expandBtn) {
        const pid = expandBtn.dataset.expand;
        if (state.expandedProjects.has(pid)) state.expandedProjects.delete(pid);
        else state.expandedProjects.add(pid);
        renderOverview();
        return;
      }

      const triBtn = e.target.closest("[data-toggle-tri]");
      if (triBtn) {
        const pid = triBtn.dataset.toggleTri;
        if (state.triFormOpen.has(pid)) state.triFormOpen.delete(pid);
        else state.triFormOpen.add(pid);
        renderOverview();
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
          showToast(curDone ? "已重新開啟待改項" : "已勾銷待改項並寫回 NOW.md");
          await loadOverview(false);
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
          showToast(curParked ? `已將 ${pid} 恢復為活躍` : `已將 ${pid} 移入停泊區`);
          await loadOverview(false);
        } catch (err) {
          showToast(err.message);
        }
      }
    });

    $("#lanes-root").addEventListener("submit", async (e) => {
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
        showToast(`已將不滿意待改寫入 ${pid}/NOW.md`);
        await loadOverview(false);
      } catch (err) {
        showToast(err.message);
      }
    });

    // Modal 開關
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
        await api("/api/projects/register", {
          method: "POST",
          body: JSON.stringify({ name, path }),
        });
        $("#dlg-project").close();
        showToast(`已登記專案 ${name}`);
        await loadOverview(false);
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
      const payload = {
        t3_base_url: $("#inp-t3-url").value.trim(),
        parked_days: Number($("#inp-parked-days").value || 3),
        overload_items: Number($("#inp-overload").value || 1000),
        auto_commit_status: $("#inp-auto-commit").checked,
        auto_push_status: $("#inp-auto-push").checked,
      };
      try {
        await api("/api/settings", {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        $("#dlg-settings").close();
        showToast("面板設定已儲存");
        await loadOverview(false);
      } catch (err) {
        showToast(err.message);
      }
    });

    // 快捷鍵 / 聚焦搜尋
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "")) {
        e.preventDefault();
        const target = state.activeTab === "tools" ? $("#tools-search") : $("#project-search");
        target?.focus();
      }
    });
  }

  // 註冊輕量 Service Worker（PWA 必要）
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  bindEvents();
  loadOverview(false);
})();
