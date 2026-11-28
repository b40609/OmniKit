"""範圍 C（外部競品與收錄交叉檢視）前置漏斗與 CLI 測試。"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    old_iso = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("k1", "https://threads.net/p/1", "web", "AI", "OpenSpec Skill Router",
             "一句話路由 Skills", '["Claude","Skill"]', 1, 0, "manual", "#競品 OmniKit", "none", now_iso, ""),
            ("k2", "https://github.com/bitbonsai/mcpvault", "web", "工具", "MCPVault",
             "Obsidian Vault MCP", '["Obsidian","MCP"]', 0, 0, "manual", "", "none", now_iso, ""),
            ("k2_dup", "https://threads.net/p/dup", "web", "工具", "MCPVault 貼文重複項",
             "介紹 https://github.com/bitbonsai/mcpvault，超好用", '["Obsidian"]', 0, 0, "manual", "", "none", now_iso, ""),
            ("k3", "https://example.com/food", "web", "美食旅遊", "台北拉麵清單",
             "週末吃拉麵推薦", '["生活"]', 0, 0, "manual", "下次去", "none", now_iso, ""),
            ("k4", "https://example.com/finance-star", "web", "投資理財", "單純加星的投資長文",
             "存股新聞整理（無競品標記無專案關聯）", '["投資"]', 1, 0, "manual", "", "none", now_iso, ""),
            ("k5", "https://github.com/acme/radar-noise", "web", "AI", "自動雷達項目",
             "origin=radar 預設不掃", '["Agent"]', 0, 0, "radar", "", "none", now_iso, ""),
            ("k6", "https://github.com/acme/prev-rejected", "web", "AI", "曾經拒絕過的工具",
             "以前測過 Windows 閃退的 mcp skill", '["MCP"]', 0, 0, "manual", "", "none", now_iso, ""),
            ("k7", "https://github.com/tobi/qmd", "web", "搜尋", "QMD Reranker",
             "本地 Markdown 混合檢索與 rerank", '["RAG","QMD"]', 1, 0, "manual", "", "none", now_iso, ""),
            ("k8_insight", "omnikeep://insight/ins_self", "insight", "Insight", "Agent 自己寫回的報告",
             "不該被當成使用者手動收錄再進漏斗", '["AgentInsight"]', 1, 0, "manual", "#競品", "none", now_iso, ""),
            ("k9_old", "https://github.com/acme/too-old", "web", "AI", "12 天前舊項目",
             "超出 7 天視窗不應撈出", '["MCP"]', 1, 0, "manual", "#競品", "none", old_iso, ""),
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
    (status_dir / "brand").mkdir(parents=True)
    (status_dir / "brand" / "NOW.md").write_text("# brand 專案\n", encoding="utf-8")
    return db_path, data_dir, status_dir


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://github.com/tobi/qmd，這個很強", ["tobi/qmd"]),
        ("見 github.com/tobi/qmd。", ["tobi/qmd"]),
        ("（https://github.com/tobi/qmd）", ["tobi/qmd"]),
        ("see github.com/tobi/qmd, and more", ["tobi/qmd"]),
        ("執行 `github.com/tobi/qmd` 即可", ["tobi/qmd"]),
        ("[github.com/tobi/qmd]", ["tobi/qmd"]),
        ("docs.github.com/en/copilot", []),
        ("gist.github.com/someone/abc123", []),
        ("https://github.com/user-attachments/assets/1234-5678", []),
        ("https://github.com/apps/dependabot", []),
        ("https://api.github.com/repos/tobi/qmd", []),
    ],
)
def test_repo_extraction_cjk_punctuation_and_non_repo_exclusions(text: str, expected: list[str]):
    assert cw.extract_github_repos(text) == expected


def test_repo_normalization_and_dedup():
    assert cw.normalize_repo("https://github.com/Fission-AI/OpenSpec.git") == "Fission-AI/OpenSpec"
    assert cw.normalize_repo("bitbonsai/mcpvault") == "bitbonsai/mcpvault"
    assert cw.normalize_repo("https://github.com/topics/mcp") is None
    repos = cw.extract_github_repos(
        "推薦 https://github.com/tobi/qmd 與 https://github.com/TOBI/QMD/issues/1 及 https://github.com/settings/tokens"
    )
    assert repos == ["tobi/qmd"]


def test_scan_funnel_filters_insight_noise_general_note_and_dedups_top3(tmp_path: Path):
    db_path, data_dir, status_dir = _make_demo_env(tmp_path)
    items = cw.fetch_recent_items(db_path, days=7, include_radar=False)
    ids = {i["id"] for i in items}
    assert "k5" not in ids  # radar 排除
    assert "k8_insight" not in ids  # agent insight 排除（防自我迎合）
    assert "k9_old" not in ids  # 超過 7 天 ISO 日期排除

    roster = cw.load_roster_tools(data_dir)
    projects = cw.load_project_profiles(status_dir)
    fake_gh = lambda r: {
        "repo": r, "verified_on": "2026-11-27", "ok": True,
        "stars": 5000, "license": "MIT", "archived": False,
        "pushed_at": "2026-11-26", "latest_release": "v2.0.0", "description": "mock",
    }
    pkt = cw.build_scan_packet(items, roster, projects, days=7, max_deep=3, verify_gh=True, gh_verifier=fake_gh)

    # 美食加一般備註「下次去」(k3) 與無備註加星投資文 (k4) 都必須被濾除
    assert {f["id"] for f in pkt["filtered_out"]} == {"k3", "k4"}
    assert pkt["counts"]["deep_candidates"] == 3
    deep_ids = [c["id"] for c in pkt["deep_candidates"]]
    assert deep_ids[0] == "k1"
    # 同一個 primary repo (bitbonsai/mcpvault) 不重複佔 Top 3
    primary_repos = [c["repos"][0].lower() for c in pkt["deep_candidates"] if c["repos"]]
    assert len(primary_repos) == len(set(primary_repos))
    assert not ({"k2", "k2_dup"} <= set(deep_ids))

    # 驗證 citation repo 萃取與名冊曾拒絕查重
    all_cands = {c["id"]: c for c in pkt["deep_candidates"] + pkt["overflow_candidates"]}
    assert "Fission-AI/OpenSpec" in all_cands["k1"]["repos"]
    assert all_cands["k6"]["roster_matches"][0]["status"] == "rejected"

    md = cw.render_markdown(pkt)
    assert "adopt_or_integrate" in md and "dismiss_with_evidence" in md


def test_verify_github_repo_handles_blank_stderr_safely():
    class _FakeProc:
        returncode = 1
        stderr = "   \n  "
        stdout = ""

    res = cw.verify_github_repo("acme/demo", runner=lambda *a, **kw: _FakeProc())
    assert res["ok"] is False and "exit 1" in res["error"]


def test_target_mode_does_not_false_match_different_owner_and_cli_selftest(tmp_path: Path):
    _, data_dir, status_dir = _make_demo_env(tmp_path)
    roster = cw.load_roster_tools(data_dir)
    projects = cw.load_project_profiles(status_dir)

    # 同 owner/repo 必命中
    pkt = cw.build_target_packet(
        "https://github.com/acme/prev-rejected",
        roster,
        projects,
        project_filter="OmniKit",
        note="新版有改善 Windows 相容性嗎？",
        verify_gh=False,
    )
    assert pkt["roster_match"]["reason"] == "Windows 下閃退"

    # 不同 owner 但同 repo 名，因名冊有填 url，絕不可誤判曾拒絕
    pkt_other = cw.build_target_packet(
        "https://github.com/another-org/prev-rejected",
        roster,
        projects,
        verify_gh=False,
    )
    assert pkt_other["roster_match"] is None

    # CLI --selftest 端到端執行（帶 stdin=DEVNULL 防 Windows WinError 6）
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "competitor_watch.py"), "--selftest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
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
        stdin=subprocess.DEVNULL,
        timeout=30,
    )
    assert proc2.returncode == 0, proc2.stderr
    doc = json.loads(proc2.stdout)
    assert doc["normalized_repo"] == "Fission-AI/OpenSpec"
    assert len(doc["dispositions"]) == 5


def test_dynamic_now_inference_watch_yaml_merged_update_and_cursor(tmp_path: Path):
    """驗證通用開箱能力：NOW.md 動態領域推導、~/.omnikit/watch.yaml 覆寫、updated_at 歸併項目、增量水位線與 Layer A 全景表。"""
    db_path = tmp_path / "omnikeep.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE items (
            id TEXT PRIMARY KEY, url TEXT, source_type TEXT, category_name TEXT,
            title_l1 TEXT, summary_l1 TEXT, tech_tags TEXT, is_starred INTEGER,
            is_read INTEGER, origin TEXT, user_note TEXT, agent_status TEXT,
            created_at TEXT, updated_at TEXT, deep_analysis TEXT
        );
        CREATE TABLE item_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_parent_id TEXT,
            target_name TEXT, target_canonical_url TEXT, mention_context TEXT
        );
    """)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    old_iso = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("q1", "https://blave.org/zh", "web", "投資理財", "Blave Agent 量化回測與 MCPT",
             "支援台股回測與三道防過擬合檢驗", '["量化","回測"]', 0, 0, "manual", "", "none", now_iso, now_iso, ""),
            ("u1", "https://www.instagram.com/reel/abc", "web", "生活娛樂", "六種 UI 彈出層怎麼選",
             "設計系統彈出層選型與三個坑", '["UI"]', 0, 0, "manual", "", "none", now_iso, now_iso, ""),
            ("m1", "https://github.com/google-gemini/gemini-api-cli", "web", "Github", "gemini-api-cli",
             "20 天前建卡但今天歸併新社群貼文", '["CLI"]', 0, 0, "manual", "", "none", old_iso, now_iso, ""),
            ("n1", "https://example.com/stock-gossip", "web", "投資理財", "台股明牌八卦閒聊",
             "純閒聊無工具無方法論", '["投資"]', 0, 0, "manual", "", "none", now_iso, now_iso, ""),
        ],
    )
    conn.commit()
    conn.close()

    status_dir = tmp_path / "status"
    (status_dir / "MyQuant").mkdir(parents=True)
    (status_dir / "MyQuant" / "NOW.md").write_text("# MyQuant\n台股量化選股與財報回測系統\n", encoding="utf-8")
    (status_dir / "MyDesign").mkdir(parents=True)
    (status_dir / "MyDesign" / "NOW.md").write_text("# MyDesign\n品牌視覺與 DESIGN.md 設計系統\n", encoding="utf-8")

    cfg_path = tmp_path / "watch.yaml"
    cfg_path.write_text(
        "projects:\n  MyQuant:\n    keywords:\n      - blave\n",
        encoding="utf-8",
    )
    cfg = cw.load_watch_config(cfg_path)
    projects = cw.load_project_profiles(status_dir, watch_cfg=cfg)
    roster = {"by_id": {}, "by_repo": {}}

    items = cw.fetch_recent_items(db_path, days=7)
    assert {i["id"] for i in items} == {"q1", "u1", "m1", "n1"}

    pkt = cw.build_scan_packet(items, roster, projects, days=7, max_deep=3, verify_gh=False, watch_cfg=cfg)
    all_ids = {c["id"] for c in pkt["deep_candidates"] + pkt["overflow_candidates"]}
    assert {"q1", "u1", "m1"} <= all_ids  # 工程方法論與歸併更新全數保留，不被生活／投資分類誤殺
    assert "n1" not in all_ids  # 純閒聊八卦仍被濾除
    assert "MyQuant" in pkt["by_project"] and "MyDesign" in pkt["by_project"]

    md = cw.render_markdown(pkt)
    assert "Layer A：各專案關聯全景" in md
    assert "歸併" in md

    # 水位線推進後，同一時間戳前不重複撈出
    cursor_p = tmp_path / "watch_cursor.json"
    cw.save_cursor(cursor_p, last_scan_at=now_iso, seen_ids=["q1", "u1", "m1"])
    assert cw.fetch_recent_items(db_path, since_iso=cw.load_cursor(cursor_p)["last_scan_at"]) == []


def test_validate_check_skills_catches_errors_and_collisions(tmp_path: Path):
    """驗證 validate.py 新增的 Skill 格式硬規則與 TF-IDF 路由碰撞提醒。"""
    import validate as val

    sroot = tmp_path / "skills"
    (sroot / "skill-a").mkdir(parents=True)
    (sroot / "skill-a" / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: 檢查前端版面溢位與行動端巡檢工具，非前端不觸發。\n---\n# A\n",
        encoding="utf-8",
    )
    (sroot / "skill-b").mkdir(parents=True)
    (sroot / "skill-b" / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: 檢查前端版面溢位與行動端巡檢工具。\n---\n# B\n",
        encoding="utf-8",
    )
    (sroot / "bad-name").mkdir(parents=True)
    (sroot / "bad-name" / "SKILL.md").write_text(
        "---\nname: wrong-name\ndescription: 錯誤名稱測試，非測試不觸發。\n---\n# Bad\n",
        encoding="utf-8",
    )

    errs, warns = val.check_skills(sroot)
    assert any("wrong-name" in e for e in errs)
    assert any("skill-b" in w and "負面觸發" in w for w in warns)
    assert any("skill-a <-> skill-b" in w for w in warns)
