# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""把 OmniKit 接到三個 agent（Claude Code、Codex、Antigravity）：規則、skills 與 MCP，不經過 skillshare。

以前靠 skillshare 同步，但公司電腦的防毒會擋下它：允許的通知要剛好盯著畫面才按得到，錯過就擋，
git hook 與 agent 在背景同步時常失敗。支援的 agent 固定是這三個，所以改由這支腳本自己接。

- 規則：交給 profiles.py（Claude 用 import，Codex 整份複製，Antigravity 在 GEMINI.md 加受管區塊）
- skills：engine/skills 的每個 skill，profile 的訪談答案不要的除外（見 profiles.OPTIONAL_SKILLS）
  - Claude Code：~/.claude/skills/<名稱> 用資料夾連結，改完馬上生效；建不起來就改用複製
  - Codex：~/.agents/skills/<名稱>，用複製
  - Antigravity：~/.gemini/config/skills/<名稱>，用複製：Antigravity 不跟隨資料夾連結。它的全域 skill 只讀
    這裡（App、IDE 與 CLI 共用），.agents/skills 只在專案資料夾裡有效（https://antigravity.google/docs/skills.md）。
    舊版把 Antigravity 也裝到 ~/.agents/skills，它其實讀不到；那份 Codex 還在用，記錄改當 Codex 的
  - 複製品裡放 .omnikit.json，記來源、repo 位置與內容雜湊；內容變了才重新複製
- MCP：data/mcp/servers.yaml 的 server，只動 OmniKit 管的欄位（command、args、env 與 options 給的）
  - Claude Code：claude mcp add-json -s user（找不到 claude 指令才直接改 ~/.claude.json）
  - Codex：~/.codex/config.toml 的 [mcp_servers.<名稱>]，原地換掉 OmniKit 管的欄位；使用者加的欄位與
    其他子表格（例如工具核准紀錄）留著。寫入前用 tomllib 比對，除了這些 server 什麼都沒變才寫
  - Antigravity：~/.gemini/config/mcp_config.json，不寫 BOM（Antigravity 讀到 BOM 會整份失敗）
  - 帳本：agents.json 記每個 server 寫入時、OmniKit 管的欄位的雜湊。同步前先比對，使用者改過的、
    OmniKit 加過但被移除的、同名但不是 OmniKit 的，都算衝突：問（--ask），或略過那個 server 並印一行，
    規則、skills 與其他 server 照常寫。用 resolve 決定要用誰的設定
  - 免問核准的欄位（Codex 的 default_tools_approval_mode）：同事版要本人同意才寫（approvals，見 edition.py）

其他設定目錄（多帳號、啟動器另外指定的，homes.py 找）：
- Claude Code（CLAUDE_CONFIG_DIR、T3 Code 的 homePath、~/.claude-* 等）：規則區塊、skills 連結、
  MCP（<目錄>/.claude.json，claude 指令帶 CLAUDE_CONFIG_DIR）、權限規則與 hook（claude_allow.py）
- Claude Code 的其他設定目錄也同步使用者自己裝在 ~/.claude 的 skill（連結）與啟用中的 plugin（claude plugin install，
  CLAUDE_CONFIG_DIR 指過去），見下面「~/.claude 使用者自己的 skill 與 plugin」那段
- Codex（CODEX_HOME 等）：規則區塊（<目錄>/AGENTS.md）、MCP（<目錄>/config.toml）；skills 在 ~/.agents/skills，共用
- T3 Code 的 Antigravity 實例：ACP 模式不讀規則檔；t3_acp.py 把實例的 Binary path 指到 OmniKit 的轉接程式
  （acp_shim.py，放在 ~/.omnikit/acp），開新對話時帶入 ~/.gemini/GEMINI.md
記錄的 key 是 <agent>@<目錄>。install 時接上當時找得到的；之後新增的，sync 會接上
（home_watch.py 在開新對話時發現新的目錄就在背景跑 sync）。

接上了哪些 agent、管了哪些 skills 與 MCP server、接上了哪些其他設定目錄（homes），
記在 ~/.omnikit/agents.json（狀態資料夾，見 statedir.py）；
同步只動記錄裡的 agent，移除時只拿掉 OmniKit 的東西，同名但不是 OmniKit 的不碰。
會寫入的指令（connect、sync、resolve、approvals、disconnect）先把舊位置（%LOCALAPPDATA%\\omnikit，以及
Claude 桌面版這類封裝的 app 轉存的副本）的狀態合併進 ~/.omnikit；sync 有搬到東西時，也用新位置重新接上規則。

用法：
  uv run engine/scripts/agents.py connect [--profile <名稱>] [--agents claude-code,codex,antigravity] [--ask]
  uv run engine/scripts/agents.py sync [--skills] [--mcp] [--plugins] [--ask]
  uv run engine/scripts/agents.py resolve <名稱> --use-omnikit|--keep-mine [--agent <agent>]
  uv run engine/scripts/agents.py approvals [--ask] [--grant <名稱>] [--revoke <名稱>]
  uv run engine/scripts/agents.py disconnect
  uv run engine/scripts/agents.py status
  uv run engine/scripts/agents.py --selftest
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_allow  # noqa: E402  Claude Code 的免問權限規則
import codex_hooks  # noqa: E402  讀寫 config.toml 時保留原本的換行
import edition  # noqa: E402  維護者版或同事版，以及免問核准的個人同意
import homes  # noqa: E402  這台每個 agent 在用的設定目錄
import profiles  # noqa: E402
import statedir  # noqa: E402  狀態資料夾 ~/.omnikit，以及從舊位置搬過來
import t3_acp  # noqa: E402  T3 Code 的 Antigravity 實例接上轉接程式
import validate  # noqa: E402
from fsretry import flaky, hold, retry  # noqa: E402  防毒短暫鎖住檔案時等一下再試（FR-34）

AGENTS = ("claude-code", "codex", "antigravity")
SHORT = {"claude-code": "claude", "codex": "codex", "antigravity": "antigravity"}
NAMES = profiles.NAMES
MARKER = ".omnikit.json"
IGNORE = ("__pycache__", MARKER, "*.pyc")
MCP_MARK = "# OmniKit：MCP server（agents.py 依 data/mcp/servers.yaml 寫入）"
TABLE = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:"((?:[^"\\]|\\.)*)"|([A-Za-z0-9_-]+))\s*(\.[^\]]*)?\]\s*(?:#.*)?$')
HEADER_LINE = re.compile(r"^\s*\[")
KEY_LINE = re.compile(r'^\s*(?:"((?:[^"\\]|\\.)*)"|([A-Za-z0-9_-]+))\s*=')
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
# 免問核准的欄位：同事版要本人同意才寫（approvals），維護者版照 servers.yaml
APPROVAL_KEYS = {"codex": ("default_tools_approval_mode",)}
RESOLVE = "uv run engine/scripts/agents.py resolve <名稱>"


@dataclass
class Env:
    home: Path
    repo: Path
    state: Path
    skillshare: Path  # 舊版用的 %APPDATA%\skillshare
    claude_cli: list | None = None  # claude 指令；None 表示直接改 ~/.claude.json
    claude_homes: list = field(default_factory=list)  # ~/.claude 以外的 Claude 設定目錄（homes.py）
    codex_homes: list = field(default_factory=list)  # ~/.codex 以外的 Codex 設定目錄（homes.py）
    which: object = shutil.which
    runner: object = None  # 跑 claude plugin 的函式 (cmd, environ) -> (exit, stdout, stderr)；None 用 subprocess（自我測試換成假的）

    @property
    def data(self):
        return self.repo / "data"

    @property
    def skills_src(self):
        return self.repo / "engine" / "skills"

    @property
    def record_file(self):
        return self.state / "agents.json"

    @property
    def rules(self):
        return {"claude-code": self.home / ".claude" / "CLAUDE.md", "codex": self.home / ".codex" / "AGENTS.md",
                "antigravity": self.home / ".gemini" / "GEMINI.md"}

    @property
    def claude_extra_rules(self):
        return [h / "CLAUDE.md" for h in self.claude_homes]

    @property
    def codex_extra_rules(self):
        return [h / "AGENTS.md" for h in self.codex_homes]

    def extra_homes(self, agents):
        """接上的 agent 的其他設定目錄：[(key, agent, 目錄)]。"""
        pairs = [("claude-code", h) for h in self.claude_homes] + [("codex", h) for h in self.codex_homes]
        return [(extra_key(h, a), a, h) for a, h in pairs if a in agents]

    @property
    def skill_dirs(self):
        """每個 agent 的全域 skills 資料夾與放法；key 跟 agent 名稱一樣，也是 agents.json 的 skills 記錄的 key。"""
        return {"claude-code": (self.home / ".claude" / "skills", "link"),
                "codex": (self.home / ".agents" / "skills", "copy"),
                "antigravity": (self.home / ".gemini" / "config" / "skills", "copy"),
                **{extra_key(h): (h / "skills", "link") for h in self.claude_homes}}

    @property
    def claude_json(self):
        return self.home / ".claude.json"

    @property
    def codex_toml(self):
        return self.home / ".codex" / "config.toml"

    @property
    def gemini_mcp(self):
        return self.home / ".gemini" / "config" / "mcp_config.json"


def extra_key(home, agent="claude-code"):
    """其他設定目錄在 skill_dirs 與 agents.json 的 key：<agent>@<目錄>。"""
    return homes.key(agent, home)


def agent_of(key):
    return key.split("@", 1)[0]


def home_of(key):
    """key 是其他設定目錄的：那個目錄；預設的：None。"""
    return Path(key.split("@", 1)[1]) if "@" in key else None


def label_of(key):
    return NAMES[agent_of(key)] + (f"（{key.split('@', 1)[1]}）" if "@" in key else "")


def real_env():
    claude = shutil.which("claude")
    found = homes.discover()
    return Env(home=Path.home(), repo=profiles.ROOT, state=profiles.STATE,
               skillshare=Path(os.environ.get("APPDATA", Path.home())) / "skillshare",
               claude_cli=[claude] if claude else None, claude_homes=homes.extra("claude-code", found=found),
               codex_homes=homes.extra("codex", found=found))


def detect(env):
    h, which = env.home, env.which
    found = []
    if (h / ".claude").is_dir() or which("claude"):
        found.append("claude-code")
    if (h / ".codex").is_dir() or which("codex"):
        found.append("codex")
    if (h / ".gemini" / "config").is_dir() or (h / ".gemini" / "antigravity").is_dir() or which("agy") or which("antigravity") \
            or any(isinstance(i, dict) and i.get("driver") == "antigravity" for i in homes.t3_instances(h).values()):
        found.append("antigravity")  # 只裝了 T3 Code 也算：T3 內建 Antigravity，規則要寫進 ~/.gemini 給轉接程式帶
    return found


def ledger_of(names):
    """帳本 {名稱: {"sha256", "keys"}}。舊版只記名稱（list），雜湊先空著（None），下次同步比對後補上。"""
    if isinstance(names, list):
        return {n: None for n in names if isinstance(n, str)}
    if not isinstance(names, dict):
        return {}
    return {n: e if isinstance(e, dict) and isinstance(e.get("sha256"), str) and isinstance(e.get("keys"), list) else None
            for n, e in names.items()}


def load_record(env):
    try:
        rec = json.loads(env.record_file.read_text(encoding="utf-8"))
        rec = rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        rec = {}
    for key, empty in (("agents", []), ("skills", {}), ("mcp", {}), ("mcp_keep", {}), ("user_skills", {}), ("user_plugins", {})):
        rec.setdefault(key, empty)
    if not isinstance(rec["skills"], dict):
        rec["skills"] = {}
    if "shared" in rec["skills"]:
        # 舊版：~/.agents/skills 記成 Codex 與 Antigravity 共用的 shared。Antigravity 讀不到那裡，
        # 那份只有 Codex 在用，改記成 Codex 的；沒有標記的複製品也才認得出是 OmniKit 放的
        rec["skills"].setdefault("codex", rec["skills"].pop("shared"))
    rec["mcp"] = {agent: ledger_of(names) for agent, names in rec["mcp"].items()} if isinstance(rec["mcp"], dict) else {}
    return rec


def save_record(env, rec):
    rec = {**rec, "mcp_keep": {a: names for a, names in rec.get("mcp_keep", {}).items() if names}}
    if not rec["mcp_keep"]:
        del rec["mcp_keep"]
    profiles.write(env.record_file, json.dumps(rec, ensure_ascii=False, indent=2) + "\n")


# ---- skills ----

def skill_names(src):
    return sorted(p.name for p in src.iterdir() if (p / "SKILL.md").is_file()) if src.is_dir() else []


