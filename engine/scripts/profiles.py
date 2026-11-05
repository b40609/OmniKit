# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit profile：這台電腦套用哪一份個人規則，並接到 Claude Code、Codex 與 Antigravity。

agent 讀到的規則是兩層接在一起：
- data/rules/baseline.md：安全底線，所有人都套用
- data/profiles/<名稱>/AGENTS.md：個人規則（語言、語氣、授權程度）
同一個 profile 資料夾裡的 scenarios.yaml 是評估工具用的真實情境，由 validate.py 讀。

選了哪個 profile 記在 %LOCALAPPDATA%\\omnikit\\profile.json。沒選過就用 default（授權偏保守），
而且每次都會提醒，直到用 --set 選定。

接上的方式（只接 agents.py 記錄裡的 agent，記在 %LOCALAPPDATA%\\omnikit\\agents.json）：
- Claude Code：~/.claude/CLAUDE.md 開頭的受管區塊 import 底線與 profile 兩份，改完開新 session 就生效。
- Codex：不支援 import，~/.codex/AGENTS.md 開頭的受管區塊放兩份接在一起的內容；原本的規則留在區塊外，
  照常生效。舊版整份換掉的（開頭是產生標記），同步時換成只有區塊，規則內容一樣。
- Antigravity：~/.gemini/GEMINI.md 開頭的受管區塊，內容跟 Codex 一樣。
Codex 與 Antigravity 的檔案常跟其他工具共用（硬連結），所以原地改寫，不換掉檔案。
第一次接上時（install.ps1 透過 agents.py connect），原本的 Codex 與 Antigravity 規則先備份成
<檔名>.pre-omnikit；之後的同步（git hook、--set）只改受管區塊，區塊被拿掉的不加回去。

用法：
  uv run engine/scripts/profiles.py                 用目前的 profile 重新接上
  uv run engine/scripts/profiles.py --set <名稱>    換 profile 並接上（skills 也跟著同步）
  uv run engine/scripts/profiles.py --show          只印出目前的 profile 名稱
  uv run engine/scripts/profiles.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA", HOME))
STATE = LOCAL / "omnikit"
RULES = {
    "claude-code": HOME / ".claude" / "CLAUDE.md",
    "codex": HOME / ".codex" / "AGENTS.md",
    "antigravity": HOME / ".gemini" / "GEMINI.md",
}
NAMES = {"claude-code": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}
# 舊版靠 skillshare 複製 Codex 的規則；還沒重跑 install.ps1 的電腦，用它判斷 Codex 有沒有接上
SKILLSHARE_CONFIG = Path(os.environ.get("APPDATA", HOME)) / "skillshare" / "config.yaml"
DEFAULT = "default"
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BEGIN, END = "<!-- omnikit:rules:begin -->", "<!-- omnikit:rules:end -->"
BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
HEADER = "<!-- 由 OmniKit 產生，不要手改："
CODEX_EXTRA = re.compile(r"(?m)^\s*- name: rules-codex\s*$")
# 訪談答案（answers.json）裡某題答 false 就不裝的 OmniKit skill：skill → （答案欄位, 說明）
OPTIONAL_SKILLS = {"omnikit-eval": ("evaluate_tools", "不評估新工具")}


def text(path):
    return path.read_bytes().decode("utf-8-sig")


def write(path, content):
    """內容沒變就不寫，回傳有沒有改。用 bytes 寫，Windows 上不會把 LF 換成 CRLF。"""
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def write_in_place(path, content):
    """原地改寫，不換掉檔案：硬連結到同一個檔案的其他名字會一起更新，不會斷開。content 是 bytes 就原樣寫。"""
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True
    if path.read_bytes() == data:
        return False
    with open(path, "r+b") as f:
        f.write(data)
        f.truncate()
    return True


def backup(path):
    """備份成 <檔名>.pre-omnikit；已經有同名備份就加上時間。回傳備份檔。"""
    target = path.with_name(path.name + ".pre-omnikit")
    if target.exists():
        target = path.with_name(f"{path.name}.pre-omnikit-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copyfile(path, target)
    return target


def available(data):
    root = data / "profiles"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "AGENTS.md").is_file())


