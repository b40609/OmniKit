"""完工宣稱 Stop 閘（engine/scripts/done_check.py）的 pytest。

重現測試對應設計〈改動 1〉與防假完工閘門 G4：沒附回執要被判定、只有靜態列要降級、有未 push 的 commit 要擋；
預設模式為 block（強制攔截），設 OMNIKIT_DONE_CHECK=log 時只記錄不擋、stop_hook_active 放行、hook 自己出錯一律放行。fixture 全部是泛化句子。
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "engine" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import done_check as dc

BLOCK = {"OMNIKIT_DONE_CHECK": "block"}

NO_RECEIPT = "【完成待收尾】已驗證桌機與手機，errors=0"

STATIC_ONLY = """【完成待收尾】警示顏色改好了。

## 完工回執
| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |
|---|---|---|---|---|
| 型別沒壞 | 靜態 | npm run typecheck | exit 0 | 本回合第 3 次工具呼叫 |
| lint 沒錯 | 靜態 | npm run lint | exit 0 | 本回合第 4 次工具呼叫 |
沒驗的範圍：無
"""


def receipt(evidence: str = "本回合第 5 次工具呼叫", scope: str | None = "沒驗的範圍：系統匣圖示（沒有開實機看）") -> str:
    lines = ["【完成待收尾】改好了。", "", "## 完工回執",
             "| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |", "|---|---|---|---|---|",
             "| 型別沒壞 | 靜態 | npm run typecheck | exit 0 | 本回合第 4 次工具呼叫 |",
             f"| 警示改成黃色 | 實跑觀察 | 開面板截圖 | 顏色正確 | {evidence} |"]
    if scope is not None:
        lines.append(scope)
    return "\n".join(lines) + "\n"


def file_receipt(*evidence: str, scope: str = "沒驗的範圍：無") -> str:
    """每一列的證據都是檔案的回執（沒有「第幾次工具呼叫」這種量不到時間的證據）。"""
    rows = [f"| 項目 {i} | 實跑觀察 | 跑過 | 通過 | {ev} |" for i, ev in enumerate(evidence, 1)]
    return "\n".join(["【完成待收尾】改好了。", "", "## 完工回執",
                      "| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |", "|---|---|---|---|---|",
                      *rows, scope]) + "\n"


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def transcript_with_writes(tmp_path: Path, start: float, writes: list, name: str = "t.jsonl",
                           final: str | None = None, cwd: str | None = None) -> Path:
    """造一份 Claude Code 對話紀錄：start 開工，依序用 Write 寫 writes（[(路徑, 時間)]），final 是最後一則回覆。"""
    rows = [{"type": "user", "timestamp": _iso(start), "message": {"content": "開工"}}]
    for i, (fp, t) in enumerate(writes):
        rows.append({"type": "assistant", "timestamp": _iso(t), "message": {"id": f"m{i}", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "Write", "input": {"file_path": fp, "content": "x"}}]}})
    if final is not None:
        rows.append({"type": "assistant", "timestamp": _iso(start + 1), "cwd": cwd,
                     "message": {"id": "final", "content": [{"type": "text", "text": final}]}})
    tr = tmp_path / name
    tr.parent.mkdir(parents=True, exist_ok=True)
    tr.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return tr


def stop(msg: str, **extra) -> dict:
    return {"hook_event_name": "Stop", "session_id": "s-test", "last_assistant_message": msg, **extra}


def rules(result) -> set[str]:
    return {rule for rule, _ in result.problems}


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    p = subprocess.run(["git", "-C", str(repo), "-c", "core.longpaths=true", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        *args],
                       capture_output=True, text=True, env=env, check=True)
    return p.stdout


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    """每個測試的 tripwire 都寫到暫存目錄，不碰這台真的 ~/.omnikit。"""
    st = tmp_path / "state"
    monkeypatch.setenv("OMNIKIT_STATE_DIR", str(st))
    monkeypatch.delenv("OMNIKIT_TRIPWIRE_LOG", raising=False)
    monkeypatch.delenv("OMNIKIT_DONE_CHECK", raising=False)
    return st


def hits(state: Path) -> list[dict]:
    p = state / "harness" / "tripwire-hits.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else []


@pytest.fixture
def pushed_repo(tmp_path):
    """已 push 的 repo：上游用 refs/remotes/origin/main 指向 HEAD 模擬，不需要 bare repo 或網路。"""
    repo = tmp_path / "repo"
    subprocess.run(["git", "-c", "core.longpaths=true", "init", "-q", "-b", "main", str(repo)], capture_output=True, check=False)
    probe = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"], capture_output=True, check=False)
    if probe.returncode != 0:
        # Windows CI 故意把暫存路徑拉到超過 260 字元；Git for Windows 無法 chdir 進去，core.longpaths 也一樣。
        # done_check 遇到這種情況會跳過 git 檢查（放行）；這組測試在一般路徑與 Ubuntu CI 會跑。
        pytest.skip("git 無法進入超過 260 字元的路徑")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "remote", "add", "origin", "https://example.invalid/repo.git")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "config", "branch.main.remote", "origin")
    git(repo, "config", "branch.main.merge", "refs/heads/main")
    return repo


# ---- 設計裡的 3 個重現測試 ----

def test_no_receipt_is_flagged(tmp_path):
    result = dc.check(NO_RECEIPT, cwd=str(tmp_path))
    assert result.triggered
    assert "no-receipt" in rules(result)
    out = dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path)), env=BLOCK)
    assert out["decision"] == "block" and "完工回執" in out["reason"]


def test_static_only_is_downgraded_not_blocked(tmp_path):
    result = dc.check(STATIC_ONLY, cwd=str(tmp_path))
    assert result.triggered and not result.problems
    assert any("只有靜態檢查" in text for _, text in result.hints)
    out = dc.handle(stop(STATIC_ONLY, cwd=str(tmp_path)), env=BLOCK)
    assert out is not None and "decision" not in out
    assert "只有靜態檢查" in out["systemMessage"] and "【等你決定】" in out["systemMessage"]


def test_unpushed_commit_blocks_in_block_mode(pushed_repo):
    (pushed_repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(pushed_repo, "add", "b.txt")
    git(pushed_repo, "commit", "-q", "-m", "second")
    out = dc.handle(stop(receipt(), cwd=str(pushed_repo)), env=BLOCK)
    assert out["decision"] == "block" and "push" in out["reason"]
    assert "git-unpushed" in rules(dc.check(receipt(), cwd=str(pushed_repo)))


# ---- 模式與放行 ----

def test_log_mode_records_but_does_not_block(tmp_path, state):
    assert dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path)), env={}) is None
    default_rows = hits(state)
    assert default_rows and {r["mode"] for r in default_rows} == {"log"}
    assert dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path)), env=BLOCK)["decision"] == "block"
    state_log = tmp_path / "state-log"
    assert dc.handle(
        stop(NO_RECEIPT, cwd=str(tmp_path)),
        env={"OMNIKIT_DONE_CHECK": "log", "OMNIKIT_STATE_DIR": str(state_log)},
    ) is None
    rows = hits(state_log)
    assert rows and {r["hook"] for r in rows} == {"done_check"}
    assert "no-receipt" in {r["rule"] for r in rows} and {r["mode"] for r in rows} == {"log"}
    assert set(rows[0]) >= {"ts", "hook", "rule", "agent"}


def test_tripwire_log_can_be_turned_off(tmp_path, state):
    dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path)), env={"OMNIKIT_TRIPWIRE_LOG": "off"})
    assert hits(state) == []


def test_stop_hook_active_passes(tmp_path, state):
    assert dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path), stop_hook_active=True), env=BLOCK) is None
    assert hits(state) == []


def test_off_switch(tmp_path, state):
    assert dc.handle(stop(NO_RECEIPT, cwd=str(tmp_path)), env={"OMNIKIT_DONE_CHECK": "off"}) is None
    assert hits(state) == []


def test_hook_exception_passes(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("壞掉")
    monkeypatch.setattr(dc, "handle", boom)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(stop(NO_RECEIPT)).encode("utf-8"))))
    assert dc.main() == 0
    assert capsys.readouterr().out == ""


def test_bad_input_passes_as_subprocess(tmp_path):
    env = {**os.environ, **BLOCK, "OMNIKIT_STATE_DIR": str(tmp_path / "st")}
    p = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py")], input=b"not json", capture_output=True, env=env,
                       check=False)
    assert p.returncode == 0 and p.stdout == b""


def test_subprocess_block_output(tmp_path):
    env = {**os.environ, **BLOCK, "OMNIKIT_STATE_DIR": str(tmp_path / "st")}
    payload = json.dumps(stop(NO_RECEIPT, cwd=str(tmp_path)), ensure_ascii=False).encode("utf-8")
    p = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py")], input=payload, capture_output=True, env=env, check=False)
    assert p.returncode == 0 and json.loads(p.stdout.decode("utf-8"))["decision"] == "block"


# ---- 其他機械檢查 ----

def test_missing_unverified_scope_line(tmp_path):
    assert "no-scope" in rules(dc.check(receipt(scope=None), cwd=str(tmp_path)))
    assert "no-scope" in rules(dc.check(receipt(scope="沒驗的範圍："), cwd=str(tmp_path)))
    assert "no-scope" not in rules(dc.check(receipt(scope="沒驗的範圍：無"), cwd=str(tmp_path)))


def test_evidence_path_must_exist(tmp_path):
    assert "evidence-missing" in rules(dc.check(receipt("scratch/panel-after.png"), cwd=str(tmp_path)))
    shot = tmp_path / "scratch" / "panel-after.png"
    shot.parent.mkdir()
    shot.write_bytes(b"png")
    assert not rules(dc.check(receipt("scratch/panel-after.png"), cwd=str(tmp_path)))
    assert not rules(dc.check(receipt(f"`{shot}`"), cwd=str(tmp_path)))


def test_evidence_path_with_spaces_without_backticks(tmp_path):
    shot = tmp_path / "my shots" / "panel after.png"
    shot.parent.mkdir()
    shot.write_bytes(b"png")
    assert not rules(dc.check(receipt(str(shot)), cwd=str(tmp_path)))
    assert "evidence-missing" in rules(dc.check(receipt(str(tmp_path / "my shots" / "none.png")), cwd=str(tmp_path)))


def test_evidence_older_than_session_is_stale(tmp_path):
    shot = tmp_path / "old.png"
    shot.write_bytes(b"png")
    old = time.time() - 3600
    os.utime(shot, (old, old))
    assert "evidence-stale" in rules(dc.check(receipt("old.png"), cwd=str(tmp_path), session_start=time.time() - 60))
    assert not rules(dc.check(receipt("old.png"), cwd=str(tmp_path), session_start=old - 60))


def test_session_start_comes_from_transcript(tmp_path):
    """時間從對話紀錄讀。2026-11-28 照改法 4：要這段對話寫過程式碼，才拿最後一次寫程式碼的時間比。"""
    shot = tmp_path / "old.png"
    shot.write_bytes(b"png")
    old = time.time() - 3600
    os.utime(shot, (old, old))
    now = time.time()
    tr = transcript_with_writes(tmp_path, now - 60, [(str(tmp_path / "app.py"), now - 30)])
    out = dc.handle(stop(file_receipt("old.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out["decision"] == "block" and "old.png" in out["reason"]


def test_unpushed_but_declared_local_only_is_allowed(pushed_repo):
    (pushed_repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(pushed_repo, "add", "b.txt")
    git(pushed_repo, "commit", "-q", "-m", "second")
    msg = receipt().replace("改好了。", "改好了，這個 repo 沒有權限 push，只在這台。")
    assert "git-unpushed" not in rules(dc.check(msg, cwd=str(pushed_repo)))


def test_uncommitted_changes_block(pushed_repo):
    (pushed_repo / "a.txt").write_text("changed\n", encoding="utf-8")
    result = dc.check(receipt(), cwd=str(pushed_repo))
    assert "git-dirty" in rules(result)


def test_clean_pushed_repo_passes(pushed_repo):
    assert dc.handle(stop(receipt(), cwd=str(pushed_repo)), env=BLOCK) is None


def test_not_a_git_repo_is_skipped(tmp_path):
    result = dc.check(receipt(), cwd=str(tmp_path))
    assert result.triggered and not rules(result)


def test_no_label_no_done_is_not_triggered(tmp_path):
    result = dc.check("改好了，等你看過再決定要不要合併。", cwd=str(tmp_path))
    assert not result.triggered and not result.problems


def test_label_in_middle_of_sentence_is_not_a_claim(tmp_path):
    msg = "【等你決定】規則說收尾要用【完成待收尾】這類標籤開頭，這次還沒做完。"
    assert not dc.check(msg, cwd=str(tmp_path)).triggered


def test_done_file_written_this_turn_triggers(tmp_path):
    tr = tmp_path / "t.jsonl"
    done = tmp_path / "report.done"
    lines = [
        {"type": "user", "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": "做完寫 .done"}},
        {"type": "assistant", "message": {"id": "m1", "content": [
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": str(done), "content": "ok"}}]}},
    ]
    tr.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    done.write_text("ok", encoding="utf-8")  # 改法 1.2：.done 要真的寫出來才算
    data = stop("寫好了。", cwd=str(tmp_path), transcript_path=str(tr))
    out = dc.handle(data, env=BLOCK)
    assert out["decision"] == "block" and "完工回執" in out["reason"]
    # 回執寫在交付檔（同名 .md）裡也算
    (tmp_path / "report.md").write_text(receipt(), encoding="utf-8")
    assert dc.handle(data, env=BLOCK) is None


def test_done_written_in_earlier_turn_does_not_trigger(tmp_path):
    tr = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": "第一回合"}},
        {"type": "assistant", "message": {"id": "m1", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "echo ok > out/report.done"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}},
        {"type": "user", "message": {"content": "第二回合：再看一下"}},
    ]
    tr.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    assert dc.done_paths_this_turn(str(tr)) == []
    lines.append({"type": "assistant", "message": {"id": "m2", "content": [
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "echo ok > out/report.done"}}]}})
    tr.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    assert dc.done_paths_this_turn(str(tr)) == ["out/report.done"]


def test_antigravity_stop_payload(tmp_path):
    tr = tmp_path / "transcript.jsonl"
    rows = [{"type": "USER_INPUT", "source": "USER_EXPLICIT", "status": "DONE", "content": "做這個",
             "created_at": "2026-01-01T00:00:00Z", "step_index": 0},
            {"type": "PLANNER_RESPONSE", "source": "MODEL", "status": "DONE", "content": NO_RECEIPT,
             "created_at": "2026-01-01T00:00:05Z", "step_index": 1}]
    tr.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    data = {"hookEventName": "Stop", "conversationId": "c1", "transcriptPath": str(tr), "cwd": str(tmp_path),
            "terminationReason": "NO_TOOL_CALL", "continuationActive": False}
    out = dc.handle(data, env=BLOCK)
    assert out["decision"] == "continue" and "完工回執" in out["reason"]
    assert dc.handle(data, env={}) == {}
    assert dc.handle({**data, "continuationActive": True}, env=BLOCK) == {}
    assert dc.handle(data, env={"OMNIKIT_DONE_CHECK": "log"}) == {}


def test_git_add_done_and_readonly_session_do_not_false_block(pushed_repo, tmp_path):
    """三方比對誤擋根因 A、B：git add *.done 與【進行中】不誤觸發；唯讀子對話不連坐主線未提交變更。"""
    (pushed_repo / "a.txt").write_text("mainline dirty\n", encoding="utf-8")
    tr_ro = tmp_path / "readonly.jsonl"
    tr_ro.write_text(
        json.dumps({"type": "user", "timestamp": "2026-11-28T00:00:00Z", "message": {"content": "請唯讀審查"}}) + "\n",
        encoding="utf-8",
    )
    out_ro = dc.handle(stop(receipt(), cwd=str(pushed_repo), transcript_path=str(tr_ro)), env=BLOCK)
    assert out_ro is None

    tr_git_add = transcript_with_command(tmp_path, 'git add -- "OmniKit/reports/review.md.done" && git commit -m "docs"')
    assert dc.done_paths_this_turn(str(tr_git_add)) == []
    out_prog = dc.handle(stop("【進行中】已歸檔報告，等待下一階段。", cwd=str(tmp_path), transcript_path=str(tr_git_add)), env=BLOCK)
    assert out_prog is None


def test_selftest_passes():
    p = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py"), "--selftest"], capture_output=True, check=False)
    assert p.returncode == 0, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")


# ---- 審查修正 D10-R-07：表格的管線符號、程式碼區塊裡的範本、「只在這台」的否定句 ----

FAKE_UNPUSHED = {("rev-parse", "--is-inside-work-tree"): (0, "true\n"), ("status", "--porcelain"): (0, ""),
                 ("rev-list", "--count", "@{u}..HEAD"): (0, "2\n")}


def unpushed_runner(args):
    return FAKE_UNPUSHED.get(tuple(args), (1, ""))


@pytest.mark.parametrize("cmd_cell", ['`pytest -k "a\\|b"`', "`grep a | wc -l`", "grep a \\| wc -l",
                                      "``echo `a|b` ``"])
def test_pipe_inside_code_or_escaped_does_not_shift_columns(tmp_path, cmd_cell):
    """D10-R-07 之 1：驗證指令欄有 \\| 跳脫或反引號裡的 |，不能把欄位右移，讓「證據位置」讀到「結果」欄而漏檢。"""
    msg = receipt("nonexistent/missing.png").replace("開面板截圖", cmd_cell)
    assert "evidence-missing" in rules(dc.check(msg, cwd=str(tmp_path)))


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_receipt_template_in_code_block_does_not_pass(tmp_path, fence):
    """D10-R-07 之 2：把內建的 RECEIPT_FORMAT 範本包在程式碼區塊裡貼出來，不能自己通過。"""
    msg = f"【完成待收尾】好了。\n\n{fence}markdown\n{dc.RECEIPT_FORMAT}\n{fence}\n"
    assert "no-receipt" in rules(dc.check(msg, cwd=str(tmp_path)))


def test_bare_receipt_template_does_not_pass(tmp_path):
    """D10-R-07 之 2：沒包程式碼區塊、原樣貼出範本也一樣：佔位列不算一列，「沒驗的範圍」的佔位字不算有寫。"""
    result = dc.check(f"【完成待收尾】好了。\n\n{dc.RECEIPT_FORMAT}\n", cwd=str(tmp_path))
    assert {"receipt-empty", "no-scope"} <= rules(result)


def test_real_receipt_next_to_a_code_block_example_still_counts(tmp_path):
    """對照：交付檔裡有真的回執，旁邊的程式碼區塊放了範本當說明，照常用真的那一份。"""
    msg = receipt() + "\n格式說明：\n```\n" + dc.RECEIPT_FORMAT + "\n```\n"
    result = dc.check(msg, cwd=str(tmp_path))
    assert result.triggered and not rules(result)


@pytest.mark.parametrize("extra", [
    "已經 push 了，不是只在這台。",
    "這次並非只在這台。",
    "改動不只在這台。",
    "\n```\n規則：不能 push 的寫明只在這台\n```\n",
    "規則寫 `只在這台` 才不查。",
])
def test_local_only_ignores_negation_and_code(tmp_path, extra):
    """D10-R-07 之 3：「只在這台」在程式碼區塊、行內程式碼或否定句裡（不是只在這台），不能跳過未 push 的檢查。"""
    msg = receipt().replace("改好了。", "改好了。" + extra)
    assert "git-unpushed" in rules(dc.check(msg, cwd=str(tmp_path), runner=unpushed_runner))


def test_local_only_declaration_still_skips_unpushed(tmp_path):
    msg = receipt().replace("改好了。", "改好了，這個 repo 沒有權限 push，只在這台。")
    assert "git-unpushed" not in rules(dc.check(msg, cwd=str(tmp_path), runner=unpushed_runner))


# ---- 審查修正 D10-R-08：無時區的對話開始時間、含空白的 .done 路徑 ----

def test_naive_transcript_time_does_not_mark_fresh_evidence_stale(tmp_path):
    """D10-R-08 之 1：對話紀錄的時間沒帶時區時，不知道是本機時間還是 UTC，不能拿來判 evidence-stale。

    模擬 UTC+8 的本機時間（比 UTC 快 8 小時、沒帶時區）：舊版硬套 UTC，剛產生的證據檔被當成對話開始前的舊檔擋下。
    三家本機的真實紀錄都帶 Z（查證見結果檔），這是保守修法：無時區就跳過這項，不擋。
    """
    shot = tmp_path / "fresh_shot.png"
    shot.write_bytes(b"png")
    naive = (datetime.now(UTC) + timedelta(hours=8)).replace(tzinfo=None).isoformat(timespec="seconds")
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "user", "timestamp": naive, "message": {"content": "開工"}}) + "\n",
                  encoding="utf-8")
    assert dc.session_start(str(tr)) is None
    assert dc.handle(stop(receipt("fresh_shot.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


@pytest.mark.parametrize("ts", ["2026-11-27T04:00:00.123Z", "2026-11-27T04:00:00Z", "2026-11-27T12:00:00+08:00"])
def test_session_start_reads_real_transcript_time_formats(tmp_path, ts):
    """三家本機紀錄實際的格式（Claude、Codex 帶毫秒的 Z；Antigravity 不帶毫秒的 Z）都照常讀成對話開始時間。"""
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"timestamp": ts, "created_at": ts}) + "\n", encoding="utf-8")
    assert dc.session_start(str(tr)) == datetime.fromisoformat(ts).timestamp()


def transcript_with_command(tmp_path: Path, command: str, tool: str = "Bash") -> Path:
    tr = tmp_path / "t.jsonl"
    rows = [{"type": "user", "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": "做完寫 .done"}},
            {"type": "assistant", "message": {"id": "m1", "content": [
                {"type": "tool_use", "id": "t1", "name": tool, "input": {"command": command}}]}}]
    tr.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return tr


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_done_path_with_spaces_in_quotes(tmp_path, quote, tool):
    """D10-R-08 之 2：shell 指令寫進含空白資料夾的 "…/my reports/out.md.done"，要抓整段路徑，不能只抓後半截而誤擋 no-receipt。"""
    folder = tmp_path / "my reports"
    folder.mkdir()
    (folder / "out.md").write_text(receipt(), encoding="utf-8")
    done = folder / "out.md.done"
    command = (f"echo ok > {quote}{done}{quote}" if tool == "Bash"
               else f"Set-Content -Path {quote}{done}{quote} -Value ok")
    tr = transcript_with_command(tmp_path, command, tool)
    assert dc.done_paths_this_turn(str(tr)) == [str(done)]
    assert dc.handle(stop("寫好了。", cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


def test_unquoted_done_paths_are_still_found(tmp_path):
    command = "echo ok > out/report.done && cp a.md.done b/c.md.done; echo x.done.bak"
    tr = transcript_with_command(tmp_path, command)
    assert dc.done_paths_this_turn(str(tr)) == ["out/report.done", "a.md.done", "b/c.md.done"]


def test_long_command_without_done_is_linear_time(tmp_path):
    """D10-R-09（順手）：很長、沒有空白的指令（base64、長 JSON），找 .done 不能二次方回溯拖過 hook 的 15 秒逾時。"""
    tr = transcript_with_command(tmp_path, "A" * 80_000 + " > out/report.done")
    t0 = time.perf_counter()
    found = dc.done_paths_this_turn(str(tr))
    assert time.perf_counter() - t0 < 2.0
    assert found == ["out/report.done"]


# ---- 壞輸入一律放行（hook 出錯不能卡住對話） ----

@pytest.mark.parametrize("msg", [
    "【完成待收尾】\n```\n沒關的程式碼區塊 | 層級 | 證據 |",
    "【完成待收尾】\n| 需求項 | 驗證層級 | 證據位置 |\n|---|---|---|\n| `沒關的反引號 | 單元 | a.png \\",
    "【完成待收尾】\n| 層級 | 證據 |\n| \\| | \\",
    "【完成待收尾】" + "`" * 5000 + "|" * 5000,
])
def test_malformed_markdown_does_not_raise(tmp_path, msg):
    result = dc.check(msg, cwd=str(tmp_path))
    assert result.triggered
    env = {**os.environ, **BLOCK, "OMNIKIT_STATE_DIR": str(tmp_path / "st")}
    payload = json.dumps(stop(msg, cwd=str(tmp_path)), ensure_ascii=False).encode("utf-8")
    p = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py")], input=payload, capture_output=True, env=env,
                       check=False)
    assert p.returncode == 0 and p.stderr == b""


@pytest.mark.parametrize("command", ['echo "', "echo '.done'", 'x > ".done"', "\"'\"'.done", "a.done" + '"' * 3000])
def test_malformed_commands_do_not_raise(tmp_path, command):
    tr = transcript_with_command(tmp_path, command)
    assert isinstance(dc.done_paths_this_turn(str(tr)), list)


def test_replay_cli_without_limit_and_per_path_line_anchor(tmp_path):
    """回歸測試（PR #12 跨家複審 P2-1 / P2-4）：--replay 不帶 --limit 不丟 ValueError；網址埠號不掩蓋同列過期截圖。"""
    env = {**os.environ, "OMNIKIT_STATE_DIR": str(tmp_path / "st"), "USERPROFILE": str(tmp_path / "empty_home"), "HOME": str(tmp_path / "empty_home")}
    env.pop("CLAUDE_CONFIG_DIR", None)  # 跑測試的這台若有設，--replay 會去掃真的設定資料夾
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "done_check.py"), "--replay", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    rep = json.loads(proc.stdout)
    assert rep["replayed_transcripts"] == 0

    old_shot = tmp_path / "old_screen.png"
    old_shot.write_bytes(b"png")
    old_code = tmp_path / "module.py"
    old_code.write_text("x = 1\n", encoding="utf-8")
    past = time.time() - 3600
    os.utime(old_shot, (past, past))
    os.utime(old_code, (past, past))

    # 同列寫了 http://127.0.0.1:3780 與時間 11:38，不得把 :3780 / :38 當成 old_screen.png 的行號錨點
    res_stale = dc.check(
        receipt("http://127.0.0.1:3780 (11:38) old_screen.png"),
        cwd=str(tmp_path),
        session_start=time.time(),
        runner=lambda _args: (1, ""),
    )
    assert "evidence-stale" in rules(res_stale)

    # 真實寫出 module.py:1 行號錨點時，既有程式碼檔不誤判 evidence-stale
    res_anchor = dc.check(
        receipt("module.py:1"),
        cwd=str(tmp_path),
        session_start=time.time(),
        runner=lambda _args: (1, ""),
    )
    assert "evidence-stale" not in rules(res_anchor)


