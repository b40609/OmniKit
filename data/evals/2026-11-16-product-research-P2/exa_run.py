# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""直接對 Exa 的 hosted MCP（https://mcp.exa.ai/mcp）講 MCP 協定，不裝進任何 agent。

用法：
  uv run exa_run.py tools                     initialize → tools/list，存 tools.json，印工具數與定義大小
  uv run exa_run.py search "<關鍵字>" <輸出.json> ["<objective>"]   tools/call web_search_exa（numResults 用預設 10）
有環境變數 EXA_API_KEY 就用 x-api-key 標頭帶上（不印、不存）；沒有就是匿名（README：匿名可用、有限速）。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

URL = "https://mcp.exa.ai/mcp"
HERE = Path(__file__).resolve().parent


class Client:
    def __init__(self):
        self.session, self.n = None, 0

    def post(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "User-Agent": "omnikit-eval"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if os.environ.get("EXA_API_KEY"):
            headers["x-api-key"] = os.environ["EXA_API_KEY"]
        req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            self.session = resp.headers.get("Mcp-Session-Id") or self.session
            body = resp.read().decode("utf-8", "replace")
        if not body.strip():
            return None
        if body.lstrip().startswith("{"):
            return json.loads(body)
        msgs = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:") and line[5:].strip()]
        return next((m for m in msgs if "result" in m or "error" in m), msgs[-1] if msgs else None)

    def call(self, method, params=None):
        self.n += 1
        return self.post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})

    def open(self):
        init = self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "omnikit-eval", "version": "0"}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return init


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c = Client()
    c.open()
    if sys.argv[1] == "tools":
        res = c.call("tools/list")
        tools = res["result"]["tools"]
        (HERE / "tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=1), encoding="utf-8")
        compact = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
        print(f"auth={'key' if os.environ.get('EXA_API_KEY') else 'anonymous'} tools={len(tools)} "
              f"bytes={len(compact.encode('utf-8'))} chars={len(compact)}")
        for t in tools:
            one = json.dumps(t, ensure_ascii=False, separators=(",", ":"))
            print(f"- {t['name']}: {len(one)} chars")
        return 0
    if sys.argv[1] == "search":
        # objective 是必填（tools/list 實測）；第 4 個參數不給就用關鍵字本身
        query, out = sys.argv[2], Path(sys.argv[3])
        objective = sys.argv[4] if len(sys.argv) > 4 else query
        res = c.call("tools/call", {"name": "web_search_exa", "arguments": {"query": query, "objective": objective}})
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"query": query, "objective": objective,
                                   "auth": "key" if os.environ.get("EXA_API_KEY") else "anonymous",
                                   "response": res}, ensure_ascii=False, indent=1), encoding="utf-8")
        text = "".join(x.get("text", "") for x in ((res or {}).get("result") or {}).get("content", []))
        print(f"saved {out.name}: {len(text)} chars; error={(res or {}).get('error') or ((res or {}).get('result') or {}).get('isError')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
