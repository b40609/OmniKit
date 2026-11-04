# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 的 Stop hook：該開新對話時提醒使用者。只提醒，不做任何動作。

兩種訊號（換主題只能靠模型判斷，不在這裡）：
1. 上下文長度：這一回合跨過 100k、200k、300k… tokens 時各提醒一次。
2. 任務告一段落：這一回合成功跑了 git push。

從 stdin 讀 hook 輸入，再讀 transcript_path 的 JSONL；有話要說就印 {"systemMessage": ...}。
任何錯誤都安靜結束（exit 0），提醒壞掉不能干擾對話。

註冊：install.ps1 經 claude_allow.py 寫進 ~/.claude/settings.json 的 hooks.Stop。
自我測試：uv run engine/scripts/session_nudge.py --selftest
"""
import json
import re
import sys

STEP = 100_000
SHELLS = {"Bash", "PowerShell"}
# 只認指令開頭或 ; & | 之後的 git push，commit 訊息裡提到 git push 不算
PUSH = re.compile(r"(?:^|[;&|]\s*)git(?:\s+-C\s+\S+)*\s+push\b(?!.*--dry-run)", re.M)


def is_prompt(e: dict) -> bool:
    """使用者自己送出的訊息；tool_result 與系統插入的不算。"""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain"):
        return False
    content = (e.get("message") or {}).get("content")
    return isinstance(content, str) or any(b.get("type") == "text" for b in content or [])


def context_tokens(e: dict) -> int:
    u = (e.get("message") or {}).get("usage") or {}
    return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)


def nudge(entries: list[dict]) -> list[str]:
    start = max((i for i, e in enumerate(entries) if is_prompt(e)), default=0)
    sized = [(i, t) for i, e in enumerate(entries)
             if e.get("type") == "assistant" and not e.get("isSidechain") and (t := context_tokens(e))]
    before = [t for i, t in sized if i < start]
    after = [t for i, t in sized if i > start]
    msgs = []
    if after:
        prev, cur = (before[-1] if before else 0), after[-1]
        if cur // STEP > prev // STEP:
            msgs.append(f"上下文約 {cur // 1000}k tokens。下一件事若跟目前任務無關，建議開新對話；要接著做就請 Claude 交接。")

    blocks = [b for e in entries[start:]
              if isinstance(c := (e.get("message") or {}).get("content"), list) for b in c]
    pushes = {b.get("id") for b in blocks if b.get("type") == "tool_use" and b.get("name") in SHELLS
              and PUSH.search(str((b.get("input") or {}).get("command", "")))}
    if any(b.get("type") == "tool_result" and b.get("tool_use_id") in pushes and not b.get("is_error") for b in blocks):
        msgs.append("這一回合已推送到遠端。這件事若告一段落，下一件事建議開新對話。")
    return msgs


def read_jsonl(path: str) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except ValueError:  # 寫到一半的最後一行
                pass
    return entries


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return 0
        msgs = nudge(read_jsonl(data["transcript_path"]))
    except Exception:
        return 0
    if msgs:
        print(json.dumps({"systemMessage": "OmniKit：" + " ".join(msgs)}))
    return 0


def selftest() -> int:
    def prompt(text="hi"):
        return {"type": "user", "message": {"content": text}}

    def reply(tokens, *blocks):
        return {"type": "assistant", "message": {"usage": {"input_tokens": 2, "cache_read_input_tokens": tokens - 2},
                                                 "content": list(blocks)}}

    def shell(cmd, ok=True, name="Bash"):
        return [reply(1, {"type": "tool_use", "id": cmd, "name": name, "input": {"command": cmd}}),
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": cmd, "is_error": not ok}]}}]

    assert nudge([]) == []
    assert len(nudge([prompt(), reply(90_000), prompt(), reply(120_000)])) == 1  # 跨過 100k
    assert nudge([prompt(), reply(120_000), prompt(), reply(150_000)]) == []  # 已提醒過
    assert len(nudge([prompt(), reply(190_000), prompt(), reply(210_000)])) == 1  # 跨過 200k
    assert nudge([prompt(), reply(180_000), prompt("/compact"), reply(30_000)]) == []  # 壓縮後變短
    assert len(nudge([prompt(), *shell("git push origin main 2>&1 | Out-String"), reply(5)])) == 1
    assert len(nudge([prompt(), *shell("cd x && git -C repo push", name="PowerShell")])) == 1
    assert nudge([prompt(), *shell("git push origin main", ok=False)]) == []  # 推送失敗
    assert nudge([prompt(), *shell("git push --dry-run")]) == []
    assert nudge([prompt(), *shell("git commit -m '記得 git push'")]) == []
    assert nudge([*shell("git push"), prompt()]) == []  # 上一回合推送的不算
    print("session_nudge selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
