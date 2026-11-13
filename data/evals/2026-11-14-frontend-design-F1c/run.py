"""前端設計槽位第三輪：LinePort 控制台（2026-11-14）。三組各一份 yomi-probe 副本，只換 skill，T3 子對話（retis 的 Claude）執行。
用法：python run3.py <model> [組,...]"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"<工作資料夾>")
LINEPORT = Path(r"<LinePort>")
BASE_COMMIT = "21729fd"
SKILLS = ROOT / "skills"
OUT = ROOT / "lp-run"
ARMS = {
    "frontend-design": SKILLS / "anthropic-skills" / "skills" / "frontend-design",
    "taste-skill": SKILLS / "taste-skill-repo" / "skills" / "taste-skill",
    "unslop": SKILLS / "unslop-repo" / "skills" / "unslop",
}
PORTS = {"frontend-design": 18771, "taste-skill": 18772, "unslop": 18773}
T3 = str(Path.home() / ".t3" / "bin" / "t3.cmd")
PROVIDER = "claudeAgent_2"
RETIS_HOME = str(Path.home() / ".claude-retis")

PROMPT = """你在 LinePort 的副本裡（LINE 訊息轉發與監控工具）。工作：重新設計它的控制台介面，讓使用者看了想用、長期每天用也順手。
介面整個在 yomi-probe/index.html 一個檔裡（HTML、CSS、JS 都在裡面），由 yomi-probe/server.mjs 服務。

規則：
- 先完整讀 .agents/skills/{skill}/SKILL.md，照它的方法做；它要求讀的參考檔也要讀。
- 功能不能少：所有畫面、按鈕、表單、轉發規則的編輯都要保留，而且要能用；JS 呼叫的 API 路徑與資料格式不能改。
- 只改 yomi-probe/index.html。不要改其他檔案，不要裝新套件。
- 完成前在 yomi-probe 執行 `npm test`，結果不能比改之前差（改之前先跑一次記下來）。
- 預覽：在 yomi-probe 執行 `node ui-mock.mjs`（先設環境變數 LINEPORT_MOCK_PORT={port}），開 http://127.0.0.1:{port}/ 檢查（桌機與手機寬度）。這是示範模式，資料是假的，不會連 LINE。檢查完輸入 stop 或結束它。
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


def base_tar():
    tar = OUT / "base.tar"
    if not tar.exists():
        r = sh(["git", "-C", str(LINEPORT), "archive", "--format=tar", "-o", str(tar), BASE_COMMIT, "yomi-probe"], OUT)
        if r.returncode:
            raise SystemExit(r.stderr)
    return tar


def patch_mock(app):
    """實測用：示範頁的 port 與自動關閉時間改成環境變數（各組都一樣）。"""
    f = app / "yomi-probe" / "ui-mock.mjs"
    s = f.read_text(encoding="utf-8")
    s = s.replace("port: 18767 }", "port: MOCK_PORT }").replace("stagedListen(server, lineDevice().id, 18767)",
                                                                 "stagedListen(server, lineDevice().id, MOCK_PORT)")
    s = s.replace("http://127.0.0.1:18767/", "http://127.0.0.1:${MOCK_PORT}/").replace("'LinePort mock UI: http", "`LinePort mock UI: http")
    s = s.replace("${MOCK_PORT}/\\n')", "${MOCK_PORT}/\\n`)")
    s = s.replace("10 * 60 * 1000", "Number(process.env.LINEPORT_MOCK_MINUTES || 10) * 60 * 1000")
    s = s.replace("const ipadQr =", "const MOCK_PORT = Number(process.env.LINEPORT_MOCK_PORT || 18767);\nconst ipadQr =", 1)
    f.write_text(s, encoding="utf-8")


def prepare(arm):
    work = OUT / arm
    if work.exists():
        shutil.rmtree(work)
    app = work / "repo"
    app.mkdir(parents=True)
    sh(["tar", "-xf", str(base_tar())], app)
    patch_mock(app)
    r = sh("npm ci --no-audit --no-fund", app / "yomi-probe", timeout=1800)
    if r.returncode:
        raise SystemExit(f"npm ci 失敗：{r.stderr[-800:]}")
    shutil.copytree(ARMS[arm], app / ".agents" / "skills" / arm)
    (app / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(work)}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "baseline"]):
        sh(cmd, app, env=env)
    return app, env


def tests(app):
    r = sh("npm test", app / "yomi-probe", timeout=900)
    text = r.stdout + r.stderr
    nums = {k: int(v) for k, v in re.findall(r"^(?:#|ℹ) (pass|fail|tests) (\d+)", text, re.M)}
    return {"exit": r.returncode, **nums}


def run(arm, model):
    app, env = prepare(arm)
    baseline = tests(app)
    before = usage()
    t0 = time.time()
    print(f"[{arm}] 原版測試 {baseline}；T3 retis {model} 開始", flush=True)
    sh([T3, "project", "add", str(app), "--title", f"OmniKit 第三輪實測：{arm}"], app, timeout=120)
    p = subprocess.run([T3, "thread", "start", str(app), "-", "--title", f"OmniKit 第 2 層 LinePort：{arm}", "--provider", PROVIDER,
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
    after_tests = tests(app)
    row = {"arm": arm, "model": model, "secs": secs, "status": doc.get("status"), "thread": doc.get("threadId"),
           "response": doc.get("response"), "quota_before": before, "quota_after": after, "changed": changed,
           "outside_allowed": [c for c in changed if c != "yomi-probe/index.html" and not c.startswith(".agents/")],
           "tests_before": baseline, "tests_after": after_tests}
    (OUT / f"{arm}.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: row[k] for k in ("arm", "secs", "status", "changed", "outside_allowed", "tests_before", "tests_after")},
                     ensure_ascii=False), flush=True)
    print(f"  retis 額度：session {before.get('session')}% → {after.get('session')}%，week {before.get('week')}% → {after.get('week')}%",
          flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    model = sys.argv[1]
    arms = sys.argv[2].split(",") if len(sys.argv) > 2 else list(ARMS)
    if arms == ["--prepare-only"]:
        app, _ = prepare("frontend-design")
        print(tests(app))
        sys.exit(0)
    for a in arms:
        run(a, model)
