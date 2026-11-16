"""計分：C1 對標準答案（AST 與 git grep 事先算好），C2 檢查 檔案:行號 引用是否存在；也記有沒有用到挑戰者的工具。"""
import json, re, sys
from pathlib import Path

S = Path(__file__).resolve().parent
DIRECT = {("app/brain.py", 195), ("app/mcp_server.py", 488), ("app/providers/__init__.py", 105),
          ("app/providers/__init__.py", 122), ("app/providers/__init__.py", 126), ("app/radar/digest.py", 10),
          ("app/radar/dreampass.py", 29), ("app/watch/relevance.py", 33), ("app/watch/scanner.py", 57)}
INDIRECT = {"app/parsers/reel.py", "app/pipeline.py", "app/research/competitor_detector.py",
            "app/research/tool_resolver.py", "app/refetch.py", "app/routers/items.py"}
DIRECT_FILES = {f for f, _ in DIRECT}
REF = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:py|md|txt|json|toml|yaml|yml))[:：]\s*L?(\d+)(?:\s*[-–~]\s*L?(\d+))?")


def norm(p):
    p = p.replace("\\", "/")
    m = re.search(r"(app/.*|clink/.*|tools/.*|systemprompts/.*|conf/.*|utils/.*|config\.py|server\.py|docs/.*|tests/.*)", p)
    return m.group(1) if m else p.lstrip("./")


def used(rec, group):
    if group == "native":
        return None
    # 真的用到才算：叫用 skill、跑它的 CLI 或腳本、讀它產生的圖或地圖。
    # 資料夾名稱（graphify-pal）與 grep 排除 graphify-out 都不算（第一版計分把這些誤算成用到）。
    pats = {"graphify": r"\"skill\":\s*\"graphify|(^|[\s;&|(\"'])graphify(\.exe)?\s+(query|explain|path|update)\b"
                        r"|graphify-out[\\/]+(graph\.json|GRAPH_REPORT\.md)",
            "floorplan": r"\"skill\":\s*\"floorplan|floorplan[\\/]+(query\.mjs|graph\.json|architecture\.json)"
                         r"|scripts[\\/]+(status|query)\.mjs|query\.mjs\s+(overview|find|show|path)"}
    full = []
    for line in (S / "out" / f"{rec['name']}.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            full += [json.dumps(c.get("input"), ensure_ascii=False) for c in ev["message"].get("content", [])
                     if c.get("type") == "tool_use"]
    hits = [x for x in full if re.search(pats[group.removesuffix("-forced")], x) and "!graphify-out" not in x]
    return len(hits)


def c1(ans):
    tail = ans[ans.find("DIRECT"):] if "DIRECT" in ans else ans
    ind_at = tail.find("INDIRECT")
    direct_txt, ind_txt = (tail[:ind_at], tail[ind_at:]) if ind_at >= 0 else (tail, "")
    got = {(norm(f), int(l)) for f, l, _ in REF.findall(direct_txt)}
    hit = {d for d in DIRECT if any(g[0] == d[0] and abs(g[1] - d[1]) <= 2 for g in got)}
    fp = {g for g in got if not any(g[0] == d[0] and abs(g[1] - d[1]) <= 2 for d in DIRECT)}
    files = {norm(m) for m in re.findall(r"(app/[A-Za-z0-9_./-]+\.py)", ind_txt)}
    ihit = files & INDIRECT
    ifp = files - INDIRECT - DIRECT_FILES
    return {"direct_hit": len(hit), "direct_fp": len(fp), "indirect_hit": len(ihit), "indirect_fp": len(ifp),
            "score": len(hit) + len(ihit), "errors": len(fp) + len(ifp),
            "missed": sorted(f"{f}:{l}" for f, l in DIRECT - hit) + sorted(INDIRECT - ihit),
            "wrong": sorted(f"{f}:{l}" for f, l in fp) + sorted(ifp)}


FILES = None


def c2(ans, repo):
    """短路徑（registry.py:58）照 repo 裡結尾相符的檔案找；有任何一個候選的行數夠就算存在，另記有歧義的。"""
    global FILES
    if FILES is None:
        FILES = {p.relative_to(repo).as_posix(): len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                 for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    refs = REF.findall(ans)
    ok = bad = 0
    bads = []
    for f, a, b in refs:
        f = norm(f)
        cands = [k for k in FILES if k == f or k.endswith("/" + f)]
        if not cands:
            bad += 1; bads.append(f"{f}:{a}（沒有這個檔）"); continue
        top = int(b or a)
        if any(FILES[k] >= top for k in cands):
            ok += 1
        else:
            bad += 1; bads.append(f"{f}:{a}（超過檔案行數）")
    return {"refs": len(refs), "refs_ok": ok, "refs_bad": bad, "ok_rate": round(ok / len(refs), 3) if refs else None,
            "bad_examples": bads[:5]}


rows = []
for p in sorted((S / "out").glob("*-C?-[1-9].json")):
    rec = json.loads(p.read_text(encoding="utf-8"))
    g, q = rec["group"], rec["q"]
    row = {"name": rec["name"], "group": g, "q": q, "used_tool": used(rec, g), "seconds": rec["seconds"],
           "cost": rec.get("cost"), "turns": rec.get("turns"), "tool_calls": len(rec["tools"])}
    row.update(c1(rec["answer"]) if q == "C1" else c2(rec["answer"], S / "base-pal"))
    rows.append(row)
(S / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
