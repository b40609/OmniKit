# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""omnikit-setup 的入口：找到 OmniKit repo，再交給 engine/scripts 的 scan.py 與 profile_new.py。

用法（路徑相對於這個 skill 的資料夾）：
  uv run scripts/setup.py scan
  uv run scripts/setup.py migrate [--yes]     舊版存在 repo 裡的 profile 搬到 repo 外（--yes：使用者已經同意）
  uv run scripts/setup.py skip                不設定、用預設：選定 default，之後開新對話不再主動帶設定
  uv run scripts/setup.py profile --answers <答案.json> [--write] [--apply] [--force]
  uv run scripts/setup.py module --draft <草稿.json> [--write] [--force]    名冊沒有的領域：寫成這台的私有模組
  uv run scripts/setup.py module --list
  uv run scripts/setup.py pool recommend [--json]                            帳號池掃描與設定建議（每格附原因）
  uv run scripts/setup.py pool render --answers <答案.json> [--write] [--force]   預覽或寫入個人 dispatch.md
"""
import json
import os
import sys
from pathlib import Path

USAGE = ("用法：uv run scripts/setup.py scan | migrate [--yes] | skip | "
         "profile --answers <答案.json> [--write] [--apply] [--force] | "
         "module --draft <草稿.json> [--write] [--force] | module --list | "
         "pool recommend [--json] | pool render --answers <答案.json> [--write] [--force]")


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
    command, rest = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else (None, [])
    if command == "scan":
        import scan
        return scan.main(rest)
    if command == "profile":
        import profile_new
        return profile_new.main(rest)
    if command == "module":
        import module_new
        return module_new.main(rest)
    if command == "migrate":
        import profiles
        return profiles.main(["--migrate", *rest])
    if command == "skip":
        import profiles
        return profiles.main(["--set", profiles.DEFAULT])
    if command == "pool":
        import pool_setup
        return pool_setup.main(rest)
    sys.exit(USAGE)


if __name__ == "__main__":
    sys.exit(main())
