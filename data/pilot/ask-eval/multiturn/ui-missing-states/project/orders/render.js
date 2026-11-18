// 訂單查詢結果的畫面。state = { loading, error, orders: [{ id, customer, total }] }
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function render(state) {
  if (state.loading) return "";
  if (state.error) return "";
  const rows = state.orders
    .map((o) => `<tr><td>${escapeHtml(o.id)}</td><td class="customer">${escapeHtml(o.customer)}</td>` +
      `<td class="total">${o.total}</td></tr>`)
    .join("");
  return `<table class="orders"><thead><tr><th>訂單編號</th><th>客戶</th><th>金額</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

if (typeof module !== "undefined") module.exports = { render };
