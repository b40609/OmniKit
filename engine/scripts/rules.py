# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""規則檔的事實：每段對話實際載入了哪些規則檔、多大，以及裡面一條一條的規則。給 advise.py 的「規則檔瘦身」用。

只讀本機、不連網、不寫檔。規則的文字是使用者自己寫的設定，會原樣放進輸出給 agent 判斷；對話內容不讀。

以 agent 實際載入的為準，讀不到對話紀錄才看磁碟上的檔案：
- Claude Code：最近一段互動對話在第一個回應之前的 instructions（每個檔的路徑、類型與內容）。
  類型是 AutoMem 的是自動記憶的索引，不是規則，只算大小。
- Codex：最近一段互動 rollout 開頭那則「# AGENTS.md instructions」訊息裡 <INSTRUCTIONS> 包住的內容。

一條規則是一行清單項目或一行文字；標題、空行、註解、@import 與表格的分隔線不算。腳本只標得出來的訊號：
- 安全底線的規則：受保護，不會變成候選（底線不能放寬）
- generated：跟訪談範本裡「想改善的習慣」「工作習慣」一字不差，是訪談產生的通用規則
- duplicate：同一條在載入的規則裡出現不只一次
- generic：通用的口號（be thorough、step by step、不要偷懶這類）
- emphasis：語氣很重（全大寫的 MUST、NEVER，或「務必」「絕對」這類字）
- long：一條就很長
另外對整個檔標出：超過 200 行（Claude Code 官方的建議）、合計超過 Codex 預設的 32 KiB。
一條規則是不是「這個 agent 現在預設就會做的行為修正」，腳本判斷不了，留給 agent 挑選時寫理由。
Claude Code 內建的 /doctor 也會檢查規則檔（重複、codebase 推得出的內容、為舊模型寫的指令）；這裡補的是
每段對話實際的成本、Codex 那一邊，以及安全底線不會被列進候選。

用法：
  uv run engine/scripts/rules.py [--json]     印出這台兩個 agent 載入的規則檔與大小
  uv run engine/scripts/rules.py --selftest
