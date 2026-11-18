import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import json
import re

KEYS = ["title", "sync_button", "sync_running", "sync_success", "sync_empty", "error_422", "error_504", "error_401"]
BANNED = re.compile(r"payload|field_|status_code|ERR_|execute|sync|rows? affected|\bnull\b|\b(422|504|401)\b|http|"
                    r"token|unauthori[sz]ed|gateway|timeout|exception|invalid|request", re.I)
ACTION = re.compile(r"請|再試|重新|聯絡|確認|檢查|選|登入|稍後|過幾分鐘")


def check():
    ws = checklib.workspace()
    try:
        s = json.loads((ws / "sync" / "strings.json").read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        return [("同步頁打開就出錯，字都不見了", f"strings.json 讀不到：{e}")]
    p = []
    missing = [k for k in KEYS if not isinstance(s.get(k), str) or not s[k].strip()]
    if missing:
        return [("同步頁有些地方的字不見了、變成空白", f"缺 {missing}")]
    for k in KEYS:
        if BANNED.search(s[k]) or not re.search(r"[\u4e00-\u9fff]", s[k]):
            p.append((f"畫面上還是有客戶看不懂的英文或代碼：「{s[k]}」", f"{k} = {s[k]!r}"))
    for k in ("error_422", "error_504", "error_401"):
        if not ACTION.search(s[k]):
            p.append((f"錯誤訊息「{s[k]}」還是沒告訴客戶接下來要怎麼做", f"{k} 沒有下一步"))
    if "狀態" not in s["error_422"]:
        p.append(("客戶看到資料沒過驗證的訊息，還是不知道要改哪個欄位", f"error_422 = {s['error_422']!r}"))
    if "登入" not in s["error_401"]:
        p.append(("登入過期時的訊息還是沒講要重新登入", f"error_401 = {s['error_401']!r}"))
    if "{count}" not in s["sync_success"]:
        p.append(("同步成功之後看不到同步了幾筆", "sync_success 少了 {count}"))
    return p


checklib.run(check)
