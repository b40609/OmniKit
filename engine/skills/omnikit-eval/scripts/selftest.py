# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""評估 skill 的離線自我測試：不連網，預期值從名冊本身推導，名冊改了也不會誤報。CI 也會跑。

用法：uv run scripts/selftest.py
"""
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import _omnikit
import layer0

HERE = Path(__file__).parent


def run(script, *args):
    """在同一個 Python 裡執行另一支腳本的 main()，回傳它印出的文字。"""
    module = __import__(script)
    sys.argv = [script, *args]
    out = io.StringIO()
    with redirect_stdout(out):
        module.main()
    return out.getvalue()


def main():
    _omnikit.utf8_stdout()
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    for text, want in [
        ("https://github.com/pbakaus/impeccable", "pbakaus/impeccable"),
        ("github.com/pbakaus/impeccable/tree/main/skill", "pbakaus/impeccable"),
        ("git@github.com:pbakaus/impeccable.git", "pbakaus/impeccable"),
        ("pbakaus/impeccable", "pbakaus/impeccable"),
        ("https://example.com/x", None),
    ]:
        check(f"解析網址 {text}", layer0.parse_repo(text) == want)

    roster = _omnikit.roster()
    tools = list(roster["tools"].values())
    ids = lambda hits: [h["id"] for h in hits]  # noqa: E731

    by_url = next(t for t in tools if layer0.repo_key(t.get("url")))
    check(f"名冊比對：用卡片網址找到 {by_url['id']}",
          by_url["id"] in ids(layer0.roster_matches(layer0.repo_key(by_url["url"]), roster)))
    for t in tools:
        source = next((s for s in (t.get("plugin") or {}).values() if isinstance(s, dict) and layer0.repo_key(s.get("url"))), None)
        if source:
            check(f"名冊比對：用 plugin 來源找到 {t['id']}",
                  t["id"] in ids(layer0.roster_matches(layer0.repo_key(source["url"]), roster)))
            break
    check("名冊比對：沒收錄的回空陣列", layer0.roster_matches("nobody/nothing-here", roster) == [])

    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    stale = {"archived": True, "pushed_at": "2024-01-01T00:00:00Z", "license": None, "stars": 3}
    check("門檻：封存是 fail，其他是 warn",
          {c["rule"]: c["level"] for c in layer0.thresholds(stale, now)} == {"archived": "fail", "stale": "warn", "license": "warn", "adoption": "warn"})
    fresh = {"archived": False, "pushed_at": "2026-11-01T00:00:00Z", "license": "MIT", "stars": 900}
    check("門檻：健康的 repo 沒有警告", layer0.thresholds(fresh, now) == [])

    merged = layer0.summarize([
        {"path": "a", "findings": [{"severity": "MEDIUM", "rule": "NET", "where": "x.js"}] * 3},
        {"path": "b", "findings": [{"severity": "MEDIUM", "rule": "NET", "where": "x.js"}] * 2},
    ])
    check("掃描摘要：同一份 skill 重複標記只算一份", [(f["skills"], f["hits"]) for f in merged] == [(2, 5)])

    for slot in roster["slots"]:
        expected = {t["id"] for t in tools if slot["id"] in t["slots"] and t["status"] in ("default", "trial")}
        if expected:
            got = {t["id"] for t in json.loads(run("peers", slot["id"]))["incumbents"]}
            check(f"配對：{slot['id']} 槽位的現任", got == expected)
            break

    trial = next((t for t in tools if t["status"] == "trial"), None)
    if trial:
        today = date.fromisoformat(trial["trial_until"]) - timedelta(days=6)
        digest = run("digest", "--today", today.isoformat(), "--no-usage")
        check(f"彙整：列出快到期的試用（{trial['name']}）", trial["name"] in digest and "剩 6 天" in digest)
        check("彙整：加 --no-usage 不讀使用紀錄", "沒用到的 skill 與 plugin" not in digest)
    digest = run("digest", "--usage-days", "14")
    active_pending = any(s["focus"] == "active" and any(s["id"] in t["slots"] and t["status"] == "pending" for t in tools)
                         for s in roster["slots"])
    if active_pending:
        check("彙整：列出建議評估的槽位", "- [ ] " in digest)
    if (_omnikit.ROOT / "data" / "funnel" / "layer0.json").exists():
        check("彙整：有漏斗資料時列出第 0 層與外部證據", "## 評估漏斗" in digest and "- 第 0 層（" in digest
              and "值得實測的外部證據" in digest)
    if (_omnikit.ROOT / "data" / "funnel" / "layer2-schedule.json").exists():
        check("彙整：有排程檔時列出第 2 層排程提案", "- 第 2 層排程提案（" in digest)
    check("彙整：最後一節是沒用到的 skill 與 plugin（使用紀錄讀不到也不中斷）",
          "## 14 天沒用到的 skill 與 plugin" in digest and "- 讀" in digest.split("## 14 天沒用到的 skill 與 plugin")[1])

    for path in sorted((HERE.parent / "contracts").glob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
            check(f"契約是合法 JSON：{path.name}", True)
        except json.JSONDecodeError:
            check(f"契約是合法 JSON：{path.name}", False)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
