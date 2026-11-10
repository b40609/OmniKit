# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 與 Codex 的 Stop hook：該開新對話時提醒使用者。只提醒，不做任何動作。

兩種訊號（換主題只能靠模型判斷，不在這裡）：
1. 自動壓縮：這段對話累計第 1、3、9、27… 次自動壓縮發生在這一回合時提醒。
   不看 token 數：對話開頭的固定成本就有幾萬 tokens，各模型的上限也不同（Opus 1M、
   Codex 常設 96000），固定門檻一定會誤判；自動壓縮是 agent 自己判斷「滿了」，會跟著模型走。
2. 任務告一段落：這一回合成功跑了 git push，而且是這段對話的第一次（之後每回合都 push，不再提醒）。
Claude 的子對話（由別的對話開出來的）兩種都不提醒：做完就收，看收尾的狀態標籤就好。

從 stdin 讀 hook 輸入，再讀 transcript_path 的 JSONL（Claude Code 的對話紀錄或 Codex 的 rollout，
自動分辨）；有話要說就印 {"systemMessage": ...}。任何錯誤都安靜結束（exit 0），提醒壞掉不能干擾對話。

註冊：install.ps1 經 claude_allow.py 寫進 ~/.claude/settings.json 的 hooks.Stop，
經 codex_hooks.py 寫進 ~/.codex/config.toml 的 [[hooks.Stop]]。
自我測試：uv run engine/scripts/session_nudge.py --selftest
"""
import json
import re
import sys
import tempfile
from pathlib import Path

SHELLS = {"Bash", "PowerShell"}
# 只認指令開頭或 ; & | 之後的 git push，commit 訊息裡提到 git push 不算
PUSH = re.compile(r"(?:^|[;&|]\s*)git(?:\s+-C\s+\S+)*\s+push\b(?!.*--dry-run)", re.M)
PUSHED = "這一回合已推送到遠端。這件事若告一段落，下一件事建議開新對話。"
# Codex rollout 只解析含這些字的行；大型 rollout 可達上百 MB
CODEX_MARKS = ('"task_started"', '"compacted"', '"UserMessage"', '"CommandExecution"',
               '"user_message"', '"exec_command_end"')


def compacted(n: int, agent: str) -> str:
    return (f"這段對話已自動壓縮 {n} 次，早先的細節可能已經遺失。"
            f"下一件事若跟目前任務無關，建議開新對話；目前的任務要接著做，跟 {agent} 說「交接」就好。")


def is_prompt(e: dict) -> bool:
    """使用者自己送出的訊息；tool_result、系統插入的與壓縮後的摘要不算。"""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain") or e.get("isCompactSummary"):
        return False
    content = (e.get("message") or {}).get("content")
    return isinstance(content, str) or any(b.get("type") == "text" for b in content or [])


def auto_compacted(e: dict) -> bool:
    return e.get("type") == "system" and e.get("subtype") == "compact_boundary" \
        and (e.get("compactMetadata") or {}).get("trigger") == "auto"


def pushed(entries: list[dict]) -> bool:
    blocks = [b for e in entries
              if isinstance(c := (e.get("message") or {}).get("content"), list) for b in c]
    pushes = {b.get("id") for b in blocks if b.get("type") == "tool_use" and b.get("name") in SHELLS
              and PUSH.search(str((b.get("input") or {}).get("command", "")))}
    return any(b.get("type") == "tool_result" and b.get("tool_use_id") in pushes and not b.get("is_error")
               for b in blocks)


def nudge(entries: list[dict]) -> list[str]:
    prompts = [i for i, e in enumerate(entries) if is_prompt(e)]
    # 第一則訊息由別的對話送出（turnOrigin 是 sdk）就是子對話；舊紀錄沒有這個欄位，當成主線
    if prompts and entries[prompts[0]].get("turnOrigin") == "sdk":
        return []
    start = prompts[-1] if prompts else 0
    msgs = []
    compacts = [i for i, e in enumerate(entries) if auto_compacted(e)]
    during = sum(i >= start for i in compacts)
    if during and compaction_level(len(compacts)) > compaction_level(len(compacts) - during):
        msgs.append(compacted(len(compacts), "Claude"))
    if pushed(entries[start:]) and not pushed(entries[:start]):
        msgs.append(PUSHED)
    return msgs


def kind(e: dict) -> str | None:
    p = e.get("payload")
    return p.get("type") if isinstance(p, dict) else None


def compaction_level(n: int) -> int:
    """第 1、3、9、27… 次壓縮各升一級。"""
    level = 0
    while n >= 3 ** level:
        level += 1
    return level


def codex_items(entries: list[dict]):
    """item_completed 與舊版事件（user_message、exec_command_end）統一成 item；兩種寫法都看過。"""
    for e in entries:
        k = kind(e)
        if k == "item_completed":
            yield e["payload"].get("item") or {}
        elif k == "user_message":
            yield {"type": "UserMessage"}
        elif k == "exec_command_end":
            yield {**e["payload"], "type": "CommandExecution"}


def codex_pushed(items) -> bool:
    for it in items:
        argv = it.get("command") or []
        argv = [argv] if isinstance(argv, str) else [str(a) for a in argv]
        if it.get("type") == "CommandExecution" and it.get("exit_code") == 0 \
                and any(PUSH.search(a) for a in [*argv, " ".join(argv)]):
            return True
    return False


def codex_nudge(entries: list[dict], turn_id: str | None = None) -> list[str]:
    """Codex rollout：回合從 task_started 開始；壓縮次數是 compacted 的 window_number。"""
    starts = [i for i, e in enumerate(entries) if kind(e) == "task_started"]
    start = next((i for i in reversed(starts) if entries[i]["payload"].get("turn_id") == turn_id),
                 starts[-1] if starts else 0)
    items = list(codex_items(entries[start:]))
    if not any(it.get("type") == "UserMessage" for it in items):
        return []  # 手動 /compact 這類沒有使用者訊息的回合

    msgs = []
    windows = [(i, e["payload"].get("window_number", 0)) for i, e in enumerate(entries)
               if e.get("type") == "compacted" and isinstance(e.get("payload"), dict)]
    during = [w for i, w in windows if i > start]
    if during:
        # 分頁後的 rollout 可能不含之前的壓縮紀錄，就當這一回合的第一次壓縮之前是 n - 1 次
        prev = next((w for i, w in reversed(windows) if i < start), during[0] - 1)
        if compaction_level(during[-1]) > compaction_level(prev):
            msgs.append(compacted(during[-1], "Codex"))

    if codex_pushed(items) and not codex_pushed(codex_items(entries[:start])):
        msgs.append(PUSHED)
    return msgs


def read_jsonl(path: str) -> list[dict]:
    entries, codex = [], False
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f):
            if codex and not any(m in line for m in CODEX_MARKS):
                continue
            try:
                e = json.loads(line)
            except ValueError:  # 寫到一半的最後一行
                continue
            codex = codex or (n == 0 and e.get("type") == "session_meta")
            entries.append(e)
    return entries


def is_codex(entries: list[dict]) -> bool:
    return bool(entries) and entries[0].get("type") == "session_meta"


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return 0
        entries = read_jsonl(data["transcript_path"])
        msgs = codex_nudge(entries, data.get("turn_id")) if is_codex(entries) else nudge(entries)
    except Exception:
        return 0
    if msgs:
        print(json.dumps({"systemMessage": "OmniKit：" + " ".join(msgs)}))
    return 0


def selftest() -> int:
    def prompt(text="hi", origin="human"):
        return {"type": "user", "message": {"content": text}, "turnOrigin": origin}

    def reply(tokens, *blocks):
        return {"type": "assistant", "message": {"usage": {"input_tokens": 2, "cache_read_input_tokens": tokens - 2},
                                                 "content": list(blocks)}}

    def shell(cmd, ok=True, name="Bash"):
        return [reply(1, {"type": "tool_use", "id": cmd, "name": name, "input": {"command": cmd}}),
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": cmd, "is_error": not ok}]}}]

    def squeeze(trigger="auto"):
        """自動壓縮：邊界紀錄後面跟著一則摘要，摘要不是使用者送的。"""
        return [{"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": trigger}},
                {"type": "user", "isCompactSummary": True, "turnOrigin": "human", "message": {"content": "摘要"}}]

    assert nudge([]) == []
    assert nudge([prompt(), reply(90_000), prompt(), reply(900_000)]) == []  # 不看 token 數
    first = nudge([prompt(), reply(1), prompt(), *squeeze(), reply(1)])
    assert len(first) == 1 and "壓縮 1 次" in first[0]  # 第一次自動壓縮
    assert nudge([prompt(), *squeeze(), prompt(), reply(1)]) == []  # 上一回合壓縮的不算
    assert nudge([prompt(), *squeeze(), prompt(), *squeeze(), reply(1)]) == []  # 第 2 次不提醒
    assert len(nudge([prompt(), *squeeze(), *squeeze(), prompt(), *squeeze(), reply(1)])) == 1  # 第 3 次
    assert nudge([prompt(), prompt("/compact"), *squeeze("manual"), reply(1)]) == []  # 手動壓縮
    assert len(nudge([prompt(), *shell("git push origin main 2>&1 | Out-String"), reply(5)])) == 1
    assert len(nudge([prompt(), *shell("cd x && git -C repo push", name="PowerShell")])) == 1
    assert nudge([prompt(), *shell("git push origin main", ok=False)]) == []  # 推送失敗
    assert nudge([prompt(), *shell("git push --dry-run")]) == []
    assert nudge([prompt(), *shell("git commit -m '記得 git push'")]) == []
    assert nudge([*shell("git push"), prompt()]) == []  # 上一回合推送的不算
    assert nudge([prompt(), *shell("git push"), prompt(), *shell("git push origin main")]) == []  # 只提醒第一次
    assert len(nudge([prompt(), *shell("git push", ok=False), prompt(), *shell("git push")])) == 1
    assert len(nudge([{"type": "user", "message": {"content": "hi"}}, *shell("git push")])) == 1  # 舊紀錄沒有 turnOrigin
    # 子對話：第一則訊息由別的對話送出，之後使用者自己接著講也一樣不提醒
    assert nudge([prompt(origin="sdk"), *shell("git push"), *squeeze()]) == []
    assert nudge([prompt(origin="sdk"), reply(1), prompt(), *shell("git push"), *squeeze()]) == []

    # Codex rollout
    def ev(**payload):
        return {"type": "event_msg", "payload": payload}

    def turn(tid, *rest):
        return [ev(type="task_started", turn_id=tid), ev(type="item_completed", item={"type": "UserMessage"}), *rest]

    def tokens(n):
        return ev(type="token_count", info={"last_token_usage": {"input_tokens": n}})

    def compact(n):
        return {"type": "compacted", "payload": {"window_number": n}}

    def run(cmd, code=0):
        argv = cmd if isinstance(cmd, list) else ["C:\\Program Files\\PowerShell\\7\\pwsh.exe", "-Command", cmd]
        return ev(type="item_completed", item={"type": "CommandExecution", "command": argv, "exit_code": code})

    meta = {"type": "session_meta", "payload": {}}
    assert codex_nudge([meta]) == []
    assert codex_nudge([meta, *turn("a", tokens(90_000)), *turn("b", tokens(900_000))]) == []  # 不看 token 數
    first = codex_nudge([meta, *turn("a", tokens(90_000)), *turn("b", tokens(95_000), compact(1), tokens(20_000))])
    assert len(first) == 1 and "壓縮 1 次" in first[0]  # 第一次壓縮
    assert codex_nudge([meta, *turn("a", compact(1)), *turn("b", compact(2))]) == []  # 第 2 次不提醒
    assert len(codex_nudge([meta, *turn("a", compact(2)), *turn("b", compact(3))])) == 1  # 第 3 次
    assert len(codex_nudge([meta, *turn("a", compact(1)), *turn("b", compact(2), compact(3), compact(4))])) == 1
    assert len(codex_nudge([meta, *turn("b", compact(9))])) == 1  # 分頁後的 rollout：之前算 8 次
    assert codex_nudge([meta, *turn("b", compact(8))]) == []
    assert codex_nudge([meta, *turn("a"), ev(type="task_started", turn_id="b"), compact(1)]) == []  # 手動壓縮
    assert codex_nudge([meta, *turn("a", run("git push origin main"))]) == [PUSHED]
    assert codex_nudge([meta, *turn("a", run(["git", "-C", "repo", "push"]))]) == [PUSHED]
    assert codex_nudge([meta, *turn("a", run("git push origin main", code=1))]) == []  # 推送失敗
    assert codex_nudge([meta, *turn("a", run("git commit -m '記得 git push'"))]) == []
    assert codex_nudge([meta, *turn("a", run("git push")), *turn("b")]) == []  # 上一回合推送的不算
    assert codex_nudge([meta, *turn("a", run("git push")), *turn("b")], turn_id="a") == [PUSHED]
    assert codex_nudge([meta, *turn("a", run("git push")), *turn("b", run("git push"))]) == []  # 只提醒第一次
    legacy = [meta, ev(type="task_started", turn_id="a"), ev(type="user_message", message="hi"), tokens(120_000),
              ev(type="exec_command_end", command=["pwsh.exe", "-Command", "git push"], exit_code=0)]
    assert codex_nudge(legacy) == [PUSHED]  # 舊版事件寫法

    # read_jsonl 分辨格式；Codex 只留下用得到的行，最後一行寫到一半也不會壞
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "rollout.jsonl"
        lines = [meta, {"type": "response_item", "payload": {"type": "message"}}, *turn("a", compact(1))]
        path.write_text("\n".join(json.dumps(e) for e in lines) + '\n{"type":', encoding="utf-8")
        entries = read_jsonl(str(path))
        assert is_codex(entries) and len(entries) == 4 and len(codex_nudge(entries, "a")) == 1
        path.write_text(json.dumps(prompt()) + "\n", encoding="utf-8")
        assert not is_codex(read_jsonl(str(path)))
    print("session_nudge selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
