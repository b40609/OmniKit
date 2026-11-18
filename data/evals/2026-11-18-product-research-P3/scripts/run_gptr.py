"""P3 B 組：用預設設定跑 GPT Researcher 的 deep research，存報告、來源、費用與時間。

用法：python -I run_gptr.py <輸出資料夾> <run 編號>
金鑰從環境變數 OPENAI_API_KEY、TAVILY_API_KEY 讀（由呼叫端設定，這支程式不印、不存）。
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from gpt_researcher import GPTResearcher
from gpt_researcher.llm_provider.generic.base import GenericLLMProvider

# 相容修正（只動這一處，研究流程不變）：Gemini 4 透過 langchain-google-genai 4.x 回傳的
# content 是分段的 list，gpt-researcher 0.17.0 只對 minimax_anthropic 改用 .text，
# 其他供應商直接拿 .content 當字串用，會在 deep_research.py 的 response.strip() 當掉。
# 這裡讓 google_genai 也走它既有的 .text 路徑。
_orig_from_provider = GenericLLMProvider.from_provider.__func__


def _from_provider(cls, provider, *args, **kwargs):
    instance = _orig_from_provider(cls, provider, *args, **kwargs)
    if provider == "google_genai":
        instance._text_only = True
    return instance


GenericLLMProvider.from_provider = classmethod(_from_provider)

QUERY = (
    "Find as many distinct tools as possible (open-source repositories, products, "
    "VS Code extensions, coding-agent skills or MCP servers) that automatically generate "
    "architecture, structure, or dependency diagrams from a GitHub repository or codebase. "
    "For each tool give its name and a link."
)


async def main(out_dir: Path, run: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now().astimezone()
    t0 = time.monotonic()
    researcher = GPTResearcher(query=QUERY, report_type="deep", verbose=False)
    await researcher.conduct_research()
    report = await researcher.write_report()
    elapsed = time.monotonic() - t0
    meta = {
        "arm": "gpt-researcher",
        "version": "0.17.0",
        "run": run,
        "query": QUERY,
        "started": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "total_cost_usd_reported": researcher.get_costs(),
        "config_env": {k: os.environ.get(k) for k in ("FAST_LLM", "SMART_LLM", "STRATEGIC_LLM", "EMBEDDING", "LLM_KWARGS")},
        "source_urls": researcher.get_source_urls(),
    }
    (out_dir / f"gptr-{run}.md").write_text(report, encoding="utf-8")
    (out_dir / f"gptr-{run}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run", "elapsed_seconds", "total_cost_usd_reported")}))
    print(f"sources={len(meta['source_urls'])} report_chars={len(report)}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2]))
