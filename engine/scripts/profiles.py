# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit profile：這台電腦套用哪一份個人規則，並接到 Claude Code、Codex 與 Antigravity。

agent 讀到的規則是兩層接在一起，依序：
- data/rules/baseline.md：安全底線，所有人都套用
- data/rules/dispatch.md：子任務分派的共用層（任務級別、模型類別、思考程度、升級、委派紀錄），所有人都套用
- profile 的 AGENTS.md：個人規則（語言、語氣、授權程度）
- profile 的 dispatch.md（查表設定，不常駐載入，由 dispatch.py 讀取）
（原 data/rules/mobile-web.md 已於 2026-11-26 移出常駐，轉為 omnikit-mobile-web 按需 skill）
同一個 profile 資料夾裡的 scenarios.yaml 是評估工具用的真實情境，由 validate.py 讀。

profile 放在兩個地方，同名時 repo 外的優先：
- ~/.omnikit/profiles/<名稱>/：訪談（omnikit-setup）產生的。個人資料不放進 repo，
  不會被 commit 或 push，git status 也看不到（FR-38）。
- data/profiles/<名稱>/：跟著 repo 的，default 與維護者手寫的。
舊版把訪談產生的 profile 寫在 data/profiles/ 裡；--migrate 把它們搬到 repo 外，刪掉 repo 裡的舊檔前先問。

選了哪個 profile 記在 ~/.omnikit/profile.json（狀態資料夾，見 statedir.py）。沒選過就用 default（授權偏保守），
而且每次都會提醒，直到用 --set 選定。

接上的方式（只接 sync.py 記錄裡的 agent，記在 ~/.omnikit/config.json）：
- Claude Code：~/.claude/CLAUDE.md 開頭的受管區塊 import 底線與 profile 兩份，改完開新 session 就生效。
  其他 Claude 設定目錄（CLAUDE_CONFIG_DIR、T3 Code 每個 Claude 實例的 homePath、~/.claude-* 等，見 homes.py）的
  CLAUDE.md 也放同一個區塊，不然那些帳號只讀自己目錄的 CLAUDE.md，完全讀不到 OmniKit 規則（claude_homes）。
- Codex：不支援 import，~/.codex/AGENTS.md 開頭的受管區塊放兩份接在一起的內容；原本的規則留在區塊外，
  照常生效。舊版整份換掉的（開頭是產生標記），同步時換成只有區塊，規則內容一樣。
  其他 Codex 設定目錄（CODEX_HOME 等，codex_homes）的 AGENTS.md 也放同一個區塊。
- Antigravity：拆成 ~/.gemini/AGENTS.md（共用）與 ~/.gemini/GEMINI.md（個人）開頭的受管區塊，單檔 <= 24,000 bytes。
Codex 與 Antigravity 的檔案常跟其他工具共用（硬連結），所以原地改寫，不換掉檔案。
第一次接上時（install.ps1 透過 sync.py connect），原本的 Codex 與 Antigravity 規則先備份成
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
from datetime import datetime, timedelta
from pathlib import Path

import homes  # 同一個資料夾：這台每個 agent 在用的設定目錄
import statedir  # 同一個資料夾：狀態資料夾 ~/.omnikit，以及從舊位置搬過來
from fsretry import flaky, retry  # 同一個資料夾：防毒短暫鎖住檔案時等一下再試（FR-34）

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA", HOME))
STATE = statedir.STATE  # ~/.omnikit：不放 %LOCALAPPDATA%，從封裝的 app（Claude 桌面版）裡跑會被轉存成另一份
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
CANARY = "看不到 OmniKit 安全底線內容時，先告訴使用者跑 omnikit doctor（uv run engine/scripts/doctor.py）"
CODEX_EXTRA = re.compile(r"(?m)^\s*- name: rules-codex\s*$")
# 訪談答案（answers.json）裡某題答 false 就不裝的 OmniKit skill：skill → （答案欄位, 說明）
OPTIONAL_SKILLS = {"omnikit-eval": ("evaluate_tools", "不評估新工具")}


def text(path):
    return path.read_bytes().decode("utf-8-sig")


def write(path, content):
    """內容沒變就不寫，回傳有沒有改。用 bytes 寫，Windows 上不會把 LF 換成 CRLF。
    防毒短暫鎖住檔案時等一下再試（fsretry）；這一節的寫入、複製、刪除都一樣。"""
    data = content.encode("utf-8")
    if path.exists() and retry(path.read_bytes) == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    retry(path.write_bytes, data)
    return True


def write_in_place(path, content):
    """原地改寫，不換掉檔案：硬連結到同一個檔案的其他名字會一起更新，不會斷開。content 是 bytes 就原樣寫。"""
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        retry(path.write_bytes, data)
        return True
    if retry(path.read_bytes) == data:
        return False
    retry(overwrite, path, data)
    return True


def overwrite(path, data):
    """打開原本的檔案改寫（r+b），不建新檔。"""
    with open(path, "r+b") as f:
        f.write(data)
        f.truncate()


def backup(path):
    """備份成 <檔名>.pre-omnikit；已經有同名備份就加上時間。回傳備份檔。"""
    target = path.with_name(path.name + ".pre-omnikit")
    if target.exists():
        target = path.with_name(f"{path.name}.pre-omnikit-{datetime.now():%Y%m%d%H%M%S}")
    retry(shutil.copyfile, path, target)
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