def tree_hash(folder):
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_file() and not any(part in ("__pycache__", MARKER) for part in rel.parts) and p.suffix != ".pyc":
            h.update(rel.as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def is_link(p):
    return p.is_symlink() or p.is_junction()


def link_target(p):
    t = os.readlink(p)
    return Path(t[4:] if t.startswith("\\\\?\\") else t)


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def make_link(target, link):
    if os.name == "nt":
        import _winapi  # 資料夾連結（junction）不用系統管理員權限
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(p):
    """只拿掉連結本身，連到的資料夾不動。"""
    if p.is_junction():
        os.rmdir(p)
    else:
        p.unlink()


def owned(entry, env, recorded=()):
    """OmniKit 管的：連到 engine/skills 的連結（舊版經過 skillshare 的 _omnikit）、帶 .omnikit.json 的複製品，
    或 agents.json 記錄是 OmniKit 放的（複製品被刪到一半、.omnikit.json 不見了也認得出來）。"""
    if entry.name in recorded:
        return True
    src = env.skills_src.resolve()
    if is_link(entry):
        target = link_target(entry)
        if target.is_relative_to(env.skillshare / "skills" / "_omnikit") or same_path(target.parent, env.skills_src):
            return True
        try:
            return entry.resolve().is_relative_to(src)
        except OSError:
            return False
    try:
        source = json.loads((entry / MARKER).read_text(encoding="utf-8"))["source"]
        return Path(source).resolve().is_relative_to(src)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def present(p):
    return p.exists() or is_link(p)


def writable(path):
    """清掉唯讀：Windows 的資料夾常帶唯讀屬性，帶著就刪不掉（存取被拒）；POSIX 給擁有者讀寫執行。"""
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


def remove_tree(path):
    """刪資料夾（含唯讀的）；有檔案被防毒短暫鎖住時，等一下從剩下的接著刪。"""
    def force(func, p, _exc):
        writable(p)
        writable(os.path.dirname(p))
        func(p)

    retry(shutil.rmtree, path, onexc=force)


def remove_owned(entry):
    if is_link(entry):
        remove_link(entry)
    else:
        remove_tree(entry)


def source_files(src_dir):
    return {p.relative_to(src_dir): p for p in sorted(src_dir.rglob("*")) if p.is_file()
            and not any(part in ("__pycache__", MARKER) for part in p.relative_to(src_dir).parts) and p.suffix != ".pyc"}


def copy_skill(src_dir, dest, env):
    """原地同步成跟 src_dir 一樣：覆寫變了的、補上缺的、刪掉多的。不先整個刪掉，也不複製資料夾屬性
    （engine/skills 的資料夾常帶唯讀屬性，複製過去就刪不掉；有程式開著資料夾時也刪不掉）。
    防毒常在掃描剛複製好的檔案（尤其是 .py）：讀、寫、刪被鎖住時等一下再試（fsretry）。"""
    dest.mkdir(parents=True, exist_ok=True)
    writable(dest)
    wanted = source_files(src_dir)
    for rel, src in wanted.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        writable(target.parent)
        if not target.is_file() or retry(target.read_bytes) != src.read_bytes():
            if target.exists():
                writable(target)
            retry(shutil.copyfile, src, target)
    for p in sorted(dest.rglob("*"), key=lambda x: -len(x.parts)):
        rel = p.relative_to(dest)
        if rel == Path(MARKER) or rel in wanted:
            continue
        if p.is_dir() and not is_link(p):
            if not any(p.iterdir()):
                writable(p)
                retry(p.rmdir)
        else:
            writable(p)
            retry(p.unlink)
    marker = {"source": str(src_dir), "repo": str(env.repo), "hash": tree_hash(src_dir)}
    retry((dest / MARKER).write_text, json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def place_skill(src_dir, dest, mode, env, recorded=()):
    """回傳 unchanged、linked、copied 或 skipped（同名但不是 OmniKit 的，不動）。"""
    if present(dest):
        if not owned(dest, env, recorded):
            return "skipped"
        if mode == "link" and is_link(dest) and same_path(link_target(dest), src_dir):
            return "unchanged"
        if not is_link(dest):
            try:
                if json.loads((dest / MARKER).read_text(encoding="utf-8")).get("hash") == tree_hash(src_dir):
                    return "unchanged"
            except (OSError, ValueError):
                pass
            if mode == "copy":
                copy_skill(src_dir, dest, env)  # 原地更新，不先刪
                return "copied"
        remove_owned(dest)
    if mode == "link":
        try:
            make_link(src_dir, dest)
            return "linked"
        except OSError:
            pass  # 建不起連結就改用複製
    copy_skill(src_dir, dest, env)
    return "copied"


def skill_targets(agents, env=None):
    """要放 skills 的 key；Claude Code 接上時，其他 Claude 設定目錄也放（env 有給才算）。
    Codex 的其他設定目錄不用：Codex 的使用者 skills 在 ~/.agents/skills，不跟著 CODEX_HOME。"""
    keys = [a for a in AGENTS if a in agents]
    if env is not None:
        keys += [k for k, a, _ in env.extra_homes(agents) if k in env.skill_dirs]
    return keys


def profile_skips(env, profile=None):
    """（profile 名稱, 不裝的 skill）。找不到 profile 時全部都裝：少裝比多裝難察覺。"""
    try:
        name, _ = profiles.resolve(env.data, env.state, profile)
    except SystemExit:
        return None, {}
    return name, profiles.skipped_skills(env.data, env.state, name)


def sync_skills(env, agents, rec, profile=None):
    profile_name, skip = profile_skips(env, profile)
    every = skill_names(env.skills_src)
    names = [n for n in every if n not in skip]
    lines = []
    shown = [n for n in skip if n in every]  # repo 裡有的才列
    if shown:
        why = "、".join(dict.fromkeys(skip[n] for n in shown))
        lines.append(f"skills：profile {profile_name} 選了{why}，不裝 {'、'.join(shown)}")
    for key in skill_targets(agents, env):
        folder, mode = env.skill_dirs[key]
        folder.mkdir(parents=True, exist_ok=True)
        placed, skipped, copied_instead = [], [], []
        recorded = set(rec["skills"].get(key, []))
        for name in names:
            status = place_skill(env.skills_src / name, folder / name, mode, env, recorded)
            if status == "skipped":
                skipped.append(name)
                continue
            placed.append(name)
            if mode == "link" and not is_link(folder / name):
                copied_instead.append(name)
        for name in sorted(recorded - set(names)):
            entry = folder / name
            if present(entry) and owned(entry, env, recorded):
                remove_owned(entry)
                lines.append(f"skills：拿掉{'這個 profile 不裝' if name in skip else '已經刪除'}的 {name}（{folder}）")
        rec["skills"][key] = placed
        how = "連結" if mode == "link" else "複製"
        lines.append(f"skills：{label_of(key)} {len(placed)} 個（{how}，{folder}）")
        if copied_instead:
            lines.append(f"  建不起資料夾連結，改用複製：{'、'.join(copied_instead)}")
        for name in skipped:
            lines.append(f"  {folder / name} 已經有同名的 skill，不是 OmniKit 的，沒有動")
    # 沒接上的 agent 的資料夾裡還有 OmniKit 之前放的（例如舊版給 Antigravity 裝在 ~/.agents/skills、這台沒有 Codex）：
    # 不更新也不刪，說一聲；disconnect（uninstall.ps1）會一起拿掉
    for key, names in rec["skills"].items():
        if key in env.skill_dirs and key not in skill_targets(agents, env):
            folder = env.skill_dirs[key][0]
            left = [n for n in names if present(folder / n)]
            if left:
                lines.append(f"skills：{folder} 還有 OmniKit 之前放的 {len(left)} 個 skill，只有 {label_of(key)} 會讀，"
                             f"它沒有接上，所以沒有更新也沒有刪；用不到可以自己刪")
    return lines


# ---- ~/.claude 使用者自己的 skill 與 plugin：同步到其他 Claude 設定目錄 ----
# 2026-11-18：T3 Code 的 retis、Kai 帳號各用 ~/.claude-retis、~/.claude-kai，OmniKit 的規則、skill、hook 都接上了，
# 但使用者自己裝在 ~/.claude 的 skill（unslop 等）與 plugin（claude-mem、floorplan、taste-skill）一個都沒有，
# 規則裡「前端預設 unslop」在那兩個帳號就失效、claude-mem 記憶也不累積。所以把 ~/.claude 當來源同步過去；
# OmniKit 自己的 skill 由 sync_skills 處理，設定檔的其他欄位與金鑰都不碰。可以重跑：缺的補上，已經有的不動。
# - skill：<目錄>/skills/<名稱> 建資料夾連結，連到 ~/.claude/skills/<名稱> 的實際位置（只有一份，改了馬上生效）。
#   名稱 . 開頭、.bak 這類備份、沒有 SKILL.md 的（synced 是 claude.ai 給各帳號各自同步的）不同步；
#   目標已經有同名、指到別處的，不動；~/.claude 拿掉的，只拿掉 OmniKit 建的連結
# - plugin：~/.claude/settings.json 的 enabledPlugins 是 true 的（停用的不同步），用官方的 claude plugin，
#   CLAUDE_CONFIG_DIR 指到那個目錄：缺 marketplace 先 marketplace add（來源照 ~/.claude/plugins/known_marketplaces.json，
#   沒有再看 settings.json 的 extraKnownMarketplaces），再 plugin install -s user。不帶 -y：要跑 marketplace 宣告的
#   指令才能裝的 plugin 要本人確認，失敗就印一行。那個目錄裝了但停用的，當成使用者的選擇不動；
#   ~/.claude 之後停用或移除的，OmniKit 裝的那份停用（不解除安裝，plugin 的資料留著），之後又啟用就再啟用

USER_SKIP = re.compile(r"^\.|\.bak(?:[-_.]|$)|\.orig$|~$", re.I)


def user_source(env):
    return env.home / ".claude"


def mirror_targets(env, agents):
    """要同步使用者 skill 與 plugin 的其他 Claude 設定目錄：[(key, 目錄)]。"""
    return [(k, h) for k, a, h in env.extra_homes(agents) if a == "claude-code" and not same_path(h, user_source(env))]


def user_skills(env, rec):
    """~/.claude/skills 裡使用者自己的 skill：{名稱: 實際位置}。OmniKit 的（連到 engine/skills、記錄裡的）不算。"""
    folder = user_source(env) / "skills"
    if not folder.is_dir():
        return {}
    ours = set(skill_names(env.skills_src)) | set(rec["skills"].get("claude-code", []))
    found = {}
    for p in sorted(folder.iterdir(), key=lambda x: x.name):
        if USER_SKIP.search(p.name) or p.name in ours or not (p / "SKILL.md").is_file() or owned(p, env):
            continue
        found[p.name] = Path(os.path.realpath(p))
    return found


def sync_user_skills(env, agents, rec):
    targets = mirror_targets(env, agents)
    if not targets:
        return []
    wanted = user_skills(env, rec)
    lines = []
    for key, h in targets:
        folder = h / "skills"
        recorded = set(rec["user_skills"].get(key, []))
        placed, added, skipped, failed = [], [], [], []
        for name, target in wanted.items():
            dest = folder / name
            if present(dest):
                if same_path(os.path.realpath(dest), target):
                    placed.append(name)
                    continue
                if not (is_link(dest) and name in recorded):
                    skipped.append(name)
                    continue
                remove_link(dest)  # OmniKit 建的連結，來源換了位置：重新連
            try:
                folder.mkdir(parents=True, exist_ok=True)
                make_link(target, dest)
            except OSError as e:
                failed.append(f"{name}（{e}）")
                continue
            placed.append(name)
            added.append(name)
        removed = [n for n in sorted(recorded - set(wanted)) if is_link(folder / n)]
        for name in removed:
            remove_link(folder / name)
        rec["user_skills"][key] = placed
        line = f"skills：{label_of(key)} 從 ~/.claude 同步使用者的 skill {len(placed)} 個（連結）"
        lines.append(line + (f"，新增 {'、'.join(added)}" if added else ""))
        if removed:
            lines.append(f"  ~/.claude 已經沒有，拿掉連結：{'、'.join(removed)}")
        for name in skipped:
            lines.append(f"  {folder / name} 已經有同名的 skill，不是從 ~/.claude 連過去的，沒有動")
        if failed:
            lines.append(f"  建不起資料夾連結，沒有同步：{'、'.join(failed)}")
    return lines


def unmirror_skills(env, rec):
    """disconnect：拿掉 OmniKit 建的使用者 skill 連結（連到的資料夾不動）。"""
    lines = []
    for key, names in rec["user_skills"].items():
        home = home_of(key)
        gone = [n for n in names if home and is_link(home / "skills" / n)]
        for name in gone:
            remove_link(home / "skills" / name)
        if gone:
            lines.append(f"skills：從 {home / 'skills'} 拿掉連到 ~/.claude 的 {'、'.join(gone)}")
    return lines


def read_doc(path):
    """讀 JSON；不存在或壞掉都當成空的（來源的設定壞了不該讓整個同步停下來）。"""
    try:
        doc = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def wanted_plugins(env):
    enabled = read_doc(user_source(env) / "settings.json").get("enabledPlugins") or {}
    if not isinstance(enabled, dict):
        return []
    return sorted(p for p, on in enabled.items() if on is True and isinstance(p, str) and "@" in p)


def marketplace_sources(env):
    """{marketplace 名稱: source}：known_marketplaces.json 優先（實際加過的），沒有再看 extraKnownMarketplaces。"""
    extra = read_doc(user_source(env) / "settings.json").get("extraKnownMarketplaces") or {}
    known = read_doc(user_source(env) / "plugins" / "known_marketplaces.json")
    found = {}
    for doc in (extra if isinstance(extra, dict) else {}, known):
        for name, entry in doc.items():
            if isinstance(entry, dict) and isinstance(entry.get("source"), dict):
                found[name] = entry["source"]
    return found


def marketplace_args(source):
    """claude plugin marketplace add 的參數；認不得的來源回傳 None。
    指定 ref 的用 <git 網址>#<ref>（官方文件的寫法；這台還沒有帶 ref 的 marketplace，未實測）。"""
    kind, ref = source.get("source"), source.get("ref")
    if kind == "github" and source.get("repo"):
        arg = f"https://github.com/{source['repo']}.git" if ref else source["repo"]
    elif kind in ("git", "url") and source.get("url"):
        arg = source["url"]
    elif kind in ("directory", "file") and source.get("path"):
        arg, ref = source["path"], None
    else:
        return None
    args = ["plugin", "marketplace", "add", arg + (f"#{ref}" if ref else ""), "--scope", "user"]
    if isinstance(source.get("sparsePaths"), list) and source["sparsePaths"]:
        args += ["--sparse", *source["sparsePaths"]]
    return args


def run_claude(env, args, key):
    """跑 claude 指令，CLAUDE_CONFIG_DIR 指到 key 的目錄；回傳 (exit, stdout, stderr)，不丟例外。"""
    cmd, environ = [*env.claude_cli, *args], claude_env(key)
    if env.runner:
        return env.runner(cmd, environ)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                           env=environ, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)
    return r.returncode, r.stdout or "", r.stderr or ""


def json_out(text):
    """--json 的輸出：前面可能夾雜提示文字，從第一個 [ 或 { 開始解析。"""
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                return json.loads(text[i:])
            except ValueError:
                return None
    return None


def brief(code, out, err):
    text = " ".join((err or out or "").split())
    return f"exit {code}：{text[:300]}" if text else f"exit {code}"


def sync_user_plugins(env, agents, rec):
    targets = mirror_targets(env, agents)
    if not targets:
        return []
    wanted = wanted_plugins(env)
    if not env.claude_cli:
        return [f"plugin：找不到 claude 指令，~/.claude 啟用的 {len(wanted)} 個 plugin 沒有同步到其他設定目錄"] if wanted else []
    sources = marketplace_sources(env)
    lines = []
    for key, _ in targets:
        old = rec["user_plugins"].get(key) or {}
        synced, turned_off = set(old.get("synced", [])), set(old.get("disabled", []))
        listed = run_claude(env, ["plugin", "list", "--json"], key)
        items = json_out(listed[1]) if listed[0] == 0 else None
        if not isinstance(items, list):
            lines.append(f"plugin：{label_of(key)} 讀不到已安裝的 plugin（{brief(*listed)}），這次沒有同步")
            continue
        installed = {i["id"]: bool(i.get("enabled")) for i in items if isinstance(i, dict) and isinstance(i.get("id"), str)}
        r = run_claude(env, ["plugin", "marketplace", "list", "--json"], key)
        markets = {m.get("name") for m in (json_out(r[1]) or []) if isinstance(m, dict)} if r[0] == 0 else set()
        have, added, enabled, left, failed = [], [], [], [], []
        for pid in wanted:
            if pid in installed:
                if installed[pid]:
                    have.append(pid)
                elif pid in turned_off:  # OmniKit 之前停用的，~/.claude 又啟用了
                    r = run_claude(env, ["plugin", "enable", pid, "--scope", "user"], key)
                    if r[0] == 0:
                        have.append(pid)
                        enabled.append(pid)
                    else:
                        failed.append(f"{pid}（enable {brief(*r)}）")
                else:
                    left.append(pid)
                continue
            mkt = pid.rsplit("@", 1)[1]
            if mkt not in markets:
                args = marketplace_args(sources.get(mkt) or {})
                if args is None:
                    failed.append(f"{pid}（~/.claude 找不到 marketplace {mkt} 的來源）")
                    continue
                r = run_claude(env, args, key)
                if r[0] != 0:
                    failed.append(f"{pid}（marketplace add {brief(*r)}）")
                    continue
                markets.add(mkt)
            r = run_claude(env, ["plugin", "install", pid, "--scope", "user"], key)
            if r[0] != 0:
                failed.append(f"{pid}（install {brief(*r)}）")
                continue
            have.append(pid)
            added.append(pid)
        off = []
        for pid in sorted((synced | turned_off) - set(wanted)):
            if installed.get(pid) is True:
                r = run_claude(env, ["plugin", "disable", pid, "--scope", "user"], key)
                if r[0] != 0:
                    failed.append(f"{pid}（disable {brief(*r)}）")
                    continue
                off.append(pid)
                turned_off.add(pid)
        turned_off = {p for p in turned_off - set(have) if p in installed}
        rec["user_plugins"][key] = {"synced": sorted(set(have) | set(left)), "disabled": sorted(turned_off)}
        line = f"plugin：{label_of(key)} 從 ~/.claude 同步啟用中的 plugin {len(have)}/{len(wanted)} 個"
        lines.append(line + (f"，新裝 {'、'.join(added)}" if added else "") + (f"，重新啟用 {'、'.join(enabled)}" if enabled else ""))
        if left:
            lines.append(f"  這個目錄裝了但停用，當成你的選擇沒有動：{'、'.join(left)}")
        if off:
            lines.append(f"  ~/.claude 已經停用或移除，這裡也停用（沒有解除安裝）：{'、'.join(off)}")
        for item in failed:
            lines.append(f"  沒有同步：{item}；可以設 CLAUDE_CONFIG_DIR={home_of(key)} 再自己跑 claude plugin install")
    return lines


# ---- MCP ----

def load_servers(env):
    path = env.data / "mcp" / "servers.yaml"
    if not path.exists():
        return {}
    doc = validate.load_yaml(path)
    errors = validate.schema_errors(validate.validator("mcp.schema.json"), doc, path)
    if errors:
        raise SystemExit("data/mcp/servers.yaml 格式不對：\n" + "\n".join(f"- {e}" for e in errors))
    return doc["servers"]


def desired(spec, agent, approved=True):
    """OmniKit 要寫進這個 agent 的設定。approved 是 False（同事版、本人還沒同意）：免問核准的欄位設成 None，
    表示 OmniKit 管這個欄位、但這台不寫。"""
    cfg = {"command": spec["command"], "args": list(spec.get("args", []))}
    if spec.get("env"):
        cfg["env"] = dict(spec["env"])
    if agent == "claude-code":
        cfg = {"type": "stdio", **cfg}
    options = dict((spec.get("options") or {}).get(SHORT[agent], {}))
    if not approved:
        options.update({k: None for k in APPROVAL_KEYS.get(SHORT[agent], ()) if k in options})
    cfg.update(options)
    return cfg


def norm(v):
    return None if v in ({}, [], None, "") else v


def managed_keys(cfg):
    """OmniKit 管的欄位：servers.yaml 給的，加上 command、args、env。使用者另外加的（例如停用）不管。"""
    return sorted(set(cfg) | {"command", "args", "env"})


def view(entry, keys):
    return {k: norm(entry.get(k)) for k in keys}


def same(current, cfg):
    """只比 OmniKit 管的欄位：使用者在 agent 裡另外加的（例如停用）不算不同。"""
    return isinstance(current, dict) and view(current, managed_keys(cfg)) == view(cfg, managed_keys(cfg))


def digest(entry, keys):
    data = json.dumps(view(entry, keys), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def ledger_entry(cfg):
    """帳本的一筆：OmniKit 寫入的設定在它管的欄位上的雜湊。之後算出來不一樣，就是被改過了。"""
    keys = managed_keys(cfg)
    return {"sha256": digest(cfg, keys), "keys": keys}


def differs(current, cfg, keys):
    """不同的欄位，只列名稱：值可能是金鑰，不印出來。"""
    return [k for k in keys if norm(current.get(k)) != norm(cfg.get(k))]


def merged(current, cfg, drop):
    """寫進 agent 的設定：換掉 OmniKit 管的欄位（drop），保留使用者加的（例如停用、Codex 的工具核准紀錄）。"""
    entry = {k: v for k, v in (current or {}).items() if k not in drop}
    entry.update({k: v for k, v in cfg.items() if v is not None})
    return entry


def read_json(path):
    try:
        return json.loads(path.read_bytes().decode("utf-8-sig")) if path.exists() else {}
    except ValueError:
        raise SystemExit(f"{path} 不是合法的 JSON，沒有改")


def mcp_targets(env, agents):
    """要寫 MCP 的 key：每個接上的 agent 的預設設定，加上它的其他設定目錄。"""
    return [a for a in AGENTS if a in agents] + [k for k, _, _ in env.extra_homes(agents)]


def mcp_file(env, key):
    home = home_of(key)
    if agent_of(key) == "claude-code":
        return home / ".claude.json" if home else env.claude_json
    if agent_of(key) == "codex":
        return home / "config.toml" if home else env.codex_toml
    return env.gemini_mcp


def claude_env(key):
    """claude 指令要改哪個設定目錄：預設的拿掉 CLAUDE_CONFIG_DIR（在其他帳號的對話裡跑也不會寫錯地方），
    其他設定目錄的指過去（user scope 的 MCP 就寫進 <目錄>/.claude.json）。"""
    environ = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
    if home_of(key):
        environ["CLAUDE_CONFIG_DIR"] = str(home_of(key))
    return environ


def run_cli(cmd, environ=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                           env=environ)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"{' '.join(cmd[-5:-2])} 無法執行：{e}")
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(cmd[-5:-2])} 失敗（exit {r.returncode}）：{(r.stderr or r.stdout).strip()}")


