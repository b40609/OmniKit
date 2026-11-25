#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""問法庫（omnikit-ask）近兩週真實對話抽樣 × SOTA 分歧過濾評測與單頁檢視器產生器。

設計重點：
1. 真實對話抽樣：取自 2026-11-11 至 2026-11-25 使用者在 OmniKit / OmniKeep / CatOS / UAnalyze / t3-deskcat
   的 10 筆真實提問與糾正原句（8 題模糊卡住／抱怨／問做法 + 2 題明確指令負樣本，已脫敏）。
2. 零記憶汙染對照：在暫存空白目錄透過 Antigravity ACP 執行 `global`（含 omnikit-ask）與 `without`
   （透過 skills.json exclude 遮蔽 omnikit-ask），不載入 claude-mem 等跨對話記憶注入。
3. 嚴守分派規則：預設 `--account ryan --model gemini-4-hydrogen-xhigh -j 1`（一次一條低併發，xhigh 思考）。
4. 分歧過濾（Disagreement Filtering）：由跨家隔離評審（Claude Sonnet，--setting-sources ""）盲評 A/B 對照，
   篩出「有／無問法庫產生實質行為差異或勝負分歧」的題目放進 `generate_review.py` 單頁檢視器最前排，
   將兩組一致通過／無差異題目收斂至摘要，讓使用者 3 分鐘內即可完成 Pass/Fail 留存判定。

用法：
  uv run data/pilot/ask-eval/disagreement_eval.py --selftest
  uv run data/pilot/ask-eval/disagreement_eval.py --out data/evals/2026-11-25-ask-disagreement-review
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import agy_eval as base

SUFFIX_ISOLATION = "\n\n（註：這件事發生在獨立專案，這台電腦目前的空白工作資料夾沒有該專案檔案，請直接針對這個處境給出做法、需要先確認的問題或可直接貼的問法。）"

