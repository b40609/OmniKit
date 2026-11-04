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
  uv run scripts/setup.py profile --answers <答案.json> [--write] [--apply] [--force]
"""
import os
import sys
from pathlib import Path

USAGE = "用法：uv run scripts/setup.py scan | profile --answers <答案.json> [--write] [--apply] [--force]"


def repo_root():
    """skill 經 skillshare 以 junction 連到各 agent，resolve 之後就回到 repo 裡；找不到再看 OMNIKIT_HOME。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "omnikit.yaml").exists():
            return parent
    env = os.environ.get("OMNIKIT_HOME")
    if env and (Path(env) / "data" / "omnikit.yaml").exists():
        return Path(env)
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
    sys.exit(USAGE)


if __name__ == "__main__":
    sys.exit(main())
