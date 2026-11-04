// OmniKit 槽位看板：搜尋、依狀態與槽位重點篩選、試用剩餘天數。頁面本身已經是完整的 HTML，沒有這支也能看。
(() => {
  const search = document.getElementById("q");
  const count = document.getElementById("count");
  const empty = document.getElementById("empty");
  // 同一個工具可能放在兩個槽位，計數用不重複的 id
  const total = new Set([...document.querySelectorAll(".card")].map((c) => c.dataset.id)).size;
  const groups = {};
  for (const group of document.querySelectorAll(".chips[data-group]")) {
    const buttons = [...group.querySelectorAll("button")];
    groups[group.dataset.group] = buttons;
    for (const button of buttons) {
      button.addEventListener("click", () => {
        button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true"));
        apply();
      });
    }
  }

  const enabled = (name) =>
    new Set(groups[name].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.value));

  function apply() {
    const term = search.value.trim().toLowerCase();
    const statuses = enabled("status");
    const focuses = enabled("focus");
    const shown = new Set();
    for (const slot of document.querySelectorAll(".slot")) {
      // 沒有重點的區塊（零件庫與未分配）只在重點全選時顯示
      const focusOk = slot.dataset.focus
        ? focuses.has(slot.dataset.focus)
        : focuses.size === groups.focus.length;
      const slotHit = term !== "" && slot.dataset.search.includes(term);
      let any = false;
      for (const card of slot.querySelectorAll(".card")) {
        const ok = focusOk && statuses.has(card.dataset.status) &&
          (term === "" || slotHit || card.dataset.search.includes(term));
        card.hidden = !ok;
        if (ok) {
          any = true;
          shown.add(card.dataset.id);
        }
      }
      slot.hidden = !any;
    }
    count.textContent = `顯示 ${shown.size} / ${total} 個工具`;
    empty.hidden = shown.size > 0;
  }

  search.addEventListener("input", apply);
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== search) {
      event.preventDefault();
      search.focus();
    }
  });

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (const el of document.querySelectorAll("[data-until]")) {
    const days = Math.round((new Date(`${el.dataset.until}T00:00:00`) - today) / 86400000);
    el.textContent = days > 0 ? `剩 ${days} 天` : days === 0 ? "今天到期" : `已過期 ${-days} 天`;
    el.classList.toggle("overdue", days <= 0);
  }

  apply();
})();
