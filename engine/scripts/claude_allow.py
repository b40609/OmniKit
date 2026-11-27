# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""管理 Claude Code settings.json 的 permissions.allow（現行清單＋墓碑清單）與 statusLine，並支援備案 hook 註冊。

2026-11-25 無帳本升級（Fable Stage 2 洞 3 修補）：
- 權限清單擁有權改由 repo 內的現行清單（data/harness/claude-allow.txt）與下架墓碑清單
  （data/harness/claude-allow-retired.txt）決定，不依賴本機雜湊帳本即可安全新增與下架權限。
- 第一次改動某個 settings.json 之前，自動留存一份 settings.json.bak-omnikit 備份。
- 預設搭配 Claude 薄 plugin（--plugin-hooks）：hooks 交由 plugin 的 hooks/hooks.json 提供，
  本腳本自動清掉舊版留在 settings.json hooks 陣列裡的重複 OmniKit hook，只寫 permissions.allow 與 statusLine；
  未傳 --plugin-hooks 時保留直接寫入 hooks 陣列的備案相容性。

用法：uv run engine/scripts/claude_allow.py [--settings <settings.json>] [--record <install-record.json>]
      [--state <資料夾>] [--plugin-hooks] [--uninstall] [--selftest]
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edition
import profiles
import statedir
from fsretry import flaky, retry

ROOT = Path(__file__).resolve().parents[2]
RECORD = statedir.STATE / "install-record.json"
NUDGE = "session_nudge.py"
WATCH = "home_watch.py"
CLAIM = "claim_check.py"
T3W = "t3_watch.py"
HARNESS = "harness_hooks.py"
DONE = "done_check.py"
HOOKS = (("Stop", NUDGE, 10), ("SessionStart", WATCH, 15), ("Stop", CLAIM, 10), ("SessionStart", T3W, 30),
         ("PreToolUse", HARNESS, 10), ("PostToolUse", HARNESS, 20), ("Stop", HARNESS, 30),
         ("Stop", DONE, 15), ("SubagentStop", DONE, 15))
MATCHERS = {("PreToolUse", HARNESS): "Bash|PowerShell|Read|Grep|Edit|Write|MultiEdit",
            ("PostToolUse", HARNESS): "Edit|Write|MultiEdit"}
HOOK_NAMES = {NUDGE: "開新對話提醒", WATCH: "設定目錄檢查", CLAIM: "說做不到查證", T3W: "T3 MCP 斷線防護",
              HARNESS: "確定性護欄", DONE: "完工宣稱檢查"}
SCRIPTS = list(dict.fromkeys(script for _, script, _ in HOOKS))
STATUSLINE_SCRIPT = "dispatch.py"
GRANT = "uv run engine/scripts/sync.py approvals --grant <名稱>"
LATEST = "Claude 的權限規則、hook 與狀態列已是最新。"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def ensure_first_backup(path: Path) -> None:
    """第一次改動既有 settings.json 之前，保留一份 settings.json.bak-omnikit。"""
    bak = path.with_name(path.name + ".bak-omnikit")
    if path.exists() and not bak.exists():
        retry(shutil.copyfile, path, bak)


def save(path: Path, data: dict) -> None:
    newline = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    raw = rendered.replace("\n", newline).encode("utf-8")
    if path.exists() and retry(path.read_bytes) == raw:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_first_backup(path)
    tmp = path.with_name(path.name + ".omnikit-tmp")
    try:
        retry(tmp.write_bytes, raw)
        retry(os.replace, tmp, path)
    except OSError:
        retry(path.write_text, rendered, encoding="utf-8", newline=newline)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _read_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


def rules(repo: Path = ROOT) -> list[str]:
    return _read_lines(repo / "data" / "harness" / "claude-allow.txt")


def retired_rules(repo: Path = ROOT) -> list[str]:
    return _read_lines(repo / "data" / "harness" / "claude-allow-retired.txt")


def is_ours(hook: dict, script: str) -> bool:
    return script in hook.get("command", "")


def is_nudge(hook: dict) -> bool:
    return is_ours(hook, NUDGE)


def hook_command(script: str, scripts_root: Path | None = None) -> str:
    uv = Path(os.environ.get("UV") or shutil.which("uv") or "uv").as_posix()
    sroot = scripts_root or (ROOT / "engine" / "scripts")
    return f'"{uv}" run --quiet --script "{(sroot / script).as_posix()}"'


def nudge_command() -> str:
    return hook_command(NUDGE)


def is_ours_statusline(sl) -> bool:
    if not isinstance(sl, dict):
        return False
    cmd = sl.get("command", "")
    return isinstance(cmd, str) and STATUSLINE_SCRIPT in cmd and "statusline" in cmd


