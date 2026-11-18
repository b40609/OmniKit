# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""在 Codex 的 ~/.codex/config.toml 註冊 OmniKit 的 Stop hook：開新對話提醒（session_nudge.py）與
說做不到查證（claim_check.py）。每支各寫成一段 [[hooks.Stop]]，可以分開加、分開拿掉。

寫進 config.toml 而不是 hooks.json：同一層兩種都有時 Codex 每次啟動都會警告，
而 config.toml 常已有別的工具寫的 [hooks]。Python 沒有保留格式的 TOML 寫入器（tomlkit 會重排表格），
所以用文字附加或刪掉一段，寫入前用 tomllib 比對：解析結果必須剛好是「原設定加上或拿掉這個 hook」，
否則不寫、直接失敗。

Codex 在 Windows 上用 `pwsh -NoProfile -Command <command>` 跑 hook，所以指令前面要加 PowerShell 的 `&`。
Codex 的新 hook 或改過的 hook 要使用者信任後才會執行（CLI 輸入 /hooks，桌面版在設定的 Hooks），
這裡不代為信任。安裝紀錄的 codex_hooks 記加了哪幾支；--uninstall 只移除紀錄裡有的。

用法：uv run engine/scripts/codex_hooks.py [--config <config.toml>] [--record <install-record.json>] [--uninstall]
"""
import argparse
import copy
import json
import os
import re
import sys
import tempfile
import tomllib
from pathlib import Path

from claude_allow import CLAIM, HOOK_NAMES, NUDGE, RECORD, hook_command, is_ours, load, save
from fsretry import flaky, retry  # 防毒短暫鎖住檔案時等一下再試（FR-34）

SCRIPTS = (NUDGE, CLAIM)  # OmniKit 在 Codex 註冊的 Stop hook，照這個順序寫
MARKS = {script: f"# OmniKit：{HOOK_NAMES[script]}（install.ps1 加入、uninstall.ps1 移除）" for script in SCRIPTS}
MARK = MARKS[NUDGE]


def command_line(script: str):
    return re.compile(r"^command\s*=.*" + re.escape(script) + r".*$", re.M)


COMMAND_LINE = command_line(NUDGE)
HEADER = re.compile(r"^\s*\[")
GROUP = re.compile(r"^\s*\[\[\s*hooks\.Stop\s*\]\]\s*$")
PARTS = re.compile(r'"([^"]+)" run --quiet --script "([^"]+)"')


def still_valid(old: str, new: str) -> bool:
    """舊指令的 uv 還在、腳本路徑也一樣就不改：指令一變，Codex 就要使用者重新信任。
    git hook 與 install.ps1 可能跑到不同支 uv，不能每次都換成當下這支。"""
    o, n = PARTS.search(old), PARTS.search(new)
    return bool(o and n) and o[2] == n[2] and Path(o[1]).exists()


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON 字串的跳脫寫法也是合法的 TOML basic string


def stop_groups(doc: dict) -> list:
    return doc.get("hooks", {}).get("Stop", [])


def without(doc: dict, script: str = NUDGE) -> dict:
    """預期的移除結果：拿掉這支 hook，變空的 group、Stop、hooks 一併拿掉。"""
    doc = copy.deepcopy(doc)
    groups = [{**g, "hooks": [h for h in g.get("hooks", []) if not is_ours(h, script)]} for g in stop_groups(doc)]
    groups = [g for g in groups if g["hooks"]]
    if groups:
        doc["hooks"]["Stop"] = groups
    elif "Stop" in doc.get("hooks", {}):
        del doc["hooks"]["Stop"]
        if not doc["hooks"]:
            del doc["hooks"]
    return doc


def checked(new: str, expected: dict) -> str:
    if tomllib.loads(new) != expected:
        raise ValueError("改完的 config.toml 解析結果跟預期不同")
    return new


def add(text: str, command: str, script: str = NUDGE) -> str | None:
    """回傳改好的內容；已是最新就回傳 None。uv 不見了或 repo 換位置時，只換掉 command 那一行。"""
    doc = tomllib.loads(text)
    ours = [h for g in stop_groups(doc) for h in g.get("hooks", []) if is_ours(h, script)]
    if ours and all(h.get("command") == command or still_valid(h.get("command", ""), command) for h in ours):
        return None
    expected = copy.deepcopy(doc)
    if ours:
        for g in stop_groups(expected):
            for h in g.get("hooks", []):
                if is_ours(h, script):
                    h["command"] = command
        return checked(command_line(script).sub(lambda _: f"command = {toml_str(command)}", text), expected)
    expected.setdefault("hooks", {}).setdefault("Stop", []).append(
        {"hooks": [{"type": "command", "command": command, "timeout": 10}]})
    block = f'{MARKS[script]}\n[[hooks.Stop]]\n\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = {toml_str(command)}\ntimeout = 10\n'
    return checked((text.rstrip("\n") + "\n\n" if text.strip() else "") + block, expected)


def remove(text: str, script: str = NUDGE) -> str | None:
    """拿掉這支 hook 所在的 [[hooks.Stop.hooks]] 表；group 因此變空就連 [[hooks.Stop]] 標頭一起拿掉。"""
    doc = tomllib.loads(text)
    if not any(is_ours(h, script) for g in stop_groups(doc) for h in g.get("hooks", [])):
        return None
    expected = without(doc, script)
    lines = text.split("\n")
    pattern = command_line(script)
    cmd = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if cmd is None:
        raise ValueError(f"找不到 {script} 的 command 那一行")
    start = max(i for i in range(cmd) if HEADER.match(lines[i]))
    end = next((i for i in range(cmd + 1, len(lines)) if HEADER.match(lines[i])), len(lines))
    while end - 1 > cmd and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1  # 後面的空行與下一個表上方的註解留給下一個表
    # 候選：連同最近的 [[hooks.Stop]] 標頭（與上方的 OmniKit 註解）一起拿掉；或只拿掉 hooks 表
    drops = [set(range(start, end)) | {g} | ({g - 1} if g and lines[g - 1] == MARKS[script] else set())
             for g in range(start - 1, -1, -1) if GROUP.match(lines[g])]
    drops.append(set(range(start, end)))
    for drop in drops:
        for i in sorted(drop):  # 每段拿掉的行，連同前面的空行一起拿掉
            while i - 1 >= 0 and i - 1 not in drop and not lines[i - 1].strip():
                i -= 1
                drop.add(i)
        new = "\n".join(line for i, line in enumerate(lines) if i not in drop)
        new = new.rstrip("\n") + "\n" if new.strip() else ""
        try:
            return checked(new, expected)
        except (ValueError, tomllib.TOMLDecodeError):
            continue
    raise ValueError(f"找不到能安全拿掉 {script} 的寫法")


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8") if path.exists() else ""
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def write(path: Path, text: str, newline: str) -> None:
    retry(path.write_bytes, text.replace("\n", newline).encode("utf-8"))


def selftest() -> int:
    cmd = '& "C:/uv.exe" run --quiet --script "C:/OmniKit/engine/scripts/session_nudge.py"'
    base = 'model = "x"\n\n[[hooks.Interrupt]]\n\n[[hooks.Interrupt.hooks]]\ntype = "command"\ncommand = "bun"\n'
    ours = add(base, cmd)
    assert add(ours, cmd) is None and remove(ours) == base  # 重跑不重複，移除後還原
    assert remove(add("", cmd)) == "" and remove(base) is None
    # Codex 信任時寫的 hooks.state 插在中間或後面：只拿掉我們的，其他留著
    trust = '[hooks.state."k"]\ntrusted_hash = "sha256:1"\n'
    mid = remove(ours.replace("[[hooks.Stop]]\n", "[[hooks.Stop]]\n\n" + trust))
    assert tomllib.loads(mid) == tomllib.loads(base + "\n" + trust)
    assert remove(ours + "\n# 別的工具\n" + trust) == base + "\n# 別的工具\n" + trust
    # 舊的 uv 不見了：只改 command 那一行；舊的 uv 還在就不改
    moved = add(ours, cmd.replace("C:/uv.exe", "D:/uv.exe"))
    assert sum(a != b for a, b in zip(ours.split("\n"), moved.split("\n"))) == 1
    alive = add(base, cmd.replace("C:/uv.exe", Path(sys.executable).as_posix()))
    assert add(alive, cmd) is None and add(alive, cmd.replace("C:/OmniKit", "D:/OmniKit")) is not None
    # 原本就有別人的 Stop hook：各自保留
    other = base + '\n[[hooks.Stop]]\n\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "other"\n'
    assert len(stop_groups(tomllib.loads(add(other, cmd)))) == 2 and remove(add(other, cmd)) == other
    shared = remove(ours + '\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "extra"\n')
    assert stop_groups(tomllib.loads(shared)) == [{"hooks": [{"type": "command", "command": "extra"}]}]
    # inline 陣列寫法無法安全附加：失敗，不寫
    try:
        add('hooks.Stop = [{ hooks = [{ type = "command", command = "x" }] }]\n', cmd)
        raise AssertionError("inline 寫法應該失敗")
    except tomllib.TOMLDecodeError:
        pass
    # 兩支 OmniKit hook（提醒與說做不到查證）各一段：分開加、分開拿掉，順序不影響
    claim = cmd.replace(NUDGE, CLAIM)
    both = add(ours, claim, CLAIM)
    assert MARKS[CLAIM] in both and add(both, claim, CLAIM) is None and add(both, cmd) is None
    assert len(stop_groups(tomllib.loads(both))) == 2
    assert remove(both, CLAIM) == ours and remove(remove(both), CLAIM) == base
    only_claim = remove(both)
    assert MARK not in only_claim and MARKS[CLAIM] in only_claim
    assert [h["command"] for g in stop_groups(tomllib.loads(only_claim)) for h in g["hooks"]] == [claim]
    assert remove(base, CLAIM) is None
    # 防毒短暫鎖住 config.toml（FR-34）：等一下再試，寫進去的內容與換行照原本的
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "config.toml"
        with flaky(Path, "write_bytes", times=2, match=lambda p, *_: p == config) as st:
            write(config, ours, "\r\n")
        assert st.calls == 3 and st.waits == [0.25, 0.5] and read(config) == (ours, "\r\n")
    print("codex_hooks selftest OK")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if "--selftest" in sys.argv:
        return selftest()
    parser = argparse.ArgumentParser()
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    parser.add_argument("--config", type=Path, default=home / "config.toml")
    parser.add_argument("--record", type=Path, default=RECORD)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    try:
        return apply(args)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"沒有改動 {args.config}：{e}。請手動處理 [[hooks.Stop]] 裡的 {'、'.join(SCRIPTS)}。", file=sys.stderr)
        return 1


def names(scripts) -> str:
    return "、".join(HOOK_NAMES[s] for s in scripts)


def apply(args: argparse.Namespace) -> int:
    record = load(args.record)
    text, newline = read(args.config)
    if args.uninstall:
        recorded = record.get("codex_hooks") or []
        # 舊版的紀錄只有提醒 hook；認不得的內容也當成提醒 hook
        wanted = [s for s in SCRIPTS if s in recorded] or ([NUDGE] if recorded else [])
        removed = []
        for script in wanted:
            new = remove(text, script)
            if new is not None:
                text = new
                removed.append(script)
        if not removed:
            print("沒有要移除的 Codex hook。")
            return 0
        if text:
            write(args.config, text, newline)
        else:
            args.config.unlink()  # 裝之前沒有這個檔，只剩 OmniKit 加的那段
        print(f"已移除 Codex 的 hook：{names(removed)}")
        return 0

    if not args.config.parent.exists():
        print("沒有 Codex 的設定資料夾，略過 Codex 的 hook。")
        return 0
    added = []
    for script in SCRIPTS:
        new = add(text, "& " + hook_command(script), script)
        if new is not None:
            text = new
            added.append(script)
    if not added:
        print("Codex 的 OmniKit hook 已是最新。")
        return 0
    write(args.config, text, newline)
    record["codex_hooks"] = list(dict.fromkeys([*(record.get("codex_hooks") or []), *added]))
    save(args.record, record)
    print(f"已註冊或更新 Codex 的 Stop hook：{names(added)}。Codex 要信任後才會執行：CLI 輸入 /hooks，桌面版到設定的 Hooks。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
