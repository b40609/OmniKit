# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 入口接線、刪舊孤兒與反假綠燈稽核器（防假完工閘門 G2＋G3，支援 OmniKit 自身與任意外部用戶專案）。

解決兩大「說完工卻一用就爆」病根：
1. 寫新漏接、刪舊留空（Unwired & Orphan Drift）：
   - 檢查名冊 default/trial 工具是否都有工作台接線；
   - 掃描活躍文件、SKILL.md、PowerShell/Shell 腳本與 GitHub Actions 引用的腳本與技能路徑是否真實存在。
2. 反假綠燈作弊（Anti-Fake-Green）：
   - 掃描 git diff 新增行是否偷加 .skip / xit / @pytest.mark.skip / @unittest.skip 或 CI `|| true` 繞過失敗。
3. 支援 `--project <任意專案路徑>`：供所有裝了 OmniKit 的外部用戶透過 `omnikit-verify`（`/ok 驗收`）檢查自己的專案。

用法：
  uv run engine/scripts/wiring_audit.py [--json]                      稽核 OmniKit 自身 repo
  uv run engine/scripts/wiring_audit.py --project <路徑> [--json]      稽核任意用戶專案（抓假綠燈與斷頭檔案引用）
  uv run engine/scripts/wiring_audit.py --selftest
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
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

# 假綠燈作弊特徵（只比對無條件跳過標記，排除 Playwright `test.skip(cond, reason)` 條件式跳過）
FAKE_GREEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("test-skip-js", re.compile(r"\b(?:it|test|describe)\.skip\s*\(\s*['\"`]")),
    ("xit-js", re.compile(r"\b(?:xit|xdescribe|xtest)\s*\(")),
    ("pytest-skip-unconditional", re.compile(r"@pytest\.mark\.skip\s*(?:\(\s*(?:reason\s*=\s*['\"][^'\"]*['\"])?\s*\))?\s*$")),
    ("unittest-skip", re.compile(r"@unittest\.skip\s*\(")),
)
CI_SWALLOW_RE = re.compile(r"\|\|\s*true\b")
TEST_FILE_RE = re.compile(r"(?:^test_|_test\.py$|\.(?:test|spec)\.[A-Za-z0-9]+$)", re.IGNORECASE)

OMNIKIT_PATH_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_./\\-])((?:engine/(?:scripts|skills|schema|cockpit)|scripts|\.githooks)/[A-Za-z0-9_./-]+)"
)
HISTORICAL_DOC_DIRS = {"proposals", "evals", "reports", "reviews", "v2"}
SELF_EXEMPT_FILES = {
    "engine/scripts/wiring_audit.py",
    "engine/scripts/done_check.py",
    "engine/scripts/harness_hooks.py",
    "engine/scripts/cleanroom_e2e.py",
}


