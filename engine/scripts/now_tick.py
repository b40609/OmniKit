# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""NOW.md 完工路徑確定性打勾腳本（KIT-X-01）。

在將 NOW.md 的「## 完工路徑」從 `- [ ]` 改成 `- [x]` 之前，先透過 `gh run list --commit <sha>` 查證該 commit 的 CI 結論：
- 全部最新 workflow run 都是 completed + success（且至少 1 筆）才允許打勾，並自動重算「還有 N 步，完成 M 步」。
- CI 失敗、進行中、查無紀錄或 `gh` 無法連線時一律拒絕打勾（exit 1），絕不 fail-open。
- 加上 `--mark-unverified` 時維持 `- [ ]`，並在該行標記「（CI 未綠：…）」供後續追蹤（exit 2）。

用法：
  uv run engine/scripts/now_tick.py check --commit <sha> [--project-dir <目錄>] [--repo <owner/repo>] [--workflow <名稱>] [--json]
  uv run engine/scripts/now_tick.py tick --now <NOW.md> --match "<步驟關鍵字>" --commit <sha> [--project-dir <目錄>] [--repo <owner/repo>] [--mark-unverified] [--dry-run]
  uv run engine/scripts/now_tick.py audit --now <NOW.md> [--project-dir <目錄>] [--repo <owner/repo>] [--json]
  uv run engine/scripts/now_tick.py --selftest
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
CHECKBOX_RE = re.compile(r"^(\s*-\s*\[)([ xX])(\]\s*)(.+?)\s*$")
PROGRESS_RE = re.compile(r"還有\s+\d+\s*步，完成\s+\d+\s*步")
CI_UNVERIFIED_RE = re.compile(r"\s*（CI 未綠[^）]*）\s*")
INLINE_SHA_RE = re.compile(r"[（(]\s*([0-9a-f]{7,40})\s*[)）]")


def _run_cmd(cmd, cwd=None, timeout=30):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"找不到指令：{cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"指令逾時（{timeout}s）：{' '.join(cmd)}"
    except OSError as e:
        return 1, "", str(e)


def resolve_commit(sha, project_dir=None, repo=None, runner=None):
    """將短 sha（或 HEAD）解析為 (full_sha, short_sha)。gh run list --commit 需要完整 40 碼 SHA。"""
    sha = (sha or "").strip()
    if not sha:
        raise ValueError("必須提供 --commit <sha>")
    run = runner or _run_cmd
    if project_dir:
        rc, out, err = run(["git", "-C", str(project_dir), "rev-parse", "--verify", f"{sha}^{{commit}}"], None)
        if rc != 0 or not out.strip():
            raise ValueError(f"在 {project_dir} 找不到 commit「{sha}」：{err.strip() or '無輸出'}")
        full = out.strip()
        return full, full[:7]
    if not SHA_RE.match(sha):
        raise ValueError(f"commit 格式不正確（需要 7 到 40 碼十六進位）：{sha}")
    if len(sha) < 40 and repo and runner is None:
        rc, out, _ = run(["gh", "api", f"repos/{repo}/commits/{sha}", "--jq", ".sha"], None)
        if rc == 0 and len(out.strip()) == 40:
            full = out.strip().lower()
            return full, full[:7]
    return sha.lower(), sha.lower()[:7]


def _latest_by_workflow(runs):
    """同一 workflow 重跑時取最新一筆（依 createdAt 與 databaseId 降冪）。"""
    groups = {}
    for idx, r in enumerate(runs):
        key = r.get("workflowName") or r.get("name") or f"run-{idx}"
        rank = (str(r.get("createdAt") or ""), int(r.get("databaseId") or 0), idx)
        prev = groups.get(key)
        if prev is None or rank > prev[0]:
            groups[key] = (rank, r)
    return [pair[1] for pair in groups.values()]