def chosen(state):
    """這台電腦用 --set 選過的 profile；沒選過或檔案壞了回 None。"""
    try:
        name = json.loads(text(state / "profile.json")).get("profile")
    except (OSError, ValueError, AttributeError):
        return None
    return name if isinstance(name, str) and NAME.match(name) else None


def resolve(data, state, wanted=None):
    """回傳（profile, 是否因為沒選過而用預設）。指定或選過的 profile 不存在就失敗，不悄悄換成別的。"""
    if wanted is not None and not NAME.match(wanted):
        raise SystemExit(f"profile 名稱只能用小寫英數與 -：{wanted}")
    name = wanted or chosen(state)
    fallback = name is None
    name = name or DEFAULT
    if name not in available(data):
        raise SystemExit(
            f"找不到 profile「{name}」（data/profiles/{name}/AGENTS.md），可選：{'、'.join(available(data)) or '無'}"
        )
    return name, fallback


def rules_files(data, name):
    return data / "rules" / "baseline.md", data / "profiles" / name / "AGENTS.md"


def skipped_skills(data, name):
    """這個 profile 不裝的 OmniKit skill：{skill: 說明}。只看訪談產生的 answers.json；
    手寫的 profile（沒有 answers.json）或檔案讀不懂時全部都裝，跟以前一樣。"""
    try:
        answers = json.loads(text(data / "profiles" / name / "answers.json"))
    except (OSError, ValueError):
        return {}
    if not isinstance(answers, dict):
        return {}
    return {skill: why for skill, (key, why) in OPTIONAL_SKILLS.items() if answers.get(key) is False}


def compose(data, name):
    """給 Codex 與 Antigravity 的規則：底線在前，profile 在後；第一行是產生標記。"""
    parts = [text(p).replace("\r\n", "\n").strip() for p in rules_files(data, name)]
    header = f"{HEADER}data/rules/baseline.md + data/profiles/{name}/AGENTS.md -->"
    return "\n\n".join([header, *parts]) + "\n"


def is_ours(content):
    return content.lstrip().startswith(HEADER)


def connected(state, paths=None, skillshare_config=SKILLSHARE_CONFIG):
    """接上了哪些 agent：看 agents.py 的記錄；舊版安裝沒有記錄，就從現有的檔案推斷。"""
    paths = paths or RULES
    try:
        agents = json.loads(text(state / "agents.json")).get("agents")
        # 空的清單：還沒接上就先記了別的（例如 agents.py resolve），一樣從現有的檔案推斷
        if isinstance(agents, list) and agents:
            return [a for a in agents if a in RULES]
    except (OSError, ValueError, AttributeError):
        pass
    agents = ["claude-code"]
    codex = paths["codex"]
    legacy = skillshare_config.exists() and CODEX_EXTRA.search(text(skillshare_config))
    if legacy or (codex.exists() and is_ours(text(codex))):
        agents.append("codex")
    return agents


def claude_block(data, name):
    """skillshare 0.28.2 的 import 模式在 Windows 寫出反斜線路徑，Claude Code 不會載入；所以自己維護，路徑用正斜線。"""
    imports = "\n".join("@" + p.resolve().as_posix() for p in rules_files(data, name))
    return f"{BEGIN}\n{imports}\n{END}"


def with_block(old, block):
    """換掉受管區塊；沒有就加在開頭。區塊以外的內容與換行都不動。"""
    return BLOCK.sub(lambda _: block, old, count=1) if BLOCK.search(old) else block + "\n" + old


def connect_claude(claude_md, block):
    old = text(claude_md) if claude_md.exists() else ""
    return write(claude_md, with_block(old, block))


def content_block(content):
    return f"{BEGIN}\n{content.rstrip()}\n{END}"


