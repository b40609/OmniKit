# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把 OmniKit 的 ACP 轉接程式（acp_shim.py）接到 T3 Code 的 Antigravity 實例，讓它們讀得到 OmniKit 規則。

為什麼要轉接見 acp_shim.py：T3 Code 用 ACP 模式跑 Antigravity，server 不讀 ~/.gemini/GEMINI.md，
只能在開新對話時由 client 帶入；轉接程式站在 T3 與 server 中間帶入規則。

agents.py connect 與 sync 呼叫這裡（只在 Windows；T3 Code 在其他系統的執行方式沒實測）：
1. ~/.omnikit/acp/ 放三個檔（見下面「為什麼放這裡」）：
   - acp_shim.py：engine/scripts/acp_shim.py 的複本，內容變了才換（T3 每開一段對話讀一次，repo 搬家或切分支不影響）
   - omnikit-acp.cmd：用 uv 跑旁邊的 acp_shim.py。uv 寫絕對路徑；cmd 用 OEM 編碼讀 .cmd，
     路徑有編不進去的字就只寫 uv，靠 PATH 找
   - localharness_external.exe：空檔。T3 收自訂執行檔的條件是旁邊要有這個檔，或檔名是 agy；
     檔名是 agy 的話 T3 會把完全存取與自動接受修改的模式降成 default，所以走旁邊放檔這條路。
     T3 會把它的路徑傳給 server，轉接程式換成 T3 自己裝的那一份，這個空檔不會被執行
2. ~/.t3/userdata/settings.json 裡每個 Antigravity 實例的 config.binaryPath（T3 設定頁的 Binary path）
   設成 omnikit-acp.cmd：只改沒設的、或已經是 OmniKit 的；使用者自己設了別的就不動，列出來。
   T3 自己補的預設實例（id 是 antigravity，settings.json 沒列）也寫一筆進去；T3 還沒存過設定（沒有
   settings.json）就新建一個只有這筆的（T3 本來就只存跟預設不同的欄位）。
   T3 監看這個檔，存檔後重建那個實例：那個實例開著的 Antigravity 對話會斷一次，新的對話起經過轉接程式。
   寫法跟 T3 一樣（JSON、兩格縮排、結尾換行），寫前比對沒被改過，先寫暫存檔再整個換上：T3 讀到寫一半的檔
   會當成設定壞掉、整份改用預設（所有實例重建），所以換不上（T3 鎖著）就這次不寫，下次 sync 再試
3. disconnect：binaryPath 還是 OmniKit 的就拿掉（T3 回到自動選），刪掉 acp 資料夾裡 OmniKit 放的檔；
   設定沒改回來就先不刪（刪了那些實例會開不了）

為什麼放這裡、不放 %LOCALAPPDATA%：從 MSIX 封裝的 app（例如 Claude 桌面版）裡跑 OmniKit 時，Windows 會把 AppData 底下新建的檔
轉存到那個 app 的私人位置（AppData\\Local\\Packages\\<app>\\LocalCache），T3 看不到，會說自訂執行檔不存在
（2026-11-18 實際發生）。家目錄底下的 .omnikit 不在 AppData，誰寫的大家都看得到。

T3 0.1.11-nightly.20261120.4979 起（上游 PR 39531）Antigravity 原生讀全域的 AGENTS.md 與 GEMINI.md，
轉接程式停用：T3 是這個版本以上時，connect 與 sync 不再寫 binaryPath，改做 disconnect 那一步
（拿掉 OmniKit 寫的 binaryPath、刪掉轉接程式的檔），state 回報 native。T3 版本用 `t3 --version` 讀，
讀不到就照舊接轉接程式。

之後在 T3 新增的實例，下一次 sync 就接上（home_watch.py 在開新的 Claude Code 對話時發現就在背景跑 sync）。

