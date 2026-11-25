# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 無帳本同步器（Fable 5.2 修訂版 Option 6，取代舊 agents.py 與 .omnikit.json 雜湊帳本）。

核心設計與 S1–S6 實測定案：
1. 無狀態對帳：期望狀態完全由 repo manifest（data/rules、engine/skills、data/mcp/servers.yaml、
   data/harness/claude-allow*.txt）計算，不維護檔案雜湊帳本（agents.json / .omnikit.json）。
2. 零遞迴刪除：程式嚴禁呼叫遞迴刪除函式；移除 Directory Junction 一律使用 os.rmdir，移除薄宣告檔逐一 unlink 後 rmdir。
3. ~/.omnikit/current 乾淨本地 clone（S4 防穿透保護）：預設將當前 repo HEAD 同步至 ~/.omnikit/current，
   所有連結與路徑指向該乾淨副本（--dev 改指開發 repo，--no-dev 切回乾淨副本）。
4. 規則：交由 profiles.py（Claude @import 附帶內金絲雀行並依 dev_link 選來源；Codex 受管區塊 <= 32 KiB；
   Antigravity 拆 ~/.gemini/AGENTS.md 共用與 GEMINI.md 個人，單檔 <= 24,000 bytes，絕不碰 T3 實例副本）。
5. Skills（擁有權依 omnikit-* 與 ok / ok-* 前綴）：
   - Claude Code（~/.claude 與明確列舉的 claude_homes）：Directory Junction，並無帳本鏡像 ~/.claude 使用者自裝 skill
   - Codex（~/.codex/skills 與明確列舉的 codex_homes/skills，S2 實測確認）：Directory Junction
   - Antigravity：於 ~/.gemini/config/skills.json 參照 POSIX 路徑 "/C:/..."（S3 實測確認，T3 自動同步至全實例）
6. Hooks 與 MCP：
   - Claude Code：本地 marketplace 薄 plugin（omnikit@omnikit-local，版本號帶內容雜湊）非互動安裝至各設定目錄，
     並鏡像同步 ~/.claude 啟用中的第三方 plugin；逐目錄搭配 claude_allow.py 寫入現行＋墓碑權限與 statusLine。
   - Codex：codex mcp add / remove CLI＋安全編輯 default_tools_approval_mode（經 tomllib 驗證）＋ codex_hooks.py。
   - Antigravity：於 ~/.gemini 與每個 T3 實例放置 config/plugins/omnikit/ 三檔薄宣告（指令加 call 前綴），
     不碰 config/hooks.json 與頂層 mcp_config.json。

用法：
  uv run engine/scripts/sync.py connect [--profile <名稱>] [--agents claude-code,codex,antigravity] [--dev|--no-dev]
  uv run engine/scripts/sync.py sync [--skills] [--mcp] [--plugins] [--check] [--dev|--no-dev]
  uv run engine/scripts/sync.py approvals [--ask] [--grant <名稱>] [--revoke <名稱>]
  uv run engine/scripts/sync.py disconnect
  uv run engine/scripts/sync.py status
  uv run engine/scripts/sync.py --selftest
