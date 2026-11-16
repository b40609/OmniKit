"""第 2 層 code-understanding：每組每題跑 claude -p（Sonnet 5.5 medium），存 stream-json 與最後回答。
用法：python run.py <group> <repo> <n> [<n> ...]   group = native|graphify|floorplan，repo = omnikeep|pal
"""
import json, subprocess, sys, time, shutil
from pathlib import Path

S = Path(__file__).resolve().parent
OUT = S / "out"
OUT.mkdir(exist_ok=True)
Q = {
    "omnikeep": ("C1", "在這個 repo（OmniKeep）裡，找出 app/providers/__init__.py 的 get_provider 的所有直接呼叫者（不含 tests/），"
                 "每一個寫 檔案:行號 與所在的函式；再找出經過 app/providers/__init__.py 裡呼叫 get_provider 的包裝函式、"
                 "間接受影響的檔案（不含 tests/）。最後說明：如果改了 get_provider 的 skip_kinds 參數行為，會影響哪些功能。"
                 "回答最後附一個清單區塊，格式：DIRECT: 檔案:行號（每行一個），INDIRECT_FILES: 檔案（每行一個）。"),
    "pal": ("C2", "深讀這個 repo（pal-mcp-server）的 clink 工具：從收到請求到回傳結果的完整流程——怎麼選要叫哪個 CLI、"
                  "怎麼組指令與系統提示、怎麼跑子程序、怎麼解析各家 CLI 的輸出、逾時與錯誤怎麼處理。"
                  "寫成繁體中文的研究筆記，每個論點附 檔案:行號 引用（至少 10 處），最後列出你覺得設計上的風險。"),
}


FORCE = {"graphify": "這個 repo 已經用 graphify 建好知識圖（graphify-out/）。請先用 graphify skill 或 graphify 指令"
                     "（query、explain、path）查，再視需要用其他工具核對。\n\n",
         "floorplan": "這個 repo 已經用 Floorplan 建好架構地圖（floorplan/）。請先用 Floorplan 的地圖與它的查詢腳本"
                      "（floorplan/query.mjs：overview、find、show、path）查，再視需要用其他工具核對。\n\n"}


def run(group, repo, n):
    forced = group.endswith("-forced")
    base = group.removesuffix("-forced")
    cwd = S / f"{base}-{repo}"
    qid, prompt = Q[repo]
    if forced:
        prompt = FORCE[base] + prompt
    name = f"{group}-{qid}-{n}"
    exe = shutil.which("claude")
    cmd = [exe, "-p", prompt, "--model", "claude-sonnet-5-5", "--effort", "medium",
           "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence",
           "--allowedTools", "Read", "Grep", "Glob", "Bash", "Skill",
           "--disallowedTools", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task",
           "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose"]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=1800)
    raw = r.stdout.decode("utf-8", "replace")
    (OUT / f"{name}.jsonl").write_text(raw, encoding="utf-8")
    final, tools, usage = "", [], {}
    for line in raw.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "tool_use":
                    tools.append({"name": c["name"], "input": json.dumps(c.get("input"), ensure_ascii=False)[:300]})
        if ev.get("type") == "result":
            final, usage = ev.get("result", ""), {"usage": ev.get("usage"), "cost": ev.get("total_cost_usd"),
                                                  "turns": ev.get("num_turns")}
    rec = {"name": name, "group": group, "q": qid, "seconds": round(time.time() - t0), "exit": r.returncode,
           "answer": final, "tools": tools, **usage, "stderr": r.stderr.decode("utf-8", "replace")[-1500:]}
    (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, rec["exit"], rec["seconds"], "s", len(tools), "tools", len(final), "chars")


if __name__ == "__main__":
    g, repo, *ns = sys.argv[1:]
    for n in ns:
        run(g, repo, int(n))