# ---- 2026-11-28 照完工閘誤擋三方比對報告第 5 節補的缺口 ----

@pytest.mark.parametrize("scope", [
    "沒驗的範圍：\n- 系統匣圖示（沒有開實機看）\n- 手機寬度",
    "**沒驗的範圍**：\n\n1. 系統匣圖示",
    "沒驗的範圍：\n  * 手機寬度",
])
def test_scope_header_followed_by_list_counts(tmp_path, scope):
    """「沒驗的範圍：」換行用條列寫（628166ec 實例）算有寫，不判 no-scope。"""
    assert "no-scope" not in rules(dc.check(receipt(scope=scope), cwd=str(tmp_path)))


@pytest.mark.parametrize("scope", [
    "沒驗的範圍：",
    "沒驗的範圍：\n\n## 下一步\n先等 CI",
    "沒驗的範圍：\n- \n",
    "沒驗的範圍：\n- …（沒有就寫「無」）",
])
def test_scope_header_without_content_is_still_no_scope(tmp_path, scope):
    assert "no-scope" in rules(dc.check(receipt(scope=scope), cwd=str(tmp_path)))


def test_old_reference_files_are_not_stale_when_session_wrote_no_code(tmp_path):
    """改法 4（4a6d9b12 實例）：這段對話沒寫過程式碼，引用對話開始前就有的檔案（同步 log、資料表）不判 evidence-stale。"""
    log = tmp_path / "sync.log"
    log.write_text("ok", encoding="utf-8")
    old = time.time() - 3600
    os.utime(log, (old, old))
    tr = transcript_with_writes(tmp_path, time.time() - 60, [])
    assert dc.handle(stop(file_receipt("sync.log"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


def test_old_reference_files_not_stale_when_session_wrote_only_docs(tmp_path):
    """只寫了文件（.md）不算寫程式碼，不拿來當新鮮度的基準。"""
    log = tmp_path / "sync.log"
    log.write_text("ok", encoding="utf-8")
    old = time.time() - 3600
    os.utime(log, (old, old))
    now = time.time()
    tr = transcript_with_writes(tmp_path, now - 60, [(str(tmp_path / "NOW.md"), now - 30)])
    assert dc.handle(stop(file_receipt("sync.log"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


def test_evidence_older_than_last_code_write_is_stale(tmp_path):
    """改法 4：寫過程式碼後，證據全都早於最後一次寫程式碼（就算晚於對話開始）判 evidence-stale。"""
    now = time.time()
    shot = tmp_path / "before_fix.png"
    shot.write_bytes(b"png")
    os.utime(shot, (now - 300, now - 300))
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / "app.py"), now - 60)])
    out = dc.handle(stop(file_receipt("before_fix.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out["decision"] == "block" and "before_fix.png" in out["reason"]


def test_one_fresh_evidence_after_last_code_write_is_enough(tmp_path):
    """改法 4：至少一項證據不早於最後一次寫程式碼就通過，其餘的舊檔當參考。"""
    now = time.time()
    ref = tmp_path / "spec.md"
    ref.write_text("spec", encoding="utf-8")
    os.utime(ref, (now - 3600, now - 3600))
    fresh = tmp_path / "pytest.txt"
    fresh.write_text("3 passed", encoding="utf-8")
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / "app.py"), now - 60)])
    out = dc.handle(stop(file_receipt("spec.md", "pytest.txt"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out is None


def test_tool_call_row_does_not_hide_old_runtime_evidence(tmp_path):
    """PR #13 審查 P1-2：量不到時間的列（第幾次工具呼叫）算中性，不能讓改碼前拍的截圖一起過關。"""
    now = time.time()
    shot = tmp_path / "old.png"
    shot.write_bytes(b"png")
    os.utime(shot, (now - 300, now - 300))
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / "app.py"), now - 60)])
    out = dc.handle(stop(receipt("old.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out["decision"] == "block" and "old.png" in out["reason"]


def test_old_reference_in_static_row_is_not_runtime_evidence(tmp_path):
    """只看實跑觀察、截圖這類層級的列：靜態列引用舊規格檔、實跑列是工具呼叫，不判 evidence-stale。"""
    now = time.time()
    spec = tmp_path / "spec.md"
    spec.write_text("spec", encoding="utf-8")
    os.utime(spec, (now - 3600, now - 3600))
    msg = ("【完成待收尾】改好了。\n\n## 完工回執\n| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |\n|---|---|---|---|---|\n"
           "| 符合規格 | 靜態 | 對照規格 | 符合 | spec.md |\n| 畫面正確 | 實跑觀察 | 開面板 | 正確 | 本回合第 9 次工具呼叫 |\n沒驗的範圍：無\n")
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / "app.py"), now - 60)])
    assert dc.handle(stop(msg, cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


def test_writes_outside_cwd_do_not_count_as_code_change(tmp_path):
    """PR #13 審查 P1-1：在 cwd 外寫暫存腳本或 HTML 摘要，不算這段對話改了程式碼，引用稍早的報告不判 evidence-stale。"""
    now = time.time()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    report = cwd / "sub-report.md"
    report.write_text("ok", encoding="utf-8")
    os.utime(report, (now - 600, now - 600))
    tr = transcript_with_writes(tmp_path, now - 7200, [(str(tmp_path / "scratch" / "repro.py"), now - 60),
                                                       (str(tmp_path / "scratch" / "summary.html"), now - 30)])
    assert dc.handle(stop(file_receipt("sub-report.md"), cwd=str(cwd), transcript_path=str(tr)), env=BLOCK) is None


@pytest.mark.parametrize("name", ["main.go", "lib.rs", "config.yaml", "settings.json", "schema.sql"])
def test_non_doc_file_writes_count_as_change(tmp_path, name):
    """PR #13 審查 P1-3：改法 4 寫的是「修改過檔案」，不限 CODE_EXTS；只有文件（.md 這類）不算。"""
    now = time.time()
    shot = tmp_path / "old.png"
    shot.write_bytes(b"png")
    os.utime(shot, (now - 300, now - 300))
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / name), now - 60)])
    out = dc.handle(stop(file_receipt("old.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out["decision"] == "block" and "old.png" in out["reason"]


def test_session_scan_reads_last_change(tmp_path):
    now = time.time()
    tr = transcript_with_writes(tmp_path, now - 600, [(str(tmp_path / "a.py"), now - 300),
                                                      (str(tmp_path / "test_a.py"), now - 200),
                                                      (str(tmp_path / "NOW.md"), now - 100),
                                                      (str(tmp_path.parent / "elsewhere.py"), now - 50)])
    scan = dc.session_scan(str(tr), str(tmp_path))
    assert scan.has_transcript and scan.sees_writes
    assert scan.last_code_write == pytest.approx(now - 200, abs=1)
    assert dc.session_scan(None).last_code_write is None


def _agy_transcript(tmp_path: Path, start: float, final: str) -> Path:
    """照本機 Antigravity 紀錄的真實形狀：工具呼叫放在 PLANNER_RESPONSE.tool_calls[]，沒有頂層 TOOL_CALL。"""
    rows = [{"source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": _iso(start), "content": "開工"},
            {"source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": _iso(time.time() - 60),
             "tool_calls": [{"name": "write_file", "args": {"Path": str(tmp_path / "app.py"), "Content": "x"}}]},
            {"source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": _iso(time.time() - 1), "content": final}]
    tr = tmp_path / "agy.jsonl"
    tr.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return tr


def _agy_user(t: float) -> dict:
    return {"source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": _iso(t), "content": "開工"}


def _agy_call(name: str, t: float, **args) -> dict:
    return {"source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": _iso(t), "tool_calls": [{"name": name, "args": args}]}


def _agy_final(t: float, msg: str) -> dict:
    return {"source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": _iso(t), "content": msg}


def _agy_rows(path: Path, rows: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return path


def _agy_stop(tr: Path, cwd: Path) -> dict:
    return {"hookEventName": "Stop", "conversationId": "c", "transcriptPath": str(tr), "cwd": str(cwd),
            "terminationReason": "NO_TOOL_CALL"}


UNIT_ONLY = ("【完成待收尾】改好了。\n\n## 完工回執\n| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |\n|---|---|---|---|---|\n"
             "| 計算正確 | 單元 | pytest | 3 passed | 本回合第 3 次工具呼叫 |\n沒驗的範圍：無\n")


def test_antigravity_session_scan_reads_planner_tool_calls(tmp_path):
    """Antigravity 的寫檔在 PLANNER_RESPONSE.tool_calls[]：write_file／edit_file 用 Path，
    write_to_file／replace_file_content／multi_replace_file_content 用 TargetFile；本機紀錄約一半的參數值是 JSON 字串（帶引號）。"""
    now = time.time()
    q = json.dumps
    tr = _agy_rows(tmp_path / "logs" / "transcript.jsonl", [
        _agy_user(now - 600),
        _agy_call("write_file", now - 500, Path=q(str(tmp_path / "old_turn.py")), Content=q("x")),
        _agy_user(now - 400),
        _agy_call("replace_file_content", now - 300, TargetFile=str(tmp_path / "app.py"), ReplacementContent="y"),
        _agy_call("multi_replace_file_content", now - 250, TargetFile=q(str(tmp_path / "pkg" / "mod.ts"))),
        _agy_call("edit_file", now - 200, Path=str(tmp_path / "test_app.py"), Target="a", Replacement="b"),
        _agy_call("write_to_file", now - 150, TargetFile=q(str(tmp_path / "NOTES.md")), CodeContent=q("n")),
        _agy_call("write_file", now - 100, Path=q(str(tmp_path.parent / "elsewhere.py"))),
        _agy_call("view_file", now - 90, AbsolutePath=q(str(tmp_path / "read_only.py"))),
        _agy_call("run_command", now - 50, CommandLine=q('git commit -m "x"'), Cwd=q(str(tmp_path))),
        _agy_final(now - 1, "好了"),
    ])
    scan = dc.session_scan(str(tr), str(tmp_path))
    assert scan.has_transcript and scan.sees_writes
    assert scan.touched == {"old_turn.py", "app.py", "pkg/mod.ts", "test_app.py", "NOTES.md"}
    assert scan.changed_code  # app.py 是這一回合（最後一則 USER_INPUT 之後）改的
    assert scan.committed
    assert scan.last_code_write == pytest.approx(now - 200, abs=1)  # 測試檔算改檔；NOTES.md 是文件、elsewhere.py 在 cwd 外
    assert scan.turn_started == pytest.approx(now - 400, abs=1)


def test_antigravity_previous_turn_write_is_not_this_turn_change(tmp_path):
    now = time.time()
    tr = _agy_rows(tmp_path / "agy.jsonl", [
        _agy_user(now - 600),
        _agy_call("write_file", now - 500, Path=str(tmp_path / "app.py")),
        _agy_user(now - 100),
        _agy_final(now - 1, "好了"),
    ])
    scan = dc.session_scan(str(tr), str(tmp_path))
    assert scan.touched == {"app.py"} and not scan.changed_code


def test_antigravity_uncommitted_write_blocks_git_dirty(pushed_repo):
    """Antigravity 改了檔沒 commit 就宣告完工：git-dirty 要查得到（以前 touched 一直是空的，整段跳過）。"""
    (pushed_repo / "a.txt").write_text("changed\n", encoding="utf-8")
    now = time.time()
    tr = _agy_rows(pushed_repo.parent / "agy.jsonl", [
        _agy_user(now - 60),
        _agy_call("write_file", now - 30, Path=json.dumps(str(pushed_repo / "a.txt"))),
        _agy_final(now - 1, receipt()),
    ])
    ev = dc.evaluate(_agy_stop(tr, pushed_repo), env=BLOCK)
    assert ev.agy and "git-dirty" in rules(ev.result)


def test_antigravity_code_change_needs_runtime_proof(tmp_path):
    """Antigravity 這一回合改了程式，回執只有單元測試：no-runtime-proof 要查得到。"""
    now = time.time()
    tr = _agy_rows(tmp_path / "agy.jsonl", [
        _agy_user(now - 60),
        _agy_call("replace_file_content", now - 30, TargetFile=json.dumps(str(tmp_path / "app.py"))),
        _agy_final(now - 1, UNIT_ONLY),
    ])
    ev = dc.evaluate(_agy_stop(tr, tmp_path), env=BLOCK)
    assert "no-runtime-proof" in rules(ev.result)


def test_antigravity_stale_compares_with_last_write(tmp_path):
    """看得到 Antigravity 的寫檔後，evidence-stale 跟 Claude Code 一樣比最後一次改檔（改法 4），不再退回對話開始時間。
    PR #13 審查 P0-1 的退回做法只剩 Codex。"""
    now = time.time()
    shot = tmp_path / "before_fix.png"
    shot.write_bytes(b"png")
    os.utime(shot, (now - 300, now - 300))  # 對話開始後拍的，但早於最後一次改檔
    tr = _agy_transcript(tmp_path, now - 7200, file_receipt("before_fix.png"))
    assert dc.session_scan(str(tr), str(tmp_path)).sees_writes is True
    out = dc.handle(_agy_stop(tr, tmp_path), env=BLOCK)
    assert out["decision"] == "continue" and "before_fix.png" in out["reason"]
    os.utime(shot, (now, now))  # 改完才拍：放行
    assert dc.handle(_agy_stop(tr, tmp_path), env=BLOCK) == {}


def test_codex_falls_back_to_session_start_for_stale(tmp_path):
    """PR #13 審查 P0-1：Codex rollout 也看不到寫檔，退回對話開始時間逐項比。"""
    now = time.time()
    shot = tmp_path / "old.png"
    shot.write_bytes(b"png")
    os.utime(shot, (now - 86400, now - 86400))
    tr = tmp_path / "rollout.jsonl"
    rows = [{"timestamp": _iso(now - 7200), "type": "session_meta", "payload": {"timestamp": _iso(now - 7200)}},
            {"timestamp": _iso(now - 60), "type": "response_item",
             "payload": {"type": "custom_tool_call", "name": "apply_patch", "input": "*** Update File: app.py"}}]
    tr.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
    out = dc.handle(stop(file_receipt("old.png"), cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK)
    assert out["decision"] == "block" and "old.png" in out["reason"]


@pytest.mark.parametrize("scope", [
    "## 沒驗的範圍\n- 手機寬度",
    "### 沒驗的範圍：\n- 手機寬度",
    "## 沒驗的範圍\n\n無",
    "**沒驗的範圍**\n- 手機寬度",
    "沒驗的範圍：\n無",
    "沒驗的範圍：\n1、手機寬度",
    "沒驗的範圍：\n（1）手機寬度",
    "沒驗的範圍：\n- [ ] 手機寬度",
])
def test_scope_heading_and_newline_forms_count(tmp_path, scope):
    """PR #13 審查 P1-4（改法 3.4）：標題式、粗體不加冒號、換行寫「無」、頓號與括號編號都算有寫。"""
    assert "no-scope" not in rules(dc.check(receipt(scope=scope), cwd=str(tmp_path)))


@pytest.mark.parametrize("scope", [
    "沒驗的範圍：\n- - -",
    "沒驗的範圍：\n- [ ]",
    "沒驗的範圍：\n\n\n\n- 下一步：等 CI 跑完再 merge",
    "## 沒驗的範圍\n\n## 下一步\n- 等 CI",
])
def test_scope_false_positives_are_still_no_scope(tmp_path, scope):
    assert "no-scope" in rules(dc.check(receipt(scope=scope), cwd=str(tmp_path)))


def test_table_row_mentioning_level_and_evidence_is_not_a_receipt(tmp_path):
    """改法 3.3：一般表格的資料列剛好提到「層級」與「證據」，下一列不是分隔列，不能當成回執表頭。"""
    msg = ("【完成待收尾】改好了。\n\n| 欄位 | 說明 |\n|---|---|\n| 驗證層級 | 證據位置要寫路徑 |\n| a | b |\n"
           "沒驗的範圍：無\n")
    assert "no-receipt" in rules(dc.check(msg, cwd=str(tmp_path)))


def test_cross_repo_relative_evidence_resolves_from_deliverable(tmp_path):
    """PR #13 審查 P1-5（改法 4.2）：回執在別的資料夾的交付檔裡，相對證據先照交付檔所在資料夾解析；
    解不到的降成提示，不判 evidence-missing。"""
    cwd = tmp_path / "repo"
    cwd.mkdir()
    other = tmp_path / "status" / "reports"
    other.mkdir(parents=True)
    (other / "evidence.txt").write_text("3 passed", encoding="utf-8")
    deliverable = other / "r.md"
    done = other / "r.md.done"
    tr = transcript_with_writes(tmp_path, time.time() - 600, [(str(done), time.time() - 5)])
    done.write_text("", encoding="utf-8")
    deliverable.write_text(file_receipt("evidence.txt"), encoding="utf-8")
    assert dc.handle(stop("寫好了。", cwd=str(cwd), transcript_path=str(tr)), env=BLOCK) is None
    deliverable.write_text(file_receipt("not-here.txt"), encoding="utf-8")
    r = dc.check("寫好了。", cwd=str(cwd), done_paths=[str(done)])
    assert "evidence-missing" not in rules(r) and any(rule == "evidence-unverifiable" for rule, _ in r.hints)


def test_done_only_mentioned_in_command_does_not_trigger(tmp_path):
    """PR #13 審查 P1-6（改法 1.2）：指令文字裡提到 .done、檔案其實沒寫出來，不算這一回合寫了 .done。"""
    command = 'cat > repro.py <<EOF\n(rep / "r.md.done").write_text("")\nEOF'
    tr = transcript_with_command(tmp_path, command)
    assert dc.handle(stop("寫好了。", cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


def test_done_written_before_this_turn_does_not_trigger(tmp_path):
    old = tmp_path / "old.md.done"
    old.write_text("", encoding="utf-8")
    past = time.time() - 86400 * 365 * 10  # transcript_with_command 的回合開在 2026-01-01，比它更早
    os.utime(old, (past, past))
    tr = transcript_with_command(tmp_path, f"echo ok > {old}")
    assert dc.handle(stop("寫好了。", cwd=str(tmp_path), transcript_path=str(tr)), env=BLOCK) is None


@pytest.mark.parametrize("args", [["--since", "yesterday"], ["--since", "2026/11/28"], ["--limit", "abc"], ["--since"],
                                  ["--since", "--json"]])
def test_replay_cli_rejects_bad_arguments_without_traceback(tmp_path, args):
    env = {**os.environ, "OMNIKIT_STATE_DIR": str(tmp_path / "st"), "USERPROFILE": str(tmp_path), "HOME": str(tmp_path)}
    env.pop("CLAUDE_CONFIG_DIR", None)
    proc = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py"), "--replay", *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, check=False)
    assert proc.returncode == 2 and "Traceback" not in proc.stderr and proc.stderr.strip()


def test_replay_limit_counts_replayed_not_skipped_and_reports_triggered(tmp_path):
    home, other, st = _replay_home(tmp_path)
    for i in range(3):  # 最新的 3 份都找不到 cwd
        tp = transcript_with_writes(home / ".claude" / "projects" / "p", time.time() - 60, [], f"nocwd{i}.jsonl",
                                    NO_RECEIPT)
        os.utime(tp, (time.time() + 10 + i, time.time() + 10 + i))
    rep = dc.replay_history(state_dir=st, home_dir=home, limit=3, extra_dirs=[other])
    assert rep["replayed_transcripts"] == 3 and rep["triggered"] == 3


def test_replay_labels_same_named_config_dirs_apart(tmp_path):
    home, _, st = _replay_home(tmp_path)
    twin = tmp_path / "elsewhere" / ".claude"
    transcript_with_writes(twin / "projects" / "p", time.time() - 60, [], "e.jsonl", NO_RECEIPT,
                           str(tmp_path / "work"))
    rep = dc.replay_history(state_dir=st, home_dir=home, limit=50, extra_dirs=[twin])
    assert sum(rep["by_config_dir"].values()) == 3 and len(rep["by_config_dir"]) == 3


def _replay_home(tmp_path: Path):
    home = tmp_path / "home"
    work = tmp_path / "work"
    work.mkdir()
    st = tmp_path / "replay-state"
    cwd = str(work)
    transcript_with_writes(home / ".claude" / "projects" / "p", time.time() - 60, [], "a.jsonl", NO_RECEIPT, cwd)
    transcript_with_writes(home / ".claude-kai" / "projects" / "p", time.time() - 60, [], "b.jsonl",
                           receipt(scope=None), cwd)
    transcript_with_writes(home / ".claude-kai" / "projects" / "p" / "s1" / "subagents", time.time() - 60, [],
                           "c.jsonl", NO_RECEIPT, cwd)
    other = tmp_path / "custom-config"
    transcript_with_writes(other / "projects" / "p", time.time() - 60, [], "d.jsonl", NO_RECEIPT, cwd)
    transcript_with_writes(home / ".claude" / "projects" / "p", time.time() - 60, [], "nocwd.jsonl", NO_RECEIPT)
    return home, other, st


def test_replay_scans_every_claude_config_dir_and_counts_rule_codes(tmp_path):
    """改法 5：回放掃所有 ~/.claude*/projects 與 CLAUDE_CONFIG_DIR，排除子代理；規則用代號統計（no-scope 這類文字比對抓不到）。"""
    home, other, st = _replay_home(tmp_path)
    rep = dc.replay_history(state_dir=st, home_dir=home, limit=50, extra_dirs=[other])
    assert rep["replayed_transcripts"] == 3
    assert rep["skipped_no_cwd"] == 1
    assert rep["would_block"] == 3
    assert rep["by_rule"] == {"no-receipt": 2, "no-scope": 1}
    assert rep["by_config_dir"] == {".claude": 1, ".claude-kai": 1, "custom-config": 1}


def test_replay_since_filters_old_transcripts(tmp_path):
    home, other, st = _replay_home(tmp_path)
    old = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    a = home / ".claude" / "projects" / "p" / "a.jsonl"
    os.utime(a, (old, old))
    rep = dc.replay_history(state_dir=st, home_dir=home, limit=50, extra_dirs=[other], since="2026-11-01")
    assert rep["replayed_transcripts"] == 2 and rep["by_rule"] == {"no-receipt": 1, "no-scope": 1}


def test_replay_cli_reads_claude_config_dir_and_since(tmp_path):
    home, other, st = _replay_home(tmp_path)
    env = {**os.environ, "OMNIKIT_STATE_DIR": str(st), "USERPROFILE": str(home), "HOME": str(home),
           "CLAUDE_CONFIG_DIR": str(other)}
    proc = subprocess.run([sys.executable, str(SCRIPTS / "done_check.py"), "--replay", "--json", "--since", "2026-01-01"],
                          capture_output=True, text=True, encoding="utf-8", env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["by_config_dir"] == {".claude": 1, ".claude-kai": 1, "custom-config": 1}


def test_fake_green_rules_match_wiring_audit():
    """E：done_check 的 skip 規則跟 wiring_audit 共用同一組，兩邊改一邊沒改要在這裡紅。"""
    import wiring_audit as wa

    assert dc.FAKE_GREEN_LINE_RE.pattern == "(?:" + "|".join(p.pattern for _, p in wa.FAKE_GREEN_PATTERNS) + ")"
    assert dc.CI_SWALLOW_LINE_RE.pattern == wa.CI_SWALLOW_RE.pattern
    assert (dc.TEST_FILE_NAME_RE.pattern, dc.TEST_FILE_NAME_RE.flags) == (wa.TEST_FILE_RE.pattern, wa.TEST_FILE_RE.flags)
    # 樣本用拼接寫，原始碼這一行本身才不會被 wiring_audit 的 diff 掃描當成新增的假綠燈
    sk, only, todo, x = ".skip", ".only", ".todo", "x"
    samples = [f"test{sk}('x', () => {{}})", f"test{sk}(cond, 'mac only')", f"{x}it('a')", f"describe{only}(",
               f"it{todo}('t')", f"@pytest.mark{sk}(reason='x')", f"@pytest.mark{sk}if(sys.platform == 'win32')",
               f"@unittest{sk}('x')", "expect(skip).toBe(1)"]
    assert sum(bool(dc.FAKE_GREEN_LINE_RE.search(s)) for s in samples) == 6
    for s in samples:
        assert bool(dc.FAKE_GREEN_LINE_RE.search(s)) == any(p.search(s) for _, p in wa.FAKE_GREEN_PATTERNS), s
