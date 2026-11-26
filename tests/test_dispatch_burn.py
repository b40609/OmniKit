"""2026-11-26 事件修正：Fable 宣告與實測不符、model_forbidden 退下一個、門檻對要派的實例判定（KIT-A-04）、
第二意見看額度到期（second_opinion_burn）。"""
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "scripts"))
import account_pool as ap
import dispatch

T0 = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
FABLE = "claude-fable-5-2"
POL = dispatch.policy(ROOT / "data")
RYAN = dispatch.personal(ROOT / "data" / "profiles" / "ryan")

# 測試用的假實例名（共用層邏輯不依賴真實帳號名）
MINE = {"instances": {
    "c_a": {"driver": "claudeAgent", "classes": ["claude-opus", "claude-fable"]},
    "c_b": {"driver": "claudeAgent", "classes": ["claude-opus"]},
    "ag": {"driver": "antigravity", "classes": ["gemini-pro", "gemini-carbon"]},
}}


def pick(table, level, cls, kind="route"):
    return next(o for o in table[level]["options"] if o["class"] == cls and o["kind"] == kind)


def rows(ids_drivers):
    return [{"id": i, "driver": d, "account": i, "auto": (True, "")} for i, d in ids_drivers]


def write_claude_cache(home, iid, used, reset):
    d = home / ".t3" / "caches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{iid}.json").write_text(json.dumps({"usageLimits": {"checkedAt": ap.iso_utc(T0), "windows": [
        {"id": "five_hour", "usedPercent": 5, "resetsAt": ap.iso_utc(T0 + timedelta(hours=3))},
        {"id": "seven_day", "usedPercent": used, "resetsAt": ap.iso_utc(reset)}]}}), encoding="utf-8")


def write_agy_cache(home, iid, used, reset):
    d = home / ".t3" / "caches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{iid}.json").write_text(json.dumps({"usageLimits": {"checkedAt": ap.iso_utc(T0), "windows": [
        {"id": "gemini-weekly", "usedPercent": used, "resetsAt": ap.iso_utc(reset)}]}}), encoding="utf-8")


@pytest.fixture
def auto_ok(monkeypatch):
    import accounts
    monkeypatch.setattr(accounts, "can_auto", lambda r, what, now=None: (True, ""))


def claude_q(tmp_path, ids, home):
    t3_raw = {i: {"driver": "claudeAgent", "config": {"homePath": f"~/.{i}"}} for i in ids}
    return ap.claude_quotas(tmp_path / "state", rows([(i, "claudeAgent") for i in ids]), None, 80,
                            home=home, t3_raw=t3_raw, now=T0)


# ---------- 第 1 項：profile 修正 ----------

def test_ryan_profile_fable_only_on_native_and_claudeagent():
    t = dispatch.resolved(POL, RYAN, "claude")
    assert pick(t, "high", "claude-fable")["instances"] == ["native", "claudeAgent"]
    assert pick(t, "architecture", "claude-fable")["instances"] == ["native", "claudeAgent"]
    assert pick(t, "high", "claude-fable", "second_opinion")["instances"] == ["native", "claudeAgent"]
    for lv in t.values():
        for o in lv["options"]:
            if o["class"] == "claude-fable":
                assert "claudeAgent_2" not in o["instances"] and "claudeAgent_claude_kai" not in o["instances"]


# ---------- 第 2 項：未實測標示與 model_forbidden 退下一個 ----------

def test_opt_in_class_without_success_record_is_marked_unverified():
    t = dispatch.resolved(POL, MINE, "claude", verified=set())
    o = pick(t, "high", "claude-fable")
    assert o["unverified"] == ["c_a"] and o["instances"] == ["native", "c_a"]
    t2 = dispatch.resolved(POL, MINE, "claude", verified={("c_a", FABLE)})
    assert pick(t2, "high", "claude-fable")["unverified"] == []
    # 一般類別不標
    assert pick(t, "higher", "claude-opus")["unverified"] == []
    assert "未實測：c_a" in dispatch.show_text(t, "x", True, pol=POL, mine=MINE)


def test_verified_pairs_reads_log_and_ignores_escalated_failures(tmp_path):
    log = dispatch.log_path(tmp_path)
    log.parent.mkdir(parents=True)
    lines = [
        {"instance": "c_a", "class": "claude-fable", "model": FABLE, "verdict": "pass", "error_kind": None, "final_class": "claude-fable"},
        {"instance": "c_b", "class": "claude-fable", "model": FABLE, "verdict": "pass", "error_kind": "model_forbidden", "final_class": "claude-opus"},
    ]
    log.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    got = dispatch.verified_pairs(tmp_path)
    assert ("c_a", FABLE) in got and ("c_b", FABLE) not in got