def check_commit_ci(sha, *, repo=None, project_dir=None, workflow=None, allow_no_ci=False, runner=None):
    """查詢指定 commit 在 GitHub Actions 的最新 CI 結論。不 fail-open。"""
    run = runner or _run_cmd
    if runner is None and not shutil.which("gh"):
        return {
            "ok": False, "state": "unknown", "commit": sha, "runs": [],
            "reason": "找不到 gh CLI，無法查證 CI 狀態（查不到不算通過）",
        }
    cmd = [
        "gh", "run", "list",
        "--commit", sha,
        "--limit", "50",
        "--json", "databaseId,name,workflowName,status,conclusion,url,headSha,createdAt",
    ]
    if repo:
        cmd += ["--repo", repo]
    if workflow:
        cmd += ["--workflow", workflow]
    cwd = str(project_dir) if (project_dir and not repo) else None
    rc, out, err = run(cmd, cwd)
    if rc != 0:
        return {
            "ok": False, "state": "unknown", "commit": sha, "runs": [],
            "reason": f"gh run list 失敗（exit {rc}）：{(err or out).strip() or '無錯誤訊息'}",
        }
    try:
        raw_runs = json.loads(out or "[]")
        if not isinstance(raw_runs, list):
            raise ValueError("回傳不是 JSON 陣列")
    except ValueError as e:
        return {
            "ok": False, "state": "unknown", "commit": sha, "runs": [],
            "reason": f"無法解析 gh run list 輸出：{e}",
        }

    if not raw_runs:
        if allow_no_ci:
            return {
                "ok": True, "state": "no_ci_allowed", "commit": sha, "runs": [],
                "reason": "查無 CI run，已指定 --allow-no-ci 放行",
            }
        return {
            "ok": False, "state": "no_runs", "commit": sha, "runs": [],
            "reason": f"查無 commit {sha[:7]} 的 GitHub Actions CI 紀錄（尚未推送、CI 未啟動或無 workflow）",
        }

    latest = _latest_by_workflow(raw_runs)
    pending = [r for r in latest if r.get("status") != "completed"]
    failed = [r for r in latest if r.get("status") == "completed" and r.get("conclusion") != "success"]
    passed = [r for r in latest if r.get("status") == "completed" and r.get("conclusion") == "success"]

    if failed:
        desc = "、".join(
            f"{r.get('workflowName') or r.get('name')}={r.get('conclusion')}" + (f" ({r.get('url')})" if r.get("url") else "")
            for r in failed
        )
        return {
            "ok": False, "state": "failed", "commit": sha, "runs": latest,
            "reason": f"CI 未通過：{desc}",
        }
    if pending:
        desc = "、".join(
            f"{r.get('workflowName') or r.get('name')}={r.get('status')}" + (f" ({r.get('url')})" if r.get("url") else "")
            for r in pending
        )
        return {
            "ok": False, "state": "pending", "commit": sha, "runs": latest,
            "reason": f"CI 尚未完成：{desc}",
        }
    if not passed:
        return {
            "ok": False, "state": "unknown", "commit": sha, "runs": latest,
            "reason": "沒有任何通過的 CI run",
        }
    desc = "、".join(
        f"{r.get('workflowName') or r.get('name')}=success" + (f" ({r.get('url')})" if r.get("url") else "")
        for r in passed
    )
    return {
        "ok": True, "state": "success", "commit": sha, "runs": latest,
        "reason": f"CI 全綠：{desc}",
    }


def _find_section_bounds(lines, heading="## 完工路徑"):
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def recount_progress(lines, start, end):
    """依完工路徑區段內的核取方塊，重算「還有 N 步，完成 M 步」。"""
    done = 0
    todo = 0
    for i in range(start, end):
        m = CHECKBOX_RE.match(lines[i])
        if not m:
            continue
        if m.group(2).lower() == "x":
            done += 1
        else:
            todo += 1
    for i in range(start, end):
        if PROGRESS_RE.search(lines[i]):
            lines[i] = PROGRESS_RE.sub(f"還有 {todo} 步，完成 {done} 步", lines[i], count=1)
            break
    return todo, done


