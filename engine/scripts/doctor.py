# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit doctor（無帳本對帳＋Fable Stage 2 第 6 節全面防呆健康檢查）。

只讀不寫；查不到的標「未知」，不當作通過；任一項失敗 exit 1。
檢查範圍：
1. 無狀態設定對帳（由 repo manifest 直接算期望狀態，不依賴 agents.json）：
   - 規則：Claude（@import＋帶內金絲雀行，並依 dev_link 檢查目標與 current HEAD 是否最新）、
     Codex（受管區塊 <= 32 KiB）、Antigravity（AGENTS.md 共用＋GEMINI.md 個人，單檔 <= 24,000 bytes、無同目錄硬連結）。
   - Skills：Claude 與 Codex 的每個設定目錄皆有指向目標的 Directory Junction；Antigravity 的 config/skills.json 有參照。
   - Hooks 與 MCP：Claude 薄 plugin（透過 --json 驗證 enabled 與內容雜湊版本）或備案 hooks、
     權限清單（現行有、墓碑無，並列出自訂權限）；Codex MCP（含 default_tools_approval_mode）與 Stop hooks；
     Antigravity 薄 plugin（~/.gemini 與全部 T3 實例）。
2. Hook 端到端自測與實際執行檔檢查：對 harness_hooks.py 實跑餵入三種輸入方言的假危險指令確認皆回傳 deny，
   並檢查已安裝 hook 實際指向的 uv / Python 執行檔真實存在且非 WindowsApps Store 別名。
3. T3 專屬健康檢查（~/.t3 存在時必跑）：
   - 列舉到 0 個 Antigravity 實例直接報錯（不沉默）；
   - 每個實例的 config/skills 是指向 ~/.gemini/config/skills 的 junction；
   - 比對每個實例的 AGENTS.md、GEMINI.md、config/skills.json 與 ~/.gemini 本尊位元組是否一致：不同但等於 T3 的
     .t3-rule-copies.json 記錄判 WARN（下次啟動會刷新，sync 也會代刷）；也不等於記錄判 FAIL「T3 同步已卡住」；
   - 每個實例的 config/plugins/omnikit/hooks.json 已就位。
4. SKILL.md 與 MCP 規範檢查：目錄名 == name、有 description、無 UTF-8 BOM、無穿出 skills 根目錄的相對路徑；
   servers.yaml 的 env 不得寫死密鑰值；同步器與 doctor 原始碼零遞迴刪除。

用法：uv run engine/scripts/doctor.py [--preflight] [--json] [--no-lists]
      uv run engine/scripts/doctor.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_allow
import edition
import homes
import profiles
import sync

OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"
MARK = {OK: "✓", WARN: "！", FAIL: "✗", UNKNOWN: "？"}
CODEX_SCRIPTS = (claude_allow.NUDGE, claude_allow.CLAIM, claude_allow.T3W, claude_allow.DONE)
REL_LINK_RE = re.compile(r"\]\(([^)]+)\)")
QUOTED_EXE_RE = re.compile(r'^(?:call\s+)?"([^"]+)"')


def row(area: str, agent: str, item: str, status: str, detail: str = "") -> dict:
    return {"area": area, "agent": agent, "item": item, "status": status, "detail": detail}


def same_text(a: str, b: str) -> bool:
    return a.replace("\r\n", "\n").strip() == b.replace("\r\n", "\n").strip()


def _git_head(repo_dir: Path) -> str | None:
    if not (repo_dir / ".git").exists() or not shutil.which("git"):
        return None
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                       env=git_env, capture_output=True, text=True, timeout=10, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def check_current_clone(env: sync.Env) -> list[dict]:
    cfg = sync.load_config(env.state)
    real_repo = sync.resolve_real_repo(env.repo, env.state)
    if cfg.get("dev_link"):
        return [row("參照副本", "", "dev_link 模式", OK, f"直接連結開發倉庫 {real_repo}")]
    if not (real_repo / ".git").exists():
        return []
    cur = env.state / "current"
    repo_head = _git_head(real_repo)
    cur_head = _git_head(cur)
    if repo_head and cur_head == repo_head:
        return [row("參照副本", "", "~/.omnikit/current", OK, f"與 repo HEAD 一致（{cur_head[:7]}）")]
    return [row("參照副本", "", "~/.omnikit/current", FAIL,
                f"與 repo HEAD 不一致或尚未建立（current={cur_head[:7] if cur_head else '無'} vs repo={repo_head[:7] if repo_head else '未知'}）：跑 sync.py sync")]


