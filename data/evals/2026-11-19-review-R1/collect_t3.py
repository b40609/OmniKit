"""R1：把 T3 對話（antigravity_ryan 的 Gemini 4 Hydrogen xhigh）的審查全文收成 run.py 相容的 JSON。

2026-11-21 起改走 T3 看得到的對話：預設 `agy` CLI 的登入換成了只有 6 個模型的帳號（沒有 Hydrogen），
GEMINI_HOME 也指不到 Ryan 的帳號；T3 的 antigravity_ryan 實例才有 Hydrogen。
用法：python collect_t3.py <根> <題>=<threadId> ...
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ARM = "gemini-hydrogen-xhigh"


def main():
    root = Path(sys.argv[1])
    out = root / "out"
    out.mkdir(parents=True, exist_ok=True)
    for pair in sys.argv[2:]:
        case, tid = pair.split("=", 1)
        raw = subprocess.run(["t3.cmd", "thread", "show", tid, "--messages", "1", "--json"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        d = json.loads(raw)
        th, msgs = d["thread"], d.get("messages") or []
        last = msgs[-1] if msgs else {}
        text = last.get("text", "")
        wt = th.get("worktreePath")
        changed = subprocess.run(["git", "-C", wt, "status", "--porcelain"], capture_output=True, text=True,
                                 encoding="utf-8").stdout.splitlines() if wt else None
        sha = subprocess.run(["git", "-C", wt, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        runs = d.get("recentRuns") or []
        secs = None
        if runs and runs[0].get("startedAt") and runs[0].get("completedAt"):
            p = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
            secs = round((p(runs[0]["completedAt"]) - p(runs[0]["startedAt"])).total_seconds())
        ok = th.get("status") == "completed" and bool(text.strip())
        row = {"case": case, "arm": ARM, "model": "gemini-4-hydrogen thought_level=xhigh",
               "instance": th.get("providerInstanceId"), "thread": tid, "sha": sha,
               "rc": 0 if ok else th.get("status"), "secs": secs, "stdout": text,
               "worktree_changed": changed, "channel": "t3_thread_launch（visible）"}
        dst = out / f"{case}-{ARM}.json"
        dst.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
        print(case, th.get("status"), f"{secs}s", f"{len(text)} 字", "改動", changed, "HEAD", sha[:7])


if __name__ == "__main__":
    main()
