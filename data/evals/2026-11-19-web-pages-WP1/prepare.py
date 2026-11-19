"""網頁槽位第 2 層（WP1，2026-11-19）：準備三組工作資料夾、印出各組的任務提示。

用法：python -I prepare.py <工作根目錄>
每組 <根>/<組>/：content/README.md（OmniKeep README）、.agents/skills/<skill>（不裝組沒有）、git init 加一個 baseline commit。
提示寫在 <根>/<組>/PROMPT.txt，由主控用 t3_thread_launch 派出去。
"""
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TASTE = Path.home() / ".claude" / "plugins" / "cache" / "taste-skill" / "taste-skill" / "2.5.1" / "skills" / "taste-skill"
HUASHU_REPO = "alchaincyf/huashu-design"
HUASHU_SHA = "e8d1148a80d5a281d4247cffe320add3df017928"
OMNIKEEP = "b40609/OmniKeep"
ARMS = {"taste-skill": 18801, "huashu-design": 18802, "none": 18803}

BRIEF = """任務：替 OmniKeep 做一頁產品介紹頁（官網首頁）。

{skill_rule}

## 產品與對象
- OmniKeep 是自架的連結收藏工具：在 Telegram 把連結丟給自己的機器人，它把網頁、影片、社群貼文讀完寫摘要，之後用搜尋或提問找得到。資料存在使用者自己的電腦。
- 事實只能來自 content/README.md（OmniKeep 的 README）。功能、安裝方式、限制都要對得上；不准編造功能、數據、使用者評價、合作夥伴或媒體 logo。
- 對象：台灣、會用 Telegram、看到值得留的連結常常收了就找不到的人。頁面用繁體中文（台灣用語）。
- 這頁要「第一眼有質感，像業界的高品質網頁，不是一般 AI 產生的樣子」。

## 必要內容
- 一句話講清楚它是什麼。
- 三步驟：丟連結、幫你讀完、找得到。
- 它能做什麼（照 README「它能做什麼」）。
- 資料在自己手上。
- 三分鐘開始用：Windows 與 macOS、Linux 的安裝指令照 README 原文。
- 連到 GitHub：https://github.com/b40609/OmniKeep

## 品牌
OmniKeep 沒有品牌規範、沒有 logo，你自己定。

## 不能問問題
這次沒有人會回答你。skill 要求先問使用者、或讓使用者從幾個方向裡挑時，照這份簡報自己決定，把你替使用者做的決定寫在 site/NOTES.md。要出好幾個方向時，挑一個做成完整版就好。不要停下來等回覆。

## 交付
- 全部放在 site/：靜態檔（index.html 加 CSS、JS、圖片），在 site/ 執行 `python -m http.server` 就能看，不要需要建置步驟的框架。
- 可以用 Google Fonts 這類 CDN 字型。圖片用自己做的（SVG、CSS、自己截的畫面）或授權允許使用的，來源寫在 site/CREDITS.md。
- 預覽：在 site/ 背景啟動 `python -m http.server {port}`，開 http://127.0.0.1:{port}/ 檢查 1440 寬與 375 寬：沒有 console 錯誤、沒有橫向捲動。檢查完把伺服器關掉。伺服器這類不會自己結束的程式一律背景跑。
- 不要 commit、不要 push、不要裝全域套件（npx 臨時執行可以）。不要改 site/ 以外的檔案（content/ 與 .agents/ 不要動）；skill 的腳本需要的套件可以在 skill 自己的資料夾裡 `npm install`，產生的 node_modules 不算改動。
- 最後回覆三到五行：設計方向、你替使用者做了哪些決定。
"""

RULES = {
    "taste-skill": "先完整讀 .agents/skills/taste-skill/SKILL.md，照它的方法做；它要求讀的參考檔、要跑的檢查也要做。這次只用這一個設計 skill，不要叫用其他設計類 skill（unslop、huashu-design、frontend-design 等），也不要用 Claude Code 全域裝的那份 taste-skill（以資料夾裡這份為準）。",
    "huashu-design": "先完整讀 .agents/skills/huashu-design/SKILL.md，照它的方法做；它要求讀的參考檔、要跑的腳本也要做（需要雲端金鑰的功能不要用）。這次只用這一個設計 skill，不要叫用其他設計類 skill（taste-skill、unslop、frontend-design 等）。",
    "none": "這次不要用任何設計類 skill（taste-skill、unslop、huashu-design、frontend-design 等都不要叫用），用你自己的判斷做。",
}


def sh(cmd, cwd, **kw):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        raise SystemExit(f"{cmd} 失敗：{r.stderr[-800:]}")
    return r.stdout


def gh_readme(repo):
    return base64.b64decode(json.loads(sh(["gh", "api", f"repos/{repo}/readme"], "."))["content"]).decode("utf-8")


def _writable(func, path, _exc):
    """Windows 上 git 的 pack 檔是唯讀的，先拿掉唯讀再刪。"""
    os.chmod(path, 0o666)
    func(path)


def huashu(dst):
    tmp = dst.parent / "_huashu_clone"
    if tmp.exists():
        shutil.rmtree(tmp, onexc=_writable)
    sh(["git", "-c", "core.longpaths=true", "clone", "--quiet", f"https://github.com/{HUASHU_REPO}.git", str(tmp)], ".")
    sh(["git", "-C", str(tmp), "checkout", "--quiet", HUASHU_SHA], ".")
    shutil.rmtree(tmp / ".git", onexc=_writable)
    shutil.move(str(tmp), str(dst))


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    readme = gh_readme(OMNIKEEP)
    for arm, port in ARMS.items():
        work = root / arm
        if work.exists():
            raise SystemExit(f"{work} 已經存在，換一個根目錄")
        (work / "content").mkdir(parents=True)
        (work / "site").mkdir()
        (work / "content" / "README.md").write_text(readme, encoding="utf-8", newline="\n")
        skills = work / ".agents" / "skills"
        if arm == "taste-skill":
            shutil.copytree(TASTE, skills / "taste-skill")
        elif arm == "huashu-design":
            skills.mkdir(parents=True)
            huashu(skills / "huashu-design")
        (work / ".gitignore").write_text("node_modules/\n", encoding="utf-8", newline="\n")
        (work / "PROMPT.txt").write_text(BRIEF.format(skill_rule=RULES[arm], port=port), encoding="utf-8", newline="\n")
        env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(root)}
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "baseline"]):
            sh(cmd, work, env=env)
        print(arm, work)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
