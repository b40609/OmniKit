# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow。

只增不刪：已有的規則和其他設定都不動；設定檔不是合法 JSON 時直接失敗，不覆寫。
這次新加的規則記進安裝紀錄；移除 OmniKit 時（--uninstall）只拿掉紀錄裡的，安裝前就有的不動。

用法：uv run engine/scripts/claude_allow.py [--settings <settings.json>] [--record <install-record.json>] [--uninstall]
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit" / "install-record.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path: Path, data: dict) -> None:
    # 沿用檔案原本的換行；Windows 上 write_text 預設會把 LF 換成 CRLF
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=newline)


def uninstall(settings_path: Path, record: dict) -> int:
    ours = set(record.get("claude_allow", []))
    settings = load(settings_path)
    allow = settings.get("permissions", {}).get("allow", [])
    removed = [r for r in allow if r in ours]
    if not removed:
        print("沒有要移除的 Claude 權限規則。")
        return 0

    settings["permissions"]["allow"] = [r for r in allow if r not in ours]
    # 移除後變空的就整個拿掉；什麼都不剩的設定檔等於沒有，直接刪
    if not settings["permissions"]["allow"]:
        del settings["permissions"]["allow"]
    if not settings["permissions"]:
        del settings["permissions"]
    if settings:
        save(settings_path, settings)
    else:
        settings_path.unlink()
    print(f"已移除 Claude 的權限規則：{', '.join(removed)}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    record = load(args.record)
    if args.uninstall:
        return uninstall(args.settings, record)

    lines = (ROOT / "data" / "harness" / "claude-allow.txt").read_text(encoding="utf-8").splitlines()
    rules = [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]

    settings = load(args.settings)
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    added = [r for r in rules if r not in allow]
    if not added:
        print("Claude 的權限規則已是最新。")
        return 0

    allow.extend(added)
    save(args.settings, settings)
    recorded = record.setdefault("claude_allow", [])
    recorded.extend(r for r in added if r not in recorded)
    save(args.record, record)
    print(f"已加入 Claude 的權限規則：{', '.join(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