def test_model_forbidden_falls_back_to_next_option(tmp_path):
    st = tmp_path / "state"
    mine = {"instances": {
        "c_a": {"driver": "claudeAgent", "classes": ["claude-opus", "claude-fable"]},
        "c_b": {"driver": "claudeAgent", "classes": ["claude-opus", "claude-fable"]},
    }}
    ap.record_error(st, "c_b", "model_forbidden", driver="claudeAgent", model=FABLE, now=T0)

    def judge(iid, model):
        blk, why, _ = ap.is_blocked(ap.load_state(st), iid, driver="claudeAgent", model=model, now=T0)
        return (not blk), why

    # 同一級的下一個實例：c_b 被擋，Fable 改走 c_a，Opus 照用 c_b
    t = dispatch.resolved(POL, mine, "codex", judge)
    fable = pick(t, "architecture", "claude-fable")
    assert fable["instances"] == ["c_a"] and fable["blocked"][0]["instance"] == "c_b"
    assert "model_forbidden" in fable["blocked"][0]["why"]
    # 全部 Fable 實例都被擋（而且沒有原生子代理）：退到同一級的 Opus 備援
    ap.record_error(st, "c_a", "model_forbidden", driver="claudeAgent", model=FABLE, now=T0)
    t = dispatch.resolved(POL, mine, "codex", judge)
    assert pick(t, "architecture", "claude-fable")["skip"]
    opus = pick(t, "architecture", "claude-opus")
    assert not opus["skip"] and opus["instances"] == ["c_a", "c_b"] and opus["superseded"] is None


# ---------- KIT-A-04：門檻對要派的實例判定，來源與 claude_quotas 一致 ----------

def test_t3_cache_only_85_percent_is_over_threshold(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 85, T0 + timedelta(days=4))
    write_claude_cache(home, "c_b", 30, T0 + timedelta(days=4))
    qs = claude_q(tmp_path, ["c_a", "c_b"], home)
    assert not dispatch.usage_path(tmp_path / "state").exists()  # 沒有狀態列快照
    assert dispatch.weekly_usage(tmp_path / "state", 80)["over"] is None  # 舊路徑：未知
    u = dispatch.weekly_usage(tmp_path / "state", 80, instance="c_a", quotas=qs)
    assert u["over"] is True and u["pct"] == 85.0 and u["source"] == "t3_cache"
    assert dispatch.weekly_usage(tmp_path / "state", 80, instance="c_b", quotas=qs)["over"] is False
    mine = {"instances": {"c_a": {"driver": "claudeAgent", "classes": ["claude-fable"]},
                          "c_b": {"driver": "claudeAgent", "classes": ["claude-fable"]}}}
    usage = {q["instance"]: dispatch.instance_usage(q, 80) for q in qs}
    fable = pick(dispatch.resolved(POL, mine, "codex", usage=usage), "high", "claude-fable")
    assert fable["instances"] == ["c_b"]
    assert fable["blocked"][0]["instance"] == "c_a" and "85%" in fable["blocked"][0]["why"]
    line = dispatch.quota_summary_text(qs, 80)
    assert "c_a 85%（已達）" in line and "c_b 30%（未達）" in line


# ---------- 第 3 項：第二意見看額度到期 ----------

def test_within_hours_matches_weekly_first():
    assert POL["second_opinion_burn"]["within_hours"] * 3600 == ap.EXPIRING_SOON_SEC
    assert dispatch.check(POL, RYAN) == []


def test_shared_layer_burn_rule_has_no_personal_instance_names():
    # 這次新增的共用層內文：常駐的 dispatch.md 與政策檔的 second_opinion_burn 段（含上方註解）
    pol_txt = (ROOT / "data" / "rules" / "dispatch-policy.md").read_text(encoding="utf-8")
    start = pol_txt.index("# 第二意見看額度到期")
    burn_txt = pol_txt[start:pol_txt.index("usage_signal:", start)]
    for label, txt in (("dispatch.md", (ROOT / "data" / "rules" / "dispatch.md").read_text(encoding="utf-8")),
                       ("second_opinion_burn", burn_txt)):
        for name in ("claudeAgent_2", "claudeAgent_claude_kai", "antigravity_ryan", "retis", "Ryan", "Kai"):
            assert name not in txt, f"{label} 出現個人實例名 {name}"


