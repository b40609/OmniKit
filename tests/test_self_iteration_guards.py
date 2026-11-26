"""自我迭代護欄單元測試（覆蓋 Fable 跨家審查 P1-1～P1-10 邊界案例）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "engine" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import doctor  # noqa: E402
import profiles  # noqa: E402
import validate  # noqa: E402


def test_review_markers_validation_and_strip(tmp_path: Path):
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    (data / "profiles" / "default").mkdir(parents=True)
    (data / "rules" / "baseline.md").write_text(
        "# 底線\n## 標題 <!-- review_on: 2026-11-28 reason: 測試 -->\n正常行 # <!-- review_on: 2026-12-01 無reason前綴也可 -->\n",
        encoding="utf-8",
    )
    (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n", encoding="utf-8")

    assert validate.check_review_markers(data) == []
    composed = profiles.compose_shared(data)
    assert "## 標題\n" in composed
    assert "正常行\n" in composed
    assert "review_on" not in composed

    # 非法日期與跨行殘破標記必須報錯，絕不靜默吞掉
    (data / "profiles" / "default" / "AGENTS.md").write_text(
        "# default\n<!-- review_on: 2026-13-45 -->\n<!-- review_on:\n2026-12-01 -->\n",
        encoding="utf-8",
    )
    errs = validate.check_review_markers(data)
    assert any("日期不合法" in e for e in errs)
    assert any("僅解析成功" in e for e in errs)


def test_patches_and_budget_all_layers(tmp_path: Path):
    data = tmp_path / "data"
    skills = tmp_path / "skills"
    (data / "rules").mkdir(parents=True)
    (data / "profiles" / "default").mkdir(parents=True)
    (data / "rules" / "baseline.md").write_text("# 底線\n安全第一\n", encoding="utf-8")
    (data / "profiles" / "default" / "AGENTS.md").write_text("# default\n這是一段個人規則文字\n", encoding="utf-8")

    sd = skills / "omnikit-demo"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text("---\nname: omnikit-demo\ndescription: 自動觸發描述\n---\n", encoding="utf-8")
    sd_manual = skills / "ok-demo"
    sd_manual.mkdir(parents=True)
    (sd_manual / "SKILL.md").write_text(
        "---\nname: ok-demo\ndescription: 手動捷徑不算入自動預算\ndisable-model-invocation: true\n---\n",
        encoding="utf-8",
    )

    # 1. patches.yaml 反例：重複 id、缺欄位、檔案不存在
    (data / "rules" / "patches.yaml").write_text(
        "patches:\n"
        "  - id: p1\n    file: data/rules/nope.md\n    section: s\n    born_at: '2026-11-26'\n    why: w\n    retire_check: r\n"
        "  - id: p1\n    file: data/rules/baseline.md\n    section: ''\n    born_at: '2026-11-26'\n    why: w\n    retire_check: r\n",
        encoding="utf-8",
    )
    p_errs = validate.check_patches(data)
    assert any("指向不存在的檔案" in e for e in p_errs)
    assert any("重複" in e for e in p_errs)
    assert any("缺少必填字串欄位 section" in e for e in p_errs)

    # 2. budget.yaml 四層同時超標皆能抓出，且執行期 validate.check() 不被 budget 阻斷
    (data / "rules" / "budget.yaml").write_text(
        "limits:\n"
        "  antigravity_shared_max_bytes: 10\n"
        "  antigravity_personal_max_bytes: 10\n"
        "  codex_combined_max_bytes: 10\n"
        "  auto_skill_desc_max_bytes: 5\n",
        encoding="utf-8",
    )
    b_errs, stats = validate.check_budget(data, skills)
    assert len(b_errs) == 4
    assert stats["auto_skill_count"] == 1

    # 3. 壞掉的 budget.yaml：doctor 仍必須輸出一列 FAIL（P1-4）
    (data / "rules" / "patches.yaml").unlink()
    (data / "rules" / "budget.yaml").write_text("limits: bad\n", encoding="utf-8")
    inv_rows = doctor.check_repo_invariants(tmp_path)
    assert any(r["item"] == "常駐預算棘輪" and r["status"] == doctor.FAIL for r in inv_rows)


def test_governance_status_and_tripwire_state_dir(tmp_path: Path):
    data = tmp_path / "data"
    (data / "rules").mkdir(parents=True)
    (data / "tools").mkdir(parents=True)
    (data / "rules" / "baseline.md").write_text("# 底線 <!-- review_on: 2026-11-28 reason: 到期測試 -->\n", encoding="utf-8")
    (data / "tools" / "t1.yaml").write_text(
        "id: t1\nname: T1\nslots: [s]\nstatus: trial\ndecided_at: '2026-11-14'\nreason: r\ntrial_until: '2026-11-28'\nadded: '2026-11-14'\n",
        encoding="utf-8",
    )
    (data / "tools" / "d1.yaml").write_text(
        "id: d1\nname: D1\nslots: [s]\nstatus: default\ndecided_at: '2026-11-04'\nreason: r\nadded: '2026-11-04'\n",
        encoding="utf-8",
    )
    (data / "tools" / "bad_doc.yaml").write_text(
        "id: bad_doc\nname: B\nslots: [s]\nstatus: default\ndecided_at: '2026-11-26'\nreason: r\n"
        "baseline_eval:\n  verified_at: '2026-11-26'\n  verified_model: m\n  verdict: essential_infra\n"
        "  eval_doc: data/evals/missing.md\nadded: '2026-11-26'\n",
        encoding="utf-8",
    )
    assert any("missing.md" in e for e in validate.check_baseline_eval_docs(data))
    gov_before = validate.governance_status(data, today="2026-11-27")
    assert gov_before["expired_trials"] == [] and gov_before["due_reviews"] == []
    assert gov_before["unverified_defaults"] == ["d1"]

    gov_on_day = validate.governance_status(data, today="2026-11-28")
    assert gov_on_day["expired_trials"] == [("t1", "2026-11-28")]
    assert len(gov_on_day["due_reviews"]) == 1

    # P1-1 & P1-10：驗證 claim_check.py 支援 OMNIKIT_STATE_DIR 並與 doctor.check_tripwire_stats 對齊
    st_dir = tmp_path / "custom-state"
    payload = {
        "session_id": "sess-123",
        "last_assistant_message": "這裡沒有工具可以做這件事，請你手動處理。",
    }
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "claim_check.py")],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        check=False,
        env={**os.environ, "OMNIKIT_STATE_DIR": str(st_dir), "OMNIKIT_CLAIM_CHECK": "1", "OMNIKIT_TRIPWIRE_LOG": "1"},
    )
    assert proc.returncode == 0 and b'"block"' in proc.stdout
    tw_rows = doctor.check_tripwire_stats(st_dir)
    assert "近 30 天 1 次／累計 1 次" in tw_rows[0]["detail"]
    assert "claim_check:" in tw_rows[0]["detail"]
