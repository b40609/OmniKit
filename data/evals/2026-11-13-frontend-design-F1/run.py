# 2026-11-13 F1 第二次實測用的執行腳本（原本放在 repo 外）。<OmniKit> 是 OmniKit repo 的路徑；ROOT 是 repo 外的工作資料夾。
"""前端設計槽位 F1 實測（2026-11-13）：三組各一份 CatOS 前端副本，只換 skill，T3 子對話（retis 的 Claude）執行。
依序跑（不平行），每次前後讀 retis 的 /usage，才分得出每組扣了多少額度。
用法：python run.py <model> [組,...]"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\omnikit-eval")
BASE_TAR = ROOT / "fe-base" / "src.tar"
SKILLS = ROOT / "skills"
OUT = ROOT / "fe-run"
DIRECTION = Path(r"<OmniKit>\data\evals\2026-11-04-frontend-design-F1\design-direction.md")
MOCK = Path(r"<OmniKit>\data\evals\2026-11-04-frontend-design-F1\mock-server.mjs")
ARMS = {
    "frontend-design": SKILLS / "anthropic-skills" / "skills" / "frontend-design",
    "taste-skill": SKILLS / "taste-skill-repo" / "skills" / "taste-skill",
    "unslop": SKILLS / "unslop-repo" / "skills" / "unslop",
}
PORTS = {"frontend-design": 8901, "taste-skill": 8902, "unslop": 8903}

PROMPT = """你在 CatOS 的前端專案（React 19、Vite、Tailwind 4）。工作：依 docs/design-direction.md 的方向，打磨儀表板首頁（網址 /）的視覺、層級與可讀性。

規則：
- 先完整讀 .agents/skills/{skill}/SKILL.md，照它的方法做；它要求讀的參考檔也要讀。
- 不改變既定方向：黑金配色、緊湊密度、圖示導航、面板工作台。功能、導航項目、面板都要保留。
- 只改 src/ 底下的檔案；skill 需要的設計說明文件可以新增在 docs/。不要改 package.json、不要裝新套件。
- 完成前執行 `npm run typecheck`，必須通過。
- 預覽：執行 `node preview.mjs`，會建置並在 http://127.0.0.1:{port} 開起來（後端是固定的假資料）。可以用瀏覽器或截圖檢查自己的結果，檢查完把它關掉。
- 不要 commit、不要 push。最後用三五行說明你改了什麼。"""

PREVIEW = r"""// 建置並用固定的假資料預覽：node preview.mjs
import { spawnSync } from 'node:child_process';
import { createReadStream, existsSync, statSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const r = spawnSync(process.execPath, ['node_modules/vite/bin/vite.js', 'build', '--outDir', '.preview-dist', '--emptyOutDir', '--logLevel', 'warn'], { stdio: 'inherit' });
if (r.status !== 0) process.exit(r.status);
const { handleApi } = await import(pathToFileURL(%MOCK%).href);
const dist = path.resolve('.preview-dist');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2' };
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname.startsWith('/api/')) { if (!handleApi(req, res)) { res.writeHead(404); res.end(); } return; }
  let file = path.join(dist, decodeURIComponent(url.pathname));
  if (!existsSync(file) || statSync(file).isDirectory()) file = path.join(dist, 'index.html');
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  createReadStream(file).pipe(res);
}).listen(%PORT%, '127.0.0.1', () => console.log('preview on http://127.0.0.1:%PORT%'));
"""


def sh(cmd, cwd, timeout=1800, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          shell=isinstance(cmd, str), **kw)


T3 = str(Path.home() / ".t3" / "bin" / "t3.cmd")
PROVIDER = "claudeAgent_2"   # T3 裡 retis 的 Claude 帳號
RETIS_HOME = str(Path.home() / ".claude-retis")


def usage():
    """retis 帳號的用量：claude /usage 不花 token。回傳 {'session': %, 'week': %}。"""
    import os
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
    (work / "src").mkdir(parents=True)
    sh(["tar", "-xf", str(BASE_TAR)], work / "src")
    app = work / "src" / "frontend" / "cat-os-vite"
    print(f"[{arm}] npm ci", flush=True)
    r = sh("npm ci --no-audit --no-fund", app, timeout=1800)
    if r.returncode:
        raise SystemExit(f"npm ci 失敗：{r.stderr[-800:]}")
    shutil.copytree(ARMS[arm], app / ".agents" / "skills" / arm)
    (app / "docs").mkdir(exist_ok=True)
    shutil.copy(DIRECTION, app / "docs" / "design-direction.md")
    (app / "preview.mjs").write_text(PREVIEW.replace("%MOCK%", json.dumps(str(MOCK))).replace("%PORT%", str(PORTS[arm])), encoding="utf-8")
    (app / ".gitignore").write_text("node_modules/\n.preview-dist/\ndist/\n", encoding="utf-8")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.name=eval", "-c", "user.email=eval@local",
                                                            "commit", "-qm", "baseline"]):
        sh(cmd, app, env={**__import__("os").environ, "GIT_CEILING_DIRECTORIES": str(app.parent)})
    return app


def run(arm, model):
    app = prepare(arm)
    before = usage()
    t0 = time.time()
    print(f"[{arm}] T3 retis {model} 開始", flush=True)
    sh([T3, "project", "add", str(app), "--title", f"OmniKit F1 實測：{arm}"], app, timeout=120)
    p = subprocess.run([T3, "thread", "start", str(app), "-", "--title", f"OmniKit 第 2 層 F1：{arm}", "--provider", PROVIDER,
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
    env = {**__import__("os").environ, "GIT_CEILING_DIRECTORIES": str(app.parent)}
    sh(["git", "add", "-A"], app, env=env)
    diff = sh(["git", "diff", "--cached", "--stat"], app, env=env).stdout
    patch = sh(["git", "diff", "--cached", "--", ".", ":!.agents"], app, env=env).stdout
    (OUT / f"{arm}.patch").write_text(patch, encoding="utf-8")
    changed = [l.split()[0] for l in sh(["git", "diff", "--cached", "--name-only"], app, env=env).stdout.splitlines()]
    tc = sh("npm run typecheck", app, timeout=600)
    build = sh([str(Path(sys.executable).parent / "node.exe") if False else "node", "node_modules/vite/bin/vite.js", "build",
                "--outDir", str(OUT / "dist" / arm), "--emptyOutDir", "--logLevel", "warn"], app, timeout=600)
    row = {"arm": arm, "model": model, "secs": secs, "status": doc.get("status"), "thread": doc.get("threadId"),
           "usage": doc.get("usage"), "num_turns": doc.get("num_turns"), "response": doc.get("response"), "quota_before": before, "quota_after": after,
           "changed": changed, "outside_src": [c for c in changed if not (c.startswith("src/") or c.startswith("docs/"))],
           "diffstat": diff.strip().splitlines()[-1:] if diff.strip() else [], "typecheck": tc.returncode == 0,
           "typecheck_tail": (tc.stdout + tc.stderr)[-800:] if tc.returncode else "", "build": build.returncode == 0}
    (OUT / f"{arm}.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: row[k] for k in ("arm", "secs", "status", "usage", "typecheck", "build", "diffstat", "outside_src")},
                     ensure_ascii=False), flush=True)
    print(f"  retis 額度：session {before.get('session')}% → {after.get('session')}%，week {before.get('week')}% → {after.get('week')}%", flush=True)


if __name__ == "__main__":
    model = sys.argv[1]
    arms = sys.argv[2].split(",") if len(sys.argv) > 2 else list(ARMS)
    for a in arms:
        run(a, model)
