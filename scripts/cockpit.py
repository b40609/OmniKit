# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 控制面板（Control Panel / Cockpit）頂層入口。

用法：
  uv run scripts/cockpit.py launch [--host 127.0.0.1] [--port 3780] [--open] [--json]
  uv run scripts/cockpit.py open [--port 3780]
  uv run scripts/cockpit.py stop [--json]
  uv run scripts/cockpit.py serve [--host 127.0.0.1] [--port 3780] [--strict-port] [--open]
  uv run scripts/cockpit.py snapshot [--json] [--sync] [--write]
  uv run scripts/cockpit.py register --name <名稱> [--path <目錄>] [--id <代號>] [--parked|--unpark]
  uv run scripts/cockpit.py autostart [--install|--uninstall|--status] [--port 3780]
  uv run scripts/cockpit.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cockpit import collector, server


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError):
                continue


def _print_snapshot_text(overview: dict) -> None:
    s = overview["summary"]
    print(f"OmniKit 控制面板摘要（{overview['generated_local']}）")
    print(
        f"總計 {s['total']} 個專案｜🔴 等你 {s['blocked_on_me']}｜🟡 待收尾 {s['ready_to_settle']}"
        f"｜🟢 執行中 {s['active']}｜⚪ 停泊 {s['parked']}｜⚠️ 過期 {s['stale']}"
    )
    print("-" * 72)
    badge = {
        "blocked_on_me": "[🔴 等你]",
        "ready_to_settle": "[🟡 待收尾]",
        "active": "[🟢 執行中]",
        "parked": "[⚪ 停泊]",
    }
    for p in overview["projects"]:
        prog = p["now"]["progress"]
        step_txt = f"{prog['done']}/{prog['total']} 步" if prog["total"] is not None else "步數未填"
        slope_txt = {"uphill": "上坡", "downhill": "下坡"}.get(prog["slope"], "未標坡度")
        remote_tag = " (遠端)" if p["remote_only"] else ""
        stale_tag = f" ⚠️ {'; '.join(p['stale_reasons'])}" if p["stale"] else ""
        print(f"{badge[p['lane']]} {p['name']}{remote_tag} | {step_txt} ({slope_txt}) | {p['last_activity_age']}{stale_tag}")
        if p["now"]["conclusions"]:
            print(f"  結論：{p['now']['conclusions'][0]}")
        open_c = [c for c in p["now"]["critiques"] if not c["done"]]
        if open_c:
            print(f"  不滿意待改（{len(open_c)}）：{open_c[0]['text']}")
        if p["now"]["next_action"]:
            print(f"  下一步：{p['now']['next_action']['text']}")


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: float = 8.0,
) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {**({"Content-Type": "application/json"} if data is not None else {}), **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"raw": raw}
        return exc.code, body


def _is_port_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def probe_cockpit_health(host: str, port: int, *, timeout: float = 1.8) -> tuple[bool, dict[str, Any]]:
    """驗證指定 host:port 確實是活著的 omnikit-cockpit（不是剛好佔用同埠的其他程式）。"""
    try:
        st, body = _http_json(f"http://{host}:{port}/api/health", timeout=timeout)
        if st == 200 and isinstance(body, dict) and body.get("service") == "omnikit-cockpit":
            return True, body
    except (OSError, ValueError):
        pass
    return False, {}


def server_info_path(state_dir: Path) -> Path:
    return state_dir / "cockpit" / "server.json"