def statusline_command(settings_path: Path, then: str | None = None, scripts_root: Path | None = None) -> str:
    uv = Path(os.environ.get("UV") or shutil.which("uv") or "uv").as_posix()
    sroot = scripts_root or (ROOT / "engine" / "scripts")
    script = (sroot / STATUSLINE_SCRIPT).as_posix()
    cfg_dir = settings_path.parent.as_posix()
    cmd = f'"{uv}" run --quiet --script "{script}" statusline --dir "{cfg_dir}"'
    if then:
        escaped = then.replace("\\", "\\\\").replace('"', '\\"')
        cmd += f' --then "{escaped}"'
    return cmd


def add_statusline(settings: dict, settings_path: Path, entry: dict | None = None,
                   scripts_root: Path | None = None, wrap_existing: bool = True) -> bool:
    cur = settings.get("statusLine")
    entry = entry if isinstance(entry, dict) else {}
    rec = entry.get("claude_statusline") if isinstance(entry.get("claude_statusline"), dict) else None
    if cur is None:
        cmd = statusline_command(settings_path, scripts_root=scripts_root)
        settings["statusLine"] = {"type": "command", "command": cmd}
        entry["claude_statusline"] = {"had_prev": False}
        return True
    if is_ours_statusline(cur):
        prev_cmd = ((rec or {}).get("prev") or {}).get("command") if (rec or {}).get("had_prev") else None
        if prev_cmd is None and '--then "' in cur.get("command", ""):
            return False
        want = statusline_command(settings_path, prev_cmd, scripts_root=scripts_root)
        if cur.get("command") == want and rec is not None:
            return False
        cur["command"] = want
        if rec is None:
            entry["claude_statusline"] = {"had_prev": False}
        return True
    if wrap_existing and isinstance(cur, dict) and cur.get("type") == "command" and isinstance(cur.get("command"), str) and cur["command"].strip():
        prev = dict(cur)
        entry["claude_statusline"] = {"had_prev": True, "prev": prev}
        settings["statusLine"] = {**prev, "command": statusline_command(settings_path, prev["command"], scripts_root=scripts_root)}
        return True
    return False


def remove_statusline(settings: dict, entry: dict | None = None) -> bool:
    cur = settings.get("statusLine")
    if not is_ours_statusline(cur):
        return False
    rec = entry.get("claude_statusline") if isinstance(entry, dict) else None
    if isinstance(rec, dict) and rec.get("had_prev") and isinstance(rec.get("prev"), dict):
        settings["statusLine"] = dict(rec["prev"])
    else:
        settings.pop("statusLine", None)
    return True


def add_hook(settings: dict, event: str, script: str, timeout: int, scripts_root: Path | None = None) -> bool:
    command = hook_command(script, scripts_root=scripts_root)
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    ours = [h for group in groups for h in group.get("hooks", []) if is_ours(h, script)]
    if ours and all(h["command"] == command for h in ours):
        return False
    for h in ours:
        h["command"] = command
    if not ours:
        group = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
        if MATCHERS.get((event, script)):
            group = {"matcher": MATCHERS[(event, script)], **group}
        groups.append(group)
    return True


def add_hooks(settings: dict, scripts_root: Path | None = None) -> bool:
    changed = False
    for event, script, timeout in HOOKS:
        changed = add_hook(settings, event, script, timeout, scripts_root=scripts_root) or changed
    return changed


def remove_hooks(settings: dict, scripts=SCRIPTS) -> bool:
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    changed = False
    for event in dict.fromkeys(e for e, _, _ in HOOKS if e in hooks):
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
    allow = settings.get("permissions", {}).get("allow", [])
    settings["permissions"]["allow"] = [r for r in allow if r not in drop]
    if not settings["permissions"]["allow"]:
        del settings["permissions"]["allow"]
    if not settings["permissions"]:
        del settings["permissions"]


def extra_entries(record: dict) -> dict:
    extra = record.get("claude_extra")
    return extra if isinstance(extra, dict) else {}


def uninstall_one(settings_path: Path, entry: dict | None = None, repo: Path = ROOT) -> list:
    entry = entry if isinstance(entry, dict) else {}
    ours = set(entry.get("claude_allow") or (rules(repo) + retired_rules(repo)))
    try:
        settings = load(settings_path)
    except ValueError:
        msg = (f"{settings_path} 不是合法的 JSON，沒有動；"
               f"請自己拿掉 {', '.join(sorted(ours))} 與 hooks 裡的 {'、'.join(SCRIPTS)}")
        return [msg]
    allow = settings.get("permissions", {}).get("allow", [])
    removed = [r for r in allow if r in ours]
    scripts_to_rm = entry.get("claude_hooks") or SCRIPTS
    hook_removed = remove_hooks(settings, scripts_to_rm) if ("claude_hooks" in entry or not entry) else False
    sl_removed = remove_statusline(settings, entry) if ("claude_statusline" in entry or not entry) else False
    if not (removed or hook_removed or sl_removed):
        return []
    if removed:
        drop_allow(settings, ours)
    if settings:
        save(settings_path, settings)
    elif settings_path.exists():
        settings_path.unlink()
    lines = []
    if removed:
        lines.append(f"已移除 Claude 的權限規則（{settings_path}）：{', '.join(removed)}")
    if hook_removed:
        lines.append(f"已移除 OmniKit 的 hook（{settings_path}）")
    if sl_removed:
        lines.append(f"已還原或移除 OmniKit 的狀態列設定（{settings_path}）")
    return lines