def read_servers(env, key):
    """key：agent（預設的設定）或 <agent>@<目錄>（其他設定目錄）。"""
    path = mcp_file(env, key)
    if agent_of(key) == "codex":
        text, _ = codex_hooks.read(path)
        try:
            return tomllib.loads(text).get("mcp_servers", {})
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"{path} 不是合法的 TOML（{e}），沒有改")
    return read_json(path).get("mcpServers", {})


# 寫入：ops 是 {名稱: (設定, 要換掉的欄位)}；設定是 None 表示移除。要不要寫由 plan_mcp 決定，這裡只照做

def claude_apply(env, ops, key="claude-code"):
    if not ops:
        return []
    path, current = mcp_file(env, key), read_servers(env, key)
    for name, (cfg, drop) in sorted(ops.items()):
        entry = None if cfg is None else merged(current.get(name), cfg, drop)
        if env.claude_cli:
            if name in current:
                run_cli([*env.claude_cli, "mcp", "remove", "-s", "user", name], claude_env(key))
            if entry is not None:
                run_cli([*env.claude_cli, "mcp", "add-json", "-s", "user", name, json.dumps(entry, ensure_ascii=False)],
                        claude_env(key))
        else:
            doc = read_json(path)
            servers = doc.setdefault("mcpServers", {})
            if entry is None:
                servers.pop(name, None)
            else:
                servers[name] = entry
            profiles.write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return sorted(ops)


def toml_key(k):
    return k if BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # JSON 字串的跳脫寫法也是合法的 TOML basic string
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(x)}" for k, x in v.items()) + " }"
    raise SystemExit(f"Codex 的 MCP 設定不支援這種值：{v!r}")


def codex_table(name, cfg):
    head = f"mcp_servers.{toml_key(name)}"
    lines = [MCP_MARK, f"[{head}]", *(f"{toml_key(k)} = {toml_value(v)}" for k, v in cfg.items() if k != "env")]
    if cfg.get("env"):
        lines += ["", f"[{head}.env]", *(f"{toml_key(k)} = {toml_value(v)}" for k, v in cfg["env"].items())]
    return "\n".join(lines) + "\n"


def strip_tables(text, names):
    """拿掉 [mcp_servers.<名稱>] 與它的子表格。表格最後一個設定之後的空行與註解屬於下一段，保留。"""
    out, pending, skipping = [], [], False
    for line in text.split("\n"):
        if HEADER_LINE.match(line):
            m = TABLE.match(line)
            name = (json.loads(f'"{m.group(1)}"') if m.group(1) is not None else m.group(2)) if m else None
            if name in names:
                if not skipping:
                    i = len(out)
                    while i and not out[i - 1].strip():
                        i -= 1
                    if i and out[i - 1] == MCP_MARK:
                        del out[i - 1:]
                skipping, pending = True, []
                continue
            if skipping:
                out.extend(pending)
                skipping, pending = False, []
        elif skipping:
            if not line.strip() or line.lstrip().startswith("#"):
                pending.append(line)
            else:
                pending = []
            continue
        out.append(line)
    if skipping:
        out.extend(pending)
    return "\n".join(out)


def key_of(line):
    m = KEY_LINE.match(line)
    if not m:
        return None
    return json.loads(f'"{m.group(1)}"') if m.group(1) is not None else m.group(2)


def table_of(line):
    """[mcp_servers.<名稱>] 回傳（名稱, ""）；子表格 [mcp_servers.<名稱>.<路徑>] 回傳（名稱, ".<路徑>"）。"""
    m = TABLE.match(line)
    if not m:
        return None
    name = json.loads(f'"{m.group(1)}"') if m.group(1) is not None else m.group(2)
    return name, re.sub(r"\s+", "", m.group(3) or "")


def codex_update(text, name, cfg, drop):
    """原地更新 [mcp_servers.<名稱>]：只換 OmniKit 管的欄位（drop）與 env 子表格。使用者加的欄位、註解，
    以及其他子表格（例如 Codex 的工具核准紀錄 tools.<工具>）都留著。找不到這個表格就回 None。"""
    lines = text.split("\n")
    heads = [i for i, line in enumerate(lines) if HEADER_LINE.match(line)]

    def end(i):
        """表格到哪一行為止：最後一個設定之後的空行與註解屬於下一段。"""
        j = next((h for h in heads if h > i), len(lines))
        while j - 1 > i and (not lines[j - 1].strip() or lines[j - 1].lstrip().startswith("#")):
            j -= 1
        return j

    main = next((i for i in heads if table_of(lines[i]) == (name, "")), None)
    if main is None:
        return None
    head = f"mcp_servers.{toml_key(name)}"
    block = [lines[main], *(f"{toml_key(k)} = {toml_value(v)}" for k, v in cfg.items() if k != "env" and v is not None),
             *(line for line in lines[main + 1:end(main)] if key_of(line) not in drop)]
    if cfg.get("env"):
        block += ["", f"[{head}.env]", *(f"{toml_key(k)} = {toml_value(v)}" for k, v in cfg["env"].items())]
    edits = [(main, end(main), block)]
    for i in heads:
        if table_of(lines[i]) == (name, ".env"):
            start = i
            while start - 1 >= 0 and not lines[start - 1].strip():
                start -= 1  # 連同前面的空行一起拿掉，重複更新也不會越空越多行
            edits.append((start, end(i), []))
    for start, stop, new in sorted(edits, key=lambda e: e[0], reverse=True):
        lines[start:stop] = new
    return "\n".join(lines)


def codex_apply(env, ops, key="codex"):
    if not ops:
        return []
    path = mcp_file(env, key)
    text, newline = codex_hooks.read(path)
    try:
        old = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path} 不是合法的 TOML（{e}），沒有改")
    current = old.get("mcp_servers", {})
    remove = {n for n, (cfg, _) in ops.items() if cfg is None}
    update = {n for n, (cfg, _) in ops.items() if cfg is not None and n in current}
    add = {n for n, (cfg, _) in ops.items() if cfg is not None and n not in current}
    new_text = strip_tables(text, remove) if remove else text
    for name in sorted(update):
        new_text = codex_update(new_text, name, *ops[name])
        if new_text is None:
            raise SystemExit(f"{path} 的 mcp_servers.{name} 用了 OmniKit 不認得的寫法，沒有寫入；請手動檢查")
    kept = new_text.rstrip("\n")
    new_text = kept + "\n" if kept.strip() else ""
    for name in sorted(add):
        new_text += ("\n" if new_text else "") + codex_table(name, {k: v for k, v in ops[name][0].items() if v is not None})
    expect = copy.deepcopy(old)
    servers = expect.setdefault("mcp_servers", {})
    for name in remove:
        servers.pop(name, None)
    for name in update | add:
        servers[name] = merged(current.get(name), *ops[name])
    if not servers:
        expect.pop("mcp_servers")
    try:
        new = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError:
        new = None
    if new != expect:
        raise SystemExit(f"改 {path} 的 MCP 設定時，結果跟預期不同（可能用了 OmniKit 不認得的寫法），沒有寫入；"
                         f"請手動檢查 mcp_servers 的 {'、'.join(sorted(ops))}")
    path.parent.mkdir(parents=True, exist_ok=True)
    codex_hooks.write(path, new_text, newline)
    return sorted(ops)


def gemini_apply(env, ops, key="antigravity"):
    path = mcp_file(env, key)
    doc = read_json(path)
    had_bom = path.exists() and path.read_bytes().startswith(b"\xef\xbb\xbf")
    servers = doc.setdefault("mcpServers", {})
    for name, (cfg, drop) in ops.items():
        if cfg is None:
            servers.pop(name, None)
        else:
            servers[name] = merged(servers.get(name), cfg, drop)
    if ops or had_bom:
        profiles.write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return sorted(ops)


WRITERS = {"claude-code": claude_apply, "codex": codex_apply, "antigravity": gemini_apply}


@dataclass
class Conflict:
    agent: str  # 寫入的對象：agent，或 <agent>@<目錄>（其他設定目錄）
    name: str
    why: str
    keys: list  # 不同的欄位，只列名稱
    managed: list  # 決定用 OmniKit 的設定時，要換掉的欄位


@dataclass
class McpPlan:
    # key 是寫入的對象：agent，或 <agent>@<目錄>（其他設定目錄，見 mcp_targets）
    wanted: dict  # key → {名稱: OmniKit 要的設定}
    ops: dict  # key → {名稱: (設定或 None, 要換掉的欄位)}
    ledger: dict  # key → 寫完之後的帳本
    keep: dict  # key → [使用者選了自己管的名稱]
    adopted: dict  # key → [同名而且設定一樣，改由 OmniKit 管的名稱]
    conflicts: list


def plan_mcp(env, agents, rec):
    """比對 servers.yaml、agent 現在的設定與帳本，決定每個 server 要新增、更新、移除、接手，還是衝突。
    只讀不寫。衝突：OmniKit 寫入之後被改過、OmniKit 加過但被移除、同名但不是 OmniKit 的、
    舊版記錄沒有雜湊又跟 servers.yaml 不同。"""
    servers = load_servers(env)
    allowed = edition.approver(env.state, env.repo)
    plan = McpPlan({}, {}, {}, {}, {}, [])
    for target in mcp_targets(env, agents):
        agent = agent_of(target)
        wanted = {n: desired(s, agent, allowed(n)) for n, s in servers.items() if SHORT[agent] in s["targets"]}
        current = read_servers(env, target)
        ledger = rec["mcp"].get(target, {})
        keep = [n for n in rec["mcp_keep"].get(target, []) if n in wanted]
        ops, new, adopted = {}, {}, []

        def conflict(name, why, keys, managed, target=target, ledger=ledger, new=new):
            plan.conflicts.append(Conflict(target, name, why, keys, sorted(managed)))
            if name in ledger:
                new[name] = ledger[name]  # 帳本照舊，等使用者決定

        for name, cfg in wanted.items():
            if name in keep:
                continue
            cur, entry, keys = current.get(name), ledger.get(name), managed_keys(cfg)
            if cur is None:
                if name in ledger:
                    conflict(name, "OmniKit 加過，後來被移除了", [], keys)
                else:
                    ops[name], new[name] = (cfg, set(keys)), ledger_entry(cfg)
                continue
            old_keys = entry["keys"] if entry else keys
            both = sorted(set(keys) | set(old_keys))
            # 以前管、現在不管的欄位（例如撤回同意的免問核准）還留著，也要更新
            stale = any(norm(cur.get(k)) is not None for k in old_keys if k not in keys)
            if same(cur, cfg) and not stale:
                new[name] = ledger_entry(cfg)
                if entry is None:
                    adopted.append(name)
            elif name not in ledger:
                conflict(name, "已經有同名的 server，不是 OmniKit 加的", differs(cur, cfg, keys), keys)
            elif entry is None:
                conflict(name, "舊版的記錄沒有雜湊，確認不了是不是你改的", differs(cur, cfg, keys), keys)
            elif digest(cur, entry["keys"]) != entry["sha256"]:
                conflict(name, "OmniKit 寫入之後被改過", differs(cur, cfg, both), both)
            else:
                ops[name], new[name] = (cfg, set(both)), ledger_entry(cfg)
        for name, entry in ledger.items():
            if name in wanted or name not in current:
                continue  # 還要的上面處理過；已經不在的就從帳本拿掉
            if entry is None:
                conflict(name, "servers.yaml 拿掉了，但舊版的記錄沒有雜湊，確認不了是不是你改的", [], list(current[name]))
            elif digest(current[name], entry["keys"]) != entry["sha256"]:
                conflict(name, "servers.yaml 拿掉了，但 OmniKit 寫入之後被改過", [], entry["keys"])
            else:
                ops[name] = (None, set())
        plan.wanted[target], plan.ops[target], plan.ledger[target] = wanted, ops, new
        plan.keep[target], plan.adopted[target] = keep, adopted
    return plan


