"""評估 skill 各腳本共用：找到 OmniKit repo、讀名冊、輸出 JSON。"""
import json
import os
import sys
from pathlib import Path


def repo_root():
    """找 OmniKit repo：Claude Code 用資料夾連結，resolve 之後就回到 repo 裡；Codex 與 Antigravity 用的是複製品，
    看 skill 資料夾裡 agents.py 寫的 .omnikit.json；都找不到再看 OMNIKIT_HOME。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "omnikit.yaml").exists():
            return parent
    try:
        repo = Path(json.loads((here.parents[1] / ".omnikit.json").read_text(encoding="utf-8"))["repo"])
        if (repo / "data" / "omnikit.yaml").exists():
            return repo
    except (OSError, ValueError, KeyError, TypeError):
        pass
    env = os.environ.get("OMNIKIT_HOME")
    if env and (Path(env) / "data" / "omnikit.yaml").exists():
        return Path(env)
    sys.exit("找不到 OmniKit repo：請把環境變數 OMNIKIT_HOME 設成 repo 根目錄")


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "engine" / "scripts"))
import validate  # noqa: E402  共用名冊的讀取與驗證


def roster():
    errors, data = validate.check(ROOT / "data")
    if errors:
        sys.exit("名冊驗證失敗，先修正：\n" + "\n".join(f"- {e}" for e in errors))
    return data


def card_summary(tool):
    keys = ("id", "name", "status", "slots", "url", "reason", "decided_at", "trial_until", "notes")
    return {k: tool[k] for k in keys if k in tool}


def emit(doc):
    utf8_stdout()
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def utf8_stdout():
    # 自我測試會把 stdout 換成 StringIO，它沒有 reconfigure
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
