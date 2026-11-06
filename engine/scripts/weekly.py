# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""個人週報（FR-37）：每位同事每週一份。跟訪談第 5 題（要不要參與評估）無關，裝了 OmniKit 就有（FR-4）：
omnikit-weekly 這個 skill 不在 profiles.OPTIONAL_SKILLS 裡，第 5 題選「先不要」也照裝。

內容依 PRD 的順序有六個區塊。查得到的照實列；還查不到的標「未知」並寫出原因，不當成「沒有」：
1. 沒在用的工具：usage.py 讀三個 agent 的本機紀錄（預設 30 天沒用到；裝不到 30 天的先不判斷）。
2. 上游有新版的工具：要等工具包 lock（FR-14）與「檢查更新」（FR-36），目前未知。
3. 有更好的選擇（E3、E4）：要等工具卡的證據等級（FR-28）與通知規則（FR-16），目前未知。
4. 設定被手動改過的項目：doctor.py 的寫入檢查（規則受管區塊、skills、MCP、權限與提醒 hook），只讀檔案，
   不跑 agent 的指令。
5. 主動建議的接受率：要等主動建議開始記錄（FR-18 到 FR-21），目前未知。
6. 成本（FR-40 到 FR-44，cost.py）：新裝的工具與開頭成本、成本高又沒在用的（不用等 30 天）、背景與非互動的
   模型用量、對話開頭的大小與跟上週比、名冊比對。存檔時一併記下這次看到的清單與這週的開頭大小，下週拿來比。

不連網、不上傳；只輸出名稱、次數與日期，不輸出對話內容。完整內容存在
%LOCALAPPDATA%\\omnikit\\weekly\\<年>-W<週>.md，同一週重跑就換成最新的。
維護者評估工具用的「每週彙整」（評估額度、建議評估的槽位、評估漏斗）在 omnikit-eval 裡，是另一份。
每週第一個 session 開頭的一行提示還沒做（要 SessionStart hook，跟 FR-39 一起做）。

用法：
  uv run engine/scripts/weekly.py [--days 30] [--today YYYY-MM-DD] [--no-save]
  uv run engine/scripts/weekly.py --selftest