"""
from __future__ import annotations

import argparse
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
import claude_allow
import codex_hooks
import edition
import homes
import profiles
import statedir
import t3_acp
from fsretry import retry

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ("claude-code", "codex", "antigravity")
SHORT = {"claude-code": "claude", "codex": "codex", "antigravity": "antigravity"}
PLUGIN_BASE_VERSION = "0.2.0"
MARKETPLACE_NAME = "omnikit-local"
PLUGIN_ID = f"omnikit@{MARKETPLACE_NAME}"
LEGACY_MARKER = ".omnikit.json"
AGY_PLUGIN_FILES = ("plugin.json", "hooks.json", "mcp_config.json")
USER_SKILL_SKIP = re.compile(r"^\.|\.bak(?:[-_.]|$)|\.orig$|~$", re.IGNORECASE)
CODEX_MCP_BEGIN = "# --- omnikit:mcp:begin ---"
CODEX_MCP_END = "# --- omnikit:mcp:end ---"
CODEX_MCP_BLOCK = re.compile(re.escape(CODEX_MCP_BEGIN) + r".*?" + re.escape(CODEX_MCP_END) + r"\n?", re.DOTALL)


def is_omnikit_skill(name: str) -> bool:
    return name == "ok" or name.startswith(("omnikit-", "ok-"))


def is_link(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def link_target(path: Path) -> Path | None:
    try:
        raw = os.readlink(path)
    except OSError:
        return None
    clean = raw.removeprefix("\\\\?\\")
    p = Path(clean)
    return p if p.is_absolute() else (path.parent / p).resolve()


def same_path(a: Path | None, b: Path | None) -> bool:
    if a is None or b is None:
        return False
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def is_inside_dir(path: Path, folder: Path) -> bool:
    try:
        a = os.path.normcase(str(path.resolve()))
        b = os.path.normcase(str(folder.resolve())).rstrip("\\/")
    except OSError:
        a = os.path.normcase(str(path))
        b = os.path.normcase(str(folder)).rstrip("\\/")
    return a == b or a.startswith(b + os.sep)


def make_dir_link(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(src.resolve()), str(dest))
    else:
        os.symlink(str(src.resolve()), str(dest), target_is_directory=True)


def remove_dir_link(path: Path) -> None:
    """移除目錄連結（Windows Junction 或 POSIX symlink），永不遞迴進目標。"""
    if os.name == "nt":
        retry(os.rmdir, path)
    else:
        retry(os.unlink, path)


def _tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_file() and not any(part in ("__pycache__", LEGACY_MARKER) for part in rel.parts) and p.suffix != ".pyc":
            h.update(rel.as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def remove_legacy_skill_copy(dest: Path, ref_src: Path | None) -> bool:
    """安全清理舊版帶有 .omnikit.json 標記檔的實體 skill 複製品（驗證未經手改、逐一刪除已知檔案後 rmdir，零遞迴刪除）。"""
    marker = dest / LEGACY_MARKER
    if is_link(dest) or not dest.is_dir() or not marker.is_file():
        return False
    try:
        mdoc = json.loads(marker.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    recorded_hash = mdoc.get("hash") if isinstance(mdoc, dict) else None
    if (
        isinstance(recorded_hash, str)
        and recorded_hash
        and _tree_hash(dest) != recorded_hash
        and not (ref_src and ref_src.is_dir() and _tree_hash(dest) == _tree_hash(ref_src))
    ):
        return False  # 使用者手改過複製品內容：保留不動
    allowed_rels = {Path(LEGACY_MARKER)}
    if ref_src and ref_src.is_dir():
        allowed_rels.update(p.relative_to(ref_src) for p in ref_src.rglob("*") if p.is_file())
    files = [p for p in dest.rglob("*") if not p.is_dir()]
    for f in files:
        rel = f.relative_to(dest)
        if not recorded_hash and rel not in allowed_rels and f.suffix != ".pyc" and "__pycache__" not in rel.parts:
            return False
    for f in files:
        os.chmod(f, stat.S_IWRITE)
        retry(f.unlink)
    dirs = sorted([d for d in dest.rglob("*") if d.is_dir()], key=lambda p: len(p.parts), reverse=True)
    for d in [*dirs, dest]:
        os.chmod(d, stat.S_IWRITE)
        retry(os.rmdir, d)
    return True


def atomic_write_json(path: Path, doc: dict) -> bool:
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists() and retry(path.read_bytes) == raw:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".omnikit-tmp")
    try:
        retry(tmp.write_bytes, raw)
        retry(os.replace, tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return True


def read_json_nobom(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def parse_json_output(text: str):
    for i, ch in enumerate(text or ""):
        if ch in "[{":
            try:
                return json.loads(text[i:])
            except ValueError:
                return None
    return None


def load_config(state: Path) -> dict:
    for fname in ("config.json", "agents.json"):
        p = state / fname
        if p.is_file():
            try:
                doc = read_json_nobom(p)
                if isinstance(doc, dict):
                    return doc
            except ValueError:
                pass
    return {}


def save_config(state: Path, cfg: dict) -> None:
    kept = {k: cfg[k] for k in ("agents", "claude_homes", "codex_homes", "dev_link", "repo") if k in cfg}
    atomic_write_json(state / "config.json", kept)
    legacy = state / "agents.json"
    if legacy.exists():
        retry(legacy.unlink)


def resolve_real_repo(candidate: Path, state: Path) -> Path:
    """當腳本是從 ~/.omnikit/current 被 hook 觸發時，自動從 config.json 轉回真實開發 repo，絕不把 current 當成來源 repo。"""
    cur = state / "current"
    if is_inside_dir(candidate, cur):
        raw = load_config(state).get("repo")
        if isinstance(raw, str) and raw.strip():
            real_p = Path(raw)
            if not is_inside_dir(real_p, cur) and (real_p / "data" / "rules" / "baseline.md").is_file():
                return real_p
    return candidate


@dataclass
class Env:
    home: Path
    repo: Path
    state: Path
    which: object = shutil.which
    runner: object = None  # (cmd, environ) -> (rc, stdout, stderr)
    environ: dict | None = None

    @property
    def config_file(self) -> Path:
        return self.state / "config.json"

    def target_root(self, dev: bool | None = None) -> Path:
        cfg = load_config(self.state)
        use_dev = bool(cfg.get("dev_link")) if dev is None else dev
        cur = self.state / "current"
        if not use_dev and (cur / "data" / "rules" / "baseline.md").is_file():
            return cur
        return resolve_real_repo(self.repo, self.state)


def real_env() -> Env:
    st = statedir.STATE
    return Env(home=Path.home(), repo=resolve_real_repo(ROOT, st), state=st)


def detect_agents(env: Env) -> list[str]:
    found = []
    if (env.home / ".claude").is_dir() or env.which("claude"):
        found.append("claude-code")
    if (env.home / ".codex").is_dir() or env.which("codex"):
        found.append("codex")
    has_t3_agy = any(isinstance(i, dict) and i.get("driver") == "antigravity" for i in homes.t3_instances(env.home).values())
    if (env.home / ".gemini" / "config").is_dir() or (env.home / ".gemini" / "antigravity").is_dir() or env.which("agy") or has_t3_agy:
        found.append("antigravity")
    return found


def active_agents(env: Env, override: list[str] | None = None) -> list[str]:
    if override is not None:
        return [a for a in override if a in AGENTS]
    cfg = load_config(env.state)
    if isinstance(cfg.get("agents"), list) and cfg["agents"]:
        return [a for a in cfg["agents"] if a in AGENTS]
    return detect_agents(env)


def ensure_current_clone(repo: Path, state: Path, dev: bool = False, check_only: bool = False) -> tuple[Path, list[str]]:
    """將 repo 的已 commit HEAD 同步至 ~/.omnikit/current，隔離保護工作區免受 Git Bash rm -rf <junc>/ 穿透刪除。"""
    real_repo = resolve_real_repo(repo, state)
    cur = state / "current"
    if check_only:
        if dev:
            return real_repo, []
        return (cur if (cur / "data" / "rules" / "baseline.md").is_file() else real_repo), []
    if not (real_repo / ".git").exists() or not shutil.which("git"):
        return real_repo, []
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if dev:
        # dev 模式仍順手更新已存在的 current（維持兩邊 HEAD 不脫節），但回傳 real_repo
        if (cur / ".git").is_dir() and not same_path(real_repo, cur):
            r1 = subprocess.run(["git", "-C", str(cur), "fetch", "--quiet", str(real_repo), "HEAD"],
                                env=git_env, capture_output=True, timeout=30, check=False)
            if r1.returncode == 0:
                subprocess.run(["git", "-C", str(cur), "-c", "core.longpaths=true", "reset", "--hard", "--quiet", "FETCH_HEAD"],
                               env=git_env, capture_output=True, timeout=30, check=False)
        return real_repo, []
    if same_path(real_repo, cur):
        return cur, []
    state.mkdir(parents=True, exist_ok=True)
    if not (cur / ".git").is_dir():
        if cur.exists():
            return real_repo, [f"警告：{cur} 已存在但非 git 倉庫（S4 保護未啟用），暫時直接參照 {real_repo}"]
        r = subprocess.run(
            ["git", "-c", "core.longpaths=true", "clone", "--quiet", "--no-hardlinks", str(real_repo), str(cur)],
            env=git_env, capture_output=True, text=True, timeout=60, check=False,
        )
        if r.returncode != 0:
            return real_repo, [f"警告：建立 {cur} 失敗（{(r.stderr or '').strip()[:120]}），暫時直接參照 {real_repo}"]
        return cur, [f"已建立乾淨參照副本：{cur}"]
    r1 = subprocess.run(["git", "-C", str(cur), "fetch", "--quiet", str(real_repo), "HEAD"], env=git_env, capture_output=True, timeout=30, check=False)
    r2 = subprocess.run(["git", "-C", str(cur), "-c", "core.longpaths=true", "reset", "--hard", "--quiet", "FETCH_HEAD"],
                        env=git_env, capture_output=True, timeout=30, check=False) if r1.returncode == 0 else r1
    return (cur, []) if r2.returncode == 0 else (real_repo, [f"警告：更新 {cur} 失敗，暫時直接參照 {real_repo}"])


def load_mcp_manifest_full(root: Path) -> tuple[dict[str, dict], set[str]]:
    path = root / "data" / "mcp" / "servers.yaml"
    if not path.is_file():
        return {}, set()
    doc = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    servers = doc.get("servers") or {}
    retired = {str(x) for x in (doc.get("retired") or []) if x}
    for name, spec in servers.items():
        env_map = spec.get("env")
        if isinstance(env_map, dict) and any(str(v).strip() for v in env_map.values() if v is not None):
            raise SystemExit(f"MCP server「{name}」在 servers.yaml 寫了 env 值（違反無密鑰規範，請改由 server 自行讀環境變數）")
    return servers, retired


def load_mcp_manifest(root: Path) -> dict[str, dict]:
    servers, _ = load_mcp_manifest_full(root)
    return servers


def expected_skills(root: Path, data: Path, state: Path) -> tuple[list[str], set[str]]:
    name, _ = profiles.resolve(data, state)
    skipped = set(profiles.skipped_skills(data, state, name))
    src = root / "engine" / "skills"
    if not src.is_dir():
        return [], skipped
    wanted = sorted(d.name for d in src.iterdir() if d.is_dir() and (d / "SKILL.md").is_file() and d.name not in skipped)
    return wanted, skipped


def sync_dir_junctions(skills_dir: Path, src_root: Path, wanted: list[str], check_only: bool = False) -> list[str]:
    """在 Claude 或 Codex 的 skills 目錄對帳 omnikit-* / ok-* Directory Junctions。"""
    diffs = []
    wanted_set = set(wanted)
    if skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            nm = item.name
            if not is_omnikit_skill(nm) and not (item.is_dir() and not is_link(item) and (item / LEGACY_MARKER).is_file()):
                continue
            if nm not in wanted_set:
                diffs.append(f"移除多餘 skill：{item}")
                if not check_only:
                    if is_link(item):
                        remove_dir_link(item)
                    elif not remove_legacy_skill_copy(item, src_root / nm):
                        diffs.append(f"保留含手改內容的舊複製品：{item}")
    for nm in wanted:
        src = src_root / nm
        dest = skills_dir / nm
        if is_link(dest) and same_path(link_target(dest), src):
            continue
        diffs.append(f"連結 skill：{dest} -> {src}")
        if not check_only:
            if is_link(dest):
                remove_dir_link(dest)
            elif dest.exists() and not remove_legacy_skill_copy(dest, src):
                diffs.append(f"略過非 OmniKit 或已手改的實體目錄：{dest}")
                continue
            make_dir_link(src, dest)
    return diffs


def discover_user_claude_skills(home: Path, repo: Path, state: Path) -> dict[str, Path]:
    """掃描 ~/.claude/skills 內使用者自己裝的第三方 skill（排除 OmniKit skill、備份檔與無 SKILL.md 的系統目錄）。"""
    src_dir = home / ".claude" / "skills"
    if not src_dir.is_dir():
        return {}
    our_roots = [repo / "engine" / "skills", state / "current" / "engine" / "skills"]
    found: dict[str, Path] = {}
    for p in sorted(src_dir.iterdir(), key=lambda x: x.name):
        if USER_SKILL_SKIP.search(p.name) or is_omnikit_skill(p.name):
            continue
        if not (p / "SKILL.md").is_file() or (not is_link(p) and (p / LEGACY_MARKER).is_file()):
            continue
        try:
            real_target = Path(os.path.realpath(p))
        except OSError:
            continue
        if any(is_inside_dir(real_target, r) for r in our_roots):
            continue
        found[p.name] = real_target
    return found


def sync_user_claude_skills(home: Path, claude_dirs: list[Path], repo: Path, state: Path, check_only: bool = False) -> list[str]:
    """無帳本鏡像 ~/.claude/skills 的使用者自裝 skill 至其他 Claude 設定目錄（如 .claude-kai、.claude-retis）。"""
    extras = [d for d in claude_dirs[1:] if not same_path(d, home / ".claude")]
    if not extras:
        return []
    wanted = discover_user_claude_skills(home, repo, state)
    primary_skills = home / ".claude" / "skills"
    diffs = []
    for cdir in extras:
        sdir = cdir / "skills"
        if sdir.is_dir():
            for item in sorted(sdir.iterdir(), key=lambda x: x.name):
                if is_omnikit_skill(item.name) or item.name in wanted or not is_link(item):
                    continue
                tgt = link_target(item)
                # 目標已刪除（dangling junction）或曾連向 ~/.claude/skills 但來源已移除：安全移除連結
                if tgt is not None and (not tgt.exists() or is_inside_dir(tgt, primary_skills)):
                    diffs.append(f"移除已下架鏡像 skill 連結：{item}")
                    if not check_only:
                        remove_dir_link(item)
        for name, real_src in wanted.items():
            dest = sdir / name
            if dest.exists() or is_link(dest):
                try:
                    if same_path(Path(os.path.realpath(dest)), real_src):
                        continue
                except OSError:
                    pass
                if not is_link(dest):
                    continue  # 該帳號自己獨立放的實體同名 skill：不動
                tgt = link_target(dest)
                if tgt is not None and tgt.exists() and not is_inside_dir(tgt, primary_skills):
                    continue  # 該帳號自己連去別處的有效連結：不動
                diffs.append(f"更新鏡像 skill 連結：{dest} -> {real_src}")
                if not check_only:
                    remove_dir_link(dest)
                    make_dir_link(real_src, dest)
            else:
                diffs.append(f"鏡像 ~/.claude 使用者 skill：{dest} -> {real_src}")
                if not check_only:
                    make_dir_link(real_src, dest)
    return diffs


def unmirror_user_claude_skills(home: Path, claude_dirs: list[Path], repo: Path, state: Path) -> list[str]:
    extras = [d for d in claude_dirs[1:] if not same_path(d, home / ".claude")]
    if not extras:
        return []
    wanted = discover_user_claude_skills(home, repo, state)
    primary_skills = home / ".claude" / "skills"
    lines = []
    for cdir in extras:
        sdir = cdir / "skills"
        if not sdir.is_dir():
            continue
        removed = []
        for item in sorted(sdir.iterdir(), key=lambda x: x.name):
            if is_omnikit_skill(item.name) or not is_link(item):
                continue
            tgt = link_target(item)
            same_as_user = False
            if item.name in wanted:
                try:
                    same_as_user = same_path(Path(os.path.realpath(item)), wanted[item.name])
                except OSError:
                    same_as_user = True
            if same_as_user or (tgt is not None and (not tgt.exists() or is_inside_dir(tgt, primary_skills))):
                remove_dir_link(item)
                removed.append(item.name)
        if removed:
            lines.append(f"已從 {sdir} 移除鏡像自 ~/.claude 的 skill 連結：{'、'.join(removed)}")
    return lines


def agy_posix_skills_path(src_root: Path) -> str:
    p = src_root.resolve().as_posix()
    return p if p.startswith("/") else "/" + p


def _is_our_agy_skills_entry(entry_path: str, env: Env) -> bool:
    candidates = {
        agy_posix_skills_path(env.repo / "engine" / "skills").lower(),
        agy_posix_skills_path(env.state / "current" / "engine" / "skills").lower(),
    }
    raw_cfg_repo = load_config(env.state).get("repo")
    if isinstance(raw_cfg_repo, str) and raw_cfg_repo.strip():
        candidates.add(agy_posix_skills_path(Path(raw_cfg_repo) / "engine" / "skills").lower())
    norm = entry_path.replace("\\", "/").lower()
    return norm in candidates or norm.endswith("/.omnikit/current/engine/skills")


def sync_antigravity_skills(env: Env, src_root: Path, skipped: set[str], check_only: bool = False) -> list[str]:
    """透過 ~/.gemini/config/skills.json 原生參照實體 skills 目錄（T3 自動同步至全部實例），並清理舊版複製品。"""
    diffs = []
    sj = env.home / ".gemini" / "config" / "skills.json"
    want_path = agy_posix_skills_path(src_root)
    want_entry = {"path": want_path, **({"exclude": sorted(skipped)} if skipped else {})}
    doc = read_json_nobom(sj) if sj.is_file() else {}
    entries = list(doc.get("entries") or []) if isinstance(doc.get("entries"), list) else []
    kept = [e for e in entries if not (isinstance(e, dict) and _is_our_agy_skills_entry(str(e.get("path", "")), env))]
    new_doc = {**doc, "entries": [*kept, want_entry]}
    if new_doc != doc or not sj.is_file():
        diffs.append(f"更新 Antigravity skills.json：{want_path}")
        if not check_only:
            atomic_write_json(sj, new_doc)
    legacy_dir = env.home / ".gemini" / "config" / "skills"
    if legacy_dir.is_dir():
        for item in sorted(legacy_dir.iterdir()):
            if is_link(item) and is_omnikit_skill(item.name):
                diffs.append(f"清理舊連結：{item}")
                if not check_only:
                    remove_dir_link(item)
            elif item.is_dir() and (item / LEGACY_MARKER).is_file():
                diffs.append(f"清理舊版 Antigravity skill 複製品：{item}")
                if not check_only:
                    remove_legacy_skill_copy(item, src_root / item.name)
    return diffs


def claude_cli_env(home: Path, cdir: Path) -> dict[str, str | None]:
    """~/.claude 必須徹底移除環境變數 CLAUDE_CONFIG_DIR（設空字串會被 Claude CLI 當成空目錄）；其他目錄明確指過去。"""
    return {"CLAUDE_CONFIG_DIR": None if same_path(cdir, home / ".claude") else str(cdir)}


def _run_cli(env: Env, cmd: list[str], extra_env: dict[str, str | None] | None = None, timeout: int = 120) -> tuple[int, str, str]:
    merged_env = dict(env.environ if env.environ is not None else os.environ)
    for k, v in (extra_env or {}).items():
        if v is None:
            merged_env.pop(k, None)
        else:
            merged_env[k] = v
    if env.runner is not None:
        return env.runner(cmd, merged_env)
    r = subprocess.run(cmd, env=merged_env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def claude_plugin_payloads(target_root: Path, servers: dict[str, dict]) -> tuple[str, dict, dict]:
    """回傳（帶內容雜湊的 SemVer 版本號, hooks 物件, mcpServers 物件），確保指令或路徑變動時更新 Claude 快取。"""
    scripts_root = target_root / "engine" / "scripts"
    hooks_obj: dict[str, list] = {}
    for event, script, timeout in claude_allow.HOOKS:
        cmd = claude_allow.hook_command(script, scripts_root=scripts_root)
        group: dict = {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}
        if claude_allow.MATCHERS.get((event, script)):
            group = {"matcher": claude_allow.MATCHERS[(event, script)], **group}
        hooks_obj.setdefault(event, []).append(group)
    mcp_servers = {
        name: {"type": "stdio", "command": s["command"], "args": list(s.get("args") or []),
               **({"env": dict(s["env"])} if s.get("env") else {})}
        for name, s in servers.items() if "claude" in (s.get("targets") or [])
    }
    raw_sig = json.dumps({"hooks": hooks_obj, "mcp": mcp_servers}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ver = f"{PLUGIN_BASE_VERSION}-{hashlib.sha256(raw_sig).hexdigest()[:8]}"
    return ver, hooks_obj, mcp_servers


def build_claude_marketplace(state: Path, target_root: Path, servers: dict[str, dict]) -> tuple[Path, str]:
    """在 ~/.omnikit/claude-marketplace 寫入薄 plugin（只含 hooks 與 MCP，不含 skills）。"""
    mp = state / "claude-marketplace"
    plug = mp / "plugins" / "omnikit"
    ver, hooks_obj, mcp_servers = claude_plugin_payloads(target_root, servers)
    atomic_write_json(mp / ".claude-plugin" / "marketplace.json", {
        "name": MARKETPLACE_NAME,
        "description": "OmniKit local thin plugin marketplace (hooks and MCP)",
        "owner": {"name": "OmniKit"},
        "plugins": [{"name": "omnikit", "source": "./plugins/omnikit",
                     "description": "OmniKit deterministic hooks and MCP bundle", "version": ver}],
    })
    atomic_write_json(plug / ".claude-plugin" / "plugin.json", {
        "name": "omnikit",
        "version": ver,
        "description": "OmniKit deterministic hooks and MCP bundle",
        "author": {"name": "OmniKit"},
    })
    atomic_write_json(plug / "hooks" / "hooks.json", {"hooks": hooks_obj})
    atomic_write_json(plug / ".mcp.json", {"mcpServers": mcp_servers})
    return mp, ver


def find_claude_plugin_entry(env: Env, exe: str, cenv: dict[str, str | None]) -> dict | None:
    rc, out, _ = _run_cli(env, [exe, "plugin", "list", "--json"], cenv)
    if rc != 0:
        return None
    items = parse_json_output(out)
    if not isinstance(items, list):
        return None
    return next((i for i in items if isinstance(i, dict) and i.get("id") == PLUGIN_ID), None)


def _claude_marketplace_args(source: dict) -> list[str] | None:
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


def sync_user_claude_plugins(env: Env, claude_dirs: list[Path], check_only: bool = False) -> list[str]:
    """將 ~/.claude 啟用中的第三方 plugin（排除 omnikit@omnikit-local）鏡像補齊至其他 Claude 設定目錄。"""
    extras = [d for d in claude_dirs[1:] if not same_path(d, env.home / ".claude")]
    if not extras:
        return []
    primary = env.home / ".claude"
    try:
        sdoc = read_json_nobom(primary / "settings.json")
    except ValueError:
        sdoc = {}
    enabled_map = sdoc.get("enabledPlugins") or {}
    wanted = sorted(p for p, on in enabled_map.items() if on is True and isinstance(p, str) and "@" in p and p != PLUGIN_ID) if isinstance(enabled_map, dict) else []
    if not wanted:
        return []
    claude_exe = env.which("claude")
    if not claude_exe and env.runner is None:
        return [f"提示：找不到 claude 指令，略過鏡像 ~/.claude 的 {len(wanted)} 個第三方 plugin"]

    sources: dict[str, dict] = {}
    extra_m = sdoc.get("extraKnownMarketplaces") or {}
    try:
        known_m = read_json_nobom(primary / "plugins" / "known_marketplaces.json")
    except ValueError:
        known_m = {}
    for mdoc in (extra_m if isinstance(extra_m, dict) else {}, known_m if isinstance(known_m, dict) else {}):
        for mname, entry in mdoc.items():
            if isinstance(entry, dict) and isinstance(entry.get("source"), dict):
                sources[mname] = entry["source"]

    exe = claude_exe or "claude"
    diffs = []
    for cdir in extras:
        cenv = claude_cli_env(env.home, cdir)
        rc_l, out_l, _ = _run_cli(env, [exe, "plugin", "list", "--json"], cenv)
        items = parse_json_output(out_l) if rc_l == 0 else None
        if not isinstance(items, list):
            continue
        installed = {i["id"]: bool(i.get("enabled")) for i in items if isinstance(i, dict) and isinstance(i.get("id"), str)}
        missing = [pid for pid in wanted if pid not in installed]
        if not missing:
            continue
        rc_m, out_m, _ = _run_cli(env, [exe, "plugin", "marketplace", "list", "--json"], cenv)
        markets = {m.get("name") for m in (parse_json_output(out_m) or []) if isinstance(m, dict)} if rc_m == 0 else set()
        for pid in missing:
            diffs.append(f"鏡像 ~/.claude 第三方 plugin：{pid} -> {cdir}")
            if check_only:
                continue
            mkt = pid.rsplit("@", 1)[1]
            if mkt not in markets:
                m_args = _claude_marketplace_args(sources.get(mkt) or {})
                if m_args is None:
                    diffs.append(f"警告：{cdir} 找不到 marketplace {mkt} 來源，略過 {pid}")
                    continue
                rc_a, _, err_a = _run_cli(env, [exe, *m_args], cenv, timeout=300)
                if rc_a != 0:
                    diffs.append(f"警告：{cdir} 新增 marketplace {mkt} 失敗（{err_a[:140]}）")
                    continue
                markets.add(mkt)
            rc_i, _, err_i = _run_cli(env, [exe, "plugin", "install", pid, "--scope", "user"], cenv, timeout=300)
            if rc_i != 0:
                diffs.append(f"警告：{cdir} 安裝第三方 plugin {pid} 失敗（{err_i[:140]}）")
    return diffs


def sync_claude_plugin_and_settings(env: Env, claude_dirs: list[Path], target_root: Path,
                                    servers: dict[str, dict], check_only: bool = False) -> list[str]:
    diffs = []
    scripts_root = target_root / "engine" / "scripts"
    claude_exe = env.which("claude")
    if check_only:
        mp = env.state / "claude-marketplace"
        want_ver, _, _ = claude_plugin_payloads(target_root, servers)
    else:
        mp, want_ver = build_claude_marketplace(env.state, target_root, servers)
    plug_folder = mp / "plugins" / "omnikit"
    can_run_plugin = bool(claude_exe or env.runner is not None)
    plugin_ok_dirs: set[str] = set()

    for cdir in claude_dirs:
        cenv = claude_cli_env(env.home, cdir)
        norm_cdir = os.path.normcase(str(cdir.resolve()))
        dir_ok = False
        if can_run_plugin:
            exe = claude_exe or "claude"
            entry = find_claude_plugin_entry(env, exe, cenv)
            folder_match = entry is not None and same_path(Path(str(entry.get("readFromFolder") or "")), plug_folder)
            ver_match = entry is not None and entry.get("version") == want_ver
            if entry is not None and folder_match and ver_match and entry.get("enabled") is True:
                dir_ok = True
            else:
                diffs.append(f"安裝／更新 Claude 薄 plugin（{want_ver}）：{cdir}")
                if not check_only:
                    if entry is not None and folder_match and ver_match and entry.get("enabled") is not True:
                        rc_e, _, err_e = _run_cli(env, [exe, "plugin", "enable", PLUGIN_ID, "--scope", "user"], cenv)
                        dir_ok = rc_e == 0
                        if not dir_ok:
                            diffs.append(f"警告：{cdir} 啟用 {PLUGIN_ID} 失敗（{err_e[:140]}），該目錄退回 settings.json hooks 備案")
                    else:
                        # 先確保本地 marketplace 同步，若已安裝舊版先嘗試 update；若因雜湊字典序未切換版本則重裝刷新快取
                        _run_cli(env, [exe, "plugin", "marketplace", "add", str(mp), "--scope", "user"], cenv)
                        _run_cli(env, [exe, "plugin", "marketplace", "update", MARKETPLACE_NAME], cenv)
                        if entry is not None:
                            _run_cli(env, [exe, "plugin", "update", PLUGIN_ID, "-y", "--json"], cenv)
                            after_u = find_claude_plugin_entry(env, exe, cenv)
                            if after_u is not None and after_u.get("version") == want_ver:
                                if after_u.get("enabled") is not True:
                                    _run_cli(env, [exe, "plugin", "enable", PLUGIN_ID, "--scope", "user"], cenv)
                                dir_ok = True
                        if not dir_ok:
                            if entry is not None:
                                _run_cli(env, [exe, "plugin", "uninstall", PLUGIN_ID], cenv)
                            rc_i, _, err_i = _run_cli(env, [exe, "plugin", "install", "omnikit", "--marketplace", str(mp), "-y", "--json"], cenv)
                            if rc_i == 0:
                                after = find_claude_plugin_entry(env, exe, cenv)
                                if after is not None and after.get("enabled") is not True:
                                    _run_cli(env, [exe, "plugin", "enable", PLUGIN_ID, "--scope", "user"], cenv)
                                dir_ok = True
                            else:
                                diffs.append(f"警告：{cdir} 安裝 Claude 薄 plugin 失敗（{err_i[:160]}），該目錄退回 settings.json hooks 備案")
        if dir_ok:
            plugin_ok_dirs.add(norm_cdir)
        # 清理舊版寫在 .claude.json 頂層 mcpServers 的重複同名項目（已由薄 plugin .mcp.json 接手）
        cjson = env.home / ".claude.json" if same_path(cdir, env.home / ".claude") else cdir / ".claude.json"
        if (dir_ok or (check_only and can_run_plugin)) and cjson.is_file():
            try:
                cdoc = read_json_nobom(cjson)
                mservers = cdoc.get("mcpServers")
                managed_names = {n for n, s in servers.items() if "claude" in (s.get("targets") or [])}
                if isinstance(mservers, dict) and (hit := managed_names & set(mservers)):
                    diffs.append(f"清理 {cjson} 舊版頂層重複 MCP：{', '.join(sorted(hit))}")
                    if not check_only:
                        for n in hit:
                            mservers.pop(n, None)
                        atomic_write_json(cjson, cdoc)
            except ValueError:
                pass
    if not check_only:
        primary = claude_dirs[0] / "settings.json"
        extras = [d / "settings.json" for d in claude_dirs[1:]]
        diffs.extend(claude_allow.apply(
            primary, env.state / "install-record.json", env.state, repo=env.repo,
            extra_settings=extras, plugin_hooks=plugin_ok_dirs, scripts_root=scripts_root,
        ))
    return diffs


def set_codex_approval_mode_toml(txt: str, name: str, mode: str | None) -> str:
    """在 TOML 的 [mcp_servers.<name>] 單一表格內安全取代或移除 default_tools_approval_mode（不產生重複鍵）。"""
    hdr_re = re.compile(rf'^\s*\[\s*mcp_servers\s*\.\s*(?:{re.escape(json.dumps(name))}|{re.escape(name)})\s*\]\s*(?:#.*)?$')
    any_hdr_re = re.compile(r"^\s*\[")
    key_re = re.compile(r"^\s*default_tools_approval_mode\s*=.*$")
    lines = txt.splitlines()
    out: list[str] = []
    in_target = False
    inserted = False
    for line in lines:
        if hdr_re.match(line):
            in_target = True
            out.append(line)
            if mode is not None and not inserted:
                out.append(f'default_tools_approval_mode = {json.dumps(mode)}')
                inserted = True
            continue
        if in_target and any_hdr_re.match(line):
            in_target = False
        if in_target and key_re.match(line):
            continue
        out.append(line)
    res = "\n".join(out) + ("\n" if txt.endswith("\n") or out else "")
    tomllib.loads(res)  # 寫入前強制驗證 TOML 語法合法、無重複鍵
    return res


def sync_codex_mcp_and_hooks(env: Env, codex_dirs: list[Path], servers: dict[str, dict],
                             retired_mcp: set[str] = frozenset(), check_only: bool = False) -> list[str]:
    diffs = []
    allowed = edition.approver(env.state, env.repo)
    wanted = {}
    managed_approval_servers = set()
    for name, s in servers.items():
        if "codex" not in (s.get("targets") or []):
            continue
        opts = dict((s.get("options") or {}).get("codex") or {})
        if "default_tools_approval_mode" in opts:
            managed_approval_servers.add(name)
            if not allowed(name):
                opts.pop("default_tools_approval_mode", None)
        wanted[name] = {"command": s["command"], "args": list(s.get("args") or []), **opts}

    codex_exe = env.which("codex.cmd") or env.which("codex")
    for cdir in codex_dirs:
        cenv = {"CODEX_HOME": str(cdir)}
        cfg_path = cdir / "config.toml"
        if codex_exe or env.runner is not None:
            exe = codex_exe or "codex"
            rc_l, out_l, _ = _run_cli(env, [exe, "mcp", "list", "--json"], cenv)
            parsed_l = parse_json_output(out_l) if rc_l == 0 else None
            cur = {item["name"]: item for item in parsed_l if isinstance(item, dict) and "name" in item} if isinstance(parsed_l, list) else {}
            for name, spec in wanted.items():
                tr = (cur.get(name) or {}).get("transport") or {}
                if tr.get("command") == spec["command"] and list(tr.get("args") or []) == spec["args"]:
                    continue
                diffs.append(f"設定 Codex MCP（CLI）：{name} @ {cdir}")
                if not check_only:
                    cdir.mkdir(parents=True, exist_ok=True)
                    _run_cli(env, [exe, "mcp", "add", name, "--", spec["command"], *spec["args"]], cenv)
            for name in list(cur):
                if (name in retired_mcp or name.startswith(("omnikit-", "omnikit_"))) and name not in wanted:
                    diffs.append(f"移除已下架 Codex MCP：{name} @ {cdir}")
                    if not check_only:
                        _run_cli(env, [exe, "mcp", "remove", name], cenv)
            # 對帳並就地更新／撤回 default_tools_approval_mode（經 tomllib 驗證）
            if cfg_path.is_file():
                txt, nl = codex_hooks.read(cfg_path)
                doc = tomllib.loads(txt) if txt.strip() else {}
                changed_toml = False
                for name in managed_approval_servers:
                    want_mode = wanted[name].get("default_tools_approval_mode")
                    cur_tbl = (doc.get("mcp_servers") or {}).get(name)
                    if not isinstance(cur_tbl, dict):
                        continue
                    if cur_tbl.get("default_tools_approval_mode") != want_mode:
                        diffs.append(f"更新 Codex MCP 免問核准欄位（{name} -> {want_mode or '移除'}）：{cfg_path}")
                        if not check_only:
                            txt = set_codex_approval_mode_toml(txt, name, want_mode)
                            changed_toml = True
                if changed_toml and not check_only:
                    codex_hooks.write(cfg_path, txt, nl)
        else:
            # 離線無 codex CLI 備案：檢查無重複表格後更新受管區塊
            txt, nl = codex_hooks.read(cfg_path)
            outside = CODEX_MCP_BLOCK.sub("", txt)
            out_doc = tomllib.loads(outside) if outside.strip() else {}
            existing_outside = set((out_doc.get("mcp_servers") or {}).keys())
            lines_b = [CODEX_MCP_BEGIN]
            for name, spec in wanted.items():
                if name in existing_outside:
                    continue
                lines_b.append(f"[mcp_servers.{name}]")
                lines_b.append(f"command = {json.dumps(spec['command'])}")
                lines_b.append(f"args = {json.dumps(spec['args'])}")
                if spec.get("default_tools_approval_mode"):
                    lines_b.append(f'default_tools_approval_mode = {json.dumps(spec["default_tools_approval_mode"])}')
            lines_b.append(CODEX_MCP_END)
            block = "\n".join(lines_b) + "\n"
            new_txt = CODEX_MCP_BLOCK.sub(lambda _, b=block: b, txt, count=1) if CODEX_MCP_BLOCK.search(txt) else (txt.rstrip("\n") + "\n\n" if txt.strip() else "") + block
            # 若區塊外已有受管 server，也同步其 default_tools_approval_mode
            for name in managed_approval_servers & existing_outside:
                new_txt = set_codex_approval_mode_toml(new_txt, name, wanted[name].get("default_tools_approval_mode"))
            if new_txt != txt:
                diffs.append(f"更新 Codex config.toml MCP 設定：{cfg_path}")
                if not check_only:
                    tomllib.loads(new_txt)
                    cfg_path.parent.mkdir(parents=True, exist_ok=True)
                    codex_hooks.write(cfg_path, new_txt, nl)
        if not check_only:
            ns = argparse.Namespace(config=cfg_path, record=env.state / "install-record.json", uninstall=False)
            cdir.mkdir(parents=True, exist_ok=True)
            codex_hooks.apply(ns)
    return diffs


def write_agy_thin_plugin(plugin_dir: Path, target_root: Path, servers: dict[str, dict], check_only: bool = False) -> list[str]:
    """在 config/plugins/omnikit/ 寫入 3 個薄宣告 JSON（指令加 call 前綴避開 Windows cmd /c 雙引號剝除問題）。"""
    diffs = []
    uv = Path(os.environ.get("UV") or shutil.which("uv") or "uv").as_posix()
    harness = (target_root / "engine" / "scripts" / "harness_hooks.py").as_posix()
    prefix = "call " if os.name == "nt" else ""
    hcmd = f'{prefix}"{uv}" run --quiet --script "{harness}"'
    files = {
        "plugin.json": {"name": "omnikit", "version": PLUGIN_BASE_VERSION},
        "hooks.json": {
            "omnikit-harness": {
                "PreToolUse": [{"matcher": "run_command|write_file|edit_file|read_file|view_file|grep_search",
                                "hooks": [{"type": "command", "command": hcmd, "timeout": 10}]}],
                "PostToolUse": [{"matcher": "write_file|edit_file",
                                 "hooks": [{"type": "command", "command": hcmd, "timeout": 20}]}],
                "Stop": [{"type": "command", "command": hcmd, "timeout": 30}],
            }
        },
        "mcp_config.json": {
            "mcpServers": {
                name: {"command": s["command"], "args": list(s.get("args") or []),
                       **({"env": dict(s["env"])} if s.get("env") else {})}
                for name, s in servers.items() if "antigravity" in (s.get("targets") or [])
            }
        },
    }
    for fname, payload in files.items():
        p = plugin_dir / fname
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not p.is_file() or p.read_bytes() != raw:
            diffs.append(f"更新 Antigravity 薄 plugin：{p}")
            if not check_only:
                atomic_write_json(p, payload)
    return diffs


def remove_agy_thin_plugin(plugin_dir: Path) -> bool:
    if is_link(plugin_dir):
        remove_dir_link(plugin_dir)
        return True
    if not plugin_dir.is_dir():
        return False
    for fname in AGY_PLUGIN_FILES:
        f = plugin_dir / fname
        if f.is_file():
            retry(f.unlink)
    if not any(plugin_dir.iterdir()):
        retry(os.rmdir, plugin_dir)
    return True


def remove_claude_marketplace_dir(state: Path) -> None:
    mp = state / "claude-marketplace"
    if not mp.is_dir():
        return
    known_files = [
        mp / ".claude-plugin" / "marketplace.json",
        mp / "plugins" / "omnikit" / ".claude-plugin" / "plugin.json",
        mp / "plugins" / "omnikit" / "hooks" / "hooks.json",
        mp / "plugins" / "omnikit" / ".mcp.json",
    ]
    for f in known_files:
        if f.is_file():
            retry(f.unlink)
    known_dirs = [
        mp / "plugins" / "omnikit" / ".claude-plugin",
        mp / "plugins" / "omnikit" / "hooks",
        mp / "plugins" / "omnikit",
        mp / "plugins",
        mp / ".claude-plugin",
        mp,
    ]
    for d in known_dirs:
        if d.is_dir() and not any(d.iterdir()):
            retry(os.rmdir, d)


def sync_antigravity_plugins(env: Env, target_root: Path, servers: dict[str, dict], check_only: bool = False) -> list[str]:
    diffs = []
    t3_profiles, t3_err = homes.t3_antigravity_profiles(env.home)
    if t3_err:
        raise SystemExit(t3_err)
    targets = [env.home / ".gemini"] + [f.path for f in t3_profiles if f.path.is_dir()]
    for gdir in targets:
        diffs.extend(write_agy_thin_plugin(gdir / "config" / "plugins" / "omnikit", target_root, servers, check_only=check_only))
    # 清理舊版直接寫在 ~/.gemini/config/mcp_config.json 的重複同名 MCP（保持 mcp_config.json 乾淨以維持 T3 文字生成可用）
    old_mcp = env.home / ".gemini" / "config" / "mcp_config.json"
    if old_mcp.is_file():
        try:
            mdoc = read_json_nobom(old_mcp)
            ms = mdoc.get("mcpServers")
            managed = {n for n, s in servers.items() if "antigravity" in (s.get("targets") or [])}
            if isinstance(ms, dict) and (hit := managed & set(ms)):
                diffs.append(f"清理 {old_mcp} 舊版頂層重複 MCP：{', '.join(sorted(hit))}")
                if not check_only:
                    for n in hit:
                        ms.pop(n, None)
                    atomic_write_json(old_mcp, mdoc)
        except ValueError:
            pass
    # 清理舊版停用的 T3 Binary path 轉接程式
    if not check_only and (env.home / ".t3").is_dir():
        t3_acp.remove(env.home, t3_acp.acp_dir(env.home))
    return diffs


def run_sync(env: Env, *, profile: str | None = None, agents_override: list[str] | None = None,
             take_over: bool = False, do_rules: bool = True, do_skills: bool = True,
             do_mcp: bool = True, do_user_plugins: bool = True, dev: bool | None = None,
             check_only: bool = False) -> tuple[int, list[str]]:
    real_repo = resolve_real_repo(env.repo, env.state)
    env = Env(home=env.home, repo=real_repo, state=env.state, which=env.which, runner=env.runner, environ=env.environ)
    cfg = load_config(env.state)
    agents = active_agents(env, agents_override)
    if not agents:
        raise SystemExit("找不到 Claude Code、Codex 或 Antigravity，請先安裝至少一個 agent")
    if dev is not None:
        cfg["dev_link"] = bool(dev)
    cfg["agents"] = agents
    if not is_inside_dir(real_repo, env.state / "current"):
        cfg["repo"] = str(real_repo.resolve())
    if not check_only:
        save_config(env.state, cfg)

    use_dev = bool(cfg.get("dev_link")) if dev is None else bool(dev)
    target_root, clone_notes = ensure_current_clone(real_repo, env.state, dev=use_dev, check_only=check_only)
    lines = list(clone_notes)
    diffs = []

    found = homes.discover(env.home, env.environ)
    claude_dirs = [env.home / ".claude", *[f.path for f in found if f.agent == "claude-code" and f.writable]]
    codex_dirs = [env.home / ".codex", *[f.path for f in found if f.agent == "codex" and f.writable]]

    if do_rules and not check_only:
        paths = {"claude-code": env.home / ".claude" / "CLAUDE.md",
                 "codex": env.home / ".codex" / "AGENTS.md",
                 "antigravity": env.home / ".gemini" / "GEMINI.md"}
        lines.extend(profiles.apply(
            real_repo / "data", env.state, paths=paths, wanted=profile, agents=agents, take_over=take_over,
            claude_extra=[d / "CLAUDE.md" for d in claude_dirs[1:]],
            codex_extra=[d / "AGENTS.md" for d in codex_dirs[1:]],
            new_extra=[d / "AGENTS.md" for d in codex_dirs[1:] if not (d / "AGENTS.md").exists()],
        ))

    if do_skills:
        wanted_skills, skipped = expected_skills(target_root, real_repo / "data", env.state)
        src_skills = target_root / "engine" / "skills"
        if "claude-code" in agents:
            for d in claude_dirs:
                diffs.extend(sync_dir_junctions(d / "skills", src_skills, wanted_skills, check_only=check_only))
            diffs.extend(sync_user_claude_skills(env.home, claude_dirs, real_repo, env.state, check_only=check_only))
        if "codex" in agents:
            for d in codex_dirs:
                diffs.extend(sync_dir_junctions(d / "skills", src_skills, wanted_skills, check_only=check_only))
            # 清理舊版留在 ~/.agents/skills 的 OmniKit 複製品或連結
            old_agents_skills = env.home / ".agents" / "skills"
            if old_agents_skills.is_dir():
                diffs.extend(sync_dir_junctions(old_agents_skills, src_skills, [], check_only=check_only))
        if "antigravity" in agents:
            diffs.extend(sync_antigravity_skills(env, src_skills, skipped, check_only=check_only))

    if do_mcp:
        servers, retired_mcp = load_mcp_manifest_full(target_root)
        if "claude-code" in agents:
            diffs.extend(sync_claude_plugin_and_settings(env, claude_dirs, target_root, servers, check_only=check_only))
            if do_user_plugins:
                diffs.extend(sync_user_claude_plugins(env, claude_dirs, check_only=check_only))
        if "codex" in agents:
            diffs.extend(sync_codex_mcp_and_hooks(env, codex_dirs, servers, retired_mcp=retired_mcp, check_only=check_only))
        if "antigravity" in agents:
            diffs.extend(sync_antigravity_plugins(env, target_root, servers, check_only=check_only))
    elif do_user_plugins and "claude-code" in agents:
        diffs.extend(sync_user_claude_plugins(env, claude_dirs, check_only=check_only))

    if check_only:
        return (1 if diffs else 0), (diffs or ["無帳本對帳通過：所有設定皆與 manifest 一致。"])
    return 0, [*lines, *(diffs or ["skills、hooks 與 MCP 已是最新。"])]


def disconnect(env: Env) -> list[str]:
    lines = []
    found = homes.discover(env.home, env.environ)
    claude_dirs = [env.home / ".claude", *[f.path for f in found if f.agent == "claude-code" and f.writable]]
    codex_dirs = [env.home / ".codex", *[f.path for f in found if f.agent == "codex" and f.writable]]
    src_skills = env.repo / "engine" / "skills"

    lines.extend(unmirror_user_claude_skills(env.home, claude_dirs, env.repo, env.state))
    servers, retired_mcp = load_mcp_manifest_full(env.repo)
    for d in [*claude_dirs, *codex_dirs, env.home / ".agents"]:
        sdir = d / "skills"
        if sdir.is_dir():
            lines.extend(sync_dir_junctions(sdir, src_skills, [], check_only=False))
        if d in claude_dirs and d != env.home / ".claude":
            lines.extend(profiles.disconnect_block(d / "CLAUDE.md"))
        if d in codex_dirs:
            lines.extend(profiles.disconnect_block(d / "AGENTS.md"))
            cfg_p = d / "config.toml"
            if cfg_p.is_file():
                txt, nl = codex_hooks.read(cfg_p)
                cleaned = CODEX_MCP_BLOCK.sub("", txt)
                if cleaned != txt:
                    codex_hooks.write(cfg_p, cleaned, nl)
            codex_exe = env.which("codex.cmd") or env.which("codex")
            if codex_exe or env.runner is not None:
                exe = codex_exe or "codex"
                for name in set(servers) | retired_mcp:
                    _run_cli(env, [exe, "mcp", "remove", name], {"CODEX_HOME": str(d)})

    claude_exe = env.which("claude")
    if claude_exe or env.runner is not None:
        exe = claude_exe or "claude"
        for cdir in claude_dirs:
            cenv = claude_cli_env(env.home, cdir)
            _run_cli(env, [exe, "plugin", "uninstall", PLUGIN_ID], cenv)
            _run_cli(env, [exe, "plugin", "marketplace", "remove", MARKETPLACE_NAME], cenv)
    remove_claude_marketplace_dir(env.state)

    sj = env.home / ".gemini" / "config" / "skills.json"
    if sj.is_file():
        doc = read_json_nobom(sj)
        kept = [e for e in (doc.get("entries") or []) if not (isinstance(e, dict) and _is_our_agy_skills_entry(str(e.get("path", "")), env))]
        if kept or doc.get("inherits"):
            atomic_write_json(sj, {**doc, "entries": kept})
        else:
            retry(sj.unlink)
        lines.append("已移除 Antigravity skills.json 的 OmniKit 參照")

    t3_profiles, _ = homes.t3_antigravity_profiles(env.home)
    for gdir in [env.home / ".gemini", *[f.path for f in t3_profiles if f.path.is_dir()]]:
        if remove_agy_thin_plugin(gdir / "config" / "plugins" / "omnikit"):
            lines.append(f"已移除 Antigravity 薄 plugin：{gdir}")
    lines.extend(profiles.disconnect_antigravity(env.home / ".gemini" / "GEMINI.md"))
    if (env.home / ".t3").is_dir():
        t3_acp.remove(env.home, t3_acp.acp_dir(env.home))

    for fname in ("config.json", "agents.json"):
        p = env.state / fname
        if p.exists():
            retry(p.unlink)
    return lines or ["沒有要移除的 OmniKit 同步項目。"]


def approvals_cmd(env: Env, ask_fn=None, grant=(), revoke=()) -> list[str]:
    servers = load_mcp_manifest(env.repo)
    tools = sorted({edition.tool_of(r) for r in claude_allow.rules(env.repo)}
                   | {n for n, s in servers.items() if ((s.get("options") or {}).get("codex") or {}).get("default_tools_approval_mode")})
    lines = []
    for name in grant:
        edition.record(env.state, name, True)
        lines.append(f"已同意免問核准：{name}")
    for name in revoke:
        edition.record(env.state, name, False)
        lines.append(f"已撤回免問核准：{name}")
    if ask_fn and edition.resolve(env.state, env.repo)[0] != "maintainer":
        for t in tools:
            if edition.decided(env.state, t) is None:
                ans = ask_fn(t)
                edition.record(env.state, t, ans)
    if grant or revoke:
        _, slines = run_sync(env, do_rules=False, do_skills=False, do_mcp=True, do_user_plugins=False)
        lines.extend(slines)
    if not lines:
        ed, _ = edition.resolve(env.state, env.repo)
        lines.append(f"目前版本：{ed}；可管免問工具：{', '.join(tools) or '無'}")
    return lines


def status_cmd(env: Env, environ: dict | None = None) -> int:
    found = homes.discover(env.home, environ if environ is not None else env.environ)
    legacy = [str(p) for _, p, _ in statedir.pending(env.state, environ)]
    out = {
        "state": str(env.state),
        "repo": str(resolve_real_repo(env.repo, env.state)),
        "target_root": str(env.target_root()),
        "agents": active_agents(env),
        "homes": [f.key for f in found],
        "legacy": legacy,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def selftest() -> int:
    fails = []

    def check(label: str, cond: bool) -> None:
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            fails.append(label)

    # 1. 靜態檢查：本檔原始碼嚴禁出現遞迴刪除函式名稱（用字串拼接檢查，避免自身誤中）
    forbidden = "rm" + "tree"
    me_src = Path(__file__).read_text(encoding="utf-8")
    check("零遞迴刪除：sync.py 原始碼完全不含遞迴刪除呼叫", forbidden not in me_src)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        home, repo, state = base / "home", base / "repo", base / "state"
        for d in (home / ".claude", home / ".claude-kai", home / ".codex", home / ".gemini" / "config"):
            d.mkdir(parents=True)
        # 放入使用者自己的檔案與 .claude-mem，驗證絕不誤觸 .claude-mem 且自訂 skill 會鏡像至 .claude-kai
        (home / ".claude-mem").mkdir()
        (home / ".claude" / "skills" / "my-own-skill").mkdir(parents=True)
        (home / ".claude" / "skills" / "my-own-skill" / "SKILL.md").write_text("---\nname: my-own-skill\n---\n", encoding="utf-8")
        t3_s = home / ".t3" / "userdata" / "settings.json"
        t3_s.parent.mkdir(parents=True)
        t3_s.write_text(json.dumps({"providerInstances": {
            "kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
            "antigravity_ryan": {"driver": "antigravity"},
        }}), encoding="utf-8")
        agy_inst = homes.t3_antigravity_dir(home, "antigravity_ryan")
        (agy_inst / "config").mkdir(parents=True)

        # 建立最小測試 repo
        (repo / "data" / "rules").mkdir(parents=True)
        (repo / "data" / "rules" / "baseline.md").write_text("# 安全底線\n", encoding="utf-8")
        (repo / "data" / "profiles" / "default").mkdir(parents=True)
        (repo / "data" / "profiles" / "default" / "AGENTS.md").write_text("# default\n", encoding="utf-8")
        (repo / "data" / "harness").mkdir(parents=True)
        (repo / "data" / "harness" / "claude-allow.txt").write_text("mcp__devtools\n", encoding="utf-8")
        (repo / "data" / "harness" / "claude-allow-retired.txt").write_text("mcp__retired_old\n", encoding="utf-8")
        for sname in ("omnikit-ask", "ok-ask", "omnikit-eval", "ok-eval"):
            sd = repo / "engine" / "skills" / sname
            sd.mkdir(parents=True)
            (sd / "SKILL.md").write_text(f"---\nname: {sname}\ndescription: test {sname}\n---\n", encoding="utf-8")
        (repo / "data" / "mcp").mkdir(parents=True)
        (repo / "data" / "mcp" / "servers.yaml").write_text(
            "servers:\n  devtools:\n    command: cmd\n    args: [/c, echo, hi]\n    targets: [claude, codex, antigravity]\n"
            "    options:\n      codex:\n        default_tools_approval_mode: approve\n",
            encoding="utf-8",
        )
        edition.set_edition(state, "maintainer")

        cli_calls = []
        installed_plugins: dict[str, dict] = {}
        codex_mcps: dict[str, dict] = {}

        def fake_runner(cmd, env_map):
            has_ccd = "CLAUDE_CONFIG_DIR" in env_map
            ccd_val = env_map.get("CLAUDE_CONFIG_DIR")
            cli_calls.append((cmd[0], cmd[1:3], has_ccd, ccd_val))
            cdir = ccd_val if has_ccd else str(home / ".claude")
            if cmd[0] == "claude":
                if cmd[1:4] == ["plugin", "list", "--json"]:
                    items = [installed_plugins[cdir]] if cdir in installed_plugins else []
                    return 0, json.dumps(items), ""
                if cmd[1:3] == ["plugin", "install"]:
                    mp_idx = cmd.index("--marketplace") + 1
                    mp_dir = Path(cmd[mp_idx])
                    pjson = json.loads((mp_dir / "plugins" / "omnikit" / ".claude-plugin" / "plugin.json").read_text("utf-8"))
                    installed_plugins[cdir] = {
                        "id": PLUGIN_ID,
                        "version": pjson["version"],
                        "enabled": True,
                        "readFromFolder": str(mp_dir / "plugins" / "omnikit"),
                    }
                    return 0, '{"outcome":"ok"}', ""
                if cmd[1:3] == ["plugin", "enable"] and cdir in installed_plugins:
                    installed_plugins[cdir]["enabled"] = True
                    return 0, "", ""
                if cmd[1:3] == ["plugin", "uninstall"]:
                    installed_plugins.pop(cdir, None)
                    return 0, "", ""
            if cmd[0] == "codex":
                ch = env_map.get("CODEX_HOME") or str(home / ".codex")
                if cmd[1:3] == ["mcp", "list"]:
                    items = [{"name": k, "enabled": True, "transport": v} for k, v in codex_mcps.get(ch, {}).items()]
                    return 0, json.dumps(items), ""
                if cmd[1:3] == ["mcp", "add"]:
                    idx = cmd.index("--")
                    name = cmd[3]
                    codex_mcps.setdefault(ch, {})[name] = {"command": cmd[idx + 1], "args": cmd[idx + 2:]}
                    toml_p = Path(ch) / "config.toml"
                    prev = toml_p.read_text("utf-8") if toml_p.is_file() else ""
                    if f"[mcp_servers.{name}]" not in prev:
                        toml_p.write_text(prev + f'\n[mcp_servers.{name}]\ncommand = "{cmd[idx + 1]}"\n', encoding="utf-8")
                    return 0, "", ""
                if cmd[1:3] == ["mcp", "remove"]:
                    codex_mcps.get(ch, {}).pop(cmd[3], None)
                    return 0, "", ""
            return 0, "", ""

        # 故意在父環境放 CLAUDE_CONFIG_DIR 指向 kai，驗證 B1 對 ~/.claude 會移除該變數而非設空字串
        env = Env(home=home, repo=repo, state=state, which=lambda n: n if n in ("claude", "codex", "agy") else None,
                  runner=fake_runner, environ={"CLAUDE_CONFIG_DIR": str(home / ".claude-kai")})
        rc, _ = run_sync(env, profile="default", agents_override=["claude-code", "codex", "antigravity"], take_over=True)
        check("connect 同步三家成功且未產生雜湊帳本 agents.json 或 .omnikit.json",
              rc == 0 and not (state / "agents.json").exists() and not list(home.rglob(LEGACY_MARKER)))
        check("B1 防護：父環境有 CLAUDE_CONFIG_DIR 時，對 ~/.claude 執行 CLI 會移除該環境變數（不設空字串）",
              any(c[0] == "claude" and c[2] is False for c in cli_calls)
              and not any(c[0] == "claude" and c[3] == "" for c in cli_calls))
        check("B8 鏡像：Claude 與 .claude-kai 皆有 OmniKit junction，且 ~/.claude 自訂 skill 自動鏡像至 .claude-kai、不碰 .claude-mem",
              is_link(home / ".claude" / "skills" / "omnikit-ask")
              and is_link(home / ".claude-kai" / "skills" / "ok-ask")
              and is_link(home / ".claude-kai" / "skills" / "my-own-skill")
              and not (home / ".claude-mem" / "CLAUDE.md").exists())
        codex_cfg = tomllib.loads((home / ".codex" / "config.toml").read_text("utf-8"))
        check("B6 Codex：skills junction 與 MCP CLI 就位，且 default_tools_approval_mode 合法寫入 TOML",
              is_link(home / ".codex" / "skills" / "omnikit-ask")
              and codex_cfg["mcp_servers"]["devtools"].get("default_tools_approval_mode") == "approve")

        # 測試同事版撤回核准時，B6 能乾淨移除 default_tools_approval_mode 且不產生重複鍵
        edition.set_edition(state, "colleague")
        approvals_cmd(env, revoke=["devtools"])
        codex_cfg_revoked = tomllib.loads((home / ".codex" / "config.toml").read_text("utf-8"))
        approvals_cmd(env, grant=["devtools"])
        codex_cfg_granted = tomllib.loads((home / ".codex" / "config.toml").read_text("utf-8"))
        check("B6 撤回與重開核准：default_tools_approval_mode 原地刪除與加回皆通過 tomllib 驗證",
              "default_tools_approval_mode" not in codex_cfg_revoked["mcp_servers"]["devtools"]
              and codex_cfg_granted["mcp_servers"]["devtools"].get("default_tools_approval_mode") == "approve")
        edition.set_edition(state, "maintainer")

        # B5 防護：模擬從 ~/.omnikit/current 觸發 sync，config.json["repo"] 不會被覆寫成 current
        cur_fake = state / "current"
        (cur_fake / "data" / "rules").mkdir(parents=True)
        (cur_fake / "data" / "rules" / "baseline.md").write_text("# 安全底線\n", encoding="utf-8")
        env_from_cur = Env(home=home, repo=cur_fake, state=state, which=env.which, runner=fake_runner, environ={})
        run_sync(env_from_cur, dev=True)
        check("B5 防護：從 ~/.omnikit/current 啟動 sync 時，config.json['repo'] 仍保持真實開發 repo",
              same_path(Path(load_config(state)["repo"]), repo))

        sj = read_json_nobom(home / ".gemini" / "config" / "skills.json")
        check("Antigravity skills.json 使用前導斜線 POSIX 路徑參照，且 ~/.gemini 與 T3 實例皆有薄 plugin 三檔（指令含 call）",
              any(e["path"].endswith("/engine/skills") and e["path"].startswith("/") for e in sj["entries"])
              and (home / ".gemini" / "config" / "plugins" / "omnikit" / "hooks.json").is_file()
              and (agy_inst / "config" / "plugins" / "omnikit" / "hooks.json").is_file()
              and (os.name != "nt" or "call " in (agy_inst / "config" / "plugins" / "omnikit" / "hooks.json").read_text("utf-8")))
        rc_chk, chk_lines = run_sync(env, check_only=True)
        check("--check 唯讀對帳模式：同步後 0 差異通過", rc_chk == 0 and "一致" in chk_lines[0])

        # MCP 密鑰阻擋測試
        (repo / "data" / "mcp" / "servers.yaml").write_text(
            "servers:\n  bad:\n    command: x\n    env:\n      API_KEY: secret123\n    targets: [claude]\n", encoding="utf-8"
        )
        blocked_secret = False
        try:
            load_mcp_manifest(repo)
        except SystemExit:
            blocked_secret = True
        check("servers.yaml 若寫死 env 密鑰值直接拒絕報錯", blocked_secret)
        (repo / "data" / "mcp" / "servers.yaml").write_text(
            "servers:\n  devtools:\n    command: cmd\n    args: [/c, echo, hi]\n    targets: [claude, codex, antigravity]\n",
            encoding="utf-8",
        )

        # disconnect 乾淨移除，.claude-kai 鏡像連結移除且 ~/.claude 使用者自己的 skill 本尊完好無損
        disconnect(env)
        check("disconnect：移除所有 OmniKit 連結、鏡像連結與薄 plugin，~/.claude 使用者自訂 skill 本尊完好保留",
              not is_link(home / ".claude" / "skills" / "omnikit-ask")
              and not is_link(home / ".claude-kai" / "skills" / "my-own-skill")
              and not is_link(home / ".codex" / "skills" / "omnikit-ask")
              and not (agy_inst / "config" / "plugins" / "omnikit").exists()
              and not (state / "claude-marketplace").exists()
              and (home / ".claude" / "skills" / "my-own-skill" / "SKILL.md").is_file())

    print(f"\n{'sync.py selftest：全部通過' if not fails else f'sync.py selftest：{len(fails)} 項失敗'}")
    return 1 if fails else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OmniKit 無帳本同步器（Claude Code、Codex、Antigravity）")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("connect", help="首次接上或重設 agent（install.ps1 用）")
    c.add_argument("--profile", help="同時指定 profile")
    c.add_argument("--agents", help=f"逗號分隔：{','.join(AGENTS)}")
    c.add_argument("--ask", action="store_true", help="相容旗標")
    cg = c.add_mutually_exclusive_group()
    cg.add_argument("--dev", action="store_true", help="直接連結開發 repo（預設使用 ~/.omnikit/current 乾淨副本）")
    cg.add_argument("--no-dev", action="store_true", help="關閉 dev_link，切回 ~/.omnikit/current 乾淨副本")

    s = sub.add_parser("sync", help="依 repo manifest 無狀態對帳同步")
    s.add_argument("--skills", action="store_true")
    s.add_argument("--mcp", action="store_true")
    s.add_argument("--plugins", action="store_true")
    s.add_argument("--ask", action="store_true")
    s.add_argument("--check", action="store_true", help="純唯讀對帳模式（有差異 exit 1）")
    sg = s.add_mutually_exclusive_group()
    sg.add_argument("--dev", action="store_true", help="直接連結開發 repo")
    sg.add_argument("--no-dev", action="store_true", help="關閉 dev_link，切回 ~/.omnikit/current 乾淨副本")

    a = sub.add_parser("approvals", help="免問核准同意或撤回")
    a.add_argument("--ask", action="store_true")
    a.add_argument("--grant", action="append", default=[], metavar="名稱")
    a.add_argument("--revoke", action="append", default=[], metavar="名稱")

    sub.add_parser("disconnect", help="移除所有 OmniKit 連結、薄 plugin 與受管區塊")
    sub.add_parser("status", help="印出目前狀態與設定目錄")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    env = real_env()
    if args.command == "status":
        return status_cmd(env)
    is_readonly_check = args.command == "sync" and args.check
    moved = statedir.migrate(env.state) if (args.command and not is_readonly_check) else statedir.Result(env.state)
    for line in moved.lines():
        print(line)

    def _dev_arg(ns) -> bool | None:
        if getattr(ns, "dev", False):
            return True
        if getattr(ns, "no_dev", False):
            return False
        return None

    if args.command == "connect":
        wanted_agents = args.agents.split(",") if args.agents else None
        if wanted_agents and (bad := [x for x in wanted_agents if x not in AGENTS]):
            parser.error(f"不認得的 agent：{'、'.join(bad)}")
        rc, lines = run_sync(env, profile=args.profile, agents_override=wanted_agents, take_over=True, dev=_dev_arg(args))
    elif args.command == "sync":
        every = not (args.skills or args.mcp or args.plugins)
        rc, lines = run_sync(
            env,
            do_rules=every,
            do_skills=bool(args.skills or every),
            do_mcp=bool(args.mcp or args.plugins or every),
            do_user_plugins=bool(args.plugins or every),
            dev=_dev_arg(args),
            check_only=args.check,
        )
    elif args.command == "approvals":
        interactive = sys.stdin.isatty()
        ask_fn = (lambda t: input(f"同意 {t} 免問核准嗎？(y/N)：").strip().lower() in ("y", "yes")) if args.ask and interactive else None
        lines = approvals_cmd(env, ask_fn=ask_fn, grant=args.grant, revoke=args.revoke)
        if args.ask and not interactive and edition.resolve(env.state, env.repo)[0] != "maintainer":
            lines.append(f"沒辦法詢問（不能互動）：還沒問的免問核准先不寫入；要同意就執行 {claude_allow.GRANT}")
        rc = 0
    elif args.command == "disconnect":
        lines = disconnect(env)
        rc = 0
    else:
        parser.print_help()
        return 2

    for line in lines:
        print(line)
    return rc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
