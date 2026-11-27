"""範圍 C（外部競品與收錄交叉檢視）前置漏斗與 CLI 測試。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "engine" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import competitor_watch as cw  # noqa: E402


def _make_demo_env(tmp_path: Path) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "omnikeep.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE items (
            id TEXT PRIMARY KEY, url TEXT, source_type TEXT, category_name TEXT,
            title_l1 TEXT, summary_l1 TEXT, tech_tags TEXT, is_starred INTEGER,
            is_read INTEGER, origin TEXT, user_note TEXT, agent_status TEXT,
            created_at TEXT, deep_analysis TEXT
        );
        CREATE TABLE item_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_parent_id TEXT,
            target_name TEXT, target_canonical_url TEXT, mention_context TEXT
        );
    """)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("k1", "https://threads.net/p/1", "web", "AI", "OpenSpec Skill Router",
             "一句話路由 Skills", '["Claude","Skill"]', 1, 0, "manual", "#競品 比較 OmniKit", "none", now_str, ""),
            ("k2", "https://github.com/bitbonsai/mcpvault", "web", "工具", "MCPVault",
             "Obsidian Vault MCP", '["Obsidian","MCP"]', 0, 0, "manual", "", "none", now_str, ""),
            ("k3", "https://example.com/food", "web", "美食旅遊", "台北拉麵清單",
             "週末吃拉麵推薦", '["生活"]', 0, 0, "manual", "", "none", now_str, ""),
            ("k4", "https://example.com/finance-star", "web", "投資理財", "單純加星的投資長文",
             "存股新聞整理（無備註無專案關聯，應被降噪不擠掉工程名額）", '["投資"]', 1, 0, "manual", "", "none", now_str, ""),
            ("k5", "https://github.com/acme/radar-noise", "web", "AI", "自動雷達項目",
             "origin=radar 預設不掃", '["Agent"]', 0, 0, "radar", "", "none", now_str, ""),
            ("k6", "https://github.com/acme/prev-rejected", "web", "AI", "曾經拒絕過的工具",
             "以前測過 Windows 閃退的 mcp skill", '["MCP"]', 0, 0, "manual", "", "none", now_str, ""),
            ("k7", "https://github.com/tobi/qmd", "web", "搜尋", "QMD Reranker",
             "本地 Markdown 混合檢索與 rerank", '["RAG","QMD"]', 0, 0, "manual", "看 OmniKeep 要不要借鏡", "none", now_str, ""),
        ],
    )
    conn.execute(
        "INSERT INTO item_citations (source_parent_id, target_name, target_canonical_url, mention_context) VALUES (?,?,?,?)",
        ("k1", "OpenSpec", "https://github.com/Fission-AI/OpenSpec", "Skill Router"),
    )
    conn.commit()
    conn.close()

    data_dir = tmp_path / "data"
    (data_dir / "tools").mkdir(parents=True)
    (data_dir / "tools" / "prev-rejected.yaml").write_text(
        "id: prev-rejected\nname: Prev Rejected\nstatus: rejected\nslots: [mcp]\n"
        "url: https://github.com/acme/prev-rejected\nreason: Windows 下閃退\n",
        encoding="utf-8",
    )

    status_dir = tmp_path / "status"
    (status_dir / "OmniKit").mkdir(parents=True)
    (status_dir / "OmniKit" / "NOW.md").write_text("# OmniKit — 目前狀態\n- 專案路徑：C:/OmniKit\n", encoding="utf-8")
    (status_dir / "OmniKeep").mkdir(parents=True)
    (status_dir / "OmniKeep" / "NOW.md").write_text("# OmniKeep：現在\n- 專案路徑：C:/OmniKeep\n", encoding="utf-8")
    return db_path, data_dir, status_dir


def test_repo_normalization_and_extraction():
    assert cw.normalize_repo("https://github.com/Fission-AI/OpenSpec.git") == "Fission-AI/OpenSpec"
    assert cw.normalize_repo("bitbonsai/mcpvault") == "bitbonsai/mcpvault"
    assert cw.normalize_repo("https://github.com/topics/mcp") is None
    repos = cw.extract_github_repos(
        "推薦 https://github.com/tobi/qmd 與 https://github.com/TOBI/QMD/issues/1 及 https://github.com/settings/tokens"
    )
    assert repos == ["tobi/qmd"]


def test_scan_funnel_fast_track_noise_filter_and_top3_cap(tmp_path: Path):
    db_path, data_dir, status_dir = _make_demo_env(tmp_path)
    items = cw.fetch_recent_items(db_path, days=7, include_radar=False)
    assert {i["id"] for i in items} == {"k1", "k2", "k3", "k4", "k6", "k7"}

    roster = cw.load_roster_tools(data_dir)
    projects = cw.load_project_profiles(status_dir)
    fake_gh = lambda r: {
        "repo": r, "verified_on": "2026-11-27", "ok": True,
        "stars": 5000, "license": "MIT", "archived": False,
        "pushed_at": "2026-11-26", "latest_release": "v2.0.0", "description": "mock",
    }
    pkt = cw.build_scan_packet(items, roster, projects, days=7, max_deep=3, verify_gh=True, gh_verifier=fake_gh)

    # 嚴格截斷最多 3 項深挖（k1/k7 快車道 + k2 工程競品；k6 落入 overflow；k3 與無備註投資文 k4 被濾除）
    assert pkt["counts"]["deep_candidates"] == 3
    assert pkt["counts"]["overflow_candidates"] == 1
    assert {f["id"] for f in pkt["filtered_out"]} == {"k3", "k4"}
    deep_ids = [c["id"] for c in pkt["deep_candidates"]]
    assert deep_ids[:2] == ["k1", "k7"] or set(deep_ids[:2]) == {"k1", "k7"}
    assert "k2" in deep_ids

    # 驗證 citation repo 萃取與名冊曾拒絕查重
    all_cands = {c["id"]: c for c in pkt["deep_candidates"] + pkt["overflow_candidates"]}
    assert "Fission-AI/OpenSpec" in all_cands["k1"]["repos"]
    assert all_cands["k6"]["roster_matches"][0]["status"] == "rejected"

    md = cw.render_markdown(pkt)
    assert "adopt_or_integrate" in md
    assert "dismiss_with_evidence" in md
    assert "禁建 pending 墳場" in md


def test_target_mode_and_cli_selftest(tmp_path: Path):
    _, data_dir, status_dir = _make_demo_env(tmp_path)
    roster = cw.load_roster_tools(data_dir)
    projects = cw.load_project_profiles(status_dir)
    pkt = cw.build_target_packet(
        "https://github.com/acme/prev-rejected",
        roster,
        projects,
        project_filter="OmniKit",
        note="新版有改善 Windows 相容性嗎？",
        verify_gh=False,
    )
    assert pkt["normalized_repo"] == "acme/prev-rejected"
    assert pkt["roster_match"]["reason"] == "Windows 下閃退"
    assert pkt["matched_projects"][0]["project"] == "OmniKit"

    # CLI --selftest 端到端執行
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "competitor_watch.py"), "--selftest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SELFTEST PASS" in proc.stdout

    # CLI target --format json 離線端到端
    proc2 = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "competitor_watch.py"),
            "target", "Fission-AI/OpenSpec",
            "--project", "OmniKit",
            "--data", str(data_dir),
            "--status-dir", str(status_dir),
            "--no-gh", "--format", "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc2.returncode == 0, proc2.stderr
    doc = json.loads(proc2.stdout)
    assert doc["normalized_repo"] == "Fission-AI/OpenSpec"
    assert len(doc["dispositions"]) == 5