"""
import argparse
import json
import socket
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
import cost  # noqa: E402
import doctor  # noqa: E402
import profiles  # noqa: E402
import usage  # noqa: E402
import validate  # noqa: E402

SKILL = "omnikit-weekly"
SECTIONS = ("沒在用的工具", "上游有新版的工具", "有更好的選擇（E3、E4）", "設定被手動改過的項目", "主動建議的接受率", "成本")
# 還沒有資料來源的區塊：原因與之後由哪條需求補上
PENDING = {
    "上游有新版的工具": "還沒有工具包 lock（FR-14）記下每個工具裝的版本，也還沒有「檢查更新」（FR-36）",
    "有更好的選擇（E3、E4）": "工具卡還沒有證據等級（FR-28），通知規則（FR-16）也還沒做",
    "主動建議的接受率": "主動建議還沒開始記錄（FR-18 到 FR-21）",
}


def week_of(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def unused_section(result):
    """沒在用的工具；result 是 usage.collect 的結果，讀不到時是例外。回傳（行, 沒在用的數量；None 表示未知）。"""
    if isinstance(result, Exception):
        return [f"- 未知：讀不到使用紀錄（{result}）"], None
    lines = usage.report(result, limit=15)
    count = sum(1 for i in result["items"] if i["status"] == "unused")
    if count:
        lines.append("- 要停用或移除就跟 agent 說；移除是刪除，會先問你。說「先留著」就不再追問，下週還會列出來")
    return lines, count


def drift_section(rows):
    """設定被手動改過的項目；rows 是 doctor.collect(lists=False) 的結果。回傳（行, 被改過的數量；None 表示未知）。"""
    if rows and rows[0]["area"] == "記錄" and rows[0]["status"] == doctor.FAIL:
        return [f"- 未知：{rows[0]['detail']}"], None
    rows = [r for r in rows if r["area"] != "記錄"]
    bad = [r for r in rows if r["status"] == doctor.FAIL]
    unknown = [r for r in rows if r["status"] == doctor.UNKNOWN]
    lines = [f"- 檢查了 {len(rows)} 項：跟 OmniKit 寫入時一樣 {len(rows) - len(bad) - len(unknown)} 項、"
             f"被改過或不見了 {len(bad)} 項、查不到 {len(unknown)} 項"]
    for r in bad + unknown:
        who = f"{r['agent']}／" if r["agent"] else ""
        state = "被改過或不見了" if r["status"] == doctor.FAIL else "查不到"
        lines.append(f"  - {state}：{r['area']} {who}{r['item']}" + (f"（{r['detail']}）" if r["detail"] else ""))
    if not bad and not unknown:
        lines.append("- 沒有被手動改過的項目")
    return lines, len(bad)


def roster_tools(env):
    """名冊的工具卡（給成本的名冊比對）；名冊讀不到或驗證失敗回 None。"""
    try:
        errors, roster = validate.check(env.data, state=env.state)
    except Exception:  # 名冊壞了不影響週報的其他區塊
        return None
    return None if errors else roster["tools"]


def cost_section(result):
    """成本；result 是 cost.measure 的結果，量不到時是例外。回傳（行, 摘要）。"""
    if isinstance(result, Exception):
        return [f"- 未知：量不到（{result}）"], "成本：未知"
    return cost.report(result), cost.summary(result)


def build(env, record_path, today, days=30, collect_usage=None, collect_cost=None, persist=False):
    """組出週報（Markdown 的每一行）。只讀本機檔案，不連網。persist：存下成本監測要比對的清單與開頭大小。"""
    try:
        result = collect_usage() if collect_usage else usage.collect(env.home, days=days)
    except Exception as e:  # 使用紀錄讀不到，不影響其他區塊
        result = e
    try:
        costs = collect_cost() if collect_cost else cost.measure(env.home, env.state, roster=roster_tools(env), persist=persist)
    except Exception as e:  # 成本量不到，不影響其他區塊
        costs = e
    unused_lines, unused = unused_section(result)
    drift_lines, drift = drift_section(doctor.collect(env, record_path, lists=False))
    cost_lines, cost_summary = cost_section(costs)
    known = lambda n, label: f"{label} {n} 項" if n is not None else f"{label}：未知"  # noqa: E731
    lines = [f"# OmniKit 本週週報（{week_of(today)}，{today}）", "",
             f"摘要：{known(unused, '沒在用的工具')}；{known(drift, '設定被手動改過')}；{cost_summary}；"
             "上游新版、更好的選擇、主動建議接受率：還沒有資料（未知）"]
    bodies = {"沒在用的工具": unused_lines, "設定被手動改過的項目": drift_lines, "成本": cost_lines}
    for number, title in enumerate(SECTIONS, 1):
        body = bodies.get(title) or [f"- 未知：{PENDING[title]}。不是沒有，是還查不到"]
        lines += ["", f"## {number}. {title}", "", *body]
    lines += ["", "只讀這台的紀錄與設定，不連網、不上傳；只列名稱、次數與日期，不含對話內容。"]
    return lines


def save(lines, state, today):
    path = state / "weekly" / f"{week_of(today)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        home, repo, state = tmp / "home", tmp / "repo", tmp / "state"

        def put(path, content):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        put(repo / "data" / "rules" / "baseline.md", "# 底線\n不碰金鑰\n")
        put(repo / "data" / "profiles" / "default" / "AGENTS.md", "# default\n")
        for name in ("omnikit-setup", "omnikit-eval", SKILL):
            put(repo / "engine" / "skills" / name / "SKILL.md", f"---\nname: {name}\n---\n")
        put(repo / "data" / "mcp" / "servers.yaml", "servers:\n  devtools:\n    command: cmd\n    args: [/c, node, x.js]\n"
                                                    "    targets: [claude, codex, antigravity]\n")
        for folder in (".claude", ".codex", ".gemini/config"):
            (home / folder).mkdir(parents=True)
        env = agents.Env(home=home, repo=repo, state=state, skillshare=tmp / "appdata" / "skillshare", which=lambda _: None)
        record = state / "install-record.json"
        today = date(2026, 11, 5)
        fake = {"days": 30, "since": "2026-10-06", "until": "2026-11-05",
                "sources": {"claude-code": 3, "codex": 1, "antigravity": 0},
                "items": [{"kind": "skill", "name": "old-helper", "where": "~/.claude/skills", "agents": ["claude-code"],
                           "status": "unused", "conversations": 0, "installed_days": 90, "last_used": None},
                          {"kind": "skill", "name": "busy", "where": "~/.agents/skills", "agents": ["codex"],
                           "status": "used", "conversations": 5, "installed_days": 40, "last_used": "2026-11-04"}]}

        lines = build(env, record, today, collect_usage=lambda: fake)
        text = "\n".join(lines)
        check("還沒接上 OmniKit：設定那一區標未知，其他照常產生",
              "## 4. 設定被手動改過的項目\n\n- 未知：" in text and "old-helper" in text)

        # 訪談第 5 題選「先不要」（evaluate_tools 是 false）：不裝 omnikit-eval，週報照樣裝（FR-4、FR-37）
        put(state / "profiles" / "bob" / "AGENTS.md", "# bob\n")
        put(state / "profiles" / "bob" / "answers.json", json.dumps({"name": "bob", "evaluate_tools": False}))
        agents.connect(env, profile="bob", agents=["claude-code", "codex", "antigravity"])
        installed = {key: sorted(names) for key, names in agents.load_record(env)["skills"].items()}
        check("第 5 題選「先不要」：不裝 omnikit-eval，個人週報兩邊都照裝",
              SKILL not in profiles.OPTIONAL_SKILLS
              and installed == {"claude-code": sorted(["omnikit-setup", SKILL]), "shared": sorted(["omnikit-setup", SKILL])})

        def offline(*_args, **_kwargs):
            raise RuntimeError("週報不應該連網")

        real_connect, real_create = socket.socket.connect, socket.create_connection
        socket.socket.connect, socket.create_connection = offline, offline
        try:
            lines = build(env, record, today, collect_usage=lambda: fake)
        finally:
            socket.socket.connect, socket.create_connection = real_connect, real_create
        text = "\n".join(lines)
        check("不連網也能產生（連網的呼叫都換成會失敗的）", lines[0] == "# OmniKit 本週週報（2026-W45，2026-11-05）")
        heads = [line for line in lines if line.startswith("## ")]
        check("六個區塊照 PRD 的順序（第 6 個是成本）", heads == [f"## {n}. {t}" for n, t in enumerate(SECTIONS, 1)])
        part6 = text[text.index("## 6. 成本"):]
        check("成本區塊：新裝的工具、成本高又沒在用的、背景用量、對話開頭的大小、名冊比對都在（FR-40 到 FR-44）",
              all(h in part6 for h in ("### 新裝的工具", "### 成本高又沒在用的", "### 背景與非互動", "### 對話開頭的大小",
                                       "### 名冊比對")))
        check("摘要也帶成本", "新裝 " in lines[2] and "成本高又沒在用" in lines[2])
        check("沒在用的工具：列出名稱，有用到的不列成沒在用",
              "30 天沒用到：1 個" in text and "old-helper（Claude Code，~/.claude/skills" in text and "會先問你" in text)
        check("剛接上：設定都跟寫入時一樣", "被改過或不見了 0 項" in text and "沒有被手動改過的項目" in text)
        check("還查不到的區塊標未知並寫原因，不當成沒有",
              all(f"## {n}. {t}\n\n- 未知：{PENDING[t]}" in text for n, t in enumerate(SECTIONS, 1) if t in PENDING))
        check("摘要一行講完", lines[2].startswith("摘要：沒在用的工具 1 項；設定被手動改過 0 項；"))

        claude_md = home / ".claude" / "CLAUDE.md"
        put(claude_md, claude_md.read_text(encoding="utf-8").replace("@", "@C:/手改/", 1))
        agents.remove_owned(home / ".agents" / "skills" / "omnikit-setup")
        text = "\n".join(build(env, record, today, collect_usage=lambda: fake))
        check("手改了規則區塊、刪了 skill：列在設定被改過，摘要也算進去",
              "被改過或不見了：規則 Claude Code／CLAUDE.md" in text and "被改過或不見了：skills" in text
              and "omnikit-setup" in text and "設定被手動改過 2 項" in text)

        def broken():
            raise OSError("紀錄檔被鎖住")

        text = "\n".join(build(env, record, today, collect_usage=broken))
        check("使用紀錄讀不到：那一區標未知，其他照常", "- 未知：讀不到使用紀錄（紀錄檔被鎖住）" in text
              and "沒在用的工具：未知" in text and "## 5. 主動建議的接受率" in text)
        text = "\n".join(build(env, record, today, collect_usage=lambda: fake, collect_cost=broken))
        check("成本量不到：那一區標未知，其他照常", "## 6. 成本\n\n- 未知：量不到（紀錄檔被鎖住）" in text and "old-helper" in text)

        check("沒存檔（--no-save）：不記成本監測要比對的清單", not (state / "weekly" / "inventory.json").exists())
        build(env, record, today, collect_usage=lambda: fake, persist=True)
        check("存檔時：記下這次看到的清單與這週的開頭大小，下週拿來比",
              (state / "weekly" / "inventory.json").exists() and (state / "weekly" / "startup.json").exists())

        path = save(lines, state, today)
        check("完整內容存在 %LOCALAPPDATA%\\omnikit\\weekly\\<年>-W<週>.md",
              path == state / "weekly" / "2026-W45.md" and path.read_text(encoding="utf-8").startswith("# OmniKit 本週週報"))
        save(["# OmniKit 本週週報（重跑）"], state, date(2026, 11, 8))
        check("同一週重跑：換成最新的，不另外多一份", (state / "weekly" / "2026-W45.md").read_text(encoding="utf-8")
              == "# OmniKit 本週週報（重跑）\n" and len(list((state / "weekly").glob("*.md"))) == 1)

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 個人週報")
    parser.add_argument("--days", type=int, default=30, help="多少天沒用到算「沒在用」，預設 30")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--no-save", action="store_true", help="只印出來，不存到 %%LOCALAPPDATA%%\\omnikit\\weekly")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    env = agents.real_env()
    lines = build(env, env.state / "install-record.json", args.today, args.days, persist=not args.no_save)
    if not args.no_save:
        lines += ["", f"完整內容存在：{save(lines, env.state, args.today)}"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
