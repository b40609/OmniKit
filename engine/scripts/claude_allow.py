# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 data/harness/claude-allow.txt 的權限規則補進 Claude Code 的 permissions.allow，並註冊 OmniKit 的 hook：
- hooks.Stop：開新對話提醒（session_nudge.py）
- hooks.SessionStart：設定目錄檢查（home_watch.py）：這台多了新的 agent 設定目錄（新帳號、新的 T3 實例）就在背景接上
其他 Claude 設定目錄（CLAUDE_CONFIG_DIR、T3 Code 每個 Claude 實例的 homePath 等，見 homes.py）的 settings.json
也一樣寫，紀錄放在安裝紀錄的 claude_extra（以設定檔路徑分開記）。

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
WATCH = "home_watch.py"
# OmniKit 註冊的 Claude Code hook：(事件, 腳本, 逾時秒數)
HOOKS = (("Stop", NUDGE, 10), ("SessionStart", WATCH, 15))
SCRIPTS = [script for _, script, _ in HOOKS]
GRANT = "uv run engine/scripts/agents.py approvals --grant <名稱>"
LATEST = "Claude 的權限規則與 OmniKit 的 hook 已是最新。"


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


def is_ours(hook: dict, script: str) -> bool:
    return script in hook.get("command", "")


def is_nudge(hook: dict) -> bool:
    return is_ours(hook, NUDGE)


def hook_command(script: str) -> str:
    """hook 的指令。Claude Code 在 Windows 上用 Git Bash 跑 hook；OmniKit 的 git hooks 本來就需要
    Git for Windows。Codex 用 PowerShell 跑，codex_hooks.py 會在前面加上 `&`"""
    uv = Path(os.environ.get("UV") or shutil.which("uv")).as_posix()
    return f'"{uv}" run --quiet --script "{(ROOT / "engine" / "scripts" / script).as_posix()}"'


def nudge_command() -> str:
    return hook_command(NUDGE)


def add_hook(settings: dict, event: str, script: str, timeout: int) -> bool:
    """註冊或更新一個 hook；回傳是否有改動。uv 或 repo 換位置時，重跑就會改成新路徑。"""
    command = hook_command(script)
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    ours = [h for group in groups for h in group.get("hooks", []) if is_ours(h, script)]
    if ours and all(h["command"] == command for h in ours):
        return False
    for h in ours:
        h["command"] = command
    if not ours:
        groups.append({"hooks": [{"type": "command", "command": command, "timeout": timeout}]})
    return True


def add_hooks(settings: dict) -> bool:
    changed = False
    for event, script, timeout in HOOKS:
        changed = add_hook(settings, event, script, timeout) or changed
    return changed


def remove_hooks(settings: dict, scripts) -> bool:
    """拿掉這些腳本的 hook；回傳是否有改動。事件或整個 hooks 變空的就一起拿掉。"""
    hooks = settings.get("hooks", {})
    changed = False
    for event in [e for e, _, _ in HOOKS if e in hooks]:
        groups = hooks[event]
        kept = [{**g, "hooks": [h for h in g.get("hooks", []) if not any(is_ours(h, s) for s in scripts)]}
                for g in groups]
        kept = [g for g in kept if g["hooks"]]
        if kept == groups:
            continue
        changed = True
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if changed and not hooks:
        del settings["hooks"]
    return changed


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
        return [f"{settings_path} 不是合法的 JSON，沒有動；"
                f"請自己拿掉 {', '.join(sorted(ours))} 與 hooks 裡的 {'、'.join(SCRIPTS)}"]
    allow = settings.get("permissions", {}).get("allow", [])
    removed = [r for r in allow if r in ours]
    hook_removed = bool(entry.get("claude_hooks")) and remove_hooks(settings, entry["claude_hooks"])
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
        lines.append(f"已移除 OmniKit 的 hook（{settings_path}）")
    return lines


