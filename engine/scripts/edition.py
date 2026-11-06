# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""這台電腦是 OmniKit 的維護者版還是同事版，以及免問核准的個人同意。

兩版只差兩件事，規則、skills、MCP 的接法都一樣：
- git hook：維護者版在 commit 或 pull 動到規則、skills、MCP、權限時自動同步；同事版不設 git hook，
  pull 不會改任何設定，要套用更新就重跑 install.ps1（先用 -WhatIf 預覽）。
- 免問核准（Claude Code 的 permissions.allow、Codex 的 default_tools_approval_mode）：維護者版沿用
  data/harness/claude-allow.txt 與 data/mcp/servers.yaml，那是維護者自己同意過的；同事版每個工具分開問，
  本人同意了才寫入，不沿用維護者的同意。

版本記在 %LOCALAPPDATA%\\omnikit\\edition.json。沒有記錄時：分版之前就裝過的電腦（有 agents.json，
而且 repo 用 .githooks）是維護者版，其他都是同事版。
同意記在 %LOCALAPPDATA%\\omnikit\\consent.json，以工具為單位（MCP server 名稱；不是 MCP 的權限規則就用規則本身）。

用法：
  uv run engine/scripts/edition.py                          印出這台的版本與判斷依據
  uv run engine/scripts/edition.py --show                   只印 maintainer 或 colleague（git hook、install.ps1 用）
  uv run engine/scripts/edition.py --set maintainer|colleague
  uv run engine/scripts/edition.py --save                   把目前判斷的版本記下來（install.ps1 用）
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

ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit"
EDITIONS = ("maintainer", "colleague")
LABELS = {"maintainer": "維護者版", "colleague": "同事版"}
SOURCES = {"recorded": "記在 edition.json", "legacy": "分版之前就裝過，沿用原本的自動同步", "default": "預設"}
# Claude Code 的 MCP 權限規則：mcp__<server> 或 mcp__<server>__<工具>
MCP_RULE = re.compile(r"^mcp__(.+?)(?:__.+)?$")


def read_json(path):
    """讀不到或格式不對都當成空的：這些檔只是記錄，壞了就退回預設（同事版、還沒問過）。"""
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
    """回傳（版本, 依據）。依據：recorded（記在 edition.json）、legacy（分版之前就裝過）、default。"""
    value = read_json(state / "edition.json").get("edition")
    if value in EDITIONS:
        return value, "recorded"
    if (state / "agents.json").exists() and git(repo) == ".githooks":
        return "maintainer", "legacy"
    return "colleague", "default"


def set_edition(state, value):
    if value not in EDITIONS:
        raise SystemExit(f"版本只能是 {' 或 '.join(EDITIONS)}：{value}")
    write_json(state / "edition.json", {"edition": value, "date": date.today().isoformat()})


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


def approver(state=STATE, repo=ROOT, git=hooks_path):
    """回傳 tool → 能不能寫入免問核准。維護者版：data 裡列的都可以；同事版：本人同意過的才可以。"""
    if resolve(state, repo, git)[0] == "maintainer":
        return lambda _tool: True
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

        check("沒有任何記錄：同事版", resolve(state, repo, hooks_on) == ("colleague", "default"))
        write_json(state / "agents.json", {"agents": ["claude-code"]})
        check("分版之前裝過（有 agents.json 而且用 .githooks）：維護者版",
              resolve(state, repo, hooks_on) == ("maintainer", "legacy"))
        check("有 agents.json 但沒用 .githooks：同事版", resolve(state, repo, hooks_off) == ("colleague", "default"))
        (state / "agents.json").unlink()
        check("用 .githooks 但沒接過 agent：同事版", resolve(state, repo, hooks_on)[0] == "colleague")

        set_edition(state, "colleague")
        write_json(state / "agents.json", {"agents": ["claude-code"]})
        check("記錄優先：記成同事版就不看舊安裝", resolve(state, repo, hooks_on) == ("colleague", "recorded"))
        set_edition(state, "maintainer")
        check("記成維護者版", resolve(state, repo, hooks_off) == ("maintainer", "recorded"))
        check("不認得的版本：失敗", fails(lambda: set_edition(state, "boss")))
        (state / "edition.json").write_bytes("﻿{\"edition\": \"colleague\"}".encode("utf-8"))
        check("edition.json 有 BOM 也讀得到", resolve(state, repo, hooks_on) == ("colleague", "recorded"))
        (state / "edition.json").write_text("{壞掉", encoding="utf-8")
        check("edition.json 壞掉：照沒有記錄判斷", resolve(state, repo, hooks_on) == ("maintainer", "legacy"))

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

        set_edition(state, "maintainer")
        check("維護者版：data 裡列的都可以寫", approver(state, repo, hooks_off)("chrome_devtools"))
        set_edition(state, "colleague")
        record(state, "chrome_devtools", True)
        allowed = approver(state, repo, hooks_off)
        check("同事版：本人同意過的才可以寫", allowed("chrome_devtools") and not allowed("other"))

        check("不是 git repo：hooksPath 是空字串", hooks_path(tmp / "not-a-repo") == "")

        # 實際跑 .githooks/sync-data.sh：%LOCALAPPDATA% 指到暫存資料夾，只餵不會觸發同步的組合，碰不到這台的設定
        sh = shutil.which("sh")
        if not sh:
            print("略過：找不到 sh，沒有實際跑 git hook")
        else:
            hook_env = {**os.environ, "LOCALAPPDATA": str(tmp / "hook")}
            if os.environ.get("UV"):  # 讓 hook 找得到正在用的這支 uv
                hook_env["PATH"] = str(Path(os.environ["UV"]).parent) + os.pathsep + hook_env.get("PATH", "")
            if os.environ.get("LOCALAPPDATA") and not os.environ.get("UV_CACHE_DIR"):
                hook_env["UV_CACHE_DIR"] = str(Path(os.environ["LOCALAPPDATA"]) / "uv" / "cache")

            def hook(changed):
                r = subprocess.run([sh, str(ROOT / ".githooks" / "sync-data.sh")], input=changed, cwd=ROOT,
                                   env=hook_env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                return r.returncode, r.stdout.strip(), r.stderr.strip()

            code, out, err = hook("data/mcp/servers.yaml\nengine/scripts/agents.py\n")
            check("git hook：同事版動到 MCP 與腳本，只印一行提醒、不同步",
                  code == 0 and len(out.splitlines()) == 1 and "不是維護者版" in out and not err)
            code, out, _ = hook("docs/v2/prd/prd.md\n")
            check("git hook：同事版只動到文件，什麼都不印", code == 0 and out == "")
            set_edition(tmp / "hook" / "omnikit", "maintainer")
            code, out, _ = hook("docs/v2/prd/prd.md\n")
            check("git hook：維護者版沒動到同步的檔案，什麼都不做", code == 0 and out == "")

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="OmniKit 的維護者版與同事版")
    parser.add_argument("--show", action="store_true", help="只印 maintainer 或 colleague")
    parser.add_argument("--set", dest="value", choices=EDITIONS, help="把這台設成這個版本")
    parser.add_argument("--save", action="store_true", help="把目前判斷的版本記下來")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.value:
        set_edition(STATE, args.value)
    elif args.save:
        value, source = resolve()
        if source != "recorded":
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
