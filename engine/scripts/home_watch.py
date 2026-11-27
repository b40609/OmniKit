# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 的 SessionStart hook：發現尚未接上 OmniKit 的設定目錄或未合併舊狀態時，在背景執行 sync.py sync。

無帳本設計（2026-11-25）：
不再依賴 agents.json 的 homes 清單，而是直接檢查 homes.discover() 找到的每個目錄是否已就位：
- Claude Code 目錄：<dir>/CLAUDE.md 含有 OmniKit 受管區塊
- Codex 目錄：<dir>/AGENTS.md 含有 OmniKit 受管區塊
- T3 Antigravity 實例目錄（已建立目錄者）：<dir>/config/plugins/omnikit/hooks.json 已存在
同一組待接目錄 6 小時內只背景觸發一次，任何錯誤皆安靜結束（exit 0）。

自我測試：uv run engine/scripts/home_watch.py --selftest
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import homes
import profiles
import statedir

ROOT = Path(__file__).resolve().parents[2]
STATE = statedir.STATE
RETRY = 6 * 3600
BREAKAWAY = 0x01000000


def _active_agents(state: Path) -> list[str]:
    for fname in ("config.json", "agents.json"):
        try:
            doc = json.loads((state / fname).read_text(encoding="utf-8-sig"))
            ag = doc.get("agents") if isinstance(doc, dict) else None
            if isinstance(ag, list) and ag:
                return [a for a in ag if a in homes.AGENTS]
        except (OSError, ValueError):
            pass
    return []


def _is_connected_dir(f: homes.Found) -> bool:
    if f.instance:
        if not f.path.is_dir():
            return True  # T3 尚未啟動建立該實例目錄，等建立後再補薄 plugin
        return (f.path / "config" / "plugins" / "omnikit" / "hooks.json").is_file()
    md = f.path / ("CLAUDE.md" if f.agent == "claude-code" else "AGENTS.md")
    return md.is_file() and bool(profiles.BLOCK.search(profiles.text(md)))


def pending(state: Path, found: list[homes.Found]) -> list[homes.Found]:
    agents = _active_agents(state)
    if not agents:
        return []
    return [f for f in found if (f.writable or f.instance) and f.agent in agents and not _is_connected_dir(f)]


def _same(a: str, b: str) -> bool:
    return a.replace("\r\n", "\n").strip() == b.replace("\r\n", "\n").strip()


def rules_drift(state: Path, home: Path, environ=None, data: Path | None = None) -> list[str]:
    """Codex 與 Antigravity 拿的是組好的規則副本（Claude Code 用 @import，改了就生效；只比對要不要接 onboarding.md）。
    個人 profile 不進 repo 之後（2026-11-27），改個人規則不會再經過 commit 的 git hook 同步，所以開新對話時比對一次：副本跟現在組出來的不同，
    回傳過期的（位置, 應有內容的摘要）。沒接上、找不到 profile 或讀不到都當作沒有過期（不擋開場）。"""
    agents = _active_agents(state)
    if not any(a in agents for a in ("claude-code", "codex", "antigravity")):
        return []
    data = data or (_resolve_repo_root(state) / "data")
    try:
        name, _ = profiles.resolve(data, state)
    except SystemExit:
        return []
    stale = []
    if "claude-code" in agents:
        # Claude 用 @import，規則內容改了自己就生效；只有「要不要接 onboarding.md」會讓區塊本身過期
        # （「先不要」的暫緩到期，2026-11-27）。只看主設定目錄，背景 sync 會把其他設定目錄一起接好
        md = home / ".claude" / "CLAUDE.md"
        found = profiles.BLOCK.search(profiles.text(md)) if md.is_file() else None
        base = profiles.folder(data, state, name)
        want = bool(base) and profiles.onboarding_active(state, name) and (base / profiles.ONBOARDING).is_file()
        if found and (profiles.ONBOARDING in found.group(0)) != want:
            stale.append((str(md), hashlib.sha256(f"onboarding:{want}".encode()).hexdigest()[:12]))
    targets = []
    if "codex" in agents:
        want = profiles.content_block(profiles.compose(data, state, name))
        dirs = [home / ".codex", *profiles.codex_homes(home, environ)]  # codex_homes 只回 ~/.codex 以外的
        targets += [(d / "AGENTS.md", want) for d in dict.fromkeys(dirs)]
    if "antigravity" in agents:
        gem = home / ".gemini"
        targets += [(gem / "AGENTS.md", profiles.content_block(profiles.compose_shared(data))),
                    (gem / "GEMINI.md", profiles.content_block(profiles.compose_personal(data, state, name)))]
    for path, want in targets:
        found = profiles.BLOCK.search(profiles.text(path)) if path.is_file() else None
        if found and not _same(found.group(0), want):  # 沒有受管區塊的是「沒接上」，交給 pending 與 doctor
            stale.append((str(path), hashlib.sha256(want.encode("utf-8")).hexdigest()[:12]))
    return stale