def check_rules(env: sync.Env, agents: list[str], claude_dirs: list[Path], codex_dirs: list[Path]) -> list[dict]:
    real_repo = sync.resolve_real_repo(env.repo, env.state)
    data = real_repo / "data"
    try:
        name, _ = profiles.resolve(data, env.state)
    except SystemExit as e:
        return [row("規則", profiles.NAMES.get(a, a), "受管區塊", FAIL, str(e.code)) for a in agents]
    out = []
    targets = []
    if "claude-code" in agents:
        for i, d in enumerate(claude_dirs):
            lbl = "Claude Code" if i == 0 else f"Claude Code（{d.name}）"
            targets.append(("claude-code", d / "CLAUDE.md", lbl))
    if "codex" in agents:
        for i, d in enumerate(codex_dirs):
            lbl = "Codex" if i == 0 else f"Codex（{d.name}）"
            targets.append(("codex", d / "AGENTS.md", lbl))
    if "antigravity" in agents:
        gem = env.home / ".gemini" / "GEMINI.md"
        targets.append(("antigravity-shared", gem.with_name("AGENTS.md"), "Antigravity"))
        targets.append(("antigravity-personal", gem, "Antigravity"))

    for kind, path, lbl in targets:
        raw_text = profiles.text(path) if path.exists() else ""
        found = profiles.BLOCK.search(raw_text) if path.exists() else None
        size_b = len(raw_text.encode("utf-8"))
        if not found:
            out.append(row("規則", lbl, path.name, FAIL, f"{path} 沒有 OmniKit 受管區塊：跑 uv run engine/scripts/sync.py sync"))
            continue
        if kind == "claude-code":
            want = profiles.claude_block(data, env.state, name)
            has_canary = profiles.CANARY in found.group(0)
            if not has_canary:
                out.append(row("規則", lbl, path.name, FAIL, "缺少帶內金絲雀行：跑 uv run engine/scripts/sync.py sync"))
            elif same_text(found.group(0), want):
                out.append(row("規則", lbl, path.name, OK, f"與 profile {name} 一致（含金絲雀行）"))
            else:
                out.append(row("規則", lbl, path.name, FAIL, f"受管區塊與 profile {name} 不同：跑 uv run engine/scripts/sync.py sync"))
        elif kind == "antigravity-shared":
            want = profiles.content_block(profiles.compose_shared(data))
            if size_b > profiles.AGY_MAX_FILE_BYTES:
                out.append(row("規則", lbl, path.name, FAIL, f"{size_b:,} bytes 超過上限 {profiles.AGY_MAX_FILE_BYTES:,} bytes"))
            elif same_text(found.group(0), want):
                out.append(row("規則", lbl, path.name, OK, f"與共用層一致（{size_b:,} bytes）"))
            else:
                out.append(row("規則", lbl, path.name, FAIL, "受管區塊與共用規則不同"))
        elif kind == "antigravity-personal":
            want = profiles.content_block(profiles.compose_personal(data, env.state, name))
            if size_b > profiles.AGY_MAX_FILE_BYTES:
                out.append(row("規則", lbl, path.name, FAIL, f"{size_b:,} bytes 超過上限 {profiles.AGY_MAX_FILE_BYTES:,} bytes"))
            elif same_text(found.group(0), want):
                out.append(row("規則", lbl, path.name, OK, f"與 profile {name} 一致（{size_b:,} bytes）"))
            else:
                out.append(row("規則", lbl, path.name, FAIL, f"受管區塊與 profile {name} 不同"))
        else:
            want = profiles.content_block(profiles.compose(data, env.state, name))
            if size_b > profiles.CODEX_MAX_FILE_BYTES:
                out.append(row("規則", lbl, path.name, FAIL, f"{size_b:,} bytes 超過 Codex 32 KiB 上限"))
            elif same_text(found.group(0), want):
                out.append(row("規則", lbl, path.name, OK, f"與 profile {name} 一致（{size_b:,} bytes）"))
            else:
                out.append(row("規則", lbl, path.name, FAIL, f"受管區塊與 profile {name} 不同"))

    if "antigravity" in agents:
        gem = env.home / ".gemini" / "GEMINI.md"
        ag = gem.with_name("AGENTS.md")
        if ag.exists() and gem.exists():
            try:
                if os.path.samefile(ag, gem):
                    out.append(row("規則", "Antigravity", "硬連結檢查", FAIL, "AGENTS.md 與 GEMINI.md 為同一硬連結，會雙重載入"))
            except OSError:
                pass
    return out


def check_skills(env: sync.Env, agents: list[str], claude_dirs: list[Path], codex_dirs: list[Path]) -> list[dict]:
    out = []
    troot = env.target_root()
    real_repo = sync.resolve_real_repo(env.repo, env.state)
    wanted, skipped = sync.expected_skills(troot, real_repo / "data", env.state)
    src_root = troot / "engine" / "skills"
    dir_checks = []
    if "claude-code" in agents:
        dir_checks += [(d / "skills", "Claude Code" if i == 0 else f"Claude Code（{d.name}）") for i, d in enumerate(claude_dirs)]
    if "codex" in agents:
        dir_checks += [(d / "skills", "Codex" if i == 0 else f"Codex（{d.name}）") for i, d in enumerate(codex_dirs)]
    for sdir, lbl in dir_checks:
        missing = [n for n in wanted if not (sync.is_link(sdir / n) and sync.same_path(sync.link_target(sdir / n), src_root / n))]
        stale = [p.name for p in (sdir.iterdir() if sdir.is_dir() else []) if sync.is_omnikit_skill(p.name) and p.name not in wanted]
        if not missing and not stale:
            out.append(row("skills", lbl, f"{len(wanted)} 個 junction", OK, f"皆指向 {src_root}"))
        else:
            detail = []
            if missing:
                detail.append(f"缺少或指錯：{', '.join(missing[:5])}")
            if stale:
                detail.append(f"多餘未清：{', '.join(stale[:5])}")
            out.append(row("skills", lbl, "junction 對帳", FAIL, "；".join(detail) + "（跑 sync.py sync）"))
    if "antigravity" in agents:
        sj = env.home / ".gemini" / "config" / "skills.json"
        want_p = sync.agy_posix_skills_path(src_root)
        doc = sync.read_json_nobom(sj) if sj.is_file() else {}
        matched = next((e for e in (doc.get("entries") or []) if isinstance(e, dict) and e.get("path") == want_p), None)
        if matched is not None and set(matched.get("exclude") or []) == skipped:
            out.append(row("skills", "Antigravity", "config/skills.json", OK, f"參照 {want_p}"))
        else:
            out.append(row("skills", "Antigravity", "config/skills.json", FAIL, f"未正確參照 {want_p}：跑 sync.py sync"))
    return out


