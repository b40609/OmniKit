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
- skills：engine/skills 的每個 skill
  - Claude Code：~/.claude/skills/<名稱> 用資料夾連結，改完馬上生效；建不起來就改用複製
  - Codex 與 Antigravity 共用 ~/.agents/skills/<名稱>，用複製：Antigravity 不跟隨資料夾連結。
    複製品裡放 .omnikit.json，記來源、repo 位置與內容雜湊；內容變了才重新複製
- MCP：data/mcp/servers.yaml 的 server
  - Claude Code：claude mcp add-json -s user（找不到 claude 指令才直接改 ~/.claude.json）
  - Codex：~/.codex/config.toml 的 [mcp_servers.<名稱>]；寫入前用 tomllib 比對，除了這些 server 什麼都沒變才寫
  - Antigravity：~/.gemini/config/mcp_config.json，不寫 BOM（Antigravity 讀到 BOM 會整份失敗）

接上了哪些 agent、管了哪些 skills 與 MCP server，記在 %LOCALAPPDATA%\\omnikit\\agents.json；
同步只動記錄裡的 agent，移除時只拿掉 OmniKit 的東西，同名但不是 OmniKit 的不碰。

用法：
  uv run engine/scripts/agents.py connect [--profile <名稱>] [--agents claude-code,codex,antigravity]
  uv run engine/scripts/agents.py sync [--skills] [--mcp]
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
import codex_hooks  # noqa: E402  讀寫 config.toml 時保留原本的換行
import profiles  # noqa: E402
import validate  # noqa: E402

AGENTS = ("claude-code", "codex", "antigravity")
SHORT = {"claude-code": "claude", "codex": "codex", "antigravity": "antigravity"}
NAMES = profiles.NAMES
MARKER = ".omnikit.json"
IGNORE = ("__pycache__", MARKER, "*.pyc")
MCP_MARK = "# OmniKit：MCP server（agents.py 依 data/mcp/servers.yaml 寫入）"
TABLE = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:"((?:[^"\\]|\\.)*)"|([A-Za-z0-9_-]+))\s*(?:\..*)?\]\s*(?:#.*)?$')
HEADER_LINE = re.compile(r"^\s*\[")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


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


def load_record(env):
    try:
        rec = json.loads(env.record_file.read_text(encoding="utf-8"))
        rec = rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        rec = {}
    for key, empty in (("agents", []), ("skills", {}), ("mcp", {})):
        rec.setdefault(key, empty)
    return rec


def save_record(env, rec):
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


def sync_skills(env, agents, rec):
    names = skill_names(env.skills_src)
    lines = []
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
                lines.append(f"skills：拿掉已經刪除的 {name}（{folder}）")
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


def desired(spec, agent):
    cfg = {"command": spec["command"], "args": list(spec.get("args", []))}
    if spec.get("env"):
        cfg["env"] = dict(spec["env"])
    if agent == "claude-code":
        cfg = {"type": "stdio", **cfg}
    cfg.update((spec.get("options") or {}).get(SHORT[agent], {}))
    return cfg


def same(current, cfg):
    """只比 OmniKit 設的欄位：使用者在 agent 裡另外加的（例如停用）不算不同。"""
    if not isinstance(current, dict):
        return False

    def norm(v):
        return None if v in ({}, [], None, "") else v

    return all(norm(current.get(k)) == norm(cfg.get(k)) for k in set(cfg) | {"command", "args", "env"})


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


def claude_apply(env, wanted, remove):
    current = read_servers(env, "claude-code")
    change = [n for n, cfg in wanted.items() if not same(current.get(n), cfg)] + [n for n in remove if n in current]
    for name in change:
        if env.claude_cli:
            if name in current:
                run_cli([*env.claude_cli, "mcp", "remove", "-s", "user", name])
            if name in wanted:
                run_cli([*env.claude_cli, "mcp", "add-json", "-s", "user", name, json.dumps(wanted[name], ensure_ascii=False)])
        else:
            doc = read_json(env.claude_json)
            servers = doc.setdefault("mcpServers", {})
            if name in wanted:
                servers[name] = wanted[name]
            else:
                servers.pop(name, None)
            profiles.write(env.claude_json, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return sorted(change)


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


def codex_apply(env, wanted, remove):
    path = env.codex_toml
    text, newline = codex_hooks.read(path)
    try:
        old = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path} 不是合法的 TOML（{e}），沒有改")
    current = old.get("mcp_servers", {})
    change = {n for n, cfg in wanted.items() if not same(current.get(n), cfg)} | {n for n in remove if n in current}
    if not change:
        return []
    kept = strip_tables(text, change).rstrip("\n")
    new_text = kept + "\n" if kept.strip() else ""
    for name in sorted(change & wanted.keys()):
        new_text += ("\n" if new_text else "") + codex_table(name, wanted[name])
    expect = copy.deepcopy(old)
    servers = expect.setdefault("mcp_servers", {})
    for name in change:
        servers.pop(name, None)
    for name in change & wanted.keys():
        servers[name] = wanted[name]
    if not servers:
        expect.pop("mcp_servers")
    try:
        new = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError:
        new = None
    if new != expect:
        raise SystemExit(f"改 {path} 的 MCP 設定時，結果跟預期不同（可能用了 OmniKit 不認得的寫法），沒有寫入；"
                         f"請手動檢查 mcp_servers 的 {'、'.join(sorted(change))}")
    path.parent.mkdir(parents=True, exist_ok=True)
    codex_hooks.write(path, new_text, newline)
    return sorted(change)