SAMPLES: list[dict] = [
    {
        "id": "r01-multiproject-chaos",
        "project": "OmniKit",
        "date": "2026-11-24",
        "expect_fire": True,
        "category": "project",
        "prompt": (
            "我現在同步開發好幾個專案，每次都忘記自己做到哪裡、目前完成度多少，"
            "都要一直問下一步？目前結論？做到哪？我不滿意還要怎麼改？等等... "
            "請跟我討論怎麼解決這個問題比較好。" + SUFFIX_ISOLATION
        ),
        "rubric": "釐清多專案狀態恢復最核心缺的欄位（完工進度、有效結論、不滿意待改、下一步球權），避免一上來蓋龐大複雜的多代理管理平台，並給出輕量可落地的做法或問法。",
    },
    {
        "id": "r02-threads-sprawl",
        "project": "OmniKit",
        "date": "2026-11-21",
        "expect_fire": True,
        "category": "agent",
        "prompt": (
            "目前主對話到底是哪一個？不知不覺又開了一堆對話，不知道要在哪一個對話接續開發；"
            "近期常開發到一半對話越來越發散，也不知道距離完工到底還有多遠、下一步是什麼，該怎麼做比較好？" + SUFFIX_ISOLATION
        ),
        "rubric": "指出單一專案留一條主線、長對話透過交接或 /clear 收斂脈絡、側邊任務獨立開子對話完畢結案，並給出可直接用來統整現況的問法。",
    },
    {
        "id": "r03-ui-ugly-stuck",
        "project": "t3-deskcat",
        "date": "2026-11-24",
        "expect_fire": True,
        "category": "ui",
        "prompt": (
            "現在的這個小工具畫面很醜、解析度毛邊很多、預設畫面也太大，看起來超沒質感，"
            "但我不知道從何改起，該怎麼跟你講才改得準？" + SUFFIX_ISOLATION
        ),
        "rubric": "引導使用者補上具體參考風格（喜歡與討厭的範例）、截圖與尺寸層級標準，或提議先出 2-3 個不同視覺方向供盲選比較，而非空談抽象設計名詞。",
    },
    {
        "id": "r04-broke-again",
        "project": "OmniKeep",
        "date": "2026-11-24",
        "expect_fire": True,
        "category": "debug",
        "prompt": (
            "為什麼這個儲存功能修好又壞了？這次是什麼情況？"
            "還有剛剛說改好的新版介面，我的手機跟機器人打開怎麼還是舊的？以後怎麼避免一直重演？" + SUFFIX_ISOLATION
        ),
        "rubric": "區分「程式碼修好但服務未重啟／快取未更新」與「缺乏回歸測試／防呆檢查導致復發」兩件事，要求驗證實際運行環境與寫成自動測試／護欄，並給出可直接貼的驗收要求。",
    },
    {
        "id": "r05-report-no-action-sycophancy",
        "project": "UAnalyze",
        "date": "2026-11-21",
        "expect_fire": True,
        "category": "docs",
        "prompt": (
            "報告寫了一堆優點缺點好壞，啊所以看完之後還是不知道該怎麼做啊... "
            "而且你現在完全順著我的意願寫好聽話是會影響判斷的！要怎麼問才能拿到公正客觀又有明確行動結論的分析？" + SUFFIX_ISOLATION
        ),
        "rubric": "針對「結論先行＋明確改判條件」與「消除迎合偏誤（不透露個人立場、要求反方論點或獨立盲審）」給出具體做法與可直接貼的提問模板。",
    },
    {
        "id": "r06-early-agent-drift",
        "project": "CatOS",
        "date": "2026-11-14",
        "expect_fire": True,
        "category": "architecture",
        "prompt": (
            "目前開發進度緩慢而且常偏離我的預期，有時甚至是開發到一半才發現早期用的低階 Agent "
            "幫我規劃跟設定了很多根本不是我需求的死規則。該怎麼釐清並重新校準接下來的開發框架？" + SUFFIX_ISOLATION
        ),
        "rubric": "建議先盤點現有規則與架構（列成白話清單標明來源，讓使用者勾留／刪／改）並確認真正的硬性底線，校準完再繼續建新工作包，避免帶著錯誤約束繼續疊床架屋。",
    },
    {
        "id": "r07-ai-verbose-novice",
        "project": "CatOS",
        "date": "2026-11-23",
        "expect_fire": True,
        "category": "agent",
        "prompt": (
            "朋友跟我抱怨 AI 每次輸出都很多廢話，但他是純新手，完全沒有全域規則或 Skill 的概念，"
            "也不知道什麼時候該寫進規則檔，這類情況怎麼幫他設定最簡單有效？" + SUFFIX_ISOLATION
        ),
        "rubric": "用白話說明全域規則檔（如 CLAUDE.md / GEMINI.md）或精簡輸出 skill 的作用，提供一段新手可直接貼上設定的精簡回覆規則（結論放最前、少客套廢話）。",
    },
    {
        "id": "r08-relogin-config-fragile",
        "project": "OmniKit",
        "date": "2026-11-22",
        "expect_fire": True,
        "category": "architecture",
        "prompt": (
            "我把幾個帳號重新登入、打亂順序換了名字之後，原本綁定的設定是不是又會壞掉？"
            "每次重登就要重設所有細節讓我很困擾，這類設定該怎麼整理才不會一動就壞？" + SUFFIX_ISOLATION
        ),
        "rubric": "指出設定不應寫死脆弱的內部雜湊或順序，應將「規則角色分工」與「機器帳號實例映射」解耦，並提供單一同步／健康檢查指令自動對帳。",
    },
    {
        "id": "r09-neg-backtest-clear",
        "project": "UAnalyze",
        "date": "2026-11-24",
        "expect_fire": False,
        "category": "negative",
        "prompt": (
            "請寫一段 Python 範例腳本（用合成資料即可，不讀外部檔案），計算三大法人買賣超數列與指數日報酬率的"
            "同期及落後 1 至 5 日 Pearson 相關係數與同向勝率統計表。"
        ),
        "rubric": "需求已完全明確：應直接給出可執行的 Python 計算程式碼與簡潔說明，不應叫用問法庫或反過來教使用者怎麼提問。",
    },
    {
        "id": "r10-neg-parse-iso-ts",
        "project": "t3-deskcat",
        "date": "2026-11-24",
        "expect_fire": False,
        "category": "negative",
        "prompt": (
            "請寫一個 TypeScript 純函式 `formatRemainingHours(resetIso: string, nowMs: number): string`，"
            "把距離重置的剩餘時間轉成 `2h 15m` 或 `< 1m`（已過期回傳 `已重置`），並附上 3 個邊界測試案例。"
        ),
        "rubric": "需求已完全明確：應直接輸出 TypeScript 函式與 3 個測試案例，不應叫用問法庫或停下來問多餘問題。",
    },
]

