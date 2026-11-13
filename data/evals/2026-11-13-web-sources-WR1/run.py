"""第 2 層試跑：WR1 找一手來源。兩組（builtin、firecrawl）× 3 題 × 2 次，claude -p 非互動執行。
結果存 out/<組>-<題>-<次>.json：回答、叫用了哪些工具、token、秒數。"""
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
MODEL = "claude-sonnet-5-5"
RUNS = 2

TASK = """請回答下面的問題，規則：
- 找一手來源（官方文件、官方 repo、法規、論文），每個結論都附連結，並寫出原文的位置（章節標題）或一句原文。
- 查不到一手來源的，標「待驗證」，不要寫成事實。
- 回答用繁體中文，最後列出所有用到的連結。

問題：{q}"""

QUESTIONS = {
    "Q1": "Claude Code 的 /doctor 指令有沒有檢查規則檔（CLAUDE.md）的功能？如果有，它檢查哪些項目？",
    "Q2": "OpenAI Codex（CLI 或 IDE 擴充）的官方文件，有沒有記載檢查或精簡 AGENTS.md 的功能？",
    "Q3": "GitHub Agentic Workflows（gh-aw）建立的 pull request 為什麼預設不會觸發 CI？官方建議怎麼處理？",
}

MCP = {
    "builtin": {"mcpServers": {}},
    "firecrawl": {"mcpServers": {"firecrawl": {"type": "http", "url": "https://mcp.firecrawl.dev/v2/mcp"}}},
}
ALLOWED = {
    "builtin": ["WebSearch", "WebFetch"],
    "firecrawl": ["WebSearch", "WebFetch", "mcp__firecrawl__firecrawl_scrape", "mcp__firecrawl__firecrawl_search",
                  "mcp__firecrawl__firecrawl_parse"],
}


def run(arm, qid, n):
    out = OUT / f"{arm}-{qid}-{n}.json"
    if out.exists():
        return out
    cfg = HERE / f"mcp-{arm}.json"
    cfg.write_text(json.dumps(MCP[arm]), encoding="utf-8")
    work = Path(tempfile.mkdtemp(prefix=f"l2web-{arm}-{qid}-"))
    cmd = ["claude", "-p", TASK.format(q=QUESTIONS[qid]), "--model", MODEL, "--setting-sources", "",
           "--strict-mcp-config", "--mcp-config", str(cfg), "--allowedTools", *ALLOWED[arm],
           "--tools", "WebSearch,WebFetch", "--output-format", "stream-json", "--verbose", "--no-session-persistence"]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    secs = round(time.time() - t0)
    tools, answer, usage, mcp_status, err = {}, "", {}, None, None
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            mcp_status = ev.get("mcp_servers")
        if ev.get("type") == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    tools[c["name"]] = tools.get(c["name"], 0) + 1
        if ev.get("type") == "result":
            answer = ev.get("result") or ""
            usage = ev.get("usage") or {}
            err = ev.get("subtype") if ev.get("is_error") else None
    doc = {"arm": arm, "q": qid, "n": n, "model": MODEL, "seconds": secs, "exit": p.returncode, "error": err,
           "mcp": mcp_status, "tools": tools, "usage": usage, "answer": answer,
           "stderr": p.stderr[-2000:] if p.returncode else ""}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    only = sys.argv[1:]
    jobs = [(a, q, n) for q in QUESTIONS for a in MCP for n in range(1, RUNS + 1)]
    if only:
        jobs = [j for j in jobs if f"{j[0]}-{j[1]}-{j[2]}" in only]
    with ThreadPoolExecutor(4) as ex:
        for path in ex.map(lambda j: run(*j), jobs):
            d = json.loads(path.read_text(encoding="utf-8"))
            print(f"{path.stem}: exit {d['exit']} {d['seconds']}s tools={d['tools']} mcp={d['mcp']} chars={len(d['answer'])}")
