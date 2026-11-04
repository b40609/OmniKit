# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""由名冊產生兩邊的 plugin marketplace 清單與槽位看板。

- .claude-plugin/marketplace.json、.agents/plugins/marketplace.json：commit 進 repo，不要手改
- 看板：單一 HTML，寫到 --site 指定的目錄（預設 _site/，不進 repo），由 GitHub Actions 部署

只有狀態是 default、而且卡片寫了該 agent 的 plugin 來源的工具，才會進 marketplace。
名冊驗證不過就不產生。

用法：uv run engine/scripts/build.py [--site <目錄>] [--marketplace-only] [--check]
  --marketplace-only  只產生 marketplace 清單（git hook 用）
  --check             只檢查 marketplace 清單是不是最新，不寫檔（CI 用）
"""
import argparse
import html
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import validate

ROOT = validate.ROOT
SITE_SRC = ROOT / "engine" / "site"
MARKETPLACES = {
    "claude": ROOT / ".claude-plugin" / "marketplace.json",
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
}

STATUS = {"default": "預設", "trial": "試用", "pending": "待評估", "rejected": "拒絕", "retired": "退役"}
FOCUS = {"active": "主動找", "watch": "有新工具才看", "frozen": "凍結"}
KIND = {
    "skill": "skill", "plugin": "plugin", "mcp": "MCP", "cli": "CLI", "app": "獨立程式",
    "service": "線上服務", "library": "程式庫", "native": "原生功能", "collection": "skill 合集", "rules": "規則包",
}
AGENT = {"claude": "Claude Code", "codex": "Codex"}
# 卡片在槽位裡的排列：先看已經決定的，待評估放最後
ORDER = {"default": 0, "trial": 1, "rejected": 2, "retired": 3, "pending": 4}
# 內嵌的 favicon，省掉一個請求，也不會 404
FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='8' fill='%231d5c47'/%3E"
    "%3Ccircle cx='16' cy='16' r='7' fill='none' stroke='white' stroke-width='3'/%3E%3C/svg%3E"
)


def esc(text):
    return html.escape(str(text), quote=True)


def plugin_name(tool):
    return tool["plugin"].get("name", tool["id"])


def default_plugins(roster, agent):
    return [t for t in roster["tools"].values() if t["status"] == "default" and agent in t.get("plugin", {})]


def slot_label(roster, tool):
    names = {s["id"]: s["name"] for s in roster["slots"]}
    return "、".join(names[s] for s in tool["slots"])


def marketplaces(roster):
    cfg = roster["config"]
    claude = {
        "name": cfg["marketplace"],
        "description": cfg["tagline"],
        "owner": {"name": cfg["owner"], "url": f"https://github.com/{cfg['owner']}"},
        "plugins": [],
    }
    for t in default_plugins(roster, "claude"):
        entry = {
            "name": plugin_name(t),
            "source": t["plugin"]["claude"],
            "description": f"{t['name']}：OmniKit「{slot_label(roster, t)}」槽位的預設。",
            "category": slot_label(roster, t),
        }
        if t.get("url"):
            entry["homepage"] = t["url"]
        claude["plugins"].append(entry)

    codex = {
        "name": cfg["marketplace"],
        "interface": {"displayName": f"OmniKit · {cfg['owner']}"},
        "plugins": [
            {
                "name": plugin_name(t),
                "source": t["plugin"]["codex"],
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": slot_label(roster, t),
            }
            for t in default_plugins(roster, "codex")
        ],
    }
    return {"claude": claude, "codex": codex}


def dump(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ---- 看板 ----

def install_lines(tool, cfg):
    if tool["status"] != "default" or not tool.get("plugin"):
        return ""
    name = f"{plugin_name(tool)}@{cfg['marketplace']}"
    lines = []
    if "claude" in tool["plugin"]:
        lines.append(f"<span>Claude Code</span><code>/plugin install {esc(name)}</code>")
    if "codex" in tool["plugin"]:
        lines.append(f"<span>Codex</span><code>codex plugin add {esc(name)}</code>")
    return f'<details><summary>安裝指令</summary><div class="install">{"".join(lines)}</div></details>'


def card(tool, roster):
    cfg = roster["config"]
    status = tool["status"]
    text = [tool["id"], tool["name"], KIND.get(tool.get("kind"), ""), tool.get("reason", ""), tool.get("notes", ""),
            *tool.get("sources", []), slot_label(roster, tool) if tool["slots"] else ""]
    title = f'<a href="{esc(tool["url"])}">{esc(tool["name"])}</a>' if tool.get("url") else esc(tool["name"])
    meta = " · ".join(x for x in [KIND.get(tool.get("kind"), ""), "、".join(AGENT[a] for a in tool.get("works_with", []))] if x)
    parts = [
        f'<article class="card st-{status}" data-id="{tool["id"]}" data-status="{status}" data-search="{esc(" ".join(text).lower())}">',
        f'<div class="card-top"><h3>{title}</h3><span class="badge st-{status}">{STATUS[status]}</span></div>',
    ]
    if meta:
        parts.append(f'<p class="card-meta">{esc(meta)}</p>')
    if tool.get("reason"):
        parts.append(f'<p class="reason"><time datetime="{tool["decided_at"]}">{tool["decided_at"]}</time>{esc(tool["reason"])}</p>')
    if tool.get("trial_until"):
        until = tool["trial_until"]
        parts.append(f'<p class="trial">試用到 <time datetime="{until}">{until}</time>（<span class="left" data-until="{until}">到期日</span>）</p>')
    parts.append(install_lines(tool, cfg))
    if tool.get("notes"):
        parts.append(f'<details><summary>備註</summary><p>{esc(tool["notes"])}</p></details>')
    source_text = "來源：" + "、".join(tool["sources"]) if tool.get("sources") else ""
    parts.append(
        f'<div class="card-foot"><span>{esc(source_text)}</span>'
        f'<a href="https://github.com/{cfg["repo"]}/blob/HEAD/data/tools/{tool["id"]}.yaml">原始資料</a></div>'
    )
    parts.append("</article>")
    return "".join(parts)


def ordered(tools):
    return sorted(tools, key=lambda t: (ORDER[t["status"]], t["name"].lower()))


def slot_section(slot, tools, roster):
    search = " ".join([slot["id"], slot["name"], *(s["text"] for s in slot["scenarios"])]).lower()
    scenarios = "".join(f'<li><b>{esc(s["id"])}</b><span>{esc(s["text"])}</span></li>' for s in slot["scenarios"])
    cards = "".join(card(t, roster) for t in ordered(tools))
    return (
        f'<section class="slot" id="slot-{slot["id"]}" data-focus="{slot["focus"]}" data-search="{esc(search)}">'
        f'<header class="slot-head"><h2>{esc(slot["name"])}</h2>'
        f'<span class="focus f-{slot["focus"]}">{FOCUS[slot["focus"]]}</span>'
        f'<code class="slot-id">{slot["id"]}</code></header>'
        f'<ul class="scenarios">{scenarios}</ul><div class="cards">{cards}</div></section>'
    )


def unassigned_section(tools, roster):
    if not tools:
        return ""
    cards = "".join(card(t, roster) for t in ordered(tools))
    return (
        '<section class="slot" id="unassigned" data-search="零件庫 未分配">'
        '<header class="slot-head"><h2>零件庫與未分配</h2></header>'
        '<p class="slot-note">還沒放進槽位的工具：大型 skill 合集當零件庫，從裡面挑單一 skill 放進槽位；另外是還不確定用途的。</p>'
        f'<div class="cards">{cards}</div></section>'
    )


def highlights(roster):
    tools = roster["tools"].values()
    trials = sorted((t for t in tools if t["status"] == "trial"), key=lambda t: t["trial_until"])
    if trials:
        items = "".join(
            f'<li><time datetime="{t["trial_until"]}">{t["trial_until"]}</time>'
            f'<span class="what">{esc(t["name"])}</span>'
            f'<span class="why">{esc(slot_label(roster, t))} · <span class="left" data-until="{t["trial_until"]}">到期日</span></span></li>'
            for t in trials
        )
        trial_html = f'<ul class="list">{items}</ul>'
    else:
        trial_html = '<p class="empty">目前沒有試用中的工具。</p>'

    # 原生功能當基準的預設不算真正的決定，不放進時間線
    decided = sorted(
        (t for t in tools if t.get("decided_at") and t.get("kind") != "native"),
        key=lambda t: (t["decided_at"], t["name"].lower()),
        reverse=True,
    )[:6]
    items = "".join(
        f'<li><time datetime="{t["decided_at"]}">{t["decided_at"]}</time>'
        f'<span class="what">{esc(t["name"])}<span class="badge st-{t["status"]}">{STATUS[t["status"]]}</span></span>'
        f'<span class="why">{esc(t["reason"])}</span></li>'
        for t in decided
    )
    return (
        '<section class="highlights" aria-label="重點"><div class="stack">'
        f'<div class="panel"><h2>試用中</h2>{trial_html}</div>'
        f'{install_panel(roster)}{eval_panel(roster["config"])}</div>'
        f'<div class="panel"><h2>最近的決定</h2><ul class="list">{items}</ul></div></section>'
    )


def install_panel(roster):
    cfg = roster["config"]
    agents_of = {}
    for agent in MARKETPLACES:
        for t in default_plugins(roster, agent):
            agents_of.setdefault(plugin_name(t), []).append(AGENT[agent])
    if not agents_of:
        return ""
    plugins = "、".join(f"{esc(name)}（{'、'.join(agents)}）" for name, agents in sorted(agents_of.items()))
    return (
        '<div class="panel"><h2>安裝預設的 plugin</h2>'
        '<p class="panel-note">先把 OmniKit 加成 marketplace，再到各工具卡展開「安裝指令」。</p>'
        '<dl class="steps">'
        f'<dt>Claude Code</dt><dd><code>/plugin marketplace add {esc(cfg["repo"])}</code></dd>'
        f'<dt>Codex</dt><dd><code>codex plugin marketplace add {esc(cfg["repo"])}</code></dd></dl>'
        f'<p class="panel-note">目前收錄：{plugins}</p></div>'
    )


def eval_panel(cfg):
    items = []
    for path in sorted((ROOT / "data" / "evals").glob("*.md"), reverse=True):
        lines = path.read_text(encoding="utf-8").splitlines()
        title = next((line[2:].strip() for line in lines if line.startswith("# ")), path.stem)
        url = f"https://github.com/{cfg['repo']}/blob/HEAD/data/evals/{path.name}"
        items.append(f'<li><a href="{esc(url)}">{esc(title)}</a></li>')
    if not items:
        return ""
    return f'<div class="panel evals"><h2>評估紀錄</h2><ul class="list">{"".join(items)}</ul></div>'


def toolbar(roster):
    counts = Counter(t["status"] for t in roster["tools"].values())
    focus_counts = Counter(s["focus"] for s in roster["slots"])
    status_chips = "".join(
        f'<button type="button" class="chip st-{k}" data-value="{k}" aria-pressed="true">'
        f'<span class="dot"></span>{v}<span class="n">{counts.get(k, 0)}</span></button>'
        for k, v in STATUS.items()
    )
    focus_chips = "".join(
        f'<button type="button" class="chip f-{k}" data-value="{k}" aria-pressed="true">'
        f'<span class="dot"></span>{v}<span class="n">{focus_counts.get(k, 0)}</span></button>'
        for k, v in FOCUS.items()
    )
    return (
        '<div class="toolbar"><div class="wrap">'
        '<input id="q" class="search" type="search" placeholder="搜尋工具、理由、備註（按 / 開始）" aria-label="搜尋工具">'
        f'<div class="chips" role="group" aria-label="依狀態篩選" data-group="status">{status_chips}</div>'
        f'<div class="chips" role="group" aria-label="依槽位重點篩選" data-group="focus">{focus_chips}</div>'
        '<p class="count" id="count" aria-live="polite"></p></div></div>'
    )


def build_info():
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
        sha = result.stdout.strip()
    return sha[:7], datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def page(roster):
    cfg = roster["config"]
    tools = roster["tools"].values()
    counts = Counter(t["status"] for t in tools)
    stats = "".join(
        f'<li class="st-{k}"><b>{counts.get(k, 0)}</b>{v}</li>' for k, v in STATUS.items()
    )
    sections = "".join(
        slot_section(slot, [t for t in tools if slot["id"] in t["slots"]], roster) for slot in roster["slots"]
    )
    sections += unassigned_section([t for t in tools if not t["slots"]], roster)
    sha, built = build_info()
    repo_url = f"https://github.com/{cfg['repo']}"
    css = (SITE_SRC / "style.css").read_text(encoding="utf-8")
    js = (SITE_SRC / "app.js").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(cfg["title"])}</title>
<meta name="description" content="{esc(cfg["tagline"])}">
<link rel="icon" href="{FAVICON}">
<style>
{css}</style>
</head>
<body>
<header class="masthead"><div class="wrap">
<h1>{esc(cfg["title"])}</h1>
<p class="tagline">{esc(cfg["tagline"])}</p>
<ul class="stats"><li><b>{len(roster["slots"])}</b>個槽位</li><li><b>{len(tools)}</b>張工具卡</li>{stats}</ul>
<p class="meta">由 <a href="{repo_url}">{esc(cfg["repo"])}</a> 的名冊自動產生 · 更新於 {built}{f"（{sha}）" if sha else ""}</p>
</div></header>
<main>
<div class="wrap">{highlights(roster)}</div>
{toolbar(roster)}
<div class="wrap">{sections}<p class="empty-state" id="empty" hidden>沒有符合的工具。換個關鍵字，或把上面的篩選打開。</p></div>
</main>
<footer><div class="wrap">
<p>每個槽位只留一個預設；新工具用真實情境評估，換或不換都把理由寫回名冊。</p>
<p>想用同一套方法管理自己的設定：fork <a href="{repo_url}">{esc(cfg["repo"])}</a>，換掉 data/ 裡的資料即可。</p>
</div></footer>
<script>
{js}</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="產生 marketplace 清單與槽位看板")
    parser.add_argument("--site", type=Path, default=ROOT / "_site", help="看板輸出目錄，預設 _site/")
    parser.add_argument("--marketplace-only", action="store_true", help="只產生 marketplace 清單")
    parser.add_argument("--check", action="store_true", help="只檢查 marketplace 清單是不是最新")
    args = parser.parse_args()

    errors, roster = validate.check(ROOT / "data")
    if errors:
        print(f"名冊驗證失敗，共 {len(errors)} 個問題，不產生：")
        for e in errors:
            print(f"- {e}")
        return 1

    outputs = {agent: dump(doc) for agent, doc in marketplaces(roster).items()}
    if args.check:
        stale = [
            validate.show(path) for agent, path in MARKETPLACES.items()
            if not path.exists() or path.read_text(encoding="utf-8") != outputs[agent]
        ]
        if stale:
            print("marketplace 清單不是最新，請執行 uv run engine/scripts/build.py：" + "、".join(stale))
            return 1
        print("marketplace 清單是最新的。")
        return 0

    for agent, path in MARKETPLACES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[agent], encoding="utf-8", newline="\n")
    summary = "、".join(f"{AGENT[a]} {len(json.loads(outputs[a])['plugins'])} 個" for a in MARKETPLACES)
    print(f"已產生 marketplace 清單：{summary} plugin。")

    if not args.marketplace_only:
        args.site.mkdir(parents=True, exist_ok=True)
        (args.site / "index.html").write_text(page(roster), encoding="utf-8", newline="\n")
        # Pages 不必用 Jekyll 處理
        (args.site / ".nojekyll").write_text("", encoding="utf-8")
        print(f"已產生看板：{validate.show(args.site / 'index.html')}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
