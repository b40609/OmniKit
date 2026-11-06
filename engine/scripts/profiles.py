# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit profile：這台電腦套用哪一份個人規則，並接到 Claude Code、Codex 與 Antigravity。

agent 讀到的規則是兩層接在一起：
- data/rules/baseline.md：安全底線，所有人都套用
- profile 的 AGENTS.md：個人規則（語言、語氣、授權程度）
同一個 profile 資料夾裡的 scenarios.yaml 是評估工具用的真實情境，由 validate.py 讀。

profile 放在兩個地方，同名時 repo 外的優先：
- %LOCALAPPDATA%\\omnikit\\profiles\\<名稱>\\：訪談（omnikit-setup）產生的。個人資料不放進 repo，
  不會被 commit 或 push，git status 也看不到（FR-38）。
- data/profiles/<名稱>/：跟著 repo 的，default 與維護者手寫的。
舊版把訪談產生的 profile 寫在 data/profiles/ 裡；--migrate 把它們搬到 repo 外，刪掉 repo 裡的舊檔前先問。

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
  uv run engine/scripts/profiles.py --migrate       把舊版存在 repo 裡的 profile 搬到 repo 外（能互動時先問）
  uv run engine/scripts/profiles.py --migrate --yes 使用者已經同意：直接搬，確認內容一樣後刪掉 repo 裡的舊檔
  uv run engine/scripts/profiles.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import stat
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


def roots(data, state=None):
    """找 profile 的地方，依優先順序：repo 外（訪談產生的）、repo 裡（default 與維護者手寫的）。"""
    return ([state / "profiles"] if state is not None else []) + [data / "profiles"]


def folder(data, state, name):
    """profile 的資料夾（有 AGENTS.md 的才算）；repo 外的優先，都沒有回 None。"""
    for root in roots(data, state):
        if (root / name / "AGENTS.md").is_file():
            return root / name
    return None


def available(data, state=None):
    names = set()
    for root in roots(data, state):
        if root.is_dir():
            names.update(p.name for p in root.iterdir() if NAME.match(p.name) and (p / "AGENTS.md").is_file())
    return sorted(names)


def label(data, state, name):
    """給人看的 profile 位置：repo 裡的寫 data/profiles/<名稱>，repo 外的寫完整路徑。"""
    found = folder(data, state, name)
    if found is None or found.parent == data / "profiles":
        return f"data/profiles/{name}"
    return found.as_posix()


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
    if folder(data, state, name) is None:
        raise SystemExit(
            f"找不到 profile「{name}」（{state / 'profiles' / name} 或 data/profiles/{name}，要有 AGENTS.md），"
            f"可選：{'、'.join(available(data, state)) or '無'}"
        )
    return name, fallback


def rules_files(data, state, name):
    return data / "rules" / "baseline.md", (folder(data, state, name) or data / "profiles" / name) / "AGENTS.md"


def answers(data, state, name):
    """訪談產生的 profile 留下的答案（answers.json）；手寫的 profile 沒有，讀不懂也回 None。"""
    found = folder(data, state, name)
    try:
        doc = json.loads(text(found / "answers.json")) if found else None
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def skipped_skills(data, state, name):
    """這個 profile 不裝的 OmniKit skill：{skill: 說明}。只看訪談產生的 answers.json；
    手寫的 profile（沒有 answers.json）或檔案讀不懂時全部都裝，跟以前一樣。"""
    doc = answers(data, state, name)
    if doc is None:
        return {}
    return {skill: why for skill, (key, why) in OPTIONAL_SKILLS.items() if doc.get(key) is False}


def compose(data, state, name):
    """給 Codex 與 Antigravity 的規則：底線在前，profile 在後；第一行是產生標記。"""
    parts = [text(p).replace("\r\n", "\n").strip() for p in rules_files(data, state, name)]
    header = f"{HEADER}data/rules/baseline.md + {label(data, state, name)}/AGENTS.md -->"
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


