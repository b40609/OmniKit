# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow，
並在 hooks.Stop 註冊開新對話提醒（session_nudge.py）。

免問核准要誰同意，看這台是哪一版（edition.py）：
- 維護者版：清單裡的規則全部補上，那是維護者自己同意過的。
- 同事版：本人同意過的工具（agents.py approvals）才補上；沒同意的不寫。OmniKit 以前加過、
  現在沒同意的（撤回同意，或從維護者版換過來）會拿掉；使用者自己加的同一條規則不動。

其他設定都不動；設定檔不是合法 JSON 時直接失敗，不覆寫。
這次新加的規則記進安裝紀錄；移除 OmniKit 時（--uninstall）只拿掉紀錄裡的，安裝前就有的不動。

用法：uv run engine/scripts/claude_allow.py [--settings <settings.json>] [--record <install-record.json>]
      [--state <資料夾>] [--uninstall] [--selftest]
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edition  # noqa: E402  同一個資料夾，沒有相依套件

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit" / "install-record.json"
NUDGE = "session_nudge.py"
GRANT = "uv run engine/scripts/agents.py approvals --grant <名稱>"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save(path: Path, data: dict) -> None:
    # 沿用檔案原本的換行；Windows 上 write_text 預設會把 LF 換成 CRLF
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=newline)


def rules(repo: Path = ROOT) -> list:
    path = repo / "data" / "harness" / "claude-allow.txt"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


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


def drop_allow(settings: dict, drop: set) -> None:
    """從 permissions.allow 拿掉這些規則；變空的就整個拿掉。"""
    allow = settings.get("permissions", {}).get("allow", [])
    settings["permissions"]["allow"] = [r for r in allow if r not in drop]
    if not settings["permissions"]["allow"]:
        del settings["permissions"]["allow"]
    if not settings["permissions"]:
        del settings["permissions"]


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
        drop_allow(settings, ours)
    # 什麼都不剩的設定檔等於沒有，直接刪
    if settings:
        save(settings_path, settings)
    else:
        settings_path.unlink()
    if removed:
        print(f"已移除 Claude 的權限規則：{', '.join(removed)}")
    if hook_removed:
        print("已移除開新對話提醒 hook")
    return 0


def apply(settings_path: Path, record_path: Path, state: Path, repo: Path = ROOT, git=edition.hooks_path) -> list:
    """補上這台可以寫的權限規則、註冊提醒 hook；回傳要印的訊息。"""
    record = load(record_path)
    allowed = edition.approver(state, repo, git)
    listed = rules(repo)
    wanted = [r for r in listed if allowed(edition.tool_of(r))]
    settings = load(settings_path)
    allow = settings.get("permissions", {}).get("allow", [])
    added = [r for r in wanted if r not in allow]
    recorded = record.setdefault("claude_allow", [])
    # 沒同意的：OmniKit 以前加過的拿掉；使用者自己加的（不在紀錄裡）不動
    withdrawn = [r for r in listed if r not in wanted and r in recorded and r in allow]
    if added:
        settings.setdefault("permissions", {}).setdefault("allow", []).extend(added)
    if withdrawn:
        drop_allow(settings, set(withdrawn))
    hooked = add_nudge_hook(settings)

    lines = []
    pending = list(dict.fromkeys(edition.tool_of(r) for r in listed if r not in wanted
                                 and edition.decided(state, edition.tool_of(r)) is None))
    if pending:
        lines.append(f"免問核准：{'、'.join(pending)} 還沒問過你，Claude Code 的權限規則沒有加；要同意就執行 {GRANT}")
    if not (added or withdrawn or hooked):
        return ["Claude 的權限規則與提醒 hook 已是最新。", *lines]

    save(settings_path, settings)
    recorded.extend(r for r in added if r not in recorded)
    record["claude_allow"] = [r for r in recorded if r not in withdrawn]
    if not record["claude_allow"]:
        del record["claude_allow"]
    if hooked:
        record["claude_hooks"] = [NUDGE]
    save(record_path, record)
    if added:
        lines.insert(0, f"已加入 Claude 的權限規則：{', '.join(added)}")
    if withdrawn:
        lines.insert(0, f"已拿掉沒有同意的 Claude 權限規則：{', '.join(withdrawn)}")
    if hooked:
        lines.append("已註冊開新對話提醒 hook（Stop）")
    return lines