def test_burn_triggers_same_vendor_review_when_claude_expiring(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 40, T0 + timedelta(hours=27))   # 週剩 60%，27 小時後重置
    write_claude_cache(home, "c_b", 68, T0 + timedelta(hours=28))   # 週剩 32%
    write_agy_cache(home, "ag", 10, T0 + timedelta(days=6))         # Gemini 12-03 才重置
    qs = claude_q(tmp_path, ["c_a", "c_b"], home)
    rs = rows([("c_a", "claudeAgent"), ("c_b", "claudeAgent"), ("ag", "antigravity")])
    cands = ap.burn_candidates(rs, MINE, qs, ap._empty_state(), within_hours=48, min_remaining_pct=20, now=T0, home=home)
    assert [c["instance"] for c in cands["claudeAgent"]] == ["c_a", "c_b"]
    assert "antigravity" not in cands
    burn = dispatch.burn_decision(POL, MINE, cands, "claude")
    assert burn["triggered"] and burn["author_driver"] == "claudeAgent"
    sw = {s["author_class"]: s for s in burn["swaps"]}
    assert sw["claude-fable"]["class"] == "claude-opus" and sw["claude-fable"]["thinking"] == "xhigh"
    assert sw["claude-fable"]["instances"][:2] == ["c_a", "c_b"]  # 快到期的排前面
    assert sw["claude-opus"]["class"] == "claude-fable" and sw["claude-opus"]["thinking"] == "high"
    for s in burn["swaps"]:
        assert POL["model_classes"][s["class"]]["model"] != POL["model_classes"][s["author_class"]]["model"]
    text = "\n".join(dispatch.burn_lines(burn))
    assert "改判" in text and "距週重置 < 48 小時" in text and "沒有快到期的額度" in text
    t = dispatch.resolved(POL, MINE, "claude")
    shown = dispatch.show_text(t, "x", True, pol=POL, mine=MINE, burn=burn)
    assert "額度到期改判：審 Claude 產出時改用上方「第二意見改判」" in shown


def test_burn_not_triggered_when_other_vendor_also_expiring_or_low_remaining(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 40, T0 + timedelta(hours=27))
    write_claude_cache(home, "c_b", 85, T0 + timedelta(hours=20))   # 週剩 15% < 20%，不算
    write_agy_cache(home, "ag", 30, T0 + timedelta(hours=30))       # Gemini 也快到期
    qs = claude_q(tmp_path, ["c_a", "c_b"], home)
    rs = rows([("c_a", "claudeAgent"), ("c_b", "claudeAgent"), ("ag", "antigravity")])
    cands = ap.burn_candidates(rs, MINE, qs, ap._empty_state(), within_hours=48, min_remaining_pct=20, now=T0, home=home)
    assert [c["instance"] for c in cands["claudeAgent"]] == ["c_a"]
    assert [c["instance"] for c in cands["antigravity"]] == ["ag"]
    burn = dispatch.burn_decision(POL, MINE, cands, "claude")
    assert not burn["triggered"] and "都有快到期的額度" in burn["reason"]
    assert not dispatch.burn_decision(POL, MINE, {}, "claude")["triggered"]