def tick_now_file(now_path, match, commit, *, project_dir=None, repo=None, workflow=None,
                  allow_no_ci=False, mark_unverified=False, dry_run=False, runner=None):
    """查驗 CI 後更新 NOW.md 完工路徑的指定列。回傳 (exit_code, result_dict)。"""
    path = Path(now_path)
    if not path.is_file():
        return 1, {"ok": False, "error": f"找不到檔案：{path}"}
    try:
        full_sha, short_sha = resolve_commit(commit, project_dir=project_dir, repo=repo, runner=runner)
    except ValueError as e:
        return 1, {"ok": False, "error": str(e)}

    text = path.read_text(encoding="utf-8")
    had_trailing_nl = text.endswith("\n")
    lines = text.splitlines()
    bounds = _find_section_bounds(lines)
    if bounds is None:
        return 1, {"ok": False, "error": f"{path} 找不到「## 完工路徑」區段"}
    start, end = bounds

    hits = []
    for i in range(start, end):
        m = CHECKBOX_RE.match(lines[i])
        if m and match in lines[i]:
            hits.append((i, m))
    if not hits:
        return 1, {"ok": False, "error": f"在「## 完工路徑」找不到符合「{match}」的步驟"}
    if len(hits) > 1:
        return 1, {"ok": False, "error": f"「{match}」命中 {len(hits)} 列，請給更精確的關鍵字避免誤改"}

    idx, m = hits[0]
    ci = check_commit_ci(
        full_sha, repo=repo, project_dir=project_dir, workflow=workflow,
        allow_no_ci=allow_no_ci, runner=runner,
    )
    prefix, _, mid, body = m.groups()
    clean_body = CI_UNVERIFIED_RE.sub("", body).rstrip()

    if ci["ok"]:
        if short_sha not in clean_body and full_sha not in clean_body:
            clean_body = f"{clean_body}（{short_sha}）"
        new_line = f"{prefix}x{mid}{clean_body}"
        lines[idx] = new_line
        todo, done = recount_progress(lines, start, end)
        if not dry_run:
            path.write_text("\n".join(lines) + ("\n" if had_trailing_nl else ""), encoding="utf-8")
        return 0, {
            "ok": True, "action": "ticked", "line": new_line, "commit": full_sha,
            "todo": todo, "done": done, "ci": ci, "dry_run": dry_run,
        }

    if mark_unverified:
        tag = f"（CI 未綠：{ci['state']} {short_sha}）"
        new_line = f"{prefix} {mid}{clean_body}{tag}"
        lines[idx] = new_line
        todo, done = recount_progress(lines, start, end)
        if not dry_run:
            path.write_text("\n".join(lines) + ("\n" if had_trailing_nl else ""), encoding="utf-8")
        return 2, {
            "ok": False, "action": "marked_unverified", "line": new_line, "commit": full_sha,
            "todo": todo, "done": done, "ci": ci, "dry_run": dry_run,
        }

    return 1, {
        "ok": False, "action": "rejected", "line": lines[idx], "commit": full_sha,
        "ci": ci, "dry_run": dry_run,
    }