def uninstall(settings_path: Path, record: dict) -> int:
    lines = uninstall_one(settings_path, record)
    for path, entry in extra_entries(record).items():
        lines += uninstall_one(Path(path), entry)
    for line in lines or ["沒有要移除的 Claude 權限規則或 hook。"]:
        print(line)
    return 0


def apply_one(settings_path: Path, entry: dict, listed: list, wanted: list):
    """把規則與 OmniKit 的 hook 寫進一個 settings.json；entry 是這個檔案的紀錄（原地更新）。
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
    hooked = add_hooks(settings)
    if added or withdrawn or hooked:
        save(settings_path, settings)
    recorded.extend(r for r in added if r not in recorded)
    entry["claude_allow"] = [r for r in recorded if r not in withdrawn]
    if not entry["claude_allow"]:
        del entry["claude_allow"]
    if hooked:
        entry["claude_hooks"] = SCRIPTS
    return added, withdrawn, hooked


def apply(settings_path: Path, record_path: Path, state: Path, repo: Path = ROOT, git=edition.hooks_path,
          extra_settings=()) -> list:
    """補上這台可以寫的權限規則、註冊 OmniKit 的 hook；回傳要印的訊息。
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
            changed.append(f"已註冊 OmniKit 的 hook（Stop 開新對話提醒、SessionStart 設定目錄檢查）{where}")
    if "claude_extra" in record:
        record["claude_extra"] = {p: e for p, e in record["claude_extra"].items() if e}
        if not record["claude_extra"]:
            del record["claude_extra"]
    if json.dumps(record, sort_keys=True) != before:
        save(record_path, record)
    if not changed:
        return [LATEST, *lines]
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
        check("同事版：提醒 hook 與設定目錄檢查 hook 照樣註冊，其他設定不動",
              any(is_nudge(h) for g in load(settings)["hooks"]["Stop"] for h in g["hooks"])
              and any(is_ours(h, WATCH) for g in load(settings)["hooks"]["SessionStart"] for h in g["hooks"])
              and load(settings)["model"] == "x")

        # 舊版只註冊了提醒 hook（紀錄是 [NUDGE]）：重跑補上設定目錄檢查，紀錄也跟著補
        old = tmp / "old" / "settings.json"
        save(old, {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": nudge_command(), "timeout": 10}]}],
                             "SessionStart": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}})
        old_entry = {"claude_hooks": [NUDGE]}
        _, _, hooked = apply_one(old, old_entry, [], [])
        check("舊版升級：補上 SessionStart 的設定目錄檢查，使用者自己的 SessionStart hook 留著",
              hooked and old_entry["claude_hooks"] == SCRIPTS
              and [h["command"] for g in load(old)["hooks"]["SessionStart"] for h in g["hooks"]][0] == "mine.sh"
              and any(is_ours(h, WATCH) for g in load(old)["hooks"]["SessionStart"] for h in g["hooks"]))
        uninstall_one(old, {"claude_hooks": [NUDGE]})
        check("舊版紀錄只有 NUDGE：移除時只拿掉提醒 hook",
              "Stop" not in load(old)["hooks"] and len(load(old)["hooks"]["SessionStart"]) == 2)

        edition.record(state, "chrome_devtools", True)
        edition.record(state, "other", False)
        lines = run()
        check("同意 chrome_devtools：只加它，不要的 other 不加也不再提醒",
              load(settings)["permissions"]["allow"] == ["Bash(ls)", "mcp__chrome_devtools"]
              and load(record)["claude_allow"] == ["mcp__chrome_devtools"] and not any("還沒問過" in line for line in lines))
        check("重跑：已是最新", run()[0] == LATEST)

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
              and any(is_ours(h, WATCH) for g in load(kai)["hooks"]["SessionStart"] for h in g["hooks"])
              and entry.get("claude_hooks") == SCRIPTS and any(".claude-kai" in line for line in lines))
        check("其他設定目錄：重跑已是最新",
              apply(settings, record2, state, repo, no_git, extra_settings=[kai])[0] == LATEST)
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
