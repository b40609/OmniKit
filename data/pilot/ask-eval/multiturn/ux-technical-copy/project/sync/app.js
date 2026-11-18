// 同步頁：文字都從 strings.json 來
const STRINGS = require("./strings.json");

function message(key, vars = {}) {
  let text = STRINGS[key];
  for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
  return text;
}

function onResult(res) {
  if (res.status === 200) return res.count ? message("sync_success", { count: res.count }) : message("sync_empty");
  return message(`error_${res.status}`);
}

module.exports = { message, onResult };