# data/rules/ 底下所有人都套用的，依序；除了安全底線，其他沒有就跳過。
# 2026-11-25（Step 1.3）：個人層 dispatch.md 屬於查表設定（帳號與實例對照），移出常駐載入規則，改由 dispatch.py 需要時讀，
# 並將 Antigravity 全域規則拆成 ~/.gemini/AGENTS.md（共用）與 ~/.gemini/GEMINI.md（個人），強制檢查單檔 <= 24,000 bytes、總計 <= 20,000 tokens。
# 2026-11-26（自我迭代 P0）：mobile-web.md 移出常駐 SHARED_RULES，轉為 omnikit-mobile-web 按需 skill；
# 規則內的 <!-- review_on: YYYY-MM-DD ... --> 到期標記於組合 Codex／Antigravity 受管區塊時自動剝除（Claude Code 直接 @import 原檔保留行尾註解）。
SHARED_RULES = ("baseline.md", "dispatch.md")
OPTIONAL_RULES = {"dispatch.md"}
PROFILE_RULES = ("AGENTS.md",)  # 個人層常駐載入的規則；dispatch.md 移出 always-on，由 dispatch.py 直接讀
# 2026-11-27：同事實測「裝好了然後呢，什麼都沒發生」。還沒選 profile 時多接一份 default/onboarding.md，
# 讓三家（不靠 hook：Codex 的 hook 要先信任、Antigravity 不吃 SessionStart）開新對話的第一則回覆主動破冰並接設定訪談
ONBOARDING = "onboarding.md"
ONBOARDING_STATE = "onboarding.json"  # 狀態資料夾裡：使用者說「先不要」的暫緩到期日
SNOOZE_DAYS = 7
AGY_MAX_FILE_BYTES = 24_000     # agy-customizations/docs/rules.md:31 單檔超過 24,000 bytes 會在行界靜默截斷
AGY_MAX_TOTAL_TOKENS = 20_000   # agy-customizations/docs/rules.md:34 全域與 always-on 合計超過 20,000 tokens 會降級為路徑指標
CODEX_MAX_FILE_BYTES = 32 * 1024
REVIEW_MARKER_RE = re.compile(r"(?:[ \t]+#(?![#]))?[ \t]*<!--\s*review_on:\s*(\d{4}-\d{2}-\d{2})(?:\s+(?:reason:\s*)?(.*?))?\s*-->")


def strip_review_comments(content: str) -> str:
    """剝除規則文字內的 <!-- review_on: YYYY-MM-DD ... --> 治理標記，避免消耗常駐上下文額度。"""
    return REVIEW_MARKER_RE.sub("", content)


def scan_review_markers(paths) -> list[dict]:
    """掃描規則檔清單中的 <!-- review_on: YYYY-MM-DD ... --> 標記，回傳 [{file, line, date, reason}]。"""
    found = []
    for p in paths:
        if not Path(p).is_file():
            continue
        for lineno, line in enumerate(text(Path(p)).splitlines(), 1):
            for m in REVIEW_MARKER_RE.finditer(line):
                found.append({
                    "file": Path(p),
                    "line": lineno,
                    "date": m.group(1),
                    "reason": (m.group(2) or "").strip(),
                })
    return found


def shared_rules_files(data):
    """所有人都套用的共用規則檔（安全底線必列，其餘有才列）。"""
    return [data / "rules" / f for f in SHARED_RULES if f not in OPTIONAL_RULES or (data / "rules" / f).is_file()]