def _run_git(cwd: Path, args: list[str]) -> tuple[int, str]:
    git_exe = shutil.which("git")
    if not git_exe or not cwd.is_dir():
        return 1, ""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    kw: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 8,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run([git_exe, "-C", str(cwd), "-c", "core.longpaths=true", *args], check=False, **kw)
        return proc.returncode, proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def scan_fakegreen_diff(project_dir: Path, *, diff_text: str | None = None, staged_only: bool = False) -> list[dict[str, Any]]:
    """掃描 git diff 新增行與新建未追蹤測試檔是否偷加假綠燈跳過標記或 CI 吞錯。"""
    findings: list[dict[str, Any]] = []
    explicit_diff = diff_text is not None
    if diff_text is None:
        if staged_only:
            rc, out = _run_git(project_dir, ["diff", "--cached", "--unified=0", "--", "."])
        else:
            rc, out = _run_git(project_dir, ["diff", "HEAD", "--unified=0", "--", "."])
            if rc != 0:
                rc, out = _run_git(project_dir, ["diff", "--cached", "--unified=0", "--", "."])
        diff_text = out if rc == 0 else ""

    if diff_text.strip():
        cur_file = ""
        for raw_line in diff_text.splitlines():
            if raw_line.startswith("+++ b/"):
                cur_file = raw_line[6:].strip()
                continue
            if not raw_line.startswith("+") or raw_line.startswith("+++"):
                continue
            if cur_file in SELF_EXEMPT_FILES or cur_file.endswith(".md"):
                continue
            added = raw_line[1:]
            stripped = added.strip()
            if not stripped or stripped.startswith(("#", "//", "/*", "*")):
                continue
            for rule_id, pat in FAKE_GREEN_PATTERNS:
                if pat.search(added):
                    findings.append({
                        "kind": "fake_green",
                        "rule": rule_id,
                        "file": cur_file,
                        "detail": f"新增測試跳過標記：{stripped[:100]}",
                    })
            if cur_file.startswith(".github/workflows/") and cur_file.endswith((".yml", ".yaml")):
                if CI_SWALLOW_RE.search(added) and "fakegreen-allow" not in added:
                    findings.append({
                        "kind": "fake_green",
                        "rule": "ci-swallow-error",
                        "file": cur_file,
                        "detail": f"CI workflow 新增 `|| true` 吞掉失敗：{stripped[:100]}",
                    })

    # 非 staged_only 且非傳入固定字串時，一併檢查新建尚未 git add 的 untracked 測試檔
    if not staged_only and not explicit_diff:
        rc_top, top_out = _run_git(project_dir, ["rev-parse", "--show-toplevel"])
        repo_top = Path(top_out.strip()) if rc_top == 0 and top_out.strip() else project_dir
        rc_u, u_out = _run_git(project_dir, ["ls-files", "--others", "--exclude-standard"])
        if rc_u == 0 and u_out.strip():
            for rel in u_out.splitlines():
                rel = rel.strip()
                name = rel.rsplit("/", 1)[-1]
                is_wf = rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))
                if not rel or rel in SELF_EXEMPT_FILES or not (TEST_FILE_RE.search(name) or is_wf):
                    continue
                fp = (project_dir / rel) if (project_dir / rel).is_file() else (repo_top / rel)
                if not fp.is_file():
                    continue
                try:
                    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for ln in lines:
                    s = ln.strip()
                    if not s or s.startswith(("#", "//", "/*", "*")):
                        continue
                    for rule_id, pat in FAKE_GREEN_PATTERNS:
                        if pat.search(ln):
                            findings.append({
                                "kind": "fake_green",
                                "rule": rule_id,
                                "file": rel,
                                "detail": f"新建未追蹤測試檔含跳過標記：{s[:100]}",
                            })
                    if is_wf and CI_SWALLOW_RE.search(ln) and "fakegreen-allow" not in ln:
                        findings.append({
                            "kind": "fake_green",
                            "rule": "ci-swallow-error",
                            "file": rel,
                            "detail": f"新建 CI workflow 含 `|| true`：{s[:100]}",
                        })
    return findings


