# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit 掃描：列出這台電腦的 agent 環境，給 omnikit-setup 訪談用。輸出 JSON。

只看存在與否、名稱與版本：不輸出金鑰、token、環境變數的值，規則檔只算行數、不輸出內容，
MCP 只列名稱。版本號是執行各工具的 --version 拿到的；agent 本身不執行，只看設定目錄與 PATH。

用法：
  uv run engine/scripts/scan.py
  uv run engine/scripts/scan.py --selftest
"""
import argparse
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


def omnikit_state(data, state):
    available = profiles.available(data)
    chosen = profiles.chosen(state)
    current = chosen if chosen in available else profiles.DEFAULT
    answers_path = data / "profiles" / current / "answers.json"
    try:
        previous = json.loads(answers_path.read_text(encoding="utf-8")) if answers_path.exists() else None
    except (OSError, ValueError):
        previous = None
    try:
        connected = json.loads((state / "agents.json").read_text(encoding="utf-8")).get("agents", [])
    except (OSError, ValueError, AttributeError):
        connected = []
    return {
        "root": str(data.parent),
        "profile": current,
        "profile_chosen": chosen is not None,
        "profiles": available,
        "connected_agents": connected,
        "answers_file": str(state / "setup-answers.json"),
        "previous_answers": previous,
    }


def scan(home, data, state, which=shutil.which, run=run_version, login=None, git_name=None):
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

    omnikit = omnikit_state(data, state)
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

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="列出這台電腦的 agent 環境（JSON）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    result = scan(Path.home(), profiles.DATA, profiles.STATE, git_name=git_user_name())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
