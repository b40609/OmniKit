"""審查槽位第 2 層（R1，2026-11-19）：三組（現任 Codex review、codex-plugin-cc adversarial-review、claudex-loop inspect）
各審 5 個 OmniKeep commit。每組每題一份拋棄式副本。

用法：python -I run.py <工作根目錄> [題,...] [組,...]
工作根目錄要先有：omnikeep/（OmniKeep 的 clone）、codex-plugin-cc/（db52e28）、claudex-loop/（53cddc4）。
輸出：<根>/out/<題>-<組>.json（指令、耗時、輸出全文、副本有沒有被改）。
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
ARMS = ("incumbent", "codex-plugin-cc", "claudex-loop")
TIMEOUT = 1800


def sh(cmd, cwd, timeout=TIMEOUT, env=None):
    """stdin 接空（codex 等輸入會一直掛著）；逾時把整棵程序樹結束掉，不留孤兒。"""
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace", env=env)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        out, err = p.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def _writable(func, path, _exc):
    os.chmod(path, 0o666)
    func(path)


def checkout(root, case, arm):
    sha = CASES[case]
    work = root / "work" / f"{case}-{arm}"
    if work.exists():
        shutil.rmtree(work, onexc=_writable)
    work.parent.mkdir(parents=True, exist_ok=True)
    sh(["git", "clone", "--quiet", "--no-hardlinks", str(root / "omnikeep"), str(work)], root)
    sh(["git", "-C", str(work), "checkout", "--quiet", "--detach", sha], root)
    parent = sh(["git", "-C", str(work), "rev-parse", f"{sha}^"], root).stdout.strip()
    full = sh(["git", "-C", str(work), "rev-parse", sha], root).stdout.strip()
    return work, full, parent


def command(root, arm, work, sha, parent, artifacts):
    if arm == "incumbent":
        return [shutil.which("codex") or "codex", "review", "--commit", sha], None
    if arm == "codex-plugin-cc":
        script = root / "codex-plugin-cc" / "plugins" / "codex" / "scripts" / "codex-companion.mjs"
        return ["node", str(script), "adversarial-review", "--wait", "--base", parent], None
    plan = artifacts / "plan.md"
    msg = sh(["git", "-C", str(work), "log", "-1", "--format=%B", sha], root).stdout
    plan.write_text("# 計畫（取自這個 commit 的說明）\n\n" + msg, encoding="utf-8")
    runner = root / "claudex-loop" / "skills" / "claudex-loop" / "scripts" / "runner.py"
    return [sys.executable, "-I", str(runner), "inspect", "--host", "claude", "--builder", "claude", "--repo", str(work),
            "--plan", str(plan), "--base", parent, "--artifacts", str(artifacts / "claudex")], None


def run(root, case, arm):
    out = root / "out"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{case}-{arm}.json"
    if dst.exists():
        print(f"{case} {arm} 已有結果，略過", flush=True)
        return
    work, sha, parent = checkout(root, case, arm)
    artifacts = root / "artifacts" / f"{case}-{arm}"
    if artifacts.exists():
        shutil.rmtree(artifacts, onexc=_writable)
    artifacts.mkdir(parents=True)
    cmd, _ = command(root, arm, work, sha, parent, artifacts)
    # ~/.codex/config.toml 的 openai_base_url 指向 codex-chatgpt-web 的本機橋接（2026-11-19 沒在跑），
    # 改用 <根>/codex-home：設定拿掉那一行、auth.json 是硬連結，其餘照 Ryan 的設定。
    env = {**os.environ, "CODEX_HOME": str(root / "codex-home"), "CLAUDE_PLUGIN_DATA": str(artifacts / "plugin-data"), "CLAUDE_PLUGIN_ROOT": str(root / "codex-plugin-cc" / "plugins" / "codex")}
    t0 = time.time()
    try:
        p = sh(cmd, work, env=env)
        rc, stdout, stderr = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, stdout, stderr = "timeout", (e.stdout or "") if isinstance(e.stdout, str) else "", "timeout"
    secs = round(time.time() - t0)
    changed = sh(["git", "-C", str(work), "status", "--porcelain"], root).stdout.splitlines()
    result_json = None
    if arm == "claudex-loop":
        found = sorted((artifacts / "claudex").rglob("result.json"))
        if found:
            result_json = json.loads(found[-1].read_text(encoding="utf-8"))
    row = {"case": case, "arm": arm, "sha": sha, "parent": parent, "cmd": [str(c) for c in cmd], "rc": rc, "secs": secs,
           "stdout": stdout, "stderr": stderr[-4000:], "result_json": result_json, "worktree_changed": changed}
    dst.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{case} {arm} rc={rc} {secs}s 改動={len(changed)} 輸出={len(stdout)} 字", flush=True)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    cases = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else list(CASES)
    arms = sys.argv[3].split(",") if len(sys.argv) > 3 else list(ARMS)
    for c in cases:
        for a in arms:
            run(root, c, a)
