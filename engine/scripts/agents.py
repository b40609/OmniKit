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
  - Codex 與 Antigravity 共用 ~/.agents/skills/<名稱>，用複製：Antigravity 不跟隨資料夾連結。
    複製品裡放 .omnikit.json，記來源、repo 位置與內容雜湊；內容變了才重新複製
- MCP：data/mcp/servers.yaml 的 server，只動 OmniKit 管的欄位（command、args、env 與 options 給的）
  - Claude Code：claude mcp add-json -s user（找不到 claude 指令才直接改 ~/.claude.json）
  - Codex：~/.codex/config.toml 的 [mcp_servers.<名稱>]，原地換掉 OmniKit 管的欄位；使用者加的欄位與
    其他子表格（例如工具核准紀錄）留著。寫入前用 tomllib 比對，除了這些 server 什麼都沒變才寫
  - Antigravity：~/.gemini/config/mcp_config.json，不寫 BOM（Antigravity 讀到 BOM 會整份失敗）
  - 帳本：agents.json 記每個 server 寫入時、OmniKit 管的欄位的雜湊。同步前先比對，使用者改過的、
    OmniKit 加過但被移除的、同名但不是 OmniKit 的，都算衝突：停下來問（--ask），或列出來並停下，
    規則、skills、MCP 都不寫。用 resolve 決定要用誰的設定
  - 免問核准的欄位（Codex 的 default_tools_approval_mode）：同事版要本人同意才寫（approvals，見 edition.py）

接上了哪些 agent、管了哪些 skills 與 MCP server，記在 %LOCALAPPDATA%\\omnikit\\agents.json；
同步只動記錄裡的 agent，移除時只拿掉 OmniKit 的東西，同名但不是 OmniKit 的不碰。

用法：
  uv run engine/scripts/agents.py connect [--profile <名稱>] [--agents claude-code,codex,antigravity] [--ask]
  uv run engine/scripts/agents.py sync [--skills] [--mcp] [--ask]
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
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_allow  # noqa: E402  Claude Code 的免問權限規則
import codex_hooks  # noqa: E402  讀寫 config.toml 時保留原本的換行
import edition  # noqa: E402  維護者版或同事版，以及免問核准的個人同意
import profiles  # noqa: E402
import validate  # noqa: E402

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
    which: object = shutil.which

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
    def skill_dirs(self):
        return {"claude-code": (self.home / ".claude" / "skills", "link"),
                "shared": (self.home / ".agents" / "skills", "copy")}

    @property
    def claude_json(self):
        return self.home / ".claude.json"

    @property
    def codex_toml(self):
        return self.home / ".codex" / "config.toml"

    @property
    def gemini_mcp(self):
        return self.home / ".gemini" / "config" / "mcp_config.json"


def real_env():
    claude = shutil.which("claude")
    return Env(home=Path.home(), repo=profiles.ROOT, state=profiles.STATE,
               skillshare=Path(os.environ.get("APPDATA", Path.home())) / "skillshare",
               claude_cli=[claude] if claude else None)


