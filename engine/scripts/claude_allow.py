# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow，
並在 hooks.Stop 註冊開新對話提醒（session_nudge.py）。
其他 Claude 設定目錄（CLAUDE_CONFIG_DIR、T3 Code 每個 Claude 實例的 homePath）的 settings.json 也一樣寫，
紀錄放在安裝紀錄的 claude_extra（以設定檔路徑分開記）。

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
import profiles  # noqa: E402  其他 Claude 設定目錄（claude_homes）
from fsretry import flaky, retry  # noqa: E402  防毒短暫鎖住檔案時等一下再試（FR-34）

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
    retry(path.write_text, json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=newline)


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


def extra_entries(record: dict) -> dict:
    """其他 Claude 設定目錄（T3 Code 的多帳號）的紀錄：{settings.json 路徑: {"claude_allow", "claude_hooks"}}。
    ~/.claude/settings.json 的紀錄照舊放在最上層。"""
    extra = record.get("claude_extra")
    return extra if isinstance(extra, dict) else {}


def uninstall_one(settings_path: Path, entry: dict) -> list:
    ours = set(entry.get("claude_allow", []))
    try:
        settings = load(settings_path)
    except ValueError:
        return [f"{settings_path} 不是合法的 JSON，沒有動；請自己拿掉 {', '.join(sorted(ours))} 與 hooks.Stop 裡的 {NUDGE}"]
    allow = settings.get("permissions", {}).get("allow", [])
    removed = [r for r in allow if r in ours]
    hook_removed = bool(entry.get("claude_hooks")) and remove_nudge_hook(settings)
    if not (removed or hook_removed):
        return []
    if removed:
        drop_allow(settings, ours)
    # 什麼都不剩的設定檔等於沒有，直接刪
    if settings:
        save(settings_path, settings)
    else:
        settings_path.unlink()
    lines = []
    if removed:
        lines.append(f"已移除 Claude 的權限規則（{settings_path}）：{', '.join(removed)}")
    if hook_removed:
        lines.append(f"已移除開新對話提醒 hook（{settings_path}）")
    return lines


def uninstall(settings_path: Path, record: dict) -> int:
    lines = uninstall_one(settings_path, record)
    for path, entry in extra_entries(record).items():
        lines += uninstall_one(Path(path), entry)
    for line in lines or ["沒有要移除的 Claude 權限規則或提醒 hook。"]:
        print(line)
    return 0


def apply_one(settings_path: Path, entry: dict, listed: list, wanted: list):
    """把規則與提醒 hook 寫進一個 settings.json；entry 是這個檔案的紀錄（原地更新）。
    回傳（加了的, 拿掉的, hook 有沒有改）。"""
    settings = load(settings_path)
    allow = settings.get("permissions", {}).get("allow", [])
    added = [r for r in wanted if r not in allow]
    recorded = entry.setdefault("claude_allow", [])
    # 沒同意的：OmniKit 以前加過的拿掉；使用者自己加的（不在紀錄裡）不動
    withdrawn = [r for r in listed if r not in wanted and r in recorded and r in allow]
    if added:
        settings.setdefault("permissions", {}).setdefault("allow", []).extend(added)
    if withdrawn:
        drop_allow(settings, set(withdrawn))
    hooked = add_nudge_hook(settings)
    if added or withdrawn or hooked:
        save(settings_path, settings)
    recorded.extend(r for r in added if r not in recorded)
    entry["claude_allow"] = [r for r in recorded if r not in withdrawn]
    if not entry["claude_allow"]:
        del entry["claude_allow"]
    if hooked:
        entry["claude_hooks"] = [NUDGE]
    return added, withdrawn, hooked


