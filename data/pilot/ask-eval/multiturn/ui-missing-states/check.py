import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import json
import re
import shutil
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import css  # noqa: E402


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def check():
    ws = checklib.workspace()
    node = shutil.which("node")
    p = subprocess.run([node, str(pathlib.Path(__file__).with_name("check.js")), str(ws / "orders" / "render.js")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return [("訂單查詢頁打開就出錯", (p.stderr or p.stdout)[-300:])]
    if "fatal" in out:
        return [("訂單查詢頁打開就出錯", out["fatal"][:300])]
    probs = []
    normal = out["normal"]
    if "A001" not in normal or "王小明" not in normal or "A002" not in normal:
        probs.append(("原本查得到的訂單列表顯示不出來了", normal[:200]))
    load_t = text_of(out["loading"])
    if not load_t and not re.search(r"load|spinner|skeleton|載入", out["loading"], re.I):
        probs.append(("資料還在抓的時候，畫面還是一片空白", repr(out["loading"][:120])))
    if not re.search(r"查無|沒有|找不到|無資料|尚無|無符合|no (orders|results)|not found|empty", text_of(out["empty"]), re.I):
        probs.append(("查不到訂單的時候，畫面還是什麼提示都沒有", repr(out["empty"][:120])))
    if not re.search(r"錯誤|失敗|重試|再試|無法|稍後|error|fail|retry", text_of(out["error"]), re.I):
        probs.append(("查詢失敗（例如網路斷掉）的時候，畫面還是一片空白", repr(out["error"][:120])))
    styles = (ws / "orders" / "style.css").read_text(encoding="utf-8") if (ws / "orders" / "style.css").exists() else ""
    styles += "\n" + "\n".join(re.findall(r'style="([^"]*)"', normal))
    styles += "\n" + "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", (ws / "orders" / "index.html").read_text(encoding="utf-8"), re.S))
    wrap = re.search(r"text-overflow\s*:\s*ellipsis|overflow-wrap\s*:\s*(break-word|anywhere)|word-wrap\s*:\s*break-word"
                     r"|word-break\s*:\s*break-(all|word)|-webkit-line-clamp", styles, re.I)
    if not wrap:
        probs.append(("客戶名稱很長的時候，還是會把表格撐爆", "沒有截斷或換行的樣式"))
    return probs


checklib.run(check)
