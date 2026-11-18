"""P3 C 組：local-deep-research 2.0.1 的 generate_report，存報告、來源與時間。

用法：python -I -X utf8 run_ldr.py <輸出資料夾> <run 編號>
金鑰由呼叫端放在 LDR_LLM_GOOGLE_API_KEY、LDR_SEARCH_ENGINE_WEB_TAVILY_API_KEY（這支程式不印、不存）。

跟預設不同的只有：
- llm.provider = google、llm.model = gemini-4-hydrogen（預設是 ollama，這台沒有本機模型；跟 A、B 組同一個模型）
- search.tool = tavily（預設是 searxng，要自己架伺服器，Windows 上要 Docker）
- search.engine.web.searxng.agent_enabled = False（沒有伺服器，免得 agent 一直挑到它）
其餘（langgraph-agent 策略、iterations、agent 可用的引擎）照預設。
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from local_deep_research.api import generate_report

QUERY = (
    "Find as many distinct tools as possible (open-source repositories, products, "
    "VS Code extensions, coding-agent skills or MCP servers) that automatically generate "
    "architecture, structure, or dependency diagrams from a GitHub repository or codebase. "
    "For each tool give its name and a link."
)

PROVIDER = os.environ.get("P3_LDR_PROVIDER", "google")
OVERRIDES = {
    "llm.provider": PROVIDER,
    "llm.model": os.environ.get("P3_LDR_MODEL", "gemini-4-hydrogen"),
    "search.tool": "tavily",
    "search.engine.web.searxng.agent_enabled": False,
}


def main(out_dir: Path, run: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone()
    t0 = time.monotonic()
    result = generate_report(QUERY, provider=PROVIDER, settings_override=OVERRIDES)
    elapsed = time.monotonic() - t0
    content = result.get("content") or ""
    meta = {
        "arm": "local-deep-research",
        "version": "2.0.1",
        "run": run,
        "query": QUERY,
        "overrides": OVERRIDES,
        "started": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "result_keys": sorted(result.keys()),
        "metadata": result.get("metadata"),
    }
    (out_dir / f"ldr-{run}.md").write_text(content, encoding="utf-8")
    (out_dir / f"ldr-{run}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"run": run, "elapsed_seconds": meta["elapsed_seconds"], "chars": len(content)}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