def choose(env, rec, c, choice):
    """記下使用者對一個衝突的決定，重新比對就不會再衝突。
    omnikit：照 servers.yaml 寫或移除；mine：保留使用者的，OmniKit 之後不管這個 server。"""
    ledger = rec["mcp"].setdefault(c.agent, {})
    keep = rec["mcp_keep"].setdefault(c.agent, [])
    if choice == "mine":
        ledger.pop(c.name, None)
        if c.name not in keep:
            keep.append(c.name)
        return
    if c.name in keep:
        keep.remove(c.name)
    cur = read_servers(env, c.agent).get(c.name)
    if cur is None:
        ledger.pop(c.name, None)  # 不在了：當成新的加回去
    else:
        ledger[c.name] = {"sha256": digest(cur, c.managed), "keys": c.managed}  # 當成 OmniKit 寫的，照常更新


def report(conflicts):
    """有衝突的 server 略過不動，其他照常寫；這裡列出略過了哪些、怎麼決定。"""
    lines = ["MCP：下面有衝突的 server 這次略過沒動（規則、skills 與其他 server 照常）："]
    for c in conflicts:
        lines.append(f"  - {label_of(c.agent)} 的 {c.name}：{c.why}" + (f"（不同的欄位：{'、'.join(c.keys)}）" if c.keys else ""))
    lines += ["  要決定用誰的設定，擇一執行：",
              f"  改用 OmniKit 的設定（data/mcp/servers.yaml）：{RESOLVE} --use-omnikit",
              f"  保留你的設定，OmniKit 之後不再管它：{RESOLVE} --keep-mine"]
    return lines


def ask_conflict(c):
    """互動時逐一問；直接按 Enter 表示先不處理。"""
    print(f"MCP：{label_of(c.agent)} 的 {c.name}：{c.why}" + (f"（不同的欄位：{'、'.join(c.keys)}）" if c.keys else ""))
    print("  1) 改用 OmniKit 的設定（data/mcp/servers.yaml）")
    print("  2) 保留你的設定，OmniKit 之後不再管它")
    try:
        answer = input("選 1 或 2（直接按 Enter 先不處理，這次略過這個 server）：").strip()
    except EOFError:
        return None
    return {"1": "omnikit", "2": "mine"}.get(answer)


def settle(env, agents, rec, ask=None):
    """寫入前先比對 MCP。有衝突就逐一問（ask）；還沒解決的留在 plan.conflicts，寫入時略過並列出來。"""
    plan = plan_mcp(env, agents, rec)
    if plan.conflicts and ask:
        chosen = False
        for c in plan.conflicts:
            choice = ask(c)
            if choice:
                choose(env, rec, c, choice)
                chosen = True
        if chosen:
            save_record(env, rec)  # 已經決定的先記下來，下次不用再問
            plan = plan_mcp(env, agents, rec)
    return plan


def apply_mcp(env, agents, rec, plan):
    lines = []
    for key in mcp_targets(env, agents):
        changed = WRITERS[agent_of(key)](env, plan.ops[key], key)
        rec["mcp"][key] = plan.ledger[key]
        rec["mcp_keep"][key] = plan.keep[key]
        state = f"（更新：{'、'.join(changed)}）" if changed else "（已是最新）"
        lines.append(f"MCP：{label_of(key)} {'、'.join(sorted(plan.wanted[key])) or '（沒有）'}{state}")
        if plan.adopted[key]:
            lines.append(f"  同名而且設定一樣，改由 OmniKit 管：{'、'.join(plan.adopted[key])}")
        if plan.keep[key]:
            lines.append(f"  你選了自己管，OmniKit 沒動：{'、'.join(plan.keep[key])}")
    if plan.conflicts:
        lines += report(plan.conflicts)
    return lines


# ---- 舊版 skillshare ----

def drop_extra(text, name):
    lines = text.split("\n")
    i = next((k for k, line in enumerate(lines) if line.strip() == f"- name: {name}"), None)
    if i is None:
        return text
    indent = len(lines[i]) - len(lines[i].lstrip())
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
        j += 1
    while j > i + 1 and not lines[j - 1].strip():
        j -= 1
    del lines[i:j]
    e = next((k for k, line in enumerate(lines) if line.rstrip() == "extras:"), None)
    if e is not None:
        rest = next((line for line in lines[e + 1:] if line.strip()), "")
        if not rest or not rest.startswith((" ", "-")):
            lines[e] = "extras: []"
    return "\n".join(lines)