def detect(env):
    h, which = env.home, env.which
    found = []
    if (h / ".claude").is_dir() or which("claude"):
        found.append("claude-code")
    if (h / ".codex").is_dir() or which("codex"):
        found.append("codex")
    if (h / ".gemini" / "config").is_dir() or (h / ".gemini" / "antigravity").is_dir() or which("agy") or which("antigravity"):
        found.append("antigravity")
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
    for key, empty in (("agents", []), ("skills", {}), ("mcp", {}), ("mcp_keep", {})):
        rec.setdefault(key, empty)
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
    def force(func, p, _exc):
        writable(p)
        writable(os.path.dirname(p))
        func(p)

    shutil.rmtree(path, onexc=force)


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
    （engine/skills 的資料夾常帶唯讀屬性，複製過去就刪不掉；有程式開著資料夾時也刪不掉）。"""
    dest.mkdir(parents=True, exist_ok=True)
    writable(dest)
    wanted = source_files(src_dir)
    for rel, src in wanted.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        writable(target.parent)
        if not target.is_file() or target.read_bytes() != src.read_bytes():
            if target.exists():
                writable(target)
            shutil.copyfile(src, target)
    for p in sorted(dest.rglob("*"), key=lambda x: -len(x.parts)):
        rel = p.relative_to(dest)
        if rel == Path(MARKER) or rel in wanted:
            continue
        if p.is_dir() and not is_link(p):
            if not any(p.iterdir()):
                writable(p)
                p.rmdir()
        else:
            writable(p)
            p.unlink()
    marker = {"source": str(src_dir), "repo": str(env.repo), "hash": tree_hash(src_dir)}
    (dest / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def skill_targets(agents):
    keys = []
    if "claude-code" in agents:
        keys.append("claude-code")
    if "codex" in agents or "antigravity" in agents:
        keys.append("shared")
    return keys


def target_label(key, agents):
    if key == "claude-code":
        return NAMES["claude-code"]
    return "、".join(NAMES[a] for a in ("codex", "antigravity") if a in agents)


def profile_skips(env, profile=None):
    """（profile 名稱, 不裝的 skill）。找不到 profile 時全部都裝：少裝比多裝難察覺。"""
    try:
        name, _ = profiles.resolve(env.data, env.state, profile)
    except SystemExit:
        return None, {}
    return name, profiles.skipped_skills(env.data, env.state, name)


def sync_skills(env, agents, rec, profile=None):
    profile_name, skip = profile_skips(env, profile)
    names = [n for n in skill_names(env.skills_src) if n not in skip]
    lines = []
    if skip:
        why = "、".join(dict.fromkeys(skip.values()))
        lines.append(f"skills：profile {profile_name} 選了{why}，不裝 {'、'.join(sorted(skip))}")
    for key in skill_targets(agents):
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
        lines.append(f"skills：{target_label(key, agents)} {len(placed)} 個（{how}，{folder}）")
        if copied_instead:
            lines.append(f"  建不起資料夾連結，改用複製：{'、'.join(copied_instead)}")
        for name in skipped:
            lines.append(f"  {folder / name} 已經有同名的 skill，不是 OmniKit 的，沒有動")
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


def run_cli(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"{' '.join(cmd[-5:-2])} 無法執行：{e}")
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(cmd[-5:-2])} 失敗（exit {r.returncode}）：{(r.stderr or r.stdout).strip()}")


def read_servers(env, agent):
    if agent == "claude-code":
        return read_json(env.claude_json).get("mcpServers", {})
    if agent == "codex":
        text, _ = codex_hooks.read(env.codex_toml)
        try:
            return tomllib.loads(text).get("mcp_servers", {})
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"{env.codex_toml} 不是合法的 TOML（{e}），沒有改")
    return read_json(env.gemini_mcp).get("mcpServers", {})


# 寫入：ops 是 {名稱: (設定, 要換掉的欄位)}；設定是 None 表示移除。要不要寫由 plan_mcp 決定，這裡只照做

def claude_apply(env, ops):
    if not ops:
        return []
    current = read_servers(env, "claude-code")
    for name, (cfg, drop) in sorted(ops.items()):
        entry = None if cfg is None else merged(current.get(name), cfg, drop)
        if env.claude_cli:
            if name in current:
                run_cli([*env.claude_cli, "mcp", "remove", "-s", "user", name])
            if entry is not None:
                run_cli([*env.claude_cli, "mcp", "add-json", "-s", "user", name, json.dumps(entry, ensure_ascii=False)])
        else:
            doc = read_json(env.claude_json)
            servers = doc.setdefault("mcpServers", {})
            if entry is None:
                servers.pop(name, None)
            else:
                servers[name] = entry
            profiles.write(env.claude_json, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
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


def codex_apply(env, ops):
    if not ops:
        return []
    path = env.codex_toml
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


def gemini_apply(env, ops):
    path = env.gemini_mcp
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
    agent: str
    name: str
    why: str
    keys: list  # 不同的欄位，只列名稱
    managed: list  # 決定用 OmniKit 的設定時，要換掉的欄位


@dataclass
class McpPlan:
    wanted: dict  # agent → {名稱: OmniKit 要的設定}
    ops: dict  # agent → {名稱: (設定或 None, 要換掉的欄位)}
    ledger: dict  # agent → 寫完之後的帳本
    keep: dict  # agent → [使用者選了自己管的名稱]
    adopted: dict  # agent → [同名而且設定一樣，改由 OmniKit 管的名稱]
    conflicts: list


def plan_mcp(env, agents, rec):
    """比對 servers.yaml、agent 現在的設定與帳本，決定每個 server 要新增、更新、移除、接手，還是衝突。
    只讀不寫。衝突：OmniKit 寫入之後被改過、OmniKit 加過但被移除、同名但不是 OmniKit 的、
    舊版記錄沒有雜湊又跟 servers.yaml 不同。"""
    servers = load_servers(env)
    allowed = edition.approver(env.state, env.repo)
    plan = McpPlan({}, {}, {}, {}, {}, [])
    for agent in agents:
        wanted = {n: desired(s, agent, allowed(n)) for n, s in servers.items() if SHORT[agent] in s["targets"]}
        current = read_servers(env, agent)
        ledger = rec["mcp"].get(agent, {})
        keep = [n for n in rec["mcp_keep"].get(agent, []) if n in wanted]
        ops, new, adopted = {}, {}, []

        def conflict(name, why, keys, managed):
            plan.conflicts.append(Conflict(agent, name, why, keys, sorted(managed)))
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
        plan.wanted[agent], plan.ops[agent], plan.ledger[agent] = wanted, ops, new
        plan.keep[agent], plan.adopted[agent] = keep, adopted
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
    lines = ["MCP 有衝突，這次什麼都沒寫（規則、skills、MCP 都沒動）："]
    for c in conflicts:
        lines.append(f"  - {NAMES[c.agent]} 的 {c.name}：{c.why}" + (f"（不同的欄位：{'、'.join(c.keys)}）" if c.keys else ""))
    lines += ["決定要用誰的設定，擇一執行，再重跑剛才的指令：",
              f"  改用 OmniKit 的設定（data/mcp/servers.yaml）：{RESOLVE} --use-omnikit",
              f"  保留你的設定，OmniKit 之後不再管它：{RESOLVE} --keep-mine"]
    return "\n".join(lines)


def ask_conflict(c):
    """互動時逐一問；直接按 Enter 表示先不處理。"""
    print(f"MCP：{NAMES[c.agent]} 的 {c.name}：{c.why}" + (f"（不同的欄位：{'、'.join(c.keys)}）" if c.keys else ""))
    print("  1) 改用 OmniKit 的設定（data/mcp/servers.yaml）")
    print("  2) 保留你的設定，OmniKit 之後不再管它")
    try:
        answer = input("選 1 或 2（直接按 Enter 先不處理，這次什麼都不寫）：").strip()
    except EOFError:
        return None
    return {"1": "omnikit", "2": "mine"}.get(answer)


def settle(env, agents, rec, ask=None):
    """寫入前先比對 MCP。有衝突就逐一問（ask）；還有沒解決的就停下，規則、skills、MCP 都不寫。"""
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
    if plan.conflicts:
        raise SystemExit(report(plan.conflicts))
    return plan


def apply_mcp(env, agents, rec, plan):
    lines = []
    for agent in agents:
        changed = WRITERS[agent](env, plan.ops[agent])
        rec["mcp"][agent] = plan.ledger[agent]
        rec["mcp_keep"][agent] = plan.keep[agent]
        state = f"（更新：{'、'.join(changed)}）" if changed else "（已是最新）"
        lines.append(f"MCP：{NAMES[agent]} {'、'.join(sorted(plan.wanted[agent])) or '（沒有）'}{state}")
        if plan.adopted[agent]:
            lines.append(f"  同名而且設定一樣，改由 OmniKit 管：{'、'.join(plan.adopted[agent])}")
        if plan.keep[agent]:
            lines.append(f"  你選了自己管，OmniKit 沒動：{'、'.join(plan.keep[agent])}")
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
                config.write_bytes(new.replace("\n", newline).encode("utf-8"))
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
    plan = settle(env, agents, rec, ask)  # MCP 有衝突就停在這裡：規則、skills、MCP 都還沒動
    rec["agents"] = list(agents)
    lines = profiles.apply(env.data, env.state, env.rules, wanted=profile, agents=agents, take_over=True,
                           skillshare_config=env.skillshare / "config.yaml")
    lines += sync_skills(env, agents, rec, profile)
    lines += apply_mcp(env, agents, rec, plan)
    save_record(env, rec)
    lines += release_skillshare(env)
    return lines


def sync(env, skills=True, mcp=True, ask=None):
    rec = load_record(env)
    if not rec["agents"]:
        return ["這台還沒用新的方式接上 agent（沒有 agents.json），skills 與 MCP 沒有同步：重跑 install.ps1"]
    plan = settle(env, rec["agents"], rec, ask) if mcp else None
    lines = []
    if skills:
        lines += sync_skills(env, rec["agents"], rec)
    if mcp:
        lines += apply_mcp(env, rec["agents"], rec, plan)
    save_record(env, rec)
    return lines


def resolve_conflict(env, name, choice, agent=None):
    """使用者決定 MCP 衝突要用誰的設定（choice：omnikit 或 mine），記下來並馬上同步。
    之前選了自己管的，也可以用 omnikit 改回由 OmniKit 管。"""
    rec = load_record(env)
    agents = rec["agents"] or detect(env)
    plan = plan_mcp(env, agents, rec)
    hits = [c for c in plan.conflicts if c.name == name and agent in (None, c.agent)]
    if choice == "omnikit":
        hits += [Conflict(a, name, "你選了自己管", [], managed_keys(plan.wanted[a][name]))
                 for a in agents if name in plan.keep[a] and agent in (None, a)]
    if not hits:
        return [f"MCP：{name} 沒有衝突，不用處理"]
    for c in hits:
        choose(env, rec, c, choice)
    save_record(env, rec)
    how = "改用 OmniKit 的設定" if choice == "omnikit" else "保留你的設定，OmniKit 之後不管它"
    lines = [f"MCP：{NAMES[c.agent]} 的 {name} {how}" for c in hits]
    if not rec["agents"]:
        return lines + ["這台還沒接上 agent：重跑 install.ps1 就會套用"]
    return lines + sync(env, skills=False)  # 其他還沒解決的衝突一樣會停下來


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
                                    env.state, env.repo)
    if not rec["agents"]:
        return lines + ["這台還沒接上 agent：重跑 install.ps1 就會套用"]
    return lines + sync(env, skills=False)


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
    servers = load_servers(env)
    allowed = edition.approver(env.state, env.repo)
    for agent in agents:
        current = read_servers(env, agent)
        if agent in rec["mcp"]:
            # 帳本裡的才拿掉；OmniKit 寫入之後被改過的，已經是使用者的設定，留著
            ledger = rec["mcp"][agent]
            drop = {n for n, e in ledger.items() if n in current and (e is None or digest(current[n], e["keys"]) == e["sha256"])}
            kept = sorted(n for n in ledger if n in current and n not in drop)
        else:
            # 舊版沒有記錄：只拿掉設定跟 servers.yaml 一模一樣的，同名但不同的可能是使用者自己的
            drop = {n for n, s in servers.items()
                    if SHORT[agent] in s["targets"] and same(current.get(n), desired(s, agent, allowed(n)))}
            kept = []
        changed = WRITERS[agent](env, {n: (None, set()) for n in drop})
        if changed:
            lines.append(f"MCP：從 {NAMES[agent]} 拿掉 {'、'.join(changed)}")
        if kept:
            lines.append(f"MCP：{NAMES[agent]} 的 {'、'.join(kept)} 在 OmniKit 寫入之後被改過，當成你的設定，沒有拿掉")
    lines += profiles.disconnect_block(env.rules["codex"])
    lines += profiles.disconnect_block(env.rules["antigravity"])
    lines += release_skillshare(env)
    if env.record_file.exists():
        env.record_file.unlink()
    return lines


def status(env):
    print(json.dumps({"detected": detect(env), **load_record(env)}, ensure_ascii=False, indent=2))
    return 0


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
            fn()
        except SystemExit as e:
            return str(e.code)
        return ""

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

        # 這一段模擬維護者這台的舊安裝：免問核准照 servers.yaml 寫。同事版在後面另一段
        edition.set_edition(state, "maintainer")
        lines = connect(env)
        claude_alpha, shared_alpha = home / ".claude" / "skills" / "alpha", home / ".agents" / "skills" / "alpha"
        check("Claude：舊的 skillshare 連結換成直接連到 engine/skills",
              is_link(claude_alpha) and same_path(link_target(claude_alpha), src / "alpha"))
        check("Codex 與 Antigravity：換成複製品，帶 .omnikit.json",
              not is_link(shared_alpha) and (shared_alpha / "scripts" / "run.py").exists() and (shared_alpha / MARKER).exists())
        marker = json.loads((shared_alpha / MARKER).read_text(encoding="utf-8"))
        check("複製品記下 repo 位置，skill 的腳本找得到 repo", marker["repo"] == str(repo))
        check("不複製 __pycache__", not (shared_alpha / "scripts" / "__pycache__").exists())
        check("同名但不是 OmniKit 的 skill 不動", "使用者自己的" in (home / ".agents" / "skills" / "beta" / "SKILL.md").read_text(encoding="utf-8")
              and any("不是 OmniKit 的" in line for line in lines))
        check("使用者自己的 skill 不動", (home / ".agents" / "skills" / "mine" / "SKILL.md").exists())
        check("Claude：beta 也接上", is_link(home / ".claude" / "skills" / "beta"))

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
        manifest = json.loads((home / ".claude" / "skills" / ".skillshare-manifest.json").read_text(encoding="utf-8"))
        check("skillshare：manifest 拿掉 OmniKit 的 skill，其他保留", manifest["managed"] == {"other": "symlink"})
        rec = load_record(env)
        check("記錄接上的 agent、skills 與 MCP；MCP 帳本記雜湊", rec["agents"] == list(AGENTS)
              and rec["skills"]["shared"] == ["alpha"] and list(rec["mcp"]["codex"]) == ["devtools"]
              and len(rec["mcp"]["codex"]["devtools"]["sha256"]) == 64)

        snapshot = {p: p.read_bytes() for p in (home / ".claude.json", home / ".codex" / "config.toml",
                                                 home / ".gemini" / "config" / "mcp_config.json",
                                                 home / ".gemini" / "GEMINI.md", ss / "config.yaml")}
        connect(env)
        check("重跑 connect：設定檔都不變", all(p.read_bytes() == b for p, b in snapshot.items()))

        put(src / "alpha" / "scripts" / "run.py", "print('alpha v2')\n")
        put(src / "gamma" / "SKILL.md", "---\nname: gamma\n---\n")
        sync(env, mcp=False)
        check("skill 改了：複製品跟著更新，Claude 的連結不用動",
              "v2" in (shared_alpha / "scripts" / "run.py").read_text(encoding="utf-8") and is_link(claude_alpha))
        check("來源資料夾是唯讀的：複製品的資料夾不帶唯讀", os.access(shared_alpha / "scripts", os.W_OK)
              and not (getattr(os.stat(shared_alpha / "scripts"), "st_file_attributes", 0) & 1))

        # 複製品被刪到一半（舊版遇到唯讀資料夾刪不掉）：.omnikit.json 不見了也照記錄認得，原地補齊
        (shared_alpha / MARKER).unlink()
        (shared_alpha / "scripts" / "run.py").unlink()
        put(shared_alpha / "scripts" / "stale.py", "多出來的\n")
        sync(env, mcp=False)
        check("複製品缺檔、標記也不見了：照記錄認出是 OmniKit 的，原地補齊、刪掉多的",
              "v2" in (shared_alpha / "scripts" / "run.py").read_text(encoding="utf-8")
              and (shared_alpha / MARKER).exists() and not (shared_alpha / "scripts" / "stale.py").exists())
        check("新增 skill：兩邊都接上", is_link(home / ".claude" / "skills" / "gamma")
              and (home / ".agents" / "skills" / "gamma" / MARKER).exists())
        shutil.rmtree(src / "gamma")
        sync(env, mcp=False)
        check("刪掉 skill：兩邊都拿掉", not present(home / ".claude" / "skills" / "gamma")
              and not present(home / ".agents" / "skills" / "gamma"))

        # 訪談第 5 題答「不要」（answers.json 的 evaluate_tools 是 false）：不裝 omnikit-eval。
        # 訪談產生的 profile 存在 repo 外（state/profiles，FR-38）
        put(src / "omnikit-eval" / "SKILL.md", "---\nname: omnikit-eval\n---\n")
        put(state / "profiles" / "bob" / "AGENTS.md", "# bob\n")
        bob_answers = state / "profiles" / "bob" / "answers.json"
        put(bob_answers, json.dumps({"name": "bob", "evaluate_tools": False}))
        claude_eval, shared_eval = home / ".claude" / "skills" / "omnikit-eval", home / ".agents" / "skills" / "omnikit-eval"
        sync(env, mcp=False)
        check("還沒選 bob：omnikit-eval 兩邊都裝", is_link(claude_eval) and (shared_eval / MARKER).exists())
        lines = connect(env, profile="bob")
        rec = load_record(env)
        check("換成不評估工具的 profile：omnikit-eval 兩邊都拿掉，其他 skill 照裝",
              not present(claude_eval) and not present(shared_eval) and is_link(claude_alpha)
              and "omnikit-eval" not in rec["skills"]["claude-code"] + rec["skills"]["shared"]
              and any("不裝 omnikit-eval" in line for line in lines))
        sync(env, mcp=False)
        check("之後的同步（git hook）照選的 profile，不會裝回來", not present(claude_eval) and not present(shared_eval))
        put(shared_eval / "SKILL.md", "---\nname: omnikit-eval\n---\n使用者自己的\n")
        sync(env, mcp=False)
        check("同名但不是 OmniKit 的 omnikit-eval 不動", (shared_eval / "SKILL.md").exists())
        shutil.rmtree(shared_eval)
        put(bob_answers, "{壞掉")
        sync(env, mcp=False)
        check("answers.json 讀不懂：全部都裝", is_link(claude_eval) and (shared_eval / MARKER).exists())
        put(bob_answers, json.dumps({"name": "bob", "evaluate_tools": False}))
        connect(env, profile="default")
        check("換回手寫的 profile（沒有 answers.json）：omnikit-eval 裝回來",
              is_link(claude_eval) and (shared_eval / MARKER).exists())
        shutil.rmtree(src / "omnikit-eval")
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
        check("Codex 已經有同名但不是 OmniKit 的 server：停下來問，不寫入",
              "不是 OmniKit 加的" in msg and weird.read_text(encoding="utf-8").startswith("[mcp_servers]\n"))
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
        os.chmod(shared_alpha / "scripts", stat.S_IREAD | stat.S_IEXEC)  # 複製品裡有唯讀資料夾也要刪得掉
        lines = disconnect(env)
        check("移除：OmniKit 的 skills 都拿掉，engine/skills 與使用者的不動",
              not present(claude_alpha) and not present(shared_alpha) and (src / "alpha" / "SKILL.md").exists()
              and (home / ".agents" / "skills" / "mine").exists() and (home / ".agents" / "skills" / "beta").exists())
        check("移除：三邊的 MCP 拿掉，別人的不動",
              "devtools" not in read_servers(env, "claude-code") and "mine" in read_servers(env, "claude-code")
              and "devtools" not in read_servers(env, "codex") and "keep" in read_servers(env, "antigravity"))
        check("移除：Antigravity 區塊原地拿掉，硬連結還在",
              profiles.text(home / ".gemini" / "GEMINI.md") == "# 我的 Antigravity 規則\n"
              and os.path.samefile(home / ".gemini" / "GEMINI.md", home / ".dsh" / "AGENTS.md"))
        check("移除：Codex 只剩區塊，還原安裝前的備份",
              profiles.text(home / ".codex" / "AGENTS.md") == "# 我的 Codex 規則\n"
              and not (home / ".codex" / "AGENTS.md.pre-omnikit").exists())
        check("移除：刪掉 agents.json", not env.record_file.exists())

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

        # 使用者在 Codex 改了 OmniKit 管的 args：下次同步停下來問，什麼都不寫
        put(toml2, codex_text2.replace('"y.js"', '"mine.js"'))
        snap = {p: p.read_bytes() for p in (toml2, home2 / ".claude.json", gem2, home2 / ".codex" / "AGENTS.md")}
        put(servers_yaml, approve_yaml.replace("x.js", "z.js"))
        msg = exit_message(lambda: sync(env2))
        check("使用者在 Codex 改過 args：同步停下來，只列欄位名稱不列值，什麼都不寫",
              "OmniKit 寫入之後被改過" in msg and "args" in msg and "mine.js" not in msg and "--keep-mine" in msg
              and all(p.read_bytes() == b for p, b in snap.items()))
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
        check("使用者移除了 OmniKit 加的 server：停下來問，不加回去",
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
        check("舊版記錄（只有名稱）又跟 servers.yaml 不同：停下來問", "舊版的記錄沒有雜湊" in msg)
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

        # 第一次接上就遇到同名但不是 OmniKit 的：規則、skills、MCP 都先不寫
        home3, state3 = tmp / "home3", tmp / "state3"
        put(home3 / ".claude" / "CLAUDE.md", "# 我的\n")
        put(home3 / ".claude.json", json.dumps({"mcpServers": {"devtools": {"type": "stdio", "command": "mine"}}}))
        env3 = Env(home=home3, repo=repo, state=state3, skillshare=tmp / "none", which=lambda _: None)
        edition.set_edition(state3, "colleague")
        before3 = [(home3 / ".claude" / "CLAUDE.md").read_bytes(), (home3 / ".claude.json").read_bytes()]
        msg = exit_message(lambda: connect(env3, agents=["claude-code"]))
        check("第一次接上遇到同名但不是 OmniKit 的 server：停下來，規則、skills、MCP 都不寫",
              "不是 OmniKit 加的" in msg and not env3.record_file.exists() and not (home3 / ".claude" / "skills").exists()
              and [(home3 / ".claude" / "CLAUDE.md").read_bytes(), (home3 / ".claude.json").read_bytes()] == before3)
        connect(env3, agents=["claude-code"], ask=lambda c: "mine")
        check("問的時候選保留自己的：同名的不動，其他照常接上",
              read_servers(env3, "claude-code")["devtools"]["command"] == "mine"
              and profiles.BEGIN in profiles.text(home3 / ".claude" / "CLAUDE.md")
              and load_record(env3)["mcp_keep"]["claude-code"] == ["devtools"])
        for d in readonly:
            writable(d)

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
    if args.command == "connect":
        agents = args.agents.split(",") if args.agents else None
        if agents and (bad := [a for a in agents if a not in AGENTS]):
            parser.error(f"不認得的 agent：{'、'.join(bad)}")
        lines = connect(env, args.profile, agents, ask=ask_conflict if args.ask and interactive else None)
    elif args.command == "sync":
        both = not (args.skills or args.mcp)
        lines = sync(env, skills=args.skills or both, mcp=args.mcp or both,
                     ask=ask_conflict if args.ask and interactive else None)
    elif args.command == "resolve":
        lines = resolve_conflict(env, args.name, "omnikit" if args.use_omnikit else "mine", args.agent)
    elif args.command == "approvals":
        lines = approvals(env, ask=ask_approval if args.ask and interactive else None, grant=args.grant, revoke=args.revoke)
        if args.ask and not interactive and edition.resolve(env.state, env.repo)[0] != "maintainer":
            lines.append(f"沒辦法詢問（不能互動）：還沒問的免問核准先不寫入；要同意就執行 {claude_allow.GRANT}")
    elif args.command == "disconnect":
        lines = disconnect(env)
    elif args.command == "status":
        return status(env)
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