def read_server_info(state_dir: Path) -> dict[str, Any] | None:
    p = server_info_path(state_dir)
    if not p.is_file():
        return None
    try:
        doc = json.loads(collector.read_utf8(p))
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def write_server_info(state_dir: Path, *, host: str, port: int, app: server.CockpitApp) -> dict[str, Any]:
    url = f"http://{host}:{port}/"
    doc = {
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "instance": app.instance,
        "version": app.version,
        "started_at": collector.iso_utc(collector.utc_now()),
        "url": url,
    }
    collector.write_utf8_atomic(server_info_path(state_dir), json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return doc


def clear_server_info(state_dir: Path, *, instance: str) -> None:
    cur = read_server_info(state_dir)
    if cur and cur.get("instance") == instance:
        try:
            server_info_path(state_dir).unlink(missing_ok=True)
        except OSError:
            pass


def _startup_shortcut_path(appdata: Path | None = None) -> Path:
    base = appdata if appdata is not None else Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "OmniKit Cockpit 自動啟動.lnk"


def build_autostart_ps1(
    repo_root: Path,
    state_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 3780,
    strict_port: bool = True,
) -> str:
    def _ps_sq(val: Any) -> str:
        return str(val).replace("'", "''")

    uv_exe = shutil.which("uv") or str(Path(os.environ.get("LOCALAPPDATA") or "") / "Programs" / "uv" / "uv.exe")
    cockpit_script = repo_root / "scripts" / "cockpit.py"
    log_file = state_dir / "cockpit" / "server.log"
    err_file = state_dir / "cockpit" / "server.err.log"
    strict_arg = ", '--strict-port'" if strict_port else ""
    return (
        "# OmniKit 控制面板背景啟動腳本（由 scripts/cockpit.py 產生）\n"
        "$ErrorActionPreference = 'SilentlyContinue'\n"
        "$mPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')\n"
        "$uPath = [Environment]::GetEnvironmentVariable('Path', 'User')\n"
        "if ($mPath -or $uPath) { $env:Path = (@($mPath, $uPath, $env:Path) | Where-Object { $_ }) -join ';' }\n"
        f"$env:OMNIKIT_STATE_DIR = '{_ps_sq(state_dir)}'\n"
        f"$HostAddr = '{_ps_sq(host)}'\n"
        f"$Port = {int(port)}\n"
        "try {\n"
        "  $h = Invoke-RestMethod -Uri \"http://${HostAddr}:${Port}/api/health\" -TimeoutSec 2 -ErrorAction Stop\n"
        f"  if ($h.service -eq 'omnikit-cockpit' -and $h.version -eq '{_ps_sq(server.SERVER_VERSION)}') {{ exit 0 }}\n"
        "} catch {}\n"
        f"$LogDir = '{_ps_sq(log_file.parent)}'\n"
        "New-Item -ItemType Directory -Force -Path $LogDir | Out-Null\n"
        f"Start-Process -FilePath '{_ps_sq(uv_exe)}' -ArgumentList @('run', '{_ps_sq(cockpit_script)}', '--state-dir', '{_ps_sq(state_dir)}', 'serve', '--host', $HostAddr, '--port', \"$Port\"{strict_arg}) "
        f"-WorkingDirectory '{_ps_sq(repo_root)}' -WindowStyle Hidden -RedirectStandardOutput '{_ps_sq(log_file)}' -RedirectStandardError '{_ps_sq(err_file)}'\n"
    )


def _spawn_detached_windows(ps_exe: str, ps1_path: Path, repo_root: Path) -> None:
    """在 Windows 啟動不受當前 Agent 工具呼叫 Job Object 回收影響的背景腳本（無黑窗）。"""
    cmdline = f'"{ps_exe}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps1_path}"'
    esc_cmd = cmdline.replace("'", "''")
    esc_cwd = str(repo_root).replace("'", "''")
    wmi_ps = (
        "$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }; "
        f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{ CommandLine = '{esc_cmd}'; CurrentDirectory = '{esc_cwd}'; ProcessStartupInformation = $si }}; "
        "if ($r.ReturnValue -ne 0) { exit 1 }"
    )
    proc = subprocess.run(
        [ps_exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", wmi_ps],
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return

    base_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    popen_kw: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    cmd_auto = [ps_exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(ps1_path)]
    try:
        subprocess.Popen(cmd_auto, creationflags=base_flags | 0x01000000, **popen_kw)
    except OSError:
        subprocess.Popen(cmd_auto, creationflags=base_flags, **popen_kw)


def _terminate_verified_cockpit_pid(host: str, port: int, recorded_pid: int | None = None) -> bool:
    """僅在已透過 /api/health 確認目標埠是 omnikit-cockpit、但舊版無 /api/server/stop 時，安全終止佔用該埠之伺服器行程。"""
    listening_pids: set[int] = set()
    if os.name == "nt":
        ps_find = (
            f"Get-NetTCPConnection -LocalAddress '{host}' -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty OwningProcess -Unique"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_find], capture_output=True, text=True, check=False)
        for ln in (r.stdout or "").splitlines():
            if ln.strip().isdigit():
                p = int(ln.strip())
                if p > 0 and p != os.getpid():
                    listening_pids.add(p)

    candidate_pids: list[int] = sorted(listening_pids)
    if not candidate_pids and isinstance(recorded_pid, int) and recorded_pid > 0 and recorded_pid != os.getpid():
        candidate_pids.append(recorded_pid)

    for pid in candidate_pids:
        try:
            if os.name == "nt":
                if pid in listening_pids:
                    chk = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    pname = (chk.stdout or "").strip().lower()
                    allow_kill = bool(pname and any(tag in pname for tag in ("python", "uv", "pwsh", "powershell")))
                else:
                    chk = subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' -ErrorAction SilentlyContinue).CommandLine",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    cmdline = (chk.stdout or "").strip().lower()
                    allow_kill = "cockpit.py" in cmdline
                if allow_kill:
                    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"], capture_output=True, check=False)
            else:
                import signal

                chk_ps = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True, check=False)
                if "cockpit.py" in (chk_ps.stdout or ""):
                    os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    for _ in range(15):
        if not probe_cockpit_health(host, port, timeout=0.5)[0]:
            return True
        time.sleep(0.15)
    return not probe_cockpit_health(host, port, timeout=0.5)[0]