def release_skillshare(env):
    """拿掉 OmniKit 在 skillshare 留下的設定（不執行 skillshare），skillshare 本身不刪。"""
    lines = []
    link = env.skillshare / "skills" / "_omnikit"
    if is_link(link):
        remove_link(link)
        lines.append("skillshare：拿掉 OmniKit 的 skills 連結（_omnikit）")
    config = env.skillshare / "config.yaml"
    if config.exists():
        raw = config.read_bytes().decode("utf-8-sig")
        newline = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        ours = env.data / "mcp" / "servers.yaml"
        new = re.sub(r"(?m)^  mcp: (.+?)\s*\n", lambda m: "" if same_path(m.group(1), ours) else m.group(0), text)
        new = drop_extra(new, "rules-codex")
        if new != text:
            old_doc, new_doc = yaml.safe_load(text) or {}, yaml.safe_load(new) or {}
            expect = copy.deepcopy(old_doc)
            sources = expect.get("sources") or {}
            if same_path(str(sources.get("mcp", "")), ours):
                sources.pop("mcp")
            expect["extras"] = [x for x in (expect.get("extras") or []) if x.get("name") != "rules-codex"]
            for d in (expect, new_doc):
                if not d.get("extras"):
                    d.pop("extras", None)
            if new_doc == expect:
                retry(config.write_bytes, new.replace("\n", newline).encode("utf-8"))
                lines.append("skillshare：設定檔拿掉 OmniKit 的 MCP 來源與 Codex 規則")
            else:
                lines.append(f"skillshare：{config} 的寫法跟預期不同，沒有改；可以自己拿掉 sources.mcp 與 rules-codex")
    ours = set(skill_names(env.skills_src))
    for folder, _ in env.skill_dirs.values():
        manifest = folder / ".skillshare-manifest.json"
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        managed = doc.get("managed") or {}
        drop = [n for n in managed if n in ours]
        if drop:
            for n in drop:
                del managed[n]
            profiles.write(manifest, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    if lines:
        lines.append(f"OmniKit 不再使用 skillshare；它本身還在（{env.skillshare}），不需要的話可以自己移除")
    return lines


# ---- 指令 ----

def connect(env, profile=None, agents=None, ask=None):
    agents = agents or detect(env)
    if not agents:
        raise SystemExit("找不到 Claude Code、Codex 或 Antigravity，沒有可以接上的 agent")
    rec = load_record(env)
    plan = settle(env, agents, rec, ask)  # 有衝突的 server 留在 plan.conflicts，寫入時略過
    rec["agents"] = list(agents)
    lines = profiles.apply(env.data, env.state, env.rules, wanted=profile, agents=agents, take_over=True,
                           skillshare_config=env.skillshare / "config.yaml", **extra_rules(env, agents))
    lines += sync_skills(env, agents, rec, profile)
    lines += sync_user_skills(env, agents, rec)
    lines += apply_mcp(env, agents, rec, plan)
    lines += sync_user_plugins(env, agents, rec)
    t3_lines, t3_keys = connect_t3(env, agents)
    lines += t3_lines
    rec["homes"] = [k for k, _, _ in env.extra_homes(agents)] + t3_keys
    save_record(env, rec)
    lines += release_skillshare(env)
    return lines


def connect_t3(env, agents):
    """T3 Code 的 Antigravity 實例：Binary path 指到 OmniKit 的轉接程式（t3_acp.py）。回傳（訊息, 處理過的實例 key）。
    出錯只印一行，規則、skills 與 MCP 照常；下次 sync 再試。"""
    if "antigravity" not in agents:
        return [], []
    try:
        # uv：PATH 上的，沒有就用正在跑這支的那個（uv run 會設 UV）
        return t3_acp.apply(env.home, t3_acp.acp_dir(env.home), env.which("uv") or os.environ.get("UV"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return [f"T3 Code 的 Antigravity：沒接上轉接程式（{e}），下次 sync 再試"], []


def extra_rules(env, agents):
    """profiles.apply 的其他設定目錄參數：只給接上了的 agent。"""
    return {"claude_extra": env.claude_extra_rules if "claude-code" in agents else [],
            "codex_extra": env.codex_extra_rules if "codex" in agents else []}


def known_homes(rec):
    """記錄裡接上過的其他設定目錄。舊版沒記 homes：那時只有 Claude 的，有放 skills 的就是。"""
    if isinstance(rec.get("homes"), list):
        return rec["homes"]
    return [k for k in rec["skills"] if "@" in k]


def attach_homes(env, rec):
    """接上這次才找到的其他設定目錄：規則區塊（可以接手原本的規則，先備份）、Claude 的權限規則與 hook。
    skills 與 MCP 由 sync 照常處理（目標本來就包含所有找得到的設定目錄）。回傳（訊息, 新的 key）。"""
    agents = rec["agents"]
    known = {os.path.normcase(k) for k in known_homes(rec)}
    new = [(k, a, h) for k, a, h in env.extra_homes(agents) if os.path.normcase(k) not in known]
    if not new:
        return [], []
    rules_of = {"claude-code": "CLAUDE.md", "codex": "AGENTS.md"}
    lines = [f"找到新的設定目錄，接上 OmniKit：{'、'.join(label_of(k) for k, _, _ in new)}"]
    lines += profiles.apply(env.data, env.state, env.rules, agents=agents, skillshare_config=env.skillshare / "config.yaml",
                            new_extra=[h / rules_of[a] for _, a, h in new], **extra_rules(env, agents))
    if any(a == "claude-code" for _, a, _ in new):
        lines += claude_allow.apply(env.home / ".claude" / "settings.json", env.state / "install-record.json",
                                    env.state, env.repo, extra_settings=[h / "settings.json" for h in env.claude_homes])
    return lines, [k for k, _, _ in new]


def sync(env, skills=True, mcp=True, ask=None, plugins=True):
    rec = load_record(env)
    if not rec["agents"]:
        return ["這台還沒用新的方式接上 agent（沒有 agents.json），skills 與 MCP 沒有同步：重跑 install.ps1"]
    lines, _ = attach_homes(env, rec)
    plan = settle(env, rec["agents"], rec, ask) if mcp else None
    if skills:
        lines += sync_skills(env, rec["agents"], rec)
        lines += sync_user_skills(env, rec["agents"], rec)
    if mcp:
        lines += apply_mcp(env, rec["agents"], rec, plan)
    if plugins:
        lines += sync_user_plugins(env, rec["agents"], rec)
    t3_lines, t3_keys = connect_t3(env, rec["agents"])
    lines += t3_lines
    rec["homes"] = [k for k, _, _ in env.extra_homes(rec["agents"])] + t3_keys
    save_record(env, rec)
    return lines


def resolve_conflict(env, name, choice, agent=None):
    """使用者決定 MCP 衝突要用誰的設定（choice：omnikit 或 mine），記下來並馬上同步。
    之前選了自己管的，也可以用 omnikit 改回由 OmniKit 管。"""
    rec = load_record(env)
    agents = rec["agents"] or detect(env)
    plan = plan_mcp(env, agents, rec)
    hits = [c for c in plan.conflicts if c.name == name and agent in (None, agent_of(c.agent))]
    if choice == "omnikit":
        hits += [Conflict(k, name, "你選了自己管", [], managed_keys(plan.wanted[k][name]))
                 for k in mcp_targets(env, agents) if name in plan.keep[k] and agent in (None, agent_of(k))]
    if not hits:
        return [f"MCP：{name} 沒有衝突，不用處理"]
    for c in hits:
        choose(env, rec, c, choice)
    save_record(env, rec)
    how = "改用 OmniKit 的設定" if choice == "omnikit" else "保留你的設定，OmniKit 之後不管它"
    lines = [f"MCP：{label_of(c.agent)} 的 {name} {how}" for c in hits]
    if not rec["agents"]:
        return lines + ["這台還沒接上 agent：重跑 install.ps1 就會套用"]
    return lines + sync(env, skills=False, plugins=False)  # 其他還沒解決的衝突一樣略過並列出來


def approval_items(env, agents):
    """要本人同意的免問核准，依工具分組：{工具: [會寫什麼]}。"""
    items = {}
    if "claude-code" in agents:
        for rule in claude_allow.rules(env.repo):
            items.setdefault(edition.tool_of(rule), []).append(f"Claude Code 的 permissions.allow 加上 {rule}")
    for name, spec in load_servers(env).items():
        for agent in agents:
            options = (spec.get("options") or {}).get(SHORT[agent], {})
            keys = [k for k in APPROVAL_KEYS.get(SHORT[agent], ()) if k in options]
            if keys and SHORT[agent] in spec["targets"]:
                items.setdefault(name, []).append(f"{NAMES[agent]} 的 " + "、".join(f"{k} = {options[k]}" for k in keys))
    return items


def ask_approval(tool, what):
    print(f"免問核准：{tool}")
    for line in what:
        print(f"  - {line}")
    try:
        answer = input("要讓 agent 用它的工具時不再逐次詢問嗎？(y/N)：").strip().lower()
    except EOFError:
        return None
    return answer in ("y", "yes")


def approvals(env, ask=None, grant=(), revoke=()):
    """免問核准：列出要本人同意的工具與狀態；ask 逐一問還沒問過的；grant、revoke 記下來並馬上套用。
    維護者版照 data 寫入，這裡的同意不影響它。"""
    rec = load_record(env)
    agents = rec["agents"] or detect(env)
    items = approval_items(env, agents)
    unknown = [t for t in (*grant, *revoke) if t not in items]
    if unknown:
        raise SystemExit(f"沒有要同意的免問核准：{'、'.join(unknown)}；可選：{'、'.join(items) or '無'}")
    for tool in grant:
        edition.record(env.state, tool, True)
    for tool in revoke:
        edition.record(env.state, tool, False)
    maintainer = edition.resolve(env.state, env.repo)[0] == "maintainer"
    if ask and not maintainer:
        for tool in [t for t in items if edition.decided(env.state, t) is None]:
            answer = ask(tool, items[tool])
            if answer is not None:
                edition.record(env.state, tool, answer)
    status = {True: "同意", False: "不要", None: "還沒問"}
    lines = ["維護者版：免問核准照 data/harness/claude-allow.txt 與 data/mcp/servers.yaml 寫入，不另外問"] if maintainer else []
    lines += [f"免問核准 {tool}（{status[edition.decided(env.state, tool)]}）：{'；'.join(what)}" for tool, what in items.items()]
    if not (grant or revoke):
        return lines
    if "claude-code" in agents:
        lines += claude_allow.apply(env.home / ".claude" / "settings.json", env.state / "install-record.json",
                                    env.state, env.repo, extra_settings=[h / "settings.json" for h in env.claude_homes])
    if not rec["agents"]:
        return lines + ["這台還沒接上 agent：重跑 install.ps1 就會套用"]
    return lines + sync(env, skills=False, plugins=False)


def disconnect(env):
    rec = load_record(env)
    agents = rec["agents"] or detect(env)
    lines = []
    names = set(skill_names(env.skills_src))
    for key, (folder, _) in env.skill_dirs.items():
        removed = []
        recorded = set(rec["skills"].get(key, []))
        for name in sorted(recorded | names):
            entry = folder / name
            if present(entry) and owned(entry, env, recorded):
                remove_owned(entry)
                removed.append(name)
        if removed:
            lines.append(f"skills：從 {folder} 拿掉 {'、'.join(removed)}")
    lines += unmirror_skills(env, rec)
    if any(v.get("synced") for v in rec["user_plugins"].values() if isinstance(v, dict)):
        lines.append("plugin：從 ~/.claude 同步到其他設定目錄的 plugin 留著（是你自己的 plugin，不是 OmniKit 的）；"
                     "不要的話設 CLAUDE_CONFIG_DIR 再跑 claude plugin uninstall")
    servers = load_servers(env)
    allowed = edition.approver(env.state, env.repo)
    # 接上過、目錄還在的其他設定目錄也要拿（這次可能找不到了，例如環境變數沒設）
    targets = mcp_targets(env, agents) + [k for k in rec["mcp"] if home_of(k) and home_of(k).is_dir()]
    for key in dict.fromkeys(targets):
        agent = agent_of(key)
        current = read_servers(env, key)
        if key in rec["mcp"]:
            # 帳本裡的才拿掉；OmniKit 寫入之後被改過的，已經是使用者的設定，留著
            ledger = rec["mcp"][key]
            drop = {n for n, e in ledger.items() if n in current and (e is None or digest(current[n], e["keys"]) == e["sha256"])}
            kept = sorted(n for n in ledger if n in current and n not in drop)
        else:
            # 舊版沒有記錄：只拿掉設定跟 servers.yaml 一模一樣的，同名但不同的可能是使用者自己的
            drop = {n for n, s in servers.items()
                    if SHORT[agent] in s["targets"] and same(current.get(n), desired(s, agent, allowed(n)))}
            kept = []
        changed = WRITERS[agent](env, {n: (None, set()) for n in drop}, key)
        if changed:
            lines.append(f"MCP：從 {label_of(key)} 拿掉 {'、'.join(changed)}")
        if kept:
            lines.append(f"MCP：{label_of(key)} 的 {'、'.join(kept)} 在 OmniKit 寫入之後被改過，當成你的設定，沒有拿掉")
    lines += profiles.disconnect_block(env.rules["codex"])
    lines += profiles.disconnect_block(env.rules["antigravity"])
    rules_of = {"claude-code": "CLAUDE.md", "codex": "AGENTS.md"}
    recorded = [(agent_of(k), home_of(k)) for k in known_homes(rec) if home_of(k)]
    extra = [h / "CLAUDE.md" for h in env.claude_homes] + [h / "AGENTS.md" for h in env.codex_homes] \
        + [h / rules_of[a] for a, h in recorded if a in rules_of]
    for path in dict.fromkeys(extra):  # ~/.claude/CLAUDE.md 由 uninstall.ps1 處理
        lines += profiles.disconnect_block(path)
    lines += t3_acp.remove(env.home, t3_acp.acp_dir(env.home))
    lines += release_skillshare(env)
    if env.record_file.exists():
        retry(env.record_file.unlink)
    return lines


def status(env, environ=None):
    legacy = [str(path) for _, path, _ in statedir.pending(env.state, environ)]
    print(json.dumps({"detected": detect(env), "state": str(env.state), **load_record(env),
                      **({"legacy": legacy} if legacy else {})}, ensure_ascii=False, indent=2))
    if legacy:
        print(f"舊位置還有沒合併的狀態檔，上面的記錄可能不完整；跑 agents.py sync（或 statedir.py migrate）合併", file=sys.stderr)
    return 0


def after_migrate(env, moved):
    """搬過家之後：用新位置重新接上規則（CLAUDE.md 的 import 可能指到舊位置的 profile）。"""
    if not moved.changed:
        return []
    rec = load_record(env)
    if not rec["agents"]:
        return []
    return profiles.apply(env.data, env.state, env.rules, agents=rec["agents"],
                          skillshare_config=env.skillshare / "config.yaml", **extra_rules(env, rec["agents"]))


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def fails(fn):
        try:
            fn()
        except SystemExit:
            return True
        return False

    def exit_message(fn):
        try:
            out = fn()
        except SystemExit as e:
            return str(e.code)
        return "\n".join(out) if isinstance(out, list) else ""

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        home, repo, state, ss = tmp / "home", tmp / "repo", tmp / "state", tmp / "appdata" / "skillshare"

        def put(path, content, raw=False):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if raw else content.encode("utf-8"))

        # repo：規則、profile、兩個 skill、MCP 定義
        put(repo / "data" / "rules" / "baseline.md", "# 底線\n不碰金鑰\n")
        put(repo / "data" / "profiles" / "default" / "AGENTS.md", "# default\n保守\n")
        put(repo / "engine" / "skills" / "alpha" / "SKILL.md", "---\nname: alpha\n---\n")
        put(repo / "engine" / "skills" / "alpha" / "scripts" / "run.py", "print('alpha')\n")
        put(repo / "engine" / "skills" / "alpha" / "scripts" / "__pycache__" / "run.cpython-313.pyc", "x")
        put(repo / "engine" / "skills" / "beta" / "SKILL.md", "---\nname: beta\n---\n")
        servers_yaml = repo / "data" / "mcp" / "servers.yaml"
        put(servers_yaml, "servers:\n  devtools:\n    command: cmd\n    args: [/c, node, x.js]\n"
                          "    targets: [claude, codex, antigravity]\n"
                          "    options:\n      codex:\n        default_tools_approval_mode: approve\n")
        src = repo / "engine" / "skills"
        # Windows 上 repo 的資料夾常帶唯讀屬性；複製時不能把它帶過去，不然之後刪不掉
        readonly = [src / "alpha", src / "alpha" / "scripts"]
        for d in readonly:
            os.chmod(d, stat.S_IREAD | stat.S_IEXEC)

        # 舊版 skillshare 留下的：_omnikit 連結、兩邊 skills 的連結、設定檔與 manifest
        (ss / "skills").mkdir(parents=True)
        make_link(src, ss / "skills" / "_omnikit")
        for folder in (home / ".claude" / "skills", home / ".agents" / "skills"):
            folder.mkdir(parents=True)
            make_link(ss / "skills" / "_omnikit" / "alpha", folder / "alpha")
            put(folder / ".skillshare-manifest.json", json.dumps({"managed": {"alpha": "symlink", "other": "symlink"}}))
        put(home / ".agents" / "skills" / "beta" / "SKILL.md", "---\nname: beta\n---\n使用者自己的\n")
        put(home / ".agents" / "skills" / "mine" / "SKILL.md", "---\nname: mine\n---\n")
        put(home / ".gemini" / "config" / "skills" / "ag-mine" / "SKILL.md", "---\nname: ag-mine\n---\n")
        put(ss / "config.yaml", f"sources:\n  mcp: {servers_yaml}\n  skills: {ss / 'skills'}\n\nmode: merge\n\n"
                                f"extras:\n  - name: rules-codex\n    source: {state / 'rules'}\n    file: AGENTS.md\n"
                                f"    targets:\n      - path: {home / '.codex'}\n        mode: copy\n\nignore:\n  - .git/\n")

        # 三個 agent 原本的設定
        put(home / ".claude" / "CLAUDE.md", "# 我的 Claude 規則\n")
        put(home / ".claude.json", json.dumps({"numStartups": 3, "mcpServers": {
            "devtools": {"args": ["/c", "node", "x.js"], "command": "cmd", "type": "stdio"},
            "mine": {"type": "stdio", "command": "mine"}}}))
        # 舊版安裝：Codex 規則是 skillshare 複製的舊副本（還沒有產生標記），原本的早就備份好了
        put(home / ".codex" / "AGENTS.md", "# OmniKit 規則\n\n規則版本：舊\n")
        put(home / ".codex" / "AGENTS.md.pre-omnikit", "# 我的 Codex 規則\n")
        nudge = '& \\"C:/uv.exe\\" run --quiet --script \\"C:/OmniKit/engine/scripts/session_nudge.py\\"'
        codex_original = ('model = "gpt"\n\n[mcp_servers.rea]\ncommand = "node"\nargs = ["rea.mjs"]\n\n'
                          "[mcp_servers.devtools]\nargs = ['/c', 'node', 'x.js']\ncommand = 'cmd'\n"
                          "default_tools_approval_mode = 'approve'\n\n"
                          f'{codex_hooks.MARK}\n[[hooks.Stop]]\n\n[[hooks.Stop.hooks]]\ntype = "command"\n'
                          f'command = "{nudge}"\n')
        put(home / ".codex" / "config.toml", codex_original.replace("\n", "\r\n"))
        put(home / ".gemini" / "config" / "mcp_config.json",
            b"\xef\xbb\xbf" + json.dumps({"mcpServers": {"keep": {"command": "keep"}}}).encode(), raw=True)
        put(home / ".gemini" / "GEMINI.md", "# 我的 Antigravity 規則\n")
        (home / ".dsh").mkdir()
        os.link(home / ".gemini" / "GEMINI.md", home / ".dsh" / "AGENTS.md")

        env = Env(home=home, repo=repo, state=state, skillshare=ss, which=lambda _: None)
        check("偵測到三個 agent", detect(env) == ["claude-code", "codex", "antigravity"])

        # 這一段模擬維護者這台的舊安裝：免問核准照 servers.yaml 寫。同事版在後面另一段。
        # skillshare 的設定檔改寫時被防毒短暫鎖住一次（FR-34）
        edition.set_edition(state, "maintainer")
        with flaky(Path, "write_bytes", times=1, match=lambda p, *_: p == ss / "config.yaml") as config_lock:
            lines = connect(env)
        claude_alpha, codex_alpha = home / ".claude" / "skills" / "alpha", home / ".agents" / "skills" / "alpha"
        agy_skills = home / ".gemini" / "config" / "skills"
        agy_alpha = agy_skills / "alpha"
        check("Claude：舊的 skillshare 連結換成直接連到 engine/skills",
              is_link(claude_alpha) and same_path(link_target(claude_alpha), src / "alpha"))
        check("Codex：~/.agents/skills 的舊連結換成複製品，帶 .omnikit.json",
              not is_link(codex_alpha) and (codex_alpha / "scripts" / "run.py").exists() and (codex_alpha / MARKER).exists())
        check("Antigravity：複製到它讀的 ~/.gemini/config/skills，帶 .omnikit.json（它不讀 ~/.agents/skills）",
              not is_link(agy_alpha) and (agy_alpha / "scripts" / "run.py").exists() and (agy_alpha / MARKER).exists()
              and (agy_skills / "beta" / MARKER).exists())
        marker = json.loads((codex_alpha / MARKER).read_text(encoding="utf-8"))
        check("複製品記下 repo 位置，skill 的腳本找得到 repo", marker["repo"] == str(repo)
              and json.loads((agy_alpha / MARKER).read_text(encoding="utf-8"))["repo"] == str(repo))
        check("不複製 __pycache__", not (codex_alpha / "scripts" / "__pycache__").exists()
              and not (agy_alpha / "scripts" / "__pycache__").exists())
        check("同名但不是 OmniKit 的 skill 不動", "使用者自己的" in (home / ".agents" / "skills" / "beta" / "SKILL.md").read_text(encoding="utf-8")
              and any("不是 OmniKit 的" in line for line in lines))
        check("使用者自己的 skill 不動", (home / ".agents" / "skills" / "mine" / "SKILL.md").exists()
              and not (agy_skills / "ag-mine" / MARKER).exists())
        check("Claude：beta 也接上", is_link(home / ".claude" / "skills" / "beta"))
        check("每個 agent 印一行，寫出放在哪", any(f"skills：Antigravity 2 個（複製，{agy_skills}）" == line for line in lines)
              and any(f"skills：Codex 1 個（複製，{home / '.agents' / 'skills'}）" == line for line in lines))

        claude_doc = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
        check("Claude MCP：跟 skillshare 寫的一樣就不動，其他設定保留",
              claude_doc["numStartups"] == 3 and "mine" in claude_doc["mcpServers"]
              and claude_doc["mcpServers"]["devtools"]["command"] == "cmd")
        codex_text = (home / ".codex" / "config.toml").read_bytes().decode("utf-8")
        check("Codex MCP：跟 skillshare 寫的一樣就不改檔", codex_text == codex_original.replace("\n", "\r\n"))
        gemini_raw = (home / ".gemini" / "config" / "mcp_config.json").read_bytes()
        gemini_doc = json.loads(gemini_raw.decode("utf-8"))
        check("Antigravity MCP：加上 devtools，原本的保留，拿掉 BOM",
              not gemini_raw.startswith(b"\xef\xbb\xbf") and gemini_doc["mcpServers"]["keep"] == {"command": "keep"}
              and gemini_doc["mcpServers"]["devtools"] == {"command": "cmd", "args": ["/c", "node", "x.js"]})

        codex_rules = profiles.text(home / ".codex" / "AGENTS.md")
        check("規則：舊版 skillshare 管的 Codex 規則直接接手，換成只有受管區塊，安裝前的備份不動",
              codex_rules.startswith(profiles.BEGIN) and "不碰金鑰" in codex_rules and "規則版本：舊" not in codex_rules
              and profiles.text(home / ".codex" / "AGENTS.md.pre-omnikit") == "# 我的 Codex 規則\n"
              and not list((home / ".codex").glob("AGENTS.md.pre-omnikit-*")))
        check("規則：Antigravity 加上區塊，硬連結的 ~/.dsh/AGENTS.md 一起更新",
              profiles.BEGIN in profiles.text(home / ".dsh" / "AGENTS.md")
              and os.path.samefile(home / ".gemini" / "GEMINI.md", home / ".dsh" / "AGENTS.md"))

        config_doc = yaml.safe_load((ss / "config.yaml").read_text(encoding="utf-8"))
        check("skillshare：拿掉 _omnikit 連結，engine/skills 本身還在",
              not present(ss / "skills" / "_omnikit") and (src / "alpha" / "SKILL.md").exists())
        check("skillshare：設定檔拿掉 MCP 來源與 rules-codex，其他保留",
              "mcp" not in config_doc["sources"] and "skills" in config_doc["sources"]
              and not config_doc.get("extras") and config_doc["mode"] == "merge")
        check("skillshare：設定檔被防毒短暫鎖住，等一下再試，照樣改好", config_lock.calls == 2)
        manifest = json.loads((home / ".claude" / "skills" / ".skillshare-manifest.json").read_text(encoding="utf-8"))
        check("skillshare：manifest 拿掉 OmniKit 的 skill，其他保留", manifest["managed"] == {"other": "symlink"})
        rec = load_record(env)
        check("記錄接上的 agent、skills 與 MCP；MCP 帳本記雜湊", rec["agents"] == list(AGENTS)
              and rec["skills"]["codex"] == ["alpha"] and rec["skills"]["antigravity"] == ["alpha", "beta"]
              and "shared" not in rec["skills"] and list(rec["mcp"]["codex"]) == ["devtools"]
              and len(rec["mcp"]["codex"]["devtools"]["sha256"]) == 64)

        snapshot = {p: p.read_bytes() for p in (home / ".claude.json", home / ".codex" / "config.toml",
                                                 home / ".gemini" / "config" / "mcp_config.json",
                                                 home / ".gemini" / "GEMINI.md", ss / "config.yaml")}
        connect(env)
        check("重跑 connect：設定檔都不變", all(p.read_bytes() == b for p, b in snapshot.items()))

        # 舊版的記錄：Codex 與 Antigravity 共用 ~/.agents/skills，記成 shared；~/.gemini/config/skills 什麼都沒有。
        # 那份 Codex 還在用：改記成 Codex 的，不刪；標記不見了也照記錄認得。Antigravity 補裝到它讀的位置
        old = json.loads(env.record_file.read_text(encoding="utf-8"))
        old["skills"] = {"claude-code": old["skills"]["claude-code"], "shared": old["skills"]["codex"]}
        env.record_file.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        for name in ("alpha", "beta"):
            remove_tree(agy_skills / name)
        (codex_alpha / MARKER).unlink()
        lines = sync(env, mcp=False)
        saved = json.loads(env.record_file.read_text(encoding="utf-8"))["skills"]
        check("舊版記錄的 shared 改記成 Codex：~/.agents/skills 的複製品留著，沒有標記的也照記錄認得、補上標記",
              (codex_alpha / MARKER).exists() and saved.get("codex") == ["alpha"] and "shared" not in saved
              and not any(str(codex_alpha) in line for line in lines))
        check("舊版沒裝到 Antigravity 讀的位置：補裝到 ~/.gemini/config/skills",
              (agy_alpha / MARKER).exists() and (agy_skills / "beta" / MARKER).exists()
              and saved.get("antigravity") == ["alpha", "beta"])
        # 這台沒有 Codex（只接 Antigravity）：~/.agents/skills 裡舊版放的不更新也不刪，說一聲
        lines = sync_skills(env, ["claude-code", "antigravity"], load_record(env))
        check("沒接 Codex：~/.agents/skills 裡 OmniKit 之前放的留著，印一行說明",
              (codex_alpha / MARKER).exists() and any(str(home / ".agents" / "skills") in line and "只有 Codex 會讀" in line
                                                      for line in lines))

        put(src / "alpha" / "scripts" / "run.py", "print('alpha v2')\n")
        put(src / "gamma" / "SKILL.md", "---\nname: gamma\n---\n")
        sync(env, mcp=False)
        check("skill 改了：Codex 與 Antigravity 的複製品都跟著更新，Claude 的連結不用動",
              "v2" in (codex_alpha / "scripts" / "run.py").read_text(encoding="utf-8")
              and "v2" in (agy_alpha / "scripts" / "run.py").read_text(encoding="utf-8") and is_link(claude_alpha))
        check("來源資料夾是唯讀的：複製品的資料夾不帶唯讀",
              all(os.access(d / "scripts", os.W_OK) and not (getattr(os.stat(d / "scripts"), "st_file_attributes", 0) & 1)
                  for d in (codex_alpha, agy_alpha)))

        # 防毒掃描剛複製好的檔案（FR-34）：複製品被短暫鎖住時等一下再試，不會失敗
        run_py = codex_alpha / "scripts" / "run.py"
        put(src / "alpha" / "scripts" / "run.py", "print('alpha v3')\n")
        with flaky(shutil, "copyfile", times=2, match=lambda s, d, *a, **k: Path(d) == run_py) as st:
            sync(env, mcp=False)
        check("複製品被防毒短暫鎖住（假的鎖檔）：等一下再試，照樣更新",
              st.calls == 3 and st.waits == [0.25, 0.5] and "v3" in run_py.read_text(encoding="utf-8"))
        if os.name == "nt":
            put(src / "alpha" / "scripts" / "run.py", "print('alpha v4')\n")
            timer = hold(run_py, 0.6)  # 真的用不分享的方式開著 0.6 秒，跟防毒掃描時一樣
            try:
                sync(env, mcp=False)
            finally:
                timer.join()
            check("複製品真的被鎖住 0.6 秒（Windows）：等到放開之後照樣更新", "v4" in run_py.read_text(encoding="utf-8"))
        else:
            print("略過：不是 Windows，沒有真的鎖住複製品")
        put(src / "alpha" / "scripts" / "run.py", "print('alpha v2')\n")
        sync(env, mcp=False)

        # 複製品被刪到一半（舊版遇到唯讀資料夾刪不掉）：.omnikit.json 不見了也照記錄認得，原地補齊
        (codex_alpha / MARKER).unlink()
        (codex_alpha / "scripts" / "run.py").unlink()
        put(codex_alpha / "scripts" / "stale.py", "多出來的\n")
        sync(env, mcp=False)
        check("複製品缺檔、標記也不見了：照記錄認出是 OmniKit 的，原地補齊、刪掉多的",
              "v2" in (codex_alpha / "scripts" / "run.py").read_text(encoding="utf-8")
              and (codex_alpha / MARKER).exists() and not (codex_alpha / "scripts" / "stale.py").exists())
        check("新增 skill：三邊都接上", is_link(home / ".claude" / "skills" / "gamma")
              and (home / ".agents" / "skills" / "gamma" / MARKER).exists() and (agy_skills / "gamma" / MARKER).exists())
        shutil.rmtree(src / "gamma")
        codex_gamma = home / ".agents" / "skills" / "gamma"
        with flaky(shutil, "rmtree", times=1, match=lambda p, *a, **k: Path(p) == codex_gamma) as st:
            sync(env, mcp=False)
        check("刪掉 skill：三邊都拿掉", not present(home / ".claude" / "skills" / "gamma") and not present(codex_gamma)
              and not present(agy_skills / "gamma"))
        check("刪複製品時被防毒短暫鎖住：等一下再試，照樣刪掉", st.calls == 2)

        # 訪談第 5 題答「不要」（answers.json 的 evaluate_tools 是 false）：不裝 omnikit-eval。
        # 訪談產生的 profile 存在 repo 外（state/profiles，FR-38）
        put(src / "omnikit-eval" / "SKILL.md", "---\nname: omnikit-eval\n---\n")
        put(src / "ok-eval" / "SKILL.md", "---\nname: ok-eval\n---\n")  # 打 /ok 時列得到的捷徑，跟著一起裝或不裝
        put(state / "profiles" / "bob" / "AGENTS.md", "# bob\n")
        bob_answers = state / "profiles" / "bob" / "answers.json"
        put(bob_answers, json.dumps({"name": "bob", "evaluate_tools": False}))
        claude_eval, codex_eval = home / ".claude" / "skills" / "omnikit-eval", home / ".agents" / "skills" / "omnikit-eval"
        agy_eval = agy_skills / "omnikit-eval"
        sync(env, mcp=False)
        check("還沒選 bob：omnikit-eval 三邊都裝", is_link(claude_eval) and (codex_eval / MARKER).exists()
              and (agy_eval / MARKER).exists())
        lines = connect(env, profile="bob")
        rec = load_record(env)
        check("換成不評估工具的 profile：omnikit-eval 三邊都拿掉，其他 skill 照裝",
              not present(claude_eval) and not present(codex_eval) and not present(agy_eval) and is_link(claude_alpha)
              and all("omnikit-eval" not in rec["skills"][a] for a in AGENTS)
              and any("不裝 omnikit-eval" in line for line in lines))
        check("捷徑 ok-eval 跟著不裝，訊息一起列", not present(home / ".claude" / "skills" / "ok-eval")
              and not present(agy_skills / "ok-eval") and any("不裝 omnikit-eval、ok-eval" in line for line in lines))
        sync(env, mcp=False)
        check("之後的同步（git hook）照選的 profile，不會裝回來", not present(claude_eval) and not present(codex_eval)
              and not present(agy_eval))
        put(codex_eval / "SKILL.md", "---\nname: omnikit-eval\n---\n使用者自己的\n")
        sync(env, mcp=False)
        check("同名但不是 OmniKit 的 omnikit-eval 不動", (codex_eval / "SKILL.md").exists())
        shutil.rmtree(codex_eval)
        put(bob_answers, "{壞掉")
        sync(env, mcp=False)
        check("answers.json 讀不懂：全部都裝", is_link(claude_eval) and (codex_eval / MARKER).exists()
              and (agy_eval / MARKER).exists())
        put(bob_answers, json.dumps({"name": "bob", "evaluate_tools": False}))
        connect(env, profile="default")
        check("換回手寫的 profile（沒有 answers.json）：omnikit-eval 裝回來",
              is_link(claude_eval) and (codex_eval / MARKER).exists() and (agy_eval / MARKER).exists())
        shutil.rmtree(src / "omnikit-eval")
        shutil.rmtree(src / "ok-eval")
        sync(env, mcp=False)

        put(servers_yaml, "servers:\n  devtools:\n    command: cmd\n    args: [/c, node, y.js]\n"
                          "    env:\n      MODE: test\n    targets: [claude, codex, antigravity]\n"
                          "    options:\n      codex:\n        default_tools_approval_mode: approve\n")
        sync(env, skills=False)
        codex_text = (home / ".codex" / "config.toml").read_bytes().decode("utf-8")
        codex_doc = tomllib.loads(codex_text.replace("\r\n", "\n"))
        check("MCP 改了：Codex 的表格換新，只有一份，換行維持 CRLF",
              codex_doc["mcp_servers"]["devtools"] == {"command": "cmd", "args": ["/c", "node", "y.js"],
                                                       "default_tools_approval_mode": "approve", "env": {"MODE": "test"}}
              and codex_text.count("[mcp_servers.devtools]") == 1 and "\r\n" in codex_text)
        check("MCP 改了：Codex 其他設定與提醒 hook 都還在",
              codex_doc["model"] == "gpt" and "rea" in codex_doc["mcp_servers"]
              and codex_hooks.MARK in codex_text and codex_hooks.remove(codex_text.replace("\r\n", "\n")) is not None)
        claude_doc = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
        check("MCP 改了：Claude 也更新", claude_doc["mcpServers"]["devtools"]["args"][-1] == "y.js"
              and claude_doc["mcpServers"]["devtools"]["env"] == {"MODE": "test"})

        gemini_doc = json.loads((home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
        gemini_doc["mcpServers"]["devtools"]["disabled"] = True
        put(home / ".gemini" / "config" / "mcp_config.json", json.dumps(gemini_doc))
        sync(env, skills=False)
        gemini_doc = json.loads((home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
        check("使用者在 Antigravity 停用的 server：同步時不改回來", gemini_doc["mcpServers"]["devtools"].get("disabled") is True)

        put(servers_yaml, "servers: {}\n")
        sync(env, skills=False)
        check("servers.yaml 拿掉 server：三邊都移除，別人的不動",
              "devtools" not in read_servers(env, "claude-code") and "mine" in read_servers(env, "claude-code")
              and "devtools" not in read_servers(env, "codex") and "rea" in read_servers(env, "codex")
              and "devtools" not in read_servers(env, "antigravity") and "keep" in read_servers(env, "antigravity"))
        check("移除後 Codex 的標記註解也拿掉", MCP_MARK not in (home / ".codex" / "config.toml").read_text(encoding="utf-8"))

        weird = home / ".codex" / "config.toml"
        put(weird, '[mcp_servers]\ndevtools = { command = "old" }\n')
        put(servers_yaml, "servers:\n  devtools:\n    command: cmd\n    targets: [codex]\n")
        msg = exit_message(lambda: sync(env, skills=False))
        check("Codex 已經有同名但不是 OmniKit 的 server：略過並列出來，不寫入",
              "不是 OmniKit 加的" in msg and "略過" in msg and weird.read_text(encoding="utf-8").startswith("[mcp_servers]\n"))
        msg = exit_message(lambda: resolve_conflict(env, "devtools", "omnikit"))
        check("決定用 OmniKit 的，但 Codex 用了 OmniKit 不認得的寫法：失敗，不寫入",
              "不認得的寫法" in msg and weird.read_text(encoding="utf-8").startswith("[mcp_servers]\n"))
        put(weird, codex_original)

        put(servers_yaml, "servers:\n  devtools:\n    command: cmd\n    args: [/c, node, x.js]\n"
                          "    targets: [claude, codex, antigravity]\n"
                          "    options:\n      codex:\n        default_tools_approval_mode: approve\n")
        sync(env, skills=False)
        check("帳本的雜湊對不上、但現在的設定剛好就是 servers.yaml 要的：直接接手，不用問",
              all("devtools" in read_servers(env, a) for a in AGENTS) and not plan_mcp(env, AGENTS, load_record(env)).conflicts)
        for d in (codex_alpha, agy_alpha):
            os.chmod(d / "scripts", stat.S_IREAD | stat.S_IEXEC)  # 複製品裡有唯讀資料夾也要刪得掉
        with flaky(Path, "unlink", times=1, match=lambda p, *a, **k: p == env.record_file) as record_lock:
            lines = disconnect(env)
        check("移除：OmniKit 的 skills 都拿掉，engine/skills 與使用者的不動",
              not present(claude_alpha) and not present(codex_alpha) and not present(agy_alpha)
              and not present(agy_skills / "beta") and (src / "alpha" / "SKILL.md").exists()
              and (home / ".agents" / "skills" / "mine").exists() and (home / ".agents" / "skills" / "beta").exists()
              and (agy_skills / "ag-mine" / "SKILL.md").exists())
        check("移除：三邊的 MCP 拿掉，別人的不動",
              "devtools" not in read_servers(env, "claude-code") and "mine" in read_servers(env, "claude-code")
              and "devtools" not in read_servers(env, "codex") and "keep" in read_servers(env, "antigravity"))
        check("移除：Antigravity 區塊原地拿掉，硬連結還在",
              profiles.text(home / ".gemini" / "GEMINI.md") == "# 我的 Antigravity 規則\n"
              and os.path.samefile(home / ".gemini" / "GEMINI.md", home / ".dsh" / "AGENTS.md"))
        check("移除：Codex 只剩區塊，還原安裝前的備份",
              profiles.text(home / ".codex" / "AGENTS.md") == "# 我的 Codex 規則\n"
              and not (home / ".codex" / "AGENTS.md.pre-omnikit").exists())
        check("移除：刪掉 agents.json（被防毒短暫鎖住時等一下再試）", not env.record_file.exists() and record_lock.calls == 2)

        # 用 claude 指令寫 MCP（假的 claude：照參數改 ~/.claude.json）
        fake = tmp / "fake_claude.py"
        put(fake, "import json, sys\nfrom pathlib import Path\n"
                  f"p = Path(r'{home / '.claude.json'}')\nd = json.loads(p.read_text(encoding='utf-8'))\na = sys.argv[1:]\n"
                  "s = d.setdefault('mcpServers', {})\n"
                  "if a[:2] == ['mcp', 'add-json']: s[a[4]] = json.loads(a[5])\n"
                  "if a[:2] == ['mcp', 'remove']: s.pop(a[4])\n"
                  "p.write_text(json.dumps(d), encoding='utf-8')\n")
        cli_env = Env(home=home, repo=repo, state=state, skillshare=ss, which=lambda _: None,
                      claude_cli=[sys.executable, str(fake)])
        cfg = {"type": "stdio", "command": "cmd"}
        claude_apply(cli_env, {"devtools": (cfg, set(managed_keys(cfg)))})
        check("有 claude 指令：用 claude mcp add-json 寫入", read_servers(env, "claude-code")["devtools"]["command"] == "cmd")
        claude_apply(cli_env, {"devtools": (None, set())})
        check("有 claude 指令：用 claude mcp remove 移除", "devtools" not in read_servers(env, "claude-code"))

        # ---- 同事版：免問核准要本人同意；MCP 被改過、被移除或同名不是 OmniKit 的，停下來問 ----
        approve_yaml = ("servers:\n  devtools:\n    command: cmd\n    args: [/c, node, x.js]\n"
                        "    targets: [claude, codex, antigravity]\n"
                        "    options:\n      codex:\n        default_tools_approval_mode: approve\n")
        put(servers_yaml, approve_yaml)
        put(repo / "data" / "harness" / "claude-allow.txt", "# 免問的權限規則\nmcp__devtools\n")
        home2, state2 = tmp / "home2", tmp / "state2"
        put(home2 / ".claude" / "CLAUDE.md", "# 同事的 Claude 規則\n")
        put(home2 / ".codex" / "AGENTS.md", "# 同事原本的 Codex 規則\n")
        put(home2 / ".codex" / "config.toml", 'model = "gpt"\n')
        (home2 / ".gemini" / "config").mkdir(parents=True)
        env2 = Env(home=home2, repo=repo, state=state2, skillshare=tmp / "none", which=lambda _: None)
        edition.set_edition(state2, "colleague")
        connect(env2)
        codex_rules = profiles.text(home2 / ".codex" / "AGENTS.md")
        check("同事版：Codex 原本的規則留在區塊外，照常生效",
              codex_rules.startswith(profiles.BEGIN) and codex_rules.endswith(profiles.END + "\n# 同事原本的 Codex 規則\n"))
        devtools = read_servers(env2, "codex")["devtools"]
        check("同事版、還沒同意：Codex 不寫免問核准，其他照寫",
              "default_tools_approval_mode" not in devtools and devtools["command"] == "cmd")
        check("approvals：列出要同意的工具、會寫什麼與狀態",
              any("devtools（還沒問）" in line and "default_tools_approval_mode" in line for line in approvals(env2)))
        asked = []
        approvals(env2, ask=lambda tool, what: asked.append(tool))
        check("approvals --ask：只問還沒問過的；沒回答就不記", asked == ["devtools"] and edition.decided(state2, "devtools") is None)
        claude_settings = home2 / ".claude" / "settings.json"
        approvals(env2, grant=["devtools"])
        check("同意之後馬上套用：Codex 寫上 default_tools_approval_mode，Claude Code 加上 mcp__devtools",
              read_servers(env2, "codex")["devtools"].get("default_tools_approval_mode") == "approve"
              and "mcp__devtools" in json.loads(claude_settings.read_text(encoding="utf-8"))["permissions"]["allow"])
        check("同意不存在的工具：失敗", fails(lambda: approvals(env2, grant=["nope"])))

        # 使用者加的欄位與 Codex 自己寫的工具核准紀錄（子表格），OmniKit 更新時都要留著
        toml2, gem2 = home2 / ".codex" / "config.toml", home2 / ".gemini" / "config" / "mcp_config.json"
        text2 = toml2.read_text(encoding="utf-8").replace("[mcp_servers.devtools]\n", "[mcp_servers.devtools]\nstartup_timeout_sec = 30\n")
        put(toml2, text2 + '\n[mcp_servers.devtools.tools.click]\napproval_mode = "approve"\n')
        approvals(env2, revoke=["devtools"])
        devtools = read_servers(env2, "codex")["devtools"]
        check("撤回同意：拿掉 Codex 的免問核准；使用者加的欄位與工具核准紀錄都留著",
              "default_tools_approval_mode" not in devtools and devtools.get("startup_timeout_sec") == 30
              and devtools.get("tools") == {"click": {"approval_mode": "approve"}})
        check("撤回同意：Claude Code 的 mcp__devtools 也拿掉",
              "mcp__devtools" not in json.loads(claude_settings.read_text(encoding="utf-8")).get("permissions", {}).get("allow", []))
        doc = json.loads(gem2.read_text(encoding="utf-8"))
        doc["mcpServers"]["devtools"]["disabled"] = True
        put(gem2, json.dumps(doc))
        put(servers_yaml, approve_yaml.replace("x.js", "y.js"))
        sync(env2, skills=False)
        gem_devtools, codex_text2 = read_servers(env2, "antigravity")["devtools"], toml2.read_text(encoding="utf-8")
        check("servers.yaml 改了：Antigravity 更新參數，使用者加的 disabled 留著",
              gem_devtools["args"][-1] == "y.js" and gem_devtools.get("disabled") is True)
        check("servers.yaml 改了：Codex 原地更新，工具核准紀錄還在，表格只有一份",
              read_servers(env2, "codex")["devtools"]["tools"] == {"click": {"approval_mode": "approve"}}
              and codex_text2.count("[mcp_servers.devtools]") == 1 and '"y.js"' in codex_text2)

        # 使用者在 Codex 改了 OmniKit 管的 args：下次同步略過 Codex 的這個 server，其他照常
        put(toml2, codex_text2.replace('"y.js"', '"mine.js"'))
        snap = toml2.read_bytes()
        put(servers_yaml, approve_yaml.replace("x.js", "z.js"))
        msg = exit_message(lambda: sync(env2))
        check("使用者在 Codex 改過 args：略過 Codex 的這個 server，只列欄位名稱不列值，其他 agent 照常更新",
              "OmniKit 寫入之後被改過" in msg and "args" in msg and "mine.js" not in msg and "--keep-mine" in msg
              and toml2.read_bytes() == snap and read_servers(env2, "claude-code")["devtools"]["args"][-1] == "z.js")
        lines = sync(env2, ask=lambda c: "mine")
        check("問的時候選保留自己的：Codex 的 args 不動，其他 agent 照常更新",
              read_servers(env2, "codex")["devtools"]["args"][-1] == "mine.js"
              and read_servers(env2, "claude-code")["devtools"]["args"][-1] == "z.js"
              and any("你選了自己管" in line for line in lines))
        rec2 = load_record(env2)
        check("記下選擇：Codex 的 devtools 由使用者自己管，帳本拿掉",
              rec2["mcp_keep"]["codex"] == ["devtools"] and "devtools" not in rec2["mcp"]["codex"])
        sync(env2)
        check("之後同步：不再問，也不改回來", read_servers(env2, "codex")["devtools"]["args"][-1] == "mine.js")
        resolve_conflict(env2, "devtools", "omnikit", agent="codex")
        devtools = read_servers(env2, "codex")["devtools"]
        check("resolve --use-omnikit：改回 OmniKit 的設定，使用者加的欄位與工具核准紀錄還在",
              devtools["args"][-1] == "z.js" and devtools.get("startup_timeout_sec") == 30 and "tools" in devtools
              and "codex" not in load_record(env2)["mcp_keep"])

        # 使用者移除了 OmniKit 加的 server：不悄悄加回去
        doc = json.loads(gem2.read_text(encoding="utf-8"))
        del doc["mcpServers"]["devtools"]
        put(gem2, json.dumps(doc))
        msg = exit_message(lambda: sync(env2, skills=False))
        check("使用者移除了 OmniKit 加的 server：略過並列出來，不加回去",
              "被移除了" in msg and "devtools" not in read_servers(env2, "antigravity"))
        resolve_conflict(env2, "devtools", "mine")
        sync(env2, skills=False)
        check("選保留自己的（移除）：之後不再加回去", "devtools" not in read_servers(env2, "antigravity"))

        # 舊版的 agents.json 只記名稱：一樣的補上雜湊；不一樣的確認不了是誰改的，停下來問
        def legacy_record():
            raw = json.loads(env2.record_file.read_text(encoding="utf-8"))
            raw["mcp"] = {a: sorted(names) for a, names in raw["mcp"].items()}
            put(env2.record_file, json.dumps(raw))

        legacy_record()
        sync(env2, skills=False)
        check("舊版記錄（只有名稱）、設定一樣：補上雜湊，不衝突",
              all(isinstance(e, dict) for a in ("claude-code", "codex") for e in load_record(env2)["mcp"][a].values()))
        legacy_record()
        put(servers_yaml, approve_yaml.replace("x.js", "w.js"))
        msg = exit_message(lambda: sync(env2, skills=False))
        check("舊版記錄（只有名稱）又跟 servers.yaml 不同：略過並列出來", "舊版的記錄沒有雜湊" in msg)
        put(servers_yaml, approve_yaml.replace("x.js", "z.js"))
        sync(env2, skills=False)

        put(toml2, toml2.read_text(encoding="utf-8").replace('"z.js"', '"mine2.js"'))
        lines = disconnect(env2)
        check("移除：被使用者改過的 MCP 當成他的，留著；其他照常拿掉",
              "devtools" in read_servers(env2, "codex") and "devtools" not in read_servers(env2, "claude-code")
              and any("當成你的設定" in line for line in lines))
        check("移除：Codex 區塊拿掉，原本的規則留著，多餘的備份收掉",
              profiles.text(home2 / ".codex" / "AGENTS.md") == "# 同事原本的 Codex 規則\n"
              and not (home2 / ".codex" / "AGENTS.md.pre-omnikit").exists())

        # 第一次接上就遇到同名但不是 OmniKit 的：那個 server 不動，規則與 skills 照常接上
        home3, state3 = tmp / "home3", tmp / "state3"
        put(home3 / ".claude" / "CLAUDE.md", "# 我的\n")
        put(home3 / ".claude.json", json.dumps({"mcpServers": {"devtools": {"type": "stdio", "command": "mine"}}}))
        env3 = Env(home=home3, repo=repo, state=state3, skillshare=tmp / "none", which=lambda _: None)
        edition.set_edition(state3, "colleague")
        before3 = [(home3 / ".claude" / "CLAUDE.md").read_bytes(), (home3 / ".claude.json").read_bytes()]
        msg = exit_message(lambda: connect(env3, agents=["claude-code"]))
        check("第一次接上遇到同名但不是 OmniKit 的 server：那個 server 不動，規則照常接上",
              "不是 OmniKit 加的" in msg and env3.record_file.exists()
              and read_servers(env3, "claude-code")["devtools"]["command"] == "mine"
              and profiles.BEGIN in profiles.text(home3 / ".claude" / "CLAUDE.md"))
        connect(env3, agents=["claude-code"], ask=lambda c: "mine")
        check("問的時候選保留自己的：同名的不動，其他照常接上",
              read_servers(env3, "claude-code")["devtools"]["command"] == "mine"
              and profiles.BEGIN in profiles.text(home3 / ".claude" / "CLAUDE.md")
              and load_record(env3)["mcp_keep"]["claude-code"] == ["devtools"])

        # 其他 Claude 設定目錄（T3 Code 的多帳號）：規則區塊與 skills 也接上，disconnect 一起拿掉
        home4, state4 = tmp / "home4", tmp / "state4"
        put(home4 / ".claude" / "CLAUDE.md", "# 我的\n")
        kai = home4 / ".claude-kai"
        put(kai / "skills" / "synced" / "x.txt", "Claude 自己同步的\n")
        env4 = Env(home=home4, repo=repo, state=state4, skillshare=tmp / "none", which=lambda _: None, claude_homes=[kai])
        edition.set_edition(state4, "colleague")
        connect(env4, agents=["claude-code"], ask=lambda c: "mine")
        names4 = [n for n in skill_names(repo / "engine" / "skills") if n not in profiles.skipped_skills(env4.data, state4, "default")]
        check("其他 Claude 設定目錄：CLAUDE.md 放受管區塊，skills 也連進去，原本的 skills 不動",
              profiles.text(kai / "CLAUDE.md").startswith(profiles.BEGIN)
              and all(present(kai / "skills" / n) for n in names4) and (kai / "skills" / "synced" / "x.txt").exists()
              and sorted(load_record(env4)["skills"][extra_key(kai)]) == sorted(names4))
        check("其他 Claude 設定目錄：MCP 寫進 <目錄>/.claude.json，帳本與 homes 用 <agent>@<目錄> 記",
              read_servers(env4, extra_key(kai)).get("devtools", {}).get("command") == "cmd"
              and extra_key(kai) in load_record(env4)["mcp"] and load_record(env4)["homes"] == [extra_key(kai)])
        disconnect(env4)
        check("其他 Claude 設定目錄：disconnect 拿掉區塊、skills 與 MCP，原本的留著",
              not (kai / "CLAUDE.md").exists() and not any(present(kai / "skills" / n) for n in names4)
              and (kai / "skills" / "synced" / "x.txt").exists() and "devtools" not in read_servers(env4, extra_key(kai)))

        # ~/.claude 使用者自己的 skill 與 plugin：同步到其他 Claude 設定目錄（T3 Code 的 retis、Kai 帳號）
        home7, state7 = tmp / "home7", tmp / "state7"
        c7 = home7 / ".claude"
        put(c7 / "CLAUDE.md", "# 我的\n")
        put(c7 / "skills" / "unslop" / "SKILL.md", "---\nname: unslop\n---\n")
        put(c7 / "skills" / "caveman" / "SKILL.md", "---\nname: caveman\n---\n")
        put(c7 / "skills" / "omnikeep-setup.bak-20261118" / "SKILL.md", "備份\n")
        put(c7 / "skills" / ".trash" / "old" / "SKILL.md", "丟掉的\n")
        put(c7 / "skills" / "synced" / "abc" / "SKILL.md", "claude.ai 同步的\n")
        put(home7 / ".agents" / "skills" / "archify" / "SKILL.md", "---\nname: archify\n---\n")
        make_link(home7 / ".agents" / "skills" / "archify", c7 / "skills" / "archify")
        put(c7 / "settings.json", json.dumps({
            "enabledPlugins": {"mem@mem": True, "taste@taste": True, "off@mem": False, "needs-cmd@mem": True},
            "extraKnownMarketplaces": {"taste": {"source": {"source": "github", "repo": "o/taste"}},
                                       "floor": {"source": {"source": "git", "url": "https://x/floor.git"}}},
            "env": {"SECRET_TOKEN": "不能被複製"}}))
        put(c7 / "plugins" / "known_marketplaces.json",
            json.dumps({"mem": {"source": {"source": "github", "repo": "o/mem"}, "installLocation": "x"}}))
        retis, kai7 = home7 / ".claude-retis", home7 / ".claude-kai"
        put(kai7 / "skills" / "unslop" / "SKILL.md", "---\nname: unslop\n---\n這個帳號自己的\n")
        fake7, calls7 = {}, []

        def runner7(cmd, environ):
            st = fake7.setdefault(environ.get("CLAUDE_CONFIG_DIR"), {"plugins": {}, "markets": set()})
            args = cmd[1:]
            calls7.append((environ.get("CLAUDE_CONFIG_DIR"), args))
            if args[:2] == ["plugin", "list"]:
                return 0, "提示文字\n" + json.dumps([{"id": k, "enabled": v} for k, v in st["plugins"].items()]), ""
            if args[:3] == ["plugin", "marketplace", "list"]:
                return 0, json.dumps([{"name": n} for n in sorted(st["markets"])]), ""
            if args[:3] == ["plugin", "marketplace", "add"]:
                st["markets"].add({"o/mem": "mem", "o/taste": "taste", "https://x/floor.git": "floor"}[args[3]])
                return 0, "", ""
            if args[:2] == ["plugin", "install"]:
                if args[2].split("@")[1] not in st["markets"]:
                    return 1, "", "marketplace not found"
                if args[2].startswith("needs-cmd"):
                    return 1, "", "requires -y when stdin is not a TTY"
                st["plugins"][args[2]] = True
                return 0, "", ""
            if args[:2] in (["plugin", "disable"], ["plugin", "enable"]):
                st["plugins"][args[2]] = args[1] == "enable"
                return 0, "", ""
            return 1, "", "unknown"

        env7 = Env(home=home7, repo=repo, state=state7, skillshare=tmp / "none", which=lambda _: None,
                   claude_homes=[retis, kai7], runner=runner7)
        edition.set_edition(state7, "colleague")
        lines = connect(env7, agents=["claude-code"], ask=lambda c: "mine")
        check("使用者的 skill：其他 Claude 設定目錄連到 ~/.claude 的實際位置；備份、. 開頭、沒有 SKILL.md、OmniKit 的不同步",
              all(is_link(retis / "skills" / n) for n in ("unslop", "caveman", "archify"))
              and same_path(os.path.realpath(retis / "skills" / "archify"), os.path.realpath(home7 / ".agents" / "skills" / "archify"))
              and not any(present(retis / "skills" / n) for n in ("omnikeep-setup.bak-20261118", ".trash", "synced"))
              and sorted(load_record(env7)["user_skills"][extra_key(retis)]) == ["archify", "caveman", "unslop"]
              and is_link(retis / "skills" / "alpha") and same_path(link_target(retis / "skills" / "alpha"), src / "alpha"))
        check("使用者的 skill：目標已經有同名、不是連過去的，不動並印出來",
              not is_link(kai7 / "skills" / "unslop") and "這個帳號自己的" in (kai7 / "skills" / "unslop" / "SKILL.md").read_text(encoding="utf-8")
              and is_link(kai7 / "skills" / "caveman") and any("不是從 ~/.claude 連過去的" in line for line in lines))
        check("plugin：沒有 claude 指令就不同步，說一聲", any("找不到 claude 指令" in line for line in lines) and not calls7)
        env7.claude_cli = ["claude"]
        lines = sync(env7, mcp=False)
        st_r, st_k = fake7[str(retis)], fake7[str(kai7)]
        check("plugin：啟用中的用 claude plugin 裝進每個設定目錄（CLAUDE_CONFIG_DIR 指過去），缺 marketplace 先加，停用的不裝",
              st_r["plugins"] == {"mem@mem": True, "taste@taste": True} == st_k["plugins"]
              and st_r["markets"] == {"mem", "taste"} and not any(d is None for d, _ in calls7)
              and ["plugin", "marketplace", "add", "o/mem", "--scope", "user"] in [a for _, a in calls7]
              and ["plugin", "install", "taste@taste", "--scope", "user"] in [a for _, a in calls7])
        check("plugin：裝不起來的（要本人確認指令）印一行，其他照常",
              any("needs-cmd@mem" in line and "沒有同步" in line for line in lines))
        check("plugin：設定檔其他欄位與金鑰不碰", not (retis / "settings.json").exists()
              or "SECRET_TOKEN" not in (retis / "settings.json").read_text(encoding="utf-8"))
        calls7.clear()
        lines = sync(env7, mcp=False)
        check("重跑：已經同步的不再裝、不再連（只讀清單）",
              all(a[:2] == ["plugin", "list"] or a[:3] == ["plugin", "marketplace", "list"] or a[2].startswith("needs-cmd")
                  for _, a in calls7) and not any("新增" in line or "新裝" in line for line in lines))
        # 之後在 ~/.claude 新裝 skill、啟用新的 plugin（marketplace 只在 extraKnownMarketplaces）、停用一個、拿掉一個 skill
        put(c7 / "skills" / "web-unblock" / "SKILL.md", "---\nname: web-unblock\n---\n")
        remove_tree(c7 / "skills" / "caveman")
        doc7 = read_json(c7 / "settings.json")
        doc7["enabledPlugins"].update({"floor@floor": True, "taste@taste": False})
        put(c7 / "settings.json", json.dumps(doc7))
        st_k["plugins"]["mem@mem"] = False  # 使用者在 Kai 帳號自己停用
        lines = sync(env7, mcp=False)
        check("重跑：新的 skill 補上，~/.claude 拿掉的只拿掉 OmniKit 建的連結",
              is_link(retis / "skills" / "web-unblock") and not present(retis / "skills" / "caveman")
              and not present(kai7 / "skills" / "caveman") and (kai7 / "skills" / "unslop" / "SKILL.md").exists())
        check("重跑：新啟用的 plugin 補裝（來源照 extraKnownMarketplaces），~/.claude 停用的這裡也停用",
              st_r["plugins"] == {"mem@mem": True, "taste@taste": False, "floor@floor": True}
              and load_record(env7)["user_plugins"][extra_key(retis)]["disabled"] == ["taste@taste"])
        check("重跑：使用者在那個帳號自己停用的不動", st_k["plugins"]["mem@mem"] is False
              and any("當成你的選擇" in line for line in lines))
        doc7["enabledPlugins"]["taste@taste"] = True
        put(c7 / "settings.json", json.dumps(doc7))
        sync(env7, mcp=False)
        check("重跑：~/.claude 又啟用，OmniKit 停用的那份再啟用", st_r["plugins"]["taste@taste"] is True
              and load_record(env7)["user_plugins"][extra_key(retis)]["disabled"] == [])
        env7.claude_cli = None  # disconnect 的 MCP 走直接改檔，不跑真的 claude 指令
        lines = disconnect(env7)
        check("disconnect：拿掉連到 ~/.claude 的連結，來源與目標自己的 skill 留著，plugin 不解除安裝",
              not present(retis / "skills" / "unslop") and (c7 / "skills" / "unslop" / "SKILL.md").exists()
              and (kai7 / "skills" / "unslop" / "SKILL.md").exists() and (home7 / ".agents" / "skills" / "archify").is_dir()
              and any("plugin 留著" in line for line in lines))

        # 安裝之後才多出來的設定目錄（新的 Claude 帳號、CODEX_HOME）：sync 就接上，不用重跑 install
        home5, state5 = tmp / "home5", tmp / "state5"
        put(home5 / ".claude" / "CLAUDE.md", "# 我的\n")
        put(home5 / ".codex" / "AGENTS.md", "# 我的 Codex\n")
        env5 = Env(home=home5, repo=repo, state=state5, skillshare=tmp / "none", which=lambda _: None)
        edition.set_edition(state5, "maintainer")
        connect(env5, agents=["claude-code", "codex"], ask=lambda c: "mine")
        check("沒有其他設定目錄：homes 記成空的", load_record(env5)["homes"] == [])
        work, cx = home5 / ".claude-work", home5 / ".codex-work"
        put(cx / "AGENTS.md", "# 這個帳號原本的\n")
        put(cx / "config.toml", 'model = "o"\n')
        env5.claude_homes, env5.codex_homes = [work], [cx]
        work.mkdir()
        lines = sync(env5)
        settings5 = read_json(work / "settings.json")
        check("sync 接上新的 Claude 設定目錄：規則區塊、skills、MCP、權限規則與 hook",
              profiles.text(work / "CLAUDE.md").startswith(profiles.BEGIN)
              and all(present(work / "skills" / n) for n in ("alpha", "beta"))
              and "devtools" in read_servers(env5, extra_key(work))
              and any(claude_allow.is_ours(h, claude_allow.WATCH) for g in settings5["hooks"]["SessionStart"] for h in g["hooks"])
              and any("找到新的設定目錄" in line for line in lines))
        check("sync 接上新的 Codex 設定目錄：規則區塊接手（原本的備份、留在區塊外），MCP 寫進它的 config.toml",
              profiles.BLOCK.search(profiles.text(cx / "AGENTS.md")) is not None
              and profiles.text(cx / "AGENTS.md").endswith("# 這個帳號原本的\n") and (cx / "AGENTS.md.pre-omnikit").exists()
              and read_servers(env5, extra_key(cx, "codex"))["devtools"]["command"] == "cmd"
              and tomllib.loads(profiles.text(cx / "config.toml"))["model"] == "o"
              and sorted(load_record(env5)["homes"]) == sorted([extra_key(work), extra_key(cx, "codex")]))
        profiles.write(cx / "AGENTS.md", "# 我把區塊拿掉了\n")
        sync(env5)
        check("已經接上過的設定目錄：使用者拿掉區塊就不加回去", profiles.text(cx / "AGENTS.md") == "# 我把區塊拿掉了\n")
        disconnect(env5)
        check("disconnect：其他 Codex 設定目錄的 MCP 拿掉，使用者的設定留著",
              "devtools" not in read_servers(env5, extra_key(cx, "codex"))
              and tomllib.loads(profiles.text(cx / "config.toml"))["model"] == "o")

        # T3 Code 的 Antigravity 實例：connect 把 Binary path 指到轉接程式，homes 記實例的 key；disconnect 改回來
        home6, state6 = tmp / "home6", tmp / "state6"
        put(home6 / ".gemini" / "GEMINI.md", "# 我的\n")
        t3_settings = home6 / ".t3" / "userdata" / "settings.json"
        put(t3_settings, json.dumps({"providerInstances": {"antigravity": {"driver": "antigravity", "enabled": True}}}, indent=2) + "\n")
        env6 = Env(home=home6, repo=repo, state=state6, skillshare=tmp / "none", which=lambda _: None)
        edition.set_edition(state6, "maintainer")
        lines = connect(env6, agents=["antigravity"], ask=lambda c: "mine")
        key6 = t3_acp.instance_key(home6, "antigravity")
        if sys.platform == "win32":
            check("T3 的 Antigravity 實例：connect 把 Binary path 指到轉接程式，homes 記實例的 key",
                  read_json(t3_settings)["providerInstances"]["antigravity"]["config"]["binaryPath"]
                  == str(home6 / ".omnikit" / "acp" / t3_acp.LAUNCHER)
                  and load_record(env6)["homes"] == [key6] and (home6 / ".omnikit" / "acp" / t3_acp.SHIM).is_file())
            disconnect(env6)
            check("T3 的 Antigravity 實例：disconnect 改回 T3 自動選，轉接程式刪掉",
                  "config" not in read_json(t3_settings)["providerInstances"]["antigravity"] and not (home6 / ".omnikit" / "acp").exists())
        else:
            check("T3 的 Antigravity 實例：Windows 以外說明不支援，設定不動",
                  any("只支援 Windows" in line for line in lines) and load_record(env6)["homes"] == [key6]
                  and "config" not in read_json(t3_settings)["providerInstances"]["antigravity"])

        # claude 指令改哪個設定目錄：預設的拿掉 CLAUDE_CONFIG_DIR，其他的指過去
        os.environ["CLAUDE_CONFIG_DIR"] = str(tmp / "some-session")
        try:
            check("claude 指令：預設的不帶 CLAUDE_CONFIG_DIR（在其他帳號的對話裡跑也不會寫錯地方）",
                  "CLAUDE_CONFIG_DIR" not in claude_env("claude-code")
                  and claude_env(extra_key(kai))["CLAUDE_CONFIG_DIR"] == str(kai))
        finally:
            del os.environ["CLAUDE_CONFIG_DIR"]
        for d in readonly:
            writable(d)

        # status：印出狀態資料夾；舊位置（%LOCALAPPDATA%\omnikit 等）還有沒合併的就列出來
        import contextlib
        import io
        old_local = tmp / "old-local"
        put(old_local / "omnikit" / "agents.json", "{}")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            status(env6, {"LOCALAPPDATA": str(old_local)})
        shown = json.loads(out.getvalue())
        check("status：印出狀態資料夾與還沒合併的舊位置",
              shown["state"] == str(state6) and shown["legacy"] == [str(old_local / "omnikit")])
        check("搬家沒有搬到東西：不重新接上規則", after_migrate(env6, statedir.Result(state6)) == [])

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 OmniKit 接到 Claude Code、Codex 與 Antigravity")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    c = sub.add_parser("connect", help="接上 agent：規則、skills 與 MCP（install.ps1 用）")
    c.add_argument("--profile", help="同時換成這個 profile")
    c.add_argument("--agents", help=f"只接這些，用逗號分隔：{','.join(AGENTS)}；預設是偵測到的")
    c.add_argument("--ask", action="store_true", help="MCP 有衝突時逐一問（要能互動）")
    s = sub.add_parser("sync", help="依記錄同步 skills 與 MCP（維護者版的 git hook 用）")
    s.add_argument("--skills", action="store_true", help="只同步 skills")
    s.add_argument("--mcp", action="store_true", help="只同步 MCP")
    s.add_argument("--plugins", action="store_true", help="只把 ~/.claude 啟用中的 plugin 同步到其他 Claude 設定目錄")
    s.add_argument("--ask", action="store_true", help="MCP 有衝突時逐一問（要能互動）")
    r = sub.add_parser("resolve", help="決定 MCP 衝突要用誰的設定，並馬上同步")
    r.add_argument("name", metavar="名稱", help="MCP server 名稱")
    choice = r.add_mutually_exclusive_group(required=True)
    choice.add_argument("--use-omnikit", action="store_true", help="改用 data/mcp/servers.yaml 的設定")
    choice.add_argument("--keep-mine", action="store_true", help="保留你的設定，OmniKit 之後不管它")
    r.add_argument("--agent", choices=AGENTS, help="只處理這個 agent；預設是有衝突的全部")
    a = sub.add_parser("approvals", help="免問核准：查看、逐一詢問、同意或撤回（同事版本人同意了才寫入）")
    a.add_argument("--ask", action="store_true", help="逐一問還沒問過的（要能互動；install.ps1 用）")
    a.add_argument("--grant", action="append", default=[], metavar="名稱", help="同意這個工具免問，並馬上套用")
    a.add_argument("--revoke", action="append", default=[], metavar="名稱", help="撤回同意，並馬上套用")
    sub.add_parser("disconnect", help="拿掉 OmniKit 的 skills、MCP 與 Codex、Antigravity 的規則區塊（uninstall.ps1 用）")
    sub.add_parser("status", help="印出偵測到的 agent 與記錄")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    env = real_env()
    interactive = sys.stdin.isatty()
    if args.command == "status":
        return status(env)
    moved = statedir.migrate(env.state) if args.command else statedir.Result(env.state)
    for line in moved.lines():
        print(line)
    if args.command == "connect":
        agents = args.agents.split(",") if args.agents else None
        if agents and (bad := [a for a in agents if a not in AGENTS]):
            parser.error(f"不認得的 agent：{'、'.join(bad)}")
        lines = connect(env, args.profile, agents, ask=ask_conflict if args.ask and interactive else None)
    elif args.command == "sync":
        every = not (args.skills or args.mcp or args.plugins)
        lines = after_migrate(env, moved) + sync(env, skills=args.skills or every, mcp=args.mcp or every,
                                                 ask=ask_conflict if args.ask and interactive else None,
                                                 plugins=args.plugins or every)
    elif args.command == "resolve":
        lines = resolve_conflict(env, args.name, "omnikit" if args.use_omnikit else "mine", args.agent)
    elif args.command == "approvals":
        lines = approvals(env, ask=ask_approval if args.ask and interactive else None, grant=args.grant, revoke=args.revoke)
        if args.ask and not interactive and edition.resolve(env.state, env.repo)[0] != "maintainer":
            lines.append(f"沒辦法詢問（不能互動）：還沒問的免問核准先不寫入；要同意就執行 {claude_allow.GRANT}")
    elif args.command == "disconnect":
        lines = disconnect(env)
    else:
        parser.print_help()
        return 2
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