def due(state: Path, keys: list[str], now: float) -> bool:
    try:
        last = json.loads((state / "home_watch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    return not (isinstance(last, dict) and last.get("keys") == sorted(keys) and now - last.get("at", 0) < RETRY)


def _resolve_repo_root(state: Path) -> Path:
    try:
        doc = json.loads((state / "config.json").read_text(encoding="utf-8-sig"))
        raw = doc.get("repo") if isinstance(doc, dict) else None
        if isinstance(raw, str) and raw.strip():
            cand = Path(raw)
            if (cand / "engine" / "scripts" / "sync.py").is_file():
                return cand
    except (OSError, ValueError):
        pass
    return ROOT


def start_sync(state: Path, popen=subprocess.Popen):
    uv = os.environ.get("UV") or shutil.which("uv") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "uv" / "uv.exe")
    repo_root = _resolve_repo_root(state)
    cmd = [uv, "run", "--quiet", str(repo_root / "engine" / "scripts" / "sync.py"), "sync"]
    state.mkdir(parents=True, exist_ok=True)
    log_path = state / "home_watch.log"
    with log_path.open("ab") as hdr:
        hdr.write(f"\n== {time.strftime('%Y-%m-%d %H:%M:%S')} sync.py sync（home_watch）\n".encode())
    log = log_path.open("ab")
    opts = {"cwd": str(repo_root), "stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT}
    if os.name != "nt":
        return popen(cmd, start_new_session=True, **opts)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        return popen(cmd, creationflags=flags | BREAKAWAY, **opts)
    except OSError:
        return popen(cmd, creationflags=flags, **opts)


def check(state=STATE, home=homes.HOME, environ=None, now=None, popen=subprocess.Popen):
    now = time.time() if now is None else now
    legacy = statedir.pending(state, environ)
    if legacy:
        keys = sorted(f"legacy:{path}" for _, path, _ in legacy)
        if not due(state, keys, now):
            return None
        state.mkdir(parents=True, exist_ok=True)
        (state / "home_watch.json").write_text(json.dumps({"keys": keys, "at": now}, ensure_ascii=False), encoding="utf-8")
        start_sync(state, popen)
        where = "、".join(str(path) for _, path, _ in legacy)
        return (f"OmniKit：狀態檔改放 {state}，已在背景把舊位置（{where}）合併過去；"
                f"過程記在 {state / 'home_watch.log'}")
    new = pending(state, homes.discover(home, environ))
    if not new:
        stale = rules_drift(state, home, environ)
        if not stale:
            return None
        keys = sorted(f"rules:{p}:{digest}" for p, digest in stale)  # 規則再改一次就是新的 key，不受 6 小時限制
        if not due(state, keys, now):
            return None
        state.mkdir(parents=True, exist_ok=True)
        (state / "home_watch.json").write_text(json.dumps({"keys": keys, "at": now}, ensure_ascii=False), encoding="utf-8")
        start_sync(state, popen)
        return (f"OmniKit：規則改過，{'、'.join(p for p, _ in stale)} 的副本還是舊的，已在背景重新接上；"
                f"下一段對話起生效。過程記在 {state / 'home_watch.log'}")
    keys = sorted(f.key for f in new)
    if not due(state, keys, now):
        return None
    state.mkdir(parents=True, exist_ok=True)
    (state / "home_watch.json").write_text(json.dumps({"keys": keys, "at": now}, ensure_ascii=False), encoding="utf-8")
    start_sync(state, popen)
    where = "、".join(f.source if f.instance else f"{f.path}（{f.source}）" for f in new)
    return (f"OmniKit：找到還沒接上的設定目錄 {where}，已在背景接上；"
            f"那個帳號下一段對話起就讀得到 OmniKit。過程記在 {state / 'home_watch.log'}")


def selftest():
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as t:
        h, state = Path(t) / "home", Path(t) / "state"
        for d in (".claude", ".claude-kai", ".claude-new"):
            (h / d).mkdir(parents=True)
        t3 = h / ".t3" / "userdata" / "settings.json"
        t3.parent.mkdir(parents=True)
        t3.write_text(json.dumps({"providerInstances": {
            "kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
            "newc": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-new"}},
            "agy_new": {"driver": "antigravity"},
        }}), encoding="utf-8")
        (h / ".claude-kai" / "CLAUDE.md").write_text(f"{profiles.BEGIN}\n@x\n{profiles.END}\n", encoding="utf-8")
        agy_dir = homes.t3_antigravity_dir(h, "agy_new")
        (agy_dir / "config").mkdir(parents=True)

        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)

        ok("未接上（無 config.json）：不動", check(state, h, {}, 0, fake) is None and not calls)
        state.mkdir(parents=True)
        (state / "config.json").write_text(json.dumps({"agents": ["claude-code"]}), encoding="utf-8")
        msg = check(state, h, {}, 1000, fake)
        ok("有尚未接上的 .claude-new：背景跑 sync.py sync，已接上的 .claude-kai 不重報",
           msg is not None and ".claude-new" in msg and ".claude-kai" not in msg.split("，已在")[0]
           and len(calls) == 1 and calls[0][-2:] == [str(ROOT / "engine" / "scripts" / "sync.py"), "sync"])
        ok("同一組 6 小時內不重跑", check(state, h, {}, 1000 + 3600, fake) is None and len(calls) == 1)
        (h / ".claude-new" / "CLAUDE.md").write_text(f"{profiles.BEGIN}\n@x\n{profiles.END}\n", encoding="utf-8")
        ok("補齊受管區塊後不再觸發", check(state, h, {}, 99999, fake) is None)

        (state / "config.json").write_text(json.dumps({"agents": ["claude-code", "antigravity"]}), encoding="utf-8")
        msg2 = check(state, h, {}, 150000, fake)
        ok("T3 新實例目錄缺少 plugins/omnikit 時觸發背景同步", msg2 is not None and "agy_new" in msg2)
        (agy_dir / "config" / "plugins" / "omnikit").mkdir(parents=True)
        (agy_dir / "config" / "plugins" / "omnikit" / "hooks.json").write_text("{}", encoding="utf-8")
        ok("T3 實例補齊薄 plugin 後不再觸發", check(state, h, {}, 300000, fake) is None)

        local = Path(t) / "AppData" / "Local"
        copy = local / "Packages" / "Claude_x" / "LocalCache" / "Local" / "omnikit"
        copy.mkdir(parents=True)
        (copy / "config.json").write_text("{}", encoding="utf-8")
        before = len(calls)
        msg3 = check(state, h, {"LOCALAPPDATA": str(local)}, 400000, fake)
        ok("舊位置有未合併狀態：背景跑 sync.py sync 合併", msg3 is not None and len(calls) == before + 1)

    # 個人 profile 不進 repo 之後：規則副本過期（改了 profile 但沒有 commit 觸發同步）時，開場背景重新接上
    with tempfile.TemporaryDirectory() as t:
        h, state, repo = Path(t) / "home", Path(t) / "state", Path(t) / "repo"
        data = repo / "data"
        (repo / "engine" / "scripts").mkdir(parents=True)
        (repo / "engine" / "scripts" / "sync.py").write_text("", encoding="utf-8")
        (data / "rules").mkdir(parents=True)
        (data / "rules" / "baseline.md").write_text("# 安全底線\n規則版本：t\n", encoding="utf-8")
        (data / "profiles" / "default").mkdir(parents=True)
        (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n第一版\n", encoding="utf-8")
        state.mkdir(parents=True)
        (state / "config.json").write_text(json.dumps({"agents": ["codex", "antigravity"], "repo": str(repo)}), encoding="utf-8")
        codex = h / ".codex" / "AGENTS.md"
        codex.parent.mkdir(parents=True)
        (h / ".gemini").mkdir(parents=True)
        name = "default"

        def deploy():
            codex.write_text(profiles.content_block(profiles.compose(data, state, name)) + "\n# 我自己的\n", encoding="utf-8")
            (h / ".gemini" / "AGENTS.md").write_text(profiles.content_block(profiles.compose_shared(data)), encoding="utf-8")
            (h / ".gemini" / "GEMINI.md").write_text(profiles.content_block(profiles.compose_personal(data, state, name)), encoding="utf-8")

        deploy()
        calls = []
        ok("規則副本與現在組出來的一樣：不觸發", rules_drift(state, h, {}) == []
           and check(state, h, {}, 1000, lambda cmd, **kw: calls.append(cmd)) is None and not calls)
        (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n第二版\n", encoding="utf-8")
        stale = [p for p, _ in rules_drift(state, h, {})]
        msg = check(state, h, {}, 2000, lambda cmd, **kw: calls.append(cmd))
        ok("改了個人規則沒同步：Codex 與 Antigravity 個人副本標成過期，背景跑 sync.py sync（共用副本沒變不報）",
           stale == [str(codex), str(h / ".gemini" / "GEMINI.md")]
           and msg is not None and "已在背景重新接上" in msg and len(calls) == 1 and calls[0][-1] == "sync")
        ok("同一版規則 6 小時內不重跑", check(state, h, {}, 2000 + 60, lambda cmd, **kw: calls.append(cmd)) is None and len(calls) == 1)
        (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n第三版\n", encoding="utf-8")
        ok("規則又改了一次：不受 6 小時限制，再觸發一次",
           check(state, h, {}, 2000 + 120, lambda cmd, **kw: calls.append(cmd)) is not None and len(calls) == 2)
        deploy()
        ok("同步之後不再觸發", check(state, h, {}, 99999, lambda cmd, **kw: calls.append(cmd)) is None and len(calls) == 2)
        codex.write_text("# 只有自己的規則，沒有受管區塊\n", encoding="utf-8")
        ok("沒有受管區塊的不算過期（那是沒接上，交給 doctor）", str(codex) not in [p for p, _ in rules_drift(state, h, {})])

    # 開場破冰（onboarding.md）：Claude 用 @import，只有「要不要接」會讓區塊過期；「先不要」暫緩到期時開場背景接回來
    with tempfile.TemporaryDirectory() as t:
        h, state, repo = Path(t) / "home", Path(t) / "state", Path(t) / "repo"
        data = repo / "data"
        (repo / "engine" / "scripts").mkdir(parents=True)
        (repo / "engine" / "scripts" / "sync.py").write_text("", encoding="utf-8")
        (data / "rules").mkdir(parents=True)
        (data / "rules" / "baseline.md").write_text("# 安全底線\n", encoding="utf-8")
        (data / "profiles" / "default").mkdir(parents=True)
        (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n", encoding="utf-8")
        (data / "profiles" / "default" / profiles.ONBOARDING).write_text("## 第一次使用\n", encoding="utf-8")
        state.mkdir(parents=True)
        (state / "config.json").write_text(json.dumps({"agents": ["claude-code"], "repo": str(repo)}), encoding="utf-8")
        md = h / ".claude" / "CLAUDE.md"
        md.parent.mkdir(parents=True)

        def deploy_claude():
            md.write_text(profiles.claude_block(data, state, "default") + "\n# 我自己的\n", encoding="utf-8")

        deploy_claude()
        ok("破冰：Claude 區塊跟現在該不該接一致，不觸發", rules_drift(state, h, {}) == [])
        profiles.snooze(state)
        ok("破冰：說了先不要但區塊還接著（還沒重新接上），標成過期", [p for p, _ in rules_drift(state, h, {})] == [str(md)])
        deploy_claude()
        ok("破冰：暫緩中重新接上之後不再觸發", profiles.ONBOARDING not in md.read_text(encoding="utf-8")
           and rules_drift(state, h, {}) == [])
        (state / profiles.ONBOARDING_STATE).write_text('{"snoozed_until": "2000-01-01"}', encoding="utf-8")
        calls = []
        msg = check(state, h, {}, 5000, lambda cmd, **kw: calls.append(cmd))
        ok("破冰：暫緩到期，開場背景重新接上", msg is not None and len(calls) == 1 and calls[0][-1] == "sync")
        md.write_text("# 只有自己的規則\n", encoding="utf-8")
        ok("破冰：沒有受管區塊的不算過期", rules_drift(state, h, {}) == [])
    print("home_watch selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def main():
    if "--selftest" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        return selftest()
    try:
        sys.stdin.read()
        msg = check()
        if msg:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