用法：uv run engine/scripts/t3_acp.py            列出每個實例接上了沒有
      uv run engine/scripts/t3_acp.py --selftest
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fsretry  # noqa: E402
import homes  # noqa: E402
from fsretry import retry  # noqa: E402  防毒短暫鎖住檔案時等一下再試

SHIM, LAUNCHER, PLACEHOLDER = "acp_shim.py", "omnikit-acp.cmd", "localharness_external.exe"
LOGS = ("shim.log", "shim.log.old")
SOURCE = Path(__file__).resolve().with_name(SHIM)
DRIVER = "antigravity"
OK, MISSING, CUSTOM, BROKEN, UNSUPPORTED, NATIVE = "ok", "missing", "custom", "broken", "unsupported", "native"
NATIVE_SINCE = (0, 1, 11, 20261120, 4979)  # T3 從這版起原生讀 AGENTS.md 與 GEMINI.md（PR 39531），轉接程式停用


def parse_version(text):
    """`t3 --version` 的輸出 → 可比大小的 tuple。nightly 是 (a, b, c, 日期, 編號)；正式版沒有 nightly 尾巴，
    當成排在同版號所有 nightly 之後。看不懂回 None。"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:-nightly\.(\d+)\.(\d+))?", text or "")
    if not m:
        return None
    a, b, c, d, n = m.groups()
    return (int(a), int(b), int(c), int(d) if d else 99999999, int(n) if n else 0)


def t3_version():
    """本機 T3 的版本（parse_version 的結果）；找不到 t3 或跑不起來回 None。"""
    exe = shutil.which("t3") or shutil.which("t3.cmd")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20,
                             stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_version(out.stdout + out.stderr)


def native(version=None):
    """T3 是不是已經原生讀規則（不需要轉接程式）。version 不給就問 t3。"""
    v = t3_version() if version is None else version
    return v is not None and v >= NATIVE_SINCE


def acp_dir(home):
    """轉接程式的資料夾：~/.omnikit/acp（不放 %LOCALAPPDATA%，原因見最上面）。"""
    return home / ".omnikit" / "acp"


def settings_file(home):
    return home / ".t3" / "userdata" / "settings.json"


def instance_key(home, iid):
    """跟 homes.discover 找到的 T3 Antigravity 實例同一個 key（agents.json 的 homes 用它）。"""
    return homes.key("antigravity", homes.canonical(homes.t3_antigravity_dir(home, iid)))


def instances(home):
    return [iid for iid, inst in homes.t3_instances(home).items() if isinstance(inst, dict) and inst.get("driver") == DRIVER]


def oem_codepage():
    try:
        import ctypes
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except (ImportError, AttributeError, OSError):
        return "ascii"


def launcher_bytes(uv, codepage=None):
    """omnikit-acp.cmd 的內容：先用寫進去的 uv 絕對路徑，那裡沒有（搬走了，或是在 MSIX 封裝的 app 裡裝的、
    T3 看不到）就用 PATH 上的 uv。cmd 照 OEM 編碼讀 .cmd，路徑編不進去就只用 PATH 上的。
    --no-project --no-config：uv 會從 acp_shim.py 的資料夾往上找 pyproject.toml、uv.toml（例如家目錄裡的），
    那裡的設定寫壞或指定別的 Python 就啟動不了（2026-11-18 實測：上層有壞掉的 uv.toml，不加就失敗）。"""
    codepage = codepage or oem_codepage()
    exe = uv or "uv"
    try:
        exe.encode(codepage)
    except (UnicodeEncodeError, LookupError):
        exe = "uv"
    # 註解只用 ASCII：雙位元組字的第二個位元組可能是 | 或 ^，cmd 用別的編碼讀到就會誤解
    lines = ["@echo off", "setlocal", "rem OmniKit ACP shim for T3 Code Antigravity (written by engine/scripts/t3_acp.py)"]
    if exe != "uv":  # .cmd 裡的 % 是變數，路徑本身有 % 要寫成 %%
        lines += [f'set "OMNIKIT_UV={exe.replace("%", "%%")}"', 'if not exist "%OMNIKIT_UV%" set "OMNIKIT_UV=uv"']
    else:
        lines += ['set "OMNIKIT_UV=uv"']
    lines += [f'"%OMNIKIT_UV%" run --quiet --no-project --no-config --script "%~dp0{SHIM}" %*']
    text = "\r\n".join(lines) + "\r\n"
    return text.encode(codepage) if exe != "uv" else text.encode("ascii")


def same_path(a, b):
    try:
        return os.path.normcase(os.path.abspath(os.path.expandvars(str(a)))) == os.path.normcase(os.path.abspath(str(b)))
    except (TypeError, ValueError):
        return False


def binary_of(inst):
    config = inst.get("config")
    return config.get("binaryPath") if isinstance(config, dict) else None


def current(real):
    """settings.json 現在的 bytes；還沒有這個檔是 None（T3 還沒存過設定）。"""
    try:
        return retry(real.read_bytes)
    except FileNotFoundError:
        return None


def read_settings(home):
    """（實際的檔案, 原本的 bytes 或 None, 內容）。settings.json 可能是連結，寫的時候寫到它指的檔。"""
    real = settings_file(home).resolve()
    raw = current(real)
    doc = {} if raw is None else json.loads(raw.decode("utf-8-sig"))
    if not isinstance(doc, dict):
        raise ValueError("settings.json 不是 JSON 物件")
    return real, raw, doc


class Changed(Exception):
    """讀了之後、寫之前，settings.json 被改過（T3 或使用者剛好也在改）。"""


def write_settings(real, raw, doc):
    """寫回 settings.json。讀了之後檔案被改過就丟 Changed，不蓋掉別人的修改（呼叫的地方重讀再試）。
    換不上（T3 鎖著，等過還是不行）就丟 PermissionError，不原地覆寫（原因見最上面）。"""
    if current(real) != raw:
        raise Changed()
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if raw and b"\r\n" in raw:
        text = text.replace("\n", "\r\n")
    tmp = real.with_name(real.name + ".omnikit-tmp")
    try:
        retry(tmp.write_bytes, text.encode("utf-8"))
        retry(os.replace, tmp, real)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def place(folder, uv):
    """放轉接程式的三個檔；回傳有換的檔名。"""
    folder.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, data in ((SHIM, SOURCE.read_bytes()), (LAUNCHER, launcher_bytes(uv))):
        path = folder / name
        if not path.exists() or retry(path.read_bytes) != data:
            retry(path.write_bytes, data)
            changed.append(name)
    if not (folder / PLACEHOLDER).is_file():
        retry((folder / PLACEHOLDER).write_bytes, b"")
        changed.append(PLACEHOLDER)
    return changed


def state(home, folder, platform=sys.platform, is_native=None):
    """每個 Antigravity 實例：{實例 id: (狀態, 說明)}。狀態：ok、missing（沒設）、custom（使用者自己設的）、
    broken（設了轉接程式但檔案不全）、unsupported（不是 Windows）、native（T3 原生讀規則，不用轉接程式）。"""
    if is_native is None:
        is_native = native()
    launcher = folder / LAUNCHER
    files_ok = all((folder / n).is_file() for n in (SHIM, LAUNCHER, PLACEHOLDER))
    out = {}
    for iid, inst in homes.t3_instances(home).items():
        if not isinstance(inst, dict) or inst.get("driver") != DRIVER:
            continue
        value = binary_of(inst)
        if is_native:
            leftover = isinstance(value, str) and value.strip() and same_path(value, launcher)
            out[iid] = (BROKEN, "T3 已原生讀規則，但 Binary path 還指著停用的轉接程式：跑 uv run engine/scripts/agents.py sync")                 if leftover else (NATIVE, "T3 原生讀 AGENTS.md 與 GEMINI.md（0.1.11-nightly.20261120.4979 起），不用轉接程式")
        elif platform != "win32":
            out[iid] = (UNSUPPORTED, "轉接程式目前只支援 Windows，這個實例讀不到 OmniKit 規則")
        elif isinstance(value, str) and value.strip() and same_path(value, launcher):
            out[iid] = (OK, "Binary path 是 OmniKit 的轉接程式") if files_ok else \
                (BROKEN, f"Binary path 指到轉接程式，但 {folder} 裡的檔不全：跑 uv run engine/scripts/agents.py sync")
        elif isinstance(value, str) and value.strip():
            out[iid] = (CUSTOM, f"Binary path 是你自己設的（{value}），OmniKit 沒有改；這個實例讀不到 OmniKit 規則")
        else:
            out[iid] = (MISSING, "Binary path 還沒設成轉接程式：跑 uv run engine/scripts/agents.py sync")
    return out


def point(home, launcher, ids):
    """讀 settings.json，把沒設的實例指到轉接程式並寫回。回傳（改了的, [(使用者自己設的, 值)]）。"""
    real, raw, doc = read_settings(home)
    insts = doc.setdefault("providerInstances", {})
    if not isinstance(insts, dict):
        raise ValueError("settings.json 的 providerInstances 不是 JSON 物件")
    pointed, custom = [], []
    for iid in ids:
        if iid not in insts and iid == homes.T3_DEFAULT_ANTIGRAVITY:  # T3 自己補的預設實例：寫一筆出來才能設
            insts[iid] = {"driver": DRIVER}
        inst = insts.get(iid)
        if not isinstance(inst, dict) or inst.get("driver") != DRIVER:  # 剛被刪掉或改掉
            continue
        value, config = binary_of(inst), inst.get("config")
        if config is not None and not isinstance(config, dict):
            custom.append((iid, "config 的格式看不懂"))
        elif value is None or (isinstance(value, str) and not value.strip()):
            inst["config"] = {**(config or {}), "binaryPath": str(launcher)}
            pointed.append(iid)
        elif not (isinstance(value, str) and same_path(value, launcher)):
            custom.append((iid, value))
    if pointed:
        write_settings(real, raw, doc)
    return pointed, custom


def apply(home, folder, uv, platform=sys.platform, is_native=None):
    """接上 T3 的每個 Antigravity 實例。回傳（訊息, 處理過的實例 key）；使用者自己設了 Binary path 的也算處理過
    （記在 agents.json 的 homes，home_watch 不會一直重試），doctor 會列出來。"""
    ids = instances(home)
    if not ids:
        return [], []
    keys = [instance_key(home, iid) for iid in ids]
    if is_native is None:
        is_native = native()
    if is_native:  # 轉接程式停用：OmniKit 寫過的 binaryPath 拿掉、檔刪掉
        return remove(home, folder), keys
    if platform != "win32":
        return ["T3 Code 的 Antigravity：轉接程式目前只支援 Windows，這台的實例讀不到 OmniKit 規則"], keys
    lines = []
    changed = place(folder, uv)
    if changed:
        lines.append(f"T3 Code 的 Antigravity：轉接程式放在 {folder}（{'、'.join(changed)}）")
    for _ in range(3):
        try:
            pointed, custom = point(home, folder / LAUNCHER, ids)
            break
        except Changed:
            continue
        except PermissionError as e:
            return lines + [f"T3 Code 的 Antigravity：T3 鎖著設定檔（{e}），這次沒設 Binary path，下次 sync 再試"], keys
    else:
        return lines + ["T3 Code 的 Antigravity：T3 一直在改設定檔，這次沒設 Binary path，下次 sync 再試"], keys
    if pointed:
        lines.append(f"T3 Code 的 Antigravity：{'、'.join(pointed)} 的 Binary path 設成轉接程式，新的對話起讀得到 OmniKit 規則")
    for iid, value in custom:
        lines.append(f"T3 Code 的 Antigravity：{iid} 的 Binary path 是你自己設的（{value}），沒有改；這個實例讀不到 OmniKit 規則")
    return lines, keys


def unpoint(home, launcher):
    """還指到轉接程式的 binaryPath 拿掉（只剩它的話 config 也拿掉）並寫回；回傳改了的實例。"""
    real, raw, doc = read_settings(home)
    restored = []
    insts = doc.get("providerInstances") or {}
    for iid, inst in (insts.items() if isinstance(insts, dict) else ()):
        value = binary_of(inst) if isinstance(inst, dict) and inst.get("driver") == DRIVER else None
        if isinstance(value, str) and same_path(value, launcher):
            del inst["config"]["binaryPath"]
            if not inst["config"]:
                del inst["config"]
            restored.append(iid)
    if restored:
        write_settings(real, raw, doc)
    return restored


def remove(home, folder):
    """disconnect：還指到轉接程式的 binaryPath 拿掉（T3 回到自動選），刪掉轉接程式的檔。"""
    lines = []
    launcher = folder / LAUNCHER
    if settings_file(home).is_file():
        restored, problem = None, "T3 一直在改設定檔"
        for _ in range(3):
            try:
                restored = unpoint(home, launcher)
                break
            except Changed:
                continue
            except (OSError, ValueError) as e:
                problem = f"讀不到或寫不回 settings.json（{e}）"
                break
        if restored is None:
            # 沒改回來就不刪檔：還指著轉接程式的實例，檔刪了會開不了
            return [f"T3 Code：{problem}，Antigravity 實例的 Binary path 沒有改回來，轉接程式先留在 {folder}；"
                    f"到 T3 設定把 Antigravity 的 Binary path 清空，再刪掉 {folder}"]
        if restored:
            lines.append(f"T3 Code 的 Antigravity：{'、'.join(restored)} 的 Binary path 拿掉，回到 T3 自動選")
    gone, busy = [], []
    for name in (SHIM, LAUNCHER, PLACEHOLDER, *LOGS):
        path = folder / name
        if path.exists():
            try:
                retry(path.unlink)
                gone.append(name)
            except OSError:
                busy.append(name)
    try:
        folder.rmdir()
    except OSError:
        pass
    if gone:
        lines.append(f"T3 Code 的 Antigravity：從 {folder} 刪掉轉接程式（{'、'.join(gone)}）")
    if busy:
        lines.append(f"T3 Code 的 Antigravity：{'、'.join(busy)} 還在用（T3 的對話開著），關掉 T3 後刪掉 {folder}")
    return lines


def selftest():
    fails = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            fails.append(name)

    global t3_version
    real_version, t3_version = t3_version, lambda: None  # 下面舊路徑的測試當成舊版 T3
    check("版本：nightly 4979 以上原生、以下不是、正式版 0.1.11 算原生",
          native(parse_version("t3 v0.1.11-nightly.20261120.4979")) and native(parse_version("0.1.12"))
          and native(parse_version("0.1.11")) and not native(parse_version("t3 v0.1.11-nightly.20261120.4978"))
          and not native(parse_version("0.1.11-nightly.20261119.9999")) and parse_version("hello") is None
          and not native(None))
    with tempfile.TemporaryDirectory() as t:
        home, folder = Path(t) / "home", Path(t) / "state" / "acp"
        check("沒有 T3：什麼都不做", apply(home, folder, "uv") == ([], []) and not folder.exists())
        settings = settings_file(home)
        settings.parent.mkdir(parents=True)
        mine = str(Path(t) / "my-agy.exe")
        doc = {"favorites": [], "providerInstances": {
            "antigravity": {"displayName": "ryan", "driver": "antigravity", "enabled": True},
            "antigravity_kai": {"driver": "antigravity", "config": {"authMethod": "oauth-personal", "binaryPath": ""}},
            "antigravity_mine": {"driver": "antigravity", "config": {"binaryPath": mine}},
            "claudeAgent": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}}}}
        original = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        settings.write_bytes(original.encode("utf-8"))
        lines, keys = apply(home, folder, r"C:\Tools\uv.exe", platform="win32")
        after = json.loads(settings.read_text(encoding="utf-8"))["providerInstances"]
        launcher = str(folder / LAUNCHER)
        check("沒設的實例：Binary path 設成轉接程式；其他 config 欄位留著",
              after["antigravity"]["config"] == {"binaryPath": launcher}
              and after["antigravity_kai"]["config"] == {"authMethod": "oauth-personal", "binaryPath": launcher})
        check("使用者自己設的不動，列出來；其他 driver 不動",
              after["antigravity_mine"]["config"]["binaryPath"] == mine and after["claudeAgent"] == doc["providerInstances"]["claudeAgent"]
              and any("antigravity_mine" in line and "沒有改" in line for line in lines))
        check("三個實例都算處理過；key 跟 homes.discover 一樣",
              keys == [instance_key(home, i) for i in ("antigravity", "antigravity_kai", "antigravity_mine")]
              and all(k.startswith("antigravity@") for k in keys))
        check("轉接程式三個檔都放好；啟動檔用 uv 的絕對路徑、跑旁邊的 acp_shim.py",
              (folder / SHIM).read_bytes() == SOURCE.read_bytes() and (folder / PLACEHOLDER).read_bytes() == b""
              and b'set "OMNIKIT_UV=C:\\Tools\\uv.exe"\r\nif not exist "%OMNIKIT_UV%" set "OMNIKIT_UV=uv"\r\n'
              b'"%OMNIKIT_UV%" run --quiet --no-project --no-config --script "%~dp0acp_shim.py" %*\r\n'
              in (folder / LAUNCHER).read_bytes())
        check("uv 的路徑有 %：寫成 %%（.cmd 裡 % 是變數）", b'set "OMNIKIT_UV=C:\\a%%b\\uv.exe"' in launcher_bytes("C:\\a%b\\uv.exe", "ascii"))
        check("寫法跟 T3 一樣：兩格縮排、結尾換行、沒有 BOM",
              settings.read_bytes().startswith(b'{\n  "favorites"') and settings.read_bytes().endswith(b"}\n")
              and not (settings.parent / "settings.json.omnikit-tmp").exists())
        before = settings.read_bytes()
        lines, _ = apply(home, folder, r"C:\Tools\uv.exe", platform="win32")
        check("再跑一次：沒變就不寫，只回報使用者自己設的", settings.read_bytes() == before
              and lines == [line for line in lines if "antigravity_mine" in line])
        real_replace, real_sleep = os.replace, fsretry.sleep

        def locked_replace(*_):
            raise PermissionError(5, "存取被拒")

        os.replace, fsretry.sleep = locked_replace, lambda _: None
        try:
            unlocked = settings.read_bytes()
            raised = _raises(lambda: write_settings(settings, unlocked, {**json.loads(unlocked), "x": 1}), PermissionError)
            locked_doc = json.loads(unlocked)
            locked_doc["providerInstances"]["antigravity"].pop("config")
            settings.write_bytes((json.dumps(locked_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            locked_bytes = settings.read_bytes()
            lines, _ = apply(home, folder, r"C:\Tools\uv.exe", platform="win32")
        finally:
            os.replace, fsretry.sleep = real_replace, real_sleep
        check("T3 鎖著設定檔不讓換掉：不原地覆寫（T3 讀到一半會整份改用預設），設定不動、暫存檔清掉、說下次再試",
              raised and settings.read_bytes() == locked_bytes and any("鎖著設定檔" in line for line in lines)
              and not (settings.parent / "settings.json.omnikit-tmp").exists())
        settings.write_bytes(before)
        st = state(home, folder, platform="win32")
        check("state：OmniKit 的 ok、自己設的 custom；不是 Windows 是 unsupported",
              st["antigravity"][0] == OK and st["antigravity_kai"][0] == OK and st["antigravity_mine"][0] == CUSTOM
              and {s for s, _ in state(home, folder, platform="linux").values()} == {UNSUPPORTED})
        (folder / PLACEHOLDER).unlink()
        check("state：檔案不全就是 broken", state(home, folder, platform="win32")["antigravity"][0] == BROKEN)
        check("路徑編不進 OEM 編碼：只用 PATH 上的 uv", b'set "OMNIKIT_UV=uv"' in launcher_bytes("C:\\使用者\\uv.exe", "ascii")
              and "使用者".encode("utf-8") not in launcher_bytes("C:\\使用者\\uv.exe", "ascii"))
        sneaky = json.loads(settings.read_text(encoding="utf-8"))
        real_read = Path.read_bytes
        calls = []

        def racing_read(self):
            data = real_read(self)
            if self.name == "settings.json":
                calls.append(1)
                if len(calls) == 1:  # OmniKit 讀完之後、寫之前，T3 剛好改了設定
                    self.write_bytes(data.replace(b'"favorites": []', b'"favorites": ["t3"]'))
            return data

        sneaky["providerInstances"]["antigravity"].pop("config")
        settings.write_bytes((json.dumps(sneaky, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        Path.read_bytes = racing_read
        try:
            apply(home, folder, r"C:\Tools\uv.exe", platform="win32")
        finally:
            Path.read_bytes = real_read
        after = json.loads(settings.read_text(encoding="utf-8"))
        check("寫之前 T3 剛好改了設定：重讀再寫，T3 的修改留著",
              after["favorites"] == ["t3"] and after["providerInstances"]["antigravity"]["config"]["binaryPath"] == launcher)
        check("其他系統：不放檔、不改設定，說明原因", apply(home, Path(t) / "other", "uv", platform="linux")[0][0].startswith("T3 Code")
              and not (Path(t) / "other").exists())
        (folder / "shim.log").write_text("x", encoding="utf-8")
        os.replace, fsretry.sleep = locked_replace, lambda _: None
        try:
            lines = remove(home, folder)
        finally:
            os.replace, fsretry.sleep = real_replace, real_sleep
        check("disconnect 時設定寫不回去：轉接程式的檔留著（還指著它的實例才開得了），說怎麼手動改",
              (folder / LAUNCHER).is_file() and len(lines) == 1 and "清空" in lines[0]
              and json.loads(settings.read_text(encoding="utf-8"))["providerInstances"]["antigravity"]["config"]["binaryPath"] == launcher)
        lines = remove(home, folder)
        after = json.loads(settings.read_text(encoding="utf-8"))["providerInstances"]
        check("disconnect：OmniKit 設的 Binary path 拿掉（只有它的話 config 也拿掉），使用者的留著",
              "config" not in after["antigravity"] and after["antigravity_kai"]["config"] == {"authMethod": "oauth-personal"}
              and after["antigravity_mine"]["config"]["binaryPath"] == mine)
        check("disconnect：轉接程式的資料夾整個清掉", not folder.exists() and any("刪掉轉接程式" in line for line in lines))
        for broken, unreadable in (("{壞掉", True), ("[]", True), ('{"providerInstances": []}', False)):
            settings.write_text(broken, encoding="utf-8")
            applied, removed = apply(home, folder, "uv", platform="win32"), remove(home, folder)
            check(f"T3 設定壞掉或格式不對（{broken}）：apply 不動；remove 讀不懂就說沒改回來，讀得懂就沒事可做",
                  applied == ([], []) and settings.read_text(encoding="utf-8") == broken
                  and (("沒有改回來" in removed[0]) if unreadable else removed == []))

        # T3 自己補的預設實例（settings.json 沒列）、還沒存過設定（沒有 settings.json）
        home2 = Path(t) / "home2"
        settings2 = settings_file(home2)
        settings2.parent.mkdir(parents=True)
        settings2.write_text('{\n  "favorites": [],\n  "providerInstances": {\n    "agy_x": {"driver": "antigravity"}\n  }\n}\n',
                             encoding="utf-8")
        folder2 = home2 / ".omnikit" / "acp"
        lines, keys = apply(home2, folder2, "uv", platform="win32")
        got = json.loads(settings2.read_text(encoding="utf-8"))["providerInstances"]
        launcher2 = str(folder2 / LAUNCHER)
        check("settings.json 沒列的預設實例 antigravity：寫一筆 driver 加 Binary path，跟列出來的一起接上",
              got == {"agy_x": {"driver": "antigravity", "config": {"binaryPath": launcher2}},
                      "antigravity": {"driver": "antigravity", "config": {"binaryPath": launcher2}}}
              and keys == [instance_key(home2, "agy_x"), instance_key(home2, "antigravity")])
        remove(home2, folder2)
        check("disconnect：預設實例回到只有 driver（跟 T3 自己補的一樣）",
              json.loads(settings2.read_text(encoding="utf-8"))["providerInstances"]["antigravity"] == {"driver": "antigravity"})
        settings2.unlink()
        check("T3 沒跑過（沒有 settings.json、沒有 environment-id）：不建設定檔",
              apply(home2, folder2, "uv", platform="win32") == ([], []) and not settings2.exists())
        (settings2.parent / "environment-id").write_text("x", encoding="utf-8")
        apply(home2, folder2, "uv", platform="win32")
        check("T3 跑過但還沒存過設定：新建 settings.json，只有預設實例這一筆",
              json.loads(settings2.read_text(encoding="utf-8")) == {"providerInstances": {"antigravity": {
                  "driver": "antigravity", "config": {"binaryPath": launcher2}}}})
    with tempfile.TemporaryDirectory() as t:
        home3, folder3 = Path(t) / "home", Path(t) / "acp"
        s3 = settings_file(home3)
        s3.parent.mkdir(parents=True)
        apply(home3, folder3, "uv", platform="win32", is_native=False)  # 先沒有 settings.json：不建
        s3.write_text(json.dumps({"providerInstances": {"antigravity_ryan": {"driver": "antigravity"},
                                                         "antigravity_kai": {"driver": "antigravity"}}}), encoding="utf-8")
        apply(home3, folder3, "uv", platform="win32", is_native=False)
        check("舊版 T3：照舊寫 binaryPath", state(home3, folder3, "win32", is_native=False)["antigravity_kai"][0] == OK)
        check("新版 T3、binaryPath 還在：state 回 broken", state(home3, folder3, "win32", is_native=True)["antigravity_kai"][0] == BROKEN)
        lines, keys = apply(home3, folder3, "uv", platform="win32", is_native=True)
        got = json.loads(s3.read_text(encoding="utf-8"))["providerInstances"]
        check("新版 T3：sync 拿掉 binaryPath、刪掉轉接程式、實例仍記成處理過",
              all(v == {"driver": "antigravity"} for v in got.values())
              and not folder3.exists() and len(keys) == len(got))
        check("新版 T3：state 回 native", {v[0] for v in state(home3, folder3, "win32", is_native=True).values()} == {NATIVE})
        apply(home3, folder3, "uv", platform="win32", is_native=True)
        check("新版 T3：再 sync 一次不會接回去", "binaryPath" not in s3.read_text(encoding="utf-8") and not folder3.exists())
    t3_version = real_version
    print("t3_acp selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def _raises(fn, kind):
    try:
        fn()
    except kind:
        return True
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--selftest" in sys.argv:
        return selftest()
    folder = acp_dir(homes.HOME)
    found = state(homes.HOME, folder)
    if not found:
        print("T3 Code 沒有 Antigravity 實例")
    for iid, (status, detail) in found.items():
        print(f"{iid}\t{status}\t{detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