def connect_block(path, content, take_over):
    """Codex 與 Antigravity：受管區塊放在開頭，區塊以外的內容不動，原地改寫（硬連結不會斷）。
    回傳（狀態, 備份檔）。狀態：updated、unchanged、skipped（同步時區塊不見了，是使用者拿掉的，不加回去）。"""
    old = text(path) if path.exists() else ""
    if not BLOCK.search(old) and old.strip() and not take_over:
        return "skipped", None
    new = with_block(old, content_block(content))
    if new == old:
        return "unchanged", None
    saved = backup(path) if take_over and old.strip() and not BLOCK.search(old) else None
    write_in_place(path, new)
    return "updated", saved


def connect_codex(path, content, take_over, legacy=False):
    """Codex 也用受管區塊，原本的規則留在區塊外照常生效（以前整份換掉，原本的只剩備份）。
    舊版整份都是 OmniKit 的內容（開頭是產生標記，或舊版 skillshare 複製的）：換成只有區塊，
    安裝前的備份（.pre-omnikit）不動。"""
    old = text(path) if path.exists() else ""
    if not BLOCK.search(old) and (is_ours(old) or (legacy and old.strip())):
        write_in_place(path, content_block(content) + "\n")
        return "updated", None
    return connect_block(path, content, take_over)


def disconnect_block(path):
    """原地拿掉受管區塊，回傳訊息。只剩區塊時：有安裝前的備份就還原，沒有（OmniKit 建的）就刪掉；
    還有別的內容時：跟備份一樣，多餘的備份也刪掉。"""
    if not path.exists() or not BLOCK.search(text(path)):
        return []
    rest = BLOCK.sub("", text(path), count=1)
    rest = rest[1:] if rest.startswith("\n") else rest
    saved = path.with_name(path.name + ".pre-omnikit")
    if not rest.strip():
        if saved.exists():
            write_in_place(path, saved.read_bytes())
            saved.unlink()
            return [f"已拿掉 {path} 的 OmniKit 區塊，還原安裝前的內容"]
        path.unlink()
        return [f"已刪除只剩 OmniKit 區塊的 {path}"]
    write_in_place(path, rest)
    lines = [f"已拿掉 {path} 的 OmniKit 區塊"]
    if saved.exists():
        if saved.read_bytes() == rest.encode("utf-8"):
            saved.unlink()
        else:
            lines.append(f"  安裝前的備份還在：{saved}，需要的話自己合併回去")
    return lines


def apply(data, state, paths=None, wanted=None, agents=None, take_over=False, skillshare_config=SKILLSHARE_CONFIG):
    """接上 profile，回傳要印給使用者看的訊息。take_over：第一次接上（install），可以接手並備份原本的規則。"""
    paths = paths or RULES
    name, fallback = resolve(data, state, wanted)
    if wanted:
        write(state / "profile.json", json.dumps({"profile": name}, ensure_ascii=False) + "\n")
    agents = agents if agents is not None else connected(state, paths, skillshare_config)
    content = compose(data, name)
    # 給 uninstall.ps1 比對 ~/.codex/AGENTS.md 是不是 OmniKit 的副本
    write(state / "rules" / "AGENTS.md", content)
    done, notes = [], []
    if "claude-code" in agents:
        connect_claude(paths["claude-code"], claude_block(data, name))
        done.append(NAMES["claude-code"])
    if "codex" in agents:
        legacy = skillshare_config.exists() and CODEX_EXTRA.search(text(skillshare_config)) is not None
        status, saved = connect_codex(paths["codex"], content, take_over, legacy)
        done.append(NAMES["codex"]) if status != "skipped" else notes.append(
            f"{paths['codex']} 的 OmniKit 區塊被拿掉了，沒有加回去；要接上請重跑 install.ps1")
        if saved:
            notes.append(f"已備份原本的 Codex 規則：{saved}（原本的規則留在區塊外，照常生效）")
    if "antigravity" in agents:
        status, saved = connect_block(paths["antigravity"], content, take_over)
        done.append(NAMES["antigravity"]) if status != "skipped" else notes.append(
            f"{paths['antigravity']} 的 OmniKit 區塊被拿掉了，沒有加回去；要接上請重跑 install.ps1")
        if saved:
            notes.append(f"已備份原本的 Antigravity 規則：{saved}")
    lines = [f"已套用 profile：{name}（{'、'.join(done) or '沒有 agent'}，開新的 session 才生效）", *notes]
    if fallback:
        lines.append(fallback_notice(data))
    return lines