def snoozed_until(state):
    """使用者說「先不要」時記下的暫緩到期日（YYYY-MM-DD）；沒有或壞掉回 None。"""
    try:
        until = json.loads(text(state / ONBOARDING_STATE)).get("snoozed_until")
    except (OSError, ValueError, AttributeError):
        return None
    return until if isinstance(until, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", until) else None


def snooze(state, days=SNOOZE_DAYS, today=None):
    """暫緩開場破冰 days 天，回傳到期日。只記日期；規則要重新接上（apply）才會拿掉，到期後 apply 或
    home_watch 的規則過期偵測會把它接回來。"""
    until = ((today or datetime.now()).date() + timedelta(days=days)).isoformat()
    write(state / ONBOARDING_STATE, json.dumps({"snoozed_until": until}, ensure_ascii=False) + "\n")
    return until


def onboarding_active(state, name, today=None):
    """還沒選過 profile、用的是預設 default，也沒在暫緩期間：開新對話要主動破冰並帶使用者做設定訪談。
    選定任何 profile（含 --set default「不要再提醒」）就關掉；「先不要」暫緩 SNOOZE_DAYS 天（業界的反模式是每次開對話都問）。
    state 是 None（預算棘輪量最大值）時當成開著。"""
    if name != DEFAULT:
        return False
    if state is None:
        return True
    until = snoozed_until(state)
    return chosen(state) is None and not (until and (today or datetime.now()).date().isoformat() < until)


def personal_rules_files(data, state, name):
    """個人層常駐載入的規則檔（AGENTS.md 必列；查表型的 dispatch.md 不常駐載入）；
    還沒選 profile 時再接上 default 的 onboarding.md（開新對話主動破冰、當場接設定訪談）。"""
    base = folder(data, state, name) or data / "profiles" / name
    files = [base / f for f in PROFILE_RULES if f not in OPTIONAL_RULES or (base / f).is_file()]
    if onboarding_active(state, name) and (base / ONBOARDING).is_file():
        files.append(base / ONBOARDING)
    return files


def rules_files(data, state, name):
    """接給 Claude Code 與 Codex 的常駐規則檔，依序：安全底線、分派共用層、個人 AGENTS.md。"""
    return shared_rules_files(data) + personal_rules_files(data, state, name)


def estimate_tokens(content):
    """保守估計規則文字的 token 數（ASCII 約 4 字元 1 token，中日韓等非 ASCII 字元以 1 字 1 token 保守計）。"""
    ascii_chars = sum(1 for ch in content if ord(ch) < 128)
    non_ascii = len(content) - ascii_chars
    return (ascii_chars + 3) // 4 + non_ascii


def check_agy_size(agents_path, agents_content, gemini_path, gemini_content):
    """回傳 Antigravity 兩份規則檔的大小問題清單（空串列代表通過）。"""
    errs = []
    for p, txt in ((agents_path, agents_content), (gemini_path, gemini_content)):
        b = len(txt.encode("utf-8"))
        if b > AGY_MAX_FILE_BYTES:
            errs.append(f"{p} 大小為 {b:,} bytes，超過 Antigravity 單檔上限 {AGY_MAX_FILE_BYTES:,} bytes（會被靜默截斷檔尾）")
    toks = estimate_tokens(agents_content) + estimate_tokens(gemini_content)
    if toks > AGY_MAX_TOTAL_TOKENS:
        errs.append(f"Antigravity 全域規則合計估計約 {toks:,} tokens，超過預算上限 {AGY_MAX_TOTAL_TOKENS:,} tokens（會被降級為路徑指標）")
    return errs


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


def _compose_from(files, data, where=None):
    parts = [strip_review_comments(text(p).replace("\r\n", "\n")).strip() for p in files]
    names = [f"data/rules/{p.name}" if p.parent == data / "rules" else f"{where}/{p.name}" for p in files]
    header = f"{HEADER}{' + '.join(names)} -->"
    return "\n\n".join([header, *parts]) + "\n"


def compose_shared(data):
    """給 Antigravity ~/.gemini/AGENTS.md 的共用層規則。"""
    return _compose_from(shared_rules_files(data), data)


def compose_personal(data, state, name):
    """給 Antigravity ~/.gemini/GEMINI.md 的個人層規則（不含查表型 dispatch.md）。"""
    return _compose_from(personal_rules_files(data, state, name), data, label(data, state, name))


def compose(data, state, name):
    """給 Codex 的合併規則：共用層在前，個人 AGENTS.md 在後；第一行是產生標記。"""
    return _compose_from(rules_files(data, state, name), data, label(data, state, name))


def is_ours(content):
    return content.lstrip().startswith(HEADER)


def connected(state, paths=None, skillshare_config=SKILLSHARE_CONFIG):
    """接上了哪些 agent：優先看 config.json（無帳本同步器）或舊 agents.json；都沒有就從現有受管區塊推斷。"""
    paths = paths or RULES
    for fname in ("config.json", "agents.json"):
        try:
            agents = json.loads(text(state / fname)).get("agents")
            if isinstance(agents, list) and agents:
                return [a for a in agents if a in RULES]
        except (OSError, ValueError, AttributeError):
            pass
    agents = ["claude-code"]
    codex = paths["codex"]
    legacy_ss = skillshare_config.exists() and CODEX_EXTRA.search(text(skillshare_config))
    if legacy_ss or (codex.exists() and (is_ours(text(codex)) or BLOCK.search(text(codex)))):
        agents.append("codex")
    gem = paths.get("antigravity")
    if gem and gem.exists() and BLOCK.search(text(gem)):
        agents.append("antigravity")
    return agents


def import_line(path):
    """Claude Code 的 @import：路徑用正斜線；空白前面要加反斜線，不然路徑在第一個空白就斷掉，
    整份規則不會載入（https://code.claude.com/docs/en/memory）。使用者名稱有空白時，repo 或 profile 的路徑就有空白。"""
    return "@" + path.resolve().as_posix().replace(" ", "\\ ")


def _use_dev_link(state) -> bool:
    if state is None:
        return False
    try:
        return bool(json.loads(text(state / "config.json")).get("dev_link"))
    except (OSError, ValueError, AttributeError):
        return False


def claude_block(data, state, name):
    """Claude 受管區塊：@import 共用層與個人規則，並附一行帶內金絲雀實體文字（倉庫被搬走時 @import 靜默失效，金絲雀仍在）。
    當 dev_link=true 時直接參照開發 repo 的 data；預設（dev_link=false）若 ~/.omnikit/current 存在則參照乾淨副本。"""
    use_current = (
        state is not None
        and not _use_dev_link(state)
        and (state / "current" / "data" / "rules" / "baseline.md").is_file()
        and (data == DATA or (state / "current" / "data") == data)
    )
    shared_src = (state / "current" / "data") if use_current else data
    files = shared_rules_files(shared_src) + personal_rules_files(data, state, name)
    imports = "\n".join(import_line(p) for p in files)
    return f"{BEGIN}\n{CANARY}\n{imports}\n{END}"


def with_block(old, block):
    """換掉受管區塊；沒有就加在開頭。區塊以外的內容與換行都不動。"""
    return BLOCK.sub(lambda _: block, old, count=1) if BLOCK.search(old) else block + "\n" + old


def connect_claude(claude_md, block):
    old = text(claude_md) if claude_md.exists() else ""
    return write(claude_md, with_block(old, block))


def expand_home(value, home):
    return homes.expand_home(value, home)


def claude_homes(home=HOME, environ=None):
    """~/.claude 以外、這台實際在用的 Claude 設定目錄。Claude Code 從 $CLAUDE_CONFIG_DIR/CLAUDE.md 讀使用者規則，
    不會回頭讀 ~/.claude/CLAUDE.md；所以多帳號（例如 T3 Code 每個 Claude 實例一個 homePath）的目錄都要放受管區塊，
    不然那個帳號完全讀不到 OmniKit 規則。怎麼找見 homes.py。"""
    return homes.extra("claude-code", home, environ)


def codex_homes(home=HOME, environ=None):
    """~/.codex 以外、這台實際在用的 Codex 設定目錄（CODEX_HOME）；Codex 從 $CODEX_HOME/AGENTS.md 讀全域規則。"""
    return homes.extra("codex", home, environ)


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


def disconnect_antigravity(gemini_md, agents_md=None):
    """拿掉 Antigravity 兩份全域規則檔（AGENTS.md 共用、GEMINI.md 個人）的受管區塊。"""
    agents_md = agents_md or gemini_md.with_name("AGENTS.md")
    lines = []
    if agents_md.exists() and gemini_md.exists():
        try:
            if os.path.samefile(agents_md, gemini_md):
                retry(agents_md.unlink)
        except OSError:
            pass
    if agents_md != gemini_md:
        lines += disconnect_block(agents_md)
    lines += disconnect_block(gemini_md)
    return lines


def connect_antigravity(gemini_md, shared_content, personal_content, take_over, agents_md=None):
    """將 Antigravity 全域規則拆成 AGENTS.md（共用）與 GEMINI.md（個人），消除硬連結雙重載入並檢查 24,000 bytes 上限。"""
    agents_md = agents_md or gemini_md.with_name("AGENTS.md")
    same_inode = False
    if agents_md.exists() and gemini_md.exists():
        try:
            same_inode = os.path.samefile(agents_md, gemini_md)
        except OSError:
            same_inode = False
    old_gemini = text(gemini_md) if gemini_md.exists() else ""
    if not BLOCK.search(old_gemini) and old_gemini.strip() and not take_over:
        return "skipped", []
    # 若 ~/.gemini/AGENTS.md 與 ~/.gemini/GEMINI.md 先前被硬連結成同一檔，先解除 AGENTS.md 的硬連結（保留 GEMINI.md 對外的硬連結如 ~/.dsh/AGENTS.md）
    if same_inode and agents_md != gemini_md:
        retry(agents_md.unlink)
    old_agents = text(agents_md) if agents_md.exists() else ""
    grab_agents = take_over or bool(BLOCK.search(old_gemini)) or same_inode
    if not BLOCK.search(old_agents) and old_agents.strip() and not grab_agents:
        new_agents = old_agents
        skip_agents = True
    else:
        new_agents = with_block(old_agents, content_block(shared_content))
        skip_agents = False
    new_gemini = with_block(old_gemini, content_block(personal_content))
    errs = check_agy_size(agents_md, new_agents, gemini_md, new_gemini)
    if errs:
        raise SystemExit("Antigravity 規則超過大小上限，已中止寫入以避免靜默截斷：\n" + "\n".join(f"- {e}" for e in errs))
    saved_notes = []
    if not skip_agents and new_agents != old_agents:
        if grab_agents and old_agents.strip() and not BLOCK.search(old_agents):
            saved_a = backup(agents_md)
            saved_notes.append(f"已備份原本的 Antigravity AGENTS.md：{saved_a}")
        write(agents_md, new_agents)
    elif skip_agents:
        saved_notes.append(f"{agents_md} 已有非 OmniKit 內容且未帶受管區塊，沒有覆寫；共用規則未寫入")
    if new_gemini != old_gemini:
        if take_over and old_gemini.strip() and not BLOCK.search(old_gemini):
            saved_g = backup(gemini_md)
            saved_notes.append(f"已備份原本的 Antigravity 規則：{saved_g}")
        write_in_place(gemini_md, new_gemini)
    return ("updated" if (new_agents != old_agents or new_gemini != old_gemini) else "unchanged"), saved_notes
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
            retry(saved.unlink)
            return [f"已拿掉 {path} 的 OmniKit 區塊，還原安裝前的內容"]
        retry(path.unlink)
        return [f"已刪除只剩 OmniKit 區塊的 {path}"]
    write_in_place(path, rest)
    lines = [f"已拿掉 {path} 的 OmniKit 區塊"]
    if saved.exists():
        if saved.read_bytes() == rest.encode("utf-8"):
            retry(saved.unlink)
        else:
            lines.append(f"  安裝前的備份還在：{saved}，需要的話自己合併回去")
    return lines


def apply(data, state, paths=None, wanted=None, agents=None, take_over=False, skillshare_config=SKILLSHARE_CONFIG,
          claude_extra=None, codex_extra=None, new_extra=()):
    """接上 profile，回傳要印給使用者看的訊息。take_over：第一次接上（install），可以接手並備份原本的規則。
    claude_extra、codex_extra：預設目錄以外也要放受管區塊的 CLAUDE.md、AGENTS.md（其他帳號或啟動器的設定目錄，
    見 homes.py）；沒給而且用的是這台的真實路徑（paths 沒給）時，自己找。
    new_extra：這次才找到的其他設定目錄的規則檔，跟 take_over 一樣可以接手（同步時新找到的帳號也要接上）。"""
    if claude_extra is None:
        claude_extra = [h / "CLAUDE.md" for h in claude_homes()] if paths is None else []
    if codex_extra is None:
        codex_extra = [h / "AGENTS.md" for h in codex_homes()] if paths is None else []
    new_extra = {os.path.normcase(str(p)) for p in new_extra}
    paths = paths or RULES
    name, fallback = resolve(data, state, wanted)
    if wanted:
        try:
            import kit as kit_mod

            if (state / "kit.yaml").is_file() or wanted != DEFAULT:
                kit_mod.sync_profile_choice(state, name)
            else:
                write(state / "profile.json", json.dumps({"profile": name}, ensure_ascii=False) + "\n")
        except ImportError:
            write(state / "profile.json", json.dumps({"profile": name}, ensure_ascii=False) + "\n")
    agents = agents if agents is not None else connected(state, paths, skillshare_config)
    content = compose(data, state, name)
    # 給 uninstall.ps1 比對 ~/.codex/AGENTS.md 是不是 OmniKit 的副本
    write(state / "rules" / "AGENTS.md", content)
    done, notes = [], []
    if "claude-code" in agents:
        block = claude_block(data, state, name)
        connect_claude(paths["claude-code"], block)
        for extra in claude_extra:
            connect_claude(extra, block)
        done.append(NAMES["claude-code"] + (f"（另外 {len(claude_extra)} 個設定目錄：{'、'.join(str(p.parent) for p in claude_extra)}）"
                                            if claude_extra else ""))
    if "codex" in agents:
        if len(content.encode("utf-8")) > CODEX_MAX_FILE_BYTES:
            raise SystemExit(f"Codex 規則達 {len(content.encode('utf-8')):,} bytes，超過預設上限 {CODEX_MAX_FILE_BYTES:,} bytes")
        legacy = skillshare_config.exists() and CODEX_EXTRA.search(text(skillshare_config)) is not None
        connected_codex = []
        for path, grab, old_copy in [(paths["codex"], take_over, legacy)] + [
                (p, take_over or os.path.normcase(str(p)) in new_extra, False) for p in codex_extra]:
            status, saved = connect_codex(path, content, grab, old_copy)
            if status == "skipped":
                notes.append(f"{path} 的 OmniKit 區塊被拿掉了，沒有加回去；要接上請重跑 install.ps1")
            else:
                connected_codex.append(path)
            if saved:
                notes.append(f"已備份原本的 Codex 規則：{saved}（原本的規則留在區塊外，照常生效）")
        others = [str(p.parent) for p in connected_codex if p != paths["codex"]]
        if connected_codex:
            done.append(NAMES["codex"] + (f"（另外 {len(others)} 個設定目錄：{'、'.join(others)}）" if others else ""))
    if "antigravity" in agents:
        shared_c = compose_shared(data)
        personal_c = compose_personal(data, state, name)
        agy_agents_md = paths.get("antigravity_shared") or paths["antigravity"].with_name("AGENTS.md")
        status, agy_notes = connect_antigravity(paths["antigravity"], shared_c, personal_c, take_over, agy_agents_md)
        if status != "skipped":
            done.append(NAMES["antigravity"])
        else:
            notes.append(f"{paths['antigravity']} 的 OmniKit 區塊被拿掉了，沒有加回去；要接上請重跑 install.ps1")
        notes.extend(agy_notes)
    lines = [f"已套用 profile：{name}（{'、'.join(done) or '沒有 agent'}，開新的 session 才生效）", *notes]
    if fallback:
        lines.append(fallback_notice(data, state))
    return lines


def sync_skills(run=subprocess.run):
    """換 profile 後重新同步 skills：不同 profile 裝的可能不同（例如不評估工具就不裝 omnikit-eval）。"""
    uv = shutil.which("uv") or str(LOCAL / "Programs" / "uv" / "uv.exe")
    sys.stdout.flush()
    try:
        code = run([uv, "run", "--quiet", str(Path(__file__).resolve().parent / "sync.py"), "sync", "--skills"]).returncode
    except OSError:
        code = None
    return [] if code == 0 else ["skills 沒有跟著 profile 同步，請在 repo 根目錄跑：uv run engine/scripts/sync.py sync --skills"]


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


def stage(src, staging):
    """複製到暫存資料夾，上次中斷留下的先刪掉；被鎖住重試時整個重來。"""
    if staging.exists():
        remove_tree(staging)
    shutil.copytree(src, staging)


def migrate(data, state, tracked=None, reapply=None):
    """把舊版存在 repo 裡的 profile 搬到 repo 外（state/profiles/<名稱>），回傳要印的訊息。
    呼叫前要先取得使用者同意：搬完會刪掉 repo 裡的舊檔。
    - 先複製到暫存資料夾再改名，中途失敗不會留下一半的 profile。防毒掃描剛複製的檔案時，資料夾會暫時改不了名
      （winerror 5），等一下再試。
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
            retry(stage, src, staging)
            retry(staging.replace, dest)
            lines.append(f"profile {name}：已複製到 {dest}")
        moved.append(name)
    if reapply and chosen(state) in moved:
        lines += reapply()
    for name in moved:
        src, dest = data / "profiles" / name, state / "profiles" / name
        if same_files(src, dest):
            retry(remove_tree, src)  # 有檔案被鎖住時，等一下從剩下的接著刪
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
        write(data / "profiles" / "default" / ONBOARDING, "## 第一次使用\n主動破冰\n")
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
        agy_shared = text(paths["antigravity"].with_name("AGENTS.md"))
        check("Antigravity：拆成 AGENTS.md（共用）與 GEMINI.md（個人）兩檔，原本內容保留且不重複載入",
              agy_shared.startswith(BEGIN) and "不碰金鑰" in agy_shared and "保守" not in agy_shared
              and gemini.startswith(BEGIN) and "保守" in gemini and "不碰金鑰" not in gemini
              and gemini.endswith("# 我原本的 Antigravity 規則\n")
              and not os.path.samefile(paths["antigravity"], paths["antigravity"].with_name("AGENTS.md")))
        check("Antigravity：原地改寫 GEMINI.md，外部硬連結（~/.dsh/AGENTS.md）一起更新不斷開",
              os.path.samefile(paths["antigravity"], shared) and text(shared) == gemini)
        check("Antigravity：原本的規則先備份",
              text(paths["antigravity"].with_name("GEMINI.md.pre-omnikit")) == "# 我原本的 Antigravity 規則\n")
        check("訊息列出三個 agent", lines[0].startswith("已套用 profile：default（Claude Code、Codex、Antigravity，"))
        check("沒選過：三家都接上開場破冰（Claude import onboarding.md、Codex 與 Antigravity 個人層含內容）",
              import_line(data / "profiles" / "default" / ONBOARDING) in md
              and codex.index("保守") < codex.index("主動破冰") < codex.index(END)
              and "主動破冰" in gemini and "主動破冰" not in agy_shared)
        day0 = datetime(2026, 11, 27)
        check("先不要：暫緩 7 天，記到期日，期間不破冰、到期當天恢復",
              snooze(state, today=day0) == "2026-12-04" and snoozed_until(state) == "2026-12-04"
              and not onboarding_active(state, DEFAULT, today=datetime(2026, 12, 3))
              and onboarding_active(state, DEFAULT, today=datetime(2026, 12, 4)))
        snooze(state)
        run(agents=all3)
        check("暫緩中重新接上：三家都拿掉破冰",
              ONBOARDING not in text(paths["claude-code"]) and all("主動破冰" not in text(p) for p in paths.values()))
        write(state / ONBOARDING_STATE, '{"snoozed_until": "2000-01-01"}\n')
        run(agents=all3)
        check("暫緩過期再接上：三家都加回破冰", ONBOARDING in text(paths["claude-code"])
              and all("主動破冰" in text(p) for p in (paths["codex"], paths["antigravity"])))
        write(state / ONBOARDING_STATE, "壞掉的檔\n")
        check("暫緩檔壞掉：當成沒暫緩", snoozed_until(state) is None and onboarding_active(state, DEFAULT))
        (state / ONBOARDING_STATE).unlink()

        before = {k: p.read_bytes() for k, p in paths.items()}
        before_agy_shared = paths["antigravity"].with_name("AGENTS.md").read_bytes()
        run(agents=all3)
        check("重複執行：四份規則都不變", all(p.read_bytes() == before[k] for k, p in paths.items())
              and paths["antigravity"].with_name("AGENTS.md").read_bytes() == before_agy_shared)

        run(agents=all3, wanted="x")
        check("--set：記下選擇", chosen(state) == "x")
        check("--set：三邊都換成 x", "/profiles/x/AGENTS.md" in text(paths["claude-code"])
              and "放手" in text(paths["codex"]) and "放手" in text(paths["antigravity"]) and "放手" in text(shared))
        check("--set：不會多出第二份備份", not list(paths["codex"].parent.glob("AGENTS.md.pre-omnikit-*")))
        check("選過之後：不再提醒", not any("還沒選" in line for line in run(agents=all3)))
        check("選了自己的 profile：開場破冰三家都拿掉",
              ONBOARDING not in text(paths["claude-code"]) and all("主動破冰" not in text(p) for p in paths.values()))
        write(paths["codex"], text(paths["codex"]) + "# 之後自己加的\n")
        run(agents=all3, wanted="default")
        codex = text(paths["codex"])
        check("Codex 換 profile：只換區塊，區塊外原本的與之後自己加的都留著",
              "保守" in codex and "放手" not in codex and codex.endswith(END + "\n# 我原本的 Codex 規則\n# 之後自己加的\n"))
        check("明確選 default（不設定、用預設）：不再破冰，也不再提醒還沒選",
              chosen(state) == "default" and ONBOARDING not in text(paths["claude-code"])
              and all("主動破冰" not in text(p) for p in paths.values())
              and onboarding_active(None, DEFAULT) and not onboarding_active(state, DEFAULT)
              and not onboarding_active(None, "x"))
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
        gem_ag = tmp / "g" / "AGENTS.md"
        write(gem, "# 原本\n")
        os.link(gem, gem_ag)  # 模擬舊環境 ~/.gemini/AGENTS.md 與 GEMINI.md 被硬連結成同一個檔
        ext_link = tmp / "g_ext" / "AGENTS.md"
        ext_link.parent.mkdir(parents=True)
        os.link(gem, ext_link)
        connect_antigravity(gem, compose_shared(data), compose_personal(data, state, "default"), take_over=True)
        check("舊環境 AGENTS.md 與 GEMINI.md 硬連結：自動解除同目錄硬連結、拆成兩份，且外部硬連結不斷",
              not os.path.samefile(gem, gem_ag) and os.path.samefile(gem, ext_link)
              and "不碰金鑰" in text(gem_ag) and "保守" in text(gem))
        lines = disconnect_antigravity(gem)
        check("移除 Antigravity 兩檔區塊：GEMINI.md 還原原本內容且外部硬連結還在，只剩區塊的 AGENTS.md 刪除",
              text(gem) == "# 原本\n" and not gem_ag.exists() and os.path.samefile(gem, ext_link)
              and any("已拿掉" in line for line in lines))
        check("移除後跟備份一樣：多餘的備份刪掉", not gem.with_name("GEMINI.md.pre-omnikit").exists())
        fresh = tmp / "f" / "GEMINI.md"
        connect_antigravity(fresh, compose_shared(data), compose_personal(data, state, "default"), take_over=True)
        disconnect_antigravity(fresh)
        check("OmniKit 建的 AGENTS.md 與 GEMINI.md：移除時兩個都刪掉", not fresh.exists() and not fresh.with_name("AGENTS.md").exists())
        oversize = tmp / "over" / "GEMINI.md"
        check("Antigravity 單檔超過 24,000 bytes 時拒絕寫入並報錯（防靜默截斷）",
              fails(lambda: connect_antigravity(oversize, "# 共用\n", "超長規則\n" * 2000, take_over=True))
              and not oversize.exists())

        # 防毒短暫鎖住檔案（FR-34，假的鎖檔）：寫入、原地改寫、備份都等一下再試；硬連結照樣不斷
        locked_md = tmp / "lock" / "GEMINI.md"
        with flaky(Path, "write_bytes", times=2, match=lambda p, *_: p == locked_md) as st:
            changed = write(locked_md, "# 新的\n")
        check("write：被鎖住兩次，每次等久一點，之後寫進去", changed and text(locked_md) == "# 新的\n"
              and st.calls == 3 and st.waits == [0.25, 0.5])
        linked = tmp / "lock" / "AGENTS.md"
        os.link(locked_md, linked)
        with flaky(sys.modules[__name__], "overwrite", times=2) as st:
            write_in_place(locked_md, "# 原地改寫\n")
        check("write_in_place：被鎖住時等一下再試，原地改寫，硬連結的其他名字一起更新",
              st.calls == 3 and text(linked) == "# 原地改寫\n" and os.path.samefile(locked_md, linked))
        with flaky(shutil, "copyfile", times=1, match=lambda s, *_, **__: Path(s) == locked_md) as st:
            saved = backup(locked_md)
        check("backup：被鎖住時等一下再試，備份的內容一樣", st.calls == 2 and text(saved) == "# 原地改寫\n")

        calls = []

        def fake_run(code):
            def run_(cmd):
                calls.append(cmd)
                if code is None:
                    raise OSError("找不到 uv")
                return subprocess.CompletedProcess(cmd, code)
            return run_

        check("換 profile 後同步 skills：交給 sync.py sync --skills",
              sync_skills(fake_run(0)) == [] and calls[-1][-3:] == [str(Path(__file__).resolve().parent / "sync.py"), "sync", "--skills"])
        check("skills 同步失敗：印出手動指令", "sync.py sync --skills" in sync_skills(fake_run(1))[0])
        check("找不到 uv：印出手動指令，不中斷", "sync.py sync --skills" in sync_skills(fake_run(None))[0])

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

        # 其他 Claude 設定目錄：CLAUDE_CONFIG_DIR 與 T3 Code 的 Claude 實例 homePath
        chome = tmp / "chome"
        for d in (".claude", ".claude-kai", ".claude-retis", "env-claude"):
            (chome / d).mkdir(parents=True)
        t3 = chome / ".t3" / "userdata" / "settings.json"
        write(t3, json.dumps({"providerInstances": {
            "claudeAgent": {"driver": "claudeAgent"},
            "kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
            "retis": {"driver": "claudeAgent", "config": {"homePath": str(chome / ".claude-retis")}},
            "same": {"driver": "claudeAgent", "config": {"homePath": "~/.claude"}},
            "gone": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-gone"}},
            "agy": {"driver": "antigravity", "config": {"homePath": "~/.claude-agy"}}}}))
        found = claude_homes(chome, {"CLAUDE_CONFIG_DIR": str(chome / "env-claude")})
        check("claude_homes：CLAUDE_CONFIG_DIR 與 T3 的 Claude 實例都找到；~/.claude、不存在的、非 Claude 的不算",
              [h.name for h in found] == ["env-claude", ".claude-kai", ".claude-retis"])
        check("claude_homes：沒有 T3 設定也沒有環境變數就是空的", claude_homes(tmp / "nohome", {}) == [])
        write(t3, "{壞掉")
        check("claude_homes：T3 設定壞掉不會失敗", claude_homes(chome, {}) == [])
        extra = [h / "CLAUDE.md" for h in found]
        write(extra[1], "# Kai 自己的規則\n")
        lines = apply(data, state, paths, agents=["claude-code"], claude_extra=extra, skillshare_config=legacy_config)
        block = claude_block(data, state, chosen(state) or DEFAULT)
        check("其他 Claude 設定目錄也放同一個受管區塊，原本的內容留著",
              all(text(p).startswith(block) for p in extra) and text(extra[1]).endswith("# Kai 自己的規則\n")
              and "另外 3 個設定目錄" in lines[0])
        check("其他 Claude 設定目錄：拿掉區塊時，只剩區塊的刪掉、有自己內容的留著",
              bool(disconnect_block(extra[0])) and not extra[0].exists()
              and bool(disconnect_block(extra[1])) and text(extra[1]) == "# Kai 自己的規則\n")

        # 其他 Codex 設定目錄（CODEX_HOME）：同步時區塊被拿掉的不加回去；這次才找到的可以接手，原本的先備份
        cx_old, cx_new = chome / "cx-old" / "AGENTS.md", chome / "cx-new" / "AGENTS.md"
        write(cx_old, "# 我自己的 Codex 規則\n")
        write(cx_new, "# 新帳號原本的規則\n")
        lines = apply(data, state, paths, agents=["codex"], codex_extra=[cx_old, cx_new], new_extra=[cx_new],
                      skillshare_config=legacy_config)
        check("其他 Codex 設定目錄：舊的沒區塊就不碰並提醒；新找到的接手並備份",
              text(cx_old) == "# 我自己的 Codex 規則\n" and any(str(cx_old) in n for n in lines)
              and BLOCK.search(text(cx_new)) is not None and text(cx_new).endswith("# 新帳號原本的規則\n")
              and (cx_new.parent / "AGENTS.md.pre-omnikit").exists()
              and f"另外 1 個設定目錄：{cx_new.parent}" in lines[0])

        # Claude Code 的 import 遇到空白就斷掉：使用者名稱有空白時，repo 與 profile 的路徑都有空白
        sdata, sstate = tmp / "王 小明 的 資料夾" / "data", tmp / "王 小明 的 資料夾" / "state"
        write(sdata / "rules" / "baseline.md", "# 底線\n")
        write(sstate / "profiles" / "amy" / "AGENTS.md", "# amy\n")
        imports = [line for line in claude_block(sdata, sstate, "amy").splitlines() if line.startswith("@")]
        check("Claude import：路徑的空白都用反斜線跳脫，還原後就是原本的路徑",
              len(imports) == 2 and not any(re.search(r"(?<!\\) ", line) for line in imports)
              and [line[1:].replace("\\ ", " ") for line in imports]
              == [p.resolve().as_posix() for p in rules_files(sdata, sstate, "amy")])

        # 子任務分派：共用層 data/rules/dispatch.md 有才接；個人層 dispatch.md 屬於查表設定，移出常駐載入規則（Step 1.3）
        write(sdata / "rules" / "dispatch.md", "# 分派共用\n")
        check("分派：共用層接在底線之後、profile 之前",
              [p.name for p in rules_files(sdata, sstate, "amy")] == ["baseline.md", "dispatch.md", "AGENTS.md"])
        write(sstate / "profiles" / "amy" / "dispatch.md", "# amy 的實例（查表，不常駐載入）\n")
        files = rules_files(sdata, sstate, "amy")
        merged = compose(sdata, sstate, "amy")
        check("分派：個人層 dispatch.md 移出常駐規則（不進 Claude import 與 Codex/Antigravity 常駐區塊）",
              [p.parent.name + "/" + p.name for p in files]
              == ["rules/baseline.md", "rules/dispatch.md", "amy/AGENTS.md"]
              and len([x for x in claude_block(sdata, sstate, "amy").splitlines() if x.startswith("@")]) == 3
              and "# amy 的實例" not in merged
              and merged.index("# 底線") < merged.index("# 分派共用") < merged.index("# amy\n"))
        # 行動端與 WebApp 底線已於 2026-11-26 移出常駐（轉為 omnikit-mobile-web 按需 skill），即使舊檔存在也不載入常駐；
        # 同時驗證 <!-- review_on: ... --> 標記可被掃描且於組合常駐文字時自動剝除。
        write(sdata / "rules" / "mobile-web.md", "# 行動端舊檔\n")
        write(sstate / "profiles" / "amy" / "AGENTS.md", "# amy\n暫定規則<!-- review_on: 2026-12-01 reason: 測試到期 -->\n")
        markers = scan_review_markers([sstate / "profiles" / "amy" / "AGENTS.md"])
        composed_amy = compose(sdata, sstate, "amy")
        check("行動端移出常駐且 review_on 註解自動剝除：mobile-web.md 不進 rules_files，review_on 可掃描但不進常駐區塊",
              [p.name for p in rules_files(sdata, sstate, "amy")] == ["baseline.md", "dispatch.md", "AGENTS.md"]
              and "# 行動端舊檔" not in composed_amy
              and "review_on" not in composed_amy
              and "暫定規則\n" in composed_amy
              and len(markers) == 1 and markers[0]["date"] == "2026-12-01" and markers[0]["reason"] == "測試到期")
        (sdata / "rules" / "mobile-web.md").unlink()

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
        # 搬的時候遇到防毒短暫鎖住（FR-34，假的鎖檔）：剛複製好的資料夾改不了名、repo 裡的舊檔刪不掉
        with flaky(Path, "replace", times=2, match=lambda p, *_: p.name == ".bob.migrating") as renamed, \
                flaky(shutil, "rmtree", times=1, match=lambda p, *_, **__: Path(p) == bob) as removed:
            out = mcli(interactive=True, ask=lambda _: "y")
        check("同意後：整個資料夾（含 .bak）搬到 repo 外，repo 裡的舊檔刪掉",
              not bob.exists() and text(moved / "AGENTS.md.bak") == "# bob 更早的\n"
              and json.loads(text(moved / "answers.json")) == {"name": "bob"}
              and any("已刪掉 repo 裡的舊檔" in line for line in out))
        check("搬的時候被防毒短暫鎖住（改名、刪舊檔）：等一下再試，照樣搬好",
              renamed.calls == 3 and removed.calls == 2 and not (mstate / "profiles" / ".bob.migrating").exists())
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
    if not args.show:
        for line in statedir.migrate(STATE).lines():  # 舊位置（%LOCALAPPDATA%\omnikit）的狀態先搬過來
            print(line)
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