def import_line(path):
    """Claude Code 的 @import：路徑用正斜線；空白前面要加反斜線，不然路徑在第一個空白就斷掉，
    整份規則不會載入（https://code.claude.com/docs/en/memory）。使用者名稱有空白時，repo 或 profile 的路徑就有空白。"""
    return "@" + path.resolve().as_posix().replace(" ", "\\ ")


def claude_block(data, state, name):
    """skillshare 0.28.2 的 import 模式在 Windows 寫出反斜線路徑，Claude Code 不會載入；所以自己維護，路徑用正斜線。"""
    imports = "\n".join(import_line(p) for p in rules_files(data, state, name))
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
    content = compose(data, state, name)
    # 給 uninstall.ps1 比對 ~/.codex/AGENTS.md 是不是 OmniKit 的副本
    write(state / "rules" / "AGENTS.md", content)
    done, notes = [], []
    if "claude-code" in agents:
        connect_claude(paths["claude-code"], claude_block(data, state, name))
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
        lines.append(fallback_notice(data, state))
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


def fallback_notice(data, state=None):
    return (f"這台還沒選 profile，先用 {DEFAULT}（下載、安裝前會先問）。要建立自己的：開新 session 說"
            f"「幫我設定 OmniKit」；用現有的：uv run engine/scripts/profiles.py --set <名稱>，"
            f"可選：{'、'.join(available(data, state))}")


# ---- 舊版存在 repo 裡的 profile：搬到 repo 外（FR-38） ----

def tracked_profiles(repo):
    """repo 裡有進版本控制的 profile 名稱（維護者 commit 的）。不是 git repo 或沒有 git：回空集合。"""
    try:
        r = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--", "data/profiles"],
                           capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if r.returncode != 0:
        return set()
    parts = (item.split("/") for item in r.stdout.decode("utf-8", "replace").split("\0"))
    return {p[2] for p in parts if len(p) >= 4 and p[:2] == ["data", "profiles"]}


def legacy(data, tracked=None):
    """舊版存在 repo 裡、由訪談產生的 profile：有 answers.json、沒進版本控制。這些是同事的個人資料，
    git status 看得到，要搬到 repo 外。手寫的（沒有 answers.json）與維護者 commit 的都不算。"""
    root = data / "profiles"
    if not root.is_dir():
        return []
    tracked = tracked_profiles(data.parent) if tracked is None else tracked
    return sorted(p.name for p in root.iterdir()
                  if NAME.match(p.name) and p.name not in tracked and (p / "answers.json").is_file())


def same_files(src, dest):
    """dest 有 src 的每一個檔案，內容也一樣（dest 多出來的不管）。"""
    files = [p.relative_to(src) for p in src.rglob("*") if p.is_file()]
    return all((dest / rel).is_file() and (dest / rel).read_bytes() == (src / rel).read_bytes() for rel in files)


def remove_tree(path):
    """刪資料夾；Windows 的唯讀屬性會讓刪除失敗，先清掉再刪。"""
    def force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))


def migrate(data, state, tracked=None, reapply=None):
    """把舊版存在 repo 裡的 profile 搬到 repo 外（state/profiles/<名稱>），回傳要印的訊息。
    呼叫前要先取得使用者同意：搬完會刪掉 repo 裡的舊檔。
    - 先複製到暫存資料夾再改名，中途失敗不會留下一半的 profile。
    - repo 外已經有同名的：每個檔案都一樣就當作搬過了；不一樣就兩邊都不動（repo 外的優先），請使用者自己決定。
    - 這台選的 profile 搬過去之後，先重新接上規則（reapply），Claude 的 import 改指到 repo 外，才刪舊檔。
    - 刪之前再比對一次，repo 外的每個檔案都跟舊檔一樣才刪。"""
    lines, moved = [], []
    for name in legacy(data, tracked):
        src, dest = data / "profiles" / name, state / "profiles" / name
        if dest.exists():
            if not same_files(src, dest):
                lines.append(f"profile {name}：{dest} 已經有同名、內容不同的 profile，以它為準；"
                             f"repo 裡的 {src} 沒有動，不需要的話自己刪掉")
                continue
        else:
            staging = dest.with_name(f".{name}.migrating")
            if staging.exists():
                remove_tree(staging)
            shutil.copytree(src, staging)
            staging.replace(dest)
            lines.append(f"profile {name}：已複製到 {dest}")
        moved.append(name)
    if reapply and chosen(state) in moved:
        lines += reapply()
    for name in moved:
        src, dest = data / "profiles" / name, state / "profiles" / name
        if same_files(src, dest):
            remove_tree(src)
            lines.append(f"profile {name}：已刪掉 repo 裡的舊檔（{src}）")
        else:
            lines.append(f"profile {name}：複製後的內容跟 repo 裡的不一樣，舊檔沒有刪（{src}）")
    return lines


