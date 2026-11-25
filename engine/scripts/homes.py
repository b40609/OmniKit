# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""找出這台每個 agent 實際在用的設定目錄（明確清單制，不使用 ~/.claude* 萬用字元掃描）。

為什麼改用明確清單（2026-11-25 Fable Stage 2 洞 2 修補）：
萬用字元掃描（如 ~/.claude*）容易誤中其他工具的資料目錄（如 ~/.claude-mem）或設定檔（~/.claude.json）。
因此 Claude Code 與 Codex 的額外設定目錄只從三個確定性來源讀取：
1. 目前行程的環境變數：CLAUDE_CONFIG_DIR、CODEX_HOME
2. OmniKit 本機設定檔：~/.omnikit/config.json 的 claude_homes、codex_homes 陣列
3. T3 Code 設定檔（~/.t3/userdata/settings.json）明確宣告的 providerInstances config.homePath

T3 Code 的 Antigravity 實例：
每個實例的設定目錄為 ~/.t3/userdata/providers/antigravity/<sha256(實例 id)>。
同步器透過列舉 providers/antigravity/ 底下的實例目錄與 settings.json 宣告實例取聯集；
若 ~/.t3 存在且已初始化，卻列舉到 0 個 Antigravity 實例目錄，回報異常不沉默。

用法：uv run engine/scripts/homes.py          列出找到的設定目錄
      uv run engine/scripts/homes.py --selftest