def launch_on_demand(
    state_dir: Path,
    *,
    repo_root: Path = ROOT,
    host: str = "127.0.0.1",
    preferred_port: int = 3780,
    open_browser: bool = False,
    wait_seconds: float = 15.0,
) -> dict[str, Any]:
    """按需背景啟動控制面板：已啟動且版本一致則重用；若為升級前舊版實例則自動停舊換新（修 M-P1-6）。"""
    expected_ver = server.SERVER_VERSION
    recorded = read_server_info(state_dir)
    if recorded and isinstance(recorded.get("port"), int):
        r_host = str(recorded.get("host") or host)
        r_port = int(recorded["port"])
        alive, hdoc = probe_cockpit_health(r_host, r_port)
        if alive:
            if hdoc.get("version") == expected_ver and (not recorded.get("instance") or hdoc.get("instance") == recorded.get("instance")):
                url = f"http://{r_host}:{r_port}/"
                opened = False
                if open_browser:
                    try:
                        opened = bool(webbrowser.open(url))
                    except Exception:  # noqa: BLE001
                        opened = False
                return {"ok": True, "reused": True, "version": hdoc.get("version"), "url": url, "port": r_port, "instance": hdoc.get("instance"), "opened": opened}
            stop_running_server(state_dir, default_host=r_host, default_port=r_port)

    alive_pref, hdoc_pref = probe_cockpit_health(host, preferred_port)
    if alive_pref:
        if hdoc_pref.get("version") == expected_ver:
            url = f"http://{host}:{preferred_port}/"
            opened = False
            if open_browser:
                try:
                    opened = bool(webbrowser.open(url))
                except Exception:  # noqa: BLE001
                    opened = False
            return {"ok": True, "reused": True, "version": hdoc_pref.get("version"), "url": url, "port": preferred_port, "instance": hdoc_pref.get("instance"), "opened": opened}
        stop_running_server(state_dir, default_host=host, default_port=preferred_port)

    cockpit_dir = state_dir / "cockpit"
    cockpit_dir.mkdir(parents=True, exist_ok=True)
    # 若已有舊版登入自啟腳本，順手刷新為新版腳本內容
    auto_ps1 = cockpit_dir / "autostart-cockpit.ps1"
    if auto_ps1.is_file():
        try:
            auto_ps1.write_text(build_autostart_ps1(repo_root, state_dir, host=host, port=preferred_port, strict_port=True), encoding="utf-8")
        except OSError:
            pass
    if os.name == "nt":
        ps1_path = cockpit_dir / "launch-on-demand.ps1"
        ps1_path.write_text(
            build_autostart_ps1(repo_root, state_dir, host=host, port=preferred_port, strict_port=False),
            encoding="utf-8",
        )
        ps_exe = str(Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        _spawn_detached_windows(ps_exe, ps1_path, repo_root)
    else:
        uv_exe = shutil.which("uv")
        cmd = (
            [uv_exe, "run", str(repo_root / "scripts" / "cockpit.py"), "--state-dir", str(state_dir), "serve", "--host", host, "--port", str(preferred_port)]
            if uv_exe
            else [sys.executable, str(repo_root / "scripts" / "cockpit.py"), "--state-dir", str(state_dir), "serve", "--host", host, "--port", str(preferred_port)]
        )
        log_f = open(cockpit_dir / "server.log", "ab")
        err_f = open(cockpit_dir / "server.err.log", "ab")
        try:
            subprocess.Popen(cmd, cwd=str(repo_root), stdin=subprocess.DEVNULL, stdout=log_f, stderr=err_f, start_new_session=True)
        finally:
            log_f.close()
            err_f.close()

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        info = read_server_info(state_dir)
        check_ports = [int(info["port"])] if info and isinstance(info.get("port"), int) else [preferred_port]
        for p in check_ports:
            alive, hdoc = probe_cockpit_health(host, p, timeout=1.2)
            if alive and hdoc.get("version") == expected_ver:
                url = f"http://{host}:{p}/"
                opened = False
                if open_browser:
                    try:
                        opened = bool(webbrowser.open(url))
                    except Exception:  # noqa: BLE001
                        opened = False
                return {"ok": True, "reused": False, "version": hdoc.get("version"), "url": url, "port": p, "instance": hdoc.get("instance"), "opened": opened}
        time.sleep(0.25)

    return {
        "ok": False,
        "reused": False,
        "url": f"http://{host}:{preferred_port}/",
        "error": f"等待本機控制面板啟動逾時（請查看 {cockpit_dir / 'server.err.log'}）",
    }


def stop_running_server(
    state_dir: Path,
    *,
    default_host: str = "127.0.0.1",
    default_port: int = 3780,
    explicit_port: int | None = None,
) -> dict[str, Any]:
    info = read_server_info(state_dir)
    host = str((info or {}).get("host") or default_host)
    port = int(explicit_port) if explicit_port is not None else int((info or {}).get("port") or default_port)
    rec_pid = int(info["pid"]) if info and isinstance(info.get("pid"), int) else None
    alive, _ = probe_cockpit_health(host, port)
    if not alive:
        if explicit_port is None:
            server_info_path(state_dir).unlink(missing_ok=True)
        return {"ok": True, "stopped": False, "port": port, "note": "目前沒有執行中的控制面板伺服器"}
    stop_http_ok = False
    try:
        st_s, ses = _http_json(f"http://{host}:{port}/api/session", timeout=2.0)
        tok = ses.get("token") if st_s == 200 and isinstance(ses, dict) else None
        if tok:
            st_stop, _ = _http_json(
                f"http://{host}:{port}/api/server/stop",
                method="POST",
                payload={},
                headers={"X-OmniKit-Token": str(tok)},
                timeout=2.0,
            )
            stop_http_ok = st_stop == 200
    except OSError:
        pass
    if stop_http_ok:
        for _ in range(20):
            if not probe_cockpit_health(host, port, timeout=0.6)[0]:
                server_info_path(state_dir).unlink(missing_ok=True)
                return {"ok": True, "stopped": True, "port": port}
            time.sleep(0.15)
    # 舊版無 /api/server/stop（404）或優雅關閉逾時：透過已驗證之 PID 後備終止
    if _terminate_verified_cockpit_pid(host, port, recorded_pid=rec_pid):
        server_info_path(state_dir).unlink(missing_ok=True)
        return {"ok": True, "stopped": True, "port": port, "fallback_killed": True}
    return {"ok": False, "stopped": False, "port": port, "error": "伺服器未在預期時間內結束"}


def _win_fs_path(path: Path) -> str:
    s = os.path.abspath(str(path))
    if os.name != "nt" or s.startswith("\\\\?\\"):
        return s
    if s.startswith("\\\\"):
        return "\\\\?\\UNC\\" + s[2:]
    return "\\\\?\\" + s


def _build_windows_shortcut_bytes(
    *,
    target_path: str,
    arguments: str,
    working_dir: str,
    window_style: int = 7,
) -> bytes:
    """透過原生 Unicode COM (IShellLinkW + IPersistStream) 於記憶體產生 .lnk 二進位資料。

    徹底避開舊版 WScript.Shell 在英文版 Windows (cp1252) 將中文／Unicode 路徑轉成 `????`
    以及超過 MAX_PATH 儲存路徑失敗的問題（修 PR #12 P1-A）。
    """
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.windll.ole32
    kernel32 = ctypes.windll.kernel32

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_GUID)]
    ole32.CLSIDFromString.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CreateStreamOnHGlobal.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(ctypes.c_void_p)]
    ole32.CreateStreamOnHGlobal.restype = ctypes.c_long
    ole32.GetHGlobalFromStream.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
    ole32.GetHGlobalFromStream.restype = ctypes.c_long

    kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    def _guid(text: str) -> _GUID:
        g = _GUID()
        hr_g = ole32.CLSIDFromString(text, ctypes.byref(g))
        if hr_g < 0:
            raise OSError(f"CLSIDFromString 失敗: {hr_g:#x}")
        return g

    def _vtbl(ptr: ctypes.c_void_p, idx: int, restype: Any, *argtypes: Any):
        vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])
        return lambda *a: fn(ptr, *a)

    def _chk(hr_val: int, step: str) -> None:
        if hr_val < 0:
            raise OSError(f"建立 Windows 捷徑失敗 ({step}): {hr_val & 0xFFFFFFFF:#x}")

    hr_init = ole32.CoInitializeEx(None, 0x2)
    need_uninit = hr_init in (0, 1)
    if hr_init < 0 and (hr_init & 0xFFFFFFFF) != 0x80010106:
        _chk(hr_init, "CoInitializeEx")

    clsid_shell_link = _guid("{00021401-0000-0000-C000-000000000046}")
    iid_shell_link_w = _guid("{000214F9-0000-0000-C000-000000000046}")
    iid_persist_stream = _guid("{00000109-0000-0000-C000-000000000046}")

    sl = ctypes.c_void_p()
    ps = ctypes.c_void_p()
    stm = ctypes.c_void_p()
    try:
        _chk(ole32.CoCreateInstance(ctypes.byref(clsid_shell_link), None, 1, ctypes.byref(iid_shell_link_w), ctypes.byref(sl)), "CoCreateInstance")
        safe_wd = working_dir if len(working_dir) < 240 else str(Path(target_path).parent)
        _chk(_vtbl(sl, 20, ctypes.c_long, ctypes.c_wchar_p)(target_path), "SetPath")
        _chk(_vtbl(sl, 11, ctypes.c_long, ctypes.c_wchar_p)(arguments), "SetArguments")
        _chk(_vtbl(sl, 9, ctypes.c_long, ctypes.c_wchar_p)(safe_wd), "SetWorkingDirectory")
        _chk(_vtbl(sl, 15, ctypes.c_long, ctypes.c_int)(int(window_style)), "SetShowCmd")
        _chk(
            _vtbl(sl, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(iid_persist_stream), ctypes.byref(ps)),
            "QueryInterface(IPersistStream)",
        )
        _chk(ole32.CreateStreamOnHGlobal(None, True, ctypes.byref(stm)), "CreateStreamOnHGlobal")
        _chk(_vtbl(ps, 6, ctypes.c_long, ctypes.c_void_p, wintypes.BOOL)(stm, True), "IPersistStream::Save")

        hglob = wintypes.HANDLE()
        _chk(ole32.GetHGlobalFromStream(stm, ctypes.byref(hglob)), "GetHGlobalFromStream")
        size = kernel32.GlobalSize(hglob)
        ptr = kernel32.GlobalLock(hglob)
        if not ptr:
            raise OSError("GlobalLock 失敗")
        try:
            return ctypes.string_at(ptr, size)
        finally:
            kernel32.GlobalUnlock(hglob)
    finally:
        for com_ptr in (stm, ps, sl):
            if com_ptr.value:
                _vtbl(com_ptr, 2, ctypes.c_ulong)()
        if need_uninit:
            ole32.CoUninitialize()


