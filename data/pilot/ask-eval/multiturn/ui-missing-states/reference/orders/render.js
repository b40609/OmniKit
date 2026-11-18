function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function render(state) {
  if (state.loading) return '<p class="status loading">載入中…</p>';
  if (state.error) return '<p class="status error">查詢失敗，請稍後再試一次。</p>';
  if (!state.orders || state.orders.length === 0) return '<p class="status empty">查無訂單，請確認訂單編號。</p>';
  const rows = state.orders
    .map((o) => `<tr><td>${escapeHtml(o.id)}</td><td class="customer">${escapeHtml(o.customer)}</td>` +
      `<td class="total">${o.total}</td></tr>`)
    .join("");
  return `<table class="orders"><thead><tr><th>訂單編號</th><th>客戶</th><th>金額</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

if (typeof module !== "undefined") module.exports = { render };
