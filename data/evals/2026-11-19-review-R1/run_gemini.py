"""R1 審查槽位補跑：另一家模型（Gemini 4 Hydrogen xhigh）對 OmniKeep T1-T5 真實 commit 做唯讀審查。

與 data/evals/2026-11-19-review-R1/run.py 使用相同 5 個 commit 與拋棄式 detached worktree，
輸出格式相容，存至 <root>/out/T{1..5}-gemini-hydrogen-xhigh.json。
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CASES = {
    "T1": "02adee8",
    "T2": "1db0b2b",
    "T3": "336a69d",
    "T4": "6d56a5d",
    "T5": "5d8e523",
}
ARM = "gemini-hydrogen-xhigh"
MODEL = "gemini-4-hydrogen-xhigh"


def _writable(func, path, _exc):
    os.chmod(path, 0o666)
    func(path)


def sh(cmd, cwd, timeout=600):
    p = subprocess.Popen(
        cmd, cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        out, err = p.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def checkout(root: Path, case: str):
    sha = CASES[case]
    work = root / "work" / f"{case}-{ARM}"
    if work.exists():
        shutil.rmtree(work, onexc=_writable)
    work.parent.mkdir(parents=True, exist_ok=True)
    sh(["git", "clone", "--quiet", "--no-hardlinks", str(root / "omnikeep"), str(work)], root)
    sh(["git", "-C", str(work), "checkout", "--quiet", "--detach", sha], root)
    parent = sh(["git", "-C", str(work), "rev-parse", f"{sha}^"], root).stdout.strip()
    full = sh(["git", "-C", str(work), "rev-parse", sha], root).stdout.strip()
    return work, full, parent


def run_case(root: Path, case: str):
    out = root / "out"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{case}-{ARM}.json"
    if dst.exists():
        print(f"{case} {ARM} 已有結果，略過", flush=True)
        return
    work, sha, parent = checkout(root, case)
    prompt = (
        f"你是唯讀程式碼審查員。請審查目前 git repo 在 commit `{sha}`（相對於 `{parent}`）的完整改動。\n"
        f"要求：\n"
        f"1. 先執行 `git show {sha}` 查看完整 diff，必要時唯讀檢視相關檔案上下文。\n"
        f"2. 嚴禁修改、建立或刪除任何檔案，嚴禁執行會改變工作區的 git 指令。\n"
        f"3. 列出所有真實的程式錯誤、邏輯缺陷、安全風險、資源／逾時問題或邊界條件漏洞；"
        f"每條請附檔案路徑、行號、具體觸發情境、問題原因與建議修法，按嚴重度排序。\n"
        f"4. 不要泛泛而談程式碼風格，只報真正會出錯或造成缺陷的問題。"
    )
    cmd = [
        "agy", "-p", prompt,
        "--model", MODEL,
        "--output-format", "json",
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
        "--print-timeout", "480s",
    ]
    t0 = time.time()
    try:
        p = sh(cmd, work, timeout=540)
        rc, raw_out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, raw_out, err = "timeout", (e.stdout or "") if isinstance(e.stdout, str) else "", "timeout"
    secs = round(time.time() - t0)

    parsed = None
    for line in reversed(raw_out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    review_text = parsed.get("response", "") if isinstance(parsed, dict) else raw_out
    usage = parsed.get("usage") if isinstance(parsed, dict) else None
    changed = sh(["git", "-C", str(work), "status", "--porcelain"], root).stdout.splitlines()

    row = {
        "case": case,
        "arm": ARM,
        "model": MODEL,
        "sha": sha,
        "parent": parent,
        "cmd": cmd,
        "rc": rc,
        "secs": secs,
        "stdout": review_text,
        "stderr": err[-4000:],
        "usage": usage,
        "worktree_changed": changed,
    }
    dst.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{case} {ARM} rc={rc} {secs}s 改動={len(changed)} 輸出={len(review_text)} 字 usage={usage}", flush=True)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    cases = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CASES)
    for c in cases:
        run_case(root, c)