PAIR_JUDGE_PROMPT = """你是客觀的雙盲評測審查員。請比較針對同一則使用者真實訊息的兩份回覆（Reply A 與 Reply B），不要使用任何工具。

## 題目類型
- 預期是否需要問法／做法引導（expect_fire）：{expect_fire}
- 評分準則：{rubric}

## 使用者真實訊息
{prompt}

## Reply A
{reply_a}

## Reply B
{reply_b}

請判斷：
1. `pass_a`：Reply A 是否符合評分準則（true/false）與一句話證據 `evidence_a`。
2. `pass_b`：Reply B 是否符合評分準則（true/false）與一句話證據 `evidence_b`。
3. `disagreement`：Reply A 與 Reply B 在「具體做法深度、是否精準點出缺的關鍵資訊、是否提供可直接貼的問法、或是否誤觸發多餘說教」上，是否存在**值得人類花 20 秒肉眼比較的實質差異**（true/false）？若兩份品質與方向高度一致（雙過且無明顯優劣），填 false。
4. `winner`：`"A"`、`"B"` 或 `"tie"`，以及一句繁體中文比較理由 `summary`。

只輸出一行合法 JSON，不要 Markdown 圍欄或其他文字：
{{"pass_a": true, "evidence_a": "...", "pass_b": true, "evidence_b": "...", "disagreement": true, "winner": "A", "summary": "..."}}"""


def find_generate_review_script() -> pathlib.Path | None:
    home = pathlib.Path.home()
    candidates = [
        home / ".claude/plugins/marketplaces/anthropic-agent-skills/skills/skill-creator/eval-viewer/generate_review.py",
    ]
    candidates.extend(sorted((home / ".claude/plugins/cache").glob("**/eval-viewer/generate_review.py"), reverse=True))
    for p in candidates:
        if p.is_file():
            return p
    return None


def judge_pair_isolated(sample: dict, with_reply: str, without_reply: str, *, model: str = "sonnet", timeout: int = 240) -> dict:
    """在完全隔離設定與記憶（--setting-sources \"\"）的中性暫存目錄呼叫 Claude 進行盲評與分歧偵測。"""
    # 固定奇偶交替位置消除位置偏誤（奇數題 A=with, B=without；偶數題 A=without, B=with）
    idx_num = int(re.search(r"\d+", sample["id"]).group(0))
    a_is_with = (idx_num % 2 == 1)
    reply_a = with_reply if a_is_with else without_reply
    reply_b = without_reply if a_is_with else with_reply

    prompt_txt = PAIR_JUDGE_PROMPT.format(
        expect_fire="是（卡住／問做法／抱怨）" if sample["expect_fire"] else "否（需求已明確，應直接交付）",
        rubric=sample["rubric"],
        prompt=sample["prompt"],
        reply_a=reply_a[:14000],
        reply_b=reply_b[:14000],
    )
    env = {k: v for k, v in os.environ.items() if not (k.startswith(("ANTHROPIC_", "CLAUDE_")) or k == "CLAUDECODE")}
    cmd = [
        shutil.which("claude") or "claude",
        "-p",
        "--model",
        model,
        "--system-prompt",
        "你是嚴格客觀的軟體工程評審，只輸出單行合法 JSON。",
        "--tools",
        "",
        "--strict-mcp-config",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--max-turns",
        "1",
    ]
    with tempfile.TemporaryDirectory(prefix="ask-disagree-judge-") as cwd:
        p = subprocess.run(cmd, input=prompt_txt, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, timeout=timeout, check=False)
    m = re.search(r"\{.*\}", p.stdout or "", re.DOTALL)
    if not m:
        return {
            "with_pass": False,
            "without_pass": False,
            "with_evidence": f"評審無 JSON：{(p.stderr or p.stdout or '')[-160:]}",
            "without_evidence": "評審無 JSON",
            "disagreement": True,
            "winner": "error",
            "summary": "評審解析失敗，排入人工檢視",
        }
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return {
            "with_pass": False,
            "without_pass": False,
            "with_evidence": "評審 JSON 語法錯誤",
            "without_evidence": "評審 JSON 語法錯誤",
            "disagreement": True,
            "winner": "error",
            "summary": "評審解析失敗，排入人工檢視",
        }

    pass_a = bool(raw.get("pass_a"))
    pass_b = bool(raw.get("pass_b"))
    ev_a = str(raw.get("evidence_a") or "")
    ev_b = str(raw.get("evidence_b") or "")
    w_raw = str(raw.get("winner") or "tie").upper()
    if w_raw == "A":
        winner = "with_skill" if a_is_with else "without_skill"
    elif w_raw == "B":
        winner = "without_skill" if a_is_with else "with_skill"
    else:
        winner = "tie"

    with_pass = pass_a if a_is_with else pass_b
    without_pass = pass_b if a_is_with else pass_a
    disagree = bool(raw.get("disagreement")) or (with_pass != without_pass) or (winner != "tie")
    return {
        "with_pass": with_pass,
        "without_pass": without_pass,
        "with_evidence": ev_a if a_is_with else ev_b,
        "without_evidence": ev_b if a_is_with else ev_a,
        "disagreement": disagree,
        "winner": winner,
        "summary": str(raw.get("summary") or ""),
    }