def uninstall(settings_path: Path, record: dict, extra_paths=(), repo: Path = ROOT) -> int:
    lines = uninstall_one(settings_path, record, repo=repo)
    seen = {os.path.normcase(str(settings_path))}
    for path, entry in extra_entries(record).items():
        seen.add(os.path.normcase(str(path)))
        lines += uninstall_one(Path(path), entry, repo=repo)
    for p in extra_paths:
        if os.path.normcase(str(p)) not in seen:
            lines += uninstall_one(Path(p), None, repo=repo)
    for line in lines or ["沒有要移除的 Claude 權限規則或 hook。"]:
        print(line)
    return 0


def apply_one(settings_path: Path, entry: dict, listed: list, wanted: list, retired: list = (),
              plugin_hooks: bool = False, scripts_root: Path | None = None):
    """套用現行權限＋墓碑移除＋狀態列；plugin_hooks=True 時移除舊版 settings.json 內的重複 OmniKit hooks。"""
    settings = load(settings_path)
    allow = settings.get("permissions", {}).get("allow", [])
    added = [r for r in wanted if r not in allow]
    recorded = entry.setdefault("claude_allow", [])
    retired_set = set(retired)
    withdrawn = [
        r for r in allow
        if (r in retired_set) or (r in listed and r not in wanted and (r in recorded or not recorded))
    ]
    if added:
        settings.setdefault("permissions", {}).setdefault("allow", []).extend(added)
    if withdrawn:
        drop_allow(settings, set(withdrawn))
    if plugin_hooks:
        hooked = remove_hooks(settings, SCRIPTS)
        entry.pop("claude_hooks", None)
    else:
        hooked = add_hooks(settings, scripts_root=scripts_root)
        if hooked:
            entry["claude_hooks"] = SCRIPTS
    statuslined = add_statusline(
        settings, settings_path, entry, scripts_root=scripts_root, wrap_existing=not plugin_hooks
    )
    if added or withdrawn or hooked or statuslined:
        save(settings_path, settings)
    recorded.extend(r for r in added if r not in recorded)
    entry["claude_allow"] = [r for r in recorded if r not in withdrawn]
    if not entry["claude_allow"]:
        del entry["claude_allow"]
    return added, withdrawn, hooked, statuslined


