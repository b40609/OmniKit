"""前端設計槽位 F1 第二輪：OmniKit 看板（2026-11-13）。三組各一份 OmniKit 副本，只換 skill，T3 子對話（retis 的 Claude）執行。
依序跑，每組前後讀 retis 的 /usage。用法：python run2.py <model> [組,...]"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"<工作資料夾>")
BASE_TAR = ROOT / "kb-base" / "repo.tar"
SKILLS = ROOT / "skills"
OUT = ROOT / "kb-run"
ARMS = {
    "frontend-design": SKILLS / "anthropic-skills" / "skills" / "frontend-design",
    "taste-skill": SKILLS / "taste-skill-repo" / "skills" / "taste-skill",
    "unslop": SKILLS / "unslop-repo" / "skills" / "unslop",
}
PORTS = {"frontend-design": 8911, "taste-skill": 8912, "unslop": 8913}
T3 = str(Path.home() / ".t3" / "bin" / "t3.cmd")
PROVIDER = "claudeAgent_2"   # T3 裡 retis 的 Claude 帳號
RETIS_HOME = str(Path.home() / ".claude-retis")
ALLOWED = ("engine/site/style.css", "engine/site/app.js", "engine/scripts/build.py")

PROMPT = """你在 OmniKit repo 的副本裡。工作：重新設計 OmniKit 的線上看板，讓第一次來的人看了想用、容易找到需要的工具。
看板由 engine/scripts/build.py 的 page() 產生 HTML，樣式在 engine/site/style.css，搜尋與篩選在 engine/site/app.js。

規則：
- 先完整讀 .agents/skills/{skill}/SKILL.md，照它的方法做；它要求讀的參考檔也要讀。
- 內容不能少：所有區塊、槽位、工具卡、連結都要保留；搜尋與篩選要能用。
- 只改 engine/site/style.css、engine/site/app.js，以及 build.py 裡產生 HTML 的部分（page() 與它呼叫的函式）。不要動 engine/site/map.html、data/ 與其他檔案；不要裝新套件。
- 完成前執行 `uv run engine/scripts/build.py --site _site` 與 `uv run engine/scripts/build.py --check`，都必須成功。
- 預覽：建置後執行 `python -m http.server {port} --bind 127.0.0.1 --directory _site`，在 http://127.0.0.1:{port} 檢查（桌機與手機寬度），檢查完把它關掉。
- 不要 commit、不要 push。最後用三五行說明你改了什麼、設計方向是什麼。"""


def sh(cmd, cwd, timeout=1800, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          shell=isinstance(cmd, str), **kw)


def usage():
    p = sh(["claude", "-p", "/usage", "--output-format", "json"], ROOT / "neutral", timeout=120,
           env={**os.environ, "CLAUDE_CONFIG_DIR": RETIS_HOME})
    text = json.loads(p.stdout).get("result", "")
    out = {}
    for key, pat in (("session", r"Current session: (\d+)% used"), ("week", r"Current week \(all models\): (\d+)% used")):
        if m := re.search(pat, text):
            out[key] = int(m.group(1))
    return out


def prepare(arm):
    work = OUT / arm
    if work.exists():
        shutil.rmtree(work)
    app = work / "repo"
    app.mkdir(parents=True)
    sh(["tar", "-xf", str(BASE_TAR)], app)
    shutil.copytree(ARMS[arm], app / ".agents" / "skills" / arm)
    (app / ".gitignore").write_text("_site/\n__pycache__/\n.venv/\n", encoding="utf-8")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(work)}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "baseline"]):
        sh(cmd, app, env=env)
    return app, env


def run(arm, model):
    app, env = prepare(arm)
    before = usage()
    t0 = time.time()
    print(f"[{arm}] T3 retis {model} 開始", flush=True)
    sh([T3, "project", "add", str(app), "--title", f"OmniKit F1b 實測：{arm}"], app, timeout=120)
    p = subprocess.run([T3, "thread", "start", str(app), "-", "--title", f"OmniKit 第 2 層 F1b：{arm}", "--provider", PROVIDER,
                        "--model", model, "--wait", "--json"], cwd=app, input=PROMPT.format(skill=arm, port=PORTS[arm]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
    secs = round(time.time() - t0)
    time.sleep(5)
    after = usage()
    try:
        doc = json.loads(p.stdout)
        doc["response"] = doc.pop("reply", None)
    except ValueError:
        doc = {"status": "parse-error", "raw": p.stdout[-1500:], "stderr": p.stderr[-1500:]}
    sh(["git", "add", "-A"], app, env=env)
    changed = sh(["git", "diff", "--cached", "--name-only"], app, env=env).stdout.split()
    patch = sh(["git", "diff", "--cached", "--", ".", ":!.agents"], app, env=env).stdout
    (OUT / f"{arm}.patch").write_text(patch, encoding="utf-8")
    site = sh("uv run engine/scripts/build.py --site _site", app, timeout=600)
    check = sh("uv run engine/scripts/build.py --check", app, timeout=600)
    shutil.rmtree(OUT / "dist" / arm, ignore_errors=True)
    if site.returncode == 0:
        shutil.copytree(app / "_site", OUT / "dist" / arm)
    row = {"arm": arm, "model": model, "secs": secs, "status": doc.get("status"), "thread": doc.get("threadId"),
           "response": doc.get("response"), "quota_before": before, "quota_after": after, "changed": changed,
           "outside_allowed": [c for c in changed if c not in ALLOWED and not c.startswith(".agents/")],
           "site_build": site.returncode == 0, "check": check.returncode == 0,
           "build_tail": (site.stdout + site.stderr)[-600:] if site.returncode else ""}
    (OUT / f"{arm}.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: row[k] for k in ("arm", "secs", "status", "site_build", "check", "changed", "outside_allowed")},
                     ensure_ascii=False), flush=True)
    print(f"  retis 額度：session {before.get('session')}% → {after.get('session')}%，week {before.get('week')}% → {after.get('week')}%",
          flush=True)


if __name__ == "__main__":
    model = sys.argv[1]
    arms = sys.argv[2].split(",") if len(sys.argv) > 2 else list(ARMS)
    for a in arms:
        run(a, model)
