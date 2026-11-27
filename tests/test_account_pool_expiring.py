"""Claude 多帳號選號：T3 快取補位與「快重置優先消耗（Expiring-Soon Burn First）」。"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "scripts"))
import account_pool as ap  # noqa: E402

T0 = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
IDS = ("claudeAgent", "claudeAgent_2", "claudeAgent_claude_b")


def rows():
    return [{"id": i, "driver": "claudeAgent", "account": i, "auto": {"auto_select": True}} for i in IDS]


def write_cache(home, iid, used, reset):
    d = home / ".t3" / "caches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{iid}.json").write_text(json.dumps({
        "auth": {"email": "secret@example.test"},
        "usageLimits": {"checkedAt": ap.iso_utc(T0), "windows": [
            {"id": "five_hour", "usedPercent": 5, "resetsAt": ap.iso_utc(T0 + timedelta(hours=3))},
            {"id": "seven_day", "usedPercent": used, "resetsAt": ap.iso_utc(reset)}]}}), encoding="utf-8")


def quotas(tmp_path, monkeypatch):
    import accounts
    monkeypatch.setattr(accounts, "can_auto", lambda r, what, now=None: (True, ""))
    home = tmp_path / "home"
    t3_raw = {i: {"driver": "claudeAgent", "config": {"homePath": f"~/.{i}"}} for i in IDS}
    return ap.claude_quotas(tmp_path / "state", rows(), None, 80, home=home, t3_raw=t3_raw, now=T0)


def test_kai_24h_beats_others_5d(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_cache(home, "claudeAgent", 10, T0 + timedelta(days=5))
    write_cache(home, "claudeAgent_2", 20, T0 + timedelta(days=5))
    write_cache(home, "claudeAgent_claude_b", 70, T0 + timedelta(hours=24))
    qs = quotas(tmp_path, monkeypatch)
    assert {q["source"] for q in qs} == {"t3_cache"}
    assert "secret@example.test" not in json.dumps(qs)
    sel = ap.select_claude_instance(rows(), None, qs, ap._empty_state(), strategy="weekly-first", now=T0)
    assert sel["chosen"] == "claudeAgent_claude_b"


def test_expiring_overrides_sticky_cooldown(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_cache(home, "claudeAgent", 10, T0 + timedelta(days=5))
    write_cache(home, "claudeAgent_2", 20, T0 + timedelta(days=5))
    write_cache(home, "claudeAgent_claude_b", 70, T0 + timedelta(hours=24))
    qs = quotas(tmp_path, monkeypatch)
    doc = ap._empty_state()
    doc["sticky"]["claudeAgent"] = {"instance": "claudeAgent", "switched_at": ap.iso_utc(T0 - timedelta(minutes=1))}
    sel = ap.select_claude_instance(rows(), None, qs, doc, strategy="weekly-first", now=T0)
    assert sel["chosen"] == "claudeAgent_claude_b"


def test_depleted_kai_not_burned(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_cache(home, "claudeAgent", 10, T0 + timedelta(days=5))
    write_cache(home, "claudeAgent_2", 20, T0 + timedelta(days=5, hours=1))
    write_cache(home, "claudeAgent_claude_b", 100, T0 + timedelta(hours=24))
    qs = quotas(tmp_path, monkeypatch)
    sel = ap.select_claude_instance(rows(), None, qs, ap._empty_state(), strategy="weekly-first", now=T0)
    assert sel["chosen"] == "claudeAgent"


def test_manual_registration(tmp_path):
    st = tmp_path / "state"
    ap.set_claude_quota(st, "claudeAgent_claude_b", weekly_used=72, weekly_resets_at=ap.iso_utc(T0 + timedelta(hours=18)), now=T0)
    snap = ap.manual_claude_snapshot(ap.load_state(st), "claudeAgent_claude_b", T0)
    assert snap["source"] == "manual" and snap["seven_day"]["used_percentage"] == 72.0
    ap.set_claude_quota(st, "claudeAgent_claude_b", clear=True, now=T0)
    assert ap.manual_claude_snapshot(ap.load_state(st), "claudeAgent_claude_b", T0) is None