def check_permissions_and_hooks(env: sync.Env, agents: list[str], claude_dirs: list[Path], codex_dirs: list[Path]) -> list[dict]:
    out = []
    real_repo = sync.resolve_real_repo(env.repo, env.state)
    troot = env.target_root()
    servers = sync.load_mcp_manifest(troot)
    allowed = edition.approver(env.state, real_repo)
    listed = claude_allow.rules(real_repo)
    retired = set(claude_allow.retired_rules(real_repo))
    wanted_allow = [r for r in listed if r not in retired and allowed(edition.tool_of(r))]

    if "claude-code" in agents:
        claude_exe = env.which("claude")
        want_ver, _, _ = sync.claude_plugin_payloads(troot, servers)
        plug_folder = env.state / "claude-marketplace" / "plugins" / "omnikit"
        for i, d in enumerate(claude_dirs):
            lbl = "Claude Code" if i == 0 else f"Claude Code（{d.name}）"
            sp = d / "settings.json"
            try:
                sdoc = claude_allow.load(sp)
            except ValueError:
                out.append(row("權限", lbl, "settings.json", FAIL, "不是合法 JSON"))
                continue
            cur_allow = sdoc.get("permissions", {}).get("allow", [])
            missing_a = [r for r in wanted_allow if r not in cur_allow]
            zombie_a = [r for r in cur_allow if r in retired]
            custom_a = [r for r in cur_allow if r not in listed and r not in retired]
            extra_note = f"；manifest 外自訂 {len(custom_a)} 項" if custom_a else ""
            if not missing_a and not zombie_a:
                out.append(row("權限", lbl, "permissions.allow", OK, f"現行齊全、墓碑已清{extra_note}"))
            else:
                out.append(row("權限", lbl, "permissions.allow", FAIL, f"缺 {missing_a} 或殘留墓碑 {zombie_a}：跑 sync.py sync"))

            cenv = sync.claude_cli_env(env.home, d)
            if claude_exe or env.runner is not None:
                entry = sync.find_claude_plugin_entry(env, claude_exe or "claude", cenv)
                enabled_ok = entry is not None and entry.get("enabled") is True
                ver_ok = entry is not None and entry.get("version") == want_ver
                folder_ok = entry is not None and sync.same_path(Path(str(entry.get("readFromFolder") or "")), plug_folder)
                if enabled_ok and ver_ok and folder_ok:
                    out.append(row("hook/MCP", lbl, sync.PLUGIN_ID, OK, f"薄 plugin 已啟用且快取版本最新（{want_ver}）"))
                elif entry is None:
                    out.append(row("hook/MCP", lbl, sync.PLUGIN_ID, FAIL, "薄 plugin 未安裝：跑 sync.py sync"))
                elif not enabled_ok:
                    out.append(row("hook/MCP", lbl, sync.PLUGIN_ID, FAIL, "薄 plugin 已被停用（護欄未生效）：跑 sync.py sync"))
                else:
                    out.append(row("hook/MCP", lbl, sync.PLUGIN_ID, FAIL,
                                   f"薄 plugin 快取版本或路徑過期（目前 {entry.get('version')}，期望 {want_ver}）：跑 sync.py sync"))
            else:
                has_fb = any(claude_allow.is_ours(h, claude_allow.HARNESS)
                             for g in sdoc.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", []))
                out.append(row("hook", lbl, "settings.json 備案", OK if has_fb else UNKNOWN,
                               "已註冊" if has_fb else "環境無 claude CLI 無法查詢 plugin 清單"))

    if "codex" in agents:
        codex_wanted = {}
        for name, s in servers.items():
            if "codex" not in (s.get("targets") or []):
                continue
            opts = dict((s.get("options") or {}).get("codex") or {})
            if "default_tools_approval_mode" in opts and not allowed(name):
                opts.pop("default_tools_approval_mode", None)
            codex_wanted[name] = {"command": s["command"], "args": list(s.get("args") or []), **opts}

        for i, d in enumerate(codex_dirs):
            lbl = "Codex" if i == 0 else f"Codex（{d.name}）"
            toml_p = d / "config.toml"
            txt = toml_p.read_text(encoding="utf-8", errors="replace") if toml_p.is_file() else ""
            missing_h = [claude_allow.HOOK_NAMES[s] for s in CODEX_SCRIPTS if not re.search(r"(?m)^command\s*=.*" + re.escape(s), txt)]
            trust_dir = d / ".hook-trust"
            trusted = trust_dir.is_dir() and any(trust_dir.iterdir())
            if missing_h:
                out.append(row("hook", lbl, "config.toml Stop hooks", FAIL, f"缺少 {'、'.join(missing_h)}"))
            elif env.runner is None and not trusted:
                out.append(row("hook", lbl, "config.toml Stop hooks", WARN,
                               f"{len(CODEX_SCRIPTS)} 支 hook 已登記，但尚未在 Codex 輸入 /hooks 按信任（信任前不會觸發）"))
            else:
                out.append(row("hook", lbl, "config.toml Stop hooks", OK,
                               f"{len(CODEX_SCRIPTS)} 支 hook 皆已登記" + ("並已信任" if trusted else "")))
            try:
                tdoc = tomllib.loads(txt) if txt.strip() else {}
                mcps = tdoc.get("mcp_servers") or {}
                mcp_probs = []
                for mname, mspec in codex_wanted.items():
                    cur_m = mcps.get(mname)
                    if not isinstance(cur_m, dict) or cur_m.get("command") != mspec["command"]:
                        mcp_probs.append(f"{mname} 未設定或指令不符")
                        continue
                    has_opt = "default_tools_approval_mode" in (((servers[mname].get("options") or {}).get("codex")) or {})
                    if has_opt and cur_m.get("default_tools_approval_mode") != mspec.get("default_tools_approval_mode"):
                        mcp_probs.append(f"{mname} 免問核准欄位不符")
                out.append(row("MCP", lbl, "config.toml mcp_servers", FAIL if mcp_probs else OK,
                               "；".join(mcp_probs) + "：跑 sync.py sync" if mcp_probs else f"{len(codex_wanted)} 個 MCP server 一致"))
            except ValueError as e:
                out.append(row("MCP", lbl, "config.toml", FAIL, f"TOML 語法錯誤：{e}"))

    if "antigravity" in agents:
        gp = env.home / ".gemini" / "config" / "plugins" / "omnikit" / "hooks.json"
        out.append(row("hook/MCP", "Antigravity", "~/.gemini 薄 plugin", OK if gp.is_file() else FAIL,
                       "已就位" if gp.is_file() else f"缺少 {gp}：跑 sync.py sync"))
    return out


def check_t3_health(home: Path, agents: list[str]) -> list[dict]:
    """T3 專屬健康檢查（Fable 第 6 節第 7 點）：列舉實例、skills junction、規則卡住比對、實例薄 plugin。"""
    if "antigravity" not in agents or not (home / ".t3").is_dir() or not homes.t3_initialized(home):
        return []
    found_profiles, err = homes.t3_antigravity_profiles(home)
    if err:
        return [row("T3 健康", "Antigravity", "實例列舉", FAIL, err)]
    out = []
    canonical_gem = home / ".gemini"
    existing_dirs = [f for f in found_profiles if f.path.is_dir()]
    if not existing_dirs:
        return [row("T3 健康", "Antigravity", "實例目錄", OK, f"已設定 {len(found_profiles)} 個實例（尚未啟動建立目錄）")]

    for f in existing_dirs:
        pdir = f.path
        lbl = f"T3（{f.instance}）"
        slink = pdir / "config" / "skills"
        if (canonical_gem / "config" / "skills").is_dir():
            ok_j = sync.is_link(slink) and sync.same_path(sync.link_target(slink), canonical_gem / "config" / "skills")
            out.append(row("T3 健康", lbl, "config/skills junction", OK if ok_j else FAIL,
                           "指向 ~/.gemini/config/skills" if ok_j else "非連結或指錯（該實例將靜默失去全域 skills）"))
        pending, stuck = sync.t3_rule_copy_state(pdir, canonical_gem)
        if stuck:
            out.append(row("T3 健康", lbl, "規則與 skills.json 副本", FAIL,
                           f"T3 同步已卡住：{', '.join(stuck)} 與 ~/.gemini 不同、也不等於 T3 的記錄，T3 不會再自動更新"
                           f"（確認不要後刪掉該檔，下次啟動 T3 會重建）"))
        elif pending:
            out.append(row("T3 健康", lbl, "規則與 skills.json 副本", WARN,
                           f"{', '.join(pending)} 還是舊版（T3 下次啟動會刷新；現在要更新就跑 sync.py sync）"))
        else:
            out.append(row("T3 健康", lbl, "規則與 skills.json 副本", OK, "與 ~/.gemini 本尊一致"))
        hp = pdir / "config" / "plugins" / "omnikit" / "hooks.json"
        out.append(row("T3 健康", lbl, "plugins/omnikit", OK if hp.is_file() else FAIL,
                       "護欄與 MCP 薄 plugin 已就位" if hp.is_file() else "缺少薄 plugin：跑 sync.py sync"))
    return out


def check_hook_e2e_and_python(env: sync.Env, repo: Path) -> list[dict]:
    """對 harness_hooks.py 實跑餵入三種方言確認拿到 deny，並檢查實際裝入 hook 的執行檔路徑存在且非 Store stub。"""
    out = []
    py_exe = Path(sys.executable)
    is_store = "windowsapps" in str(py_exe).lower()
    out.append(row("護欄自測", "", "Python 直譯器", FAIL if is_store else OK,
                   f"{py_exe}（Microsoft Store 別名會拖慢或失效）" if is_store else str(py_exe)))

    # 檢查實際寫入薄 plugin hooks.json 的啟動程式（如 uv.exe）是否真實存在且非 WindowsApps stub
    hook_files = [
        env.state / "claude-marketplace" / "plugins" / "omnikit" / "hooks" / "hooks.json",
        env.home / ".gemini" / "config" / "plugins" / "omnikit" / "hooks.json",
    ]
    checked_exes: set[str] = set()
    bad_exes: list[str] = []
    for hf in hook_files:
        if not hf.is_file():
            continue
        for m in re.finditer(r'"command"\s*:\s*"((?:\\.|[^"\\])*)"', hf.read_text("utf-8", errors="replace")):
            cmd_str = json.loads(f'"{m.group(1)}"')
            em = QUOTED_EXE_RE.match(cmd_str)
            if not em:
                continue
            exe_raw = em.group(1)
            checked_exes.add(exe_raw)
            resolved_exe = shutil.which(exe_raw) if "/" not in exe_raw and "\\" not in exe_raw else (exe_raw if Path(exe_raw).is_file() else None)
            if not resolved_exe or "windowsapps" in str(resolved_exe).lower():
                bad_exes.append(exe_raw)
    if checked_exes:
        out.append(row("護欄自測", "", "已安裝 hook 執行檔路徑", FAIL if bad_exes else OK,
                       f"找不到或為 Store 別名：{', '.join(sorted(set(bad_exes)))}" if bad_exes else f"已驗證 {', '.join(sorted(checked_exes))} 存在可用"))

    harness = repo / "engine" / "scripts" / "harness_hooks.py"
    dialects = [
        ("Claude Code 方言", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
         lambda d: (d.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"),
        ("通用 snake_case 方言", {"hook_event_name": "PreToolUse", "tool_name": "PowerShell", "tool_input": {"command": "Get-Content .env"}},
         lambda d: (d.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"),
        ("Antigravity 方言", {"hookEventName": "PreToolUse", "toolCall": {"name": "run_command", "args": {"CommandLine": "git push --no-verify"}}},
         lambda d: d.get("decision") == "deny"),
    ]
    t0 = time.monotonic()
    e2e_env = {**os.environ, "OMNIKIT_TRIPWIRE_LOG": "off"}
    for dname, payload, verifier in dialects:
        try:
            r = subprocess.run([sys.executable, str(harness)], input=json.dumps(payload).encode("utf-8"),
                               capture_output=True, timeout=10, check=False, env=e2e_env)
            parsed = json.loads(r.stdout.decode("utf-8") or "{}")
            passed = r.returncode == 0 and verifier(parsed)
            out.append(row("護欄自測", dname, "PreToolUse deny 端到端", OK if passed else FAIL,
                           "成功攔截假危險指令" if passed else f"未攔截：rc={r.returncode} out={r.stdout[:120]!r}"))
        except Exception as e:  # noqa: BLE001
            out.append(row("護欄自測", dname, "PreToolUse deny 端到端", FAIL, str(e)[:160]))
    elapsed_ms = int((time.monotonic() - t0) * 1000 / len(dialects))
    out.append(row("護欄自測", "", "單次啟動延遲", OK if elapsed_ms < 3000 else FAIL, f"平均約 {elapsed_ms} ms"))
    return out


def check_repo_invariants(repo: Path) -> list[dict]:
    """檢查 SKILL.md 規範、MCP 無寫死密鑰、以及同步器原始碼零遞迴刪除。"""
    out = []
    forbidden = "rm" + "tree"
    scripts_dir = Path(__file__).resolve().parent
    bad_rec_del = [fn for fn in ("sync.py", "doctor.py") if (scripts_dir / fn).is_file() and forbidden in (scripts_dir / fn).read_text("utf-8")]
    out.append(row("防呆規範", "", "零遞迴刪除", FAIL if bad_rec_del else OK,
                   f"{', '.join(bad_rec_del)} 出現禁用遞迴刪除" if bad_rec_del else "sync.py 與 doctor.py 無遞迴刪除"))

    skills_root = (repo / "engine" / "skills").resolve()
    skill_probs = []
    if skills_root.is_dir():
        for sd in sorted(skills_root.iterdir()):
            if not sd.is_dir():
                continue
            sm = sd / "SKILL.md"
            if not sm.is_file():
                continue
            raw = sm.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                skill_probs.append(f"{sd.name}: 含 UTF-8 BOM")
            txt = raw.decode("utf-8-sig")
            parts = txt.split("---", 2)
            fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
            if not isinstance(fm, dict) or fm.get("name") != sd.name or not str(fm.get("description") or "").strip():
                skill_probs.append(f"{sd.name}: name 與目錄不符或缺 description")
            for md in sd.rglob("*.md"):
                for target in REL_LINK_RE.findall(md.read_text("utf-8", errors="replace")):
                    if ".." in target and not target.startswith(("http://", "https://", "#")):
                        resolved = (md.parent / target.split("#")[0]).resolve()
                        if not str(resolved).startswith(str(skills_root)):
                            skill_probs.append(f"{sd.name}/{md.name}: 相對連結穿出 skills 目錄 ({target})")
    out.append(row("防呆規範", "", "SKILL.md 格式與邊界", FAIL if skill_probs else OK,
                   "；".join(skill_probs[:4]) if skill_probs else "目錄名、description、無 BOM、相對路徑皆合規"))

    try:
        sync.load_mcp_manifest(repo)
        out.append(row("防呆規範", "", "MCP 無密鑰檢查", OK, "servers.yaml 未寫死 env 密鑰"))
    except SystemExit as e:
        out.append(row("防呆規範", "", "MCP 無密鑰檢查", FAIL, str(e.code)))

    import validate
    gov_errs = (
        validate.check_patches(repo / "data")
        + validate.check_review_markers(repo / "data")
        + validate.check_baseline_eval_docs(repo / "data")
    )
    b_errs, b_stats = validate.check_budget(repo / "data", skills_root if skills_root.is_dir() else None)
    all_b_errs = gov_errs + b_errs
    if all_b_errs or b_stats:
        if all_b_errs:
            b_detail = "；".join(all_b_errs[:3])
        else:
            lim = b_stats["limits"]
            b_detail = (
                f"共用 {b_stats['shared_bytes']:,}/{lim['antigravity_shared_max_bytes']:,}B、"
                f"Codex {b_stats['max_codex_bytes']:,}/{lim['codex_combined_max_bytes']:,}B、"
                f"自動 skill 描述 {b_stats['auto_skill_desc_bytes']:,}/{lim['auto_skill_desc_max_bytes']:,}B"
            )
        out.append(row("防呆規範", "", "常駐預算棘輪", FAIL if all_b_errs else OK, b_detail))

    gov = validate.governance_status(repo / "data")
    due_parts = (
        [f"試用到期 {t}({d})" for t, d in gov["expired_trials"]]
        + [f"規則檢討 {loc}({d})" for loc, d, _ in gov["due_reviews"]]
    )
    soon_n = len(gov["upcoming_trials"]) + len(gov["upcoming_reviews"])
    unv_n = len(gov["unverified_defaults"])
    if due_parts:
        g_detail = f"注意：{len(due_parts)} 項已到期需結算（{'、'.join(due_parts[:4])}）；未驗裸模型 default 卡 {unv_n} 張"
    else:
        g_detail = f"無過期項目（待到期追蹤 {soon_n} 項、待補裸模型對照 default 卡 {unv_n} 張）"
    out.append(row("自我迭代", "", "到期與世代錨點體檢", OK, g_detail))
    return out


def check_tripwire_stats(state: Path) -> list[dict]:
    """彙總 ~/.omnikit/harness/tripwire-hits.jsonl 的護欄絆線命中紀錄（含近 30 天與累計，對話內不跨目錄讀檔）。"""
    from datetime import UTC, datetime, timedelta
    hits_file = state / "harness" / "tripwire-hits.jsonl"
    if not hits_file.is_file():
        return [row("自我迭代", "", "護欄絆線命中計數", OK, "尚無攔截紀錄（檔案將於首次真實攔截時自動建立）")]
    cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts: dict[str, int] = {}
    recent = 0
    total = 0
    for line in hits_file.read_text("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            if not isinstance(d, dict):
                continue
            key = f"{d.get('hook', '?')}:{d.get('rule', '?')}"
            counts[key] = counts.get(key, 0) + 1
            total += 1
            if str(d.get("ts") or "") >= cutoff:
                recent += 1
        except ValueError:
            continue
    top = "、".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
    detail = f"近 30 天 {recent} 次／累計 {total} 次（{top}）" if total else "累計 0 次"
    return [row("自我迭代", "", "護欄絆線命中計數", OK, detail)]


def preflight(run=subprocess.run) -> list[dict]:
    script = Path(__file__).with_name("preflight.ps1")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        return [row("安裝前", "", "preflight.ps1", UNKNOWN, "找不到 PowerShell")]
    try:
        r = run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Json"], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=180, stdin=subprocess.DEVNULL)
        text = r.stdout or ""
        items = json.loads(text[text.index("["):])
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return [row("安裝前", "", "preflight.ps1", UNKNOWN, str(e)[:200])]
    return [row("安裝前", "", i["name"], OK if i["ok"] else FAIL) for i in items]


def collect(env: sync.Env, lists: bool = True, pre: bool = False, run=subprocess.run, environ: dict | None = None) -> list[dict]:
    import statedir
    environ = (None if env.home == homes.HOME else {}) if environ is None else environ
    state_rows = [row("狀態", "", item, OK if ok else FAIL, detail) for ok, item, detail in statedir.report(env.state, environ)]
    cfg = sync.load_config(env.state)
    agents = sync.active_agents(env)
    has_any_block = any(
        p.is_file() and profiles.BLOCK.search(profiles.text(p))
        for p in (env.home / ".claude" / "CLAUDE.md", env.home / ".codex" / "AGENTS.md", env.home / ".gemini" / "GEMINI.md")
    )
    if not cfg.get("agents") and not has_any_block:
        legacy = any(r["status"] == FAIL for r in state_rows)
        return [row("記錄", "", "連線狀態", FAIL,
                    "舊位置的狀態還沒合併過來：跑 uv run engine/scripts/sync.py sync" if legacy
                    else "這台還沒接上 OmniKit：跑 install.ps1 或 uv run engine/scripts/sync.py connect")] + state_rows

    found = homes.discover(env.home, environ)
    claude_dirs = [env.home / ".claude", *[f.path for f in found if f.agent == "claude-code" and f.writable]]
    codex_dirs = [env.home / ".codex", *[f.path for f in found if f.agent == "codex" and f.writable]]

    rows = []
    rows += check_current_clone(env)
    rows += check_rules(env, agents, claude_dirs, codex_dirs)
    rows += check_skills(env, agents, claude_dirs, codex_dirs)
    rows += check_permissions_and_hooks(env, agents, claude_dirs, codex_dirs)
    rows += check_t3_health(env.home, agents)
    rows += check_hook_e2e_and_python(env, sync.ROOT)
    rows += check_repo_invariants(sync.resolve_real_repo(env.repo, env.state))
    rows += check_tripwire_stats(env.state)
    rows += state_rows
    if pre:
        rows += preflight(run)
    return rows


def report(rows: list[dict]) -> list[str]:
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in (OK, WARN, FAIL, UNKNOWN)}
    lines = [f"# OmniKit doctor：通過 {counts[OK]}、警告 {counts[WARN]}、失敗 {counts[FAIL]}、未知 {counts[UNKNOWN]}"
             f"（警告與未知都不算通過）", ""]
    for r in rows:
        who = f"{r['agent']}／" if r["agent"] else ""
        lines.append(f"{MARK[r['status']]} {r['area']}：{who}{r['item']}" + (f"（{r['detail']}）" if r["detail"] else ""))
    return lines


def selftest() -> int:
    checks = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        home, repo, state = base / "home", base / "repo", base / "state"
        for d in (home / ".claude", home / ".codex", home / ".gemini" / "config" / "skills"):
            d.mkdir(parents=True)
        (repo / "data" / "rules").mkdir(parents=True)
        (repo / "data" / "rules" / "baseline.md").write_text("# 底線\n不碰金鑰\n", encoding="utf-8")
        (repo / "data" / "profiles" / "default").mkdir(parents=True)
        (repo / "data" / "profiles" / "default" / "AGENTS.md").write_text("# default\n保守\n", encoding="utf-8")
        (repo / "data" / "harness").mkdir(parents=True)
        (repo / "data" / "harness" / "claude-allow.txt").write_text("mcp__devtools\n", encoding="utf-8")
        (repo / "data" / "harness" / "claude-allow-retired.txt").write_text("mcp__retired\n", encoding="utf-8")
        for sname in ("omnikit-alpha", "ok-alpha"):
            sd = repo / "engine" / "skills" / sname
            sd.mkdir(parents=True)
            (sd / "SKILL.md").write_text(f"---\nname: {sname}\ndescription: {sname} desc\n---\n", encoding="utf-8")
        (repo / "data" / "mcp").mkdir(parents=True)
        (repo / "data" / "mcp" / "servers.yaml").write_text(
            "servers:\n  devtools:\n    command: cmd\n    args: [/c, echo, x]\n    targets: [claude, codex, antigravity]\n",
            encoding="utf-8",
        )
        t3_s = home / ".t3" / "userdata" / "settings.json"
        t3_s.parent.mkdir(parents=True)
        t3_s.write_text(json.dumps({"providerInstances": {"antigravity": {"driver": "antigravity"}}}), encoding="utf-8")
        inst_d = homes.t3_antigravity_dir(home, "antigravity")
        (inst_d / "config").mkdir(parents=True)
        sync.make_dir_link(home / ".gemini" / "config" / "skills", inst_d / "config" / "skills")

        edition.set_edition(state, "maintainer")
        plugin_enabled = [True]

        def fake_runner(cmd, env_map):
            if cmd[0] == "claude":
                if cmd[1:4] == ["plugin", "list", "--json"]:
                    pjson = state / "claude-marketplace" / "plugins" / "omnikit" / ".claude-plugin" / "plugin.json"
                    if not pjson.is_file():
                        return 0, "[]", ""
                    ver = json.loads(pjson.read_text("utf-8"))["version"]
                    return 0, json.dumps([
                        {"id": "other@builtin", "enabled": True, "version": "1.0.0"},
                        {"id": sync.PLUGIN_ID, "enabled": plugin_enabled[0], "version": ver,
                         "readFromFolder": str(state / "claude-marketplace" / "plugins" / "omnikit")},
                    ]), ""
                return 0, '{"outcome":"ok"}', ""
            if cmd[0] == "codex":
                ch = env_map.get("CODEX_HOME") or str(home / ".codex")
                if cmd[1:3] == ["mcp", "list"]:
                    return 0, json.dumps([{"name": "devtools", "enabled": True, "transport": {"command": "cmd", "args": ["/c", "echo", "x"]}}]), ""
                if cmd[1:3] == ["mcp", "add"]:
                    toml_p = Path(ch) / "config.toml"
                    prev = toml_p.read_text("utf-8") if toml_p.is_file() else ""
                    if "[mcp_servers.devtools]" not in prev:
                        toml_p.write_text(prev + '\n[mcp_servers.devtools]\ncommand = "cmd"\nargs = ["/c", "echo", "x"]\n', encoding="utf-8")
            return 0, '{"outcome":"ok"}', ""

        env = sync.Env(home=home, repo=repo, state=state, which=lambda n: sys.executable if n == "uv" else (n if n in ("claude", "codex", "agy") else None),
                       runner=fake_runner, environ={})
        os.environ["UV"] = sys.executable
        sync.run_sync(env, profile="default", agents_override=["claude-code", "codex", "antigravity"], take_over=True)
        # 補齊 fake runner 的 codex config.toml MCP 表格（因 fake list 一開始就回傳已存在）
        ctoml = home / ".codex" / "config.toml"
        ctoml.write_text(ctoml.read_text("utf-8") + '\n[mcp_servers.devtools]\ncommand = "cmd"\nargs = ["/c", "echo", "x"]\n', encoding="utf-8")

        rows = collect(env, lists=False, environ={})
        check("無帳本同步完成後 doctor 全部項目通過（含三方言 hook 端到端自測、實際執行檔與 T3 健康檢查）",
              all(r["status"] == OK for r in rows))

        # B2 驗證：即使內建其他 plugin 為 enabled，只要 omnikit@omnikit-local 被停用，doctor 立即抓出 FAIL
        plugin_enabled[0] = False
        rows_disabled = collect(env, lists=False, environ={})
        check("B2 防護：薄 plugin 被停用時（即使其他內建 plugin enabled），doctor 精準判為 FAIL",
              any(r["item"] == sync.PLUGIN_ID and r["status"] == FAIL for r in rows_disabled))
        plugin_enabled[0] = True

        # T3 實例的規則副本（KIT-B-04、KIT-X-02：驗狀態，不只驗訊息文字）。T3 每次啟動實例時，只有副本等於
        # 它上次記在 .t3-rule-copies.json 的內容才會刷新；不等於就當作實例自己改過，之後永遠不再更新
        def t3_row(rows):
            return next(r for r in rows if r["area"] == "T3 健康" and r["item"] == "規則與 skills.json 副本")

        gem_agents = (home / ".gemini" / "AGENTS.md").read_text(encoding="utf-8")
        (inst_d / "AGENTS.md").write_bytes("舊版規則\n".encode("utf-8"))
        (inst_d / ".t3-rule-copies.json").write_text(json.dumps({"AGENTS.md": "舊版規則\n"}), encoding="utf-8")
        r_pending = t3_row(collect(env, lists=False, environ={}))
        check("T3 副本是舊版但 T3 認得（等於記錄）：判 WARN（下次啟動會刷新），不是通過",
              r_pending["status"] == WARN and "AGENTS.md" in r_pending["detail"])
        check("摘要行把警告數出來", any(line.startswith("# OmniKit doctor：") and "警告 1" in line
                                       for line in report([r_pending])))
        sync.refresh_t3_rule_copies(home)
        check("sync 照 T3 的規則刷新認得的舊副本並更新記錄，doctor 回到通過",
              (inst_d / "AGENTS.md").read_text(encoding="utf-8") == gem_agents
              and json.loads((inst_d / ".t3-rule-copies.json").read_text(encoding="utf-8"))["AGENTS.md"] == gem_agents
              and t3_row(collect(env, lists=False, environ={}))["status"] == OK)
        (inst_d / "AGENTS.md").write_text("手改過\n", encoding="utf-8")
        rows_stuck = collect(env, lists=False, environ={})
        check("T3 副本被改過（不等於記錄）：判 FAIL，T3 不會再自動更新",
              t3_row(rows_stuck)["status"] == FAIL and "T3 同步已卡住" in t3_row(rows_stuck)["detail"])
        sync.refresh_t3_rule_copies(home)
        check("sync 不覆蓋被改過的副本（由使用者決定）", (inst_d / "AGENTS.md").read_text(encoding="utf-8") == "手改過\n")
        (inst_d / "AGENTS.md").unlink()
        (inst_d / ".t3-rule-copies.json").unlink()

        # 模擬刪除 Codex skill junction 與塞回墓碑權限 -> doctor 抓出 FAIL
        sync.remove_dir_link(home / ".codex" / "skills" / "omnikit-alpha")
        s_doc = claude_allow.load(home / ".claude" / "settings.json")
        s_doc["permissions"]["allow"].append("mcp__retired")
        claude_allow.save(home / ".claude" / "settings.json", s_doc)
        rows_bad = collect(env, lists=False, environ={})
        st_bad = {(r["area"], r["agent"]): r["status"] for r in rows_bad if r["status"] == FAIL}
        check("skill junction 遺失與墓碑權限殘留皆被 doctor 判為 FAIL",
              ("skills", "Codex") in st_bad and ("權限", "Claude Code") in st_bad)

        # 未接上的全新環境 -> 提示 install.ps1；若有舊狀態未合併 -> 提示 sync.py sync
        empty = sync.Env(home=base / "nohome", repo=repo, state=base / "nostate", environ={})
        check("未接上環境直接提示 install.ps1", collect(empty, lists=False, environ={})[0]["status"] == FAIL)
        local = base / "AppData" / "Local"
        (local / "Packages" / "Claude_x" / "LocalCache" / "Local" / "omnikit").mkdir(parents=True)
        (local / "Packages" / "Claude_x" / "LocalCache" / "Local" / "omnikit" / "install-record.json").write_text("{}", encoding="utf-8")
        first = collect(empty, lists=False, environ={"LOCALAPPDATA": str(local)})
        check("舊位置有未合併狀態時判 FAIL 並提示合併", first[0]["status"] == FAIL and "sync.py sync" in first[0]["detail"])

        # 預算棘輪測試：寫入過低的 budget.yaml 時 doctor 必須判 FAIL
        (repo / "data" / "rules" / "budget.yaml").write_text(
            "schema_version: 1\nupdated_at: '2026-11-26'\nlimits:\n"
            "  antigravity_shared_max_bytes: 10\n  antigravity_personal_max_bytes: 1000\n"
            "  codex_combined_max_bytes: 1000\n  auto_skill_desc_max_bytes: 1000\n",
            encoding="utf-8",
        )
        rows_over = collect(env, lists=False, environ={})
        check("常駐預算棘輪超標時 doctor 精準判為 FAIL",
              any(r["item"] == "常駐預算棘輪" and r["status"] == FAIL for r in rows_over))

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"doctor 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OmniKit doctor：無帳本對帳與端到端健康檢查")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--no-lists", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.selftest:
        return selftest()
    env = sync.real_env()
    rows = collect(env, lists=not args.no_lists, pre=args.preflight)
    print(json.dumps(rows, ensure_ascii=False, indent=1) if args.json else "\n".join(report(rows)))
    return 1 if any(r["status"] == FAIL for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
