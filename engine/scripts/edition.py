# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit 安裝模式（標準安裝 standard / 開發模式 dev）與免問核准的個人同意。

對外只有一套產品，一般使用者直接標準安裝（鎖定穩定發行 tag、使用 ~/.omnikit/current 乾淨副本、不設 git hook）；
僅在開發 OmniKit 本身或 fork 自建名冊時啟用開發模式（install.ps1 -Dev）：
- git hook：開發模式在 commit 或 pull 動到規則、skills、MCP、權限時自動同步；標準安裝不設 git hook，
  pull 不會改任何設定，要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）。
- 免問核准（Claude Code 的 permissions.allow、Codex 的 default_tools_approval_mode）：
  標準安裝與開發模式統一走個人同意紀錄（~/.omnikit/consent.json）或本機控制面板工作台開關，不再依模式自動放行。

模式記在 ~/.omnikit/edition.json（狀態資料夾，見 statedir.py）；向後相容舊值 colleague（→ standard）與 maintainer（→ dev）。
沒有記錄時：舊版已設 .githooks 且有設定檔的開發機視為 dev，其餘預設為 standard。
同意記在 ~/.omnikit/consent.json，以工具為單位（MCP server 名稱；不是 MCP 的權限規則就用規則本身）。

用法：
  uv run engine/scripts/edition.py                          印出這台的模式與判斷依據
  uv run engine/scripts/edition.py --show                   只印 standard 或 dev（git hook、install.ps1 用）
  uv run engine/scripts/edition.py --set standard|dev       設定模式（亦相容舊別名 colleague|maintainer）
  uv run engine/scripts/edition.py --save                   把目前判斷的模式記下來（install.ps1 用）
  uv run engine/scripts/edition.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from fsretry import flaky, retry  # 同一個資料夾：防毒短暫鎖住檔案時等一下再試（FR-34）
import statedir  # 同一個資料夾：狀態資料夾 ~/.omnikit

ROOT = Path(__file__).resolve().parents[2]
STATE = statedir.STATE
EDITIONS = ("standard", "dev")
ALIASES = {"standard": "standard", "dev": "dev", "colleague": "standard", "maintainer": "dev"}
LABELS = {"standard": "標準安裝", "dev": "開發模式"}
SOURCES = {"recorded": "記在 edition.json", "legacy": "偵測到既有的 .githooks 開發設定", "default": "預設"}
# Claude Code 的 MCP 權限規則：mcp__<server> 或 mcp__<server>__<工具>
MCP_RULE = re.compile(r"^mcp__(.+?)(?:__.+)?$")


def normalize(value):
    """正規化模式名稱（相容舊值 colleague -> standard、maintainer -> dev）。"""
    if not isinstance(value, str):
        return None
    return ALIASES.get(value.strip().lower())