def apply(settings_path: Path, record_path: Path | None, state: Path, repo: Path = ROOT, git=edition.hooks_path,
          extra_settings=(), plugin_hooks: bool | set[str] = False, scripts_root: Path | None = None) -> list:
    record = load(record_path) if record_path else {}
    before = json.dumps(record, sort_keys=True)
    allowed = edition.approver(state, repo, git)
    listed = rules(repo)
    retired = retired_rules(repo)
    wanted = [r for r in listed if r not in retired and allowed(edition.tool_of(r))]

    lines = []
    pending = list(dict.fromkeys(edition.tool_of(r) for r in listed if r not in wanted and r not in retired
                                 and edition.decided(state, edition.tool_of(r)) is None))
    if pending:
        lines.append(f"免問核准：{'、'.join(pending)} 還沒問過你，Claude Code 的權限規則沒有加；要同意就執行 {GRANT}")
    targets = [(settings_path, record, "")]
    if extra_settings:
        extra = record.setdefault("claude_extra", {})
        targets += [(Path(p), extra.setdefault(str(p), {}), f"（{Path(p).parent}）") for p in extra_settings]
    changed = []
    for path, entry, where in targets:
        use_plug = (
            os.path.normcase(str(path.parent.resolve())) in plugin_hooks
            if isinstance(plugin_hooks, set)
            else bool(plugin_hooks)
        )
        added, withdrawn, hooked, statuslined = apply_one(
            path, entry, listed, wanted, retired=retired, plugin_hooks=use_plug, scripts_root=scripts_root
        )
        if withdrawn:
            changed.append(f"已拿掉沒有同意或已下架的 Claude 權限規則{where}：{', '.join(withdrawn)}")
        if added:
            changed.append(f"已加入 Claude 的權限規則{where}：{', '.join(added)}")
        if hooked:
            if use_plug:
                changed.append(f"已清理 settings.json 舊版重複 hook（改由薄 plugin 提供）{where}")
            else:
                changed.append(f"已註冊 OmniKit 的 hook（Stop 開新對話提醒與說做不到查證、SessionStart 設定目錄檢查與 T3 MCP 斷線防護、PreToolUse／PostToolUse／Stop 確定性護欄、Stop／SubagentStop 完工宣稱檢查）{where}")
        if statuslined:
            changed.append(f"已接上 OmniKit 狀態列額度快照（dispatch.py statusline）{where}")
    if "claude_extra" in record:
        record["claude_extra"] = {p: e for p, e in record["claude_extra"].items() if e}
        if not record["claude_extra"]:
            del record["claude_extra"]
    if record_path and json.dumps(record, sort_keys=True) != before:
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

    os.environ.setdefault("UV", sys.executable)
    no_git = lambda _repo: ""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo, state = tmp / "repo", tmp / "state"
        settings, record = tmp / "home" / ".claude" / "settings.json", state / "install-record.json"
        (repo / "data" / "harness").mkdir(parents=True)
        (repo / "data" / "harness" / "claude-allow.txt").write_text(
            "# 註解\nmcp__chrome_devtools\nmcp__other__click\n", encoding="utf-8")
        (repo / "data" / "harness" / "claude-allow-retired.txt").write_text(
            "# 墓碑\nmcp__legacy_old\n", encoding="utf-8")
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Bash(ls)", "mcp__legacy_old"]}}), encoding="utf-8")

        def run(**kw):
            return apply(settings, record, state, repo, no_git, **kw)

        with flaky(os, "replace", times=2, match=lambda _s, d, *_: Path(d) == settings) as st:
            lines = run()
        allow = load(settings)["permissions"]["allow"]
        check("settings.json 首次修改先留 .bak-omnikit 備份，防毒鎖檔時重試成功",
              (settings.parent / "settings.json.bak-omnikit").is_file() and st.calls == 3)
        check("墓碑清單裡的舊權限自動移除，使用者自己的 Bash(ls) 保留；同事版還沒問過的先不加",
              allow == ["Bash(ls)"] and any("還沒問過你" in line and "chrome_devtools、other" in line for line in lines))
        check("同事版：hook 照樣註冊，其他設定不動",
              any(is_nudge(h) for g in load(settings)["hooks"]["Stop"] for h in g["hooks"])
              and load(settings)["model"] == "x")

        edition.record(state, "chrome_devtools", True)
        edition.record(state, "other", False)
        run()
        check("同意 chrome_devtools：只加它", load(settings)["permissions"]["allow"] == ["Bash(ls)", "mcp__chrome_devtools"])
        check("重跑：已是最新", run()[0] == LATEST)

        # plugin_hooks 模式：清掉 settings.json 裡的重複 OmniKit hooks，保留使用者自己的 hook
        doc_m = load(settings)
        doc_m["hooks"]["SessionStart"].insert(0, {"hooks": [{"type": "command", "command": "mine.sh"}]})
        save(settings, doc_m)
        run(plugin_hooks=True)
        after_p = load(settings)
        check("plugin_hooks 模式：移除 settings.json 內 OmniKit hooks，保留使用者自訂 mine.sh",
              list(after_p["hooks"].keys()) == ["SessionStart"]
              and [h["command"] for g in after_p["hooks"]["SessionStart"] for h in g["hooks"]] == ["mine.sh"])

        edition.set_edition(state, "maintainer")
        kai = tmp / "home" / ".claude-kai" / "settings.json"
        kai.parent.mkdir(parents=True, exist_ok=True)
        kai.write_text(json.dumps({"permissions": {"allow": ["Bash(git status)"]},
                                   "statusLine": {"type": "command", "command": "my-status.sh"}}), encoding="utf-8")
        record2 = state / "record2.json"
        apply(settings, record2, state, repo, no_git, extra_settings=[kai])
        check("維護者版其他設定目錄：規則、hook 與串接 statusLine 皆寫入",
              load(kai)["permissions"]["allow"] == ["Bash(git status)", "mcp__chrome_devtools", "mcp__other__click"]
              and is_ours_statusline(load(kai)["statusLine"]))
        uninstall(settings, load(record2))
        check("移除後使用者權限與原 statusLine 完整還原",
              load(kai) == {"permissions": {"allow": ["Bash(git status)"]}, "statusLine": {"type": "command", "command": "my-status.sh"}})

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--state", type=Path, default=RECORD.parent)
    parser.add_argument("--plugin-hooks", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    extra = () if args.settings else [h / "settings.json" for h in profiles.claude_homes()]
    if args.uninstall:
        return uninstall(args.settings or Path.home() / ".claude" / "settings.json", load(args.record), extra_paths=extra)
    for line in apply(args.settings or Path.home() / ".claude" / "settings.json", args.record, args.state,
                      extra_settings=extra, plugin_hooks=args.plugin_hooks):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
