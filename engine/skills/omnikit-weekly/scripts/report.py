# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""omnikit-weekly 的入口：找到 OmniKit repo，再交給 engine/scripts/weekly.py 產生個人週報，
或交給 engine/scripts/advise.py 給建議（裝、拿掉、用內建的就好）。兩者讀的是同一份本機紀錄。

用法（路徑相對於這個 skill 的資料夾）：
  uv run scripts/report.py [--days 30] [--no-save]                      個人週報
  uv run scripts/report.py advise [--agent claude|codex]                建議的事實與候選（JSON）
  uv run scripts/report.py advise --picks <檔> [--no-save]              驗證挑選，寫出建議
  uv run scripts/report.py pool find                                    名冊沒有答案的槽位，找名冊外的候選（會連網）
  uv run scripts/report.py pool add --slot <id> --file <檔>             記下 agent 上網找到的候選
  uv run scripts/report.py feedback status | consent yes|no             回流：看狀態、同意或撤回
  uv run scripts/report.py feedback export [--write]                    回流：預覽去識別的使用統計；--write 才寫檔
  uv run scripts/report.py feedback import <檔或資料夾>... [--write]     維護者：彙整收到的回流檔
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
    if sys.argv[1:2] == ["advise"]:
        import advise
        return advise.main(sys.argv[2:])
    if sys.argv[1:2] == ["pool"]:
        import pool
        return pool.main(sys.argv[2:])
    if sys.argv[1:2] == ["feedback"]:
        import feedback
        return feedback.main(sys.argv[2:])
    import weekly
    return weekly.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
