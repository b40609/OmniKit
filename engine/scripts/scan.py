# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 掃描：列出這台電腦的 agent 環境，給 omnikit-setup 訪談用。輸出 JSON。

只看存在與否、名稱與版本：不輸出金鑰、token、環境變數的值，規則檔只算行數、不輸出內容，
MCP 只列名稱。版本號是執行各工具的 --version 拿到的；agent 本身不執行，只看設定目錄與 PATH。

另外列出名冊的領域（訪談第 1 題的選項），並依線索預選：專案資料夾裡的檔名（只看檔名，不讀內容）、
上次訪談寫的背景、上次選過的領域。預選只是建議，使用者可以改。

用法：
  uv run engine/scripts/scan.py [--project <專案資料夾>]
  uv run engine/scripts/scan.py --selftest
"""
import argparse
import fnmatch
import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402  這台選的 profile
import validate  # noqa: E402  讀模組檔

# OmniKit 接得上的 agent（agents.py 會設定的）；其他的只回報有沒有裝
SUPPORTED = {"claude-code", "codex", "antigravity"}

# id、名稱、設定目錄（相對家目錄，任一個存在就算）、指令（任一個在 PATH 上就算）
AGENTS = [
    ("claude-code", "Claude Code", (".claude",), ("claude",)),
    ("codex", "Codex", (".codex",), ("codex",)),
    ("antigravity", "Antigravity", (".gemini/config", ".gemini/antigravity"), ("agy", "antigravity")),
    ("gemini-cli", "Gemini CLI", (".gemini",), ("gemini",)),
    ("copilot-cli", "GitHub Copilot CLI", (".copilot",), ("copilot",)),
    ("cursor", "Cursor", (".cursor",), ("cursor",)),
    ("windsurf", "Windsurf", (".codeium/windsurf",), ("windsurf",)),
    ("opencode", "OpenCode", (".config/opencode",), ("opencode",)),
    ("kiro", "Kiro", (".kiro",), ("kiro",)),
]

# 各 agent 的全域規則檔（相對家目錄）；Antigravity 與 Gemini CLI 共用 GEMINI.md
RULES = {"claude-code": ".claude/CLAUDE.md", "codex": ".codex/AGENTS.md", "antigravity": ".gemini/GEMINI.md",
         "gemini-cli": ".gemini/GEMINI.md"}

# 各 agent 讀的全域 skills 資料夾（相對家目錄）；~/.agents/skills 是 Codex 與 Antigravity 共用的
SKILLS = {"claude-code": [".claude/skills"], "codex": [".agents/skills", ".codex/skills"],
          "antigravity": [".gemini/config/skills", ".agents/skills"]}

TOOLS = ["git", "node", "uv", "gh", "pwsh"]

GENERIC_USERS = {"user", "admin", "administrator", "owner", "pc", "default"}


def run_version(path, *args):
    """執行指令拿版本，回傳（第一行輸出, 錯誤）。"""
    try:
        r = subprocess.run([str(path), *(args or ("--version",))], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e).rstrip("。")
    if r.returncode != 0:
        return None, f"exit {r.returncode}"
    lines = (r.stdout or r.stderr).strip().splitlines()
    return (lines[0].strip()[:100] if lines else ""), None


def git_user_name(which=shutil.which, run=run_version):
    git = which("git")
    if not git:
        return None
    name, _ = run(git, "config", "--global", "user.name")
    return name or None


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:30].strip("-")


def suggest_name(git_name, login, taken):
    """profile 名稱建議：git 的名字或登入帳號轉成小寫英數；太通用或撞到現有的就不建議。"""
    for raw in (git_name, login):
        s = slug(raw)
        if s and s not in GENERIC_USERS and s not in taken and profiles.NAME.match(s):
            return s
    return None


def names_in(folder):
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def mcp_names(agent, home):
    """只回傳 MCP server 名稱；檔案壞了回傳錯誤說明，不丟例外。"""
    try:
        if agent == "claude-code":
            path = home / ".claude.json"
            return sorted(json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})) if path.exists() else []
        if agent == "codex":
            path = home / ".codex" / "config.toml"
            return sorted(tomllib.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {})) if path.exists() else []
        if agent in ("antigravity", "gemini-cli"):
            rel = "config/mcp_config.json" if agent == "antigravity" else "settings.json"
            path = home / ".gemini" / rel
            return sorted(json.loads(path.read_bytes().decode("utf-8-sig")).get("mcpServers", {})) if path.exists() else []
    except (OSError, ValueError, tomllib.TOMLDecodeError, AttributeError):
        return {"error": "讀不到或格式不對"}
    return None


def rules_info(path):
    if not path.is_file():
        return {"path": str(path), "exists": False}
    text = path.read_bytes().decode("utf-8-sig", errors="replace")
    return {
        "path": str(path),
        "exists": True,
        "lines": len(text.splitlines()),
        "omnikit": "omnikit:rules:begin" in text or "由 OmniKit 產生" in text,
    }


SKIP_DIRS = {"node_modules", "__pycache__", "venv", "dist", "build", "target"}
MAX_NAMES = 5000  # 專案很大時只看前面這麼多個檔名


def project_names(project):
    """專案資料夾裡的檔名：最上層與往下兩層，略過 . 開頭與套件資料夾。只回檔名，不讀內容。"""
    names = []
    if not project or not Path(project).is_dir():
        return names
    root = Path(project)
    for folder, dirs, files in os.walk(root):
        depth = len(Path(folder).relative_to(root).parts)
        dirs[:] = [] if depth >= 2 else [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        names += files
        if len(names) >= MAX_NAMES:
            break
    return names[:MAX_NAMES]


def domain_options(data, project=None, previous=None):
    """訪談第 1 題的選項：名冊的每個領域，加上預選的依據。上次選過的照舊；沒選過才看專案的檔名與背景的關鍵字。"""
    previous = previous or {}
    before = previous.get("domains") or []
    names = [n.lower() for n in project_names(project)]
    text = str(previous.get("background") or "").lower()
    out = []
    for m in validate.load_modules(data)[1]:
        if m["kind"] != "domain":
            continue
        signals = m.get("signals") or {}
        why = ["上次選過"] if m["id"] in before else []
        if not before:
            hits = [p for p in signals.get("files", []) if any(fnmatch.fnmatch(n, p.lower()) for n in names)]
            words = [k for k in signals.get("keywords", []) if k.lower() in text]
            why += [f"專案裡有 {'、'.join(hits[:3])}"] if hits else []
            why += [f"上次寫的背景提到「{'、'.join(words[:3])}」"] if words else []
        out.append({"id": m["id"], "name": m["name"], "summary": m["summary"], "suggested": bool(why), "why": why})
    return out


def omnikit_state(data, state, tracked=None):
    available = profiles.available(data, state)
    chosen = profiles.chosen(state)
    current = chosen if chosen in available else profiles.DEFAULT
    try:
        connected = json.loads((state / "agents.json").read_text(encoding="utf-8")).get("agents", [])
    except (OSError, ValueError, AttributeError):
        connected = []
    return {
        "root": str(data.parent),
        "profile": current,
        "profile_chosen": chosen is not None,
        "profiles": available,
        # 訪談產生的 profile 存在這裡（repo 外，FR-38）
        "profiles_dir": str(state / "profiles"),
        # 舊版存在 repo 裡的 profile：訪談前先問使用者要不要搬到 repo 外（profiles.py --migrate）
        "legacy_profiles": profiles.legacy(data, tracked),
        "connected_agents": connected,
        "answers_file": str(state / "setup-answers.json"),
        "previous_answers": profiles.answers(data, state, current),
    }


def scan(home, data, state, which=shutil.which, run=run_version, login=None, git_name=None, tracked=None, project=None):
    agents = []
    for agent_id, name, folders, commands in AGENTS:
        evidence = [f"~/{f}" for f in folders if (home / f).is_dir()]
        evidence += [f"{c} 在 PATH 上" for c in commands if which(c)]
        entry = {"id": agent_id, "name": name, "found": bool(evidence), "evidence": evidence,
                 "omnikit_supported": agent_id in SUPPORTED}
        if evidence:
            if agent_id in RULES:
                entry["rules"] = rules_info(home / RULES[agent_id])
            if agent_id in SKILLS:
                entry["skills"] = sorted({n for d in SKILLS[agent_id] for n in names_in(home / d)})
            mcp = mcp_names(agent_id, home)
            if mcp is not None:
                entry["mcp"] = mcp
        agents.append(entry)

    tools = {}
    for tool in TOOLS:
        path = which(tool)
        version, error = run(path) if path else (None, None)
        tools[tool] = {"found": bool(path), "version": version, **({"error": error} if error else {})}

    omnikit = omnikit_state(data, state, tracked)
    # 訪談第 1 題的選項與預選；project 是使用者現在的專案資料夾（沒給就只看上次的答案）
    omnikit["domains"] = domain_options(data, project, omnikit["previous_answers"])
    return {
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version()},
        "suggested_profile": suggest_name(git_name, login or getpass.getuser(), set(omnikit["profiles"])),
        "omnikit": omnikit,
        "agents": agents,
        "tools": tools,
    }


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home, data, state = tmp / "home", tmp / "repo" / "data", tmp / "state"

        def write(path, text):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        write(home / ".claude" / "CLAUDE.md", "<!-- omnikit:rules:begin -->\n@x\n<!-- omnikit:rules:end -->\n# 我的\n")
        (home / ".claude" / "skills" / "caveman").mkdir(parents=True)
        (home / ".claude" / "skills" / ".hidden").mkdir(parents=True)
        write(home / ".claude.json", json.dumps({"mcpServers": {"m1": {"env": {"TOKEN": "s3cret-claude"}}}}))
        write(home / ".codex" / "config.toml",
              '[mcp_servers.m2]\ncommand = "x"\n[mcp_servers.m2.env]\nKEY = "s3cret-codex"\n')
        (home / ".agents" / "skills" / "okx").mkdir(parents=True)
        (home / ".gemini" / "config" / "skills" / "search-first").mkdir(parents=True)
        write(home / ".gemini" / "config" / "mcp_config.json", '﻿{"mcpServers": {"m3": {"command": "x"}}}')
        write(home / ".gemini" / "GEMINI.md", "# 共用的規則\n")
        write(home / ".gemini" / "settings.json", "{壞掉的 JSON")
        write(data / "profiles" / "default" / "AGENTS.md", "# default\n")
        write(data / "profiles" / "ryan" / "AGENTS.md", "# ryan\n")
        write(data / "profiles" / "ryan" / "answers.json", '{"name": "ryan"}')

        paths = {"git": "/bin/git", "claude": "/bin/claude", "node": "/bin/node"}

        def fake_run(path, *args):
            return ("v22.0.0", None) if "node" in str(path) else ("git version 2.50", None)

        result = scan(home, data, state, which=paths.get, run=fake_run, login="user", git_name="Kai Chen")
        text = json.dumps(result, ensure_ascii=False)
        by_id = {a["id"]: a for a in result["agents"]}

        check("找到 Claude Code（設定目錄與 PATH）", by_id["claude-code"]["evidence"] == ["~/.claude", "claude 在 PATH 上"])
        check("找到 Codex、Antigravity 與 Gemini CLI",
              by_id["codex"]["found"] and by_id["antigravity"]["found"] and by_id["gemini-cli"]["found"])
        check("沒裝的 agent 標成沒找到", not by_id["cursor"]["found"] and "skills" not in by_id["cursor"])
        check("標出 OmniKit 接得上的 agent：Claude Code、Codex、Antigravity",
              all(by_id[a]["omnikit_supported"] for a in ("claude-code", "codex", "antigravity"))
              and not by_id["gemini-cli"]["omnikit_supported"])
        check("Antigravity：skills 含共用的 ~/.agents/skills，MCP 讀 config/mcp_config.json（有 BOM 也讀得到）",
              by_id["antigravity"]["skills"] == ["okx", "search-first"] and by_id["antigravity"]["mcp"] == ["m3"]
              and by_id["antigravity"]["rules"]["exists"])
        check("規則檔只回報行數與 OmniKit 標記",
              by_id["claude-code"]["rules"]["lines"] == 4 and by_id["claude-code"]["rules"]["omnikit"])
        check("skills 只列名稱，略過 . 開頭", by_id["claude-code"]["skills"] == ["caveman"]
              and by_id["codex"]["skills"] == ["okx"])
        check("MCP 只列名稱", by_id["claude-code"]["mcp"] == ["m1"] and by_id["codex"]["mcp"] == ["m2"])
        check("設定檔壞掉時回報錯誤，不中斷", by_id["gemini-cli"]["mcp"] == {"error": "讀不到或格式不對"})
        check("不輸出金鑰的值", "s3cret" not in text)
        check("工具版本", result["tools"]["node"]["version"] == "v22.0.0" and not result["tools"]["uv"]["found"])
        check("不再檢查 skillshare", "skillshare" not in result["tools"])
        check("建議的 profile 名稱來自 git 名字", result["suggested_profile"] == "kai-chen")
        check("沒選過 profile：目前是 default", result["omnikit"]["profile"] == "default"
              and not result["omnikit"]["profile_chosen"] and result["omnikit"]["profiles"] == ["default", "ryan"])
        check("中文名字與通用帳號不建議", suggest_name("鄭逸民", "user", set()) is None)
        check("撞到現有 profile 就改用登入帳號", suggest_name("Ryan", "alice", {"ryan"}) == "alice")

        write(state / "profile.json", '{"profile": "ryan"}')
        write(state / "agents.json", '{"agents": ["claude-code", "antigravity"]}')
        again = scan(home, data, state, which=paths.get, run=fake_run, login="user", git_name=None)
        check("選過 profile：帶出上次的訪談答案", again["omnikit"]["profile"] == "ryan"
              and again["omnikit"]["previous_answers"] == {"name": "ryan"})
        check("列出已經接上的 agent", again["omnikit"]["connected_agents"] == ["claude-code", "antigravity"])
        check("舊版存在 repo 裡的訪談 profile（有 answers.json、沒進版本控制）：列出來，訪談前問要不要搬",
              again["omnikit"]["legacy_profiles"] == ["ryan"]
              and scan(home, data, state, which=paths.get, run=fake_run, login="user",
                       tracked={"default", "ryan"})["omnikit"]["legacy_profiles"] == [])

        # 訪談產生的 profile 存在 repo 外（FR-38）
        write(state / "profiles" / "alice" / "AGENTS.md", "# alice\n")
        write(state / "profiles" / "alice" / "answers.json", '{"name": "alice", "evaluate_tools": false}')
        write(state / "profile.json", '{"profile": "alice"}')
        local = scan(home, data, state, which=paths.get, run=fake_run, login="alice", git_name=None, tracked=set())
        check("repo 外的 profile：列在可選的裡，選了它就帶出它的答案",
              local["omnikit"]["profiles"] == ["alice", "default", "ryan"] and local["omnikit"]["profile"] == "alice"
              and local["omnikit"]["previous_answers"] == {"name": "alice", "evaluate_tools": False}
              and local["omnikit"]["profiles_dir"] == str(state / "profiles"))
        check("建議的名稱不撞 repo 外已經有的", local["suggested_profile"] is None)

        # 訪談第 1 題：領域的選項與預選
        write(data / "modules" / "domain" / "dev.yaml", "id: dev\nkind: domain\nname: 軟體開發\nsummary: 寫程式\n"
              "signals:\n  files: ['package.json', '*.csproj']\n  keywords: [前端, API]\n"
              "slots:\n  - id: s1\n    name: 槽位\n    focus: watch\n    scenarios:\n      - {id: A1, text: 情境}\n")
        write(data / "modules" / "domain" / "data.yaml", "id: data\nkind: domain\nname: 數據分析\nsummary: 分析資料\n"
              "signals:\n  files: ['*.ipynb']\n  keywords: [量測]\n"
              "slots:\n  - id: s2\n    name: 槽位\n    focus: watch\n    scenarios:\n      - {id: B1, text: 情境}\n")
        write(data / "modules" / "foundation" / "ops.yaml", "id: ops\nkind: foundation\nname: 基礎\nsummary: 每個人都有\n"
              "slots:\n  - id: s3\n    name: 槽位\n    focus: watch\n    scenarios:\n      - {id: C1, text: 情境}\n")
        project = tmp / "proj"
        write(project / "web" / "package.json", "{}")
        write(project / "node_modules" / "x" / "notes.ipynb", "秘密內容")
        write(project / "a" / "b" / "c" / "deep.ipynb", "{}")
        options = {d["id"]: d for d in domain_options(data, project)}
        check("領域選項：只列領域模組，附名稱與一句說明", list(options) == ["data", "dev"] and options["dev"]["name"] == "軟體開發")
        check("預選：專案裡有對得上的檔名就預選並寫出依據；套件資料夾與太深的不看",
              options["dev"]["suggested"] and options["dev"]["why"] == ["專案裡有 package.json"] and not options["data"]["suggested"])
        check("預選：上次寫的背景有關鍵字也算", domain_options(data, None, {"background": "量測資料處理"})[0]["why"] == ["上次寫的背景提到「量測」"])
        again = {d["id"]: d for d in domain_options(data, project, {"domains": ["data"], "background": "前端"})}
        check("預選：上次選過領域就照上次的，不再用檔名或背景猜", again["data"]["why"] == ["上次選過"] and not again["dev"]["suggested"])
        check("沒給專案資料夾、也沒有上次的答案：照樣列出，都不預選", not any(d["suggested"] for d in domain_options(data)))
        check("掃描結果帶領域選項，而且不讀檔案內容", [d["id"] for d in scan(home, data, state, which=paths.get, run=fake_run, login="u",
              project=project)["omnikit"]["domains"]] == ["data", "dev"] and "秘密內容" not in json.dumps(options, ensure_ascii=False))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="列出這台電腦的 agent 環境（JSON）")
    parser.add_argument("--project", type=Path, help="使用者現在的專案資料夾：依裡面的檔名預選領域（只看檔名）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    result = scan(Path.home(), profiles.DATA, profiles.STATE, git_name=git_user_name(), project=args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
