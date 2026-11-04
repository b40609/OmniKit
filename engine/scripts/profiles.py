# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit profile：這台電腦套用哪一份個人規則。

agent 讀到的規則是兩層接在一起：
- data/rules/baseline.md：安全底線，所有人都套用
- data/profiles/<名稱>/AGENTS.md：個人規則（語言、語氣、授權程度）
同一個 profile 資料夾裡的 scenarios.yaml 是評估工具用的真實情境，由 validate.py 讀。

選了哪個 profile 記在 %LOCALAPPDATA%\\omnikit\\profile.json。沒選過就用 default（授權偏保守），
而且每次都會提醒，直到用 --set 選定。

接上的方式：
- Claude Code：~/.claude/CLAUDE.md 開頭的受管區塊 import 底線與 profile 兩份，改完開新 session 就生效。
- Codex：不支援 import，所以把兩份接成 %LOCALAPPDATA%\\omnikit\\rules\\AGENTS.md，再由 skillshare
  （extras：rules-codex）複製到 ~/.codex/AGENTS.md。已經接上 Codex，或加了 --codex，才會動 Codex。

用法：
  uv run engine/scripts/profiles.py                 用目前的 profile 重新接上
  uv run engine/scripts/profiles.py --set <名稱>    換 profile 並接上
  uv run engine/scripts/profiles.py --show          只印出目前的 profile 名稱
  uv run engine/scripts/profiles.py --selftest
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA", HOME))
STATE = LOCAL / "omnikit"
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_DIR = HOME / ".codex"
SKILLSHARE = LOCAL / "Programs" / "skillshare" / "skillshare.exe"
SKILLSHARE_CONFIG = Path(os.environ.get("APPDATA", HOME)) / "skillshare" / "config.yaml"
DEFAULT = "default"
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BLOCK = re.compile(r"<!-- omnikit:rules:begin -->.*?<!-- omnikit:rules:end -->", re.S)
CODEX_EXTRA = re.compile(r"(?m)^\s*- name: rules-codex\s*$")


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


def compose(data, name):
    """給 Codex 的規則：底線在前，profile 在後。"""
    parts = [text(p).replace("\r\n", "\n").strip() for p in rules_files(data, name)]
    header = f"<!-- 由 OmniKit 產生，不要手改：data/rules/baseline.md + data/profiles/{name}/AGENTS.md -->"
    return "\n\n".join([header, *parts]) + "\n"


def claude_block(data, name):
    """skillshare 0.28.2 的 import 模式在 Windows 寫出反斜線路徑，Claude Code 不會載入；所以自己維護，路徑用正斜線。"""
    imports = "\n".join("@" + p.resolve().as_posix() for p in rules_files(data, name))
    return f"<!-- omnikit:rules:begin -->\n{imports}\n<!-- omnikit:rules:end -->"


def connect_claude(claude_md, block):
    """換掉受管區塊；沒有就加在開頭。區塊以外的內容與換行都不動。"""
    old = text(claude_md) if claude_md.exists() else ""
    new = BLOCK.sub(lambda _: block, old, count=1) if BLOCK.search(old) else block + "\n" + old
    return write(claude_md, new)


def codex_connected(config):
    try:
        return CODEX_EXTRA.search(text(config)) is not None
    except OSError:
        return False