def read_json(path):
    """讀不到或格式不對都當成空的：這些檔只是記錄，壞了就退回預設（標準安裝、還沒問過）。"""
    try:
        doc = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    retry(path.write_bytes, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def hooks_path(repo):
    """repo 自己設的 core.hooksPath；不是 git repo、沒有 git 或沒設就回空字串。只看 repo 這一層，
    不看全域設定。"""
    try:
        r = subprocess.run(["git", "-C", str(repo), "config", "--local", "--get", "core.hooksPath"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def resolve(state=STATE, repo=ROOT, git=hooks_path):
    """回傳（模式, 依據）。模式為 standard 或 dev；依據：recorded、legacy、default。"""
    value = normalize(read_json(state / "edition.json").get("edition"))
    if value in EDITIONS:
        return value, "recorded"
    if ((state / "config.json").exists() or (state / "agents.json").exists()) and git(repo) == ".githooks":
        return "dev", "legacy"
    return "standard", "default"


def is_dev(state=STATE, repo=ROOT, git=hooks_path):
    return resolve(state, repo, git)[0] == "dev"


def set_edition(state, value):
    norm = normalize(value)
    if norm not in EDITIONS:
        raise SystemExit(f"模式只能是 {' 或 '.join(EDITIONS)}：{value}")
    write_json(state / "edition.json", {"edition": norm, "date": date.today().isoformat()})


def tool_of(rule):
    """Claude Code 的權限規則屬於哪個工具：mcp__<server>（__<工具>）是那個 server，其他就是規則本身。"""
    m = MCP_RULE.match(rule)
    return m.group(1) if m else rule


def decisions(state):
    doc = read_json(state / "consent.json").get("auto_approve")
    return doc if isinstance(doc, dict) else {}


def decided(state, tool):
    """這個工具的免問核准：True（同意）、False（不要）、None（還沒問過）。"""
    entry = decisions(state).get(tool)
    granted = entry.get("granted") if isinstance(entry, dict) else None
    return granted if isinstance(granted, bool) else None


def record(state, tool, granted):
    doc = read_json(state / "consent.json")
    approve = doc.get("auto_approve") if isinstance(doc.get("auto_approve"), dict) else {}
    approve[tool] = {"granted": bool(granted), "date": date.today().isoformat()}
    doc["auto_approve"] = approve
    write_json(state / "consent.json", doc)


def _legacy_allow_tools(repo):
    """讀取舊版免問核准清單（claude-allow.txt 與 servers.yaml 的 Codex default_tools_approval_mode）。"""
    tools = []
    allow_file = repo / "data" / "harness" / "claude-allow.txt"
    if allow_file.is_file():
        for ln in allow_file.read_text(encoding="utf-8", errors="replace").splitlines():
            item = ln.strip()
            if not item or item.startswith("#"):
                continue
            t = tool_of(item)
            if t not in tools:
                tools.append(t)
    servers_file = repo / "data" / "mcp" / "servers.yaml"
    if servers_file.is_file():
        cur_server = None
        for ln in servers_file.read_text(encoding="utf-8", errors="replace").splitlines():
            m_srv = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", ln)
            if m_srv:
                cur_server = m_srv.group(1)
            elif cur_server and re.match(r"^\s+default_tools_approval_mode\s*:", ln):
                if cur_server not in tools:
                    tools.append(cur_server)
    return tools


def migrate_legacy_consent(state=STATE, repo=ROOT, git=hooks_path):
    """若本機為舊版 maintainer（edition.json 原值為 maintainer 或未記但由 .githooks 判為 legacy dev）且尚無 consent.json，
    一次性將既有的免問清單遷移為明確同意，避免 git hook 或升級同步時誤撤回既有權限。新安裝的 dev 模式不自動遷移。"""
    if (state / "consent.json").exists():
        return []
    raw_ed = read_json(state / "edition.json").get("edition")
    is_legacy_maintainer = raw_ed == "maintainer" or (raw_ed is None and resolve(state, repo, git) == ("dev", "legacy"))
    if not is_legacy_maintainer:
        return []
    migrated = []
    for t in _legacy_allow_tools(repo):
        record(state, t, True)
        migrated.append(t)
    return migrated


def approver(state=STATE, repo=ROOT, git=hooks_path):
    """回傳 tool → 能不能寫入免問核准。標準安裝與開發模式統一依本人同意紀錄（consent.json）決定。"""
    _ = (repo, git)
    return lambda tool: decided(state, tool) is True


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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        state, repo = tmp / "state", tmp / "repo"
        hooks_on, hooks_off = (lambda _repo: ".githooks"), (lambda _repo: "")

        check("沒有任何記錄：預設為標準安裝（standard）", resolve(state, repo, hooks_on) == ("standard", "default"))
        write_json(state / "agents.json", {"agents": ["claude-code"]})
        check("既有開發機（有設定檔而且用 .githooks）：自動識別為開發模式（dev）",
              resolve(state, repo, hooks_on) == ("dev", "legacy"))
        check("有設定檔但沒用 .githooks：標準安裝（standard）", resolve(state, repo, hooks_off) == ("standard", "default"))
        (state / "agents.json").unlink()
        check("用 .githooks 但沒接過 agent：標準安裝（standard）", resolve(state, repo, hooks_on)[0] == "standard")

        set_edition(state, "standard")
        write_json(state / "agents.json", {"agents": ["claude-code"]})
        check("記錄優先：記成 standard 就不看舊安裝", resolve(state, repo, hooks_on) == ("standard", "recorded"))
        set_edition(state, "dev")
        check("記成開發模式（dev）", resolve(state, repo, hooks_off) == ("dev", "recorded") and is_dev(state, repo, hooks_off))
        # 向後相容舊別名 colleague / maintainer
        set_edition(state, "colleague")
        check("舊別名 colleague 正規化為 standard", resolve(state, repo, hooks_on) == ("standard", "recorded"))
        write_json(state / "edition.json", {"edition": "maintainer"})
        check("舊 edition.json 寫 maintainer 自動讀成 dev", resolve(state, repo, hooks_off) == ("dev", "recorded"))
        check("不認得的模式：失敗", fails(lambda: set_edition(state, "boss")))
        (state / "edition.json").write_bytes("﻿{\"edition\": \"colleague\"}".encode("utf-8"))
        check("edition.json 有 BOM 也讀得到且正規化為 standard", resolve(state, repo, hooks_on) == ("standard", "recorded"))
        (state / "edition.json").write_text("{壞掉", encoding="utf-8")
        check("edition.json 壞掉：照沒有記錄判斷", resolve(state, repo, hooks_on) == ("dev", "legacy"))

        check("權限規則對應到工具：mcp__<server> 與 mcp__<server>__<工具> 都是那個 server",
              tool_of("mcp__chrome_devtools") == "chrome_devtools"
              and tool_of("mcp__chrome_devtools__click") == "chrome_devtools" and tool_of("Bash(git status)") == "Bash(git status)")

        check("還沒問過：None", decided(state, "chrome_devtools") is None)
        record(state, "chrome_devtools", True)
        record(state, "other", False)
        check("記下同意與不要", decided(state, "chrome_devtools") is True and decided(state, "other") is False)
        record(state, "chrome_devtools", False)
        check("撤回同意", decided(state, "chrome_devtools") is False and decided(state, "other") is False)
        with flaky(Path, "write_bytes", times=2, match=lambda p, *_: p == state / "consent.json") as st:
            record(state, "other", True)
        check("consent.json 被防毒短暫鎖住（FR-34）：等一下再試，照樣記下", st.calls == 3 and decided(state, "other") is True)
        (state / "consent.json").write_text("{壞掉", encoding="utf-8")
        check("consent.json 壞掉：當成都還沒問過", decided(state, "other") is None)

        # 方案 A：開發模式與標準安裝統一走個人同意，不再自動放行
        set_edition(state, "dev")
        check("開發模式未同意前亦不自動放行", not approver(state, repo, hooks_off)("chrome_devtools"))
        record(state, "chrome_devtools", True)
        allowed = approver(state, repo, hooks_off)
        check("本人同意過的工具才放行（不論 standard 或 dev）", allowed("chrome_devtools") and not allowed("other"))

        # 舊版 maintainer / legacy .githooks 升級遷移：無 consent.json 時保留既有 Claude 與 Codex 免問權限；新 dev 不遷移
        mig_state = tmp / "mig_state"
        mig_repo = tmp / "mig_repo"
        (mig_repo / "data" / "harness").mkdir(parents=True)
        (mig_repo / "data" / "harness" / "claude-allow.txt").write_text("mcp__chrome_devtools\n", encoding="utf-8")
        (mig_repo / "data" / "mcp").mkdir(parents=True)
        (mig_repo / "data" / "mcp" / "servers.yaml").write_text(
            "servers:\n  codex_only:\n    options:\n      codex:\n        default_tools_approval_mode: approve\n",
            encoding="utf-8",
        )
        write_json(mig_state / "edition.json", {"edition": "maintainer"})
        migrated = migrate_legacy_consent(mig_state, mig_repo, hooks_off)
        check("舊版 maintainer 無 consent.json 時一次性遷移既有 Claude 與 Codex 免問權限",
              migrated == ["chrome_devtools", "codex_only"]
              and decided(mig_state, "chrome_devtools") is True
              and decided(mig_state, "codex_only") is True)
        leg_state = tmp / "leg_state"
        write_json(leg_state / "config.json", {"agents": ["claude-code"]})
        leg_mig = migrate_legacy_consent(leg_state, mig_repo, hooks_on)
        check("舊版無 edition.json 但由 .githooks 判為 legacy 開發機時亦可平滑遷移",
              leg_mig == ["chrome_devtools", "codex_only"])
        fresh_dev = tmp / "fresh_dev"
        set_edition(fresh_dev, "dev")
        check("新安裝的 dev 模式不自動遷移繞過同意", migrate_legacy_consent(fresh_dev, mig_repo, hooks_on) == [])

        check("不是 git repo：hooksPath 是空字串", hooks_path(tmp / "not-a-repo") == "")

        # 實際跑 .githooks/sync-data.sh：%LOCALAPPDATA% 與狀態資料夾都指到暫存資料夾，只餵不會觸發同步的組合，
        # 碰不到這台的設定
        sh = shutil.which("sh")
        if not sh:
            print("略過：找不到 sh，沒有實際跑 git hook")
        else:
            hook_env = {**os.environ, "LOCALAPPDATA": str(tmp / "hook"), statedir.ENV: str(tmp / "hook" / "omnikit")}
            if os.environ.get("UV"):  # 讓 hook 找得到正在用的這支 uv
                hook_env["PATH"] = str(Path(os.environ["UV"]).parent) + os.pathsep + hook_env.get("PATH", "")
            if os.environ.get("LOCALAPPDATA") and not os.environ.get("UV_CACHE_DIR"):
                hook_env["UV_CACHE_DIR"] = str(Path(os.environ["LOCALAPPDATA"]) / "uv" / "cache")

            def hook(changed, cwd=ROOT, env=hook_env):
                r = subprocess.run([sh, str(ROOT / ".githooks" / "sync-data.sh")], input=changed, cwd=cwd,
                                   env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                return r.returncode, r.stdout.strip(), r.stderr.strip()

            code, out, err = hook("data/mcp/servers.yaml\nengine/scripts/sync.py\n")
            check("git hook：標準安裝動到 MCP 與腳本，只印一行提醒、不同步",
                  code == 0 and len(out.splitlines()) == 1 and "開發模式" in out and not err)
            code, out, _ = hook("docs/v2/prd/prd.md\n")
            check("git hook：標準安裝只動到文件，什麼都不印", code == 0 and out == "")
            set_edition(tmp / "hook" / "omnikit", "dev")
            code, out, _ = hook("docs/v2/prd/prd.md\n")
            check("git hook：開發模式沒動到同步的檔案，什麼都不做", code == 0 and out == "")

            # linked worktree：暫存 repo 放假的 edition.py（固定 dev）與 sync.py（只寫記號檔），
            # 實際同步什麼都碰不到；主 checkout 要寫出記號，證明假腳本有接上，worktree 不寫才有意義
            main, wt, mark = tmp / "wt-main", tmp / "wt-linked", tmp / "synced.txt"
            scripts = main / "engine" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "edition.py").write_text('print("dev")\n', encoding="utf-8")
            (scripts / "sync.py").write_text(
                "import os, sys\n"
                f"with open({str(mark)!r}, 'a', encoding='utf-8') as f:\n"
                "    f.write(' '.join(sys.argv[1:]) + ' @ ' + os.getcwd() + '\\n')\n", encoding="utf-8")
            (tmp / "no-hooks").mkdir()
            git_env = {k: v for k, v in hook_env.items() if not k.startswith("GIT_")}
            git = ["git", "-c", f"core.hooksPath={tmp / 'no-hooks'}", "-c", "commit.gpgsign=false",
                   "-c", "user.name=OmniKit selftest", "-c", "user.email=selftest@example.invalid"]
            setup_ok = all(subprocess.run(git + args, cwd=main, env=git_env, capture_output=True, timeout=60).returncode == 0
                           for args in (["init", "--quiet"], ["add", "-A"], ["commit", "--quiet", "-m", "init"],
                                        ["worktree", "add", "--quiet", "-b", "wt", str(wt)]))
            if not setup_ok:
                check("git hook：建立暫存 repo 與 linked worktree", False)
            else:
                skills = "engine/skills/demo/SKILL.md\n"
                code, out, err = hook(skills, cwd=wt, env=git_env)
                check("git hook：linked worktree 動到 skills，只印一行提醒、不同步",
                      code == 0 and len(out.splitlines()) == 1 and "worktree" in out and not err and not mark.exists())
                code, out, err = hook("docs/v2/prd/prd.md\n", cwd=wt, env=git_env)
                check("git hook：linked worktree 只動到文件，什麼都不印", code == 0 and out == "" and not err)
                code, out, err = hook(skills, cwd=main, env=git_env)
                synced = mark.read_text(encoding="utf-8") if mark.exists() else ""
                check("git hook：主 checkout 照常同步 skills",
                      code == 0 and not err and synced.startswith("sync --skills") and "worktree" not in out)

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="OmniKit 安裝模式（standard / dev）與免問授權狀態")
    parser.add_argument("--show", action="store_true", help="只印 standard 或 dev")
    parser.add_argument("--set", dest="value", choices=("standard", "dev", "colleague", "maintainer"), help="設定安裝模式")
    parser.add_argument("--save", action="store_true", help="把目前判斷的模式記下來")
    parser.add_argument("--migrate-consent", action="store_true", help="將舊版 maintainer 既有免問規則一次性遷移至 consent.json")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.migrate_consent:
        migrate_legacy_consent(STATE, ROOT)
    if args.value:
        set_edition(STATE, args.value)
    elif args.save:
        value, source = resolve()
        if source != "recorded" or read_json(STATE / "edition.json").get("edition") not in EDITIONS:
            set_edition(STATE, value)
    value, source = resolve()
    if args.show:
        print(value)
    else:
        print(f"{LABELS[value]}（{value}）：{SOURCES[source]}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