def migrate_plan(data, state, tracked=None):
    """還沒同意時給使用者看的：要搬哪些、搬到哪裡。"""
    return [f"profile {name}：{data / 'profiles' / name} → {state / 'profiles' / name}" for name in legacy(data, tracked)]


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

    def fails_with(fn):
        try:
            fn()
        except SystemExit as e:
            return e.code
        return None

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
              and import_line(data / "profiles" / "default" / "AGENTS.md") in md)
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
              text(paths["codex"]) == content_block(compose(data, state, "x")) + "\n"
              and not list(paths["codex"].parent.glob("AGENTS.md.pre-omnikit-*")))
        legacy_config.unlink()
        write(paths["codex"], compose(data, state, "x"))  # 舊版整份換掉的格式：開頭是產生標記
        run(agents=["codex"])
        check("舊版整份換掉的 Codex 規則：換成只有區塊，內容一樣，安裝前的備份不動",
              text(paths["codex"]) == content_block(compose(data, state, "x")) + "\n"
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
        connect_block(gem, compose(data, state, "default"), take_over=True)
        lines = disconnect_block(gem)
        check("移除 Antigravity 區塊：還原成原本的內容，硬連結還在",
              text(gem) == "# 原本\n" and os.path.samefile(gem, link) and any("已拿掉" in line for line in lines))
        check("移除後跟備份一樣：多餘的備份刪掉", not gem.with_name("GEMINI.md.pre-omnikit").exists())
        fresh = tmp / "f" / "GEMINI.md"
        connect_block(fresh, compose(data, state, "default"), take_over=True)
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

        write(data / "profiles" / "x" / "AGENTS.md", "# x\n放手\n")
        write(data / "profiles" / "x" / "answers.json", json.dumps({"evaluate_tools": False}))
        write(data / "profiles" / "y" / "AGENTS.md", "# y\n")
        write(data / "profiles" / "y" / "answers.json", "﻿" + json.dumps({"evaluate_tools": True}))
        check("訪談答不評估工具：不裝 omnikit-eval；答要或手寫的 profile：全部都裝",
              set(skipped_skills(data, state, "x")) == {"omnikit-eval"} and skipped_skills(data, state, "y") == {}
              and skipped_skills(data, state, "default") == {})

        # ---- repo 外的 profile（FR-38）：訪談產生的存在 state/profiles，同名時優先 ----
        local = state / "profiles"
        write(local / "alice" / "AGENTS.md", "# alice\n存在 repo 外\n")
        write(local / "x" / "AGENTS.md", "# x（repo 外）\n本機的優先\n")
        write(local / "x" / "answers.json", json.dumps({"evaluate_tools": True}))
        write(local / "Bad_Name" / "AGENTS.md", "# 名稱不合格式的不算\n")
        check("可選的 profile：repo 外的也算，同名只列一次，名稱不合格式的不算",
              available(data, state) == ["alice", "default", "x", "y"] and available(data) == ["default", "x", "y"])
        check("同名時 repo 外的優先；沒給 state 就只看 repo 裡的",
              folder(data, state, "x") == local / "x" and folder(data, None, "x") == data / "profiles" / "x")
        check("答案也照優先順序讀：repo 外的 x 要評估，所以全部都裝", skipped_skills(data, state, "x") == {})
        lines = run(agents=["claude-code"], wanted="alice")
        md = text(paths["claude-code"])
        check("repo 外的 profile：Claude import 指到 repo 外，接好的規則也是它",
              import_line(local / "alice" / "AGENTS.md") in md and "存在 repo 外" in text(state / "rules" / "AGENTS.md")
              and chosen(state) == "alice" and lines[0].startswith("已套用 profile：alice"))
        check("產生標記寫出 repo 外的位置", compose(data, state, "alice").splitlines()[0]
              == f"{HEADER}data/rules/baseline.md + {(local / 'alice').as_posix()}/AGENTS.md -->")
        check("repo 裡的 profile：產生標記照舊", compose(data, state, "default").splitlines()[0]
              == f"{HEADER}data/rules/baseline.md + data/profiles/default/AGENTS.md -->")
        check("找不到時說兩個位置", "data/profiles/nope" in str(fails_with(lambda: resolve(data, state, "nope"))))

        # Claude Code 的 import 遇到空白就斷掉：使用者名稱有空白時，repo 與 profile 的路徑都有空白
        sdata, sstate = tmp / "王 小明 的 資料夾" / "data", tmp / "王 小明 的 資料夾" / "state"
        write(sdata / "rules" / "baseline.md", "# 底線\n")
        write(sstate / "profiles" / "amy" / "AGENTS.md", "# amy\n")
        imports = [line for line in claude_block(sdata, sstate, "amy").splitlines() if line.startswith("@")]
        check("Claude import：路徑的空白都用反斜線跳脫，還原後就是原本的路徑",
              len(imports) == 2 and not any(re.search(r"(?<!\\) ", line) for line in imports)
              and [line[1:].replace("\\ ", " ") for line in imports]
              == [p.resolve().as_posix() for p in rules_files(sdata, sstate, "amy")])

        # ---- 舊版存在 repo 裡的 profile：搬到 repo 外 ----
        mdata, mstate = tmp / "m" / "data", tmp / "m" / "state"
        mpaths = {k: tmp / "m" / "home" / p.relative_to(tmp / "home") for k, p in paths.items()}
        write(mdata / "rules" / "baseline.md", "# 底線\n")
        write(mdata / "profiles" / "default" / "AGENTS.md", "# default\n")
        write(mdata / "profiles" / "ryan" / "AGENTS.md", "# 維護者手寫的\n")
        write(mdata / "profiles" / "keep" / "AGENTS.md", "# 維護者 commit 的訪談 profile\n")
        write(mdata / "profiles" / "keep" / "answers.json", "{}")
        bob, moved = mdata / "profiles" / "bob", mstate / "profiles" / "bob"
        write(bob / "AGENTS.md", "# bob\n舊版存在 repo 裡\n")
        write(bob / "answers.json", json.dumps({"name": "bob"}))
        write(bob / "AGENTS.md.bak", "# bob 更早的\n")
        check("舊版 profile：有 answers.json、沒進版本控制的才算；手寫的與 commit 過的不算",
              legacy(mdata, tracked={"default", "ryan", "keep"}) == ["bob"])
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q", str(mdata.parent)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(mdata.parent), "-c", "core.autocrlf=false", "-c", "core.longpaths=true", "add",
                            "data/profiles/default", "data/profiles/ryan", "data/profiles/keep"], check=True, capture_output=True)
            check("用 git 判斷有沒有進版本控制", tracked_profiles(mdata.parent) == {"default", "ryan", "keep"}
                  and legacy(mdata) == ["bob"])
        else:
            print("略過：找不到 git，沒有測 tracked_profiles")
        tracked = {"default", "ryan", "keep"}

        def mapply():
            return apply(mdata, mstate, mpaths, agents=["claude-code"], skillshare_config=legacy_config)

        def mcli(**kw):
            kw.setdefault("reapply", mapply)
            kw.setdefault("tracked", tracked)
            return migrate_cli(mdata, mstate, **kw)

        write(mstate / "profile.json", json.dumps({"profile": "bob"}))
        mapply()
        check("搬之前：舊版的 profile 照常可以用（Claude import 指到 repo 裡）",
              import_line(bob / "AGENTS.md") in text(mpaths["claude-code"]))
        out = mcli(interactive=False)
        check("不能互動又沒加 --yes：列出要搬的，什麼都沒改",
              bob.exists() and not moved.exists() and any("--migrate --yes" in line for line in out)
              and any(str(bob) in line and str(moved) in line for line in out))
        out = mcli(interactive=True, ask=lambda _: "n")
        check("問了、使用者說不要：什麼都沒改", bob.exists() and not moved.exists() and out[0].startswith("沒有搬"))
        out = mcli(interactive=True, ask=lambda _: "y")
        check("同意後：整個資料夾（含 .bak）搬到 repo 外，repo 裡的舊檔刪掉",
              not bob.exists() and text(moved / "AGENTS.md.bak") == "# bob 更早的\n"
              and json.loads(text(moved / "answers.json")) == {"name": "bob"}
              and any("已刪掉 repo 裡的舊檔" in line for line in out))
        check("搬的是這台選的 profile：刪舊檔前先重新接上，Claude import 改指到 repo 外",
              import_line(moved / "AGENTS.md") in text(mpaths["claude-code"]) and chosen(mstate) == "bob")
        check("手寫的與 commit 過的不動", (mdata / "profiles" / "ryan").exists() and (mdata / "profiles" / "keep").exists())
        check("再跑一次：沒有要搬的", mcli(yes=True)[0].startswith("沒有要搬的"))
        write(bob / "AGENTS.md", "# bob\n另一份\n")
        write(bob / "answers.json", "{}")
        out = migrate(mdata, mstate, tracked=tracked, reapply=mapply)
        check("repo 外已經有內容不同的同名 profile：兩邊都不動", bob.exists() and "另一份" not in text(moved / "AGENTS.md")
              and any("內容不同" in line for line in out))
        remove_tree(bob)
        shutil.copytree(moved, bob)
        out = migrate(mdata, mstate, tracked=tracked, reapply=mapply)
        check("上次複製完還沒刪（中斷過）：repo 外的一模一樣，直接刪 repo 裡的舊檔",
              not bob.exists() and moved.exists() and any("已刪掉" in line for line in out))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def migrate_cli(data, state, yes=False, interactive=None, ask=input, reapply=None, tracked=None):
    """--migrate：列出要搬的；使用者同意（--yes，或能互動時回答 y）才搬。"""
    plan = migrate_plan(data, state, tracked)
    if not plan:
        return ["沒有要搬的 profile：repo 裡沒有舊版訪談產生、也沒進版本控制的 profile"]
    lines = [f"舊版把訪談產生的 profile 存在 repo 裡；新版改存在 repo 外（{state / 'profiles'}），不會被 commit：",
             *(f"  {line}" for line in plan)]
    if not yes:
        interactive = sys.stdin.isatty() if interactive is None else interactive
        if not interactive:
            return lines + ["沒辦法詢問（不能互動），什麼都沒改。使用者同意後執行：uv run engine/scripts/profiles.py --migrate --yes"]
        try:
            answer = ask("\n".join(lines) + "\n要搬過去嗎？複製好、確認內容一樣之後，會刪掉 repo 裡的舊檔（y/N）：")
        except EOFError:
            answer = ""
        lines = []
        answer = answer.strip().lower()
        if answer not in ("y", "yes"):
            return ["沒有搬：repo 裡的 profile 照常可以用；之後要搬就重跑 uv run engine/scripts/profiles.py --migrate"]
    return lines + migrate(data, state, tracked, reapply or (lambda: apply(data, state)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="選擇並接上 OmniKit profile")
    parser.add_argument("--set", dest="wanted", metavar="名稱", help="換成這個 profile 並記下來")
    parser.add_argument("--show", action="store_true", help="只印出目前的 profile 名稱，不改任何東西")
    parser.add_argument("--migrate", action="store_true", help="把舊版存在 repo 裡的 profile 搬到 repo 外（能互動時先問）")
    parser.add_argument("--yes", action="store_true", help="搭配 --migrate：使用者已經同意，直接搬並刪掉 repo 裡的舊檔")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.yes and not args.migrate:
        parser.error("--yes 要搭配 --migrate")
    if args.migrate:
        for line in migrate_cli(DATA, STATE, yes=args.yes):
            print(line)
        return 0
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