def audit_now_file(now_path, *, project_dir=None, repo=None, workflow=None, runner=None):
    """審計 NOW.md「## 完工路徑」所有已打勾項目對應的 commit CI 狀態。"""
    path = Path(now_path)
    if not path.is_file():
        return 1, {"ok": False, "error": f"找不到檔案：{path}", "items": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    bounds = _find_section_bounds(lines)
    if bounds is None:
        return 1, {"ok": False, "error": f"{path} 找不到「## 完工路徑」區段", "items": []}
    start, end = bounds
    items = []
    any_bad = False
    for i in range(start, end):
        m = CHECKBOX_RE.match(lines[i])
        if not m or m.group(2).lower() != "x":
            continue
        body = m.group(4)
        shas = INLINE_SHA_RE.findall(body)
        if not shas:
            items.append({"line": lines[i], "commits": [], "ok": False, "state": "missing_sha", "reason": "已打勾但未附 commit SHA"})
            any_bad = True
            continue
        checks = []
        line_ok = True
        for s in shas:
            try:
                full_sha, _ = resolve_commit(s, project_dir=project_dir, repo=repo, runner=runner)
                res = check_commit_ci(full_sha, repo=repo, project_dir=project_dir, workflow=workflow, runner=runner)
            except ValueError as e:
                res = {"ok": False, "state": "invalid_sha", "commit": s, "reason": str(e), "runs": []}
            checks.append(res)
            if not res["ok"]:
                line_ok = False
        if not line_ok:
            any_bad = True
        items.append({"line": lines[i], "commits": shas, "ok": line_ok, "checks": checks})
    return (1 if any_bad else 0), {"ok": not any_bad, "items": items}


def selftest():
    failures = []

    def ok(label, cond):
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            failures.append(label)

    sample_now = (
        "# Sample — 目前狀態\n\n"
        "## 完工路徑\n\n"
        "還有 2 步，完成 0 步（下坡：收尾中）\n\n"
        "- [ ] Step 1：補齊護欄與測試\n"
        "- [ ] Step 2：開啟分支保護\n\n"
        "## 下一步\n\n"
        "1. 測試\n"
    )

    def make_runner(runs_by_sha, fail_gh=False):
        def _fake(cmd, cwd=None, timeout=30):
            if cmd[0] == "gh":
                if fail_gh:
                    return 1, "", "HTTP 500 API error"
                sha = cmd[cmd.index("--commit") + 1]
                return 0, json.dumps(runs_by_sha.get(sha, [])), ""
            return 1, "", f"unexpected cmd: {cmd}"
        return _fake

    with tempfile.TemporaryDirectory() as td:
        now_f = Path(td) / "NOW.md"

        # 1. CI 紅燈：預設拒絕打勾，檔案不動
        now_f.write_text(sample_now, encoding="utf-8")
        r_fail = make_runner({"aaaaaaa": [
            {"databaseId": 1, "workflowName": "檢查", "status": "completed", "conclusion": "failure", "url": "https://example/1", "createdAt": "2026-11-27T01:00:00Z"}
        ]})
        rc, res = tick_now_file(now_f, "Step 1", "aaaaaaa", runner=r_fail)
        ok("CI 紅燈時拒絕打勾（exit 1）且 NOW.md 維持 - [ ] 不改寫",
           rc == 1 and res["action"] == "rejected" and res["ci"]["state"] == "failed" and now_f.read_text(encoding="utf-8") == sample_now)

        # 2. CI 進行中：拒絕打勾
        r_pend = make_runner({"bbbbbbb": [
            {"databaseId": 2, "workflowName": "檢查", "status": "in_progress", "conclusion": None, "url": "https://example/2", "createdAt": "2026-11-27T01:00:00Z"}
        ]})
        rc, res = tick_now_file(now_f, "Step 1", "bbbbbbb", runner=r_pend)
        ok("CI 仍在執行（in_progress）時拒絕打勾（exit 1）",
           rc == 1 and res["ci"]["state"] == "pending" and "- [ ] Step 1" in now_f.read_text(encoding="utf-8"))

        # 3. 查無 CI run：拒絕打勾（不 fail-open）
        r_empty = make_runner({})
        rc, res = tick_now_file(now_f, "Step 1", "ccccccc", runner=r_empty)
        ok("查無 CI 紀錄（0 runs）時拒絕打勾（exit 1）",
           rc == 1 and res["ci"]["state"] == "no_runs")

        # 4. gh CLI 失敗：拒絕打勾（不 fail-open）
        r_err = make_runner({}, fail_gh=True)
        rc, res = tick_now_file(now_f, "Step 1", "ccccccc", runner=r_err)
        ok("gh 查詢失敗時拒絕打勾（exit 1，不 fail-open）",
           rc == 1 and res["ci"]["state"] == "unknown")

        # 5. --mark-unverified + CI 紅燈：維持 - [ ] 並標記「CI 未綠」（exit 2）
        rc, res = tick_now_file(now_f, "Step 1", "aaaaaaa", mark_unverified=True, runner=r_fail)
        after_mark = now_f.read_text(encoding="utf-8")
        ok("--mark-unverified 在 CI 紅燈時維持 - [ ] 並標「CI 未綠」（exit 2）",
           rc == 2 and res["action"] == "marked_unverified"
           and "- [ ] Step 1：補齊護欄與測試（CI 未綠：failed aaaaaaa）" in after_mark
           and "還有 2 步，完成 0 步" in after_mark)

        # 6. 多個 workflow 一綠一紅：仍拒絕打勾
        r_mixed = make_runner({"ddddddd": [
            {"databaseId": 3, "workflowName": "檢查", "status": "completed", "conclusion": "success", "createdAt": "2026-11-27T01:00:00Z"},
            {"databaseId": 4, "workflowName": "安全", "status": "completed", "conclusion": "failure", "createdAt": "2026-11-27T01:01:00Z"},
        ]})
        rc, res = tick_now_file(now_f, "Step 1", "ddddddd", runner=r_mixed)
        ok("多個 workflow 一綠一紅時拒絕打勾", rc == 1 and res["ci"]["state"] == "failed")

        # 7. 同 workflow 舊失敗、重跑後最新為 success：允許打勾並移除舊的「CI 未綠」、更新進度計數
        r_rerun_ok = make_runner({"eeeeeee": [
            {"databaseId": 5, "workflowName": "檢查", "status": "completed", "conclusion": "failure", "createdAt": "2026-11-27T01:00:00Z"},
            {"databaseId": 6, "workflowName": "檢查", "status": "completed", "conclusion": "success", "url": "https://example/6", "createdAt": "2026-11-27T01:05:00Z"},
        ]})
        rc, res = tick_now_file(now_f, "Step 1", "eeeeeee", runner=r_rerun_ok)
        after_ok = now_f.read_text(encoding="utf-8")
        ok("CI 重跑轉綠時允許打勾、清除舊的 CI 未綠標記、補 SHA 並更新為「還有 1 步，完成 1 步」",
           rc == 0 and res["action"] == "ticked"
           and "- [x] Step 1：補齊護欄與測試（eeeeeee）" in after_ok
           and "CI 未綠" not in after_ok
           and "還有 1 步，完成 1 步（下坡：收尾中）" in after_ok)

        # 8. 關鍵字命中超過 1 列：拒絕修改
        rc, res = tick_now_file(now_f, "Step ", "eeeeeee", runner=r_rerun_ok)
        ok("關鍵字命中多列時拒絕修改（exit 1）", rc == 1 and "命中 2 列" in res.get("error", ""))

        # 9. audit：抓出已打勾卻 CI 紅燈的假完工
        now_f.write_text(
            "## 完工路徑\n\n- [x] Step 1：綠（eeeeeee）\n- [x] Step 2：紅（aaaaaaa）\n",
            encoding="utf-8",
        )
        r_audit = make_runner({
            "eeeeeee": [{"databaseId": 6, "workflowName": "檢查", "status": "completed", "conclusion": "success", "createdAt": "2026-11-27T01:05:00Z"}],
            "aaaaaaa": [{"databaseId": 1, "workflowName": "檢查", "status": "completed", "conclusion": "failure", "createdAt": "2026-11-27T01:00:00Z"}],
        })
        rc_a, res_a = audit_now_file(now_f, runner=r_audit)
        ok("audit 抓出已打勾但 CI 紅燈的假完工列（exit 1）",
           rc_a == 1 and res_a["items"][0]["ok"] is True and res_a["items"][1]["ok"] is False)

    print(f"\nnow_tick.py selftest：{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="NOW.md 完工路徑確定性 CI 門檻工具")
    ap.add_argument("--selftest", action="store_true", help="執行離線自我測試")
    sub = ap.add_subparsers(dest="cmd")

    p_chk = sub.add_parser("check", help="查驗單一 commit 的 CI 狀態")
    p_chk.add_argument("--commit", required=True)
    p_chk.add_argument("--project-dir")
    p_chk.add_argument("--repo", help="GitHub owner/repo（不給則從 --project-dir 推）")
    p_chk.add_argument("--workflow")
    p_chk.add_argument("--allow-no-ci", action="store_true")
    p_chk.add_argument("--json", action="store_true")

    p_tick = sub.add_parser("tick", help="查驗 CI 通過後才將 NOW.md 完工路徑指定步驟打勾")
    p_tick.add_argument("--now", required=True, help="NOW.md 路徑")
    p_tick.add_argument("--match", required=True, help="完工路徑中要打勾的步驟關鍵字（須唯一命中）")
    p_tick.add_argument("--commit", required=True, help="對應該步驟的 commit SHA")
    p_tick.add_argument("--project-dir")
    p_tick.add_argument("--repo")
    p_tick.add_argument("--workflow")
    p_tick.add_argument("--allow-no-ci", action="store_true")
    p_tick.add_argument("--mark-unverified", action="store_true", help="CI 未綠時不打勾，改標記「CI 未綠」")
    p_tick.add_argument("--dry-run", action="store_true")
    p_tick.add_argument("--json", action="store_true")

    p_aud = sub.add_parser("audit", help="審計 NOW.md 已打勾步驟的 CI 結論")
    p_aud.add_argument("--now", required=True)
    p_aud.add_argument("--project-dir")
    p_aud.add_argument("--repo")
    p_aud.add_argument("--workflow")
    p_aud.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "check":
        try:
            full_sha, _ = resolve_commit(args.commit, project_dir=args.project_dir, repo=args.repo)
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) if args.json else f"錯誤：{e}")
            return 1
        res = check_commit_ci(full_sha, repo=args.repo, project_dir=args.project_dir,
                              workflow=args.workflow, allow_no_ci=args.allow_no_ci)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"{'通過' if res['ok'] else '未通過'}（{res['state']}）：{res['reason']}")
        return 0 if res["ok"] else 1
    if args.cmd == "tick":
        rc, res = tick_now_file(
            args.now, args.match, args.commit,
            project_dir=args.project_dir, repo=args.repo, workflow=args.workflow,
            allow_no_ci=args.allow_no_ci, mark_unverified=args.mark_unverified, dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            if res.get("error"):
                print(f"錯誤：{res['error']}")
            else:
                print(f"[{res['action']}] {res['line']}")
                print(f"CI：{res['ci']['reason']}")
        return rc
    if args.cmd == "audit":
        rc, res = audit_now_file(args.now, project_dir=args.project_dir, repo=args.repo, workflow=args.workflow)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            if res.get("error"):
                print(f"錯誤：{res['error']}")
            for it in res.get("items", []):
                mark = "✓" if it["ok"] else "✗"
                print(f"{mark} {it['line']}")
                if not it["ok"]:
                    if it.get("reason"):
                        print(f"    原因：{it['reason']}")
                    for c in it.get("checks", []):
                        if not c["ok"]:
                            print(f"    原因：{c['reason']}")
        return rc
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
