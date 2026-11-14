# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""把已有的實測結果帶到決定的畫面（提案 2026-11-14-decision-evidence 第 3 步）。

給「換」的建議（advise.py）與實測勝出的通知（notify.py）用：從實測紀錄讀出
挑戰者與現任的差距、雜訊基準、執行次數、評審家族、沒驗證到的部分，照實印出來。
只讀 repo 裡的檔案，不連網、不寫檔。

資料來源（data/evals/ 底下）：
- <紀錄>.md 同名的資料夾裡的 result.json（contracts/layer2-result.schema.json）與 verdict.json（layer2.py 的計算）。
- spec.yaml（執行的模型、每組每題跑幾次）、judge-1.json（評審的 provider 與模型）、out/（實際執行的檔案）。
沒有這些檔案的紀錄（例如手動做的盲選）就照實說「沒有結構化的數字」，不猜。

用法：
  uv run engine/scripts/proof.py show <data/evals/...md 或資料夾> [--tool <挑戰者 id>]
  uv run engine/scripts/proof.py --selftest
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

FAMILIES = (("claude", "Claude"), ("gemini", "Gemini"), ("gpt", "OpenAI"), ("o3", "OpenAI"), ("o4", "OpenAI"),
            ("codex", "OpenAI"), ("llama", "Llama"), ("qwen", "Qwen"), ("deepseek", "DeepSeek"))

NO_TEST = "沒有實測：名冊卡片只寫明它取代舊的，沒有第 2 層的比對結果，差距、雜訊基準、執行次數、評審都沒有"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def family(model):
    m = str(model or "").lower()
    return next((name for key, name in FAMILIES if m.startswith(key)), None)


def folder_of(repo, evidence):
    """紀錄路徑 → 放數字的資料夾；找不到回 None。"""
    if not evidence:
        return None
    path = repo / evidence
    if path.is_dir():
        return path
    if path.suffix == ".md" and path.with_suffix("").is_dir():
        return path.with_suffix("")
    if path.name in ("result.json", "verdict.json"):
        return path.parent
    for r in sorted((repo / "data" / "evals").glob("*/result.json")):
        if (read_json(r, {}) or {}).get("eval_doc") == evidence:
            return r.parent
    return None