def write_viewer_workspace(records: list[dict], out_dir: pathlib.Path, *, include_converged: bool = False) -> tuple[pathlib.Path, pathlib.Path, dict]:
    """將分歧過濾後的對照結果轉成官方 generate_review.py 可直接讀取的 workspace 與 benchmark.json。"""
    viewer_ws = out_dir / "viewer-workspace"
    if viewer_ws.is_dir():
        shutil.rmtree(viewer_ws)
    viewer_ws.mkdir(parents=True, exist_ok=True)

    disagreed = [r for r in records if r["filter"]["keep_for_human"]]
    selected = records if include_converged else (disagreed or records[:3])

    for idx, rec in enumerate(selected, 1):
        case_dir = viewer_ws / f"{idx:02d}-{rec['id']}"
        meta = {
            "eval_id": idx,
            "prompt": (
                f"【來源：{rec['project']}｜{rec['date']}｜預期叫用：{'是' if rec['expect_fire'] else '否（負樣本）'}｜"
                f"分歧原因：{rec['filter']['reason']}】\n\n{rec['prompt']}"
            ),
        }
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "eval_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # 將兩組並排放在同一張單頁卡片，讓使用者 20 秒內上下／切換比完直接打 Pass/Fail 回饋
        run_dir = case_dir / "comparison"
        outputs_dir = run_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        summary_md = (
            f"# 分歧過濾摘要：{rec['id']}\n\n"
            f"- **真實對話來源**：`{rec['project']}`（{rec['date']}）\n"
            f"- **預期叫用問法庫**：`{'是' if rec['expect_fire'] else '否（明確需求負樣本）'}`\n"
            f"- **實際叫用（with_skill / without_skill）**：`{rec['with']['fired']}` / `{rec['without']['fired']}`\n"
            f"- **跨家盲評勝負**：`{rec['judge']['winner']}` — {rec['judge']['summary']}\n"
            f"- **為何保留給你看**：{rec['filter']['reason']}\n\n"
            f"---\n\n"
            f"## 🟢 有問法庫（with_skill，耗時 {rec['with']['seconds']}s，叫用={rec['with']['fired']}）\n\n"
            f"{rec['with']['reply']}\n\n"
            f"---\n\n"
            f"## ⚪ 無問法庫（without_skill，耗時 {rec['without']['seconds']}s，叫用={rec['without']['fired']}）\n\n"
            f"{rec['without']['reply']}\n"
        )
        (outputs_dir / "01-side-by-side.md").write_text(summary_md, encoding="utf-8")
        (outputs_dir / "02-with-skill.md").write_text(rec["with"]["reply"], encoding="utf-8")
        (outputs_dir / "03-without-skill.md").write_text(rec["without"]["reply"], encoding="utf-8")

        grading = {
            "summary": {
                "passed": int(rec["judge"]["with_pass"]) + int(rec["expect_fire"] == rec["with"]["fired"]),
                "failed": int(not rec["judge"]["with_pass"]) + int(rec["expect_fire"] != rec["with"]["fired"]),
                "total": 2,
                "pass_rate": (int(rec["judge"]["with_pass"]) + int(rec["expect_fire"] == rec["with"]["fired"])) / 2.0,
            },
            "expectations": [
                {
                    "text": f"[with_skill 品質] {rec['rubric']}",
                    "passed": rec["judge"]["with_pass"],
                    "evidence": rec["judge"]["with_evidence"],
                },
                {
                    "text": f"[叫用精準度] expect_fire={rec['expect_fire']}，實際 fired={rec['with']['fired']}",
                    "passed": rec["expect_fire"] == rec["with"]["fired"],
                    "evidence": f"with_skill fired={rec['with']['fired']}，without_skill fired={rec['without']['fired']}",
                },
                {
                    "text": f"[without_skill 對照基準] {rec['judge']['summary']}",
                    "passed": rec["judge"]["without_pass"],
                    "evidence": rec["judge"]["without_evidence"],
                },
            ],
        }
        (run_dir / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(records) or 1
    with_pass_rate = round(sum(1 for r in records if r["judge"]["with_pass"]) / n, 3)
    without_pass_rate = round(sum(1 for r in records if r["judge"]["without_pass"]) / n, 3)
    with_sec = round(sum(r["with"]["seconds"] for r in records) / n, 2)
    without_sec = round(sum(r["without"]["seconds"] for r in records) / n, 2)
    pos_cases = [r for r in records if r["expect_fire"]]
    neg_cases = [r for r in records if not r["expect_fire"]]
    fire_recall = round(sum(1 for r in pos_cases if r["with"]["fired"]) / (len(pos_cases) or 1), 3)
    false_fire = sum(1 for r in neg_cases if r["with"]["fired"])

    benchmark = {
        "metadata": {
            "skill_name": "omnikit-ask",
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "total_sampled": len(records),
            "disagreement_kept": len(disagreed),
            "converged_filtered_out": len(records) - len(disagreed),
        },
        "run_summary": {
            "with_skill": {
                "pass_rate": {"mean": with_pass_rate, "stddev": 0.0},
                "time_seconds": {"mean": with_sec, "stddev": 0.0},
                "tokens": {"mean": 0, "stddev": 0},
            },
            "without_skill": {
                "pass_rate": {"mean": without_pass_rate, "stddev": 0.0},
                "time_seconds": {"mean": without_sec, "stddev": 0.0},
                "tokens": {"mean": 0, "stddev": 0},
            },
            "delta": {
                "pass_rate": f"{with_pass_rate - without_pass_rate:+.3f}",
                "time_seconds": f"{with_sec - without_sec:+.1f}s",
                "tokens": "0",
            },
        },
        "notes": [
            f"近兩週真實對話抽樣共 {len(records)} 題（8 題卡住／問做法、2 題明確指令負樣本）。",
            f"分歧過濾結果：自動收斂免人工檢視 {len(records) - len(disagreed)} 題，保留具實質分歧／勝負差異 {len(disagreed)} 題進 Outputs 分頁供 3 分鐘快速判定。",
            f"叫用精準度：正向題叫用率 {sum(1 for r in pos_cases if r['with']['fired'])}/{len(pos_cases)}（{fire_recall:.0%}），負樣本誤叫用 {false_fire}/{len(neg_cases)}，without_skill 洩漏叫用 {sum(1 for r in records if r['without']['fired'])}/{len(records)}。",
            f"跨家盲評勝負：with_skill 勝 {sum(1 for r in records if r['judge']['winner'] == 'with_skill')} 題｜without_skill 勝 {sum(1 for r in records if r['judge']['winner'] == 'without_skill')} 題｜平手 {sum(1 for r in records if r['judge']['winner'] == 'tie')} 題。",
        ],
    }
    bench_path = out_dir / "benchmark.json"
    bench_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    return viewer_ws, bench_path, benchmark


def build_static_html(viewer_ws: pathlib.Path, bench_path: pathlib.Path, html_out: pathlib.Path) -> None:
    gen = find_generate_review_script()
    if gen is None:
        raise RuntimeError("找不到官方 eval-viewer/generate_review.py")
    env = {**os.environ, "PYTHONUTF8": "1"}
    p = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(gen),
            str(viewer_ws),
            "--skill-name",
            "omnikit-ask（分歧過濾 3 分鐘留存判定）",
            "--benchmark",
            str(bench_path),
            "--static",
            str(html_out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if p.returncode != 0 or not html_out.is_file():
        raise RuntimeError(f"generate_review.py 執行失敗：{p.stderr or p.stdout}")


def selftest() -> int:
    """離線驗證：1) without_skill_dir 正確在 skills.json 寫入 exclude 遮蔽 omnikit-ask；2) 分歧過濾與 generate_review.py HTML 產出正常。"""
    with tempfile.TemporaryDirectory(prefix="ask-disagree-selftest-") as tmp:
        root = pathlib.Path(tmp)
        fake_gem = root / "gem"
        (fake_gem / "config" / "skills").mkdir(parents=True)
        (fake_gem / "config" / "skills.json").write_text(
            json.dumps({"entries": [{"path": "/C:/Users/user/Desktop/OmniKit/engine/skills"}]}, indent=2),
            encoding="utf-8",
        )
        overlay, made = base.without_skill_dir(fake_gem)
        try:
            sj = json.loads((overlay / "config" / "skills.json").read_text(encoding="utf-8"))
            excl = set(sj["entries"][0].get("exclude") or [])
            assert "omnikit-ask" in excl and "ok-ask" in excl, f"skills.json 未遮蔽 omnikit-ask: {sj}"
        finally:
            base.drop_dir(made)

        fake_records = [
            {
                "id": "r01-demo-disagree",
                "project": "OmniKit",
                "date": "2026-11-24",
                "expect_fire": True,
                "prompt": "測試分歧題",
                "rubric": "給出明確做法",
                "with": {"reply": "有問法庫回覆", "fired": True, "seconds": 12},
                "without": {"reply": "無問法庫回覆", "fired": False, "seconds": 10},
                "judge": {
                    "with_pass": True,
                    "without_pass": False,
                    "with_evidence": "精準",
                    "without_evidence": "發散",
                    "disagreement": True,
                    "winner": "with_skill",
                    "summary": "with_skill 結構明顯更清楚",
                },
                "filter": {"keep_for_human": True, "reason": "盲評分出勝負（winner=with_skill）且通過狀態不同"},
            },
            {
                "id": "r09-demo-converged",
                "project": "UAnalyze",
                "date": "2026-11-24",
                "expect_fire": False,
                "prompt": "測試負樣本一致題",
                "rubric": "直接寫程式不誤觸發",
                "with": {"reply": "print(1)", "fired": False, "seconds": 8},
                "without": {"reply": "print(1)", "fired": False, "seconds": 8},
                "judge": {
                    "with_pass": True,
                    "without_pass": True,
                    "with_evidence": "直接交付",
                    "without_evidence": "直接交付",
                    "disagreement": False,
                    "winner": "tie",
                    "summary": "兩組皆直接交付程式碼且未誤觸發",
                },
                "filter": {"keep_for_human": False, "reason": "兩組一致通過且無行為分歧，自動收斂"},
            },
        ]
        out = root / "out"
        ws, bp, _ = write_viewer_workspace(fake_records, out)
        runs = list(ws.iterdir())
        assert len(runs) == 1 and "r01-demo-disagree" in runs[0].name, f"分歧過濾未正確篩選：{runs}"
        html_file = out / "review.html"
        build_static_html(ws, bp, html_file)
        assert html_file.is_file() and html_file.stat().st_size > 10_000, "未產出有效單頁檢視器 HTML"
    print("ok  without_skill_dir skills.json exclude 遮蔽驗證通過")
    print("ok  分歧過濾與 generate_review.py 單頁檢視器 HTML 產出驗證通過")
    return 0


def classify_disagreement(sample: dict, with_res: dict, without_res: dict, j: dict) -> dict:
    # 負樣本若兩組皆未叫用問法庫且雙雙通過，兩份輸出差異僅為同設定隨機取樣變異，自動收斂免人工檢視
    if (not sample["expect_fire"]) and (not with_res["fired"]) and (not without_res["fired"]) and j["with_pass"] and j["without_pass"]:
        return {
            "keep_for_human": False,
            "reason": "負樣本兩組皆未誤叫用且雙雙通過（隨機變異自動收斂）",
        }

    reasons = []
    if sample["expect_fire"] != with_res["fired"]:
        reasons.append(f"叫用預期不符（expect_fire={sample['expect_fire']}, actual={with_res['fired']}）")
    if without_res["fired"]:
        reasons.append("對照組意外載入 skill")
    if j["with_pass"] != j["without_pass"]:
        reasons.append(f"評審通過狀態分歧（with={j['with_pass']}, without={j['without_pass']}）")
    elif j["winner"] != "tie" and j["disagreement"]:
        reasons.append(f"盲評具實質品質差異（winner={j['winner']}）")
    elif j["disagreement"]:
        reasons.append("盲評標記兩組解法策略有實質差異")

    return {
        "keep_for_human": bool(reasons),
        "reason": "；".join(reasons) if reasons else "兩組一致通過且無實質行為分歧（自動收斂）",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", default="ryan")
    ap.add_argument("--model", default="gemini-4-hydrogen-xhigh")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--out", default=str(pathlib.Path.home() / ".omnikit" / "ask-review" / "2026-11-25"))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 題（0 代表全部 10 題）")
    ap.add_argument("--rebuild-only", action="store_true", help="只根據已存 raw/*.json 重建檢視器")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    out_dir = pathlib.Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    samples = SAMPLES[: args.limit] if args.limit > 0 else SAMPLES
    records: list[dict] = []

    if not args.rebuild_only:
        gem_with = base.profile_dir(args.account)
        gem_without, made = base.without_skill_dir(gem_with)
        try:
            for idx, s in enumerate(samples, 1):
                rec_file = raw_dir / f"{s['id']}.json"
                if rec_file.is_file():
                    old = json.loads(rec_file.read_text(encoding="utf-8"))
                    if not old.get("with", {}).get("error") and not old.get("without", {}).get("error") and old.get("judge", {}).get("winner") != "error":
                        records.append(old)
                        print(f"[{idx}/{len(samples)}] {s['id']}: 沿用已完成紀錄（keep={old['filter']['keep_for_human']}）", flush=True)
                        continue

                print(f"[{idx}/{len(samples)}] 執行 {s['id']} (with_skill)...", flush=True)
                ws_w = base.make_workspace("global", None)
                try:
                    r_w = base.run_turn(gem_with, ws_w, args.model, s["prompt"], args.timeout)
                finally:
                    shutil.rmtree(ws_w, ignore_errors=True)
                w_fired = base.fired(r_w)

                print(f"[{idx}/{len(samples)}] 執行 {s['id']} (without_skill)...", flush=True)
                ws_wo = base.make_workspace("without", None)
                try:
                    r_wo = base.run_turn(gem_without, ws_wo, args.model, s["prompt"], args.timeout)
                finally:
                    shutil.rmtree(ws_wo, ignore_errors=True)
                wo_fired = base.fired(r_wo)

                if r_w["error"] or r_wo["error"]:
                    raise RuntimeError(f"{s['id']} 執行錯誤：with={r_w['error']} without={r_wo['error']}")

                j = judge_pair_isolated(s, r_w["reply"], r_wo["reply"], model=args.judge_model)
                with_clean = {"reply": r_w["reply"], "fired": w_fired, "seconds": r_w["seconds"], "error": r_w["error"]}
                without_clean = {"reply": r_wo["reply"], "fired": wo_fired, "seconds": r_wo["seconds"], "error": r_wo["error"]}
                filt = classify_disagreement(s, with_clean, without_clean, j)

                rec = {**s, "with": with_clean, "without": without_clean, "judge": j, "filter": filt}
                rec_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                records.append(rec)
                print(
                    f"  -> {s['id']}: fired={w_fired}/{wo_fired} winner={j['winner']} keep_for_human={filt['keep_for_human']} ({filt['reason']})",
                    flush=True,
                )
        finally:
            base.drop_dir(made)
    else:
        for s in samples:
            rec_file = raw_dir / f"{s['id']}.json"
            if rec_file.is_file():
                records.append(json.loads(rec_file.read_text(encoding="utf-8")))

    viewer_ws, bench_path, benchmark = write_viewer_workspace(records, out_dir)
    html_out = out_dir / "review.html"
    build_static_html(viewer_ws, bench_path, html_out)
    (out_dir / "summary.json").write_text(
        json.dumps({"benchmark": benchmark, "records": [{k: v for k, v in r.items() if k not in ("with", "without")} for r in records]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n單頁檢視器已產出：{html_out}")
    print("\n".join(benchmark["notes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
