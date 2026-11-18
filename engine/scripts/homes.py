# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""找出這台每個 agent 實際在用的設定目錄：預設的 ~/.claude、~/.codex、~/.gemini 以外，多帳號與啟動器另外指定的也算。

為什麼要找：agent 只讀「自己這個設定目錄」裡的規則、skills、MCP 與 hook。換了目錄（CLAUDE_CONFIG_DIR、
CODEX_HOME、T3 Code 每個實例的 homePath）就完全讀不到預設目錄裡的 OmniKit，而且不會報錯。
2026-11-17 實際發生過：T3 Code 的 Kai、retis 兩個 Claude 帳號各用自己的目錄，OmniKit 規則一條都沒載入。
所以安裝、同步、doctor、開新對話時的檢查（home_watch.py）都從這裡拿清單，不各自寫死路徑。

來源（由上往下找，同一個目錄只留第一次找到的）：
1. 這個行程的環境變數：CLAUDE_CONFIG_DIR、CODEX_HOME
2. 已知啟動器的設定：T3 Code（~/.t3/userdata/settings.json 的 providerInstances）
3. 掃 home 底下的命名慣例，用特徵檔認（只看檔案在不在，不讀內容）：
   - Claude：~/.claude-*、~/.ccs/instances/*，裡面要有 .claude.json（Claude Code 在設定目錄裡建的）
   - Codex：~/.codex-*，裡面要有 config.toml，加上 auth.json 或 sessions/
   ~/.claude-mem、~/.codex-chatgpt-web 這類別的工具的資料夾沒有特徵檔，不會被當成設定目錄。
新的啟動器在 LAUNCHERS 加一個讀法；新的命名慣例在 SCANS 加一行。

T3 Code 的 Antigravity 實例比較特別：每個實例的設定目錄是 ~/.t3/userdata/providers/antigravity/<sha256(實例 id)>，
走 ACP 模式，不讀任何規則檔（GEMINI.md、hooks.json 都不載入；只吃 T3 在 session/new 傳的 systemPrompt），
T3 也刻意讓它的 mcp_config.json 保持空的（有 MCP 或 hooks 的實例，T3 會停用它的文字生成）。
所以這類目錄 writable=False、instance=實例 id：不寫目錄裡的檔，改由 t3_acp.py 把實例的 Binary path 指到
OmniKit 的轉接程式（acp_shim.py），開新對話時帶入規則。T3 剛加的實例可能還沒建目錄，也照樣列出來；
settings.json 沒列的預設實例（id 是 antigravity，T3 自己補的）也算。

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
# T3 Code 的 driver → agent
T3_DRIVERS = {"claudeAgent": "claude-code", "codex": "codex", "antigravity": "antigravity"}
# 掃描：(agent, home 底下的 glob, 特徵：全部要有的, 至少要有一個的)
SCANS = (
    ("claude-code", ".claude-*", (".claude.json",), ()),
    ("claude-code", ".ccs/instances/*", (".claude.json",), ()),
    ("codex", ".codex-*", ("config.toml",), ("auth.json", "sessions")),
)


@dataclass(frozen=True)
class Found:
    agent: str
    path: Path
    source: str  # 在哪裡找到的，給人看
    writable: bool = True  # False：這種目錄不讀規則檔（T3 的 Antigravity），不寫目錄裡的檔
    instance: str | None = None  # T3 Code 的 Antigravity 實例 id（t3_acp.py 用它接上轉接程式）

    @property
    def key(self):
        return key(self.agent, self.path)


def key(agent, path):
    """其他設定目錄在 agents.json 的 key：<agent>@<目錄>（skills、MCP、homes 的記錄都用它）。"""
    return f"{agent}@{path}"


def expand_home(value, home):
    value = value.strip()
    if value == "~" or value.startswith(("~/", "~\\")):
        return home / value[2:] if len(value) > 1 else home
    return Path(os.path.expandvars(value))


def canonical(path):
    """同一個目錄只算一次：解析連結、統一大小寫與斜線（Windows 上大小寫不同也是同一個）。"""
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


T3_DEFAULT_ANTIGRAVITY = "antigravity"


def t3_instances(home):
    """T3 Code 的 providerInstances，加上 T3 自己補的預設 Antigravity 實例：settings.json 沒列，T3 也會用
    {"driver": "antigravity"} 開一個 id 是 antigravity 的（server.asar 的 deriveProviderInstanceConfigMap；
    內建 driver 只有 ACP Registry 沒有預設實例）。T3 只存跟預設不同的設定，還沒改過設定就沒有 settings.json，
    這時看 ~/.t3/userdata/environment-id 判斷有沒有跑過 T3。沒裝或設定壞掉就是空的（T3 讀不懂設定時也只用預設）。"""
    userdata = home / ".t3" / "userdata"
    try:
        doc = json.loads((userdata / "settings.json").read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if not (userdata / "environment-id").is_file():
            return {}
        doc = {}
    except (OSError, ValueError):
        return {}
    instances = doc.get("providerInstances", {}) if isinstance(doc, dict) else None
    if instances is None and isinstance(doc, dict):
        instances = {}
    if not isinstance(instances, dict):  # 格式不對：T3 也讀不懂、只用預設，OmniKit 不碰
        return {}
    if T3_DEFAULT_ANTIGRAVITY in instances:
        return instances
    return {**instances, T3_DEFAULT_ANTIGRAVITY: {"driver": "antigravity"}}


def t3_antigravity_dir(home, iid):
    """T3 Code 給 Antigravity 實例的設定目錄（GEMINI_HOME）：providers/antigravity/<sha256(實例 id)>。"""
    return home / ".t3" / "userdata" / "providers" / "antigravity" / hashlib.sha256(str(iid).encode("utf-8")).hexdigest()


def from_t3(home):
    """T3 Code：Claude 與 Codex 實例的 homePath（沒設就是預設目錄）；Antigravity 實例各有一個 ACP 設定目錄。
    Codex 的 authOverlay 模式另有 shadowHomePath，但它把 log、memories、tmp 以外的東西都連回 homePath，
    接上 homePath 就夠了。"""
    out = []
    for iid, inst in t3_instances(home).items():
        if not isinstance(inst, dict) or inst.get("driver") not in T3_DRIVERS:
            continue
        agent = T3_DRIVERS[inst["driver"]]
        config = inst.get("config") if isinstance(inst.get("config"), dict) else {}
        source = f"T3 Code 的 {iid} 實例"
        if agent == "antigravity":
            out.append(Found(agent, t3_antigravity_dir(home, iid), source, False, str(iid)))
        elif isinstance(config.get("homePath"), str) and config["homePath"].strip():
            out.append(Found(agent, expand_home(config["homePath"], home), source))
    return out


LAUNCHERS = (from_t3,)


def from_scans(home):
    out = []
    for agent, pattern, need_all, need_any in SCANS:
        for path in sorted(home.glob(pattern)):
            if path.is_dir() and all((path / n).exists() for n in need_all) \
                    and (not need_any or any((path / n).exists() for n in need_any)):
                out.append(Found(agent, path, f"掃描 ~/{pattern}"))
    return out


def discover(home=HOME, environ=None):
    """這台預設目錄以外、實際存在的 agent 設定目錄，依找到的順序。"""
    environ = os.environ if environ is None else environ
    found = [Found(agent, expand_home(environ[var], home), f"環境變數 {var}")
             for agent, var in ENV_VARS.items() if environ.get(var, "").strip()]
    for launcher in LAUNCHERS:
        found += launcher(home)
    found += from_scans(home)
    seen = {os.path.normcase(str(canonical(home / d))) for d in DEFAULTS.values()}
    out = []
    for f in found:
        path = canonical(f.path)
        name = os.path.normcase(str(path))
        if name not in seen and (path.is_dir() or f.instance):
            seen.add(name)
            out.append(Found(f.agent, path, f.source, f.writable, f.instance))
    return out


def extra(agent, home=HOME, environ=None, found=None):
    """某個 agent 要接上 OmniKit 的其他設定目錄（writable 的）。"""
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
        for d in (".claude", ".codex", ".gemini", ".claude-kai", ".claude-retis", ".claude-work", ".claude-mem",
                  ".codex-work", ".codex-chatgpt-web", ".codex-empty", "envclaude", ".ccs/instances/a"):
            (h / d).mkdir(parents=True)
        for f in (".claude-work/.claude.json", ".ccs/instances/a/.claude.json", ".claude-mem/settings.json",
                  ".codex-work/config.toml", ".codex-work/auth.json", ".codex-chatgpt-web/config.json",
                  ".codex-empty/config.toml"):
            (h / f).write_text("{}", encoding="utf-8")
        t3 = h / ".t3" / "userdata" / "settings.json"
        t3.parent.mkdir(parents=True)
        t3.write_text(json.dumps({"providerInstances": {
            "claudeAgent": {"driver": "claudeAgent"},
            "kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
            "retis": {"driver": "claudeAgent", "config": {"homePath": str(h / ".claude-retis")}},
            "same": {"driver": "claudeAgent", "config": {"homePath": "~/.claude"}},
            "gone": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-gone"}},
            "codex": {"driver": "codex"},
            "agy": {"driver": "antigravity"},
            "agy2": {"driver": "antigravity"},
            "odd": {"driver": "someNewDriver", "config": {"homePath": "~/.claude-work"}}}}), encoding="utf-8")
        agy = h / ".t3" / "userdata" / "providers" / "antigravity" / hashlib.sha256(b"agy").hexdigest()
        agy.mkdir(parents=True)
        found = discover(h, {"CLAUDE_CONFIG_DIR": str(h / "envclaude"), "CODEX_HOME": str(h / ".codex")})
        names = [(f.agent, f.path.name, f.writable) for f in found]
        agy2, agy0 = hashlib.sha256(b"agy2").hexdigest(), hashlib.sha256(b"antigravity").hexdigest()
        check("環境變數、T3、掃描都找到，依序；預設目錄、不存在的、沒有特徵檔的、不認得的 driver 不算",
              names == [("claude-code", "envclaude", True), ("claude-code", ".claude-kai", True),
                        ("claude-code", ".claude-retis", True), ("antigravity", agy.name, False), ("antigravity", agy2, False),
                        ("antigravity", agy0, False),
                        ("claude-code", ".claude-work", True), ("claude-code", "a", True), ("codex", ".codex-work", True)])
        check("T3 的 Antigravity 實例記實例 id；T3 還沒建目錄的、T3 自己補的預設實例（antigravity）也列",
              [f.instance for f in found if f.agent == "antigravity"] == ["agy", "agy2", "antigravity"]
              and all(f.instance is None for f in found if f.agent != "antigravity"))
        bare = h / "bare"
        (bare / ".t3" / "userdata").mkdir(parents=True)
        never_ran = t3_instances(bare)
        (bare / ".t3" / "userdata" / "environment-id").write_text("x", encoding="utf-8")
        check("T3 裝了但還沒有 settings.json：沒跑過 T3 不算；跑過（有 environment-id）就有預設的 antigravity 實例",
              never_ran == {} and t3_instances(bare) == {"antigravity": {"driver": "antigravity"}})
        check("T3 的 .claude-kai 沒有 .claude.json 也算（啟動器明講用它）；掃描到同一個不重複",
              sum(1 for f in found if f.path.name == ".claude-kai") == 1)
        check("來源寫清楚", found[0].source == "環境變數 CLAUDE_CONFIG_DIR" and found[1].source == "T3 Code 的 kai 實例")
        check("extra 只回 writable 的", [p.name for p in extra("antigravity", found=found)] == []
              and [p.name for p in extra("codex", found=found)] == [".codex-work"])
        check("key 跟 agents.py 的記錄一樣是 <agent>@<目錄>", found[1].key == f"claude-code@{h.resolve() / '.claude-kai'}")
        same_case = discover(h, {"CLAUDE_CONFIG_DIR": str(h / ".CLAUDE-KAI")}) if os.name == "nt" else found
        check("Windows：大小寫不同也是同一個目錄", sum(1 for f in same_case if f.path.name.lower() == ".claude-kai") == 1)
        t3.write_text("{壞掉", encoding="utf-8")
        check("T3 設定壞掉不會失敗，只是少了 T3 的", [f.path.name for f in discover(h, {})]
              == [".claude-work", "a", ".codex-work"])
        check("什麼都沒有就是空的", discover(h / "nobody", {}) == [])
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
        note = "" if f.writable else "（ACP 模式不讀規則檔，由 t3_acp.py 接上轉接程式）"
        print(f"{f.agent}\t{f.path}\t{f.source}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