def _read_windows_shortcut_info(raw: bytes) -> dict[str, Any]:
    """從 .lnk 二進位資料經原生 Unicode COM (IShellLinkW) 讀回捷徑屬性，供自我測試與單元測試驗證無失真。"""
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.windll.ole32
    kernel32 = ctypes.windll.kernel32

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_GUID)]
    ole32.CLSIDFromString.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CreateStreamOnHGlobal.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(ctypes.c_void_p)]
    ole32.CreateStreamOnHGlobal.restype = ctypes.c_long

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    def _guid(text: str) -> _GUID:
        g = _GUID()
        ole32.CLSIDFromString(text, ctypes.byref(g))
        return g

    def _vtbl(ptr: ctypes.c_void_p, idx: int, restype: Any, *argtypes: Any):
        vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])
        return lambda *a: fn(ptr, *a)

    hr_init = ole32.CoInitializeEx(None, 0x2)
    need_uninit = hr_init in (0, 1)
    clsid_shell_link = _guid("{00021401-0000-0000-C000-000000000046}")
    iid_shell_link_w = _guid("{000214F9-0000-0000-C000-000000000046}")
    iid_persist_stream = _guid("{00000109-0000-0000-C000-000000000046}")

    sl = ctypes.c_void_p()
    ps = ctypes.c_void_p()
    stm = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(ctypes.byref(clsid_shell_link), None, 1, ctypes.byref(iid_shell_link_w), ctypes.byref(sl))
        _vtbl(sl, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(iid_persist_stream), ctypes.byref(ps))
        hglob = kernel32.GlobalAlloc(0x0002, len(raw))
        ptr = kernel32.GlobalLock(hglob)
        ctypes.memmove(ptr, raw, len(raw))
        kernel32.GlobalUnlock(hglob)
        ole32.CreateStreamOnHGlobal(hglob, True, ctypes.byref(stm))
        _vtbl(ps, 5, ctypes.c_long, ctypes.c_void_p)(stm)
        arg_buf = ctypes.create_unicode_buffer(2048)
        wd_buf = ctypes.create_unicode_buffer(2048)
        show_cmd = ctypes.c_int()
        _vtbl(sl, 10, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)(arg_buf, 2048)
        _vtbl(sl, 8, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)(wd_buf, 2048)
        _vtbl(sl, 14, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(ctypes.byref(show_cmd))
        return {"arguments": arg_buf.value, "working_dir": wd_buf.value, "window_style": show_cmd.value}
    finally:
        for com_ptr in (stm, ps, sl):
            if com_ptr.value:
                _vtbl(com_ptr, 2, ctypes.c_ulong)()
        if need_uninit:
            ole32.CoUninitialize()


def manage_autostart(
    state_dir: Path,
    *,
    action: str,
    repo_root: Path = ROOT,
    host: str = "127.0.0.1",
    port: int = 3780,
    appdata: Path | None = None,
    start_now: bool = True,
) -> dict:
    ps1_path = state_dir / "cockpit" / "autostart-cockpit.ps1"
    lnk_path = _startup_shortcut_path(appdata)
    lnk_fs = _win_fs_path(lnk_path)
    ps1_fs = _win_fs_path(ps1_path)
    if action == "uninstall":
        for raw_p in (lnk_fs, ps1_fs):
            if os.path.isfile(raw_p):
                collector.fs_retry(os.unlink, raw_p)
        alive, _ = probe_cockpit_health(host, port)
        return {"action": "uninstall", "installed": False, "shortcut": str(lnk_path), "listening": alive}

    if action == "install":
        os.makedirs(_win_fs_path(ps1_path.parent), exist_ok=True)
        ps1_bytes = build_autostart_ps1(repo_root, state_dir, host=host, port=port, strict_port=True).encode("utf-8")
        collector.fs_retry(lambda: open(ps1_fs, "wb").write(ps1_bytes))
        if os.name == "nt":
            os.makedirs(_win_fs_path(lnk_path.parent), exist_ok=True)
            ps_exe = str(Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
            lnk_args = f'-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps1_path}"'
            raw_lnk = _build_windows_shortcut_bytes(
                target_path=ps_exe,
                arguments=lnk_args,
                working_dir=str(repo_root),
                window_style=7,
            )
            tmp_fs = _win_fs_path(lnk_path.parent / f".ok-lnk-{os.getpid()}.tmp")
            try:
                with open(tmp_fs, "wb") as fh:
                    fh.write(raw_lnk)
                collector.fs_retry(os.replace, tmp_fs, lnk_fs)
            finally:
                if os.path.exists(tmp_fs):
                    try:
                        os.unlink(tmp_fs)
                    except OSError:
                        pass
            if start_now and not probe_cockpit_health(host, port)[0]:
                _spawn_detached_windows(ps_exe, ps1_path, repo_root)
                for _ in range(40):
                    if probe_cockpit_health(host, port, timeout=1.0)[0]:
                        break
                    time.sleep(0.2)

    alive, _ = probe_cockpit_health(host, port)
    installed_ok = os.path.isfile(lnk_fs) if os.name == "nt" else os.path.isfile(ps1_fs)
    return {
        "action": action,
        "installed": installed_ok,
        "shortcut": str(lnk_path),
        "script": str(ps1_path),
        "host": host,
        "port": port,
        "listening": alive,
    }


def selftest() -> int:
    """離線完整自我測試（不連網、不寫真實 ~/.omnikit、相容 Windows cp950 與長路徑）。"""
    fails: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        mark = "ok  " if cond else "FAIL"
        print(f"{mark} {label}" + (f" ({detail})" if detail else ""))
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory(prefix="ok-cp-") as tmp:
        root = Path(tmp)
        state = root / "state"
        repo_a = root / "Alpha 專案"
        repo_a.mkdir(parents=True)

        def git(*args: str) -> None:
            flags = ["-c", "core.longpaths=true", "-c", "commit.gpgsign=false"]
            if args and args[0] != "init":
                flags.extend(["--git-dir=.git", "--work-tree=."])
            subprocess.run(["git", *flags, *args], cwd=str(repo_a), check=True, capture_output=True)

        git("init", "--quiet", ".")
        git("config", "core.longpaths", "true")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.com")
        (repo_a / "README.md").write_text("hello\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-m", "init alpha")
        (repo_a / "dirty.txt").write_text("wip\n", encoding="utf-8")

        old_time = (datetime.now(UTC) - timedelta(hours=5)).astimezone().strftime("%Y-%m-%d %H:%M")
        alpha_now = state / "status" / "Alpha" / "NOW.md"
        alpha_now.parent.mkdir(parents=True)
        alpha_now.write_text(
            f"# Alpha\n\n- 更新時間：{old_time}\n- 專案路徑：`{repo_a}`\n\n"
            "## 完工路徑\n還有 2 步，完成 3 步（下坡）\n- [x] 建置核心\n- [ ] 行動端驗證\n\n"
            "## 目前結論\n- 採用單一 PWA 架構\n\n"
            "## 不滿意待改\n- [ ] 卡片太擠 -> 手機字體偏小 -> 調整間距與字級 >= 16px\n\n"
            "## 等使用者決定的事\n- 決定上線埠號\n\n"
            "## 下一步\n- 【等使用者】確認首頁資訊密度\n",
            encoding="utf-8",
        )
        remote_now = state / "status" / "CompanyOnly" / "NOW.md"
        remote_now.parent.mkdir(parents=True)
        remote_now.write_text(
            "# CompanyOnly\n\n- 更新時間：2026-11-24 10:00\n- 專案路徑：`Z:\\nonexistent\\CompanyOnly`\n\n"
            "## 完工路徑\n- [x] 完成資料清洗\n- [ ] 產出查核報告\n\n"
            "## 目前結論\n- 頻響分析改採新濾波參數\n\n"
            "## 下一步\n- 【agent 可直接做】跑驗證腳本\n",
            encoding="utf-8",
        )

        def fake_t3(path: Path) -> list[dict]:
            if path.resolve() == repo_a.resolve():
                return [
                    {
                        "threadId": "th-1",
                        "title": "Alpha 主線",
                        "status": "completed",
                        "settled": False,
                        "itemCount": 1250,
                        "updatedAt": collector.iso_utc(datetime.now(UTC)),
                        "model": "gemini-4-neon",
                        "providerInstanceId": "antigravity_main",
                        "link": "https://app.t3.codes/threads/env1/th-1",
                    }
                ]
            return []

        ov = collector.collect_overview(state, default_repo_root=None, t3_runner=fake_t3)
        by_id = {p["id"]: p for p in ov["projects"]}
        check("多機聯集探索 2 個專案", set(by_id.keys()) == {"Alpha", "CompanyOnly"}, str(list(by_id.keys())))
        check("Alpha 判為 blocked_on_me 且過期紅燈", by_id["Alpha"]["lane"] == "blocked_on_me" and by_id["Alpha"]["stale"])
        check(
            "Alpha 偵測到 Git dirty 與 T3 超載/待 settle",
            by_id["Alpha"]["git"]["dirty_count"] == 1
            and by_id["Alpha"]["t3"]["overloaded_count"] == 1
            and by_id["Alpha"]["t3"]["ready_to_settle_count"] == 1,
        )
        check(
            "Alpha 四格解析（步數 3/5、下坡、三段式不滿意）",
            by_id["Alpha"]["now"]["progress"]["done"] == 3
            and by_id["Alpha"]["now"]["progress"]["total"] == 5
            and by_id["Alpha"]["now"]["progress"]["slope"] == "downhill"
            and by_id["Alpha"]["now"]["critiques"][0]["criteria"] == "調整間距與字級 >= 16px",
        )
        check("CompanyOnly 標記為遠端專案且不報錯", by_id["CompanyOnly"]["remote_only"] is True and by_id["CompanyOnly"]["now"]["progress"]["total"] == 2)

        fake_home = root / "home"
        (fake_home / ".codex").mkdir(parents=True)
        app = server.CockpitApp(
            state_dir=state,
            home_dir=fake_home,
            default_repo_root=None,
            t3_runner=fake_t3,
            cache_ttl=0,
            allowed_hosts={"box.example.ts.net"},
            token="selftest-token",
        )
        tok = {"X-OmniKit-Token": app.token}
        httpd = server.create_server("127.0.0.1", 0, app=app)
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            # 驗證排他埠綁定與自動順移（P0-1）
            blocked_dup = False
            try:
                dup = server.create_server("127.0.0.1", port, app=app)
                dup.server_close()
            except OSError:
                blocked_dup = True
            check("ExclusiveHTTPServer 阻止雙進程重複綁定同埠（P0-1）", blocked_dup)

            fallback_srv = server.bind_server("127.0.0.1", port, app=app, strict_port=False)
            fb_port = fallback_srv.server_address[1]
            fallback_srv.server_close()
            check("bind_server 在首選埠被佔用時自動順移至下一可用埠", fb_port > port, f"{port} -> {fb_port}")

            base = f"http://127.0.0.1:{port}"
            st_h, body_h = _http_json(f"{base}/api/health")
            check(
                "GET /api/health 回傳 200、instance 與 version",
                st_h == 200 and body_h.get("ok") is True and body_h.get("instance") == app.instance,
            )

            st_boot, boot = _http_json(f"{base}/api/bootstrap")
            check(
                "GET /api/bootstrap 回傳精選工作台、習慣清單與 Context 預算",
                st_boot == 200 and len(boot["workbench"]["items"]) >= 8 and len(boot["habits_catalog"]) == 9,
            )

            st_o, body_o = _http_json(f"{base}/api/overview")
            check("GET /api/overview 回傳完整摘要", st_o == 200 and body_o["summary"]["total"] == 2)

            st_add, body_add = _http_json(
                f"{base}/api/projects/Alpha/critiques",
                method="POST",
                payload={"text": "按鈕太靠邊需要加間距"},
                headers=tok,
            )
            check("POST 新增不滿意待改成功", st_add == 201 and len(body_add.get("critiques", [])) == 2)
            raw_after = alpha_now.read_text(encoding="utf-8")
            check("新增待改保留原更新時間（不掩蓋過期紅燈）", f"更新時間：{old_time}" in raw_after)

            st_tog, body_tog = _http_json(
                f"{base}/api/projects/Alpha/critiques/0",
                method="PATCH",
                payload={"done": True},
                headers=tok,
            )
            check("PATCH 勾銷不滿意待改成功", st_tog == 200 and body_tog["critiques"][0]["done"] is True)

            st_set, _ = _http_json(
                f"{base}/api/settings",
                method="PATCH",
                payload={"t3_base_url": "https://t3.example.ts.net:2388"},
                headers=tok,
            )
            st_o2, body_o2 = _http_json(f"{base}/api/overview")
            alpha2 = next(p for p in body_o2["projects"] if p["id"] == "Alpha")
            check(
                "設定 T3 Tailscale URL 後正確改寫深連結",
                st_set == 200 and st_o2 == 200 and alpha2["primary_t3_url"] == "https://t3.example.ts.net:2388/threads/env1/th-1",
            )

            st_bad, _ = _http_json(
                f"{base}/api/projects/..%2Fevil/critiques",
                method="POST",
                payload={"text": "bad"},
                headers=tok,
            )
            check("路徑穿越防護拒絕 .. 專案代號", st_bad == 400)

            # 安全邊界檢查（Host 白名單、Sec-Fetch-Site、Origin 埠號精準比對、Tailscale 唯讀）
            st_ses, ses = _http_json(f"{base}/api/session")
            check("本機開：/api/session 給 token、可寫", st_ses == 200 and ses == {"writable": True, "mode": "local", "token": "selftest-token"})
            st_sfs, _ = _http_json(f"{base}/api/session", headers={"Sec-Fetch-Site": "cross-site"})
            check("跨站讀取 /api/session（Sec-Fetch-Site: cross-site）拒絕 403", st_sfs == 403)
            st_evil, _ = _http_json(f"{base}/api/health", headers={"Host": "evil.example"})
            check("不在白名單的 Host（DNS rebinding）讀也 403", st_evil == 403)
            st_ts, ses_ts = _http_json(f"{base}/api/session", headers={"Host": "box.example.ts.net:2389", "X-Forwarded-For": "100.64.0.9"})
            check("經 Tailscale：可以讀、不給 token", st_ts == 200 and ses_ts["writable"] is False and ses_ts["token"] is None)
            st_tsw, _ = _http_json(
                f"{base}/api/projects/Alpha/critiques",
                method="POST",
                payload={"text": "x"},
                headers={**tok, "Host": "box.example.ts.net", "Tailscale-User-Login": "u@example.test"},
            )
            check("經 Tailscale：帶對的 token 寫入也 403", st_tsw == 403)
            st_org_port, _ = _http_json(
                f"{base}/api/projects/Alpha/critiques",
                method="POST",
                payload={"text": "x"},
                headers={**tok, "Origin": f"http://127.0.0.1:{port + 1}"},
            )
            check("Origin 同為 127.0.0.1 但埠號不同：拒絕 403", st_org_port == 403)
            check("strip_log_query 剝除日誌內 URL 查詢參數", "secret" not in server.strip_log_query('"GET /api/session?secret=123 HTTP/1.1" 200 -'))

            with urllib.request.urlopen(f"{base}/", timeout=5) as resp:
                html_text = resp.read().decode("utf-8")
                check("GET / 正常提供 PWA 首頁且無 black-translucent", resp.status == 200 and "OmniKit" in html_text and "black-translucent" not in html_text)
        finally:
            httpd.shutdown()
            httpd.server_close()

        fake_appdata = root / "Roaming ⚡テスト"
        st_auto = manage_autostart(state, action="install", repo_root=ROOT, port=37809, appdata=fake_appdata, start_now=False)
        with open(_win_fs_path(Path(st_auto["script"])), encoding="utf-8") as fh_ps1:
            ps1_txt = fh_ps1.read()
        lnk_ok = st_auto["installed"] is True and "/api/health" in ps1_txt
        if os.name == "nt" and lnk_ok:
            with open(_win_fs_path(Path(st_auto["shortcut"])), "rb") as fh_lnk:
                lnk_info = _read_windows_shortcut_info(fh_lnk.read())
            lnk_ok = (
                str(st_auto["script"]) in lnk_info["arguments"]
                and "????" not in lnk_info["arguments"]
                and lnk_info["window_style"] == 7
            )
        check(
            "autostart --install 產生啟動腳本（驗證 /api/health 而非裸 TCP）與原生 Unicode Startup 捷徑",
            lnk_ok,
        )
        st_un = manage_autostart(state, action="uninstall", repo_root=ROOT, port=37809, appdata=fake_appdata, start_now=False)
        check("autostart --uninstall 乾淨移除捷徑與腳本", st_un["installed"] is False and not os.path.exists(_win_fs_path(Path(st_auto["script"]))))

    return 1 if fails else 0


def main() -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(description="OmniKit 本機控制面板（桌面設定商店＋Tailscale 手機 PWA）")
    parser.add_argument("--selftest", action="store_true", help="執行離線完整自我測試")
    parser.add_argument("--state-dir", type=Path, default=None, help="指定狀態目錄（預設 ~/.omnikit）")
    sub = parser.add_subparsers(dest="cmd")

    p_launch = sub.add_parser("launch", help="按需背景啟動控制面板（已啟動則直接重用）")
    p_launch.add_argument("--host", default="127.0.0.1", help="監聽位址（預設 127.0.0.1）")
    p_launch.add_argument("--port", type=int, default=3780, help="首選埠號（預設 3780，佔用時自動順移）")
    p_launch.add_argument("--open", action="store_true", help="就緒後自動開啟瀏覽器")
    p_launch.add_argument("--json", action="store_true", help="輸出 JSON 結果")

    p_open = sub.add_parser("open", help="按需啟動並立即在預設瀏覽器開啟控制面板")
    p_open.add_argument("--host", default="127.0.0.1", help="監聽位址（預設 127.0.0.1）")
    p_open.add_argument("--port", type=int, default=3780, help="首選埠號（預設 3780）")

    p_stop = sub.add_parser("stop", help="停止目前背景執行中的控制面板伺服器")
    p_stop.add_argument("--host", default="127.0.0.1", help="監聽位址（預設 127.0.0.1）")
    p_stop.add_argument("--port", type=int, default=None, help="指定連接埠（不指定則讀 server.json 或預設 3780）")
    p_stop.add_argument("--json", action="store_true", help="輸出 JSON 結果")

    p_serve = sub.add_parser("serve", help="前景啟動本機控制面板伺服器")
    p_serve.add_argument("--host", default="127.0.0.1", help="監聽位址（預設 127.0.0.1）")
    p_serve.add_argument("--port", type=int, default=3780, help="監聽埠號（預設 3780）")
    p_serve.add_argument("--strict-port", action="store_true", help="禁止連接埠自動順移（供登入自啟／Tailscale 綁定使用）")
    p_serve.add_argument("--open", action="store_true", help="啟動後自動開啟瀏覽器")

    p_snap = sub.add_parser("snapshot", help="輸出跨專案指揮台狀態快照")
    p_snap.add_argument("--json", action="store_true", help="輸出 UTF-8 JSON")
    p_snap.add_argument("--sync", action="store_true", help="先對狀態庫執行安全同步")
    p_snap.add_argument("--write", action="store_true", help="寫入 ~/.omnikit/cockpit/snapshot.json")

    p_reg = sub.add_parser("register", help="登記或更新專案到控制面板")
    p_reg.add_argument("--name", required=True, help="顯示名稱")
    p_reg.add_argument("--id", default=None, help="專案代號（預設由名稱產生）")
    p_reg.add_argument("--path", default=None, help="本機專案目錄")
    p_reg.add_argument("--parked", action="store_true", help="標記為手動停泊")
    p_reg.add_argument("--unpark", action="store_true", help="取消手動停泊")
    p_reg.add_argument("--remove", action="store_true", help="從清單移除")

    p_auto = sub.add_parser("autostart", help="管理 Windows 登入背景自啟（Startup 資料夾無黑窗啟動）")
    ag = p_auto.add_mutually_exclusive_group()
    ag.add_argument("--install", action="store_true", help="安裝登入自啟捷徑並立即確認服務已啟動")
    ag.add_argument("--uninstall", action="store_true", help="移除登入自啟捷徑")
    ag.add_argument("--status", action="store_true", help="查詢登入自啟與監聽狀態（預設）")
    p_auto.add_argument("--host", default="127.0.0.1", help="監聽位址（預設 127.0.0.1）")
    p_auto.add_argument("--port", type=int, default=3780, help="監聽埠號（預設 3780）")
    p_auto.add_argument("--no-start", action="store_true", help="只安裝自啟捷徑，不立即啟動服務")

    args = parser.parse_args()
    if args.selftest:
        return selftest()

    sdir = args.state_dir if args.state_dir is not None else collector.default_state_dir()

    if args.cmd in ("launch", "open"):
        want_open = True if args.cmd == "open" else bool(getattr(args, "open", False))
        res = launch_on_demand(sdir, host=args.host, preferred_port=args.port, open_browser=want_open)
        if getattr(args, "json", False):
            print(json.dumps(res, ensure_ascii=False))
        elif res.get("ok"):
            print(f"OmniKit 控制面板：{res['url']}")
        else:
            print(res.get("error") or "啟動失敗", file=sys.stderr)
        return 0 if res.get("ok") else 1

    if args.cmd == "stop":
        res = stop_running_server(sdir, default_host=args.host, explicit_port=args.port)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            print("已停止 OmniKit 控制面板伺服器。" if res.get("stopped") else (res.get("note") or res.get("error") or ""))
        return 0 if res.get("ok") else 1

    if args.cmd == "autostart":
        act = "install" if args.install else ("uninstall" if args.uninstall else "status")
        res = manage_autostart(sdir, action=act, host=args.host, port=args.port, start_now=not args.no_start)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "snapshot":
        ov = collector.collect_overview(sdir, sync=args.sync)
        if args.write:
            collector.write_snapshot(sdir, ov)
        if args.json:
            print(json.dumps(ov, ensure_ascii=False, indent=2))
        else:
            _print_snapshot_text(ov)
        return 0

    if args.cmd == "register":
        parked_val = True if args.parked else (False if args.unpark else None)
        res = collector.register_project(
            sdir,
            name=args.name,
            path=args.path,
            project_id=args.id,
            parked=parked_val,
            remove=args.remove,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    # 預設（或 serve）啟動前景伺服器
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 3780)
    strict_port = bool(getattr(args, "strict_port", False))
    should_open = bool(getattr(args, "open", False))
    app = server.CockpitApp(state_dir=sdir)
    httpd = server.bind_server(host, port, app=app, strict_port=strict_port)
    actual_port = httpd.server_address[1]
    write_server_info(sdir, host=host, port=actual_port, app=app)
    url = f"http://{host}:{actual_port}/"
    print(f"OmniKit 控制面板已啟動：{url}")
    print(f"狀態目錄：{sdir}")
    print("按 Ctrl+C 停止服務。")
    if should_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 OmniKit 控制面板。")
    finally:
        clear_server_info(sdir, instance=app.instance)
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
