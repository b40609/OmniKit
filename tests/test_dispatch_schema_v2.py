"""Phase 1 單元測試：dispatch.py 去噪計量 Schema v2、源頭寫入防呆、v1 非破壞性回溯瀑布流、
複合缺陷覆寫保護（Defect-Override Guard）、Wilson CI、annotations.jsonl 覆寫、
log.fields 契約漂移檢查、model_eval.py weekly_diff 去噪對接與 backfill-audit 零寫改驗證。

嚴守 PR #14 隔離鐵律：所有狀態讀寫均隔離在 pytest tmp_path，絕不觸碰真實家目錄設定。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "engine" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dispatch  # noqa: E402
import model_eval  # noqa: E402
import profiles  # noqa: E402

POL = dispatch.policy(ROOT / "data")
T0 = datetime(2026, 11, 29, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """強制將 profiles.STATE 與家目錄環境變數導向 tmp_path，杜絕污染真實 ~/.omnikit 或 ~/.claude*。"""
    fake_home = tmp_path / "fake_home"
    fake_state = fake_home / ".omnikit"
    fake_home.mkdir(parents=True, exist_ok=True)
    fake_state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("OMNIKIT_STATE_DIR", str(fake_state))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(fake_home / ".claude"))
    monkeypatch.setattr(profiles, "STATE", fake_state)
    return fake_state


def _ns(**overrides):
    base = dict(
        task="docs",
        cls="claude-sonnet",
        thinking="medium",
        verdict="pass",
        first_pass=None,
        retries=0,
        retries_infra=None,
        retries_quality=None,
        escalations=0,
        final_class=None,
        origin=None,
        role=None,
        infra=None,
        scope=None,
        scope_capped=False,
        unverified=False,
        subject_pass=None,
        model_ok=None,
        defect=None,
        duration_sec=None,
        work=None,
        eval_ref_json=None,
        channel="native",
        instance=None,
        level=None,
        project="OmniKit",
        control=False,
        error=None,
        error_text=None,
        note=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ---------- 1. Schema v2 寫入、正交推導與舊 CLI 向後相容 ----------


def test_make_record_schema_v2_fields_and_auto_inference():
    rec = dispatch.make_record(POL, _ns(), "2026-11-29-1", "default", "OmniKit", now=T0)
    assert tuple(rec.keys()) == dispatch.LOG_FIELDS
    assert set(rec.keys()) == set(POL["log"]["fields"])
    assert rec["schema_version"] == 2
    assert rec["origin"] == "field"
    assert rec["role"] == "author"
    assert rec["infra_issue"] is None
    assert rec["scope"] == "complete"
    assert rec["unverified"] is False
    assert rec["subject_pass"] is None
    assert rec["model_ok"] is True
    assert rec["defect_kind"] is None
    assert rec["retries_infra"] == 0 and rec["retries_quality"] == 0
    assert rec["judged_model"] == "claude-sonnet-5-5"
    assert rec["judged_thinking"] == "medium"
    assert rec["duration_sec"] is None and rec["work_id"] is None and rec["eval_ref"] is None
    assert "role" in rec["inferred"] and "model_ok" in rec["inferred"]


def test_make_record_verify_defaults_and_subject_pass_no():
    # verify 未傳 --role 時預設 reviewer；抓出被審物 bug 記 --verdict pass --subject-pass no -> model_ok=True
    catch_rec = dispatch.make_record(
        POL,
        _ns(
            task="verify",
            cls="claude-opus",
            thinking="xhigh",
            verdict="pass",
            retries=1,
            subject_pass="no",
            duration_sec=142.5,
            work="wp-42",
            eval_ref_json='{"run_id": "t2-01", "arm": "A"}',
        ),
        "2026-11-29-1",
        "default",
        "OmniKit",
        now=T0,
    )
    assert catch_rec["role"] == "reviewer"
    assert catch_rec["subject_pass"] is False
    assert catch_rec["model_ok"] is True
    assert catch_rec["first_pass"] is False
    assert catch_rec["duration_sec"] == 142.5
    assert catch_rec["work_id"] == "wp-42"
    assert catch_rec["eval_ref"] == {"run_id": "t2-01", "arm": "A"}


def test_make_record_scope_capped_unverified_and_infra_mapping():
    # 12 組上限封頂：scope=="capped_by_caller" 且 verdict=="partial" 且無 defect -> model_ok=True
    cap_rec = dispatch.make_record(
        POL,
        _ns(task="readonly", cls="gemini-fast", thinking="xhigh", verdict="partial", scope_capped=True),
        "2026-11-29-1",
        "default",
        "OmniKit",
        now=T0,
    )
    assert cap_rec["scope"] == "capped_by_caller"
    assert cap_rec["model_ok"] is True

    # unverified -> model_ok=None
    unv_rec = dispatch.make_record(
        POL,
        _ns(task="readonly", cls="gemini-fast", thinking="xhigh", verdict="partial", unverified=True),
        "2026-11-29-1",
        "default",
        "OmniKit",
        now=T0,
    )
    assert unv_rec["unverified"] is True
    assert unv_rec["model_ok"] is None

    # error_kind 自動映射 infra_issue，且未通過時 model_ok=None
    mapping_cases = [
        ("quota_exhausted", "quota"),
        ("rate_limit", "rate_limit"),
        ("model_forbidden", "model_unavailable"),
        ("auth_expired", "auth"),
        ("timeout_15min", "harness_timeout"),
        ("other", "harness_tooling"),
    ]
    for err_k, exp_infra in mapping_cases:
        r = dispatch.make_record(POL, _ns(verdict="fail", error=err_k, retries=2), "v", "default", "OmniKit", now=T0)
        assert r["infra_issue"] == exp_infra
        assert r["model_ok"] is None
        assert r["retries_infra"] == 2 and r["retries_quality"] == 0


def test_legacy_cli_invocation_backward_compatible(isolated_state: Path, capsys: pytest.CaptureFixture[str]):
    # SKILL.md:142 舊範例原樣呼叫不壞，且正確推導 final_class 對應的 judged_model
    rc = dispatch.main([
        "log",
        "--task", "docs",
        "--class", "claude-sonnet",
        "--thinking", "medium",
        "--verdict", "pass",
        "--escalations", "1",
        "--final-class", "claude-opus",
    ])
    assert rc == 0
    out_lines = capsys.readouterr().out.strip().splitlines()
    logged = json.loads(out_lines[0])
    assert logged["schema_version"] == 2
    assert logged["class"] == "claude-sonnet"
    assert logged["final_class"] == "claude-opus"
    assert logged["judged_model"] == "claude-opus-5-5"
    assert logged["first_pass"] is False
    assert logged["model_ok"] is False
    saved, bad = dispatch.read_log(dispatch.log_path(isolated_state))
    assert len(saved) == 1 and bad == 0


# ---------- 2. 源頭寫入防呆（make_record 強制擋下） ----------


def test_make_record_guardrails_block_ambiguous_writes():
    # 1. 顯式 --model-ok no 卻沒給 --defect -> SystemExit
    with pytest.raises(SystemExit, match="--defect"):
        dispatch.make_record(POL, _ns(verdict="fail", model_ok="no"), "v", "default", "OmniKit", now=T0)

    # 給了 --defect 即可通過
    ok_def = dispatch.make_record(
        POL, _ns(verdict="fail", model_ok="no", defect="wrong_fact"), "v", "default", "OmniKit", now=T0
    )
    assert ok_def["model_ok"] is False and ok_def["defect_kind"] == "wrong_fact"

    # 2. reviewer 且 --verdict fail 卻沒給 --subject-pass 也沒給 --infra / --error -> SystemExit
    with pytest.raises(SystemExit, match="--subject-pass no"):
        dispatch.make_record(
            POL, _ns(task="verify", cls="claude-opus", thinking="xhigh", verdict="fail"), "v", "default", "OmniKit", now=T0
        )

    # 帶了 --infra 即可記環境故障
    rev_infra = dispatch.make_record(
        POL,
        _ns(task="verify", cls="claude-opus", thinking="xhigh", verdict="fail", infra="quota"),
        "v",
        "default",
        "OmniKit",
        now=T0,
    )
    assert rev_infra["model_ok"] is None and rev_infra["infra_issue"] == "quota"

    # 3. 非 reviewer/judge 傳 --subject-pass -> SystemExit
    with pytest.raises(SystemExit, match="reviewer"):
        dispatch.make_record(POL, _ns(task="docs", subject_pass="no"), "v", "default", "OmniKit", now=T0)

    # 4. --scope-capped 與 --scope complete 衝突 -> SystemExit
    with pytest.raises(SystemExit, match="衝突"):
        dispatch.make_record(POL, _ns(scope="complete", scope_capped=True), "v", "default", "OmniKit", now=T0)


# ---------- 3. v1 回溯瀑布流與複合缺陷覆寫保護（Defect-Override Guard） ----------


@pytest.mark.parametrize(
    ("sample_id", "row", "exp_model_ok", "exp_attr", "exp_extra"),
    [
        (
            "#1_timeout_plus_missed_cuda",
            {
                "ts": "2026-11-14T01:00:00+00:00",
                "task": "readonly",
                "level": "medium",
                "class": "gemini-pro",
                "model": "gemini-4-hydrogen",
                "thinking": "high",
                "verdict": "partial",
                "first_pass": False,
                "retries": 1,
                "escalations": 0,
                "final_class": "gemini-pro",
                "error_kind": None,
                "note": "兩輪都因 15 分鐘無輸出被 T3 停掉；事後發現漏掉官方 cuda-gpu 變體，結論不可靠",
            },
            False,
            "compound_defect",
            {"infra_issue": "harness_timeout", "defect_kind": "missed_requirement"},
        ),
        (
            "#18_cap15_plus_wrong_numbers",
            {
                "ts": "2026-11-15T01:00:00+00:00",
                "task": "readonly",
                "level": "medium",
                "class": "gemini-pro",
                "model": "gemini-4-hydrogen",
                "thinking": "high",
                "verdict": "partial",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "gemini-pro",
                "error_kind": None,
                "note": "跑滿 15 組上限沒有飽和（上限是主控設的）；1 個數字對不上（原文 20% 與 84%，報告寫 37% 到 55%）",
            },
            False,
            "compound_defect",
            {"scope": "capped_by_caller", "defect_kind": "wrong_fact"},
        ),
        (
            "#27_gitbash_plus_false_positive",
            {
                "ts": "2026-11-16T01:00:00+00:00",
                "task": "readonly",
                "level": "medium",
                "class": "claude-sonnet",
                "model": "claude-sonnet-5-5",
                "thinking": "medium",
                "verdict": "pass",
                "first_pass": False,
                "retries": 1,
                "escalations": 0,
                "final_class": "claude-sonnet",
                "error_kind": None,
                "note": "第一次失敗是呼叫端 Git Bash 路徑轉換；主控逐項核對，12 項裡 2 項誤報",
            },
            False,
            "compound_defect",
            {"infra_issue": "harness_tooling", "defect_kind": "wrong_fact"},
        ),
        (
            "#32_quota_reset_plus_unfounded_claims",
            {
                "ts": "2026-11-17T01:00:00+00:00",
                "task": "risk",
                "level": "high",
                "class": "gemini-pro",
                "model": "gemini-4-hydrogen",
                "thinking": "xhigh",
                "verdict": "partial",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "gemini-pro",
                "error_kind": None,
                "note": "額度重置後重派，拆兩份平行；查到 3 個成立的缺陷，4 條經核對不成立",
            },
            False,
            "compound_defect",
            {"infra_issue": "quota", "defect_kind": "wrong_fact"},
        ),
        (
            "#65_unverified_delivery",
            {
                "ts": "2026-11-20T01:00:00+00:00",
                "task": "readonly",
                "level": "medium",
                "class": "gemini-flash",
                "model": "gemini-3.8-flash",
                "thinking": "high",
                "verdict": "partial",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "gemini-flash",
                "error_kind": None,
                "note": "台股替代資料源飽和調研，交付完成，內容待主控查證",
            },
            None,
            "unverified",
            {"unverified": True},
        ),
        (
            "#7_verify_caught_22_bugs",
            {
                "ts": "2026-11-14T05:00:00+00:00",
                "task": "verify",
                "level": "verify",
                "class": "claude-opus",
                "model": "claude-opus-5-5",
                "thinking": "high",
                "verdict": "fail",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "claude-opus",
                "error_kind": None,
                "note": "架構圖原型獨立驗收：抓到光束、動畫截斷、內容錯誤等 22 項，已修",
            },
            True,
            "verify_subject_fail",
            {"role": "reviewer", "subject_pass": False},
        ),
        (
            "pure_skipped",
            {
                "ts": "2026-11-21T01:00:00+00:00",
                "task": "synthesis",
                "level": "high",
                "class": "claude-fable",
                "model": "claude-fable-5-2",
                "thinking": "high",
                "verdict": "skipped",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "claude-fable",
                "error_kind": None,
                "note": "依指令開啟獨立頂層對話供討論",
            },
            None,
            "skipped",
            {},
        ),
        (
            "pure_scope_cap_12_groups",
            {
                "ts": "2026-11-21T02:00:00+00:00",
                "task": "readonly",
                "level": "medium",
                "class": "claude-sonnet",
                "model": "claude-sonnet-5-5",
                "thinking": "medium",
                "verdict": "partial",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "claude-sonnet",
                "error_kind": None,
                "note": "帳號池調研：12 組未飽和，報告完整，結論有一手證據",
            },
            True,
            "scope_cap_partial",
            {"scope": "capped_by_caller"},
        ),
        (
            "zero_false_positive_not_misclassified",
            {
                "ts": "2026-11-24T01:00:00+00:00",
                "task": "readonly",
                "level": "high",
                "class": "claude-fable",
                "model": "claude-fable-5-2",
                "thinking": "high",
                "verdict": "pass",
                "first_pass": False,
                "retries": 0,
                "escalations": 1,
                "final_class": "claude-opus",
                "error_kind": "model_forbidden",
                "note": "優化檢視；無 Fable 改 Opus xhigh；交叉審查 27 條 0 誤報",
            },
            None,
            "infra_quota",
            {"infra_issue": "model_unavailable", "judged_model": "claude-opus-5-5", "judged_thinking": "xhigh"},
        ),
        (
            "false_claim_no_file_change",
            {
                "ts": "2026-11-25T01:00:00+00:00",
                "task": "readonly",
                "level": "high",
                "class": "claude-fable",
                "model": "claude-fable-5-2",
                "thinking": "high",
                "verdict": "partial",
                "first_pass": False,
                "retries": 0,
                "escalations": 0,
                "final_class": "claude-fable",
                "error_kind": None,
                "note": "內容經交叉審查 0 誤報，但跑必跑測試覆寫正式快照卻宣稱沒改檔",
            },
            False,
            "model_defect",
            {"defect_kind": "false_claim"},
        ),
    ],
)
def test_project_record_v1_waterfall_and_compound_guard(sample_id, row, exp_model_ok, exp_attr, exp_extra):
    orig_copy = copy.deepcopy(row)
    proj = dispatch.project_record(row, pol=POL)
    assert row == orig_copy, f"{sample_id}: project_record 不可原地改動傳入 dict"
    assert proj["model_ok"] is exp_model_ok, sample_id
    assert proj["failure_attribution"] == exp_attr, sample_id
    if exp_attr == "compound_defect":
        assert "compound_defect" in proj["inferred"], sample_id
    for k, v in exp_extra.items():
        assert proj[k] == v, f"{sample_id}: {k} 預期 {v!r}，實際 {proj.get(k)!r}"


# ---------- 4. (level, judged_model, judged_thinking) 拆開 gemini-pro 混模型、Wilson CI 與 annotations 覆寫 ----------


def test_wilson_ci_precision_and_edges():
    assert dispatch.wilson_ci(0, 0) == [0.0, 0.0]
    lo9, hi9 = dispatch.wilson_ci(9, 9)
    assert abs(lo9 - 0.7008) < 0.002 and hi9 == 1.0
    lo25, hi25 = dispatch.wilson_ci(25, 25)
    assert lo25 > 0.85 and hi25 == 1.0
    lo0, hi0 = dispatch.wilson_ci(0, 10)
    assert lo0 == 0.0 and 0.25 < hi0 < 0.30


def test_stats_splits_mixed_gemini_pro_models_and_computes_summaries():
    rows = []
    # 9 筆歷史 class=gemini-pro 但實際 model=gemini-4-hydrogen (high)
    for i in range(9):
        rows.append({
            "ts": f"2026-11-15T00:00:{i:02d}+00:00",
            "level": "medium",
            "task": "readonly",
            "channel": "delegate_task",
            "instance": "ag_1",
            "class": "gemini-pro",
            "model": "gemini-4-hydrogen",
            "thinking": "high",
            "verdict": "pass",
            "first_pass": True,
            "retries": 0,
            "escalations": 0,
            "final_class": "gemini-pro",
            "duration_sec": 30.0 + i,
        })
    # 25 筆新制 class=gemini-pro 且實際 model=gemini-4-neon (xhigh) -> 25/25 應觸發 ceiling_warn
    for i in range(25):
        rows.append({
            "ts": f"2026-11-26T00:00:{i:02d}+00:00",
            "schema_version": 2,
            "origin": "field",
            "role": "author",
            "level": "medium",
            "task": "code-small",
            "channel": "delegate_task",
            "instance": "ag_1",
            "class": "gemini-pro",
            "model": "gemini-4-neon",
            "thinking": "xhigh",
            "judged_model": "gemini-4-neon",
            "judged_thinking": "xhigh",
            "verdict": "pass",
            "first_pass": True,
            "model_ok": True,
            "retries": 0,
            "escalations": 0,
            "final_class": "gemini-pro",
            "duration_sec": 60.0,
        })
    # 1 筆 origin=eval 不應計入 clean_table
    rows.append({
        "ts": "2026-11-27T00:00:00+00:00",
        "schema_version": 2,
        "origin": "eval",
        "role": "author",
        "level": "medium",
        "task": "code-small",
        "channel": "delegate_task",
        "instance": "ag_1",
        "class": "gemini-pro",
        "model": "gemini-4-neon",
        "thinking": "xhigh",
        "judged_model": "gemini-4-neon",
        "judged_thinking": "xhigh",
        "verdict": "fail",
        "first_pass": False,
        "model_ok": False,
        "defect_kind": "other",
        "retries": 0,
        "escalations": 0,
        "final_class": "gemini-pro",
    })
    # 2 筆 reviewer（1 筆抓蟲 subject_pass=False、1 筆無蟲 subject_pass=True）+ 1 筆 infra quota
    rows.extend([
        {
            "ts": "2026-11-28T01:00:00+00:00",
            "schema_version": 2,
            "origin": "field",
            "role": "reviewer",
            "level": "verify",
            "task": "verify",
            "channel": "delegate_task",
            "instance": "cl_1",
            "class": "claude-opus",
            "model": "claude-opus-5-5",
            "thinking": "xhigh",
            "judged_model": "claude-opus-5-5",
            "judged_thinking": "xhigh",
            "verdict": "pass",
            "first_pass": False,
            "retries": 1,
            "escalations": 0,
            "final_class": "claude-opus",
            "subject_pass": False,
            "model_ok": True,
        },
        {
            "ts": "2026-11-28T02:00:00+00:00",
            "schema_version": 2,
            "origin": "field",
            "role": "reviewer",
            "level": "verify",
            "task": "verify",
            "channel": "delegate_task",
            "instance": "cl_1",
            "class": "claude-opus",
            "model": "claude-opus-5-5",
            "thinking": "xhigh",
            "judged_model": "claude-opus-5-5",
            "judged_thinking": "xhigh",
            "verdict": "pass",
            "first_pass": True,
            "retries": 0,
            "escalations": 0,
            "final_class": "claude-opus",
            "subject_pass": True,
            "model_ok": True,
        },
        {
            "ts": "2026-11-28T03:00:00+00:00",
            "schema_version": 2,
            "origin": "field",
            "role": "author",
            "level": "high",
            "task": "major-change",
            "channel": "delegate_task",
            "instance": "cl_1",
            "class": "claude-fable",
            "model": "claude-fable-5-2",
            "thinking": "high",
            "judged_model": "claude-fable-5-2",
            "judged_thinking": "high",
            "verdict": "fail",
            "first_pass": False,
            "retries": 0,
            "escalations": 0,
            "final_class": "claude-fable",
            "infra_issue": "quota",
            "model_ok": None,
        },
    ])

    s = dispatch.stats(POL, rows)
    # 舊版 table 仍把 35 筆 (9+25+1) 聚在 ("medium", "gemini-pro")
    raw_gp = next(r for r in s["table"] if r["level"] == "medium" and r["class"] == "gemini-pro")
    assert raw_gp["n"] == 35

    # 新版 clean_table 乾淨拆開 hydrogen 與 neon，且排除 origin=eval 與 model_ok=None
    by_key = {(c["level"], c["judged_model"], c["judged_thinking"]): c for c in s["clean_table"]}
    hyd = by_key[("medium", "gemini-4-hydrogen", "high")]
    neon = by_key[("medium", "gemini-4-neon", "xhigh")]
    assert hyd["n"] == 9 and hyd["ok"] == 9 and hyd["ceiling_warn"] is False and hyd["median_duration_sec"] == 34.0
    assert abs(hyd["wilson_ci"][0] - 0.7008) < 0.002
    assert neon["n"] == 25 and neon["ok"] == 25 and neon["ceiling_warn"] is True and neon["median_duration_sec"] == 60.0

    # verify_summary 與 infra_summary
    assert s["verify_summary"]["reviewer_total"] == 2
    assert s["verify_summary"]["caught_n"] == 1
    assert s["verify_summary"]["catch_rate"] == 0.5
    cl_infra = next(x for x in s["infra_summary"] if x["instance"] == "cl_1")
    assert cl_infra["infra_count"] == 1 and cl_infra["issues"] == {"quota": 1}

    # CLI 文字模式雙視圖檢查
    txt_both = dispatch.stats_text(s, mode="both")
    txt_raw = dispatch.stats_text(s, mode="raw")
    txt_clean = dispatch.stats_text(s, mode="clean")
    assert "原始一次通過率" in txt_both and "去噪模型良率" in txt_both
    assert "去噪模型良率" not in txt_raw
    assert "原始一次通過率" not in txt_clean and "觸頂警示" in txt_clean and "n<20" in txt_clean


def test_annotations_override_without_mutating_log(isolated_state: Path):
    lp = dispatch.log_path(isolated_state)
    row = {
        "ts": "2026-11-25T10:00:00+00:00",
        "project": "OmniKit",
        "task": "synthesis",
        "level": "high",
        "channel": "delegate_task",
        "instance": "ag_main",
        "class": "gemini-pro",
        "model": "gemini-4-neon",
        "thinking": "xhigh",
        "verdict": "pass",
        "first_pass": False,
        "retries": 5,
        "escalations": 0,
        "final_class": "gemini-pro",
        "note": "多批合併完成 PR #4",
    }
    dispatch.append(lp, row)
    before_sha = hashlib.sha256(lp.read_bytes()).hexdigest()

    # 未覆寫前：無 infra 與缺陷詞但 retries=5 -> model_defect
    p_before = dispatch.project_record(row, pol=POL)
    assert p_before["model_ok"] is False and p_before["failure_attribution"] == "model_defect"

    # 寫入 annotations.jsonl 覆寫為多批封頂合格
    ap = dispatch.annotations_path(isolated_state)
    fp = dispatch.record_fingerprint(row)
    ap.write_text(
        json.dumps({"key": fp, "model_ok": True, "defect_kind": None, "scope": "capped_by_caller", "reason": "人工複核為多批切片"}) + "\n",
        encoding="utf-8",
    )
    anns = dispatch.read_annotations(isolated_state)
    assert fp in anns
    p_after = dispatch.project_record(row, annotations=anns, pol=POL)
    assert p_after["model_ok"] is True
    assert p_after["failure_attribution"] == "scope_cap_partial"
    assert "annotation" in p_after["inferred"]

    # backfill_audit 驗證原 log.jsonl SHA-256 完全未變
    rep = dispatch.backfill_audit(lp, annotations=anns, pol=POL)
    assert rep["zero_mutation"] is True
    assert rep["log_sha256"] == before_sha
    assert rep["annotated_count"] == 1
    assert rep["defect_total"] == 0


# ---------- 5. check() 偵測 log.fields 漂移 與 model_eval.py weekly_diff 去噪不誤退 ----------


def test_check_detects_log_fields_drift():
    assert dispatch.check(POL) == []
    drifted = copy.deepcopy(POL)
    drifted["log"]["fields"] = [
        "ts", "project", "task", "level", "channel", "instance",
        "model", "thinking", "first_pass", "retries", "escalations",
        "final_model", "verdict", "error_kind", "rules_version", "profile", "control", "note",
    ]
    errs = dispatch.check(drifted)
    assert any("log.fields" in e and "final_model" in e and "final_class" in e for e in errs)


def test_trials_and_weekly_diff_denoise_quota_and_verify_catches(isolated_state: Path):
    # 若不扣噪：試用模型 29 筆含 5 筆撞額度 fail + 3 筆 verify 抓蟲 fail + 1 筆 eval fail -> first_pass 僅 20/29 = 69.0%（誤退回！）
    # 去噪後：5 筆撞額度 model_ok=None 排除、1 筆 eval 排除、3 筆 verify 抓蟲 model_ok=True -> 去噪良率 23/23 = 100%
    # （Wilson 95% CI 下限 0.8569 > 0.85，不誤退且觸發 ceiling_warn！）
    tr_doc = model_eval.load_trials(isolated_state)
    tr_doc["models"]["claude-sonnet-5-5"] = {
        "status": "trial",
        "role": "medium",
        "baseline": "claude-opus",
        "smoke": {},
    }
    model_eval.save_trials(isolated_state, tr_doc, now=T0)

    lp = dispatch.log_path(isolated_state)
    # 20 筆正常 pass
    for i in range(20):
        dispatch.append(lp, {
            "ts": T0.isoformat(),
            "schema_version": 2,
            "origin": "field",
            "role": "author",
            "level": "medium",
            "task": "docs",
            "class": "claude-sonnet",
            "model": "claude-sonnet-5-5",
            "thinking": "medium",
            "judged_model": "claude-sonnet-5-5",
            "judged_thinking": "medium",
            "verdict": "pass",
            "first_pass": True,
            "model_ok": True,
        })
    # 3 筆 verify 抓出被審物真問題（舊制 first_pass=False，新制 subject_pass=False, model_ok=True）
    for i in range(3):
        dispatch.append(lp, {
            "ts": T0.isoformat(),
            "schema_version": 2,
            "origin": "field",
            "role": "reviewer",
            "level": "medium",
            "task": "verify",
            "class": "claude-sonnet",
            "model": "claude-sonnet-5-5",
            "thinking": "medium",
            "judged_model": "claude-sonnet-5-5",
            "judged_thinking": "medium",
            "verdict": "fail",
            "first_pass": False,
            "subject_pass": False,
            "model_ok": True,
        })
    # 5 筆純撞額度（只填 v2 infra_issue="quota"，未填舊 error_kind）
    for i in range(5):
        dispatch.append(lp, {
            "ts": T0.isoformat(),
            "schema_version": 2,
            "origin": "field",
            "role": "author",
            "level": "medium",
            "task": "docs",
            "class": "claude-sonnet",
            "model": "claude-sonnet-5-5",
            "thinking": "medium",
            "judged_model": "claude-sonnet-5-5",
            "judged_thinking": "medium",
            "verdict": "fail",
            "first_pass": False,
            "error_kind": None,
            "infra_issue": "quota",
            "model_ok": None,
        })
    # 1 筆 eval 失敗（origin="eval"，不可污染實地統計）
    dispatch.append(lp, {
        "ts": T0.isoformat(),
        "schema_version": 2,
        "origin": "eval",
        "role": "author",
        "level": "medium",
        "task": "docs",
        "class": "claude-sonnet",
        "model": "claude-sonnet-5-5",
        "thinking": "medium",
        "judged_model": "claude-sonnet-5-5",
        "judged_thinking": "medium",
        "verdict": "fail",
        "first_pass": False,
        "model_ok": False,
        "defect_kind": "other",
    })
    # 基準 claude-opus 20 筆中 19 筆通過（95%）
    for i in range(20):
        dispatch.append(lp, {
            "ts": T0.isoformat(),
            "schema_version": 2,
            "origin": "field",
            "role": "author",
            "level": "medium",
            "task": "docs",
            "class": "claude-opus",
            "model": "claude-opus-5-5",
            "thinking": "medium",
            "judged_model": "claude-opus-5-5",
            "judged_thinking": "medium",
            "verdict": "pass" if i < 19 else "fail",
            "first_pass": i < 19,
            "model_ok": i < 19,
            "defect_kind": None if i < 19 else "other",
        })

    rows, _ = dispatch.read_log(lp)
    st = dispatch.stats(POL, rows)
    tr_res = st["trials"]["sonnet-trial"][0]
    assert tr_res["revert"] is False
    assert tr_res["trial_n"] == 23 and tr_res["trial_rate"] == 1.0
    assert tr_res["raw_trial_n"] == 29 and round(tr_res["raw_trial_rate"], 4) == round(20 / 29, 4)

    diff = model_eval.weekly_diff(
        isolated_state,
        ROOT / "data",
        {"thinking_preference": "max_available"},
        days=7,
        now=T0,
    )
    by_kind = {it["kind"]: it for it in diff["items"]}
    assert "trial_promote" in by_kind and "trial_demote" not in by_kind
    assert "ceiling_warn" in by_kind
    assert diff["recent_quota_hits"] == 5
    assert "thinking_downgrade_hint" in by_kind


def test_cli_backfill_audit_json_and_zero_mutation(isolated_state: Path, capsys: pytest.CaptureFixture[str]):
    lp = dispatch.log_path(isolated_state)
    dispatch.append(lp, {
        "ts": "2026-11-18T00:00:00+00:00",
        "task": "readonly",
        "level": "medium",
        "class": "gemini-pro",
        "model": "gemini-4-hydrogen",
        "thinking": "high",
        "verdict": "partial",
        "first_pass": False,
        "retries": 1,
        "escalations": 0,
        "final_class": "gemini-pro",
        "note": "兩輪都因 15 分鐘無輸出被 T3 停掉；事後發現漏掉官方 cuda-gpu 變體，結論不可靠",
    })
    before_bytes = lp.read_bytes()
    before_sha = hashlib.sha256(before_bytes).hexdigest()

    rc = dispatch.main(["backfill-audit", "--json"])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["log_sha256"] == before_sha
    assert rep["zero_mutation"] is True
    assert rep["total"] == 1 and rep["unreadable_lines"] == 0
    assert rep["defect_total"] == 1
    assert rep["defects"][0]["failure_attribution"] == "compound_defect"
    assert lp.read_bytes() == before_bytes


def test_context_falls_back_cleanly_in_worktree_when_gitignored_profile_absent(isolated_state: Path):
    # 模擬 profile.json 指向被 .gitignore 忽略、不在當前 worktree 的個人 profile
    (isolated_state / "profile.json").write_text('{"profile": "missing-local-profile"}\n', encoding="utf-8")
    _, st, name, folder = dispatch.context()
    assert st == isolated_state
    assert name == "default"
    assert folder is not None and (folder / "AGENTS.md").is_file()