def gemini_apply(env, wanted, remove):
    path = env.gemini_mcp
    doc = read_json(path)
    had_bom = path.exists() and path.read_bytes().startswith(b"\xef\xbb\xbf")
    servers = doc.setdefault("mcpServers", {})
    change = []
    for name, cfg in wanted.items():
        if not same(servers.get(name), cfg):
            servers[name] = cfg
            change.append(name)
    for name in remove:
        if name in servers:
            del servers[name]
            change.append(name)
    if change or had_bom:
        profiles.write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return sorted(change)


WRITERS = {"claude-code": claude_apply, "codex": codex_apply, "antigravity": gemini_apply}


def sync_mcp(env, agents, rec):
    servers = load_servers(env)
    lines = []
    for agent in agents:
        wanted = {n: desired(s, agent) for n, s in servers.items() if SHORT[agent] in s["targets"]}
        remove = set(rec["mcp"].get(agent, [])) - set(wanted)
        changed = WRITERS[agent](env, wanted, remove)
        rec["mcp"][agent] = sorted(wanted)
        state = f"（更新：{'、'.join(changed)}）" if changed else "（已是最新）"
        lines.append(f"MCP：{NAMES[agent]} {'、'.join(sorted(wanted)) or '（沒有）'}{state}")
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

def connect(env, profile=None, agents=None):
    agents = agents or detect(env)
    if not agents:
        raise SystemExit("找不到 Claude Code、Codex 或 Antigravity，沒有可以接上的 agent")
    rec = load_record(env)
    rec["agents"] = list(agents)
    lines = profiles.apply(env.data, env.state, env.rules, wanted=profile, agents=agents, take_over=True,
                           skillshare_config=env.skillshare / "config.yaml")
    lines += sync_skills(env, agents, rec)
    lines += sync_mcp(env, agents, rec)
    save_record(env, rec)
    lines += release_skillshare(env)
    return lines


def sync(env, skills=True, mcp=True):
    rec = load_record(env)
    if not rec["agents"]:
        return ["這台還沒用新的方式接上 agent（沒有 agents.json），skills 與 MCP 沒有同步：重跑 install.ps1"]
    lines = []
    if skills:
        lines += sync_skills(env, rec["agents"], rec)
    if mcp:
        lines += sync_mcp(env, rec["agents"], rec)
    save_record(env, rec)
    return lines


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
    for agent in agents:
        recorded = rec["mcp"].get(agent)
        if recorded is None:
            # 舊版沒有記錄：只拿掉設定跟 servers.yaml 一模一樣的，同名但不同的可能是使用者自己的
            current = read_servers(env, agent)
            recorded = [n for n, s in servers.items()
                        if SHORT[agent] in s["targets"] and same(current.get(n), desired(s, agent))]
        changed = WRITERS[agent](env, {}, set(recorded))
        if changed:
            lines.append(f"MCP：從 {NAMES[agent]} 拿掉 {'、'.join(changed)}")
    lines += profiles.disconnect_gemini(env.rules["antigravity"])
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

        check("規則：舊版 skillshare 管的 Codex 規則直接接手，安裝前的備份不動",
              profiles.is_ours(profiles.text(home / ".codex" / "AGENTS.md"))
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
        check("記錄接上的 agent、skills 與 MCP", rec["agents"] == list(AGENTS)
              and rec["skills"]["shared"] == ["alpha"] and rec["mcp"]["codex"] == ["devtools"])

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
        check("Codex 用了 OmniKit 不認得的寫法：失敗，不寫入",
              fails(lambda: sync(env, skills=False)) and weird.read_text(encoding="utf-8").startswith("[mcp_servers]\n"))
        put(weird, codex_original)

        put(servers_yaml, "servers:\n  devtools:\n    command: cmd\n    targets: [claude, codex, antigravity]\n")
        sync(env, skills=False)
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
        claude_apply(cli_env, {"devtools": {"type": "stdio", "command": "cmd"}}, set())
        check("有 claude 指令：用 claude mcp add-json 寫入", read_servers(env, "claude-code")["devtools"]["command"] == "cmd")
        claude_apply(cli_env, {}, {"devtools"})
        check("有 claude 指令：用 claude mcp remove 移除", "devtools" not in read_servers(env, "claude-code"))
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
    s = sub.add_parser("sync", help="依記錄同步 skills 與 MCP（git hook 用）")
    s.add_argument("--skills", action="store_true", help="只同步 skills")
    s.add_argument("--mcp", action="store_true", help="只同步 MCP")
    sub.add_parser("disconnect", help="拿掉 OmniKit 的 skills、MCP 與 Antigravity 規則（uninstall.ps1 用）")
    sub.add_parser("status", help="印出偵測到的 agent 與記錄")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    env = real_env()
    if args.command == "connect":
        agents = args.agents.split(",") if args.agents else None
        if agents and (bad := [a for a in agents if a not in AGENTS]):
            parser.error(f"不認得的 agent：{'、'.join(bad)}")
        lines = connect(env, args.profile, agents)
    elif args.command == "sync":
        both = not (args.skills or args.mcp)
        lines = sync(env, skills=args.skills or both, mcp=args.mcp or both)
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
