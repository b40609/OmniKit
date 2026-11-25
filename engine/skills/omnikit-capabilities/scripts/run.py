# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""omnikit-capabilities 的入口：找到 OmniKit repo，再交給 engine/scripts/capabilities.py。

用法（路徑相對於這個 skill 的資料夾）：
  uv run scripts/run.py                  能力清點：指令（含 Git Bash 找不到的）、各 agent 的 MCP、本機端點、建議
  uv run scripts/run.py --cmd ffmpeg     多找幾個指令（可重複）
  uv run scripts/run.py --versions       加跑每個找到的指令的 --version
  uv run scripts/run.py --json
"""
import json
import os
import sys
from pathlib import Path


def repo_root():
    """找 OmniKit repo：優先看 OMNIKIT_HOME；次看連結解析（若落在 ~/.omnikit/current 則優先轉回 config.json 的開發 repo）；
    最後看 ~/.omnikit/config.json。"""
    env = os.environ.get("OMNIKIT_HOME")
    if env and (Path(env) / "data" / "omnikit.yaml").exists():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "omnikit.yaml").exists():
            if parent.name == "current" and (parent.parent / "config.json").is_file():
                try:
                    cfg_repo = Path(json.loads((parent.parent / "config.json").read_text(encoding="utf-8-sig"))["repo"])
                    if (cfg_repo / "data" / "omnikit.yaml").exists():
                        return cfg_repo
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            return parent
    state = Path(os.environ.get("OMNIKIT_STATE_DIR") or (Path.home() / ".omnikit"))
    for candidate_fn in (
        lambda: Path(json.loads((state / "config.json").read_text(encoding="utf-8-sig"))["repo"]),
        lambda: state / "current",
    ):
        try:
            cand = candidate_fn()
            if (cand / "data" / "omnikit.yaml").exists():
                return cand
        except (OSError, ValueError, KeyError, TypeError):
            pass
    sys.exit("找不到 OmniKit repo：請把環境變數 OMNIKIT_HOME 設成 repo 根目錄")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(repo_root() / "engine" / "scripts"))
    import capabilities
    return capabilities.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