def apply(settings_path: Path, record_path: Path, state: Path, repo: Path = ROOT, git=edition.hooks_path,
          extra_settings=()) -> list:
    """補上這台可以寫的權限規則、註冊提醒 hook；回傳要印的訊息。
    extra_settings：其他 Claude 設定目錄的 settings.json（profiles.claude_homes），一樣寫。"""
    record = load(record_path)
    before = json.dumps(record, sort_keys=True)
    allowed = edition.approver(state, repo, git)
    listed = rules(repo)
    wanted = [r for r in listed if allowed(edition.tool_of(r))]

    lines = []
    pending = list(dict.fromkeys(edition.tool_of(r) for r in listed if r not in wanted
                                 and edition.decided(state, edition.tool_of(r)) is None))
    if pending:
        lines.append(f"免問核准：{'、'.join(pending)} 還沒問過你，Claude Code 的權限規則沒有加；要同意就執行 {GRANT}")
    targets = [(settings_path, record, "")]
    if extra_settings:
        extra = record.setdefault("claude_extra", {})
        targets += [(Path(p), extra.setdefault(str(p), {}), f"（{Path(p).parent}）") for p in extra_settings]
    changed = []
    for path, entry, where in targets:
        added, withdrawn, hooked = apply_one(path, entry, listed, wanted)
        if withdrawn:
            changed.append(f"已拿掉沒有同意的 Claude 權限規則{where}：{', '.join(withdrawn)}")
        if added:
            changed.append(f"已加入 Claude 的權限規則{where}：{', '.join(added)}")
        if hooked:
            changed.append(f"已註冊開新對話提醒 hook（Stop）{where}")
    if "claude_extra" in record:
        record["claude_extra"] = {p: e for p, e in record["claude_extra"].items() if e}
        if not record["claude_extra"]:
            del record["claude_extra"]
    if json.dumps(record, sort_keys=True) != before:
        save(record_path, record)
    if not changed:
        return ["Claude 的權限規則與提醒 hook 已是最新。", *lines]
    return [*[c for c in changed if not c.startswith("已註冊")], *lines, *[c for c in changed if c.startswith("已註冊")]]


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

        # 第一次寫 settings.json 就遇到防毒短暫鎖住（FR-34）：等一下再試，照樣寫進去
        with flaky(Path, "write_text", times=2, match=lambda p, *_, **__: p == settings) as st:
            lines = run()
        allow = load(settings)["permissions"]["allow"]
        check("settings.json 被防毒短暫鎖住：等一下再試，照樣寫進去", st.calls == 3 and st.waits == [0.25, 0.5]
              and any(is_nudge(h) for g in load(settings)["hooks"]["Stop"] for h in g["hooks"]))
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

        # 其他 Claude 設定目錄（T3 Code 的多帳號）：各自寫規則與 hook，紀錄分開；移除時只拿掉 OmniKit 加的
        edition.set_edition(state, "maintainer")
        kai = tmp / "home" / ".claude-kai" / "settings.json"
        save(kai, {"permissions": {"allow": ["Bash(git status)"]}})
        record2 = state / "record2.json"
        lines = apply(settings, record2, state, repo, no_git, extra_settings=[kai])
        entry = extra_entries(load(record2)).get(str(kai), {})
        check("其他設定目錄：規則與提醒 hook 也寫進去，紀錄分開記",
              load(kai)["permissions"]["allow"] == ["Bash(git status)", "mcp__chrome_devtools", "mcp__other__click"]
              and any(is_nudge(h) for g in load(kai)["hooks"]["Stop"] for h in g["hooks"])
              and entry.get("claude_allow") == ["mcp__chrome_devtools", "mcp__other__click"]
              and entry.get("claude_hooks") == [NUDGE] and any(".claude-kai" in line for line in lines))
        check("其他設定目錄：重跑已是最新",
              apply(settings, record2, state, repo, no_git, extra_settings=[kai])[0] == "Claude 的權限規則與提醒 hook 已是最新。")
        uninstall(settings, load(record2))
        check("其他設定目錄：移除時只拿掉 OmniKit 加的，使用者的留著",
              load(kai) == {"permissions": {"allow": ["Bash(git status)"]}})

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=None,
                        help="預設是 ~/.claude/settings.json，加上其他 Claude 設定目錄（T3 Code 的多帳號）的")
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--state", type=Path, default=RECORD.parent, help="edition.json 與 consent.json 所在的資料夾")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.uninstall:
        return uninstall(args.settings or Path.home() / ".claude" / "settings.json", load(args.record))
    extra = () if args.settings else [h / "settings.json" for h in profiles.claude_homes()]
    for line in apply(args.settings or Path.home() / ".claude" / "settings.json", args.record, args.state,
                      extra_settings=extra):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