def audit_omnikit_repo(repo_root: Path = ROOT, *, staged_only: bool = False) -> dict[str, Any]:
    """稽核 OmniKit repo 的工具名冊接線、活躍文件／腳本孤兒引用與工作區假綠燈。"""
    problems: list[dict[str, Any]] = []

    # 1. 檢查 default / trial 工具卡是否皆納入工作台目錄（kit.py TOOL_COSTS）
    sys.path.insert(0, str(repo_root / "engine" / "scripts"))
    import kit as kit_mod

    tools_dir = repo_root / "data" / "tools"
    if tools_dir.is_dir():
        for tf in sorted(tools_dir.glob("*.yaml")):
            tdoc = yaml.safe_load(tf.read_text(encoding="utf-8")) or {}
            st = tdoc.get("status")
            tid = tdoc.get("id") or tf.stem
            if st in ("default", "trial") and tid not in kit_mod.TOOL_COSTS:
                problems.append({
                    "kind": "unwired_tool",
                    "file": f"data/tools/{tf.name}",
                    "detail": f"工具「{tid}」（狀態 {st}）未在 engine/scripts/kit.py 的 TOOL_COSTS 登記工作台與 Context 成本接線",
                })

    # 2. 掃描活躍文件、SKILL.md、腳本與 CI workflow 引用的內部路徑是否真實存在
    scan_targets: list[Path] = []
    readme = repo_root / "README.md"
    if readme.is_file():
        scan_targets.append(readme)
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        for p in sorted(docs_dir.rglob("*.md")):
            rel_parts = p.relative_to(docs_dir).parts
            if rel_parts and rel_parts[0] in HISTORICAL_DOC_DIRS:
                continue
            scan_targets.append(p)
    for folder_rel, globs in (
        ("engine/skills", ("*/SKILL.md",)),
        ("engine/scripts", ("*.ps1",)),
        (".githooks", ("*",)),
        (".github/workflows", ("*.yml", "*.yaml")),
    ):
        fdir = repo_root / folder_rel
        if fdir.is_dir():
            for g in globs:
                scan_targets.extend(sorted(p for p in fdir.glob(g) if p.is_file()))

    for src in scan_targets:
        rel_src = src.relative_to(repo_root).as_posix()
        txt = src.read_text(encoding="utf-8", errors="replace")
        for m in OMNIKIT_PATH_REF_RE.finditer(txt):
            tail_two = txt[m.end() : m.end() + 2]
            if tail_two.startswith((r"\.", "(", "|")):
                continue  # grep / regex 模式（例如 engine/scripts/profiles\.py$）
            ref = m.group(1).rstrip(".,;:)`'\"\\")
            if any(ch in ref for ch in ("<", ">", "*", "{", "}", "$")):
                continue
            if ref in ("engine/skills", "engine/scripts", "engine/schema", "engine/cockpit", ".githooks"):
                continue
            cand_root = repo_root / ref
            cand_rel = src.parent / ref
            if not cand_root.exists() and not cand_rel.exists():
                problems.append({
                    "kind": "dangling_reference",
                    "file": rel_src,
                    "detail": f"引用了不存在的內部路徑：{ref}",
                })

    # 3. 反假綠燈 diff 掃描
    problems.extend(scan_fakegreen_diff(repo_root, staged_only=staged_only))

    return {
        "ok": len(problems) == 0,
        "target": str(repo_root),
        "mode": "omnikit",
        "scanned_files": len(scan_targets),
        "problems": problems,
    }


def audit_user_project(project_dir: Path, *, staged_only: bool = False) -> dict[str, Any]:
    """稽核任意外部用戶專案：抓假綠燈作弊、package.json / workflow 斷頭腳本引用與未提交衝突標記。"""
    pdir = project_dir.resolve()
    if not pdir.is_dir():
        return {"ok": False, "target": str(pdir), "mode": "project", "problems": [{"kind": "missing_dir", "file": "", "detail": f"找不到目錄：{pdir}"}]}

    problems: list[dict[str, Any]] = []
    problems.extend(scan_fakegreen_diff(pdir, staged_only=staged_only))

    # 1. 檢查 package.json 裡的本地檔案引用（如 node scripts/xxx.js）是否存在
    pkg_json = pdir / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            for sname, scmd in (pkg.get("scripts") or {}).items():
                if not isinstance(scmd, str):
                    continue
                for m in re.finditer(r"(?:node|python|pwsh|bash|sh|tsx|ts-node)\s+([./A-Za-z0-9_-]+\.(?:js|mjs|cjs|ts|py|ps1|sh))", scmd):
                    rel_f = m.group(1)
                    if not (pdir / rel_f).is_file():
                        problems.append({
                            "kind": "dangling_script",
                            "file": "package.json",
                            "detail": f"scripts.{sname} 引用了不存在的腳本：{rel_f}",
                        })
        except (OSError, ValueError):
            problems.append({"kind": "invalid_json", "file": "package.json", "detail": "package.json 不是合法的 JSON"})

    # 2. 掃描常見原始碼是否有殘留 Git 合併衝突標記 `<<<<<<< `
    skip_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next", "target"}
    checked = 0
    for root_s, dirs, files in os.walk(pdir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in files:
            if not fn.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".html", ".css", ".json", ".yaml", ".yml")):
                continue
            fp = Path(root_s) / fn
            checked += 1
            if checked > 1500:
                break
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"(?m)^<<<<<<<\s", content) and re.search(r"(?m)^>>>>>>>\s", content):
                problems.append({
                    "kind": "merge_conflict",
                    "file": fp.relative_to(pdir).as_posix(),
                    "detail": "檔案內殘留未解決的 Git 合併衝突標記（<<<<<<<）",
                })
        if checked > 1500:
            break

    return {
        "ok": len(problems) == 0,
        "target": str(pdir),
        "mode": "project",
        "scanned_files": checked,
        "problems": problems,
    }