def sync_skills(run=subprocess.run):
    """換 profile 後重新同步 skills：不同 profile 裝的可能不同（例如不評估工具就不裝 omnikit-eval）。
    agents.py 要用 pyyaml，這支沒有相依套件，所以交給 uv 另外跑。"""
    uv = shutil.which("uv") or str(LOCAL / "Programs" / "uv" / "uv.exe")
    sys.stdout.flush()
    try:
        code = run([uv, "run", "--quiet", str(Path(__file__).resolve().parent / "agents.py"), "sync", "--skills"]).returncode
    except OSError:
        code = None
    return [] if code == 0 else ["skills 沒有跟著 profile 同步，請在 repo 根目錄跑：uv run engine/scripts/agents.py sync --skills"]


def fallback_notice(data):
    return (f"這台還沒選 profile，先用 {DEFAULT}（下載、安裝前會先問）。要建立自己的：開新 session 說"
            f"「幫我設定 OmniKit」；用現有的：uv run engine/scripts/profiles.py --set <名稱>，"
            f"可選：{'、'.join(available(data))}")


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def fails(fn):
        try:
            fn()
        except SystemExit:
            return True
        return False

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data, state = tmp / "data", tmp / "state"
        paths = {"claude-code": tmp / "home" / ".claude" / "CLAUDE.md",
                 "codex": tmp / "home" / ".codex" / "AGENTS.md",
                 "antigravity": tmp / "home" / ".gemini" / "GEMINI.md"}
        legacy_config = tmp / "skillshare.yaml"
        write(data / "rules" / "baseline.md", "# 底線\r\n\r\n不碰金鑰\r\n")
        write(data / "profiles" / "default" / "AGENTS.md", "# default\n保守\n")
        write(data / "profiles" / "x" / "AGENTS.md", "# x\n放手\n")
        write(data / "profiles" / "empty" / "notes.md", "沒有 AGENTS.md 的資料夾不算 profile\n")
        old_block = f"{BEGIN}\n@C:/old/data/rules/AGENTS.md\n{END}"
        write(paths["claude-code"], old_block + "\r\n# 我自己的規則\r\nkeep\r\n")
        write(paths["codex"], "# 我原本的 Codex 規則\n")
        write(paths["antigravity"], "# 我原本的 Antigravity 規則\n")
        shared = tmp / "home" / ".dsh" / "AGENTS.md"
        shared.parent.mkdir(parents=True)
        os.link(paths["antigravity"], shared)

        def run(**kw):
            kw.setdefault("paths", paths)
            kw.setdefault("skillshare_config", legacy_config)
            return apply(data, state, **kw)

        check("可選的 profile 只算有 AGENTS.md 的資料夾", available(data) == ["default", "x"])
        check("沒選過：用 default 並標記為預設", resolve(data, state) == ("default", True))
        check("沒有記錄也沒有舊安裝：只接 Claude Code", connected(state, paths, legacy_config) == ["claude-code"])

        all3 = ["claude-code", "codex", "antigravity"]
        lines = run(agents=all3, take_over=True)
        md = text(paths["claude-code"])
        check("沒選過：提醒還沒選 profile", any("還沒選 profile" in line for line in lines))
        check("沒選過：不記錄選擇", not (state / "profile.json").exists())
        check("Claude：舊的單一 import 換成底線與 profile 兩份",
              "@C:/old" not in md and md.count(BEGIN) == 1
              and (data / "profiles" / "default" / "AGENTS.md").resolve().as_posix() in md)
        check("Claude：區塊以外的內容與 CRLF 不動", md.endswith("\r\n# 我自己的規則\r\nkeep\r\n"))
        codex = text(paths["codex"])
        check("Codex：受管區塊加在開頭，放底線加 profile；原本的規則留在區塊外照常生效",
              codex.startswith(BEGIN) and codex.index("不碰金鑰") < codex.index("保守") < codex.index(END)
              and codex.endswith(END + "\n# 我原本的 Codex 規則\n") and "\r" not in codex)
        check("Codex：原本的規則先備份", text(paths["codex"].with_name("AGENTS.md.pre-omnikit")) == "# 我原本的 Codex 規則\n")
        gemini = text(paths["antigravity"])
        check("Antigravity：受管區塊加在開頭，原本的內容保留",
              gemini.startswith(BEGIN) and "不碰金鑰" in gemini and gemini.endswith("# 我原本的 Antigravity 規則\n"))
        check("Antigravity：原地改寫，硬連結的其他名字一起更新",
              os.path.samefile(paths["antigravity"], shared) and text(shared) == gemini)
        check("Antigravity：原本的規則先備份",
              text(paths["antigravity"].with_name("GEMINI.md.pre-omnikit")) == "# 我原本的 Antigravity 規則\n")
        check("訊息列出三個 agent", lines[0].startswith("已套用 profile：default（Claude Code、Codex、Antigravity，"))

        before = {k: p.read_bytes() for k, p in paths.items()}
        run(agents=all3)
        check("重複執行：三份規則都不變", all(p.read_bytes() == before[k] for k, p in paths.items()))

        run(agents=all3, wanted="x")
        check("--set：記下選擇", chosen(state) == "x")
        check("--set：三邊都換成 x", "/profiles/x/AGENTS.md" in text(paths["claude-code"])
              and "放手" in text(paths["codex"]) and "放手" in text(paths["antigravity"]) and "放手" in text(shared))
        check("--set：不會多出第二份備份", not list(paths["codex"].parent.glob("AGENTS.md.pre-omnikit-*")))
        check("選過之後：不再提醒", not any("還沒選" in line for line in run(agents=all3)))
        write(paths["codex"], text(paths["codex"]) + "# 之後自己加的\n")
        run(agents=all3, wanted="default")
        codex = text(paths["codex"])
        check("Codex 換 profile：只換區塊，區塊外原本的與之後自己加的都留著",
              "保守" in codex and "放手" not in codex and codex.endswith(END + "\n# 我原本的 Codex 規則\n# 之後自己加的\n"))
        run(agents=all3, wanted="x")

        write(paths["codex"], "# 使用者自己換掉的\n")
        lines = run(agents=all3)
        check("同步時：被拿掉的 Codex 區塊不加回去", text(paths["codex"]) == "# 使用者自己換掉的\n"
              and any(str(paths["codex"]) in line and "區塊被拿掉了" in line for line in lines))
        write_in_place(paths["antigravity"], "# 使用者拿掉了區塊\n")
        lines = run(agents=all3)
        check("同步時：被拿掉的 Antigravity 區塊不加回去", text(paths["antigravity"]) == "# 使用者拿掉了區塊\n"
              and any("區塊被拿掉了" in line for line in lines))

        write(state / "agents.json", json.dumps({"agents": ["claude-code", "antigravity"]}))
        check("有記錄：照記錄接", connected(state, paths, legacy_config) == ["claude-code", "antigravity"])
        (state / "agents.json").unlink()
        write(legacy_config, "extras:\n  - name: rules-codex\n")
        check("舊版 skillshare 安裝：推斷 Codex 有接上", connected(state, paths, legacy_config) == ["claude-code", "codex"])
        lines = run(agents=["codex"])
        check("舊版 skillshare 管的 Codex 規則：直接接手換成只有區塊，不另外備份",
              text(paths["codex"]) == content_block(compose(data, "x")) + "\n"
              and not list(paths["codex"].parent.glob("AGENTS.md.pre-omnikit-*")))
        legacy_config.unlink()
        write(paths["codex"], compose(data, "x"))  # 舊版整份換掉的格式：開頭是產生標記
        run(agents=["codex"])
        check("舊版整份換掉的 Codex 規則：換成只有區塊，內容一樣，安裝前的備份不動",
              text(paths["codex"]) == content_block(compose(data, "x")) + "\n"
              and text(paths["codex"].with_name("AGENTS.md.pre-omnikit")) == "# 我原本的 Codex 規則\n")
        lines = disconnect_block(paths["codex"])
        check("移除 Codex 區塊：只剩區塊時還原安裝前的備份，備份收掉",
              text(paths["codex"]) == "# 我原本的 Codex 規則\n" and not paths["codex"].with_name("AGENTS.md.pre-omnikit").exists()
              and any("還原安裝前的內容" in line for line in lines))

        check("不存在的 profile 失敗", fails(lambda: run(wanted="nope")))
        check("名稱格式不對失敗", fails(lambda: run(wanted="Bad_Name")))
        check("失敗時不改記錄", chosen(state) == "x")
        (data / "profiles" / "x" / "AGENTS.md").unlink()
        check("選過的 profile 被刪掉：失敗，不悄悄換回 default", fails(lambda: run()))

        gem = tmp / "g" / "GEMINI.md"
        write(gem, "# 原本\n")
        link = tmp / "g" / "AGENTS.md"
        os.link(gem, link)
        connect_block(gem, compose(data, "default"), take_over=True)
        lines = disconnect_block(gem)
        check("移除 Antigravity 區塊：還原成原本的內容，硬連結還在",
              text(gem) == "# 原本\n" and os.path.samefile(gem, link) and any("已拿掉" in line for line in lines))
        check("移除後跟備份一樣：多餘的備份刪掉", not gem.with_name("GEMINI.md.pre-omnikit").exists())
        fresh = tmp / "f" / "GEMINI.md"
        connect_block(fresh, compose(data, "default"), take_over=True)
        disconnect_block(fresh)
        check("OmniKit 建的 GEMINI.md：移除時整個刪掉", not fresh.exists())

        calls = []

        def fake_run(code):
            def run_(cmd):
                calls.append(cmd)
                if code is None:
                    raise OSError("找不到 uv")
                return subprocess.CompletedProcess(cmd, code)
            return run_

        check("換 profile 後同步 skills：交給 agents.py sync --skills",
              sync_skills(fake_run(0)) == [] and calls[-1][-3:] == [str(Path(__file__).resolve().parent / "agents.py"), "sync", "--skills"])
        check("skills 同步失敗：印出手動指令", "agents.py sync --skills" in sync_skills(fake_run(1))[0])
        check("找不到 uv：印出手動指令，不中斷", "agents.py sync --skills" in sync_skills(fake_run(None))[0])

        write(data / "profiles" / "x" / "answers.json", json.dumps({"evaluate_tools": False}))
        write(data / "profiles" / "y" / "answers.json", "﻿" + json.dumps({"evaluate_tools": True}))
        check("訪談答不評估工具：不裝 omnikit-eval；答要或手寫的 profile：全部都裝",
              set(skipped_skills(data, "x")) == {"omnikit-eval"} and skipped_skills(data, "y") == {}
              and skipped_skills(data, "default") == {})

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="選擇並接上 OmniKit profile")
    parser.add_argument("--set", dest="wanted", metavar="名稱", help="換成這個 profile 並記下來")
    parser.add_argument("--show", action="store_true", help="只印出目前的 profile 名稱，不改任何東西")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.show:
        # 只印名稱：install.ps1 會接住 stdout；PowerShell 5.1 轉向 stderr 會出錯，所以不印提醒
        print(resolve(DATA, STATE)[0])
        return 0
    for line in apply(DATA, STATE, wanted=args.wanted):
        print(line)
    if args.wanted:
        for line in sync_skills():
            print(line)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
