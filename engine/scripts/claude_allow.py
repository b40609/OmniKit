# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow。

只增不刪：已有的規則和其他設定都不動；設定檔不是合法 JSON 時直接失敗，不覆寫。

用法：uv run engine/scripts/claude_allow.py [--settings <settings.json>]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    args = parser.parse_args()

    lines = (ROOT / "data" / "harness" / "claude-allow.txt").read_text(encoding="utf-8").splitlines()
    rules = [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]

    settings = json.loads(args.settings.read_text(encoding="utf-8")) if args.settings.exists() else {}
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    added = [r for r in rules if r not in allow]
    if not added:
        print("Claude 的權限規則已是最新。")
        return 0

    allow.extend(added)
    args.settings.parent.mkdir(parents=True, exist_ok=True)
    args.settings.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已加入 Claude 的權限規則：{', '.join(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
