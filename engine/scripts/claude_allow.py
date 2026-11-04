# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow，
並在 hooks.Stop 註冊開新對話提醒（session_nudge.py）。

只增不刪：已有的規則和其他設定都不動；設定檔不是合法 JSON 時直接失敗，不覆寫。
這次新加的規則記進安裝紀錄；移除 OmniKit 時（--uninstall）只拿掉紀錄裡的，安裝前就有的不動。

用法：uv run engine/scripts/claude_allow.py [--settings <settings.json>] [--record <install-record.json>] [--uninstall]
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit" / "install-record.json"
NUDGE = "session_nudge.py"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path: Path, data: dict) -> None:
    # 沿用檔案原本的換行；Windows 上 write_text 預設會把 LF 換成 CRLF
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=newline)


def is_nudge(hook: dict) -> bool:
    return NUDGE in hook.get("command", "")


def nudge_command() -> str:
    """提醒 hook 的指令。Claude Code 在 Windows 上用 Git Bash 跑 hook；OmniKit 的 git hooks 本來就需要
    Git for Windows。Codex 用 PowerShell 跑，codex_hooks.py 會在前面加上 `&`"""
    uv = Path(os.environ.get("UV") or shutil.which("uv")).as_posix()
    return f'"{uv}" run --quiet --script "{(ROOT / "engine" / "scripts" / NUDGE).as_posix()}"'


def add_nudge_hook(settings: dict) -> bool:
    """註冊或更新提醒 hook；回傳是否有改動。uv 或 repo 換位置時，重跑就會改成新路徑。"""
    command = nudge_command()
    stop = settings.setdefault("hooks", {}).setdefault("Stop", [])
    ours = [h for group in stop for h in group.get("hooks", []) if is_nudge(h)]
    if ours and all(h["command"] == command for h in ours):
        return False
    for h in ours:
        h["command"] = command
    if not ours:
        stop.append({"hooks": [{"type": "command", "command": command, "timeout": 10}]})
    return True


def remove_nudge_hook(settings: dict) -> bool:
    hooks = settings.get("hooks", {})
    stop = hooks.get("Stop", [])
    kept = [{**g, "hooks": [h for h in g.get("hooks", []) if not is_nudge(h)]} for g in stop]
    kept = [g for g in kept if g["hooks"]]
    if kept == stop:
        return False
    if kept:
        hooks["Stop"] = kept
    else:
        del hooks["Stop"]
    if not hooks:
        del settings["hooks"]
    return True


def uninstall(settings_path: Path, record: dict) -> int:
    ours = set(record.get("claude_allow", []))
    settings = load(settings_path)
    allow = settings.get("permissions", {}).get("allow", [])
    removed = [r for r in allow if r in ours]
    hook_removed = bool(record.get("claude_hooks")) and remove_nudge_hook(settings)
    if not (removed or hook_removed):
        print("沒有要移除的 Claude 權限規則或提醒 hook。")
        return 0

    if removed:
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
    if removed:
        print(f"已移除 Claude 的權限規則：{', '.join(removed)}")
    if hook_removed:
        print("已移除開新對話提醒 hook")
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
    allow.extend(added)
    hooked = add_nudge_hook(settings)
    if not (added or hooked):
        print("Claude 的權限規則與提醒 hook 已是最新。")
        return 0

    save(args.settings, settings)
    recorded = record.setdefault("claude_allow", [])
    recorded.extend(r for r in added if r not in recorded)
    if hooked:
        record["claude_hooks"] = [NUDGE]
    save(args.record, record)
    if added:
        print(f"已加入 Claude 的權限規則：{', '.join(added)}")
    if hooked:
        print("已註冊開新對話提醒 hook（Stop）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
