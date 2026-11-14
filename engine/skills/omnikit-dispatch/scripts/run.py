# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""omnikit-dispatch 的入口：找到 OmniKit repo，再交給 engine/scripts/dispatch.py。

用法（路徑相對於這個 skill 的資料夾）：
  uv run scripts/run.py show                 套上這台 profile 之後的分派表，開頭附本週 Claude 用量
  uv run scripts/run.py log --task ... --class ... --thinking ... --verdict ...   記一行委派紀錄
  uv run scripts/run.py stats                一次通過率與 Sonnet 試行的判定
  uv run scripts/run.py usage                本週 Claude 用量（狀態列快照）
"""
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(repo_root() / "engine" / "scripts"))
    import dispatch
    return dispatch.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
