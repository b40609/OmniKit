# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""公開 repo 的「個人與私有字串」檢查：把公開規則與私有清單接成一份 gitleaks 設定（2026-11-27，KIT-A-02、KIT-X-03）。

公開規則在 .github/gitleaks-tree.toml（tailnet 主機名、個人 profile、評測 patch，外加 gitleaks 預設的金鑰規則）。
私有清單是雇主、私有專案代號、帳號名這類不能寫進公開 repo 的字串，一行一條 RE2 正規式（# 開頭是註解），
依序從這幾個地方找第一個有的：
  1. --denylist <檔案>
  2. 環境變數 OMNIKIT_PRIVATE_DENYLIST（CI 從 repo secret 帶進來；fork 與外部 PR 沒有，只跑公開規則）
  3. ~/.omnikit/private-denylist.txt（維護者本機；pre-commit 用）
產生的設定與任何輸出都不印私有字串本身：規則 id 只有編號，gitleaks 一律加 --redact。

用法：
  uv run engine/scripts/privacy_rules.py config --out <檔案>   寫出合併後的 gitleaks 設定（stderr 印條數與來源）
  uv run engine/scripts/privacy_rules.py scan                 掃這份 repo 的 index（就是下一次 commit 的內容）
  uv run engine/scripts/privacy_rules.py --selftest
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / ".github" / "gitleaks-tree.toml"
ENV = "OMNIKIT_PRIVATE_DENYLIST"
LOCAL = Path.home() / ".omnikit" / "private-denylist.txt"


def parse(text):
    """一行一條正規式；空行與 # 開頭的註解跳過。含 ''' 的寫不進 TOML 字面字串，直接報錯。"""
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "'''" in line:
            raise ValueError(f"私有清單第 {n} 行含有 '''，寫不進 gitleaks 設定")
        out.append(line)
    return out


def source(denylist=None, environ=None, local=LOCAL):
    """回傳（清單內容, 來源說明）。來源說明不含清單內容。"""
    environ = os.environ if environ is None else environ
    if denylist:
        return Path(denylist).read_text(encoding="utf-8-sig"), f"檔案 {denylist}"
    if environ.get(ENV, "").strip():
        return environ[ENV], f"環境變數 {ENV}"
    if local.is_file():
        return local.read_text(encoding="utf-8-sig"), f"本機 {local}"
    return "", "沒有（只跑公開規則）"


def render(patterns, base=BASE):
    lines = ["# 由 engine/scripts/privacy_rules.py 產生，含私有字串：不要 commit、不要印出來", "",
             "[extend]", f"path = '''{Path(base).as_posix()}'''", ""]
    for i, pat in enumerate(patterns, 1):
        lines += ["[[rules]]", f'id = "omnikit-private-{i}"',
                  f'description = "私有字串清單第 {i} 條（內容不在公開 repo）"',
                  f"regex = '''{pat}'''", ""]
    return "\n".join(lines)


def write_config(out, denylist=None, environ=None, local=LOCAL, base=BASE):
    text, where = source(denylist, environ, local)
    patterns = parse(text)
    Path(out).write_text(render(patterns, base), encoding="utf-8")
    return len(patterns), where


def find_gitleaks():
    found = shutil.which("gitleaks")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "gitleaks" / "gitleaks.exe"
    return str(local) if local.is_file() else None


def scan(repo=ROOT, run=subprocess.run):
    """把 index 匯出到暫存資料夾再用 gitleaks dir 掃：只看會被 commit 的檔案，本機沒追蹤的個人檔不會誤報。"""
    gl = find_gitleaks()
    if not gl:
        print("找不到 gitleaks：先跑 engine/scripts/install.ps1", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        tree, cfg = Path(tmp) / "tree", Path(tmp) / "privacy.toml"
        run(["git", "-C", str(repo), "checkout-index", "-a", f"--prefix={tree.as_posix()}/"], check=True)
        n, where = write_config(cfg)
        print(f"私有字串 {n} 條（來源：{where}）", file=sys.stderr)
        return run([gl, "dir", "--config", str(cfg), "--redact", "--no-banner", "--log-level", "warn",
                    "--verbose", str(tree)]).returncode


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    check("空行與註解跳過，其餘照順序", parse("# 註解\n\n(?i)\\bfoo\\b\n  bar  \n") == ["(?i)\\bfoo\\b", "bar"])
    try:
        parse("a'''b")
        caught = False
    except ValueError as e:
        caught = "'''" in str(e) and "a'''b" not in str(e)
    check("含 ''' 的行報錯，錯誤訊息不印內容", caught)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        local = tmp / "local.txt"
        local.write_text("本機的\n", encoding="utf-8")
        check("來源順序：--denylist、環境變數、本機檔", source(None, {ENV: "環境的"}, local)[0] == "環境的"
              and source(None, {}, local)[0] == "本機的\n" and source(None, {}, tmp / "none")[1].startswith("沒有"))
        given = tmp / "given.txt"
        given.write_text("﻿給的\n", encoding="utf-8")
        check("--denylist 優先，去掉 BOM", source(given, {ENV: "環境的"}, local)[0] == "給的\n")
        out = tmp / "cfg.toml"
        n, where = write_config(out, None, {ENV: "(?i)\\bsecret-proj\\b\n"}, local)
        doc = tomllib.loads(out.read_text(encoding="utf-8"))
        rule = doc["rules"][0]
        check("產生的設定是合法 TOML：接在公開規則後面，私有規則只有編號",
              n == 1 and doc["extend"]["path"] == BASE.as_posix() and rule["id"] == "omnikit-private-1"
              and rule["regex"] == "(?i)\\bsecret-proj\\b" and "secret-proj" not in rule["description"]
              and "secret-proj" not in where)
        n0, _ = write_config(out, None, {}, tmp / "none")
        check("沒有私有清單時只接公開規則", n0 == 0 and "rules" not in tomllib.loads(out.read_text(encoding="utf-8")))
    base = tomllib.loads(BASE.read_text(encoding="utf-8"))
    ids = {r["id"] for r in base.get("rules", [])}
    check("公開規則有 tailnet 主機名、個人 profile、評測 patch，並沿用 gitleaks 預設規則",
          {"omnikit-tailnet-hostname", "omnikit-personal-profile", "omnikit-eval-patch"} <= ids
          and base["extend"]["useDefault"] is True)
    print("全部通過" if not failures else f"{len(failures)} 項失敗")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="公開 repo 的個人與私有字串檢查（gitleaks 設定）")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    c = sub.add_parser("config", help="寫出合併後的 gitleaks 設定")
    c.add_argument("--out", required=True)
    c.add_argument("--denylist")
    sub.add_parser("scan", help="掃這份 repo 的 index")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "config":
        n, where = write_config(args.out, args.denylist)
        print(f"私有字串 {n} 條（來源：{where}）", file=sys.stderr)
        return 0
    if args.cmd == "scan":
        return scan()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