def skillshare(exe, *args):
    """exe 是 skillshare 的指令（list）；自我測試時換成假的。"""
    label = f"skillshare {' '.join(args[:3])}"
    try:
        result = subprocess.run([*exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        # 公司電腦的防毒（例如 Trend Micro）可能擋下 skillshare.exe，CreateProcess 會回「存取被拒」
        raise SystemExit(f"{label} 無法執行（{str(e).rstrip('。')}），可能被防毒軟體擋下；Codex 的規則還是舊的")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"{label} 失敗（exit {result.returncode}）：{detail}")


def connect_codex(source, config, exe, codex_dir):
    """rules-codex 改從 source 複製再同步。來源已經是 source 就不重設（舊版指向 data/rules 的會改過來）。"""
    if not Path(exe[0]).exists():
        raise SystemExit(f"找不到 skillshare（{exe[0]}），先執行 engine/scripts/install.ps1")
    current = text(config) if config.exists() else ""
    if not (CODEX_EXTRA.search(current) and f"source: {source}" in current):
        skillshare(exe, "extras", "init", "rules-codex", "--source", str(source), "--file", "AGENTS.md",
                   "--target", str(codex_dir), "--as", "AGENTS.md", "--mode", "copy", "--force", "--no-tui")
    skillshare(exe, "sync", "extras")


def apply(data, state, claude_md, config, exe, codex_dir, wanted=None, codex=False):
    """接上 profile，回傳要印給使用者看的訊息。"""
    name, fallback = resolve(data, state, wanted)
    # 名稱確認存在就記下：Codex 那邊中途失敗的話，下次（例如 git hook）會用同一個 profile 重試，
    # 不會讓 Claude Code 退回 default
    if wanted:
        write(state / "profile.json", json.dumps({"profile": name}, ensure_ascii=False) + "\n")
    connect_claude(claude_md, claude_block(data, name))
    source = state / "rules"
    write(source / "AGENTS.md", compose(data, name))
    targets = ["Claude Code"]
    if codex or codex_connected(config):
        connect_codex(source, config, exe, codex_dir)
        targets.append("Codex")
    lines = [f"已套用 profile：{name}（{'、'.join(targets)}，開新的 session 才生效）"]
    if fallback:
        lines.append(fallback_notice(data))
    return lines


def fallback_notice(data):
    return (f"這台還沒選 profile，先用 {DEFAULT}（下載、安裝前會先問）。要用自己的："
            f"uv run engine/scripts/profiles.py --set <名稱>，可選：{'、'.join(available(data))}")


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
        claude_md, config = tmp / "claude" / "CLAUDE.md", tmp / "skillshare.yaml"
        codex_dir, calls = tmp / "codex", tmp / "calls.txt"
        exe = [str(tmp / "missing-skillshare.exe")]
        write(data / "rules" / "baseline.md", "# 底線\r\n\r\n不碰金鑰\r\n")
        write(data / "profiles" / "default" / "AGENTS.md", "# default\n保守\n")
        write(data / "profiles" / "x" / "AGENTS.md", "# x\n放手\n")
        write(data / "profiles" / "empty" / "notes.md", "沒有 AGENTS.md 的資料夾不算 profile\n")
        old_block = "<!-- omnikit:rules:begin -->\n@C:/old/data/rules/AGENTS.md\n<!-- omnikit:rules:end -->"
        write(claude_md, old_block + "\r\n# 我自己的規則\r\nkeep\r\n")

        def run(**kw):
            return apply(data, state, claude_md, config, exe, codex_dir, **kw)

        check("可選的 profile 只算有 AGENTS.md 的資料夾", available(data) == ["default", "x"])
        check("沒選過：用 default 並標記為預設", resolve(data, state) == ("default", True))

        lines = run()
        md = text(claude_md)
        check("沒選過：提醒還沒選 profile", any("還沒選 profile" in line for line in lines))
        check("沒選過：不記錄選擇", not (state / "profile.json").exists())
        check("Claude：舊的單一 import 換成底線與 profile 兩份",
              "@C:/old" not in md and md.count("omnikit:rules:begin") == 1
              and (data / "rules" / "baseline.md").resolve().as_posix() in md
              and (data / "profiles" / "default" / "AGENTS.md").resolve().as_posix() in md)
        check("Claude：區塊以外的內容與 CRLF 不動", md.endswith("\r\n# 我自己的規則\r\nkeep\r\n"))
        composed = text(state / "rules" / "AGENTS.md")
        check("Codex：底線在前、profile 在後", composed.index("不碰金鑰") < composed.index("保守"))
        check("Codex：換行統一成 LF", "\r" not in composed)
        check("Codex 沒接上就不動 Codex", lines[0].startswith("已套用 profile：default（Claude Code，"))

        before = claude_md.read_bytes()
        run()
        check("重複執行：CLAUDE.md 不變", claude_md.read_bytes() == before)

        run(wanted="x")
        check("--set：記下選擇", chosen(state) == "x")
        check("--set：Claude 改 import x", "/profiles/x/AGENTS.md" in text(claude_md))
        check("--set：Codex 規則換成 x", "放手" in text(state / "rules" / "AGENTS.md"))
        check("選過之後：不再提醒", not any("還沒選" in line for line in run()))

        check("不存在的 profile 失敗", fails(lambda: run(wanted="nope")))
        check("名稱格式不對失敗", fails(lambda: run(wanted="Bad_Name")))
        check("失敗時不改記錄", chosen(state) == "x")

        (data / "profiles" / "x" / "AGENTS.md").unlink()
        check("選過的 profile 被刪掉：失敗，不悄悄換回 default", fails(lambda: run()))

        write(data / "profiles" / "x" / "AGENTS.md", "# x\n放手\n")
        write(config, "extras:\n  - name: rules-codex\n    source: C:\\old\\data\\rules\n")
        check("Codex 已接上但找不到 skillshare：失敗", fails(lambda: run(wanted="default")))
        check("Codex 失敗時仍記下選擇，下次用同一個重試", chosen(state) == "default")

        # 假的 skillshare：記下參數；extras init 改寫設定檔的來源，sync extras 把來源複製到 Codex
        fake = tmp / "fake_skillshare.py"
        write(fake, (
            "import shutil, sys\nfrom pathlib import Path\n"
            f"Path(r'{calls}').open('a', encoding='utf-8').write(' '.join(sys.argv[1:3]) + '\\n')\n"
            "a = sys.argv[1:]\n"
            "if a[:2] == ['extras', 'init']:\n"
            f"    Path(r'{config}').write_text('extras:\\n  - name: rules-codex\\n    source: ' + a[a.index('--source') + 1] + '\\n', encoding='utf-8')\n"
            "if a[:2] == ['sync', 'extras']:\n"
            f"    Path(r'{codex_dir}').mkdir(exist_ok=True)\n"
            f"    shutil.copy(Path(r'{state}') / 'rules' / 'AGENTS.md', Path(r'{codex_dir}') / 'AGENTS.md')\n"
        ))
        exe[:] = [sys.executable, str(fake)]
        lines = run(wanted="x")
        check("Codex 已接上：舊來源改指到組合好的規則", f"source: {state / 'rules'}" in text(config))
        check("Codex：同步後內容是 x", "放手" in text(codex_dir / "AGENTS.md"))
        check("Codex：訊息列出兩邊", "Claude Code、Codex" in lines[0])
        run()
        check("Codex：來源已正確就不重設，只同步",
              text(calls).splitlines() == ["extras init", "sync extras", "sync extras"])

        fresh = tmp / "new" / "CLAUDE.md"
        connect_claude(fresh, claude_block(data, "default"))
        check("沒有 CLAUDE.md：建立只有受管區塊的檔案", text(fresh).startswith("<!-- omnikit:rules:begin -->"))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="選擇並接上 OmniKit profile")
    parser.add_argument("--set", dest="wanted", metavar="名稱", help="換成這個 profile 並記下來")
    parser.add_argument("--codex", action="store_true", help="Codex 還沒接上也要接（install.ps1 用）")
    parser.add_argument("--show", action="store_true", help="只印出目前的 profile 名稱，不改任何東西")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.show:
        # 只印名稱：install.ps1 會接住 stdout；PowerShell 5.1 轉向 stderr 會出錯，所以不印提醒
        print(resolve(DATA, STATE)[0])
        return 0
    for line in apply(DATA, STATE, CLAUDE_MD, SKILLSHARE_CONFIG, [str(SKILLSHARE)], CODEX_DIR, args.wanted, args.codex):
        print(line)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