"""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost  # noqa: E402
import profile_new  # noqa: E402
import profiles  # noqa: E402

AGENTS = ("claude", "codex")
RECENT = 60          # 最多往回看幾段對話找規則檔的載入紀錄
LONG = 80            # 一條規則超過這麼多 token 算長
BEGIN, END = "omnikit:rules:begin", "omnikit:rules:end"
CODEX_HEAD = "# AGENTS.md instructions"
MAX_LINES = 200      # Claude Code 官方建議每個規則檔 200 行以下
CODEX_BYTES = 32 * 1024  # Codex 的 project_doc_max_bytes 預設值：合計超過就不再加入
EMPHASIS = re.compile(r"\b(?:IMPORTANT|MUST|NEVER|ALWAYS|CRITICAL|MANDATORY|DO NOT)\b|務必|絕對|一定要|千萬|嚴禁|絕不")
# 通用的口號：兩家的提示詞指南都說新模型不需要，還可能過度套用
GENERIC = re.compile(r"\b(?:be thorough|think (?:hard|harder|carefully|step by step)|step[- ]by[- ]step|don'?t be lazy|"
                     r"keep going|take a deep breath)\b|一步一步|逐步思考|仔細思考|深思熟慮|不要偷懶|全力以赴", re.I)
MARK = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
LABEL = re.compile(r"^(?:profile|規則版本|rules version)\s*[：:]", re.I)  # 檔案自己的標記行，不是規則
TABLE_RULE = re.compile(r"^\|?\s*:?-{2,}")


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def tilde(path, home):
    try:
        return "~/" + Path(path).resolve().relative_to(Path(home).resolve()).as_posix()
    except (ValueError, OSError):
        return str(path).replace("\\", "/")


def read(path):
    try:
        return Path(path).read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return None


# ---------- 實際載入的規則檔 ----------

def claude_from_sessions(home):
    """最近一段互動對話第一個回應之前的 instructions：[{path, type, content}]，連同那段對話的日期。"""
    root = Path(home) / ".claude" / "projects"
    if not root.is_dir():
        return None
    files = sorted((p for p in root.glob("*/*.jsonl")), key=lambda p: p.stat().st_mtime, reverse=True)[:RECENT]
    for p in files:
        background, found = False, None
        try:
            f = p.open("rb")
        except OSError:
            continue
        with f:
            for raw in f:
                if b'"entrypoint"' in raw and (d := cost.loads(raw)) and str(d.get("entrypoint") or "").startswith("sdk"):
                    background = True
                    break
                if b'"type":"assistant"' in raw and (d := cost.loads(raw)) and d.get("type") == "assistant":
                    break
                if b'"instructions"' in raw and (d := cost.loads(raw)) and d.get("type") == "attachment":
                    a = d.get("attachment") if isinstance(d.get("attachment"), dict) else {}
                    if a.get("type") == "instructions" and not a.get("changed"):
                        found = [{"path": str(e.get("path") or ""), "type": str(e.get("type") or ""), "content": str(e.get("content") or "")}
                                 for e in a.get("files") or [] if isinstance(e, dict)]
        if found and not background:
            return {"source": "session", "when": date.fromtimestamp(p.stat().st_mtime).isoformat(), "files": found}
    return None


def claude_from_disk(home):
    """沒有對話紀錄時：~/.claude/CLAUDE.md 加上它 @import 的檔（只展開一層）。"""
    main = Path(home) / ".claude" / "CLAUDE.md"
    text = read(main)
    if text is None:
        return None
    files = [{"path": str(main), "type": "User", "content": text}]
    for line in text.splitlines():
        if line.startswith("@"):
            target = Path(line[1:].strip().replace("\\ ", " ")).expanduser()
            if (content := read(target)) is not None:
                files.append({"path": str(target), "type": "User", "content": content})
    return {"source": "disk", "when": None, "files": files}


def codex_from_sessions(home):
    root = Path(home) / ".codex" / "sessions"
    if not root.is_dir():
        return None
    for p in sorted(root.glob("*/*/*/rollout-*.jsonl"), reverse=True)[:RECENT]:
        try:
            f = p.open("rb")
        except OSError:
            continue
        with f:
            for i, raw in enumerate(f):
                if i > 60:
                    break
                d = cost.loads(raw) if (b"session_meta" in raw or CODEX_HEAD.encode() in raw) else None
                payload = d.get("payload") if d and isinstance(d.get("payload"), dict) else {}
                if d and d.get("type") == "session_meta" and payload.get("source") == "exec":
                    break  # 非互動的不算
                for c in payload.get("content") or []:
                    text = c.get("text", "") if isinstance(c, dict) else ""
                    if CODEX_HEAD in text and "<INSTRUCTIONS>" in text:
                        body = text.split("<INSTRUCTIONS>", 1)[1].rsplit("</INSTRUCTIONS>", 1)[0].strip("\n")
                        return {"source": "session", "when": date.fromtimestamp(p.stat().st_mtime).isoformat(),
                                "files": [{"path": str(Path(home) / ".codex" / "AGENTS.md"), "type": "User", "content": body}]}
    return None


def codex_from_disk(home):
    path = Path(home) / ".codex" / "AGENTS.md"
    text = read(path)
    return None if text is None else {"source": "disk", "when": None, "files": [{"path": str(path), "type": "User", "content": text}]}


def loaded(home, agent):
    if agent == "claude":
        return claude_from_sessions(home) or claude_from_disk(home)
    return codex_from_sessions(home) or codex_from_disk(home)


# ---------- 一條一條的規則 ----------

def split(content):
    """規則檔 → [(行號, 所在的標題, 文字, 在不在 OmniKit 的受管區塊裡)]。標題、空行、註解、@import、表格分隔線與程式碼區塊不算。"""
    out, section, managed, fenced = [], "", False, False
    for n, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if BEGIN in line:
            managed = True
        if END in line:
            managed = False
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line or line.startswith(("<!--", "@", ">")) or TABLE_RULE.match(line):
            continue
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        text = MARK.sub("", line).strip()
        if text and not LABEL.match(text):
            out.append((n, section, text, managed))
    return out


def template_habits():
    """訪談範本裡的通用規則：{正規化的文字: 是哪一題}。這些是訪談產生的，不是使用者自己寫的。"""
    out = {}
    for lang in profile_new.TEXT.values():
        for key, label in (("pains", "想改善的習慣"), ("work", "工作習慣")):
            for text in lang[key].values():
                out[norm(text)] = label
    return out


def inspect(found, home, baseline, profile_file=None, agent="claude"):
    """實際載入的規則檔 → 給 advise.py 的事實：每個檔的大小，以及不受保護的每一條規則與腳本標得出的訊號。"""
    if not found:
        return None
    protected = {norm(text) for _, _, text, _ in split(baseline or "")}
    habits = template_habits()
    files, rows = [], []
    for f in found["files"]:
        memory = f["type"] == "AutoMem"
        entry = {"file": tilde(f["path"], home), "type": "memory" if memory else f["type"].lower() or "user",
                 "lines": len(f["content"].splitlines()), "tokens": cost.estimate(f["content"])}
        files.append(entry)
        if memory:
            continue  # 自動記憶的索引不是規則，只算大小
        for n, section, text, managed in split(f["content"]):
            # Codex 讀的是 OmniKit 接好的副本：受管區塊裡的規則要回來源的 profile 改
            source = tilde(profile_file, home) if managed and profile_file else entry["file"]
            rows.append({"file": source, "loaded_from": entry["file"], "line": n, "section": section, "text": text,
                         "managed": managed, "key": norm(text)})
    counts = {}
    for r in rows:
        counts[r["key"]] = counts.get(r["key"], 0) + 1
    units, seen, kept = [], set(), 0
    for r in rows:
        if r["key"] in protected:
            kept += 1
            continue
        if r["key"] in seen:
            continue
        seen.add(r["key"])
        signals = []
        if r["key"] in habits:
            signals.append({"code": "generated", "text": f"訪談產生的通用規則（{habits[r['key']]}），不是你自己寫的"})
        if counts[r["key"]] > 1:
            signals.append({"code": "duplicate", "text": f"同一條在載入的規則裡出現 {counts[r['key']]} 次"})
        if GENERIC.search(r["text"]):
            signals.append({"code": "generic", "text": "通用的口號，新模型不需要這類指令"})
        if EMPHASIS.search(r["text"]):
            signals.append({"code": "emphasis", "text": "語氣很重：建議改成平鋪直敘，不能有例外的改用 hook 或權限規則"})
        tokens = cost.estimate(r["text"])
        if tokens >= LONG:
            signals.append({"code": "long", "text": f"一條約 {tokens} tokens"})
        units.append({"id": "rule:" + hashlib.sha1(r["key"].encode("utf-8")).hexdigest()[:10], "text": r["text"],
                      "file": r["file"], "loaded_from": r["loaded_from"], "line": r["line"], "section": r["section"],
                      "managed": r["managed"], "tokens": tokens, "signals": signals})
    rule_files = [f for f in files if f["type"] != "memory"]
    warnings = [f"{f['file']} 有 {f['lines']} 行，超過建議的 {MAX_LINES} 行" for f in rule_files if f["lines"] > MAX_LINES]
    size = sum(len(f["content"].encode("utf-8")) for f in found["files"] if f["type"] != "AutoMem")
    if agent == "codex" and size > CODEX_BYTES:
        warnings.append(f"合計 {size:,} 位元組，超過 Codex 預設的上限 {CODEX_BYTES:,}：後面的內容不會被讀到")
    return {"source": found["source"], "when": found["when"], "files": files, "warnings": warnings,
            "tokens": sum(f["tokens"] for f in rule_files), "memory_tokens": sum(f["tokens"] for f in files if f["type"] == "memory"),
            "protected": kept, "units": units,
            # OmniKit 的 profile 來源檔：改這個檔之後要重新接上，Codex 與 Antigravity 讀的副本才會變
            "profile_file": tilde(profile_file, home) if profile_file else None,
            "profile_generated": bool(profile_file and (Path(profile_file).parent / "answers.json").exists())}


def collect(home, data, state, profile_dir=None):
    baseline = read(Path(data) / "rules" / "baseline.md") or ""
    profile_file = Path(profile_dir) / "AGENTS.md" if profile_dir else None
    return {agent: inspect(loaded(home, agent), home, baseline, profile_file, agent) for agent in AGENTS}


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        home = Path(tmp) / "home"

        def put(path, text):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path

        def jsonl(path, records):
            put(path, "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records))

        baseline = "# 底線\n\n## 先確認才做\n- 刪除前先確認。\n- 不讀金鑰。\n"
        habit = profile_new.TEXT["zh-TW"]["pains"]["guesses"]
        mine = ("# 個人規則\n\nprofile：me\n\n## 語言\n- 用繁體中文回覆。\n\n## 習慣\n"
                f"- {habit}\n- 刪除前先確認。\n- 你 MUST 每次都跑測試，絕對不能跳過。\n- Be thorough，不要偷懶。\n- "
                + "很長的一條規則，" * 20 + "\n"
                "\n| 欄 | 值 |\n|---|---|\n\n```\n- 程式碼區塊裡的不算\n```\n<!-- 註解不算 -->\n@C:/somewhere/else.md\n")
        profile = put(home / "kit" / "profiles" / "me" / "AGENTS.md", mine)
        base = put(home / "kit" / "rules" / "baseline.md", baseline)
        attach = {"type": "attachment", "attachment": {"type": "instructions", "files": [
            {"path": str(home / ".claude" / "CLAUDE.md"), "type": "User", "content": f"@{base}\n@{profile}\n"},
            {"path": str(base), "type": "User", "content": baseline},
            {"path": str(profile), "type": "User", "content": mine},
            {"path": str(home / "proj" / "CLAUDE.md"), "type": "Project", "content": "# 專案\n- 用繁體中文回覆。\n- 測試指令是 npm test。\n"},
            {"path": str(home / ".claude" / "projects" / "p" / "memory" / "MEMORY.md"), "type": "AutoMem", "content": "- 記憶索引 " * 30}]}}
        start = {"type": "user", "entrypoint": "claude-desktop", "message": {"role": "user", "content": "秘密內容"}}
        answer = {"type": "assistant", "message": {"content": [{"type": "text", "text": "回答"}]}}
        later = {"type": "attachment", "attachment": {"type": "instructions", "changed": True, "files": [
            {"path": "x", "type": "User", "content": "- 之後才載入的"}]}}
        jsonl(home / ".claude" / "projects" / "p" / "talk.jsonl", [start, attach, later, answer, later])
        found = loaded(home, "claude")
        check("Claude Code：規則檔照對話紀錄開頭實際載入的那一份，中途變動的增減不算",
              found["source"] == "session" and [Path(f["path"]).name for f in found["files"]]
              == ["CLAUDE.md", "baseline.md", "AGENTS.md", "CLAUDE.md", "MEMORY.md"])
        got = inspect(found, home, baseline, profile)
        texts = [u["text"] for u in got["units"]]
        by = {u["text"][:12]: u for u in got["units"]}
        check("一條一條拆開：標題、空行、註解、@import、表格分隔線與程式碼區塊不算",
              "用繁體中文回覆。" in texts and not any("程式碼區塊" in t or "註解" in t or t.startswith("@") or "---" in t
                                              or t.startswith("profile") for t in texts)
              and by["用繁體中文回覆。"]["section"] == "語言" and by["用繁體中文回覆。"]["file"] == "~/kit/profiles/me/AGENTS.md")
        check("安全底線的規則受保護，不會變成候選；使用者自己重寫的同一句也一樣", got["protected"] == 3
              and not any("刪除前先確認" in t or "不讀金鑰" in t for t in texts))
        def codes(start):
            return [s["code"] for u in got["units"] if u["text"].startswith(start) for s in u["signals"]]

        check("訊號：訪談產生的通用規則、重複、通用的口號、語氣很重、很長，各自標出來",
              codes(habit) == ["generated"] and codes("用繁體中文回覆。") == ["duplicate"] and codes("Be thorough") == ["generic"]
              and codes("你 MUST") == ["emphasis"] and codes("很長的一條規則") == ["long"] and codes("測試指令是") == [])
        big = inspect({"source": "disk", "when": None, "files": [
            {"path": str(home / "big.md"), "type": "User", "content": "- 一條規則，內容不重複 %d\n" * 201 % tuple(range(201))}]},
            home, baseline, agent="codex")
        huge = inspect({"source": "disk", "when": None, "files": [
            {"path": str(home / "huge.md"), "type": "User", "content": "- " + "很大的檔" * 3000 + "\n"}]}, home, baseline, agent="codex")
        check("整個檔的警告：超過 200 行；Codex 合計超過 32 KiB（後面的不會被讀到）；沒超過就沒有警告",
              len(big["warnings"]) == 1 and "201 行" in big["warnings"][0] and len(huge["warnings"]) == 1
              and "32,768" in huge["warnings"][0] and got["warnings"] == [])
        check("重複的規則只列一次，id 由文字決定（兩次執行對得上）",
              texts.count("用繁體中文回覆。") == 1 and by["用繁體中文回覆。"]["id"] == inspect(found, home, baseline)["units"][0]["id"])
        check("大小：規則檔與自動記憶分開算；自動記憶不拆成規則",
              got["tokens"] == sum(f["tokens"] for f in got["files"] if f["type"] != "memory") and got["memory_tokens"] > 0
              and [f["type"] for f in got["files"]] == ["user", "user", "user", "project", "memory"] and not any("記憶索引" in t for t in texts))
        check("不輸出對話內容", "秘密內容" not in json.dumps(got, ensure_ascii=False))

        jsonl(home / ".claude" / "projects" / "p" / "bg.jsonl", [{**start, "entrypoint": "sdk-ts"}, {
            "type": "attachment", "attachment": {"type": "instructions", "files": [{"path": "bg", "type": "User", "content": "- 背景的"}]}}])
        check("背景對話載入的不算", loaded(home, "claude")["files"][0]["path"].endswith("CLAUDE.md"))

        other = Path(tmp) / "disk"
        put(other / ".claude" / "CLAUDE.md", f"<!-- {BEGIN} -->\n@{base}\n<!-- {END} -->\n- 我自己加的一條\n")
        disk = inspect(loaded(other, "claude"), other, baseline)
        check("沒有對話紀錄：改看磁碟上的 CLAUDE.md 與它 @import 的檔", disk["source"] == "disk" and len(disk["files"]) == 2
              and [u["text"] for u in disk["units"]] == ["我自己加的一條"] and disk["protected"] == 2)

        block = f"<!-- {BEGIN} -->\n<!-- 由 OmniKit 產生 -->\n{baseline}\n{mine}\n<!-- {END} -->\n\n## 我原本的\n- 區塊外自己寫的。\n"
        message = f"{CODEX_HEAD}\n\n<INSTRUCTIONS>\n{block}</INSTRUCTIONS>"
        day = home / ".codex" / "sessions" / "2026" / "11" / "10"
        jsonl(day / "rollout-2026-11-10T09-00-00-a.jsonl", [
            {"type": "session_meta", "payload": {"source": "vscode"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": message}]}}])
        jsonl(day / "rollout-2026-11-10T10-00-00-b.jsonl", [
            {"type": "session_meta", "payload": {"source": "exec"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"{CODEX_HEAD}\n<INSTRUCTIONS>\n- 非互動的\n</INSTRUCTIONS>"}]}}])
        codex = inspect(loaded(home, "codex"), home, baseline, profile)
        where = {u["text"]: (u["file"], u["managed"]) for u in codex["units"]}
        check("Codex：照互動 rollout 開頭實際載入的 AGENTS.md；非互動的不算", codex["source"] == "session"
              and "非互動的" not in where and codex["protected"] == 3)
        check("Codex：受管區塊裡的規則要回 profile 的來源檔改，區塊外的改 ~/.codex/AGENTS.md",
              where["用繁體中文回覆。"] == ("~/kit/profiles/me/AGENTS.md", True)
              and where["區塊外自己寫的。"] == ("~/.codex/AGENTS.md", False))
        put(other / ".codex" / "AGENTS.md", "- 磁碟上的一條\n")
        check("Codex 沒有對話紀錄：改看 ~/.codex/AGENTS.md；兩邊都沒有就回 None",
              [u["text"] for u in inspect(loaded(other, "codex"), other, baseline)["units"]] == ["磁碟上的一條"]
              and loaded(Path(tmp) / "nobody", "claude") is None and inspect(None, home, baseline) is None)
        both = collect(home, home / "kit", Path(tmp) / "state", profile.parent)
        check("兩個 agent 一起收", set(both) == set(AGENTS) and both["codex"]["units"] and both["claude"]["units"])

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="這台兩個 agent 實際載入的規則檔與大小")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    import validate
    _, roster = validate.check(profiles.DATA, state=profiles.STATE)
    result = collect(Path.home(), profiles.DATA, profiles.STATE, roster.get("profile_dir"))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for agent, r in result.items():
        if not r:
            print(f"{agent}：找不到規則檔")
            continue
        print(f"{agent}：每段對話載入規則約 {r['tokens']:,} tokens、自動記憶約 {r['memory_tokens']:,} tokens"
              f"（{'對話紀錄 ' + r['when'] if r['source'] == 'session' else '磁碟上的檔案'}）；"
              f"安全底線 {r['protected']} 條、其他 {len(r['units'])} 條")
        for f in r["files"]:
            print(f"  - {f['file']}（{f['type']}）：{f['lines']} 行、約 {f['tokens']:,} tokens")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