def test_burn_forced_by_user_named_accounts(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_b", 20, T0 + timedelta(days=5))     # 不快到期
    qs = claude_q(tmp_path, ["c_a", "c_b"], home)
    rs = rows([("c_a", "claudeAgent"), ("c_b", "claudeAgent"), ("ag", "antigravity")])
    assert ap.burn_candidates(rs, MINE, qs, ap._empty_state(), now=T0, home=home) == {}
    cands = ap.burn_candidates(rs, MINE, qs, ap._empty_state(), forced=["c_b"], now=T0, home=home)
    assert cands["claudeAgent"][0]["forced"] and "使用者指定要燒" in cands["claudeAgent"][0]["why"]
    burn = dispatch.burn_decision(POL, MINE, cands, "claude")
    assert burn["triggered"]
    assert {s["author_class"]: s for s in burn["swaps"]}["claude-fable"]["instances"][0] == "c_b"


def test_burn_skips_blocked_and_manual_accounts(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 40, T0 + timedelta(hours=27))
    qs = claude_q(tmp_path, ["c_a"], home)
    doc = ap._empty_state()
    doc["accounts"]["c_a"] = {**ap._empty_account(), "paused": True}
    rs = rows([("c_a", "claudeAgent")])
    assert ap.burn_candidates(rs, MINE, qs, doc, now=T0, home=home) == {}
    manual = {"instances": {"c_a": {"driver": "claudeAgent", "classes": []}}}
    assert ap.burn_candidates(rs, manual, qs, ap._empty_state(), now=T0, home=home) == {}


def test_check_rejects_same_model_or_cross_vendor_mapping():
    import copy
    bad = copy.deepcopy(POL)
    bad["second_opinion_burn"]["same_vendor"]["claude-opus"] = {"class": "claude-opus", "thinking": "xhigh"}
    bad["second_opinion_burn"]["same_vendor"]["claude-fable"] = {"class": "gemini-carbon", "thinking": "high"}
    errs = dispatch.check(bad)
    assert any("同一個模型不能審自己" in e for e in errs)
    assert any("改判要同一家" in e for e in errs)


# ---------- 帳號訂閱到期（profile 的 access_ends） ----------

def _sel_rows(ends):
    import accounts
    rs = []
    for iid, end in ends.items():
        r = {"id": iid, "driver": "claudeAgent", "account": iid, "usage_scope": "auto_dispatch", "in_t3": True,
             "enabled": True, "registered": True, "owner": "self", "tos_ack": "x", "access_ends": end,
             "terms": {"auto_dispatch": "needs_ack", "auto_select": "needs_ack"}}
        r["auto"] = accounts.can_auto(r, "auto_dispatch", now=T0)
        rs.append(r)
    return rs


def test_ryan_profile_declares_kai_access_ends_before_nov_28():
    import accounts
    spec = RYAN["instances"]["claudeAgent_claude_kai"]
    end = accounts.access_end(spec)
    assert end == datetime(2026, 11, 27, 16, 0, tzinfo=UTC)  # 台北 11-28 00:00
    assert accounts.access_end(RYAN["instances"]["claudeAgent"]) is None


def test_access_end_parsing():
    import accounts
    assert accounts.access_end({"access_ends": "2026-11-28T00:00:00+08:00"}) == datetime(2026, 11, 27, 16, tzinfo=UTC)
    assert accounts.access_end({"access_ends": "亂寫"}) is None
    assert accounts.access_end({}) is None
    reg = accounts.registry({}, {"instances": {"x": {"driver": "claudeAgent", "classes": ["claude-opus"], "access_ends": "亂寫"}}},
                            {"terms": {}})
    assert any("access_ends" in p for p in reg[0]["problems"])


def test_access_ends_soon_ranks_first_even_with_far_weekly_reset(tmp_path, auto_ok):
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 55, T0 + timedelta(hours=30))   # 週剩 45%，30 小時後重置
    write_claude_cache(home, "c_k", 4, T0 + timedelta(days=5))      # 週剩 96%，5 天後才重置，但訂閱 9 小時後到期
    qs = claude_q(tmp_path, ["c_a", "c_k"], home)
    rs = _sel_rows({"c_a": None, "c_k": ap.iso_utc(T0 + timedelta(hours=9))})
    mine = {"instances": {"c_a": {"driver": "claudeAgent", "classes": ["claude-opus"]},
                          "c_k": {"driver": "claudeAgent", "classes": ["claude-opus"]}}}
    sel = ap.select_claude_instance(rs, mine, qs, ap._empty_state(), now=T0)
    assert sel["ordered"] == ["c_k", "c_a"]
    assert "訂閱" in sel["reason"] and "到期前先燒完" in sel["reason"]
    # 第二意見改判也算它，而且排最前
    cands = ap.burn_candidates(rs, mine, qs, ap._empty_state(), now=T0, home=home)
    assert [c["instance"] for c in cands["claudeAgent"]] == ["c_k", "c_a"]
    assert "訂閱" in cands["claudeAgent"][0]["why"]


def test_access_ended_is_no_longer_recommended_or_dispatched(tmp_path):
    import accounts
    home = tmp_path / "home"
    write_claude_cache(home, "c_a", 55, T0 + timedelta(days=3))
    write_claude_cache(home, "c_k", 4, T0 + timedelta(days=5))
    qs = claude_q(tmp_path, ["c_a", "c_k"], home)
    rs = _sel_rows({"c_a": None, "c_k": ap.iso_utc(T0 - timedelta(minutes=1))})
    mine = {"instances": {"c_a": {"driver": "claudeAgent", "classes": ["claude-opus"]},
                          "c_k": {"driver": "claudeAgent", "classes": ["claude-opus"]}}}
    sel = ap.select_claude_instance(rs, mine, qs, ap._empty_state(), now=T0)
    assert sel["chosen"] == "c_a" and "c_k" not in sel["ordered"]
    assert "訂閱已到期" in next(c for c in sel["candidates"] if c["instance"] == "c_k")["why"]
    assert ap.burn_candidates(rs, mine, qs, ap._empty_state(), forced=["c_k"], now=T0, home=home) == {}
    # 自動派的判斷（judge 走 can_auto）也擋掉
    ok, why = accounts.can_auto(rs[1], "auto_dispatch", now=T0)
    assert not ok and "訂閱已到期" in why
    assert accounts.can_auto(rs[1], "auto_dispatch", now=T0 - timedelta(hours=1))[0]
