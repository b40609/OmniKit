# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""當下提醒用的兩種小提示（session_nudge.py 呼叫；不匯入任何第三方套件）。

1. due(agent)：主線對話第一回合結束時講一則用法提示。內容在 data/tips.json，一天最多一則，每則只講一次。
   新的官方功能加進 data/tips.json 的最後，使用者就會在下一次開對話時聽到一次。
2. insights_due()：這段對話第一次 git push（一件事告一段落）時，如果 Claude Code 的 /insights 報告超過 14 天沒更新
   （或從沒跑過），提醒一句。14 天內只提醒一次。只有 Claude Code 有 /insights。

「OmniKit 通知靜音」（~/.omnikit/notify/mute.json 的 all）與環境變數 CI、OMNIKIT_NO_NOTIFY 都會讓兩種提示安靜。
只寫 ~/.omnikit/tips/state.json。任何錯誤都當成沒有提示。

自我測試：uv run engine/scripts/tips.py --selftest
"""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statedir  # noqa: E402  同一個資料夾，沒有相依套件

STATE = statedir.STATE  # ~/.omnikit
TIPS = Path(__file__).resolve().parents[2] / "data" / "tips.json"
REPORT = Path.home() / ".claude" / "usage-data" / "report.html"
INSIGHTS_DAYS = 14
INSIGHTS = ("這件事告一段落了。/insights 已經 {age} 沒跑：它會讀你最近的對話，整理常卡住的地方與建議寫進規則檔的內容。"
            "拿到建議後，只挑重複發生兩次以上的錯誤寫進規則檔或確定性 hook。")


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def quiet(state, env):
    return bool(env.get("CI") or env.get("OMNIKIT_NO_NOTIFY")
                or read_json(Path(state) / "notify" / "mute.json", {}).get("all"))


def due(agent, state=STATE, today=None, env=None, tips=TIPS):
    """這個 agent 還沒講過的第一則提示；今天已經講過一則就不再講。講了就記下來。"""
    env = os.environ if env is None else env
    if quiet(state, env):
        return None
    today = (today or date.today()).isoformat()
    path = Path(state) / "tips" / "state.json"
    st = read_json(path, {})
    if st.get("last_day") == today:
        return None
    shown = set(st.get("shown") or [])
    for tip in read_json(tips, {}).get("tips") or []:
        if tip.get("id") not in shown and agent in (tip.get("agents") or []) and tip.get("text"):
            st["shown"] = sorted(shown | {tip["id"]})
            st["last_day"] = today
            write_json(path, st)
            return tip["text"]
    return None


def insights_due(state=STATE, now=None, env=None, report=REPORT):
    """/insights 的報告超過 14 天沒更新（或沒有）而且 14 天內沒提醒過：回提醒文字並記下來。"""
    env = os.environ if env is None else env
    if quiet(state, env):
        return None
    now = now or datetime.now()
    path = Path(state) / "tips" / "state.json"
    st = read_json(path, {})
    try:
        last = datetime.fromisoformat(st.get("insights_reminded", ""))
    except ValueError:
        last = None
    if last and now - last < timedelta(days=INSIGHTS_DAYS):
        return None
    try:
        age = now - datetime.fromtimestamp(Path(report).stat().st_mtime)
        if age < timedelta(days=INSIGHTS_DAYS):
            return None
        text = f"{age.days} 天"
    except OSError:
        text = "很久（這台還沒有報告）"
    st["insights_reminded"] = now.isoformat(timespec="seconds")
    write_json(path, st)
    return INSIGHTS.format(age=text)


def selftest():
    def ok(name, cond):
        if not cond:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tips = tmp / "tips.json"
        tips.write_text(json.dumps({"tips": [
            {"id": "a", "agents": ["claude"], "text": "甲"},
            {"id": "b", "agents": ["codex"], "text": "乙"},
            {"id": "c", "agents": ["claude", "codex"], "text": "丙"}]}), encoding="utf-8")
        d1, d2, d3 = date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)
        st = tmp / "s1"
        ok("第一則給對應的 agent", due("claude", st, d1, {}, tips) == "甲")
        ok("同一天不講第二則", due("claude", st, d1, {}, tips) is None)
        ok("隔天講下一則，跳過不是這個 agent 的", due("claude", st, d2, {}, tips) == "丙")
        ok("講完就沒有了", due("claude", st, d3, {}, tips) is None)
        ok("另一個 agent 只拿到自己還沒聽過的", due("codex", st, d3, {}, tips) == "乙")
        ok("CI 與 OMNIKIT_NO_NOTIFY 都安靜", due("claude", tmp / "s2", d1, {"CI": "1"}, tips) is None
           and due("claude", tmp / "s2", d1, {"OMNIKIT_NO_NOTIFY": "1"}, tips) is None)
        write_json(tmp / "s3" / "notify" / "mute.json", {"all": True})
        ok("通知靜音時不講", due("claude", tmp / "s3", d1, {}, tips) is None)
        ok("提示檔壞掉或不存在當成沒有", due("claude", tmp / "s4", d1, {}, tmp / "nope.json") is None)

        now = datetime(2026, 11, 17, 12, 0)
        st = tmp / "i1"
        ok("沒有報告：提醒", "還沒有報告" in (insights_due(st, now, {}, tmp / "none.html") or ""))
        ok("14 天內不再提醒", insights_due(st, now + timedelta(days=13), {}, tmp / "none.html") is None)
        ok("過了 14 天再提醒", insights_due(st, now + timedelta(days=15), {}, tmp / "none.html") is not None)
        rep = tmp / "report.html"
        rep.write_text("x", encoding="utf-8")
        fresh = datetime.fromtimestamp(rep.stat().st_mtime)
        ok("報告是新的：不提醒", insights_due(tmp / "i2", fresh + timedelta(days=3), {}, rep) is None)
        msg = insights_due(tmp / "i2", fresh + timedelta(days=20), {}, rep)
        ok("報告超過 14 天：提醒並寫出幾天", msg is not None and "20 天" in msg)
        ok("靜音時不提醒", insights_due(tmp / "s3", now, {}, tmp / "none.html") is None)
        ok("真的提示檔讀得懂、id 不重複、每則都有對象與文字",
           (real := read_json(TIPS, {}).get("tips")) and len({t["id"] for t in real}) == len(real)
           and all(t.get("text") and set(t.get("agents") or []) <= {"claude", "codex"} and t.get("agents") for t in real))
    print("tips selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