def selftest() -> int:
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    os.environ.setdefault("UV", sys.executable)  # nudge_command 要一個 uv 路徑；這裡不會真的執行
    no_git = lambda _repo: ""  # noqa: E731
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo, state = tmp / "repo", tmp / "state"
        settings, record = tmp / "home" / ".claude" / "settings.json", state / "install-record.json"
        (repo / "data" / "harness").mkdir(parents=True)
        (repo / "data" / "harness" / "claude-allow.txt").write_text(
            "# 註解\nmcp__chrome_devtools\nmcp__other__click\n", encoding="utf-8")
        save(settings, {"model": "x", "permissions": {"allow": ["Bash(ls)"]}})

        def run():
            return apply(settings, record, state, repo, no_git)

        lines = run()
        allow = load(settings)["permissions"]["allow"]
        check("同事版、還沒問過：權限規則都不加，提醒怎麼同意",
              allow == ["Bash(ls)"] and any("還沒問過你" in line and "chrome_devtools、other" in line for line in lines))
        check("同事版：提醒 hook 照樣註冊，其他設定不動",
              any(is_nudge(h) for g in load(settings)["hooks"]["Stop"] for h in g["hooks"]) and load(settings)["model"] == "x")

        edition.record(state, "chrome_devtools", True)
        edition.record(state, "other", False)
        lines = run()
        check("同意 chrome_devtools：只加它，不要的 other 不加也不再提醒",
              load(settings)["permissions"]["allow"] == ["Bash(ls)", "mcp__chrome_devtools"]
              and load(record)["claude_allow"] == ["mcp__chrome_devtools"] and not any("還沒問過" in line for line in lines))
        check("重跑：已是最新", run()[0] == "Claude 的權限規則與提醒 hook 已是最新。")

        edition.record(state, "chrome_devtools", False)
        allow = load(settings)["permissions"]["allow"]
        allow.append("mcp__other__click")  # 使用者自己加的，OmniKit 沒加過
        save(settings, {**load(settings), "permissions": {"allow": allow}})
        lines = run()
        check("撤回同意：拿掉 OmniKit 加的，使用者自己加的不動",
              load(settings)["permissions"]["allow"] == ["Bash(ls)", "mcp__other__click"]
              and "claude_allow" not in load(record) and any("已拿掉沒有同意" in line for line in lines))

        edition.set_edition(state, "maintainer")
        run()
        check("維護者版：清單裡的都加，不用另外同意",
              load(settings)["permissions"]["allow"] == ["Bash(ls)", "mcp__other__click", "mcp__chrome_devtools"]
              and load(record)["claude_allow"] == ["mcp__chrome_devtools"])

        uninstall(settings, load(record))
        doc = load(settings)
        check("移除：只拿掉紀錄裡的規則與提醒 hook，使用者的留著",
              doc["permissions"]["allow"] == ["Bash(ls)", "mcp__other__click"] and "hooks" not in doc)

        edition.set_edition(state, "colleague")
        bare = tmp / "bare" / "settings.json"
        apply(bare, tmp / "bare" / "record.json", state, repo, no_git)
        check("沒有規則可加：不留下空的 permissions", "permissions" not in load(bare))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--state", type=Path, default=RECORD.parent, help="edition.json 與 consent.json 所在的資料夾")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.uninstall:
        return uninstall(args.settings, load(args.record))
    for line in apply(args.settings, args.record, args.state):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