def summary(repo, evidence, tool=None):
    """回傳 {evidence, exists, structured, gap, noise, runs, judge, runner, unverified}；沒有的項目是 None。"""
    s = {"evidence": evidence, "exists": bool(evidence) and (repo / evidence).exists(), "structured": False,
         "tool": tool, "gap": None, "noise": None, "runs": None, "judge": None, "runner": None, "unverified": []}
    folder = folder_of(repo, evidence)
    if folder is None:
        return s
    result = read_json(folder / "result.json", {}) or {}
    verdict = read_json(folder / "verdict.json", {}) or {}
    if not result and not verdict:
        return s
    s["exists"], s["structured"] = True, True
    result = result or verdict.get("result") or {}
    s["unverified"] = [str(u) for u in (result.get("unverified") or verdict.get("unverified") or [])]
    arms = verdict.get("arms") or {}
    arm_id = tool if tool in arms else (next(iter(arms)) if len(arms) == 1 else None)
    if arm_id is None and tool:
        arm_id = next((k for k, a in arms.items() if a.get("tool") == tool), None)
    if arm_id:
        a = arms[arm_id]
        s["tool"] = a.get("tool") or arm_id
        s["gap"] = {k: a.get(k) for k in ("pairs", "wins", "losses", "ties", "net", "outcome")}
    noise = verdict.get("noise")
    if isinstance(noise, dict):
        s["noise"] = {"pairs": noise.get("pairs") or 0, "decisive": noise.get("decisive") or 0, "rate": noise.get("rate")}
    try:
        spec = yaml.safe_load((folder / "spec.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        spec = {}
    out = folder / "out"
    if out.is_dir():
        counts = {}
        for f in out.glob("*.json"):
            arm = f.stem.split("-")[0]
            counts[arm] = counts.get(arm, 0) + 1
        s["runs"] = {"per_question": spec.get("runs"), "questions": len(spec.get("questions") or {}) or None,
                     "files": counts}
    elif spec.get("runs"):
        s["runs"] = {"per_question": spec.get("runs"), "questions": len(spec.get("questions") or {}) or None, "files": {}}
    judge = (read_json(folder / "judge-1.json", {}) or {}).get("judge") or {}
    model = judge.get("model") or (spec.get("judge") or {}).get("model")
    if model:
        s["judge"] = {"model": model, "provider": judge.get("provider") or (spec.get("judge") or {}).get("provider"),
                      "family": family(model)}
    if spec.get("model"):
        s["runner"] = {"model": spec["model"], "family": family(spec["model"])}
    return s


def gap_text(s):
    g = s["gap"]
    if not g or not g.get("pairs"):
        return "差距：紀錄裡沒有挑戰者對現任的比較數字"
    net = f"，淨 {g['net']:+.2f}" if isinstance(g.get("net"), (int, float)) else ""
    return f"差距：{s['tool']} 對現任比了 {g['pairs']} 組，{g['wins'] or 0} 勝 {g['losses'] or 0} 負 {g['ties'] or 0} 平{net}"


def noise_text(s):
    n = s["noise"]
    if not n or not n["pairs"]:
        return "雜訊基準：沒有量（現任自己比自己 0 組），所以分不出差距是工具造成的還是每次跑的差異"
    return f"雜訊基準：現任自己比自己 {n['pairs']} 組，{n['decisive']} 組分出勝負（{n['rate']:.0%}）"


def runs_text(s):
    r = s["runs"]
    if not r:
        return "執行次數：紀錄裡沒有"
    parts = []
    if r.get("per_question"):
        parts.append(f"每組每題 {r['per_question']} 次" + (f"、{r['questions']} 題" if r.get("questions") else ""))
    if r.get("files"):
        parts.append("實際執行 " + "、".join(f"{k} {v} 次" for k, v in sorted(r["files"].items())))
    return "執行次數：" + ("；".join(parts) if parts else "紀錄裡沒有")


def judge_text(s):
    j, run = s["judge"], s["runner"]
    if not j:
        return "評審：紀錄裡沒有"
    text = f"評審：{j['family'] or '不明家族'}（{j['model']}）"
    if run:
        same = j["family"] and j["family"] == run["family"]
        text += f"，執行的是 {run['family'] or '不明家族'}（{run['model']}）" + ("，同一家，可能偏袒自家" if same else "，不同家")
    return text


def unverified_text(s):
    return "沒驗證到：" + ("；".join(s["unverified"]) if s["unverified"] else "紀錄沒有列出")


def lines(s):
    """給畫面用的幾行（不含前綴符號）。"""
    if not s["structured"]:
        where = s["evidence"] or "（沒有紀錄路徑）"
        if not s["exists"]:
            return [f"實測：找不到紀錄 {where}，差距、雜訊基準、執行次數、評審都沒辦法列"]
        return [f"實測：{where} 只有文字紀錄，沒有結構化的數字（差距、雜訊基準、執行次數、評審），要看就打開紀錄"]
    return [gap_text(s), noise_text(s), runs_text(s), judge_text(s), unverified_text(s)]


def brief(s):
    """通知用的一句：五項都講，越短越好。"""
    if not s["structured"]:
        return "紀錄只有文字，沒有差距、雜訊基準、執行次數、評審的數字" if s["exists"] else "找不到實測紀錄"
    g, n, r, j = s["gap"], s["noise"], s["runs"], s["judge"]
    parts = [f"{g['wins'] or 0} 勝 {g['losses'] or 0} 負 {g['ties'] or 0} 平" if g and g.get("pairs") else "沒有差距數字",
             (f"雜訊 {n['rate']:.0%}" if n and n["pairs"] else "沒量雜訊基準"),
             (f"每組 {max(r['files'].values())} 次" if r and r.get("files") else
              f"每組每題 {r['per_question']} 次" if r and r.get("per_question") else "次數不明"),
             f"評審 {j['family'] or j['model']}" if j else "評審不明",
             f"沒驗證到 {len(s['unverified'])} 項" if s["unverified"] else "沒驗證到的部分沒列"]
    return "、".join(parts)


# ---------- selftest ----------

def selftest():
    fails = []

    def check(name, ok):
        print(("通過" if ok else "失敗") + "：" + name)
        if not ok:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        ev = repo / "data" / "evals"
        f = ev / "2026-01-01-x-A"
        (f / "out").mkdir(parents=True)
        (ev / "2026-01-01-x-A.md").write_text("紀錄", encoding="utf-8")
        (ev / "manual.md").write_text("手動盲選", encoding="utf-8")
        (f / "result.json").write_text(json.dumps({"slot": "x", "verdict": "Update", "winner": "new", "eval_doc": "data/evals/2026-01-01-x-A.md",
                                                   "decided_by": "rule", "unverified": ["手機版沒測"]}), encoding="utf-8")
        (f / "verdict.json").write_text(json.dumps({"arms": {"new": {"tool": "new", "pairs": 6, "wins": 4, "losses": 1, "ties": 1, "net": 0.5}},
                                                    "noise": {"pairs": 3, "decisive": 1, "rate": 1 / 3}}), encoding="utf-8")
        (f / "spec.yaml").write_text("model: claude-sonnet-5-5\nruns: 3\nquestions: {Q1: a, Q2: b}\n", encoding="utf-8")
        (f / "judge-1.json").write_text(json.dumps({"judge": {"provider": "antigravity", "model": "gemini-4-hydrogen"}}), encoding="utf-8")
        for arm in ("old", "new"):
            for q in ("Q1", "Q2"):
                for n in (1, 2, 3):
                    (f / "out" / f"{arm}-{q}-{n}.json").write_text("{}", encoding="utf-8")

        s = summary(repo, "data/evals/2026-01-01-x-A.md", "new")
        ls = lines(s)
        check("md 找到同名資料夾", s["structured"])
        check("差距", ls[0] == "差距：new 對現任比了 6 組，4 勝 1 負 1 平，淨 +0.50")
        check("雜訊基準", ls[1] == "雜訊基準：現任自己比自己 3 組，1 組分出勝負（33%）")
        check("執行次數", ls[2] == "執行次數：每組每題 3 次、2 題；實際執行 new 6 次、old 6 次")
        check("評審家族不同", ls[3] == "評審：Gemini（gemini-4-hydrogen），執行的是 Claude（claude-sonnet-5-5），不同家")
        check("沒驗證到", ls[4] == "沒驗證到：手機版沒測")
        check("通知一句", brief(s) == "4 勝 1 負 1 平、雜訊 33%、每組 6 次、評審 Gemini、沒驗證到 1 項")
        check("result.json 路徑也能讀", summary(repo, "data/evals/2026-01-01-x-A/result.json")["gap"]["wins"] == 4)

        # 沒有雜訊組、評審跟執行同一家
        (f / "verdict.json").write_text(json.dumps({"arms": {"new": {"pairs": 2, "wins": 2, "losses": 0, "ties": 0}},
                                                    "noise": {"pairs": 0, "decisive": 0, "rate": None}}), encoding="utf-8")
        (f / "judge-1.json").write_text(json.dumps({"judge": {"model": "claude-opus-5-5"}}), encoding="utf-8")
        s = summary(repo, "data/evals/2026-01-01-x-A.md")
        check("沒雜訊照實說", lines(s)[1].startswith("雜訊基準：沒有量") and "沒量雜訊基準" in brief(s))
        check("同家評審要標", "同一家" in lines(s)[3])

        # 只有文字的紀錄、找不到的紀錄
        s = summary(repo, "data/evals/manual.md")
        check("只有文字", not s["structured"] and "只有文字紀錄" in lines(s)[0] and brief(s).startswith("紀錄只有文字"))
        s = summary(repo, "data/evals/none.md")
        check("找不到", "找不到紀錄" in lines(s)[0] and brief(s) == "找不到實測紀錄")
        check("沒給路徑", "沒有紀錄路徑" in lines(summary(repo, None))[0])
        check("replaces 沒實測的字", NO_TEST.startswith("沒有實測"))
        check("家族", family("gpt-5.5") == "OpenAI" and family("x") is None)

    # 真實紀錄：WR1（沒有雜訊組）
    real = summary(REPO, "data/evals/2026-11-13-web-sources-WR1.md", "firecrawl")
    if real["structured"]:
        check("真實紀錄 WR1", "4 勝 1 負 1 平" in lines(real)[0] and lines(real)[1].startswith("雜訊基準：沒有量"))

    print(f"\n{'全部通過' if not fails else f'{len(fails)} 項失敗'}")
    return 1 if fails else 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    sh = sub.add_parser("show")
    sh.add_argument("evidence")
    sh.add_argument("--tool")
    args = p.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.cmd == "show":
        for line in lines(summary(REPO, args.evidence, args.tool)):
            print("- " + line)
        return
    p.print_help()


if __name__ == "__main__":
    main()