def selftest() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    fails: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            fails.append(label)

    # 1. 假綠燈 diff 偵測測試
    fake_diff = (
        "diff --git a/tests/app.test.ts b/tests/app.test.ts\n"
        "+++ b/tests/app.test.ts\n"
        "+  test.skip('login broken', () => {});\n"
        "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
        "+++ b/.github/workflows/ci.yml\n"
        "+      - run: pytest || true\n"
    )
    hits = scan_fakegreen_diff(ROOT, diff_text=fake_diff)
    check("scan_fakegreen_diff 能同時抓出 test.skip 與 CI `|| true` 吞錯",
          len(hits) == 2 and {h["rule"] for h in hits} == {"test-skip-js", "ci-swallow-error"})

    # 2. 外部用戶專案斷頭腳本與合併衝突測試
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "demo"
        proj.mkdir()
        (proj / "package.json").write_text(json.dumps({"scripts": {"start": "node scripts/missing.js"}}), encoding="utf-8")
        (proj / "app.js").write_text("<<<<<<< HEAD\nconst a = 1;\n=======\nconst a = 2;\n>>>>>>> branch\n", encoding="utf-8")
        res_bad = audit_user_project(proj)
        check("audit_user_project 能抓出 package.json 斷頭腳本與殘留衝突標記",
              not res_bad["ok"] and {p["kind"] for p in res_bad["problems"]} == {"dangling_script", "merge_conflict"})

        (proj / "scripts").mkdir()
        (proj / "scripts" / "missing.js").write_text("console.log('ok');\n", encoding="utf-8")
        (proj / "app.js").write_text("const a = 2;\n", encoding="utf-8")
        res_good = audit_user_project(proj)
        check("修好後 audit_user_project 通過（0 問題）", res_good["ok"])

    print(f"\n{'wiring_audit.py selftest：全部通過' if not fails else f'wiring_audit.py selftest：{len(fails)} 項失敗'}")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="OmniKit 入口接線、孤兒引用與反假綠燈稽核器")
    parser.add_argument("--project", help="指定要檢查的外部專案目錄（不指定則檢查 OmniKit repo 自身）")
    parser.add_argument("--staged", action="store_true", help="只掃描 git staged 變更（pre-commit hook 用）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    res = audit_user_project(Path(args.project), staged_only=args.staged) if args.project else audit_omnikit_repo(ROOT, staged_only=args.staged)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["ok"]:
            print(f"接線與防假綠燈檢查通過（掃描 {res['scanned_files']} 個檔案，0 項異常）。")
        else:
            print(f"發現 {len(res['problems'])} 項斷頭接線或假綠燈異常：")
            for p in res["problems"]:
                loc = f"[{p['file']}] " if p.get("file") else ""
                print(f"  - {loc}{p['detail']}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
