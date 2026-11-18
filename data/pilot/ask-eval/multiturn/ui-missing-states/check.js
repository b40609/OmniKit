// node check.js <render.js 路徑>：印出各狀態的輸出（JSON）
const path = require("path");
const fs = require("fs");
const os = require("os");
const { pathToFileURL } = require("url");

async function load(file) {
  try {
    const m = require(file);
    if (m && typeof m.render === "function") return m.render;
    if (m && m.default && typeof m.default.render === "function") return m.default.render;
    if (typeof m === "function") return m;
  } catch (e) { /* 試 ESM */ }
  const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "chk-esm-")), "render.mjs");
  fs.copyFileSync(file, tmp);
  const m = await import(pathToFileURL(tmp).href);
  return m.render || (m.default && m.default.render) || m.default;
}

(async () => {
  const render = await load(path.resolve(process.argv[2]));
  const long = "台灣超長名稱國際貿易股份有限公司附設物流倉儲及售後服務中心南區第二營業所採購部".repeat(1);
  const call = async (s) => { try { return String(await render(s) ?? ""); } catch (e) { return "THROW:" + e.message; } };
  const out = {
    loading: await call({ loading: true, orders: [] }),
    empty: await call({ orders: [] }),
    error: await call({ error: new Error("timeout"), orders: [] }),
    normal: await call({ orders: [{ id: "A001", customer: "王小明", total: 1200 }, { id: "A002", customer: long, total: 99 }] }),
  };
  console.log(JSON.stringify(out));
})().catch((e) => { console.log(JSON.stringify({ fatal: String(e) })); });