"""
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()
AGENTS = ("claude-code", "codex", "antigravity")
DEFAULTS = {"claude-code": ".claude", "codex": ".codex", "antigravity": ".gemini"}
ENV_VARS = {"claude-code": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME"}
T3_DRIVERS = {"claudeAgent": "claude-code", "codex": "codex", "antigravity": "antigravity"}
T3_DEFAULT_ANTIGRAVITY = "antigravity"


@dataclass(frozen=True)
class Found:
    agent: str
    path: Path
    source: str
    writable: bool = True
    instance: str | None = None

    @property
    def key(self):
        return key(self.agent, self.path)


def key(agent, path):
    return f"{agent}@{path}"


def expand_home(value, home):
    value = value.strip()
    if value == "~" or value.startswith(("~/", "~\\")):
        return home / value[2:] if len(value) > 1 else home
    return Path(os.path.expandvars(value))


def canonical(path):
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def state_dir_for(home, environ=None):
    environ = os.environ if environ is None else environ
    override = environ.get("OMNIKIT_STATE_DIR", "").strip()
    if override and home == HOME:
        return Path(override)
    return home / ".omnikit"


def from_omnikit_config(home, environ=None):
    """讀取 ~/.omnikit/config.json 明確列出的 claude_homes 與 codex_homes。"""
    cfg_path = state_dir_for(home, environ) / "config.json"
    try:
        doc = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(doc, dict):
        return []
    out = []
    for field_name, agent in (("claude_homes", "claude-code"), ("codex_homes", "codex")):
        items = doc.get(field_name)
        if not isinstance(items, list):
            continue
        for raw in items:
            if isinstance(raw, str) and raw.strip():
                p = expand_home(raw, home)
                out.append(Found(agent, p, f"~/.omnikit/config.json 的 {field_name}"))
    return out


def t3_initialized(home):
    userdata = home / ".t3" / "userdata"
    return (
        (userdata / "settings.json").is_file()
        or (userdata / "environment-id").is_file()
        or (userdata / "providers" / "antigravity").is_dir()
    )


def t3_instances(home):
    """讀取 T3 Code 的 providerInstances，並補上預設 antigravity 實例。"""
    userdata = home / ".t3" / "userdata"
    try:
        doc = json.loads((userdata / "settings.json").read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if not t3_initialized(home):
            return {}
        doc = {}
    except (OSError, ValueError):
        return {}
    instances = doc.get("providerInstances", {}) if isinstance(doc, dict) else None
    if instances is None and isinstance(doc, dict):
        instances = {}
    if not isinstance(instances, dict):
        return {}
    if T3_DEFAULT_ANTIGRAVITY in instances:
        return instances
    return {**instances, T3_DEFAULT_ANTIGRAVITY: {"driver": "antigravity"}}


def t3_antigravity_dir(home, iid):
    return home / ".t3" / "userdata" / "providers" / "antigravity" / hashlib.sha256(str(iid).encode("utf-8")).hexdigest()


def t3_antigravity_profiles(home):
    """列舉 T3 的 Antigravity 實例目錄：結合 providers/antigravity/* 實體目錄與 settings.json 宣告。
    回傳 (實例 Found 串列, 錯誤訊息或 None)。若 ~/.t3 已初始化但列舉出 0 個實例則回傳錯誤不沉默。"""
    t3_root = home / ".t3"
    if not t3_root.is_dir() or not t3_initialized(home):
        return [], None
    prov_root = t3_root / "userdata" / "providers" / "antigravity"
    by_hash = {}
    for iid, inst in t3_instances(home).items():
        if isinstance(inst, dict) and inst.get("driver") == "antigravity":
            d = t3_antigravity_dir(home, iid)
            by_hash[d.name.lower()] = (str(iid), d, f"T3 Code 的 {iid} 實例")
    out = []
    seen = set()
    if prov_root.is_dir():
        for child in sorted(prov_root.iterdir()):
            if not child.is_dir():
                continue
            k = child.name.lower()
            seen.add(k)
            if k in by_hash:
                iid, _, src = by_hash[k]
                out.append(Found("antigravity", child, src, False, iid))
            else:
                out.append(Found("antigravity", child, f"T3 Code 實例目錄 {child.name[:12]}", False, child.name))
    for k, (iid, d, src) in by_hash.items():
        if k not in seen:
            out.append(Found("antigravity", d, src, False, iid))
    if not out:
        return [], f"偵測到 {t3_root}，但列舉不到任何 Antigravity 實例（T3 設定損毀或內部目錄版面已變更）"
    return out, None


def from_t3(home):
    out = []
    for iid, inst in t3_instances(home).items():
        if not isinstance(inst, dict) or inst.get("driver") not in T3_DRIVERS:
            continue
        agent = T3_DRIVERS[inst["driver"]]
        if agent == "antigravity":
            continue
        config = inst.get("config") if isinstance(inst.get("config"), dict) else {}
        if isinstance(config.get("homePath"), str) and config["homePath"].strip():
            out.append(Found(agent, expand_home(config["homePath"], home), f"T3 Code 的 {iid} 實例"))
    agy_found, _ = t3_antigravity_profiles(home)
    out.extend(agy_found)
    return out


LAUNCHERS = (from_omnikit_config, from_t3)


def discover(home=HOME, environ=None):
    """預設目錄以外、由明確清單宣告的設定目錄（絕不掃描 ~/.claude-mem 等工具目錄）。"""
    environ = os.environ if environ is None else environ
    found = [Found(agent, expand_home(environ[var], home), f"環境變數 {var}")
             for agent, var in ENV_VARS.items() if environ.get(var, "").strip()]
    for launcher in LAUNCHERS:
        found += launcher(home, environ) if launcher is from_omnikit_config else launcher(home)
    seen = {os.path.normcase(str(canonical(home / d))) for d in DEFAULTS.values()}
    # 明確防禦：永遠排除 ~/.claude-mem 與非目錄檔案
    blocked = {os.path.normcase(str(canonical(home / ".claude-mem")))}
    out = []
    for f in found:
        path = canonical(f.path)
        name = os.path.normcase(str(path))
        if name in seen or name in blocked or path.is_file():
            continue
        if path.is_dir() or f.instance:
            seen.add(name)
            out.append(Found(f.agent, path, f.source, f.writable, f.instance))
    return out


def extra(agent, home=HOME, environ=None, found=None):
    found = discover(home, environ) if found is None else found
    return [f.path for f in found if f.agent == agent and f.writable]


def selftest():
    fails = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            fails.append(name)

    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        for d in (".claude", ".codex", ".gemini", ".claude-kai", ".claude-retis", ".claude-unlisted", ".claude-mem",
                  ".codex-work", "envclaude", ".omnikit"):
            (h / d).mkdir(parents=True)
        for f in (".claude-unlisted/.claude.json", ".claude-mem/settings.json", ".claude.json"):
            (h / f).write_text("{}", encoding="utf-8")
        (h / ".omnikit" / "config.json").write_text(
            json.dumps({"claude_homes": ["~/.claude-mem"], "codex_homes": ["~/.codex-work"]}), encoding="utf-8"
        )
        t3 = h / ".t3" / "userdata" / "settings.json"
        t3.parent.mkdir(parents=True)
        t3.write_text(json.dumps({"providerInstances": {
            "claudeAgent": {"driver": "claudeAgent"},
            "kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
            "retis": {"driver": "claudeAgent", "config": {"homePath": str(h / ".claude-retis")}},
            "same": {"driver": "claudeAgent", "config": {"homePath": "~/.claude"}},
            "gone": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-gone"}},
            "agy": {"driver": "antigravity"},
        }}), encoding="utf-8")
        agy = h / ".t3" / "userdata" / "providers" / "antigravity" / hashlib.sha256(b"agy").hexdigest()
        agy.mkdir(parents=True)
        found = discover(h, {"CLAUDE_CONFIG_DIR": str(h / "envclaude"), "CODEX_HOME": str(h / ".codex")})
        names = [(f.agent, f.path.name, f.writable) for f in found]
        agy0 = hashlib.sha256(b"antigravity").hexdigest()
        check("明確清單制：未宣告的 .claude-unlisted 與工具目錄 .claude-mem 絕不誤入",
              names == [
                  ("claude-code", "envclaude", True),
                  ("codex", ".codex-work", True),
                  ("claude-code", ".claude-kai", True),
                  ("claude-code", ".claude-retis", True),
                  ("antigravity", agy.name, False),
                  ("antigravity", agy0, False),
              ])
        check("T3 Antigravity 實例列舉正常且無錯誤", t3_antigravity_profiles(h)[1] is None)
        t3.write_text("{壞掉", encoding="utf-8")
        agy.rmdir()
        (h / ".t3" / "userdata" / "providers" / "antigravity").rmdir()
        _, err = t3_antigravity_profiles(h)
        check("~/.t3 存在但設定損毀導致列舉 0 個實例時明確回傳錯誤不沉默", err is not None)
    print("homes selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--selftest" in sys.argv:
        return selftest()
    found = discover()
    if not found:
        print("只有預設的設定目錄（~/.claude、~/.codex、~/.gemini）")
    for f in found:
        note = "" if f.writable else "（T3 Antigravity 實例目錄）"
        print(f"{f.agent}\t{f.path}\t{f.source}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
